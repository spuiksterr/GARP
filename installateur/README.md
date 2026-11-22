# G.A.R.P : installateur Windows

`GARP-Setup` installe l'outil du PC lui-même (celui de `lancer.bat`, voir [portefeuille/README.md](../portefeuille/README.md)), avec son propre Python : rien d'autre à installer, et l'affichage est exactement celui de l'outil.

```
Chaque nuit, GitHub (flux « Données de l'application ») : pf maj → pf export-outil → release « donnees »
                                                                                         │
PC (outil installé) ── sans jeton (dépôt public) ──▶ télécharge garp-outil.zip ◀────────┘
Nouvelle version : release « app-b<n> », proposée dans la barre latérale
```

## Télécharger

Page de téléchargement : https://github.com/spuiksterr/GARP/releases/latest. Le dépôt est public : la page s'ouvre sans compte GitHub. Le fichier `GARP-Setup-b<n>.exe` (environ 150 Mo) est tout en bas, sous « Assets ».

## Installer (Windows 11)

1. Lancez `GARP-Setup-b<n>.exe`. Il installe G.A.R.P pour votre compte seulement, sans droits d'administrateur, dans `%LOCALAPPDATA%\Programs\G.A.R.P`, avec un raccourci dans le menu Démarrer et, si vous le cochez, sur le Bureau. Une installation existante garde son dossier.
2. L'installateur n'est pas signé : SmartScreen affiche « Windows a protégé votre ordinateur ». Choisissez « Informations complémentaires », puis « Exécuter quand même ».
3. Au premier lancement, les données de la nuit se téléchargent d'elles-mêmes (environ 55 Mo), sans jeton. Ensuite, à chaque ouverture, G.A.R.P s'affiche aussitôt avec les données déjà installées, cherche les nouvelles et les télécharge en arrière-plan ; la barre latérale propose alors « Charger les nouvelles données » (quelques secondes). Elles vont dans `%LOCALAPPDATA%\Climax\donnees`, avec votre portefeuille.
4. « Importer mon portefeuille » reprend vos lignes depuis l'export du courtier, en CSV ou en classeur Excel (`.xlsx`, `.xlsm` ; un ancien `.xls` est à réenregistrer en `.xlsx`), ou depuis un tableau collé.
5. Mise à jour : quand une nouvelle version est publiée, la barre latérale propose « Installer la version n » ; l'installateur ferme G.A.R.P, remplace les fichiers et le rouvre.
6. Désinstallation : Paramètres > Applications > G.A.R.P. Les données et le portefeuille de `%LOCALAPPDATA%\Climax` restent en place.
7. La version installée remplace les mises à jour Yahoo et SEC de l'outil par les données de la nuit : elle ne calcule rien elle-même. Sur le PC de développement, `lancer.bat` et le dossier `portefeuille/` gardent leur fonctionnement et leurs propres données.

Un jeton GitHub n'est utile que si GitHub limite les requêtes sans jeton (60 par heure et par connexion) : « Jeton GitHub (facultatif) », en bas de la barre latérale, ouvre la page de création d'un jeton à grain fin (*Public repositories*, lecture seule). Il est chiffré par Windows pour votre session (`%LOCALAPPDATA%\Climax\jeton.dat`) et n'est envoyé qu'à `api.github.com`.

## Construction

- `garp.iss` décrit l'installateur (Inno Setup) ; `preparer_outil.ps1` en assemble le contenu : Python 3.12 du serveur de construction, les bibliothèques de `portefeuille/requirements.txt` (sans pytest), le code de l'outil, la méthode (`docs/METHODE.md`) et `autonome.json` (numéro de version). Le script vérifie ensuite que le serveur de l'outil démarre et répond.
- L'identifiant `AppId` de `garp.iss` ne doit jamais changer : sinon, les mises à jour s'installeraient à côté de l'ancienne version.
- Les images de l'assistant (`*.bmp`) viennent de `portefeuille/assets/composer_icones.py` (voir `portefeuille/docs/MARQUE.md`) ; ne pas les retoucher à la main.
- Pas besoin d'outils sur le PC : le flux « Installateur Windows » (`.github/workflows/app.yml`) construit l'installateur et publie une release `app-b<n>` à chaque envoi sur `main` qui touche l'outil. Pour essayer une branche avant fusion : `gh workflow run app.yml --ref <branche>` (installateur en artefact, sans release).
