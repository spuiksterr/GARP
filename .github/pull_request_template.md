## Ticket

Ticket de la feuille de route : <!-- ex. Q-04, et le lien du ticket GitHub s'il existe -->

## Ce qui change

<!-- En quelques phrases, en français : pourquoi, quoi, et ce que l'utilisateur verra de différent. -->

## Vérifications (depuis `portefeuille/`)

- [ ] `.venv/Scripts/python.exe -m pytest tests -q` passe (obligatoire si `pf/` est modifié)
- [ ] `.venv/Scripts/python.exe -m pytest tests -q -m pages` passe (obligatoire si `vues/` ou `pf/ui.py` est modifié)
- [ ] `README.md` et `docs/METHODE.md` à jour si le comportement change
- [ ] Ticket coché dans `FEUILLE_DE_ROUTE.md`

## Garde-fous

- [ ] Aucun fichier protégé modifié sans accord écrit du propriétaire : `portefeuille_modele.csv`, `selection_claude_2026-10.csv`, `surveillance.csv`, `transactions.csv`
- [ ] Rien dans `ai-berkshire-main/`
- [ ] Aucune donnée personnelle (adresse, montants, thèses, `profil/prive.json`, `data/`)
- [ ] CSV : séparateur `;`, UTF-8, aucun `;` dans un texte
- [ ] Textes visibles et message de commit en français
