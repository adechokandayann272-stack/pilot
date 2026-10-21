#!/usr/bin/env python3
"""Local, same-origin bridge for syncing Poste de pilotage data to Notion.

The Notion integration secret is held only in this process (or read from the
process environment); it is never written to the project JSON or browser storage.
Run this script and open http://127.0.0.1:8765/ to configure Notion in the app settings.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
MAX_REQUEST_BYTES = 3 * 1024 * 1024
MAX_PROJECT_BYTES = 2 * 1024 * 1024
RICH_TEXT_CHUNK = 1800
RICH_TEXT_PARTS_PER_BLOCK = 90
MAX_NOTION_BATCH_BYTES = 400 * 1024

_CONFIG_LOCK = threading.RLock()
_RATE_LOCK = threading.Lock()
_LAST_NOTION_REQUEST = 0.0


def normalize_page_id(value: str) -> str:
    """Accept a UUID or a Notion page URL and return a canonical UUID."""
    candidate = str(value or "").strip()
    match = re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{32}",
        candidate,
    )
    if not match:
        raise ValueError("L'ID ou l'URL de la page Notion ne contient pas d'identifiant valide.")
    try:
        return str(uuid.UUID(match.group(0)))
    except ValueError as exc:
        raise ValueError("L'identifiant de page Notion n'est pas valide.") from exc


def _environment_config() -> tuple[str, str, str]:
    token = os.environ.get("NOTION_TOKEN", "").strip()
    raw_page_id = os.environ.get("NOTION_PARENT_PAGE_ID", "").strip()
    try:
        page_id = normalize_page_id(raw_page_id) if raw_page_id else ""
    except ValueError:
        page_id = ""
    return token, page_id, "environment"


_INITIAL_TOKEN, _INITIAL_PAGE_ID, _INITIAL_SOURCE = _environment_config()
_CONFIG: dict[str, str] = {
    "token": _INITIAL_TOKEN,
    "parent_page_id": _INITIAL_PAGE_ID,
    "source": _INITIAL_SOURCE,
}


def _get_config() -> tuple[str, str, str]:
    with _CONFIG_LOCK:
        return (_CONFIG["token"], _CONFIG["parent_page_id"], _CONFIG["source"])


def _set_config(token: str, parent_page_id: str, source: str) -> None:
    with _CONFIG_LOCK:
        _CONFIG.update(token=token, parent_page_id=parent_page_id, source=source)


def _clear_config() -> None:
    # Environment credentials are deliberately not reloaded here. Clear both
    # the active session and this process's environment copies on disconnect.
    os.environ.pop("NOTION_TOKEN", None)
    os.environ.pop("NOTION_PARENT_PAGE_ID", None)
    _set_config("", "", "session")


class NotionAPIError(RuntimeError):
    pass


def _notion_request(token: str, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make a rate-limited Notion API request without exposing the secret in errors."""
    global _LAST_NOTION_REQUEST
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"

    for attempt in range(4):
        with _RATE_LOCK:
            wait = 0.34 - (time.monotonic() - _LAST_NOTION_REQUEST)
            if wait > 0:
                time.sleep(wait)
            _LAST_NOTION_REQUEST = time.monotonic()
        request = Request(NOTION_API + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=35) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
            except (TypeError, ValueError):
                detail = {}
            message = str(detail.get("message") or detail.get("code") or "Erreur API")
            message = message.replace(token, "[clé masquée]")
            if exc.code == 429 and attempt < 3:
                try:
                    delay = float(exc.headers.get("Retry-After", "1"))
                except (TypeError, ValueError):
                    delay = 1.0
                time.sleep(max(0.5, min(delay, 10.0)))
                continue
            if exc.code >= 500 and attempt < 3:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise NotionAPIError(f"Notion API ({exc.code}) : {message}") from None
        except URLError as exc:
            reason = str(getattr(exc, "reason", "connexion impossible"))
            raise NotionAPIError(f"Connexion à l'API Notion impossible : {reason}") from None
        except (TimeoutError, OSError) as exc:
            raise NotionAPIError(f"Erreur réseau vers Notion : {exc}") from None
    raise NotionAPIError("Notion n'a pas répondu après plusieurs tentatives.")


def _title_of_page(page: dict[str, Any]) -> str:
    properties = page.get("properties") or {}
    for prop in properties.values():
        if prop.get("type") == "title":
            return "".join(part.get("plain_text", "") for part in prop.get("title", []))
    return ""


def _chunks(text: str, size: int = RICH_TEXT_CHUNK) -> list[str]:
    text = str(text or "")
    if not text:
        return [""]
    return [text[index:index + size] for index in range(0, len(text), size)]


def _rich_text(text: str) -> list[dict[str, Any]]:
    return [
        {"type": "text", "text": {"content": part}}
        for part in _chunks(text)
    ]


def _text_blocks(text: str, block_type: str = "paragraph", language: str | None = None) -> list[dict[str, Any]]:
    """Create Notion blocks within rich-text item/request limits."""
    parts = _chunks(text)
    blocks: list[dict[str, Any]] = []
    for start in range(0, len(parts), RICH_TEXT_PARTS_PER_BLOCK):
        rich = [
            {"type": "text", "text": {"content": part}}
            for part in parts[start:start + RICH_TEXT_PARTS_PER_BLOCK]
        ]
        content: dict[str, Any] = {"rich_text": rich}
        if language:
            content["language"] = language
        blocks.append({"object": "block", "type": block_type, block_type: content})
    return blocks


def _heading(text: str, level: int = 2) -> dict[str, Any]:
    kind = f"heading_{level}"
    return {"object": "block", "type": kind, kind: {"rich_text": _rich_text(text[:RICH_TEXT_CHUNK])}}


def _get_record(suivi: dict[str, Any], number: Any) -> dict[str, Any]:
    return suivi.get(str(number), suivi.get(number, {})) or {}


def _effective_tasks(project_file: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    base = project_file.get("base") or {}
    suivi = project_file.get("suivi") or {}
    tasks: list[tuple[dict[str, Any], dict[str, Any]]] = []
    known: set[str] = set()
    for original in base.get("tasks") or []:
        if not isinstance(original, dict):
            continue
        number = original.get("n", "?")
        record = _get_record(suivi, number)
        effective = dict(original)
        if isinstance(record.get("mod"), dict):
            effective.update(record["mod"])
        effective["st"] = "Terminé" if record.get("fait") else effective.get("st", "À faire")
        tasks.append((effective, record))
        known.add(str(number))
    for key, record in suivi.items():
        if not isinstance(record, dict) or not record.get("cree") or not isinstance(record.get("task"), dict):
            continue
        number = record.get("n", key)
        if str(number) in known:
            continue
        effective = dict(record["task"])
        effective["n"] = number
        if isinstance(record.get("mod"), dict):
            effective.update(record["mod"])
        effective["st"] = "Terminé" if record.get("fait") else effective.get("st", "À faire")
        tasks.append((effective, record))
    return sorted(tasks, key=lambda pair: (str(pair[0].get("n", "")), str(pair[0].get("t", "")).casefold()))


def _display(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ": "))
    return str(value)


def build_notion_blocks(project_file: dict[str, Any], app_context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Build a readable Notion report plus a complete JSON snapshot."""
    project = project_file.get("projet") or {}
    base = project_file.get("base") or {}
    suivi = project_file.get("suivi") or {}
    app_context = app_context if isinstance(app_context, dict) else {}
    name = str(project.get("nom") or "Projet sans nom")
    tasks = _effective_tasks(project_file)
    events = [event for event in (base.get("events") or []) if isinstance(event, dict)]
    file_meta = project_file.get("maj") if isinstance(project_file.get("maj"), dict) else {}

    blocks: list[dict[str, Any]] = [
        _heading("Vue d'ensemble", 1),
        *_text_blocks(
            "\n".join([
                f"Projet : {name}",
                f"Responsable : {_display(project.get('responsable'))}",
                f"Fonction : {_display(project.get('fonction'))}",
                f"Modules : {_display(project.get('modules'))}",
                f"Dernière mise à jour du fichier : {_display(file_meta.get('le'))}",
                f"Date affichée dans l'application : {_display(app_context.get('dateAffichee'))}",
                f"Priorités épinglées : {_display(app_context.get('prioritesEpinglees'))}",
                f"Tâches : {len(tasks)} · Événements : {len(events)}",
            ])
        ),
        _heading(f"Tâches ({len(tasks)})", 1),
    ]

    task_lines: list[str] = []
    for task, record in tasks:
        task_lines.append(f"\n{task.get('n', '?')} — {task.get('t') or 'Tâche sans intitulé'}")
        task_lines.append(
            "  Lot : {lot} · Rôle : {role} · Responsable : {resp} · Statut : {status} · Début : {start} · Échéance : {due}".format(
                lot=_display(task.get("lot")), role=_display(task.get("role")),
                resp=_display(task.get("resp")), status=_display(task.get("st")),
                start=_display(task.get("deb")), due=_display(task.get("fin")),
            )
        )
        if task.get("com"):
            task_lines.append(f"  Commentaire initial : {_display(task.get('com'))}")
        if task.get("notes"):
            task_lines.append(f"  Notes : {_display(task.get('notes'))}")
        comments = record.get("com") or []
        if comments:
            task_lines.append("  Commentaires de suivi :")
            for comment in comments:
                if isinstance(comment, dict):
                    stamp = " ".join(str(value) for value in (comment.get("d"), comment.get("h")) if value)
                    author = f" · {comment.get('by')}" if comment.get("by") else ""
                    task_lines.append(f"    - [{stamp or 'date inconnue'}]{author} : {comment.get('txt', '')}")
                else:
                    task_lines.append(f"    - {_display(comment)}")
        history = record.get("hist") or []
        if history:
            task_lines.append("  Historique des modifications :")
            for change in history:
                if isinstance(change, dict):
                    task_lines.append(
                        f"    - [{change.get('d', 'date inconnue')}] {change.get('by', '')} · {change.get('champ', '')} : "
                        f"{change.get('avant', '')} → {change.get('apres', '')}"
                    )
                else:
                    task_lines.append(f"    - {_display(change)}")
    blocks.extend(_text_blocks("\n".join(task_lines) if task_lines else "Aucune tâche."))

    blocks.append(_heading(f"Agenda ({len(events)})", 1))
    event_lines: list[str] = []
    for event in events:
        event_lines.append(
            f"- {event.get('date', 'Date inconnue')} · {event.get('type', 'Événement')} · {event.get('lib', '')}"
        )
        for key, label in (("st", "Statut"), ("alerte", "Alerte"), ("par", "Ajouté par")):
            if event.get(key):
                event_lines.append(f"  {label} : {_display(event.get(key))}")
    blocks.extend(_text_blocks("\n".join(event_lines) if event_lines else "Aucun événement."))

    snapshot = json.dumps(
        {"fichierProjet": project_file, "contexteLocal": app_context},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    blocks.append(_heading("Données source complètes (JSON)", 1))
    blocks.extend(_text_blocks(snapshot, block_type="code", language="json"))
    return blocks


def _list_children(token: str, block_id: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor = ""
    while True:
        query = {"page_size": "100"}
        if cursor:
            query["start_cursor"] = cursor
        response = _notion_request(token, f"/blocks/{block_id}/children?{urlencode(query)}")
        results.extend(response.get("results") or [])
        if not response.get("has_more") or not response.get("next_cursor"):
            return results
        cursor = response["next_cursor"]


def _find_project_page(token: str, parent_page_id: str, title: str) -> dict[str, Any] | None:
    for child in _list_children(token, parent_page_id):
        if child.get("type") == "child_page" and (child.get("child_page") or {}).get("title") == title:
            return {"id": child.get("id"), "url": child.get("url", "")}
    return None


def _clear_children(token: str, page_id: str) -> int:
    children = _list_children(token, page_id)
    removed = 0
    for child in children:
        block_id = child.get("id")
        if block_id:
            _notion_request(token, f"/blocks/{block_id}", method="DELETE")
            removed += 1
    return removed


def _append_children(token: str, page_id: str, blocks: list[dict[str, Any]]) -> None:
    batch: list[dict[str, Any]] = []
    for block in blocks:
        candidate = batch + [block]
        encoded = json.dumps({"children": candidate}, ensure_ascii=False).encode("utf-8")
        if batch and (len(candidate) > 100 or len(encoded) > MAX_NOTION_BATCH_BYTES):
            _notion_request(
                token,
                f"/blocks/{page_id}/children",
                method="PATCH",
                payload={"children": batch},
            )
            batch = []
            encoded = json.dumps({"children": [block]}, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_NOTION_BATCH_BYTES:
            raise ValueError("Un bloc Notion dépasse la taille maximale de requête.")
        batch.append(block)
    if batch:
        _notion_request(
            token,
            f"/blocks/{page_id}/children",
            method="PATCH",
            payload={"children": batch},
        )


def sync_project(token: str, parent_page_id: str, project_file: dict[str, Any], app_context: dict[str, Any] | None = None) -> dict[str, Any]:
    project = project_file.get("projet") or {}
    project_name = str(project.get("nom") or "Projet sans nom").strip() or "Projet sans nom"
    title = f"Poste de pilotage — {project_name}"[:180]
    page = _find_project_page(token, parent_page_id, title)
    if page:
        page_id = page["id"]
        response = _notion_request(
            token,
            f"/pages/{page_id}",
            method="PATCH",
            payload={"properties": {"title": {"title": _rich_text(title)}}},
        )
        page_url = response.get("url") or page.get("url", "")
        _clear_children(token, page_id)
        created = False
    else:
        response = _notion_request(
            token,
            "/pages",
            method="POST",
            payload={
                "parent": {"page_id": parent_page_id},
                "properties": {"title": {"title": _rich_text(title)}},
            },
        )
        page_id = response["id"]
        page_url = response.get("url", "")
        created = True

    blocks = build_notion_blocks(project_file, app_context)
    _append_children(token, page_id, blocks)
    return {
        "pageId": page_id,
        "url": page_url,
        "title": title,
        "created": created,
        "tasks": len(_effective_tasks(project_file)),
        "events": len((project_file.get("base") or {}).get("events") or []),
        "blocks": len(blocks),
    }


class BridgeHandler(SimpleHTTPRequestHandler):
    server_version = "PilotageNotionBridge/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if urlsplit(self.path).path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _same_origin_request(self) -> bool:
        origin = self.headers.get("Origin", "")
        parsed = urlsplit(origin)
        host = self.headers.get("Host", "").lower()
        return bool(
            origin
            and parsed.scheme in {"http", "https"}
            and parsed.netloc.lower() == host
            and self.headers.get("X-Pilotage-Request") == "1"
        )

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Taille de requête invalide.") from exc
        if length <= 0:
            raise ValueError("Corps JSON manquant.")
        if length > MAX_REQUEST_BYTES:
            raise OverflowError("Requête trop volumineuse (limite de 3 Mo).")
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Le corps de requête doit être un JSON UTF-8 valide.") from exc
        if not isinstance(body, dict):
            raise ValueError("Le JSON doit être un objet.")
        return body

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/notion/status":
            token, parent_id, source = _get_config()
            allowed = bool(getattr(self.server, "allow_notion_credentials", False))
            self._json(200, {
                "bridge": True,
                "configured": bool(token and parent_id) and allowed,
                "credentialInputAllowed": allowed,
                "source": source,
            })
            return
        if path.startswith("/api/"):
            self._json(404, {"error": "Route API inconnue."})
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        routes = {
            "/api/notion/connect",
            "/api/notion/disconnect",
            "/api/notion/test",
            "/api/notion/sync",
        }
        if path not in routes:
            self._json(404, {"error": "Route API inconnue."})
            return
        if not self._same_origin_request():
            self._json(403, {"error": "Requête refusée : origine ou en-tête de sécurité invalide."})
            return
        if path == "/api/notion/connect" and not getattr(self.server, "allow_notion_credentials", False):
            self._json(403, {"error": "La saisie d'identifiants est désactivée : le pont doit écouter uniquement sur l'ordinateur local."})
            return
        try:
            body = self._read_json() if path != "/api/notion/disconnect" else {}
        except OverflowError as exc:
            self._json(413, {"error": str(exc)})
            return
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return

        try:
            if path == "/api/notion/connect":
                token = str(body.get("token") or "").strip()
                if not token:
                    raise ValueError("Saisissez le token de votre intégration Notion.")
                parent_id = normalize_page_id(str(body.get("parentPageId") or ""))
                parent = _notion_request(token, f"/pages/{parent_id}")
                if parent.get("object") != "page":
                    raise ValueError("La destination doit être une page Notion, pas une base de données.")
                _set_config(token, parent_id, "session")
                self._json(200, {"connected": True, "parentTitle": _title_of_page(parent)})
                return

            if path == "/api/notion/disconnect":
                _clear_config()
                self._json(200, {"connected": False})
                return

            token, parent_id, _source = _get_config()
            if not token or not parent_id:
                self._json(409, {"error": "Connectez d'abord une intégration Notion et une page de destination."})
                return

            if path == "/api/notion/test":
                parent = _notion_request(token, f"/pages/{parent_id}")
                self._json(200, {"connected": True, "parentTitle": _title_of_page(parent)})
                return

            project_file = body.get("project")
            if not isinstance(project_file, dict) or not isinstance(project_file.get("base"), dict):
                raise ValueError("Aucun fichier projet valide n'a été transmis.")
            if project_file.get("projet") is not None and not isinstance(project_file.get("projet"), dict):
                raise ValueError("Les métadonnées du projet ne sont pas valides.")
            if project_file.get("suivi") is not None and not isinstance(project_file.get("suivi"), dict):
                raise ValueError("Le suivi des tâches n'est pas valide.")
            project_base = project_file["base"]
            for field in ("tasks", "events"):
                if project_base.get(field) is not None and not isinstance(project_base.get(field), list):
                    raise ValueError(f"Le champ base.{field} doit être une liste.")
            project_bytes = json.dumps(project_file, ensure_ascii=False).encode("utf-8")
            if len(project_bytes) > MAX_PROJECT_BYTES:
                self._json(413, {"error": "Le fichier projet dépasse la limite de synchronisation de 2 Mo."})
                return
            app_context = body.get("appContext")
            if not isinstance(app_context, dict):
                app_context = {}
            result = sync_project(token, parent_id, project_file, app_context)
            self._json(200, result)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except NotionAPIError as exc:
            self._json(502, {"error": str(exc)})
        except (KeyError, TypeError, IndexError) as exc:
            self._json(502, {"error": f"Réponse Notion inattendue ({type(exc).__name__})."})


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Pont local sécurisé entre Poste de pilotage et l'API Notion")
    parser.add_argument("--host", default=os.environ.get("PILOTAGE_HOST", "127.0.0.1"), help="Adresse d'écoute (défaut : 127.0.0.1)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PILOTAGE_PORT", "8765")), help="Port HTTP (défaut : 8765)")
    args = parser.parse_args()
    local_only = _is_loopback_host(args.host)
    token, parent_id, _source = _get_config()
    if not local_only and token:
        parser.error("refus de démarrer avec un token Notion sur une adresse réseau ; utilisez 127.0.0.1")
    server = ThreadingHTTPServer((args.host, args.port), BridgeHandler)
    server.allow_notion_credentials = local_only
    server.daemon_threads = True
    status = "identifiants Notion présents (ils restent côté serveur)" if token and parent_id else "en attente de configuration Notion dans les réglages"
    print(f"Poste de pilotage : http://{args.host}:{args.port}/ — {status}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Arrêt du pont Notion.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
