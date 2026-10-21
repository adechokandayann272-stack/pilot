# Poste de pilotage

Application web monopage, sans base de données, pour piloter un projet : agenda de la semaine,
tâches priorisées et assistant IA. Un pont Python facultatif permet la synchronisation sécurisée
vers Notion.

Les données vivent dans un fichier `pilotage_*.json` rangé dans le dossier partagé du projet
(OneDrive / Teams / disque réseau), ou à défaut dans le navigateur.

## Contenu du dossier

```
index.html                        l'application (HTML + CSS + JS, sans build)
notion_bridge.py                  serveur local facultatif pour la synchronisation Notion
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
manquante. Les tests du pont Notion s'exécutent avec `python3 -m unittest discover -s tests`.

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

## Synchronisation Notion (facultative)

La synchronisation crée ou met à jour une page enfant par projet sous une page Notion de
votre choix. Elle comprend les tâches de tous les statuts, leurs échéances, rôles, responsables,
commentaires et historique, l'agenda, ainsi qu'un bloc JSON complet du fichier source. La page
est remplacée à chaque synchronisation : gardez-y uniquement les données gérées par l'application.

Pour utiliser cette fonction, lancez `python3 notion_bridge.py` depuis le dossier du projet, puis
ouvrez l'adresse locale affichée (par défaut `http://127.0.0.1:8765`). Ouvrez les **Réglages**
(roue dentée), puis la section **Connexion Notion**. Collez le token d'une intégration interne et
l'ID ou l'URL d'une page Notion partagée avec cette intégration. Le pont local conserve le token
uniquement en mémoire et l'efface à l'arrêt ; il
n'est jamais écrit dans le fichier projet ou dans le stockage du navigateur. La synchronisation
vers Notion ne démarre qu'au clic sur **Synchroniser maintenant**.

Le pont accepte aussi `NOTION_TOKEN` et `NOTION_PARENT_PAGE_ID` comme variables d'environnement
au démarrage, pour une configuration gérée par l'administrateur. Ne publiez jamais le pont sur
Internet avec un token Notion configuré ; il est conçu pour tourner localement sur `127.0.0.1`.
