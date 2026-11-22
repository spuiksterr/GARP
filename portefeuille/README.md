# Portefeuille long terme — outils de stock-picking

Outils pour constituer, suivre et faire vivre un portefeuille d'actions de long terme, pensé pour un investisseur français (PEA + compte-titres) :

- un **screener** d'environ 1 760 entreprises (S&P 500, STOXX Europe 600, Nasdaq Global Select d'au moins 1 milliard de dollars et une sélection internationale), avec filtres d'exclusion et note GARP (croissance 40 %, valorisation 35 %, qualité 25 %) ;
- **votre portefeuille réel** (repris le 29/10/2026 depuis votre courtier : 8 lignes sur le compte-titres) avec ses poids cibles, une fiche de thèse par ligne et le suivi de performance contre l'ETF MSCI World ;
- la **sélection de 25 valeurs proposée par Claude** le 29/10/2026, archivée dans `profil/selection_claude_2026-10.csv` et comparable dans le backtest ;
- trois **signaux de santé** (Piotroski, Altman, Beneish) et une note selon **quatre regards**, intégrés au score avec la valorisation, qui y compte aussi comme un bloc à part ;
- un **moat estimé** et une comparaison du PER à son historique, hors note ;
- **six critères de qualité** remplis ou non (croissance du CA et du free cash flow, ROCE, dette nette / FCF, nombre d'actions, marge de FCF), en cartes sur la fiche valeur et en filtre dans le screener, hors score par défaut ;
- une **interface** locale (Streamlit) : tableau de bord, fiche valeur avec DCF inversé, construction, backtest, suivi réel, apport du mois ;
- une **ligne de commande** et des **commandes Claude Code** en français pour l'analyse et les revues.

La méthode complète est dans [docs/METHODE.md](docs/METHODE.md) (aussi visible dans l'interface, page « Méthode et routine »).

## Démarrer

1. Double-cliquez sur `installer.bat` (une seule fois : environnement Python et premier téléchargement des données, environ 5 minutes). Déjà fait sur ce poste.
2. Ouvrez **G.A.R.P (projet)** (icône sur le bureau et dans le menu Démarrer ; « G.A.R.P » tout court est la version installée par `GARP-Setup`) : l'application s'ouvre dans sa propre fenêtre, et s'arrête quand on la ferme. Raccourcis à recréer après un déplacement du dossier : clic droit sur `creer_raccourcis.ps1` > « Exécuter avec PowerShell ». Toujours possible : `lancer.bat`, qui l'ouvre dans le navigateur sur http://localhost:8501. La fenêtre est toujours en thème sombre.

**Sur un autre PC, sans Python ni ce dossier** : l'installateur `GARP-Setup-b<n>.exe` des Releases GitHub installe ce même outil avec tout ce qu'il lui faut (voir [app/README.md](../app/README.md)). Il télécharge, sans jeton, chaque nuit les données calculées par GitHub (`pf export-outil`) au lieu de les calculer ; « Importer mon portefeuille » reprend les lignes depuis l'export du courtier, en CSV ou en classeur Excel (`.xlsx`).
3. Dans l'interface (barre latérale), bouton « Mise à jour rapide » avant chaque session : cours, changes et scores en quelques minutes. Une fois par semaine, « Mise à jour complète » : fondamentaux par roulement et comptes déposés (SEC, rapports européens), environ 10 minutes. La barre latérale signale une mise à jour complète vieille de plus d'une semaine.

## Sur le téléphone

L'application tourne sur le PC ; le téléphone y accède de partout par un réseau privé chiffré (Tailscale, gratuit
pour un usage personnel). Rien n'est ouvert sur Internet et vos données restent sur le PC.

1. Installez Tailscale sur le PC et sur le téléphone (https://tailscale.com/download, ou l'App Store / le Play
   Store), et connectez-vous **avec le même compte** sur les deux.
2. Sur le PC : `.venv\Scripts\python.exe -m pf mobile`. La commande affiche l'adresse à ouvrir sur le téléphone
   (`https://<nom-du-pc>.<…>.ts.net`). À faire une fois : le réglage est mémorisé par Tailscale.
3. Sur le téléphone : ouvrez cette adresse, puis menu du navigateur > « Ajouter à l'écran d'accueil ».

Le PC doit être allumé et l'application lancée (fenêtre G.A.R.P ouverte, ou `lancer.bat` pour la laisser tourner
sans fenêtre). `pf mobile --arreter` coupe l'accès.

## Routine conseillée

| Quand | Quoi |
|---|---|
| Chaque mois | Mise à jour, tableau de bord, « La bonne action au bon prix », proposition d'apport (onglet « Équilibre » du portefeuille) |
| Chaque trimestre | `/revue-portefeuille` dans Claude Code après les publications de résultats |
| Chaque semestre | Revue de la poche opportunités, `/nouvelles-idees` pour les meilleures notes GARP hors portefeuille |
| Chaque année | Bilan contre l'ETF MSCI World, rééquilibrage par les apports |

## Ligne de commande

Depuis ce dossier : `.venv\Scripts\python.exe -m pf <commande>`, ou `.venv\Scripts\pf <commande>` après `.venv\Scripts\python.exe -m pip install -e .` (installation décrite par `pyproject.toml`, dépendances figées dans `requirements.txt`).

| Commande | Rôle |
|---|---|
| `maj` | Mise à jour complète : cours et scores, un quart des fiches de fondamentaux par roulement (vos lignes d'abord ; tout l'univers relu en quatre semaines), comptes SEC et rapports européens à renouveler ; `--rapide` pour les cours, changes et scores seulement (chaque jour) ; `--complet` pour tout re-télécharger (environ une heure). Le compte rendu donne la durée de chaque étape |
| `maj --auto` | Mode planifié : complète si la dernière a 6 jours ou plus, rapide sinon ; journal dans `data/journaux`. Pour le lancer chaque jour à 6 h 30 (réveil de la veille, rattrapage au démarrage) : clic droit sur `planifier_mise_a_jour.ps1` > « Exécuter avec PowerShell » (`-Retirer` pour l'enlever) |
| `contexte ADBE` | Tout le contexte d'une valeur : historique et sa source, multiples et médianes, dirigeants, grands investisseurs, élus, actualités, scénarios, conditions de vente, prix visé (`--hors-ligne` sans réseau) |
| `risques` | Risques du portefeuille : concentration, devises, corrélations, pertes passées, scénarios de choc |
| `idees` | Valeurs retenues par plusieurs méthodes de notation, et titres détenus par plusieurs grands investisseurs |
| `regards --top 50` | Note sur 5 selon quatre regards (Buffett, Munger, Fisher, Smith) ; `--tous` pour toutes les actions, exclues comprises |
| `homme-cle` | Risque homme-clé (0 à 10) du portefeuille et de la watchlist, en relisant tout de suite leurs dirigeants ; `homme-cle TSLA META` pour des valeurs précises, `--tous` pour l'univers (environ 40 minutes) |
| `esef` | Allonge l'historique des valeurs européennes avec leurs rapports annuels (ESEF). Premier passage : deux à trois heures, au rythme imposé par la base ; ensuite `maj` s'en charge |
| `investisseurs` | Portefeuilles 13F des grands investisseurs suivis et transactions des élus américains (aussi fait par `maj` et par le bouton de la page « Grands investisseurs ») ; `--force` pour tout relire |
| `indices` | Ajoute à l'univers les nouveaux entrants du S&P 500, du STOXX 600 et du Nasdaq Global Select (au moins 1 milliard de dollars, vérifié auprès de Yahoo ; `--sans-nasdaq` pour aller vite). À lancer chaque trimestre, puis `maj` |
| `screener --top 30 --enveloppe PEA` | Classement ; `--tous` inclut les exclues |
| `fiche ASML.AS` | Tous les indicateurs d'une valeur et sa thèse |
| `modele` | Composition du portefeuille (poids cibles), caractéristiques, répartitions |
| `construire --n 22` | Construction de portefeuille : portefeuille construit par des règles (plancher de qualité, cycliques plafonnés), réglages de config/strategie.json , classement par la note GARP ; `--pea 0.5` impose une part PEA |
| `backtest --depuis 2016-01-01 --reequilibrage annuel` | Profil de risque historique (attention au biais rétrospectif) |
| `suivi` | Positions, performance, écart à l'ETF, écarts aux poids cibles |
| `apport 1000 --compte PEA` | Ordres à passer pour investir un apport sans vendre |
| `export` | Classeur Excel dans `rapports/` |
| `sauvegarde --vers DOSSIER` | Archive zip datée de vos données personnelles (profil, thèses, journal d'opérations, historique des scores), hors de Git. Choisir un dossier hors de ce disque ou synchronisé (OneDrive…) : il est mémorisé, puis chaque mise à jour refait l'archive du jour ; les 30 dernières sont gardées. Restaurer : décompresser l'archive dans `portefeuille/` |
| `verifier` | Contrôle du projet : doublons de l'univers (même société cotée deux fois), secteurs ou enveloppes inconnus, cours absents ou figés, fiches incomplètes, lignes de CSV mal formées (un « ; » dans un texte). Rien n'est modifié ; à lancer après avoir édité un fichier de `config/` ou de `profil/` |

## Commandes Claude Code

Ouvrez Claude Code dans le dossier `Claude investissement` :

| Commande | Rôle |
|---|---|
| `/analyse-valeur ASML.AS` | Analyse approfondie (4 regards : Buffett, Munger, Fisher, Terry Smith), verdict et fiche de thèse |
| `/revue-portefeuille` | Revue trimestrielle : chaque thèse est confrontée aux faits récents |
| `/apport-mensuel 1500 PEA` | Prépare et explique les ordres du mois |
| `/nouvelles-idees` | Cherche des candidats dans le screener et au-delà |

## Fichiers à connaître

Vos fichiers personnels sont dans `profil/`. Ce dossier n'est pas envoyé sur GitHub et n'a pas d'autre copie : réglez une sauvegarde avec `pf sauvegarde --vers DOSSIER`. Sur une installation neuve, il est créé à partir de `profil.exemple/` (données fictives). La variable d'environnement `PF_PROFIL` désigne un autre dossier.

| Fichier | Contenu | Modifiable |
|---|---|---|
| `config/univers.csv` | Les valeurs suivies (ticker Yahoo, enveloppe, secteur). Les lignes à `profil` vide viennent des indices | Oui, sous Excel (séparateur `;`) |
| `profil/portefeuille_modele.csv` | Vos lignes et leurs poids cibles (visés par l'apport du mois), thèses, conditions de vente | Oui |
| `profil/selection_claude_2026-10.csv` | Sélection de 25 valeurs proposée par Claude (archive) | Oui |
| `profil/surveillance.csv` | Valeurs écartées pour l'instant et condition d'entrée | Oui |
| `profil/regles_vente.csv` | Conditions de vente chiffrées (indicateur, comparaison, seuil), vérifiées à chaque mise à jour | Oui (ou depuis la fiche, section Thèse) |
| `profil/scenarios.csv` | Scénarios de valorisation à 5 ans enregistrés, datés | Oui (ou depuis la fiche, section Valorisation) |
| `profil/actualites.csv` | Recherches de presse propres à une valeur (`"Ferrari" -F1`, `en:` pour la presse anglaise) | Oui |
| `config/investisseurs.csv`, `config/elus.csv` | Grands investisseurs et élus américains suivis | Oui (ou depuis la page « Grands investisseurs ») |
| `config/regards_ajustements.csv` | Corrections manuelles des notes « quatre regards », avec leur motif | Oui |
| `config/strategie.json` | Poids des piliers, seuils des filtres, paramètres ; garde-fous de concentration (`suivi.garde_fous` : poids d'une ligne, des trois premières, d'un secteur, corrélation moyenne), signalés au tableau de bord, sur la page Risques et dans le simulateur | Oui (ou via l'interface) |
| `data/historique/scores.parquet` | Photo datée du screener à chaque mise à jour normale ou complète : évolution du rang (fiche valeur), changements de statut (tableau de bord). À sauvegarder : il ne se reconstitue pas | Non |
| `data/transactions.csv` | Votre journal d'opérations, en commençant par la reprise de vos lignes | Oui |
| `theses/*.md` | Une fiche de thèse par ligne, avec journal de suivi | Oui |
| `data/cache/` | Données téléchargées | Non (régénéré) |

## Reprendre un portefeuille existant

Une ligne déjà détenue s'enregistre comme une opération `REPRISE` : quantité, PRU et coût total en euros indiqués par le courtier (colonne `montant_eur`). Le prix de revient et les plus-values latentes sont ainsi ceux du courtier. La performance, elle, part de la valeur de marché du jour de la reprise : les gains acquis avant le suivi ne la gonflent pas, et la comparaison avec l'ETF reste équitable.

Watchlist : page « Watchlist » (espace « Acheter au bon prix »). On y ajoute une valeur depuis la page elle-même, depuis le bouton « Ajouter à la watchlist » de sa fiche, ou en cochant une ligne du screener ; un clic sur une ligne ouvre la fiche. Elle est enregistrée dans `profil/watchlist.csv`, avec la date et le cours d'ajout. La liste de surveillance (`profil/surveillance.csv`, conditions d'entrée décidées lors des analyses) s'y consulte dans un second onglet.

Grands investisseurs : page de l'espace « Explorer ». On y voit les portefeuilles déclarés (formulaires 13F) de 16 investisseurs reconnus (Buffett, Ackman, Li Lu, Klarman, Terry Smith, Nick Train…) et leurs mouvements trimestriels, ainsi que les transactions déclarées par 9 élus de la Chambre des représentants (Nancy Pelosi…). Les listes se modifient dans l'onglet « Gérer les listes » (fichiers `config/investisseurs.csv` et `config/elus.csv`). Méthode et limites : `docs/METHODE.md`, section « Grands investisseurs ».

Prix visé : dans la fiche, la section « Prix juste » calcule le cours auquel l'action se paierait au multiple choisi (P/FCF, P/FCF hors SBC, PER ou prix / chiffre d'affaires), avec les médianes historiques comme repères. Le bouton « Ajouter à la watchlist » de cette section enregistre ce prix. Quand le cours passe dessous, la watchlist et le tableau de bord le signalent. Méthode et limites : `docs/METHODE.md`, section « Prix juste et prix visé ».

Affichage : l'interface suit le thème clair ou sombre de Windows ; le menu « ⋮ > Settings » de l'application permet de choisir l'un ou l'autre. Les graphiques reprennent les couleurs du thème actif après un clic ou un changement de page.

Sécurité : l'interface n'est accessible que depuis cet ordinateur (`.streamlit/config.toml`). Le journal `data/transactions.csv` est copié dans `data/sauvegardes` avant chaque modification. `profil/prive.json` (adresse de contact SEC) et le dossier `data/` sont personnels : ne les partagez pas avec le code (voir `.gitignore`).

Une valeur hors univers doit être ajoutée à `config/univers.csv`. Pour un ETF ou un ETC, choisissez le secteur « Fonds & matières premières » : il sera suivi sur son cours, sans filtres ni score.

## Organisation de l'outil

G.A.R.P sert d'abord à **trouver la bonne action au bon prix**. Votre portefeuille, importé de votre courtier, est analysé avec les mêmes outils ; l'équilibre n'y est qu'un onglet de propositions.

- **Tableau de bord** : les actions de qualité au bon prix aujourd'hui, le verdict de vos lignes, les points de vigilance.
- **Trouver** : La bonne action au bon prix (dans tout l'univers, votre portefeuille ou votre watchlist : qualité, classement par note GARP, prix juste au rendement exigé, prix d'achat après marge de sécurité, verdict ; ouvrir une fiche ou ajouter à la watchlist depuis le tableau), Screener (douze colonnes par défaut, « Colonnes avancées » pour toutes), Fiche valeur (qui commence par cours, prix d'achat, prix juste, verdict et « Suivre à ce prix »), Watchlist.
- **Mon portefeuille** : Analyse de mon portefeuille (analyse des lignes, répartition et risques, équilibre proposé, poids modifiables, thèses), Risques, Importer mon portefeuille (CSV, Excel, tableau collé ; les quantités peuvent être enregistrées pour comparer poids réels et cibles).
- **Explorer** : Actualités, Quatre regards (lus un par un, hors note), Grands investisseurs, Construction automatique, Backtest, Méthode et routine.

Les quantités de vos lignes viennent du dernier import (photo du portefeuille, `profil/positions.csv`), remplacée à chaque réimport : rien à saisir à la main. Performance et fiscalité restent chez le courtier ; l'ancien journal des opérations (`data/transactions.csv`) n'est plus tenu par l'interface, mais reste lu s'il n'y a pas encore de photo.

## Pages ajoutées en novembre 2026

- **Actualités** (espace « Explorer ») : presse française, déclarations officielles à la SEC, dates de résultats et signaux de l'outil pour vos lignes et votre watchlist. Les 5 dernières figurent au tableau de bord.
- **Risques** (espace « Mon portefeuille » ; la concentration est aussi dans l'onglet « Équilibre » du portefeuille) : concentration, devises, secteurs, part du risque, corrélations, pertes passées et scénarios de choc (marché -30 %, dollar -10 %, or -20 %).
- **Fiche valeur** en sections (Résumé, Prix juste, Activité, Historique, Valorisation, Thèse) : seule la section choisie se calcule. Valorisation : scénarios à 5 ans. Thèse : conditions de vente chiffrées.
- **Backtest**, second mode « Méthodes de notation : test à date » : les méthodes testées sans regarder l'avenir.
- **Recherche** dans la barre latérale : tapez un nom ou un ticker pour ouvrir sa fiche depuis n'importe quelle page.

Le projet est versionné avec Git (dépôt à la racine du dossier « Claude investissement ») : chaque changement peut être annulé. Tests : `.venv\Scripts\python.exe -m pytest tests -q` (calculs) et `-m pages` (affichage de toutes les pages, une minute). Ils utilisent le jeu d'essai `tests/jeu_essai/` (16 valeurs aux données figées, sans réseau ni données personnelles) ; `PF_TESTS_REELS=1` pour les lancer sur vos données. La variable `PF_DOSSIER` désigne un autre dossier de données que celui du code.

## Avertissement

Outil d'aide à la décision, pas un conseil en investissement personnalisé. Les données gratuites (Yahoo Finance, recoupées avec la SEC pour les sociétés américaines et avec la BCE pour les changes, prolongées par les rapports ESEF en Europe) peuvent être erronées : vérifiez les chiffres clés dans les publications des entreprises avant d'acheter. Les performances passées, et a fortiori les backtests, ne préjugent pas des performances futures.
