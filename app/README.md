# G.A.R.P : application Android et installateur Windows

Sur Windows, `GARP-Setup` installe l'outil du PC lui-même (celui de `lancer.bat`, voir [portefeuille/README.md](../portefeuille/README.md)), avec son propre Python : rien d'autre à installer, et l'affichage est exactement celui de l'outil. Le reste de cette page décrit surtout l'application Android.

L'application affiche les données que GitHub calcule chaque nuit (screener, fiches, rangs), sans PC allumé. Votre portefeuille et votre watchlist restent sur l'appareil. Elle se met à jour depuis les Releases du dépôt, comme CloudStream.

```
Chaque nuit, GitHub (flux « Données de l'application ») : pf maj → pf export-app → release « donnees »
                                                                                      │
Téléphone (application) ── jeton en lecture seule ──▶ télécharge garp-donnees.json.gz
PC (outil installé)     ── sans jeton (public) ───▶ télécharge garp-outil.zip (pf export-outil)
Les deux proposent, sur demande, la dernière version « app-b<n> »
```

## Télécharger

Page de téléchargement : https://github.com/spuiksterr/GARP/releases/latest. Le dépôt est public : la page s'ouvre sans compte GitHub.

Le QR code de [assets/qr-telechargement.png](assets/qr-telechargement.png) ouvre cette page sur le téléphone.

| Appareil | Fichier |
|---|---|
| Android | `GARP-b<n>.apk` |
| Windows 11 | `GARP-Setup-b<n>.exe` (l'outil du PC complet, environ 150 Mo) |

## Installer

**Android (Xiaomi et autres)**
1. Sur la page de téléchargement, touchez le fichier `.apk`.
2. Ouvrez-le : Android demande d'autoriser l'installation depuis le navigateur ou le gestionnaire de fichiers. Sur un Xiaomi (HyperOS), acceptez l'avertissement.
3. Les versions suivantes s'installent depuis l'application : Réglages > Rechercher une mise à jour.

**Windows 11**
1. Lancez `GARP-Setup-b<n>.exe`. Il installe G.A.R.P pour votre compte seulement, sans droits d'administrateur, dans `%LOCALAPPDATA%\Programs\G.A.R.P`, avec un raccourci dans le menu Démarrer et, si vous le cochez, sur le Bureau.
2. L'installateur n'est pas signé : SmartScreen affiche « Windows a protégé votre ordinateur ». Choisissez « Informations complémentaires », puis « Exécuter quand même ».
3. Au premier lancement, les données de la nuit se téléchargent d'elles-mêmes (environ 55 Mo), sans jeton : le dépôt est public. Ensuite, à chaque ouverture, G.A.R.P s'affiche aussitôt avec les données déjà installées, cherche les nouvelles et les télécharge en arrière-plan ; la barre latérale propose alors « Charger les nouvelles données » (quelques secondes). Elles vont dans `%LOCALAPPDATA%\Climax\donnees`, avec votre portefeuille.
4. « Importer mon portefeuille » (espace « Construire ») reprend vos lignes depuis l'export du courtier, en CSV ou en classeur Excel (`.xlsx`, `.xlsm` ; un ancien `.xls` est à réenregistrer en `.xlsx`), ou depuis un tableau collé.
5. Mise à jour : quand une nouvelle version est publiée, la barre latérale propose « Installer la version n » ; l'installateur ferme G.A.R.P, remplace les fichiers et le rouvre.
6. Désinstallation : Paramètres > Applications > G.A.R.P. Les données et le portefeuille de `%LOCALAPPDATA%\Climax` restent en place.
7. La version installée remplace les mises à jour Yahoo et SEC de l'outil par les données de la nuit : elle ne calcule rien elle-même. Sur le PC de développement, `lancer.bat` et le raccourci du dossier `portefeuille/` gardent leur fonctionnement et leurs propres données.

## Créer le jeton GitHub (téléphone ; facultatif sur PC)

Sur PC, le jeton ne sert que si GitHub limite les requêtes sans jeton (60 par heure et par connexion) : « Jeton GitHub (facultatif) », en bas de la barre latérale.

1. Réglages de l'application (ou, sur PC, « Jeton GitHub (facultatif) ») > « Créer un jeton sur GitHub » (ou https://github.com/settings/personal-access-tokens/new).
2. **Token name** : `G.A.R.P téléphone` ; **Expiration** : 1 an.
3. **Repository access** : *Public repositories* (lecture seule des dépôts publics, dont `spuiksterr/GARP`).
4. *Generate token*, copiez-le (`github_pat_…`), collez-le dans l'application, puis « Enregistrer et télécharger les données ».

Le jeton ne permet que de lire les dépôts publics. Il est stocké chiffré sur l'appareil (sur PC, par Windows pour votre session : `%LOCALAPPDATA%\Climax\jeton.dat`) et n'est envoyé qu'à `api.github.com`.

## Premier lancement

L'application guide en trois écrans : ce que fait G.A.R.P, l'accès aux données (le bouton ouvre la page de création du jeton déjà remplie, il reste à choisir « Public repositories »), puis l'import du portefeuille. Réglages > « Revoir l'accueil » les rouvre.

## Importer votre portefeuille

Onglet Portefeuille, trois façons :
- **Fichier du courtier** : l'export CSV des positions (Boursorama, Degiro, Fortuneo, Saxo…). Plusieurs fichiers à la fois pour réunir PEA et compte-titres. Pour un classeur Excel, copiez le tableau puis « Coller ».
- **Coller un tableau** : copié depuis Excel ou la page « positions » du site du courtier.
- **Saisir mes lignes** : une ligne par valeur, par exemple `Alphabet 20` ou `NUKL.DE;5`.

G.A.R.P devine le séparateur et la ligne d'en-tête. Il reconnaît chaque ligne par son ISIN, son ticker ou son nom, et calcule les poids : d'abord le poids donné, sinon le montant (en euros de préférence), sinon la quantité multipliée par le dernier cours en euros. Les lignes « liquidités » et « total » sont écartées.

L'écran de vérification montre chaque ligne : reconnue, à vérifier, ou hors des données (fonds, or, valeur non suivie, gardée avec son poids). Touchez une ligne pour la corriger : le choix est retenu pour les prochains imports.

Ensuite :
- le bouton « + » ajoute une valeur ;
- toucher un poids le modifie ;
- glisser une ligne vers la gauche la retire ;
- le menu « Copier le portefeuille » le transporte vers un autre appareil (puis « Coller » là-bas).

## Mon profil et les méthodes d'évaluation

Réglages > **Mon profil investisseur** :
- **ma méthode d'évaluation** : score composite, quatre regards, Buffett, Munger, Fisher, Terry Smith, qualité d'abord, croissance, valeur, momentum ou six critères. Elle classe le screener et l'accueil (« En tête selon… ») ;
- **où j'investis** : PEA, CTO ou les deux, le filtre de départ du screener ;
- **mes limites de concentration** : une ligne, les trois premières, un secteur. Les alertes de l'accueil et de la page Portefeuille les suivent.

Chaque note est le rang centile de la valeur dans l'univers selon la méthode (90 : mieux placée que 90 % des valeurs), calculé comme sur le PC. Le bouton de méthode du screener en essaie une autre sans changer le profil. La fiche d'une valeur donne sa note selon chaque méthode, ses quatre regards et le détail des six critères. La page « Méthodes d'évaluation » les explique et liste les valeurs retenues par au moins quatre méthodes.

## Différences avec l'application du PC

L'application, toujours en thème sombre, reprend l'interface de l'outil du PC (`G.A.R.P` ou `lancer.bat`) : même barre latérale à gauche (dans un tiroir, bouton ☰, sur un téléphone), mêmes rubriques dans le même ordre, mêmes couleurs, même police, mêmes cartes de chiffres et tableaux. La barre latérale permet aussi de rechercher une valeur et de télécharger les données de la nuit.

- **Investir** :
  - **Tableau de bord** : chiffres de votre portefeuille, profil (TRI implicite, croissance, PER, volatilité) et courbe face à l'indice sur un an, points de vigilance (prix visé atteint, condition de vente atteinte, forte variation, concentration), dernières actualités, lignes du portefeuille ;
  - **Actualités** : signaux et presse ;
  - **Composition** : poids cibles en tableau, répartition par secteur, devise, compte et pays, import du fichier du courtier ;
  - **Apport du mois** : ordres sans rien vendre ;
  - **Mon portefeuille** : titres détenus, prix de revient, plus-values, poids réels et poids cibles ;
  - **Risques** : concentration, corrélations, pertes passées, chocs, simulation d'un changement.
- **Analyser** :
  - **Pour moi** : la bonne action au bon prix. Les valeurs qui conviennent à votre profil (méthode, critères de qualité, moat, taille, secteurs écartés, enveloppe), avec leur prix juste (le cours auquel elles rapportent votre rendement exigé) et votre prix d'achat (marge de sécurité déduite) : au bon prix, prix correct, à attendre ;
  - **Screener**, **Watchlist** (prix visés et écart au cours), **Fiche valeur**, **Quatre regards** ;
  - **Grands investisseurs** : titres les plus partagés, portefeuilles 13F, mouvements du trimestre, transactions des élus américains ;
  - **Construction de portefeuille** : un portefeuille bâti par des règles, comparé à l'indice, que l'on peut adopter ;
  - **Backtest** : votre portefeuille face à l'indice.
- **Comprendre** : méthode et routine, méthodes d'évaluation.
- **Mon compte** : profil, réglages.

La fiche d'une valeur a six onglets : résumé (scores, indicateurs, « pour moi »), prix juste (au multiple choisi, avec ses repères historiques, ou au rendement exigé), activité (dirigeants, ventilation du chiffre d'affaires, grands investisseurs, description), historique financier, valorisation (value drivers, sensibilité, scénarios à 5 ans), notes (thèse, prix visé, conditions de vente).

Restent sur le PC seulement : la mise à jour à la demande, les analyses avec Claude (`/analyse-valeur`…) et le journal des opérations. Les risques et le backtest de l'application travaillent sur des cours hebdomadaires : leurs chiffres sont proches de ceux du PC, pas identiques. Thèses, prix visés, scénarios et règles restent sur l'appareil où vous les saisissez. Les valeurs américaines y ont 10 ans d'historique (comptes SEC) ; sur GitHub, 4 ans, faute d'adresse de contact SEC.

## Développement

L'installateur Windows est décrit par `windows/installateur/garp.iss` (Inno Setup), et son contenu assemblé par `windows/installateur/preparer_outil.ps1` : Python 3.12 du serveur de construction, les bibliothèques de `portefeuille/requirements.txt` (sans pytest), le code de l'outil et `autonome.json` (numéro de version). Le script vérifie que le serveur de l'outil démarre. Son identifiant `AppId` ne doit jamais changer, sinon les mises à jour s'installeraient à côté ; il a remplacé sans réinstallation l'ancienne version Flutter pour Windows. Le code Flutter garde la cible Windows, qui n'est plus publiée. Code Flutter dans `lib/` (import du portefeuille : `lib/import_portefeuille.dart`, sans réseau ; méthodes d'évaluation : `lib/methodes.dart`, même calcul que `pf/portfolio.py` `note_construction`), tests dans `test/`. Le logo et les icônes viennent de `portefeuille/assets/composer_icones.py` (voir `portefeuille/docs/MARQUE.md`). Pas besoin d'outils sur le PC : le flux « Application » (`.github/workflows/app.yml`) analyse, teste, construit l'APK signé et l'installateur Windows, et publie une release à chaque envoi sur `main`. Le dépôt privé n'a que 2 000 minutes de calcul par mois (Windows compte double) : hors de `main`, les installateurs se construisent à la demande (`gh workflow run app.yml --ref <branche> -f plateformes=windows`), les tests des demandes de fusion tournent sous Linux seulement, et les données de la nuit ne passent que sur `main` (mise à jour complète chaque semaine, rapide les autres nuits). La clé de signature Android est dans `portefeuille/profil/` (hors Git) et dans les secrets du dépôt `ANDROID_CLE_B64` et `ANDROID_CLE_MOT_DE_PASSE`.
