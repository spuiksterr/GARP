![G.A.R.P : la croissance, au juste prix.](portefeuille/docs/bandeau.png)

# G.A.R.P

*Growth at a reasonable price* : la croissance, au juste prix.

Application personnelle d'analyse d'actions et de construction de portefeuille de long terme, pensée pour un investisseur français (PEA et compte-titres).

- **La bonne action au bon prix** : les entreprises qui passent les filtres de qualité, classées par la note GARP (croissance 40 %, valorisation 35 %, qualité 25 %), avec leur prix juste au rendement que vous exigez, votre prix d'achat après marge de sécurité, et un verdict.
- **Screener** d'environ 1 760 entreprises (S&P 500, STOXX Europe 600, Nasdaq Global Select d'au moins 1 milliard de dollars) : filtres d'exclusion, note GARP ; comme repères, hors note : quatre regards d'investisseurs, six critères de qualité, signaux de santé, momentum.
- **Fiche valeur** : historique sur dix ans quand les comptes déposés le permettent (SEC, rapports européens ESEF), DCF inversé, multiples, scénarios à cinq ans, conditions de vente.
- **Mon portefeuille** : import depuis l'export du courtier (CSV ou Excel), analyse des lignes, risques, équilibre proposé.
- **Commandes Claude Code** pour l'analyse qualitative et les revues (`/analyse-valeur`, `/revue-portefeuille`, `/apport-mensuel`, `/nouvelles-idees`).

Un rang élevé dans le screener n'est pas une recommandation d'achat. Cet outil ne fournit pas de conseil en investissement.

## Installer (Windows 11)

1. Téléchargez `GARP-Setup-b<n>.exe` sur la [page des versions](https://github.com/spuiksterr/GARP/releases/latest), sous « Assets ».
2. Lancez-le : il installe G.A.R.P pour votre compte, sans droits d'administrateur, avec tout ce qu'il lui faut (Python compris). L'installateur n'est pas signé : à l'avertissement de SmartScreen, choisissez « Informations complémentaires », puis « Exécuter quand même ».
3. Ouvrez G.A.R.P depuis le menu Démarrer. Les données, calculées chaque nuit par GitHub, se téléchargent d'elles-mêmes, sans compte ni jeton. Les nouvelles versions se proposent dans la barre latérale.

Détails : [installateur/README.md](installateur/README.md).

## Depuis le code source (développement)

Pour modifier l'outil ou calculer les données soi-même (Windows, Python 3.11 ou plus) :

```bat
cd portefeuille
installer.bat   :: une seule fois : environnement Python et premier téléchargement des données
lancer.bat      :: interface dans le navigateur, http://localhost:8501
```

Fenêtre de bureau : `pf bureau` (raccourcis par `portefeuille\creer_raccourcis.ps1`). Ligne de commande : `portefeuille\.venv\Scripts\python.exe -m pf --help`, depuis `portefeuille/`. Mode d'emploi détaillé : [portefeuille/README.md](portefeuille/README.md).

## Organisation

| Emplacement | Contenu |
|---|---|
| [portefeuille/README.md](portefeuille/README.md) | Mode d'emploi détaillé, commandes, routine |
| [portefeuille/docs/METHODE.md](portefeuille/docs/METHODE.md) | Méthode : filtres, note GARP, repères, règles de vente |
| `portefeuille/pf/` | Calculs et accès aux données (package Python) |
| `portefeuille/vues/`, `portefeuille/app.py` | Interface Streamlit |
| `portefeuille/tests/` | Tests (`pytest tests -q`, et `-m pages` pour l'affichage) |
| `portefeuille/config/` | Univers et réglages ; vos fichiers personnels (portefeuille, watchlist) vont dans `portefeuille/profil/`, exclu du dépôt |
| [installateur/](installateur/README.md) | Installateur Windows (`GARP-Setup`) : l'outil du PC et son Python, données de la nuit publiées par GitHub, installation et mises à jour depuis les Releases |
| [portefeuille/docs/MARQUE.md](portefeuille/docs/MARQUE.md) | Marque : positionnement, logo, couleurs, ton, textes de présentation |
| `.claude/skills/` | Commandes Claude Code |
| [FEUILLE_DE_ROUTE.md](FEUILLE_DE_ROUTE.md) | Améliorations prévues, en tickets confiés à des agents |
| [CLAUDE.md](CLAUDE.md) | Conventions de travail pour Claude |

Les données téléchargées, les fiches de thèse, le journal des opérations et les rapports restent sur le poste : ils sont exclus du dépôt.

## Sources de données

Yahoo Finance (cours, fondamentaux), SEC (comptes des sociétés américaines et formulaires des dirigeants), filings.xbrl.org (rapports européens ESEF), BCE (taux de change), iShares et Nasdaq Trader (composition des indices).

## Crédits et licence

La méthode d'analyse s'inspire du projet open source [ai-berkshire](https://github.com/xbtlin/ai-berkshire) (licence MIT), gardé en lecture seule sur le poste et absent de ce dépôt.

Distribué sous [licence MIT](LICENSE).
