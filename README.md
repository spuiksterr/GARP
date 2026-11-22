![G.A.R.P : la croissance, au juste prix.](portefeuille/docs/bandeau.png)

# G.A.R.P

*Growth at a reasonable price* : la croissance, au juste prix. Le projet s'appelait Climax jusqu'au 18/11/2026.

Application personnelle d'analyse d'actions et de construction de portefeuille de long terme, pensée pour un investisseur français (PEA et compte-titres).

- **Screener** d'environ 1 760 entreprises (S&P 500, STOXX Europe 600, Nasdaq Global Select d'au moins 1 milliard de dollars) : filtres d'exclusion, score Qualité / Croissance / Valorisation / Momentum, signaux de santé, note selon quatre regards d'investisseurs.
- **Fiche valeur** : historique sur dix ans quand les comptes déposés le permettent (SEC, rapports européens ESEF), DCF inversé, scénarios à cinq ans, conditions de vente.
- **Construction et suivi** du portefeuille : poids cibles, risques, backtest, performance contre l'ETF MSCI World, apport du mois.
- **Commandes Claude Code** pour l'analyse qualitative et les revues (`/analyse-valeur`, `/revue-portefeuille`, `/apport-mensuel`, `/nouvelles-idees`).

Un rang élevé dans le screener n'est pas une recommandation d'achat. Cet outil ne fournit pas de conseil en investissement.

## Démarrer (Windows, Python 3.11 ou plus)

```bat
cd portefeuille
installer.bat   :: une seule fois : environnement Python et premier téléchargement des données
lancer.bat      :: interface dans le navigateur, http://localhost:8501
```

Version bureau : icône **G.A.R.P (projet)** (créée par `portefeuille\creer_raccourcis.ps1`), ou `pf bureau`. Version téléphone : `pf mobile`, par le réseau privé Tailscale (voir le README détaillé).

**Application autonome** (Android et Windows, sans PC allumé) : GitHub calcule les données chaque nuit et les publie ; l'application s'installe et se met à jour depuis les Releases du dépôt. Voir [app/README.md](app/README.md).

Ligne de commande : `portefeuille\.venv\Scripts\python.exe -m pf --help`, depuis `portefeuille/`.

## Organisation

| Emplacement | Contenu |
|---|---|
| [portefeuille/README.md](portefeuille/README.md) | Mode d'emploi détaillé, commandes, routine |
| [portefeuille/docs/METHODE.md](portefeuille/docs/METHODE.md) | Méthode : filtres, score, quatre regards, règles de vente |
| `portefeuille/pf/` | Calculs et accès aux données (package Python) |
| `portefeuille/vues/`, `portefeuille/app.py` | Interface Streamlit |
| `portefeuille/tests/` | Tests (`pytest tests -q`, et `-m pages` pour l'affichage) |
| `portefeuille/config/` | Univers, réglages, portefeuille modèle et listes de suivi |
| [app/](app/README.md) | Application Android et Windows (Flutter) : données de la nuit publiées par GitHub, installation et mises à jour depuis les Releases |
| [portefeuille/docs/MARQUE.md](portefeuille/docs/MARQUE.md) | Marque : positionnement, logo, couleurs, ton, textes de présentation |
| `.claude/skills/` | Commandes Claude Code |
| [FEUILLE_DE_ROUTE.md](FEUILLE_DE_ROUTE.md) | Améliorations prévues, en tickets confiés à des agents |
| [CLAUDE.md](CLAUDE.md) | Conventions de travail pour Claude |

Les données téléchargées, les fiches de thèse, le journal des opérations et les rapports restent sur le poste : ils sont exclus du dépôt.

## Sources de données

Yahoo Finance (cours, fondamentaux), SEC (comptes des sociétés américaines et formulaires des dirigeants), filings.xbrl.org (rapports européens ESEF), BCE (taux de change), iShares et Nasdaq Trader (composition des indices).

## Crédits

La méthode d'analyse s'inspire du projet open source [ai-berkshire](https://github.com/xbtlin/ai-berkshire) (licence MIT), gardé en lecture seule sur le poste et absent de ce dépôt.
