---
name: revue-portefeuille
description: Revue trimestrielle du portefeuille long terme. Met à jour les données, confronte chaque thèse aux faits récents, classe les lignes (intacte, à réexaminer, invalidée) et propose des actions disciplinées. À utiliser après les publications de résultats ou quand l'utilisateur demande un point sur son portefeuille.
argument-hint: "[facultatif : tickers à cibler]"
---

# Revue du portefeuille $ARGUMENTS

## 1. Données

Lancer `date`, puis depuis `portefeuille/` :

- `.venv/Scripts/python.exe -m pf maj`
- `.venv/Scripts/python.exe -m pf modele`
- `.venv/Scripts/python.exe -m pf suivi` (si des opérations ont été saisies)
- `.venv/Scripts/python.exe -m pf risques` : concentration, devises, corrélations, scénarios de choc (marché -30 %, dollar -10 %, or -20 %)

## 2. Ligne par ligne

Pour chaque ligne du portefeuille modèle (ou seulement $ARGUMENTS si précisé) :

1. Lire `theses/<TICKER>.md` : thèse, condition de vente, journal.
2. Lancer `-m pf contexte <TICKER>` : conditions de vente chiffrées (« Atteinte » = à examiner en priorité), scénarios à 5 ans enregistrés (cours au-dessus de l'optimiste ou sous le pessimiste ?), achats ou ventes des dirigeants, mouvements des grands investisseurs, actualités récentes et date des prochains résultats.
3. Rechercher les faits du dernier trimestre : résultats, perspectives, événements, en partant des actualités relevées et en remontant aux sources primaires.
4. Confronter les faits à la condition de vente et classer :
   - **Intacte** : rien ne contredit la thèse.
   - **À réexaminer** : un signal à comprendre (trimestre décevant, départ d'un dirigeant, sortie des filtres, forte baisse inexpliquée). Préciser ce qu'il faut surveiller et à quelle échéance.
   - **Invalidée** : un fait établi casse la thèse. Proposer la sortie, progressive en cas de doute.
5. Ajouter au journal de la fiche une ligne datée, factuelle et sourcée (`- AAAA-MM-JJ : …`). Si une condition de vente mesurable n'a pas encore de règle chiffrée, la proposer pour `profil/regles_vente.csv` (voir /analyse-valeur).

## 3. Vue d'ensemble

- Poids : lignes à plus de 2 fois leur cible, secteurs au-delà de 30 %.
- Risques (`-m pf risques`) : poids de la plus grosse ligne, nombre effectif de lignes, part en dollar, effet des scénarios de choc. Signaler une concentration qui dépasse ce que la thèse justifie.
- Performance du modèle depuis sa création et du portefeuille réel contre l'ETF MSCI World (TWR et écart en euros, commande `suivi`).
- Liste de surveillance (`profil/surveillance.csv`) et watchlist (prix visés) : une condition d'entrée est-elle remplie ?

## 4. Rapport

Écrire `portefeuille/rapports/revue-AAAA-MM-JJ.md` : synthèse en cinq lignes, tableau (ligne, statut, fait clé, action), actions proposées, points à surveiller au prochain trimestre.

## Discipline

Trois raisons de vendre seulement : erreur sur l'entreprise, thèse invalidée par les faits, opportunité nettement meilleure (rendement attendu supérieur d'au moins 5 points à risque comparable). Ni la baisse du cours ni le prix de revient ne justifient une vente. Rééquilibrer par les apports d'abord ; s'il faut vendre, le faire dans le PEA plutôt que sur le compte-titres.

Aucune modification de `portefeuille_modele.csv`, `surveillance.csv` ou `transactions.csv` sans l'accord de l'utilisateur.
