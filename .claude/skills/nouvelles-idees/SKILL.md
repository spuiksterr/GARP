---
name: nouvelles-idees
description: Cherche de nouveaux candidats pour le portefeuille long terme. Part des meilleures notes GARP du screener hors portefeuille (ou d'un thème), applique des contrôles rapides et propose des ajouts à l'univers ou à la liste de surveillance. À utiliser chaque semestre ou quand l'utilisateur cherche des idées.
argument-hint: "[facultatif : thème, secteur ou pays]"
---

# Nouvelles idées $ARGUMENTS

1. Lancer `date`, puis depuis `portefeuille/` : `.venv/Scripts/python.exe -m pf maj`, `.venv/Scripts/python.exe -m pf screener --top 40` (ajouter `--enveloppe PEA` si l'objectif est d'alimenter le PEA) et `.venv/Scripts/python.exe -m pf idees`. Cette dernière liste les meilleures notes GARP qui passent les garde-fous de qualité, ainsi que les titres détenus par plusieurs grands investisseurs suivis. Les quatre regards et les six critères servent de repères pour départager.
2. Écarter les valeurs déjà présentes dans `profil/portefeuille_modele.csv` et `profil/surveillance.csv`. Si un thème est demandé ($ARGUMENTS), filtrer. Si le thème dépasse l'univers, rechercher 10 à 15 sociétés cotées pertinentes, proposer leurs lignes pour `config/univers.csv`, les ajouter après accord et relancer `maj`.
3. Pour les cinq meilleurs candidats, lancer `-m pf contexte <TICKER>`, puis un contrôle rapide en six portes (une ligne chacune) : modèle économique compréhensible, avantage durable, dirigeants fiables (achats ou ventes en bourse), bilan solide, croissance possible sur 10 ans (attention aux historiques de 4 exercices seulement), prix raisonnable (TRI implicite d'au moins 9 %, multiple par rapport à sa médiane).
4. Comparer chaque candidat à la ligne la plus faible de la même poche du portefeuille modèle : un remplacement ne se justifie que si le rendement attendu dépasse d'au moins 5 points, à risque comparable.
5. Restituer : tableau des candidats (note GARP, regards et critères comme repères, TRI implicite, verdict rapide), une à trois valeurs à approfondir avec `/analyse-valeur`, lignes proposées pour `surveillance.csv` ou prix visés pour la watchlist. N'écrire dans les fichiers qu'après accord.
