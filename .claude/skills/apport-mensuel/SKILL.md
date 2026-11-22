---
name: apport-mensuel
description: Prépare l'investissement mensuel du portefeuille long terme. Calcule les ordres qui rapprochent le portefeuille de ses cibles sans rien vendre, écarte les lignes en alerte, puis aide à enregistrer les ordres exécutés. À utiliser quand l'utilisateur veut investir une somme.
argument-hint: <montant en euros> [PEA|CTO]
---

# Apport du mois : $ARGUMENTS

1. Lire le montant (obligatoire) et le compte (par défaut, celui qui porte le plus de poids cible). Si l'utilisateur dispose des deux comptes, rappeler que le PEA se remplit en priorité tant que le plafond de 150 000 € de versements n'est pas atteint.
2. Depuis `portefeuille/` : `.venv/Scripts/python.exe -m pf maj`, puis `.venv/Scripts/python.exe -m pf apport <montant> [--compte PEA|CTO]`. La commande écarte d'elle-même les lignes sorties des filtres ou en forte baisse et le signale (`--toutes-lignes` pour les garder). Ajouter `--fractions` si le courtier accepte les fractions d'action, `--max-ordres N` si l'utilisateur veut limiter les frais.
3. Contrôler chaque ordre proposé avec `-m pf fiche <TICKER>` et `-m pf contexte <TICKER> --hors-ligne` : alertes, critères, thèse, conditions de vente chiffrées (une règle « Atteinte » suspend le renforcement jusqu'à la revue), scénarios, actualités et prochains résultats (renforcer la veille d'une publication est un pari). Vérifier aussi avec `-m pf risques` que l'apport ne renforce pas une concentration déjà forte (plus grosse ligne, part en dollar). Pour une ligne écartée par la commande, rappeler qu'elle attend sa revue (`/revue-portefeuille`) ; si l'utilisateur préfère la renforcer quand même, relancer avec `--toutes-lignes`.
4. Présenter un tableau clair (valeur, quantité, cours indicatif, montant) et conseiller des ordres à cours limité proches du dernier cours.
5. Une fois les ordres exécutés, proposer de les enregistrer dans `portefeuille/data/transactions.csv` (en-tête `date;compte;type;ticker;quantite;prix_unitaire;devise;frais_eur;montant_eur;taux_change;note`, montant réellement débité si connu). Ne rien écrire sans les prix réels ou l'accord de l'utilisateur ; l'interface (page « Apport du mois ») le fait aussi en un clic.
