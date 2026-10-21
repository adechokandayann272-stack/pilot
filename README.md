# Poste de pilotage

Application web d'une seule page (aucun serveur, aucune base de données) pour piloter un projet :
agenda de la semaine et tâches priorisées.

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

## Réglages (roue dentée sur le bord droit de l'écran)

Les préférences sont **propres à ce navigateur** (clé `pilotage-reglages`) : elles ne sont jamais
écrites dans le fichier `pilotage_*.json` partagé avec l'équipe.

| Réglage | Valeurs |
|---|---|
| Thème | automatique (suit le système), clair, foncé — appliqué à l’interface |
| Police | humaniste (défaut), système, classique (serif), compacte (Arial), mono |
| Taille du texte | petite, normale, grande |
| Densité | confortable, compacte (plus de lignes visibles) |
| Accessibilité | réduire les animations, contraste renforcé |
| Ouverture | « Ma journée » ou dernière vue utilisée |
| Rappel de sauvegarde | tous les 7 / 14 / 30 jours (ou jamais) |
| Divers | réouvrir le dernier projet, rétablir les réglages par défaut |

Aucune police n'est téléchargée : le choix se fait parmi des familles présentes sur la machine,
pour que l'application reste utilisable hors ligne.

## Assistant IA

L'onglet **Assistant IA** permet d'interroger le projet ouvert avec une clé API personnelle :
OpenAI, Anthropic (Claude), Google Gemini ou un endpoint compatible avec l'API OpenAI
(par exemple un service compatible Mistral, OpenRouter ou Ollama). Renseignez le fournisseur,
le modèle, l'URL d'API et la clé, puis enregistrez la connexion. Les identifiants des modèles
proposés par défaut sont modifiables selon les modèles disponibles chez votre fournisseur.

L'application étant statique et sans serveur, les requêtes partent directement du navigateur.
À chaque question, le fichier complet du projet (tâches, agenda, suivis, commentaires, noms et
historique), la date affichée, les priorités épinglées et les derniers échanges réussis sont
envoyés au fournisseur choisi. La clé API est également transmise directement au fournisseur.
La connexion dépend de ses autorisations CORS. N'utilisez cette fonction qu'avec un fournisseur
approuvé pour les données concernées. La clé est conservée uniquement en mémoire de la page par
défaut ; si « Mémoriser la clé » est coché, elle est enregistrée **en clair dans le stockage local
du navigateur**. Pour un usage d'équipe ou des données sensibles, privilégiez une passerelle serveur
sécurisée plutôt que le stockage d'une clé côté navigateur.
