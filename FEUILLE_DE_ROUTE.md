# Feuille de route

Trame des améliorations du projet, rédigée le 13 novembre 2026 après une analyse du code. Chaque ticket est écrit pour être confié tel quel à un agent (Claude Opus) : il dit pourquoi, quoi, où, et à quoi on reconnaît que c'est fini.

**Tickets sur GitHub :** https://github.com/spuiksterr/GARP/issues (titre `[X-00]`, étiquettes de phase, priorité et taille, un jalon par phase). Ce fichier reste la référence ; `.github/creer_tickets.py --envoyer` crée les tickets ajoutés ici, sans doublon.

**Objectif du propriétaire :** une application d'analyse d'actions et de construction de portefeuille, gérée depuis GitHub (code, tickets, vérifications automatiques, travail des agents).

## 1. Mode d'emploi pour l'agent

1. Lire `CLAUDE.md` (conventions, fichiers protégés), puis le ticket en entier et ses dépendances.
2. Un ticket = une branche = une demande de fusion. Ne pas regrouper plusieurs tickets.
3. Avant de coder, lire les fichiers cités. Si le constat du ticket n'est plus vrai, le dire et s'arrêter.
4. Vérifier avant de livrer, depuis `portefeuille/` :
   - `.venv/Scripts/python.exe -m pytest tests -q` après toute modification de `pf/` ;
   - `.venv/Scripts/python.exe -m pytest tests -q -m pages` après une modification de `vues/` ou de `pf/ui.py`.
5. Ne jamais modifier sans accord explicite du propriétaire : `portefeuille_modele.csv`, `selection_claude_2026-10.csv`, `surveillance.csv`, `transactions.csv`. Ne jamais toucher à `ai-berkshire-main/`.
6. Tout texte visible (interface, documentation, messages de commit) est en français. CSV : séparateur `;`, UTF-8, jamais de `;` dans un texte.
7. Mettre à jour `README.md` et `docs/METHODE.md` quand le comportement change, puis cocher le ticket ici.
8. Un ticket marqué « Décision » attend une réponse du propriétaire : ne pas trancher à sa place.

**Priorités :** P0 bloque le reste, P1 forte valeur, P2 utile, P3 confort. **Tailles :** S (moins d'une heure), M (une séance), L (plusieurs séances, à découper).

## 2. État des lieux

| Sujet | Constat |
|---|---|
| Code | 35 modules dans `pf/` (7 850 lignes), 14 pages dans `vues/` (2 700 lignes), une ligne de commande (`pf/__main__.py`), 4 commandes Claude dans `.claude/skills/` |
| Tests | 82 tests de calcul dans un seul fichier de 1 257 lignes, 18 tests d'affichage qui lisent les données réelles du poste |
| Données | 1 757 valeurs (S&P 500, STOXX 600, Nasdaq Global Select d'au moins 1 Md$) ; 133 Mo de cache ; sources : Yahoo, SEC, rapports européens ESEF, BCE |
| Résultat du tri | 850 éligibles, 905 exclues, 2 fonds ; 637 valeurs n'ont que 4 exercices d'historique ou moins |
| Git | 19 commits, dépôt privé `spuiksterr/Climax` (branche `main`) depuis le 14/11/2026, une modification non enregistrée (`watchlist.csv`) |
| Outillage | Pas de vérification automatique, pas de contrôle de style, pas de `pyproject.toml`, scripts Windows seulement (`.bat`, `.ps1`) |
| Mise à jour | Manuelle : la tâche planifiée n'est pas enregistrée ; 5 min (rapide) à 20-30 min (complète) |

**Points forts à préserver :** documentation et commentaires soignés, écritures de fichiers sûres, recoupement des comptes Yahoo avec la SEC, fichiers protégés, séparation nette entre calcul (`pf/`) et affichage (`vues/`).

**Faiblesses principales :**

1. Rien ne tourne hors du poste du propriétaire : les tests d'affichage dépendent de ses données, les chemins sont fixés à l'import (`pf/config.py`).
2. Données personnelles et code sont mêlés dans `config/` ; les thèses et le journal d'opérations ne sont sauvegardés nulle part.
3. Yahoo est la seule source de cours et de fondamentaux récents.
4. La méthode de notation n'est pas validée : au test à date (2012-2026), les sélections qualité et valeur font 1,5 à 2 points de moins par an que l'univers à poids égaux.
5. La construction de portefeuille ne dit pas ce qu'un ajout change au risque du portefeuille réel.
6. Aucun historique des scores : impossible de voir l'évolution d'un rang ou de tester la méthode sans biais à l'avenir.

## 3. Décisions à prendre par le propriétaire

| N° | Question | Options | Bloque |
|---|---|---|---|
| DEC-1 | Où tourne l'application ? | **Tranché le 14/11/2026 :** A, sur le PC ; le téléphone y accède par le réseau privé Tailscale (U-11), et une fenêtre dédiée sert de version bureau (U-10) | G-05, D-08, U-08 |
| DEC-2 | Données personnelles dans le dépôt privé, ou séparées du code ? | **Tranché le 14/11/2026 :** séparées, dans `portefeuille/profil/` exclu du dépôt | G-05 |
| DEC-3 | Nom de l'application et du dépôt | **Tranché :** application nommée **G.A.R.P** le 18/11/2026 (d'abord Climax, le 14/11) ; dépôt public `spuiksterr/GARP` le 22/11/2026, le dépôt privé `spuiksterr/Climax` gardé en archive | G-03, U-01 |
| DEC-4 | Qui fusionne les demandes des agents ? | **Tranché le 14/11/2026 :** relecture et fusion par le propriétaire, jamais de fusion automatique | K-01 |
| DEC-5 | Pseudo GitHub, adresse anonyme et nom d'auteur des commits | **Tranché le 14/11/2026 :** pseudo et auteur `spuiksterr`, adresse `264869162+spuiksterr@users.noreply.github.com` | G-01, G-03 |
| DEC-6 | Accords en attente sur des fichiers protégés | Voir la liste ci-dessous | – |
| DEC-7 | Sources de données avec clé ou payantes, pour l'historique allemand et suisse | Écarté le 08/11/2026 ; à rouvrir seulement sur demande | D-11 |
| DEC-8 | Ajouter une valeur hors indices depuis l'interface | Écarté une première fois ; depuis, On et Sterling ont été ajoutées à la main | U-02 |

**Accords en attente (DEC-6) :**

- retirer Novo Nordisk de `surveillance.csv` ;
- ajouter Deckers à `portefeuille_modele.csv` ;
- renommer l'indicateur « P/FCF hors SBC » ;
- baisser le poids de la valorisation dans le score ;
- ajouter MP Materials et Neo Performance à l'univers ;
- Sterling : prix visé de 250 $, ligne de surveillance, trois scénarios, règle de vente chiffrée.

## 4. Les chantiers

### Phase 0 : mise sur GitHub

| N° | Ticket | P | Taille |
|---|---|---|---|
| G-01 | Anonymiser l'auteur des commits (**fait le 14/11/2026**) | P0 | S |
| G-02 | Enregistrer ou écarter la watchlist en attente (**fait le 14/11/2026**) | P0 | S |
| G-03 | Créer le dépôt privé et envoyer le projet (**fait le 14/11/2026**) | P0 | S |
| G-04 | README à la racine et licence (**fait le 14/11/2026**, sans capture ni licence : dépôt privé) | P1 | S |
| G-05 | Séparer les données personnelles du code (**fait le 14/11/2026**) | P1 | M |
| G-06 | Créer les tickets GitHub depuis cette feuille de route (**fait le 14/11/2026** : `.github/creer_tickets.py`, relançable sans doublon) | P1 | S |
| G-07 | Protéger la branche principale, gabarits de ticket et de demande de fusion (**gabarits faits le 14/11/2026**) | P1 | S |

- **G-01.** Les 15 commits portent l'adresse Gmail du propriétaire. La remplacer par son adresse GitHub anonyme (`…@users.noreply.github.com`) sur tout l'historique, puis régler `git config user.name` et `user.email` du dépôt. *Fini quand :* `git log --format=%ae | sort -u` ne montre que l'adresse anonyme. *Dépend de :* DEC-5.
- **G-02.** `portefeuille/config/watchlist.csv` a des ajouts faits depuis l'application et jamais enregistrés. Les committer, sauf si G-05 sort ce fichier du dépôt.
- **G-03.** Le propriétaire crée un dépôt vide et privé ; l'agent ajoute le dépôt distant et pousse `main`. Windows ouvre une fenêtre de connexion que le propriétaire valide. *Fini quand :* `git status` indique une branche à jour avec `origin/main`.
- **G-04.** Le dépôt n'a pas de README à sa racine (il est dans `portefeuille/`). En écrire un court : ce que fait l'application, une capture, comment l'installer, lien vers la méthode. Ajouter une licence si le code devient public, et citer le projet `ai-berkshire` (licence MIT) dont la méthode s'inspire.
- **G-05.** `config/` mêle des fichiers généraux (`univers.csv`, `strategie.json`, `cas_particuliers.csv`, `investisseurs.csv`, `elus.csv`) et personnels (`portefeuille_modele.csv`, `watchlist.csv`, `surveillance.csv`, `regles_vente.csv`, `scenarios.csv`, `selection_claude_2026-10.csv`, `actualites.csv`). Déplacer les personnels dans un dossier `profil/`, avec un dossier `profil.exemple/` fictif versionné. Rendre l'emplacement réglable par une variable d'environnement (voir Q-04). *Fini quand :* l'application démarre sur un clone neuf avec le profil d'exemple, et les tests passent sans le profil réel. *Dépend de :* DEC-2. Demande l'accord du propriétaire, car des fichiers protégés sont déplacés.
- **G-06.** Un script crée les étiquettes (phase, priorité, taille), les jalons (une phase = un jalon) et un ticket par ligne de ce document, avec `gh`. *Fini quand :* chaque ticket d'ici a son ticket GitHub, et ce fichier renvoie vers eux.
- **G-07.** Interdire la poussée directe sur `main`, exiger les vérifications de Q-03. Gabarit de demande de fusion avec la liste du § 1. *Fait le 14/11/2026 :* gabarits dans `.github/`. *Reste :* la protection de branche, que GitHub réserve aux dépôts publics ou aux comptes payants (Pro) pour un dépôt privé ; à défaut, la discipline « une branche, une demande de fusion » du § 1 et la relecture par le propriétaire (DEC-4).

### Phase 1 : socle technique

| N° | Ticket | P | Taille |
|---|---|---|---|
| Q-01 | `pyproject.toml` et paquet installable (**fait le 14/11/2026**) | P1 | S |
| Q-02 | Contrôle de style avec ruff (**fait le 14/11/2026** : ruff, lignes de 150 au plus pour l'existant) | P1 | M |
| Q-03 | Vérifications automatiques sur GitHub (**fait le 14/11/2026**, sans ruff : voir Q-02) | P0 | M |
| Q-04 | Dossiers de données réglables et jeu d'essai (**fait le 14/11/2026**) | P0 | L |
| Q-05 | Mesure de la couverture et tests manquants (**fait le 14/11/2026** : couverture 73 %, non-régression sur 5 valeurs ; reste les modules qui téléchargent) | P1 | L |
| Q-06 | Découper les grandes fonctions | P2 | L |
| Q-07 | Découper `tests/test_calculs.py` par module | P2 | S |
| Q-08 | Dictionnaire des colonnes et contrôle des fichiers de configuration | P1 | M |
| Q-09 | Journalisation et erreurs précises | P2 | M |
| Q-10 | Lancement hors Windows | P3 | S |
| Q-11 | Mise à jour surveillée des dépendances | P2 | S |
| Q-12 | Commande `pf verifier` (**fait le 14/11/2026** ; constat réel : doublon ASML, voir D-02) | P1 | M |
| Q-13 | Schéma d'architecture (**fait le 14/11/2026** : `docs/ARCHITECTURE.md`) | P1 | S |

- **Q-01.** Aujourd'hui : `requirements.txt` et `pythonpath = .` dans `pytest.ini`. Créer `pyproject.toml` (métadonnées, dépendances, point d'entrée `pf`), garder des versions figées. *Fini quand :* `pip install -e .` puis `pf --help` fonctionnent dans un environnement neuf.
- **Q-02.** Aucune règle de style ; 336 lignes dépassent 120 caractères. Configurer ruff (style et erreurs courantes), corriger, sans changer le comportement. Un commit de mise en forme séparé des corrections.
- **Q-03.** Flux GitHub Actions : tests de calcul à chaque poussée, sous Windows et Linux, Python 3.12 ; ruff ; tests d'affichage une fois Q-04 fait. *Fini quand :* une demande de fusion affiche les vérifications, et un test cassé la bloque.
- **Q-04.** Les chemins sont des constantes de `pf/config.py` et les tests d'affichage lisent le cache réel. Introduire une variable `PF_DOSSIER` qui déplace `config/`, `data/` et `theses/`. Construire un jeu d'essai versionné d'une quinzaine de valeurs fictives ou figées (une américaine, une européenne, une banque, un fonds, une valeur à historique court). *Fini quand :* les 18 tests d'affichage passent sur un clone neuf, sans réseau. C'est le ticket qui rend le projet « gérable depuis GitHub ».
- **Q-05.** Ajouter `pytest-cov`. Modules sans test direct : `actualites`, `contexte`, `theses`, `historique`, `formats`, la ligne de commande, et `metrics.compute_one` dans son ensemble. Ajouter des tests de non-régression : indicateurs attendus pour cinq valeurs du jeu d'essai. *Dépend de :* Q-04.
- **Q-06.** Fonctions longues : `metrics.compute_one` (199 lignes), `contexte.contexte_valeur` (105), `tracker.contribution_plan` (89), `data.update_all` (86), `criteres.evaluer` (83). Les découper par bloc logique, résultats identiques. *Fini quand :* les tests de non-régression de Q-05 donnent les mêmes chiffres. *Dépend de :* Q-05.
- **Q-08.** Le screener a 128 colonnes, aux noms tantôt français tantôt anglais, sans liste de référence. Écrire un dictionnaire (nom, libellé, unité, formule, module d'origine) qui alimente les info-bulles et la documentation. Contrôler à la lecture le format des CSV de configuration, avec un message d'erreur qui nomme le fichier et la ligne.
- **Q-09.** 30 `except Exception` avalent des erreurs, et les messages passent par `print`. Passer au module `logging` avec un journal dans `data/journaux`, et resserrer les exceptions là où la cause est connue.
- **Q-10.** `installer.bat`, `lancer.bat`, `mettre_a_jour.bat` et `planifier_mise_a_jour.ps1` n'existent que pour Windows. Ajouter `pf lancer` et `pf installer`, et réduire les `.bat` à un appel.
- **Q-11.** Activer Dependabot. yfinance émet déjà des avertissements de dépréciation avec pandas 3.1.
- **Q-12.** Une commande qui contrôle l'état du projet : doublons de l'univers, secteurs inconnus, valeurs sans cours ou au cours figé, fiches incomplètes, fichiers de configuration mal formés. Exemple réel à détecter : ASML est présente deux fois (`ASML.AS` et `ASML` au Nasdaq).
- **Q-13.** `docs/ARCHITECTURE.md` : le trajet des données (sources, cache, indicateurs, score, pages), le rôle de chaque module, où ajouter un indicateur, une page ou une source. C'est ce qu'un agent lit en premier.

### Phase 2 : données

| N° | Ticket | P | Taille |
|---|---|---|---|
| D-01 | Entretien automatique de l'univers | P1 | M |
| D-02 | Doublons de cotation (**fait le 14/11/2026** : même racine de ticker et même premier mot, ASML retirée) | P1 | S |
| D-03 | Historique daté des scores (**fait le 14/11/2026** : première vraie photo à la prochaine mise à jour normale) | P0 | M |
| D-04 | Recalcul partiel des indicateurs | P2 | M |
| D-05 | Contrôles de qualité des données | P1 | L |
| D-06 | Page « État des données » | P2 | M |
| D-07 | Couche commune pour les sources, et source de secours des cours | P2 | L |
| D-08 | Mise à jour planifiée | P1 | S à L |
| D-09 | Sauvegarde des données personnelles (**fait le 14/11/2026** : `pf sauvegarde` vers le OneDrive personnel, refaite à chaque mise à jour) | P0 | S |
| D-10 | Stockage du cache | P3 | L |
| D-11 | Historique allemand et suisse | P3 | L |

- **D-01.** L'import d'indices ajoute sans jamais retirer. Kenvue (rachetée) et un droit de souscription Unipol sont restés avec un cours figé jusqu'à un retrait manuel. Ajouter à `pf indices` une liste de retraits proposés (sortie d'indice, cours figé depuis plus de 10 jours, titre qui n'est pas une action), que le propriétaire valide. Ne jamais proposer une ligne détenue ou surveillée.
- **D-02.** `indices.extend_nasdaq` écarte les sociétés déjà présentes en comparant les noms, ce qui a laissé passer `ASML` à côté de `ASML.AS`. Comparer aussi par identifiant (ISIN ou code SEC) et retirer les doublons existants.
- **D-03.** Enregistrer à chaque mise à jour complète une photo datée du screener (statut, score, rang, piliers, cours, estimations de bénéfices). *Fini quand :* la fiche montre l'évolution du rang, et le tableau de bord signale un changement de statut. Ce ticket ouvre A-01, A-08 et A-10.
- **D-04.** Le recalcul prend environ 2 min 30 pour 1 757 valeurs, à chaque mise à jour. Ne recalculer que les valeurs dont les comptes, le cours ou les réglages ont changé. Tenir compte des 8 Go de mémoire du poste.
- **D-05.** Contrôles automatiques avec un rapport : chiffre d'affaires négatif, capitalisation incohérente avec cours × actions, comptes et cotation dans deux devises (certificats de sociétés chinoises ou israéliennes au Nasdaq), division d'actions non détectée, marge hors bornes. Les valeurs douteuses sont marquées dans le screener.
- **D-06.** Une page qui montre la date de chaque source, la durée des étapes, les fiches en échec et le résultat de D-05.
- **D-07.** Chaque source a sa propre logique de reprise, de pause et de cache. Définir une interface commune, puis ajouter une seconde source de cours pour les jours où Yahoo refuse.
- **D-08.** Selon DEC-1 : A, le propriétaire lance `planifier_mise_a_jour.ps1` (rien à coder) ; C, un flux GitHub planifié calcule et publie les données. Risque à vérifier d'abord : Yahoo limite souvent les requêtes venant de serveurs.
- **D-09.** `theses/`, `data/transactions.csv` et `profil/` (portefeuille, listes de suivi, `prive.json`) sont exclus de Git et n'ont aucune sauvegarde. Proposer un second dépôt privé ou une archive datée. *Fini quand :* une perte du disque ne fait perdre ni les thèses ni le journal d'opérations.

### Phase 3 : analyse

| N° | Ticket | P | Taille |
|---|---|---|---|
| A-01 | Valider et régler le score par le test à date | P0 | L |
| A-02 | Notation propre aux banques, assureurs, foncières et services publics | P1 | L |
| A-03 | Secteurs à deux niveaux | P2 | M |
| A-04 | Comparaison aux pairs | P1 | M |
| A-05 | Filtre de dilution qui reconnaît les fusions | P1 | M |
| A-06 | Valorisation : sensibilités et marge de sécurité | P2 | M |
| A-07 | Qualité des bénéfices | P2 | M |
| A-08 | Révisions des estimations | P2 | M |
| A-09 | « Pourquoi ce rang ? » | P1 | M |
| A-10 | Alertes sur tout l'univers | P2 | S |
| A-11 | Thèses dans un format lisible par l'application | P1 | M |
| A-12 | Activité par segment dans le temps | P3 | M |

- **A-01.** Constat (`docs/METHODE.md`, backtest à date) : de 2012 à 2026, qualité et valeur font moins bien que l'univers à poids égaux. Le test ne reconstitue que quatre piliers, sans les filtres ni les quatre regards, et subit le biais du survivant. À faire : reconstituer les filtres à date, tester les poids des piliers, mesurer par sous-période, chercher une liste des anciens membres du S&P 500. *Fini quand :* la méthode documente ce que le score apporte, ou est modifiée. Tout changement de poids demande l'accord du propriétaire.
- **A-02.** 905 exclues, dont l'essentiel des foncières et une grande part de l'énergie et des banques régionales, jugées avec des ratios d'industriel. Définir des indicateurs par famille (fonds propres et coût du risque pour une banque, ratio combiné pour un assureur, flux récurrent et endettement sur actifs pour une foncière).
- **A-03.** 18 secteurs maison ; les constructeurs automobiles sont rangés avec le luxe. Ajouter un niveau « industrie » (celle de Yahoo) sous le secteur.
- **A-04.** Sur la fiche, comparer la valeur à cinq à huit sociétés de la même industrie : marges, croissance, rentabilité, multiples, rang. *Dépend de :* A-03.
- **A-05.** 313 exclusions pour dilution, dont des fusions payées en actions ou des introductions en Bourse, corrigées une à une dans `strategie.json`. Détecter le cas (hausse du nombre d'actions et du chiffre d'affaires la même année) et le signaler au lieu d'exclure.
- **A-06.** Ajouter au calcul existant (`pf/valuation.py`) un tableau croissance × taux d'actualisation, une marge de sécurité, et un prix juste qui combine les méthodes déjà présentes.
- **A-07.** Écart entre résultat et trésorerie sur 5 ans, rentabilité hors écarts d'acquisition, pente et régularité des marges.
- **A-08.** Conserver les estimations de bénéfices à chaque mise à jour, puis mesurer leur révision sur 1 et 3 mois. *Dépend de :* D-03.
- **A-09.** Une section de la fiche décompose le score : contribution de chaque pilier, écart à chaque seuil de filtre, et ce qui ferait changer le statut.
- **A-10.** Alertes hors portefeuille : une valeur de la watchlist devient éligible, une valeur entre dans les 50 premières. *Dépend de :* D-03.
- **A-11.** Les fiches `theses/*.md` sont du texte libre. Ajouter un en-tête structuré (verdict, date, prix d'entrée, conditions de vente, date de dernière revue) que l'application lit, et faire écrire ce format par `/analyse-valeur`.

### Phase 4 : construction de portefeuille

| N° | Ticket | P | Taille |
|---|---|---|---|
| C-01 | Simulateur « et si j'ajoute cette ligne ? » (**fait le 14/11/2026** : page Risques et bouton de la fiche ; pas encore sur la page Construction) | P0 | M |
| C-02 | Expositions par thème et par facteur | P1 | L |
| C-03 | Autres méthodes de pondération et contraintes | P2 | M |
| C-04 | Du portefeuille réel au portefeuille cible | P1 | M |
| C-05 | Règles de taille de position | P2 | S |
| C-06 | Projection du patrimoine | P2 | M |
| C-07 | Test à date des règles de construction | P2 | L |
| C-08 | Répartition entre PEA et compte-titres | P2 | M |
| C-09 | Plusieurs portefeuilles candidats | P2 | M |
| C-10 | Garde-fous de concentration (**fait le 14/11/2026** : tableau de bord, page Risques, simulateur) | P1 | S |

- **C-01.** `pf/risques.py` décrit le portefeuille réel et `pf/portfolio.py` construit un portefeuille théorique ; rien ne relie les deux. Sur la fiche et la page Construction, simuler l'ajout, le retrait ou le changement de poids d'une ligne, et montrer l'effet sur la concentration, les secteurs, les devises, la volatilité, les scénarios de choc et la corrélation avec les lignes existantes. Exemple : deux lignes qui portent le même pari sur les centres de données.
- **C-02.** Regrouper les lignes par corrélation, mesurer l'exposition aux grands thèmes et aux facteurs (qualité, valeur, momentum, taille), et regarder dans les fonds détenus (matières premières, thèmes).
- **C-03.** Trois méthodes existent : poids égaux, score sur volatilité, variance minimale. Ajouter la parité de risque et un plafond de contribution au risque ; ajouter des plafonds par devise, par pays et par thème ; comparer les méthodes côte à côte.
- **C-04.** `tracker.contribution_plan` répartit un apport. Ajouter la trajectoire : combien de mois d'apports pour rejoindre la cible sans vendre, et le coût fiscal s'il fallait vendre.
- **C-06.** Simulation sur un horizon choisi, avec apports mensuels : fourchette de patrimoine et chance d'atteindre un objectif, avec ses limites rappelées à l'écran.
- **C-08.** Quelle ligne dans quelle enveloppe, selon l'éligibilité au PEA, son plafond et l'imposition des dividendes étrangers. Les règles fiscales sont à vérifier dans les textes en vigueur ; aucun conseil personnalisé.
- **C-09.** Généraliser ce qui existe pour la sélection Claude : un dossier de portefeuilles nommés, comparables dans le backtest et la page Risques.
- **C-10.** Seuils réglables dans `strategie.json` (poids d'une ligne, des trois premières, d'un secteur, corrélation moyenne), signalés à la construction et au tableau de bord.

### Phase 5 : suivi du portefeuille réel

| N° | Ticket | P | Taille |
|---|---|---|---|
| S-01 | Import des relevés du courtier | P1 | M |
| S-02 | Dividendes | P2 | M |
| S-03 | Aide à la déclaration fiscale | P3 | M |
| S-04 | Attribution de performance | P1 | M |
| S-05 | Journal des décisions | P2 | M |
| S-06 | Tableau de revue des thèses | P1 | S |
| S-07 | Rapport périodique | P2 | M |
| S-08 | Notifications | P3 | M |

- **S-01.** Lire l'export CSV du courtier, montrer les opérations nouvelles, et ne les écrire dans `transactions.csv` qu'après confirmation à l'écran (fichier protégé).
- **S-04.** Contribution de chaque ligne, secteur et devise à la performance ; part du change et part du titre ; écart à l'indice de référence.
- **S-05.** Relier chaque achat et chaque vente à sa thèse et à sa raison (les trois raisons de vendre de la méthode), puis mesurer après coup ce que la décision a rapporté.
- **S-06.** Une table des thèses : date de dernière revue, prochaine publication de résultats, statut (intacte, à réexaminer, invalidée). *Dépend de :* A-11.
- **S-07.** Un rapport mensuel ou trimestriel (performance, risques, alertes, thèses à revoir), produit par `/revue-portefeuille` ou par une tâche planifiée.
- **S-08.** Prévenir quand un prix visé est atteint ou une condition de vente remplie. Piste simple si DEC-1 = C : un ticket GitHub ouvert automatiquement.

### Phase 6 : interface

| N° | Ticket | P | Taille |
|---|---|---|---|
| U-01 | Nom, titre et icône de l'application | P2 | S |
| U-02 | Ajouter une valeur depuis l'interface | P2 | M |
| U-03 | Vitesse d'affichage | P1 | M |
| U-04 | Screener : vues enregistrées et comparaison côte à côte | P2 | M |
| U-05 | Glossaire et info-bulles | P2 | M |
| U-06 | Tests des interactions | P2 | M |
| U-07 | Mise à jour de l'application depuis GitHub | P1 | S |
| U-08 | Hébergement en ligne | P3 | L |
| U-09 | Premier lancement guidé | P3 | M |
| U-10 | Version bureau : fenêtre dédiée et raccourcis (**fait le 14/11/2026**) | P1 | M |
| U-11 | Version téléphone par le réseau privé Tailscale (**code fait le 14/11/2026** ; reste à installer Tailscale) | P1 | M |
| U-12 | Pages lisibles sur un écran de téléphone | P1 | M |

- **U-01.** Le titre est « Portefeuille long terme » (`app.py`). *Dépend de :* DEC-3.
- **U-02.** Aujourd'hui, ajouter On ou Sterling demande d'éditer `univers.csv` puis de lancer une mise à jour. Un formulaire vérifie le ticker auprès de Yahoo, propose pays, enveloppe et secteur, et charge la valeur. *Dépend de :* DEC-8.
- **U-03.** L'univers a grandi de 1 121 à 1 757 valeurs sur un poste de 8 Go. Mesurer le temps d'ouverture de chaque page, puis traiter les plus lentes.
- **U-04.** Filtres nommés et réutilisables, choix des colonnes, comparaison de deux à quatre valeurs.
- **U-05.** Un terme par notion, expliqué au survol, à partir du dictionnaire de Q-08. *Dépend de :* Q-08.
- **U-06.** Les tests d'affichage ne cliquent sur rien. Tester les formulaires (watchlist, règles de vente, scénarios, apport) sur des copies. *Dépend de :* Q-04.
- **U-07.** Un script récupère la dernière version depuis GitHub, met à jour les dépendances et lance les tests ; la barre latérale affiche la version installée.
- **U-10.** `pf bureau` et le raccourci « Climax » (`Climax.pyw`, `creer_raccourcis.ps1`) : serveur sans console, fenêtre pywebview (Edge WebView2), arrêt du serveur à la fermeture, ou branchement sur un serveur déjà lancé.
- **U-11.** `pf mobile` relaie le serveur local par `tailscale serve` (HTTPS, réseau privé seulement). Le propriétaire installe Tailscale sur le PC et le téléphone avec le même compte. Ensuite : vérifier sur le téléphone que la connexion WebSocket de Streamlit passe le relais, et que l'icône s'affiche à l'ajout à l'écran d'accueil.
- **U-12.** L'interface est pensée pour un grand écran (mise en page large, tableaux de 20 colonnes, quatre chiffres par ligne). Sur un téléphone : tableau de bord et fiche lisibles en une colonne, screener réduit aux colonnes essentielles, boutons atteignables au pouce. Mesurer d'abord avec un navigateur en largeur 390 px. *Dépend de :* U-11.
- **U-08.** Seulement si DEC-1 = B. Demande un accès protégé et un stockage des données.

### Phase 8 : application autonome (Android et Windows)

| N° | Ticket | P | Taille |
|---|---|---|---|
| M-01 | Données calculées chaque nuit sur GitHub et publiées (**fait le 14/11/2026**) | P0 | M |
| M-02 | Application Flutter : accueil, screener, fiche, portefeuille, watchlist, réglages (**fait le 14/11/2026**) | P0 | L |
| M-03 | Mises à jour depuis les Releases, APK signé (**fait le 14/11/2026** ; secrets de signature à poser par le propriétaire) | P0 | M |
| M-04 | Sauvegarde chiffrée du portefeuille de l'application | P1 | M |
| M-05 | Simulateur et risques dans l'application (**fait le 17/11/2026**) | P2 | L |
| M-06 | Thèses lisibles dans l'application (**en partie le 17/11/2026** : thèse saisie sur l'appareil ; les fiches `theses/*.md` du PC n'y sont pas) | P2 | M |
| M-07 | Notifications : statut changé, prix visé, condition de vente | P2 | M |
| M-08 | Recoupement SEC sur GitHub (historique de 10 ans des valeurs américaines) | P2 | S |
| M-09 | Import du portefeuille dans l'application : export de courtier, tableau collé, saisie ; vérification ligne par ligne (**fait le 14/11/2026**) | P0 | M |
| M-10 | Identité visuelle : logo 3D (Blender), icônes Android et Windows, écran de démarrage, accueil du premier lancement, charte `docs/MARQUE.md` (**fait le 14/11/2026**) | P1 | M |
| M-13 | Installateur Windows (`Climax-Setup.exe`, Inno Setup), mise à jour en un clic, page de téléchargement et QR code (**fait le 14/11/2026**) | P1 | S |
| M-11 | Ouvrir un export de courtier avec Climax depuis Android (« Partager » ou « Ouvrir avec ») | P2 | S |
| M-12 | Données lisibles sans jeton (release publique des seules données de marché) | P2 | S |
| M-14 | Méthodes d'évaluation dans l'application (screener, fiche, accueil, page « Méthodes », consensus) et profil investisseur (**fait le 15/11/2026**) | P1 | M |
| M-15 | Grands investisseurs (13F) et élus du Congrès dans l'application (**fait le 17/11/2026** ; 13F publiés une fois le secret `SEC_CONTACT` posé) | P1 | M |
| M-16 | Fiche complète dans l'application : prix juste, valorisation inversée, ventilation du CA, historique, achats des dirigeants (**fait le 17/11/2026**) | P2 | L |
| M-17 | Construction de portefeuille et backtest des méthodes dans l'application (**fait le 17/11/2026** : backtest du portefeuille face à l'indice ; celui « à date » des méthodes reste sur le PC) | P2 | M |
| M-18 | Suivi dans l'application : opérations, performance face à l'indice, apport du mois ; actualités (**fait le 17/11/2026**) | P2 | L |
| M-19 | Nouvelle identité visuelle : logo « Exponentielle » (courbe ocre, barres ivoire, fond anthracite), icônes, thème, charte (**fait le 15/11/2026**) | P1 | S |

- **M-04.** Le portefeuille et la watchlist ne vivent que dans l'appareil. Exporter et importer un fichier chiffré par une phrase de passe (vers OneDrive, ou d'un appareil à l'autre).
- **M-05.** Reprendre `pf/simulation.py` et `pf/risques.py` : il faut les rendements, donc des cours quotidiens ou hebdomadaires de toutes les lignes (déjà dans l'export, en hebdomadaire).
- **M-06.** Les thèses (`theses/*.md`) sont personnelles : les publier chiffrées, ou les saisir dans l'application. *Dépend de :* A-11, M-04.
- **M-07.** Notifications locales après le téléchargement de la nuit. Android demande une autorisation.
- **M-08.** Demande que le propriétaire confie son adresse de contact SEC à GitHub (secret du dépôt). *Décision.*
- **M-11.** Filtre d'intention Android sur les fichiers CSV et texte, puis le même écran de vérification.
- **M-14.** Demande du 15/11/2026 : intégrer à l'application tout l'outil du .bat, à commencer par le choix de la méthode d'évaluation (« 6 critères, Buffett, Munger etc. ») et un profil. Ajout de « Six critères » aux méthodes de `pf/portfolio.py`.
- **M-15.** Exporter les positions 13F des investisseurs suivis (`config/investisseurs.csv`), les titres les plus partagés et les transactions des élus (`config/elus.csv`). Les 13F demandent l'adresse de contact SEC : le propriétaire a accepté le 15/11/2026 de la confier à un secret GitHub (`SEC_CONTACT`), ce qui règle aussi M-08. Les élus se lisent sans contact.
- **M-16.** `pf/prix_juste.py`, `valuation.py`, `ventilation.py`, `historique.py`, `dirigeants.py` : exporter leurs résultats par valeur (fichier séparé, chargé à l'ouverture d'une fiche, pour garder l'export principal léger).
- **M-17.** Construction : reprendre `build_quant_portfolio` en Dart sur les notes de M-14. Backtest : publier les résultats précalculés de `backtest_pit.py` plutôt que de les recalculer sur l'appareil.
- **M-18.** Le portefeuille de l'application ne connaît que des poids cibles : saisir les opérations (ou des quantités) pour le suivi, l'apport du mois et la performance. Recoupe M-05 (risques) et M-04 (sauvegarde).
- **M-19.** Après la piste verte (M-10), cinq planches de pistes le 15/11/2026 (performance, anthracite et ocre, C de Climax, mélange « ascension » et « lame », C ocre sur fond blanc) ; le propriétaire a retenu « Exponentielle » sur fond anthracite. Charte `docs/MARQUE.md`, thème de l'application (ocre), toutes les icônes, écran de démarrage, installateur et QR code mis à jour.
- **M-12.** Le jeton est l'étape la plus difficile du premier lancement. Publier le fichier de données (aucune donnée personnelle) dans un dépôt public dédié la supprimerait ; à peser avec les conditions d'usage des sources. *Décision.*

### Phase 7 : travailler avec Claude depuis GitHub

| N° | Ticket | P | Taille |
|---|---|---|---|
| K-01 | Faire traiter un ticket par Claude depuis GitHub | P1 | M |
| K-02 | `CLAUDE.md` complété pour les agents (**fait le 14/11/2026**) | P1 | S |
| K-03 | Blocage automatique des fichiers protégés (**sans objet depuis G-05** : ces fichiers ne sont plus dans le dépôt) | P1 | S |
| K-04 | Tests des commandes Claude (**fait le 14/11/2026** : `tests/test_ligne_de_commande.py`) | P2 | M |
| K-05 | Versions et journal des changements | P2 | S |
| K-06 | Relecture automatique des demandes de fusion | P2 | S |
| K-07 | Revue de portefeuille planifiée | P3 | M |

- **K-01.** Installer l'action GitHub de Claude Code : une mention dans un ticket lance un agent qui ouvre une demande de fusion. Droits limités au dépôt, clé stockée en secret. *Dépend de :* G-03, Q-03, DEC-4.
- **K-02.** Ajouter à `CLAUDE.md` : le lien vers `docs/ARCHITECTURE.md` et vers cette feuille de route, la définition de « fini », et les erreurs déjà rencontrées (guillemets dans les scripts en ligne, fichiers verrouillés sous Windows, débit de Yahoo). *Dépend de :* Q-13.
- **K-03.** Une vérification fait échouer toute demande de fusion qui modifie un fichier protégé sans l'étiquette « accord du propriétaire ».
- **K-04.** Lancer `pf contexte`, `pf risques` et `pf idees` sur le jeu d'essai à chaque vérification. *Dépend de :* Q-04.
- **K-07.** Après chaque saison de résultats, un agent lance `/revue-portefeuille` et dépose le rapport dans un ticket.

## 5. Ordre conseillé

1. **Mettre sur GitHub :** G-01, G-02, G-03, D-09.
2. **Rendre le projet vérifiable ailleurs que sur le PC :** Q-04, Q-03, Q-01, Q-13, K-02, K-03, G-06, G-07.
3. **Donner la main aux agents :** K-01, puis Q-02, Q-05, Q-12.
4. **Fiabiliser les données :** D-03, D-01, D-02, D-05.
5. **Répondre à l'objectif du propriétaire :** C-01, C-10, A-01, A-09, A-11, S-06.
6. **Le reste par priorité**, phase par phase.

Les tickets de taille L sont à découper en sous-tickets avant d'être confiés à un agent.

## 6. Écarté pour l'instant

| Sujet | Raison |
|---|---|
| Application en `.exe` | Abandonné le 08/11/2026 : lancement par `lancer.bat` conservé |
| Tout le Nasdaq sans seuil de taille | Périmètre retenu le 11/11/2026 : Global Select d'au moins 1 Md$ |
| Historique allemand et suisse (D-11) | Pas de source gratuite structurée ; écarté le 08/11/2026 |
| Stockage du cache en base (D-10) | Aucun problème constaté à 133 Mo |
