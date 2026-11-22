# Profil d'exemple

Données **fictives**, copiées dans `portefeuille/profil/` au premier lancement d'une installation neuve. Elles permettent de démarrer l'application et de lancer les tests sans données personnelles.

Le vrai profil (`portefeuille/profil/`) reste sur le poste : il est exclu du dépôt. Pour en utiliser un autre, définir la variable d'environnement `PF_PROFIL` avec son chemin.

| Fichier | Contenu |
|---|---|
| `portefeuille_modele.csv` | Lignes du portefeuille et poids cibles (en %), thèse, risque, condition de vente |
| `selection_claude_2026-10.csv` | Sélection de 25 valeurs proposée par Claude le 29/10/2026 (archive comparée dans le backtest) |
| `surveillance.csv` | Valeurs écartées pour l'instant et leur condition d'entrée |
| `regles_vente.csv` | Conditions de vente chiffrées (indicateur, comparaison, seuil) |
| `watchlist.csv` | Valeurs suivies, date et cours d'ajout, prix visé |
| `actualites.csv` | Recherches de presse propres à une valeur |
| `scenarios.csv` | Créé à la première sauvegarde d'un scénario depuis la fiche valeur |
| `prive.json` | Facultatif, absent de l'exemple : `{"contact_sec": "Nom adresse@exemple.fr"}`, exigé par la SEC pour lire ses données |

Séparateur `;`, UTF-8, jamais de `;` dans un texte.
