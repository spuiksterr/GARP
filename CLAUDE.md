# Espace « Claude investissement »

## Contenu

- `portefeuille/` : outils de stock-picking long terme (package Python `pf`, interface Streamlit), portefeuille réel de l'utilisateur (`profil/portefeuille_modele.csv` = ses lignes et poids cibles, repris de son courtier le 2026-10-29 ; la sélection Claude d'origine est archivée dans `profil/selection_claude_2026-10.csv`). Point d'entrée `portefeuille/README.md`, méthode `portefeuille/docs/METHODE.md`.
- `ai-berkshire-main/` : framework open source de recherche value (en chinois) dont la méthode s'inspire (quatre regards, filtres anti-médiocrité, règles de vente). Référence en lecture seule, ne pas modifier.

- `portefeuille/profil/` : fichiers personnels (portefeuille, watchlist, surveillance, règles de vente, scénarios, `prive.json`), exclus de Git ; copie datée par `pf sauvegarde` dans le dossier choisi par l'utilisateur (`dossier_sauvegarde` de `prive.json`). `portefeuille/profil.exemple/` : données fictives versionnées, copiées dans `profil/` sur une installation neuve. Variable `PF_PROFIL` pour un autre emplacement (tests).

## Conventions

- Répondre et rédiger en français.
- Python : toujours l'environnement du projet, lancé depuis `portefeuille/` : `.venv/Scripts/python.exe -m pf <commande>` (`--help` pour la liste).
- Avant une analyse : `date`, puis `-m pf maj` si les données ont plus d'un jour.
- Chiffres clés recoupés avec au moins deux sources ; faits et opinions séparés ; devise toujours précisée.
- CSV de `portefeuille/config` et `portefeuille/data` : séparateur `;`, UTF-8, jamais de `;` dans un texte.
- `portefeuille_modele.csv`, `selection_claude_2026-10.csv`, `surveillance.csv` et `transactions.csv` ne se modifient qu'avec l'accord explicite de l'utilisateur. Les fiches `theses/*.md` peuvent être enrichies (journal daté).
- Pas de conseil personnalisé : rappeler les limites dès qu'une décision d'achat ou de vente est en jeu.
- Univers : `config/univers.csv` couvre S&P 500, STOXX 600 et Nasdaq Global Select d'au moins 1 Md$ (environ 1 760 valeurs ; `-m pf indices` pour les nouveaux entrants, puis `-m pf maj`). Un rang élevé n'est pas une recommandation : seule une analyse qualitative (`/analyse-valeur`) peut étayer un achat.
- Après une modification du code de `pf/` : `.venv/Scripts/python.exe -m pytest tests -q`. Après une modification de `vues/` ou de `pf/ui.py`, aussi les tests d'affichage : `.venv/Scripts/python.exe -m pytest tests -q -m pages` (une minute environ). Les tests tournent sur le jeu d'essai `tests/jeu_essai/` (16 valeurs figées, réseau coupé), jamais sur les données du poste sauf avec `PF_TESTS_REELS=1`. Un nouveau test qui a besoin de données s'appuie sur ce jeu ; le reconstruire (`tests/construire_jeu_essai.py`) seulement si le format des données change. `PF_DOSSIER` déplace `config/`, `data/`, `theses/`, `rapports/` et `profil/`.
- Style : `.venv/Scripts/python.exe -m ruff check` depuis `portefeuille/` (réglages dans `pyproject.toml`, vérifié par GitHub). Lignes de 120 caractères au plus pour le nouveau code. Après `ruff check --fix`, relancer aussi les tests d'affichage : le tri des imports a déjà supprimé un alias réexporté (`ui.num`).
- Le projet est sous Git (dépôt à la racine, branche `main`, dépôt privé `https://github.com/spuiksterr/Climax`) : un commit par changement cohérent, données personnelles exclues (`.gitignore`). Auteur des commits : `spuiksterr` avec l'adresse anonyme GitHub, jamais l'adresse Gmail.

## Commandes Claude

`/analyse-valeur`, `/revue-portefeuille`, `/apport-mensuel`, `/nouvelles-idees` (dossier `.claude/skills/`).

## Travailler sur un ticket

- Lire d'abord `portefeuille/docs/ARCHITECTURE.md` (trajet des données, rôle des modules, recettes), puis le ticket dans `FEUILLE_DE_ROUTE.md` ou sur GitHub (`[X-00]` dans le titre).
- Un ticket = une branche = une demande de fusion, avec le gabarit `.github/pull_request_template.md`. Le propriétaire relit et fusionne lui-même chaque demande (DEC-4) : un agent ne fusionne jamais.
- **Fini** veut dire : le critère « Fini quand » du ticket est vérifié ; les tests de calcul passent, et ceux d'affichage si `vues/` ou `pf/ui.py` a changé ; `README.md`, `docs/METHODE.md` ou `docs/ARCHITECTURE.md` suivent le changement ; le ticket est marqué fait dans la feuille de route ; les vérifications GitHub sont vertes.
- Une décision (`DEC-x`, étiquette « décision ») revient au propriétaire : la poser, ne pas la trancher.

## Erreurs déjà rencontrées

- Code Python dans un heredoc ou un `python -c` : les guillemets et `\b` cassent. Écrire le script dans un fichier.
- `sed` sur du code multiligne : a abîmé un script. Faire les remplacements en Python, avec vérification du nombre d'occurrences.
- Fins de ligne : le dépôt mêle LF et CRLF. `Path.write_text` sous Windows écrit du CRLF : utiliser `newline=""` ou les octets, et contrôler `git diff --cached --shortstat` avant de committer.
- Windows verrouille parfois un fichier pendant `os.replace` (`PermissionError`) : passer par `config.ecriture_atomique`.
- Yahoo limite le débit (fiches refusées, réponses vides) : ne pas augmenter le parallélisme ; `api.nasdaq.com` répond 403, utiliser l'annuaire nasdaqtrader.com.
- Un processus Streamlit ou de mise à jour déjà lancé garde l'ancien code importé : le relancer après une modification de `pf/`.
- Lire l'identifiant GitHub enregistré dans Windows est refusé par le contrôle de sécurité : passer par `gh`, connecté par le propriétaire.
