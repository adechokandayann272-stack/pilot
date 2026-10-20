# Poste de pilotage

Application web d'une seule page (aucun serveur, aucune base de données) pour piloter un projet :
agenda de la semaine, tâches priorisées, bilan de période, kit COPIL, ordre du jour et compte-rendu
de réunion, relances, registre des risques et des décisions.

Les données vivent dans un fichier `pilotage_*.json` rangé dans le dossier partagé du projet
(OneDrive / Teams / disque réseau), ou à défaut dans le navigateur.

## Contenu du dossier

```
index.html                        l'application (HTML + CSS + JS, sans build)
manifest.webmanifest              installation « application »
sw.js                             fonctionnement hors ligne (réseau d'abord)
assets/demo/pilotage_demo.json    projet de démonstration
assets/fonts/fonts.css            alias de polices système (aucun téléchargement)
assets/img/favicon.svg            icône
assets/vendor/xlsx.full.min.js    lecture des modèles Excel (SheetJS, licence Apache-2.0)
```

**Le dossier `assets/` est indispensable** : sans lui la démonstration, l'icône et l'import Excel
ne fonctionnent pas (l'application elle-même s'ouvre quand même).

## Ouvrir l'application

- **Utilisation normale** : ouvrir le dossier partagé puis `index.html` (double-clic).
- **Enregistrement dans le fichier partagé** : Edge ou Chrome (API *File System Access*) ; Firefox,
  Safari et les mobiles basculent automatiquement sur un stockage dans le navigateur, avec export
  `.json` possible à tout moment.
- **Sans fichier de données** : bouton « Ouvrir un projet de démonstration », qui fonctionne aussi
  en double-clic (les données sont embarquées dans la page et redatées à aujourd'hui).

## Tests

Aucune chaîne de build. Pour un contrôle rapide, ouvrir `index.html` depuis un petit serveur
statique (`python3 -m http.server`) : la console du navigateur ne doit signaler aucune ressource
manquante.
