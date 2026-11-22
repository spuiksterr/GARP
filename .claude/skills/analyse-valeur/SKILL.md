---
name: analyse-valeur
description: Analyse approfondie d'une action pour le portefeuille long terme (chiffres de l'outil, recherche récente, quatre regards d'investisseurs), verdict tranché et fiche de thèse. À utiliser quand l'utilisateur veut étudier, acheter, renforcer ou juger une valeur précise.
argument-hint: <ticker Yahoo ou nom de société>
---

# Analyse d'une valeur : $ARGUMENTS

But : décider si $ARGUMENTS mérite une place dans le portefeuille long terme, et à quelles conditions. Un verdict tranché, pas un « d'un côté, de l'autre ».

## 0. Préparer

- Lancer `date` : c'est la référence pour « dernier cours » et « derniers résultats ».
- Trouver le ticker Yahoo (`ASML.AS`, `SAF.PA`, `MSFT`…). S'il manque dans `portefeuille/config/univers.csv`, proposer la ligne `ticker;nom;pays;enveloppe;secteur;profil` (enveloppe PEA seulement si siège dans l'UE ou l'EEE et cotation européenne ; secteur parmi ceux de `pf/config.py`), l'ajouter après accord, puis lancer la mise à jour.

## 1. Les chiffres de l'outil

Depuis `portefeuille/` : `.venv/Scripts/python.exe -m pf fiche <TICKER>` (Git Bash) ou `& .\.venv\Scripts\python.exe -m pf fiche <TICKER>` (PowerShell). Si les données ont plus d'un jour : `-m pf maj` d'abord.

Relever : statut des filtres et motifs, note GARP et ses trois piliers, ROIC, marges, conversion en cash, dette, dilution, croissance historique et consensus, PER prospectif, croissance implicite, TRI implicite, momentum, alertes.

Puis `-m pf contexte <TICKER>` (tout ce que l'outil sait d'autre) :

- **Historique** : nombre d'exercices et source (Yahoo seul, prolongé par la SEC ou par les rapports européens ESEF). Avec 4 exercices seulement, les croissances ne couvrent que 3 ans : le dire.
- **Multiples** : actuel contre médianes sur 5 et 10 ans (P/FCF, P/FCF hors SBC, PER, P/CA). Une forte décote peut traduire une dégradation : chercher laquelle.
- **Dirigeants** (sociétés américaines) : des achats en bourse, surtout groupés, sont un indice ; des ventes programmées ne disent presque rien.
- **Grands investisseurs** (déclarations 13F) et **élus américains** : qui détient, qui a bougé ce trimestre. Une information parmi d'autres, avec 45 jours de retard, jamais une raison d'acheter.
- **Actualités** : point de départ de la recherche web, à vérifier dans les sources primaires.
- Prix visé, scénarios et conditions de vente déjà enregistrés, le cas échéant.

## 2. Vérifier et compléter

Rechercher sur le web : derniers résultats et perspectives, faits marquants des 12 derniers mois (réglementation, concurrence, dirigeants, acquisitions), position concurrentielle.

- Recouper les trois chiffres qui portent la thèse (croissance, marge, valorisation) avec au moins deux sources, la publication de l'entreprise d'abord. Signaler tout écart de plus de 5 % avec les données Yahoo.
- Séparer faits sourcés et opinions. Écrire « données insuffisantes » plutôt que combler par des suppositions.
- Pour un calcul exact (capitalisation, multiples, scénarios), `ai-berkshire-main/tools/financial_rigor.py` fonctionne sans dépendance.

## 3. Quatre regards (chacun conclut par une note sur 5)

| Regard | Question |
|---|---|
| Buffett : l'entreprise et le prix | Comprend-on comment elle gagne de l'argent ? L'avantage est-il durable ? Le prix laisse-t-il une marge (TRI implicite contre 9 %) ? |
| Munger : l'inversion | Comment perdrait-elle la moitié de sa valeur en 5 ans ? Trois à cinq scénarios avec probabilité. Pourquoi des investisseurs avisés vendent-ils ? |
| Fisher : croissance et dirigeants | Reste-t-il 10 ans de croissance ? Le capital est-il bien alloué (R&D, rachats, acquisitions) ? Les dirigeants sont-ils francs quand tout va mal ? |
| Terry Smith : la qualité | Rentabilité du capital élevée et durable ? Croissance autofinancée ? Prix raisonnable pour cette qualité (rendement du flux de trésorerie) ? |

Mettre en avant les désaccords entre regards : c'est là que se trouve l'information. Le framework détaillé à quatre perspectives se trouve dans `ai-berkshire-main/skills/investment-team.md` (en chinois).

## 4. Verdict, un seul

- **Achat, poche cœur** (poids 4 à 6,5 %) : premier ordre, durable, prix raisonnable.
- **Achat, poche opportunités** (2,5 à 3,5 %) : qualité décotée ou thèse contrarienne avec un catalyseur identifiable.
- **Surveillance** : bonne entreprise, mauvais moment ; condition d'entrée chiffrée. La traduire en prix visé : le cours auquel l'action se paierait au multiple jugé raisonnable (section « Prix juste » de la fiche : prix cible = cours × multiple cible / multiple actuel). Proposer de l'enregistrer dans la watchlist ; après accord : `.venv/Scripts/python.exe -c "from pf import watchlist as wl; wl.fixer_cible('<TICKER>', <prix>, '<ratio> <cible>')"`. La watchlist et le tableau de bord signaleront le moment où le cours passe dessous.
- **Rejet** : la raison principale en une phrase.

Test du miroir : la thèse doit tenir en cinq phrases. Sinon, rejet.

## 5. Fiche de thèse

Créer ou mettre à jour `portefeuille/theses/<TICKER>.md` en conservant le journal existant : Thèse, Ce qui pourrait la casser, Conditions de vente (au moins une condition factuelle et mesurable, plus la règle des trois raisons), Indicateurs du jour, Journal de suivi (ligne datée avec le verdict et les sources).

Deux compléments, à proposer puis à écrire seulement après accord :

- **Scénarios à 5 ans** (pessimiste, central, optimiste) : croissance annuelle du chiffre d'affaires, marge (de FCF, ou nette pour une financière) et multiple de sortie, avec le prix et le rendement annuel qui en découlent. L'utilisateur peut les enregistrer depuis la fiche (section Valorisation), ou : `.venv/Scripts/python.exe -c "from pf import scenarios as s; from pf.scoring import build_screener; sc = build_screener(); s.enregistrer('<TICKER>', sc.loc['<TICKER>'], {'Pessimiste': {'croissance': 0.04, 'marge': 0.20, 'multiple': 15}, 'Central': {...}, 'Optimiste': {...}})"`. Un multiple central au-dessus du multiple actuel suppose une revalorisation : le justifier.
- **Conditions de vente chiffrées** : traduire chaque condition mesurable en règle (indicateurs disponibles dans `pf/regles.py` : CA des 12 derniers mois contre le dernier exercice, rentabilité, marges, dette nette / EBITDA, dilution, critères, multiples…). Ligne de `portefeuille/profil/regles_vente.csv` : `ticker;indicateur;operateur;seuil;note` (seuil en % pour un pourcentage, « -5 » pour -5 %). Elles sont vérifiées à chaque mise à jour et remontent au tableau de bord. Une condition sur un segment d'activité ou un événement (procès, départ d'un dirigeant) ne se chiffre pas : la laisser en texte.

## 6. Proposer sans imposer

Si le verdict modifie le portefeuille modèle (ajout, retrait, poids), proposer la ligne exacte pour `portefeuille/profil/portefeuille_modele.csv` (séparateur `;`, aucun `;` dans les textes, poids rééquilibrés pour que le total reste 100) et ne l'écrire qu'après accord. Pour une surveillance, proposer la ligne de `profil/surveillance.csv`.

Restitution en français, directe, chiffres sourcés et devise précisée. Terminer par une ligne rappelant qu'il ne s'agit pas d'un conseil personnalisé.
