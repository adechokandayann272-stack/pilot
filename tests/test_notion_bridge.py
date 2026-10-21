import json
import unittest
from unittest.mock import patch

import notion_bridge


class NotionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.project = {
            "version": 1,
            "projet": {
                "nom": "Projet démo",
                "responsable": "Alex Martin",
                "fonction": "Chef de projet",
                "modules": ["Cadrage", "Recette"],
            },
            "base": {
                "tasks": [
                    {"n": 1, "t": "Valider le périmètre", "lot": "Cadrage", "role": "Pilote", "st": "En cours"},
                ],
                "events": [
                    {"date": "2026-10-21", "type": "Atelier", "lib": "Atelier de recette", "alerte": "Préparer les jeux de test"},
                ],
            },
            "suivi": {
                "1": {
                    "n": 1,
                    "mod": {"st": "Bloqué"},
                    "com": [{"d": "2026-10-20", "h": "09:30", "by": "Alex Martin", "txt": "En attente du fournisseur."}],
                    "hist": [{"d": "2026-10-20", "by": "Alex Martin", "champ": "Statut", "avant": "En cours", "apres": "Bloqué"}],
                },
                "2": {
                    "n": 2,
                    "cree": True,
                    "fait": True,
                    "faitLe": "2026-10-20",
                    "task": {"t": "Envoyer le compte rendu", "lot": "Cadrage", "role": "Consulté", "st": "À faire"},
                    "com": [{"d": "2026-10-20", "txt": "Envoyé à l'équipe."}],
                },
            },
            "maj": {"par": "Alex Martin", "le": "2026-10-21T10:00:00Z"},
        }
        self.context = {"dateAffichee": "2026-10-21", "prioritesEpinglees": {"2026-10-21": [1]}}

    def test_notion_secrets_are_only_allowed_on_loopback(self):
        self.assertTrue(notion_bridge._is_loopback_host("127.0.0.1"))
        self.assertTrue(notion_bridge._is_loopback_host("localhost"))
        self.assertFalse(notion_bridge._is_loopback_host("0.0.0.0"))
        self.assertFalse(notion_bridge._is_loopback_host("192.168.1.20"))

    def test_page_id_accepts_uuid_and_notion_url(self):
        expected = "12345678-1234-5678-1234-567812345678"
        self.assertEqual(notion_bridge.normalize_page_id(expected), expected)
        self.assertEqual(
            notion_bridge.normalize_page_id("https://www.notion.so/Mon-espace-12345678123456781234567812345678?pvs=4"),
            expected,
        )
        with self.assertRaises(ValueError):
            notion_bridge.normalize_page_id("pas un identifiant")

    def test_blocks_include_effective_status_comments_events_and_full_snapshot(self):
        blocks = notion_bridge.build_notion_blocks(self.project, self.context)
        rendered = "\n".join(
            part["text"]["content"]
            for block in blocks
            for part in block.get(block["type"], {}).get("rich_text", [])
        )
        self.assertIn("1 — Valider le périmètre", rendered)
        self.assertIn("Statut : Bloqué", rendered)
        self.assertIn("En attente du fournisseur.", rendered)
        self.assertIn("Historique des modifications", rendered)
        self.assertIn("Atelier de recette", rendered)
        self.assertIn("2 — Envoyer le compte rendu", rendered)
        self.assertIn("Statut : Terminé", rendered)

        code = "".join(
            part["text"]["content"]
            for block in blocks if block["type"] == "code"
            for part in block["code"]["rich_text"]
        )
        source = json.loads(code)
        self.assertEqual(source["fichierProjet"], self.project)
        self.assertEqual(source["contexteLocal"], self.context)

    def test_append_children_sends_each_block_once_and_respects_batch_limit(self):
        blocks = [{"object": "block", "payload": {"value": str(index)}} for index in range(205)]
        with patch.object(notion_bridge, "_notion_request", return_value={}) as request:
            notion_bridge._append_children("token", "page", blocks)
        sent = [call.kwargs["payload"]["children"] for call in request.call_args_list]
        self.assertEqual([block for batch in sent for block in batch], blocks)
        self.assertTrue(all(len(batch) <= 100 for batch in sent))

    def test_sync_creates_one_page_and_appends_content(self):
        calls = []

        def fake_request(token, path, method="GET", payload=None):
            calls.append((path, method, payload))
            if path == "/pages" and method == "POST":
                return {"id": "new-page", "url": "https://www.notion.so/new-page"}
            return {}

        with patch.object(notion_bridge, "_find_project_page", return_value=None), patch.object(
            notion_bridge, "_notion_request", side_effect=fake_request
        ):
            result = notion_bridge.sync_project("token", "parent-page", self.project, self.context)

        self.assertTrue(result["created"])
        self.assertEqual(result["pageId"], "new-page")
        self.assertEqual(result["tasks"], 2)
        self.assertEqual(result["events"], 1)
        self.assertTrue(any(path == "/blocks/new-page/children" and method == "PATCH" for path, method, _ in calls))


if __name__ == "__main__":
    unittest.main()
