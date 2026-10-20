# Poste de pilotage

Application web autonome (un seul écran, sans serveur) pour piloter un projet :
agenda de la semaine, tâches priorisées, bilan de période, kit COPIL, ordre du jour
et compte-rendu de réunion, relances par responsable, registre des risques et des décisions.

Tout tient dans `index.html` ; les données du projet sont des fichiers `.json` que
l'application lit et écrit directement (dossier OneDrive / Teams partagé).

## Pourquoi la page semblait ne pas fonctionner

Le dépôt ne contenait que `index.html`, alors que la page appelle plusieurs ressources
dans `assets/`. Résultat : erreurs 404 en cascade et plusieurs fonctions inutilisables.

| Ressource | Conséquence quand elle manque |
|---|---|
| `assets/vendor/xlsx.full.min.js` | « Importer un modèle Excel » et « Exporter en Excel » ne font rien (message « nécessite une connexion internet ») |
| jeu de démonstration | « Ouvrir un projet de démonstration » répond « Démonstration indisponible » |
| `assets/fonts/fonts.css` | retombée sur les polices système (mise en page moins propre) |
| `manifest.webmanifest`, icônes | pas d'installation en « application », favicon manquant |
| `sw.js` | pas de fonctionnement hors ligne |

Deux autres défauts ont été corrigés au passage :

- un **script Cloudflare** (`/cdn-cgi/challenge-platform/...`) avait été enregistré avec la
  page : il créait une iframe invisible et provoquait des 404 à chaque ouverture. Il est retiré.
- la démonstration dépendait d'un `fetch()` : elle échouait aussi quand la page est ouverte
  par double-clic (`file://`) ou hors ligne. Elle est désormais **construite dans la page**,
  sans aucun appel réseau.

## Utilisation

1. Ouvrir `index.html` (double-clic, ou en ligne sur l'hébergement du dossier partagé).
2. Saisir son nom — il signe les modifications et les commentaires.
3. « Ouvrir un projet existant » (fichier `pilotage_*.json`) ou « Créer un nouveau projet ».
   Pour découvrir l'outil : « ouvrir un projet de démonstration » sur l'écran d'accueil.

Navigateurs : **Edge ou Chrome** enregistrent directement dans le fichier `.json` du dossier
partagé (File System Access API). Avec **Firefox, Safari ou un mobile**, les données restent
dans le navigateur et s'exportent / s'importent via les boutons `.json` en bas de page.

## Fichiers de données

- `pilotage_<projet>.json` — tâches, agenda, suivi (cases cochées, commentaires, historique).
- `risques_<projet>.json` — registre des risques et journal des décisions (créé depuis l'onglet
  « Risques & décisions »).

Aucune donnée n'est envoyée à un serveur : tout reste dans les fichiers choisis, ou dans le
stockage local du navigateur.

## Structure

```
index.html                 application complète (HTML + CSS + JS)
manifest.webmanifest       métadonnées « application installable »
sw.js                      service worker (ouverture hors ligne)
assets/vendor/             SheetJS (import / export Excel) + licence
assets/fonts/              Instrument Sans & JetBrains Mono (woff2) + licence
assets/img/                favicon et icônes d'application
```

Les bibliothèques tierces sont embarquées (aucun CDN) : la page fonctionne hors ligne et
depuis un simple dossier partagé.

## Servir la page en local

```bash
python3 -m http.server 8080
# puis http://localhost:8080/
```

Un serveur local n'est pas obligatoire : `index.html` s'ouvre aussi par double-clic.
