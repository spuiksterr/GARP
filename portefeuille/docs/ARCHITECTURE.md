# Architecture

À lire en premier avant de modifier le code. Le *pourquoi* des calculs est dans [METHODE.md](METHODE.md) ; ici, le *où*.

## Trajet des données

```
Sources externes                      Cache (data/cache/)                  Calculs                         Affichage
────────────────                      ───────────────────                  ───────                         ─────────
Yahoo (fiches)        ── data ──▶     fondamentaux/<TICKER>.json ─┐
SEC companyfacts      ── sec ───▶     sec/<TICKER>.json ──────────┤
ESEF (filings.xbrl)   ── esef ──▶     esef/<TICKER>.json ─────────┼─▶ postes.historique ─┐
Yahoo (cours)         ── data ──▶     prix.parquet ───────────────┤                      ├─▶ metrics.compute_all ─▶ indicateurs.parquet
BCE (changes)         ── data ──▶     fx.parquet ─────────────────┘                      │        (une ligne par valeur)
                                                                                         │
config/univers.csv, config/strategie.json, config/cas_particuliers.csv ──────────────────┘
                                                                                                   │
                                                          scoring.build_screener ◀────────────────┘
                                                          (filtres, piliers, score, rang, alertes)
                                                                   │
                                     ┌─────────────────────────────┼──────────────────────────┐
                                     ▼                             ▼                          ▼
                              pf/ui.py (cache Streamlit)     pf/__main__.py (CLI)       pf/contexte.py (textes pour Claude)
                                     │
                                     ▼
                              vues/*.py (15 pages, app.py)

Données de la nuit : chaque nuit, .github/workflows/donnees.yml lance pf maj sur GitHub (cache conservé), puis
pf export-outil, qui lit d'abord pendant 10 minutes les sources SEC des fiches (dirigeants, ventilation :
export_outil.prechauffer) et publie garp-outil.zip dans la release « donnees ». Aucune donnée personnelle
n'y est exportée. Les sources SEC ne sont lues sur GitHub qu'avec le secret `SEC_CONTACT` (variable
`PF_CONTACT_SEC`).

Outil du PC installé (GARP-Setup, Windows) : cet outil lui-même, avec son Python
(installateur/preparer_outil.ps1). GARP.pyw → pf/autonome.py (autonome.json présent) :
PF_DOSSIER = %LOCALAPPDATA%\Climax\donnees, PF_AUTONOME=1. Chaque nuit, pf export-outil publie
garp-outil.zip (config/, data/cache/, data/historique/) ; la barre latérale le télécharge et l'installe
fichier par fichier, sans toucher au profil ni au journal des transactions. Pas de pf maj sur ce poste.
L'archive contient aussi le screener tout prêt (data/cache/screener.parquet, scoring.enregistrer_screener) avec son
empreinte (stratégie, indicateurs, corrections des regards, code du calcul) : ui.screener le lit en 0,05 s si
l'empreinte correspond au poste, sinon le recalcule. scipy, yfinance et pf.maj ne sont importés qu'à l'usage :
l'interface se charge en 1,5 s environ au lieu de 10.

Sources annexes, lues à part : 13F (investisseurs → sec/13f/), élus (congres → congres/),
formulaires 4 (dirigeants), presse Google News (actualites → actualites/), composition des indices (indices).
```

- **Mise à jour** : `maj.tout_mettre_a_jour` enchaîne `data.update_all` (téléchargements), `metrics.compute_all`, `scoring.build_screener`, puis crée les fiches de thèse manquantes. Même code pour le bouton de l'interface (`ui.run_update`) et la commande `pf maj`.
- **Niveaux** : rapide (cours et changes), normal (en plus, un quart des fiches de fondamentaux par roulement, `config.renouvellement`), complet (tout).
- **Le screener n'est pas stocké** : il est recalculé à partir de `indicateurs.parquet` à chaque chargement (`ui.screener`, en cache Streamlit une heure, invalidé quand les fichiers changent).
- **Historique** : Yahoo donne 4 exercices ; `postes.prolonger` l'allonge avec la SEC (américaines) ou l'ESEF (européennes), seulement si les deux sources concordent sur au moins deux exercices communs.

## Dossiers

Tous les chemins sont dans `pf/config.py`. `PF_DOSSIER` déplace les données, `PF_PROFIL` le seul profil.

| Dossier | Contenu | Dans Git |
|---|---|---|
| `pf/` | Calculs, accès aux données, ligne de commande | Oui |
| `vues/`, `app.py` | Pages Streamlit et navigation | Oui |
| `config/` | Univers, réglages de la méthode, listes d'investisseurs et d'élus suivis | Oui |
| `profil/` | Portefeuille, watchlist, surveillance, règles de vente, scénarios, `prive.json` | **Non** (personnel) |
| `profil.exemple/` | Profil fictif, copié dans `profil/` sur une installation neuve | Oui |
| `data/` | Cache des sources, journal d'opérations `transactions.csv`, historique des scores `historique/`, journaux | **Non** |
| `theses/` | Une fiche de thèse par valeur détenue ou étudiée | **Non** (personnel) |
| `rapports/` | Exports Excel | **Non** |
| `tests/` | Tests ; `jeu_essai/` = 16 valeurs aux données figées | Oui |
| `docs/` | Méthode, architecture | Oui |

## Modules de `pf/`

**Socle**

| Module | Rôle |
|---|---|
| `config` | Chemins, lecture/écriture CSV « à la française » (`read_csv_fr`, `write_csv_fr`), JSON, écriture atomique, univers, stratégie, portefeuille modèle |
| `formats` | Nombres et pourcentages à la française |
| `data` | Téléchargements Yahoo et BCE, cache des fiches, cours, changes, conversion en euros ; `update_all` |
| `maj` | Orchestration d'une mise à jour et son compte rendu |
| `sauvegarde` | Archive datée des données personnelles dans le dossier choisi (`pf sauvegarde`, et à chaque mise à jour) |
| `verifier` | Contrôles de cohérence (`pf verifier`) : univers, fichiers de configuration, cours, fiches |

**Sources de comptes et annexes**

| Module | Rôle |
|---|---|
| `sec` | Comptes officiels SEC (us-gaap et ifrs-full), recoupement avec Yahoo ; table `CONCEPTS` |
| `esef` | Rapports annuels européens (filings.xbrl.org) |
| `postes` | Table de correspondance des postes et historique annuel unique, prolongé par la SEC ou l'ESEF |
| `historique` | Données des graphiques de la fiche (un exercice par ligne + 12 mois) |
| `ventilation` | Chiffre d'affaires par activité et par zone (SEC) |
| `dirigeants` | Achats et ventes des dirigeants (formulaires 4) |
| `investisseurs` | Portefeuilles 13F des grands investisseurs |
| `congres` | Transactions déclarées des élus (STOCK Act, PDF) |
| `actualites` | Presse (Google News), déclarations, signaux de l'outil |
| `indices` | Élargissement de l'univers (iShares, annuaire Nasdaq) |

**Calculs**

| Module | Rôle |
|---|---|
| `metrics` | Indicateurs par valeur (`compute_one`, ~200 lignes) et pour tout l'univers (`compute_all`) |
| `valuation` | DCF par les « value drivers », TRI et croissance implicites |
| `sante` | Piotroski, Altman, Beneish |
| `homme_cle` | Risque homme-clé (0 à 10) : dirigeants Yahoo gardés dans le cache des fondamentaux (`info.dirigeants`), part des initiés, risque du conseil ISS ; corrections dans `config/homme_cle.csv` ; `pf homme-cle` relit les dirigeants sans attendre le renouvellement des fiches |
| `moat` | Moat estimé |
| `criteres` | Six critères de qualité remplis ou non |
| `regards` | Note sur 5 selon quatre regards (Buffett, Munger, Fisher, Smith), lus un par un : repères, hors note GARP |
| `scoring` | Filtres d'exclusion, piliers, note GARP (`score` : croissance 40 %, valorisation 35 %, qualité 25 %, `POIDS_GARP`), alertes, `build_screener` ; empreinte du screener préparé limitée aux filtres, à la valorisation et aux critères |
| `prix_juste` | Prix d'achat juste à un multiple jugé raisonnable |
| `positions` | Photo du portefeuille : quantités par ligne prises au dernier import (`profil/positions.csv`, remplacée à chaque import) ; valorisée au dernier cours pour les poids réels (onglet Équilibre, tableau de bord, risques). À défaut, positions du journal `data/transactions.csv` (lecture seule) |
| `prix_achat` | Prix juste au rendement exigé (modèle du TRI implicite, entrées de `entrees_valorisation`), prix d'achat après marge de sécurité, verdict ; réglages dans `profil/prix_achat.json` ; page « La bonne action au bon prix », analyse du portefeuille, en-tête de la fiche et tableau de bord |
| `scenarios` | Scénarios à 5 ans enregistrés (`profil/scenarios.csv`) |
| `regles` | Conditions de vente chiffrées (`profil/regles_vente.csv`) |
| `photos` | Photo datée du screener à chaque mise à jour normale ou complète (`data/historique/scores.parquet`) : évolution du rang, changements de statut, futur test sans biais |

**Portefeuille**

| Module | Rôle |
|---|---|
| `portfolio` | Construction sous contraintes, pondération, caractéristiques |
| `backtest` | Backtest d'une allocation, en euros, dividendes réinvestis |
| `backtest_pit` | Backtest « à date » des méthodes de notation |
| `tracker` | Suivi réel à partir de `data/transactions.csv` (positions, performance, apport du mois) |
| `risques` | Concentration, devises, corrélations, pertes, chocs ; garde-fous de concentration (`suivi.garde_fous` de `strategie.json`) |
| `simulation` | « Et si j'ajoute cette ligne ? » : avant / après sur le portefeuille réel (page Risques, bouton de la fiche) |
| `watchlist` | Watchlist (`profil/watchlist.csv`) |
| `theses` | Fiches `theses/TICKER.md` |

**Sorties**

| Module | Rôle |
|---|---|
| `ui` | Briques Streamlit communes : thème, graphiques, tableaux, données en cache, barre latérale |
| `contexte` | Synthèses texte pour la CLI et les commandes Claude |
| `__main__` | Ligne de commande `pf <commande>` |
| `bureau` | Version bureau : fenêtre pywebview ouverte aussitôt sur un écran d'attente en trois étapes (moteur, outil et données, interface, avec le temps écoulé), puis branchée au serveur sans console (`pf bureau`, `GARP.pyw`, raccourcis par `creer_raccourcis.ps1`) ; serveur sur 127.0.0.1 |
| `serveur` | Lanceur du serveur de la fenêtre (`python -m pf.serveur app.py …`) : charge pf.ui puis démarre Streamlit dans le même processus, pour que la première page trouve les modules en mémoire |
| `autonome` | Version installée par `GARP-Setup` (repérée par `autonome.json` à côté du code) : données dans `%LOCALAPPDATA%\Climax\donnees`, accès anonyme au dépôt public (jeton GitHub facultatif, chiffré par Windows), téléchargement et installation de `garp-outil.zip`, nouvelles versions |
| `export_outil` | Archive des données publiques (configuration, cache, historique des scores) pour la version installée : `pf export-outil`, publiée chaque nuit |
| `import_portefeuille` | Import d'un portefeuille (export du courtier en CSV ou classeur Excel, tableau collé, liste tapée ; chaque feuille Excel avec une ligne d'en-tête reconnue devient un tableau tabulé, `textes_fichier`) ; page `vues/importer.py` |

## Pages (`vues/`)

Déclarées dans `app.py` : Tableau de bord, « Trouver » (la bonne action au bon prix, screener, fiche, watchlist), « Mon portefeuille » (analyse, risques, import), « Explorer » pour le reste ; tous dépliés (`st.navigation(expanded=True)`). Chaque page est un script Streamlit qui lit ses données par `pf.ui` (jamais directement les fichiers du cache). La plus grosse est `fiche.py` (~630 lignes, sections Résumé, Prix juste, Activité, Historique, Valorisation, Thèse).

## Recettes

**Ajouter un indicateur**
1. Le calculer dans `metrics.compute_one` (ou une fonction appelée par lui) et l'ajouter au dictionnaire de la valeur.
2. S'il compte dans la note GARP : `scoring.PILIERS` (croissance, valorisation ou qualité), `POIDS_GARP` et la section 3 de `METHODE.md`. Un repère hors note s'affiche sans toucher au calcul. S'il change les paramètres de valorisation, `metrics_a_jour` impose un recalcul.
3. L'afficher : colonne dans `vues/screener.py` ou carte dans `vues/fiche.py`.
4. Un test dans `tests/test_calculs.py` sur un cas chiffré à la main, et vérifier la valeur sur le jeu d'essai.
5. Recalculer : `pf maj --rapide`.

**Ajouter une page** : un fichier `vues/<nom>.py`, une ligne `st.Page` dans `app.py`, les données via `pf.ui`. `tests/test_pages.py` la teste automatiquement.

**Ajouter une source** : un module `pf/<source>.py` avec un cache dans `CACHE_DIR / "<source>"`, écrit par `config.ecrire_json` (atomique), un `User-Agent` générique, des nouveaux essais espacés ; un appel dans `data.update_all` avec sa durée dans `durees`. Les tests ne doivent jamais toucher le réseau : simuler la réponse.

**Ajouter une commande** : une sous-commande dans `__main__.main` (argparse), le texte dans `README.md`.

## Tests

- `tests/test_calculs.py` : calculs, sur des cas construits ou le jeu d'essai (`pytest tests -q`, quelques secondes).
- `tests/test_pages.py` : chaque page et chaque section de la fiche s'affichent sans erreur (`-m pages`, une minute).
- `tests/test_non_regression.py` : indicateurs et score de cinq valeurs comparés à `tests/attendus_indicateurs.json` ; un écart voulu se régénère avec `PF_REGENERER_ATTENDUS=1`.
- Couverture : `pytest tests -m "pages or not pages" --cov=pf` (73 % au 14/11/2026 ; les modules qui téléchargent sont les moins couverts).
- `tests/conftest.py` copie `tests/jeu_essai/` dans un dossier temporaire (`PF_DOSSIER`) et coupe le réseau. `PF_TESTS_REELS=1` teste sur les données du poste.
- GitHub lance les deux séries sous Linux et Windows à chaque envoi (`.github/workflows/tests.yml`).

## Pièges connus

- **Yahoo limite le débit** : d'où le renouvellement par roulement et les nouveaux essais. Ne pas paralléliser davantage.
- **Windows verrouille les fichiers** (antivirus, indexation) : `ecriture_atomique` réessaie `os.replace`.
- **Fins de ligne mixtes** (LF et CRLF selon les fichiers) : réécrire un fichier en Python avec `newline=""` ou en octets, et vérifier `git diff --stat`.
- **Scripts en ligne** : pas de code Python avec guillemets ou barres obliques inverses dans un heredoc ou une commande `-c` ; l'écrire dans un fichier.
- **Mémoire** : le poste a 8 Go ; `OPENBLAS_NUM_THREADS=1` pour les tests d'affichage.
- **CSV** : séparateur `;`, UTF-8 (BOM toléré à la lecture), jamais de `;` dans un texte.
