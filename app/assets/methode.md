# Méthode et routine

**En une phrase :** acheter des entreprises exceptionnelles à un prix raisonnable, les garder longtemps, et ne vendre que si les faits cassent la raison de l'achat.

La performance à long terme d'une action suit celle de l'entreprise : sur dix ans, l'essentiel du rendement vient de la croissance des bénéfices par action et du cash rendu aux actionnaires, pas de la variation du multiple payé. D'où trois questions, dans cet ordre : **l'entreprise est-elle de premier ordre ? Va-t-elle croître ? Le prix laisse-t-il une marge ?** Le momentum sert de garde-fou contre les pièges de valeur.

---

## 1. L'univers

Environ 1 760 entreprises : le S&P 500, le STOXX Europe 600 (composition reprise des ETF iShares qui répliquent ces indices), les actions du segment principal du Nasdaq (Global Select) d'au moins 1 milliard de dollars de capitalisation (annuaire officiel du Nasdaq, taille et type de titre vérifiés auprès de Yahoo ; ni bons de souscription, ni actions de préférence, ni coquilles de rachat) et une sélection de valeurs de qualité hors indices. Ce n'est donc plus une liste présélectionnée pour sa qualité : ce sont les filtres qui font le tri. La liste vit dans `config/univers.csv` : ajoutez une ligne (ticker Yahoo, nom, pays, enveloppe, secteur, profil) puis lancez une mise à jour, ou `python -m pf indices` chaque trimestre pour intégrer les nouveaux entrants. L'import ajoute des valeurs, il n'en retire jamais.

Deux limites découlent de cet élargissement. Les foncières et les services aux collectivités sont presque toutes exclues, car leurs ratios (endettement, rentabilité du capital) ne se lisent pas comme ceux d'un industriel. Et le filtre de dilution ne distingue pas une fusion ou une introduction en Bourse d'une vraie dilution : avant d'écarter une valeur intéressante pour ce seul motif, regardez le nombre d'actions année par année (dérogations dans `config/strategie.json`).

## Les sources de données

| Donnée | Source principale | Recoupement |
|---|---|---|
| Cours (ajustés des dividendes) | Yahoo Finance | Aucun : pas de seconde source gratuite accessible par programme |
| Taux de change | Banque centrale européenne (cours de référence quotidiens) | Yahoo : écart médian sur 90 jours, affiché page Méthode. Yahoo fournit seul le lari géorgien et le dollar de Taïwan, que la BCE ne publie pas |
| États financiers, sociétés américaines | Yahoo Finance | Comptes déposés à la SEC (10-K, 20-F) : chiffre d'affaires, résultat net, flux d'exploitation, fonds propres et total du bilan du dernier exercice, tolérance 3 % |
| États financiers, sociétés européennes | Yahoo Finance | Aucun recoupement du dernier exercice ; les rapports annuels ESEF (filings.xbrl.org) allongent l'historique vers le passé, voir plus bas |
| Achats et ventes des dirigeants, sociétés américaines | Formulaires 4 déposés à la SEC | — |
| Consensus des analystes, PER prospectif | Yahoo Finance | Aucun |
| Secteurs | iShares (classification GICS), affinés par l'industrie Yahoo | — |
| Composition des indices | iShares | — |

**Rapports annuels européens (ESEF).** Depuis l'exercice 2020, les sociétés cotées dans l'Union européenne publient leur rapport annuel avec des étiquettes XBRL. Le Royaume-Uni et la Norvège suivent un régime proche ; la Suisse n'est pas concernée. La base publique filings.xbrl.org les rassemble. Chaque rapport donne l'exercice et son comparatif, d'où deux à quatre exercices de plus que Yahoo.

- **Identification.** La base ne connaît pas les tickers : la société est cherchée par son nom. Elle n'est retenue que si son chiffre d'affaires, son résultat net ou son total de bilan d'un exercice commun reproduit Yahoo à 3 % près.
- **Raccord.** Comme pour la SEC, chaque poste ne prolonge l'historique que s'il concorde avec Yahoo sur deux exercices communs. Les investissements sont essayés sous plusieurs formes : corporels seuls, corporels + incorporels, postes propres à la société. Le flux de trésorerie disponible (flux d'exploitation − investissements) l'est aussi. Quand aucune forme ne reproduit Yahoo, comme chez LVMH ou L'Oréal, le FCF reste sur 4 exercices.
- **Couverture.** Les sociétés allemandes sont presque absentes de la base, car elles déposent au registre allemand. Les rapports les plus récents y arrivent parfois avec plusieurs mois de retard.
- **Rythme.** La base limite le débit à une requête par seconde. Le premier chargement prend donc deux à trois heures (`python -m pf esef`). Ensuite, chaque mise à jour complète lit au plus 60 nouvelles sociétés et vérifie chaque mois, en moyenne, les nouveaux rapports. Les vérifications sont réparties sur le mois, comme le renouvellement des comptes SEC (tous les 14 jours en moyenne) : aucune mise à jour ne les relit tous d'un coup.

Une valeur dont les comptes Yahoo s'écartent de ceux de la SEC porte l'alerte « Données Yahoo contredites par la SEC », et la fiche détaille l'écart poste par poste. Les investissements sont montrés mais ne déclenchent pas d'alerte : Yahoo y ajoute souvent les logiciels immobilisés. La SEC exige une adresse de contact dans chaque requête : elle se règle dans `profil/prive.json` (clé `contact_sec`), fichier personnel à ne pas partager.

## 2. Les filtres d'exclusion

Inspirés des sept critères « anti-médiocrité » du framework ai-berkshire : ils ne prétendent pas trouver les meilleures entreprises, ils écartent celles qui ne sont **certainement pas** de premier ordre.

| Filtre | Seuil d'exclusion | Ce qu'il mesure |
|---|---|---|
| Rentabilité moyenne (ROIC, ou ROE pour banques, assureurs, holdings) | < 8 % | L'entreprise crée-t-elle de la valeur au-delà du coût du capital ? |
| Flux de trésorerie disponible cumulé (4-5 ans) | ≤ 0 | Les bénéfices se transforment-ils en cash ? |
| Couverture des intérêts (EBIT / intérêts) | < 3x | Solidité face à une récession ou une hausse des taux |
| Dette nette / EBITDA | > 3,5x | Levier excessif |
| Marge brute | < 15 % (sauf ROIC > 20 %) | Pouvoir de prix ; la dérogation couvre les modèles à forte rotation (Costco) |
| Évolution du nombre d'actions | > +3 % par an | Dilution des actionnaires (dérogations listées pour les fusions payées en titres) |
| Résultat sur 12 mois | ≤ 0 | Pertes |

**Dérogation « devenue rentable »** : une entreprise dont la moyenne est plombée par une phase d'investissement terminée passe le filtre de rentabilité si sa dernière année dépasse 12 %, avec une marge brute supérieure à 30 % et des flux d'exploitation positifs deux ans de suite.

## 3. Le score composite (0 à 100)

Le score final est la moyenne de six analyses, chacune ramenée sur 100 :

| Analyse | Conversion sur 100 |
|---|---|
| **Piliers** | Le bloc décrit ci-dessous (colonne « Piliers » du screener) |
| **Valorisation** | Le pilier valorisation seul : rang centile du rendement du FCF, du rendement des bénéfices, du TRI implicite et du PER prospectif |
| **Quatre regards** | Total sur 20, multiplié par 5 |
| **Piotroski** | Note sur 9 ramenée sur 100 |
| **Altman** | 0 sous 1,81, 100 au-dessus de 2,99, progression linéaire entre les deux |
| **Beneish** | 0 au-dessus de -1,78, 100 à -2,22 ou moins, progression linéaire entre les deux |

Les poids sont égaux par défaut (0 pour les six critères) et se règlent dans `config/strategie.json` (`poids_score`). Un signal absent, comme Piotroski pour une banque, reçoit la médiane de l'univers : la société n'a ni bonus ni malus. Sans cela, les financières seraient pénalisées d'office.

**Pourquoi un bloc Valorisation à part.** L'audit du 04/11/2026 a montré que, dans le seul bloc Piliers, la valorisation ne pesait que 5 % du score (25 % d'un bloc sur cinq), alors que Piotroski, Altman et Beneish mesurent la santé financière et que les regards recoupent le pilier qualité (corrélation de rang de 0,59). Pour une stratégie « qualité à prix raisonnable », le prix ne passait donc presque que par les filtres. Compté aussi à part, il pèse environ 21 % du score. Momentum et croissance ne comptent que dans le bloc Piliers. La grille des six critères peut devenir un septième bloc (`criteres` dans `poids_score`, 0 par défaut).

### Le bloc Piliers

Chaque indicateur est converti en **rang centile** dans l'univers (100 = meilleur), puis moyenné par pilier. Les banques, assureurs et holdings sont comparés entre eux sur la qualité et la valorisation (un PER d'assureur ne se compare pas à une VE/EBIT d'industriel).

| Pilier | Poids par défaut | Indicateurs |
|---|---|---|
| Qualité | 35 % | ROIC/ROE moyen, marge brute, marge opérationnelle, conversion du résultat en cash, stabilité des marges, dette nette/EBITDA, évolution du nombre d'actions |
| Valorisation | 25 % | Rendement du flux de trésorerie (après rémunérations en actions), EBIT/valeur d'entreprise, TRI implicite, PER prospectif |
| Croissance | 20 % | Croissance historique du CA, du BPA et du flux par action, consensus des analystes (BPA, CA) |
| Momentum | 20 % | Performance 12 mois hors dernier mois, performance 6 mois, écart à la moyenne 200 jours |

Les poids se règlent dans le screener ou dans `config/strategie.json`. Le facteur momentum est l'un des mieux documentés en finance ; il évite d'acheter trop tôt une action dont les mauvaises nouvelles ne sont pas finies.

## 4. La valorisation : que suppose le cours ?

Plutôt que de prédire un prix, l'outil retourne la question (approche « expectations investing » de Mauboussin) : **quelle croissance le cours actuel suppose-t-il ?**

Le modèle des *value drivers* relie croissance et capital : pour croître de `g`, une entreprise au ROIC `R` doit réinvestir `g / R` de son résultat. Le flux disponible vaut donc `résultat × (1 − g / R)`. Une entreprise très rentable croît sans consommer de cash ; une entreprise peu rentable doit tout réinvestir.

- **Croissance implicite** : la croissance annuelle sur 5 ans (puis convergence vers 3 % sur 5 ans) qui justifie exactement la valeur d'entreprise, pour un rendement exigé de 9 %.
- **TRI implicite** : le rendement annuel obtenu si la croissance attendue (médiane du consensus et de l'historique) se réalise.

Lecture : un TRI implicite supérieur à 10 % pour une entreprise de qualité est attrayant ; en dessous de 6 %, le cours intègre déjà beaucoup de bonnes nouvelles. La page « Fiche valeur » permet de changer chaque hypothèse.

**Limites connues** : le ROIC des entreprises qui croissent par acquisitions est minoré par l'écart d'acquisition (Schneider, Assa Abloy…) ; les cycliques au sommet paraissent bon marché ; les holdings ne sont pas valorisées (il faut la décote sur actif net).

## Moat estimé, P/FCF et PER historique

Ces deux données éclairent la décision mais n'entrent ni dans le score ni dans les filtres.

**Moat estimé (Large, Étroit, Faible).** Le moat de Morningstar est un jugement d'analystes vendu sous licence : il n'est pas accessible ici. Celui-ci en est une approximation chiffrée, qui mesure les traces d'un avantage dans les comptes, avec un point par critère :

- ROIC moyen d'au moins 15 % ;
- ROIC d'au moins 12 % même la pire année ;
- ROIC final à au moins 80 % du premier, sans année de pertes ;
- marge brute moyenne d'au moins 40 % ;
- marge brute qui ne recule pas de plus de 2 points, sans année de pertes ;
- marge opérationnelle stable (écart-type de 3 points au plus).

De 5 à 6 points : Large. 3 ou 4 : Étroit. Moins : Faible. Il porte sur les cinq derniers exercices de l'historique commun (Yahoo, prolongé par la SEC pour les sociétés américaines) ; le ROIC et la marge brute, que la SEC ne permet pas de reconstituer, restent sur les quatre exercices de Yahoo. C'est court pour juger de la durabilité. Un ROIC plombé par les écarts d'acquisition sous-note les groupes issus de grandes fusions, et une marge brute faible sous-note les distributeurs à forte rotation. Ce score constate un résultat sans en expliquer la cause. Il n'est pas calculé pour les banques, assureurs et holdings.

**Prix sur flux de trésorerie disponible (P/FCF).** Capitalisation divisée par le flux de trésorerie disponible des 12 derniers mois, et comparée comme le PER à son niveau médian des dernières clôtures annuelles (six au plus). Le screener permet de fixer un P/FCF maximum et de ne garder que les actions sous leur P/FCF habituel. Ce ratio n'entre pas dans le score, qui compte déjà son inverse : le rendement du FCF hors rémunérations en actions (pilier valorisation). Il n'est pas calculé quand le flux est négatif, ni pour les banques et assureurs.

**P/FCF hors SBC.** Même calcul sur le flux de trésorerie disponible diminué des rémunérations en actions (stock-based compensation) : ces actions gratuites sont un coût réel, payé en dilution plutôt qu'en cash. Son inverse, le rendement du FCF net, compte dans le pilier valorisation. Faute de rémunérations en actions publiées (fréquent hors des États-Unis), elles comptent pour 0. La fiche trace le P/FCF jour par jour, avec ou sans les SBC : capitalisation du jour divisée par le flux du dernier exercice publié (clôture + 60 jours), puis des 12 derniers mois ; le dernier point vaut donc le P/FCF actuel. Pour les sociétés américaines, l'historique remonte aussi loin que les comptes SEC le permettent.

**PER historique.** Médiane du PER aux dernières clôtures annuelles (six au plus), comparée au PER actuel. Elle dit si une action est chère ou non par rapport à elle-même. Une forte décote n'est pas forcément une occasion : elle peut signaler que le marché voit un vrai problème.

## Prix juste et prix visé

La section « Prix juste » de la fiche répond à une question simple : à quel cours l'action se paierait-elle au multiple que je juge raisonnable ? On choisit un ratio et sa cible, l'outil en déduit le prix.

- **Calcul.** Prix cible = cours actuel × multiple cible / multiple actuel. Le multiple actuel porte sur les résultats des 12 derniers mois, qu'on suppose inchangés : le prix cible bouge donc à chaque publication.
- **Ratios proposés.** Les ratios proposés sont le P/FCF, le P/FCF hors SBC, le PER et le prix / chiffre d'affaires (P/CA). Une banque ou un assureur n'a que le PER : ses flux de trésorerie mêlent dépôts et crédits. Une holding n'en a aucun : elle se juge sur sa décote par rapport à l'actif net. Un résultat négatif ou nul ne donne pas de prix.
- **Repères pour fixer sa cible.** La fiche trace chaque multiple jour par jour (P/FCF, avec ou sans les SBC, et P/CA ; PER pour une banque), avec son minimum et un tableau des médianes : sur 5 ans, sur 10 ans, depuis le début de l'historique. Une médiane sur 5 ou 10 ans n'est donnée que si l'historique couvre la période à 5 % près. Pour une société européenne (quatre exercices chez Yahoo), il ne reste souvent que la médiane depuis le début. La saisie part de la médiane sur 5 ans, à défaut sur 10 ans, puis sur tout l'historique. Ce point de départ est neutre : viser en dessous ménage une marge de sécurité.
- **Limite principale.** Un multiple tombé loin sous sa médiane n'est pas forcément une aubaine : la croissance a pu ralentir, un brevet expirer, un concurrent arriver. La médiane passée n'est un repère que si l'entreprise n'a pas changé. Cours ajustés des dividendes : les multiples passés sont un peu sous-estimés.
- **Prix visé.** Le bouton « Ajouter à la watchlist » (ou « Viser ce prix » pour une valeur déjà suivie) enregistre le prix et ce qui l'a fixé (« P/FCF 20,0 ») dans `profil/watchlist.csv`. La page Watchlist affiche ensuite le cours, le prix visé et l'écart (−20 % : il faut une baisse de 20 %). Dès que le cours passe sous le prix visé, elle affiche un bandeau et le tableau de bord ajoute un point de vigilance. Le prix visé ne se recalcule pas tout seul : revenez dans la fiche après une publication pour le mettre à jour. Atteindre son prix n'est pas un signal d'achat en soi : c'est le moment de relire la thèse.

## Un seul historique, des données datées du même jour

- **Un seul historique.** Tous les calculs lisent les comptes par le même module (`pf/postes.py`) : une seule correspondance avec les postes Yahoo, et un historique prolongé par la SEC quand le raccord est vérifié. Croissance du chiffre d'affaires, marge de FCF et évolution du nombre d'actions ont donc la même valeur dans le screener, la fiche, les filtres et les six critères, sur la même fenêtre (cinq ans au plus, trois pour les sociétés européennes). Le ROIC (rentabilité du capital investi, celle des filtres et du moat) et le ROCE (résultat opérationnel sur capitaux employés, celui des critères) restent deux mesures différentes : le premier retire la trésorerie, le second non.
- **Dette nette au dernier bilan publié.** Elle vient du dernier bilan trimestriel quand il existe, pour la valeur d'entreprise, la dette nette / EBITDA (sur 12 mois glissants) et le critère dette / FCF. Sans bilan, elle est inconnue, pas nulle.
- **Tout au dernier cours.** Les fiches Yahoo datent de leur téléchargement (jusqu'à une semaine). Capitalisation, PER prospectif et objectif des analystes sont recalés sur le dernier cours.
- **Données insuffisantes.** Une valeur dont la rentabilité ne peut pas être calculée (bilan ou résultat absents) est exclue avec ce motif, au lieu de passer les autres filtres par défaut. Une section que Yahoo refuse lors d'un téléchargement garde sa version précédente ; une fiche sans compte de résultat, bilan ou flux est retentée dès le lendemain.

## Suivre ses lignes

- **Actualités.** Pour vos lignes (hors fonds) et votre watchlist, la page « Actualités » réunit :
  - la presse française (flux public de Google Actualités, titres seuls, recherche sur le nom de la société avec des mots boursiers pour écarter les homonymes, réglable par valeur dans `profil/actualites.csv`) ;
  - les déclarations officielles 8-K à la SEC (résultats, dirigeants, acquisitions) pour les sociétés américaines ;
  - la date des prochains résultats ;
  - les signaux de l'outil : prix visé atteint, achats de dirigeants, mouvements des grands investisseurs, forte variation, sortie des filtres.

  Relues au plus toutes les 6 heures, à chaque mise à jour.
- **Conditions de vente chiffrées.** Une condition de vente mesurable devient une règle : un indicateur, une comparaison et un seuil (`profil/regles_vente.csv`, ou la fiche, section Thèse). Exemple : le CA des 12 derniers mois sous celui du dernier exercice. Les règles sont vérifiées à chaque mise à jour ; une règle atteinte remonte au tableau de bord. C'est une invitation à relire la thèse, pas un ordre de vente. Yahoo ne donne qu'un point « 12 mois » : la tendance récente du CA est donc une approximation (12 derniers mois contre dernier exercice clos).
- **Scénarios à 5 ans.** Dans la fiche (section Valorisation), trois jeux d'hypothèses donnent chacun un prix dans 5 ans et un rendement annuel hors dividendes. Les hypothèses : croissance du CA, marge (de FCF, ou nette pour une financière) et multiple de sortie. Le point de départ est prudent : croissance plafonnée à 15 %, et multiple central au plus égal au multiple actuel, donc sans revalorisation supposée. Le retour au multiple médian est le cas optimiste. Une fois enregistrés, les scénarios sont suivis : le tableau de bord signale un cours au-dessus du prix optimiste ou sous le prix pessimiste.
- **Risques.** La page « Risques » porte sur vos positions réelles (à défaut, les poids cibles), avec 3 ans de cours en euros. Elle montre :
  - la concentration : plus grosse ligne, trois premières, nombre effectif de lignes ;
  - la volatilité, la perte maximale et le pire mois ;
  - les devises de cotation et les secteurs ;
  - la part du risque de chaque ligne et les corrélations ;
  - trois scénarios de choc : marché -30 % selon la sensibilité passée de chaque ligne à l'indice, dollar -10 %, or -20 %.

  Ce sont des ordres de grandeur.
- **Fraîcheur des données.** La fiche donne la date du dernier cours et celle de la lecture des comptes. Un cours resté en arrière du marché (ticker changé, valeur suspendue) est signalé, et le tableau de bord le relève pour vos lignes. Le screener indique le nombre d'exercices d'historique : 4 = Yahoo seul, soit 3 ans de croissance seulement.

## Construction de portefeuille

La page « Construction de portefeuille » (menu Analyser) construit un portefeuille par des règles seules. Il sert de point de comparaison et de liste d'idées, pas de cible : il ne modifie jamais vos poids cibles.

- **Méthode de notation.** Elle classe les candidats. Chaque note est ramenée à son rang dans l'univers (0 à 100) pour rester comparable, et le score composite départage les ex aequo. Méthodes proposées :
  - **Score composite** : la note de l'outil ;
  - **Quatre regards** : leur moyenne ;
  - **un regard seul** : Buffett, Munger, Fisher ou Terry Smith ;
  - **Qualité d'abord** : pilier qualité 60 %, six critères 40 % ;
  - **Croissance** ;
  - **Valeur** : valorisation 70 %, qualité 30 % ;
  - **Momentum** ;
  - **Personnalisée** : des curseurs dosent chaque composante.

  L'onglet « Comparer les méthodes » montre quelles valeurs chaque méthode retient avec les mêmes garde-fous. Une valeur retenue par beaucoup de méthodes plaît sous plusieurs angles.
- **Sélection.** Les meilleures notes parmi les valeurs éligibles, sous trois conditions réglables :
  - un plancher de qualité : par défaut, au moins 4 des 6 critères remplis, en proportion des critères évalués (une banque n'en a que deux, elle doit les remplir tous les deux) ;
  - pas de moat estimé « Faible » ;
  - au plus 25 % des lignes et du poids dans les secteurs cycliques (énergie et infrastructures, matériaux et chimie, banques).

  Ces garde-fous corrigent un biais connu du score : au sommet du cycle, les cycliques paraissent bon marché et le bloc valorisation les favorise.
- **Diversification.** Nombre de lignes, plafond par secteur, poids minimal et maximal par ligne. La part PEA n'est imposée que si on le demande.
- **Pondération.** Note de la méthode choisie × 1/volatilité par défaut, ou parts égales, ou variance minimale.
- **Ce que montre la page.**
  - Pour chaque idée : note de la méthode, score composite, les quatre regards (1 à 5), critères, moat, P/FCF comparé à son niveau habituel, nombre de grands investisseurs qui la détiennent, achats de dirigeants.
  - Une comparaison avec la seule partie actions de votre portefeuille : les ETF et ETC n'ont pas ces indicateurs.
- **Interactions.** Cocher une ligne l'ajoute à la watchlist ; cliquer sur une cellule ouvre la fiche.
- **Usage partagé.** Les réglages enregistrés servent aussi au backtest du portefeuille systématique et à la commande `construire`.

## Backtest à date des méthodes de notation

Le backtest du portefeuille note les actions avec les comptes d'aujourd'hui : il sait déjà qui a réussi. Le mode « Méthodes de notation : test à date » de la page Backtest refait le choix à chaque 1er avril depuis 2012, avec les seuls comptes publiés à cette date. Ce sont les comptes déposés à la SEC, réputés connus 90 jours après la clôture.

- **Univers.** Les sociétés américaines de l'univers, hors financières : environ 450.
- **Indicateurs reconstitués.**
  - Qualité : rentabilité des fonds propres, marges opérationnelle et de FCF, dilution.
  - Croissance : CA sur 3 ans.
  - Valeur : rendements du FCF et des bénéfices.
  - Momentum : 12-1 mois.

  Les quatre regards et les critères ne sont pas reconstitués.
- **Capitalisation d'époque.** Elle est déduite de celle d'aujourd'hui, avec les divisions d'actions repérées et neutralisées : la SEC publie les nombres d'actions d'origine.
- **Simulation.** Les valeurs choisies sont gardées un an à poids égaux, en euros. La comparaison se fait avec toutes les valeurs testables à poids égaux et avec le S&P 500.
- **Ce que montre le test (novembre 2026, 20 lignes, 2012-2026).** Qualité et valeur n'ont pas battu l'ensemble des valeurs à poids égaux (environ 1,5 à 2 points de moins par an). Elles l'ont fait avec moins de volatilité et des pertes maximales plus faibles pour la qualité. Croissance et momentum ont fait beaucoup mieux, mais avec un biais : l'univers d'aujourd'hui contient les sociétés qui ont réussi à grossir, ce qui avantage précisément ces méthodes.
- **Limite principale : le biais du survivant.** Il gonfle toutes les courbes ; seule la comparaison au sein du même univers est juste.

## Grands investisseurs

Page « Grands investisseurs » (menu Analyser) : ce que détiennent et achètent des investisseurs reconnus, pour trouver des idées à étudier. C'est une source d'inspiration, pas un signal : elle n'entre ni dans le score ni dans les filtres.

**Gérants (formulaires 13F)**
- **Source.** Tout gérant qui détient plus de 100 millions de dollars d'actions américaines déclare ses positions à la SEC dans les 45 jours qui suivent la fin de chaque trimestre.
- **Ce que montre la page.** Le portefeuille de chaque investisseur suivi, et ses mouvements d'un trimestre à l'autre : entrée, renforcement, allègement, sortie, d'après le nombre d'actions. S'y ajoutent les mouvements récents de tous les investisseurs et les titres qu'ils partagent (les classes d'actions d'un même émetteur sont réunies).
- **Rectificatifs.** Les positions d'abord tenues confidentielles, puis révélées par un rectificatif (« NEW HOLDINGS »), sont ajoutées à leur trimestre.
- **Tickers.** Ils viennent d'OpenFIGI (Bloomberg), à partir du code CUSIP. À défaut, un rapprochement par le nom est fait, seulement s'il est sans ambiguïté. Un clic sur une ligne de votre univers ouvre sa fiche.
- **Limites.**
  - Positions longues en actions américaines seulement : ni ventes à découvert, ni options, ni liquidités, ni la plupart des valeurs européennes.
  - Photo d'un seul jour, publiée jusqu'à six semaines plus tard, sans le prix payé ni la raison de l'achat.
  - Une division d'actions apparaît comme un renforcement.
  - Un changement de nom (nouveau CUSIP) apparaît comme une sortie suivie d'une entrée.

**Élus de la Chambre des représentants (STOCK Act)**
- **Source.** Les représentants déclarent au greffe de la Chambre les achats et ventes de titres faits par eux, leur conjoint ou leurs enfants à charge, au plus tard 45 jours après l'opération. Le délai réel médian est affiché.
- **Lecture.** Les rapports remplis en ligne sont lus automatiquement (pypdf), y compris le détail des options : nombre de contrats, prix d'exercice, échéance. Les rapports déposés sur papier (images scannées, par exemple ceux de Ro Khanna ou Michael McCaul) ne sont pas lisibles sans reconnaissance de caractères : seul leur lien est donné.
- **Limites.** Les montants ne sont connus que par tranches (« 1 001 – 15 000 $ »). Le Sénat n'est pas couvert : son site impose d'accepter des conditions à chaque visite.

**Mise à jour et listes**
- **Quand.** Les déclarations se mettent à jour à chaque `maj`, avec le bouton de la page, ou avec `python -m pf investisseurs`. Les gérants sont consultés au plus une fois par semaine, les élus chaque jour. Seules les nouvelles déclarations sont lues.
- **Listes suivies.** `config/investisseurs.csv` (CIK SEC du gérant) et `config/elus.csv` (nom et circonscription). Elles se modifient depuis l'onglet « Gérer les listes » : un gérant est vérifié auprès de la SEC avant d'être ajouté, et un élu se choisit parmi ceux qui ont déclaré des transactions.

## La fiche valeur : activité et historique

- **D'où vient le chiffre d'affaires.** Deux camemberts : « comment » (par activité, produit ou segment) et « où » (États-Unis contre international). Ils sont lus dans le dernier rapport annuel déposé à la SEC (10-K), où les montants portent des étiquettes XBRL ; Yahoo n'a pas ces données. Une répartition n'est retenue que si ses parts somment au chiffre d'affaires (à 2 % près, le reste devenant « Autres ») ; les sous-totaux sont écartés. Sociétés américaines seulement ; libellés repris du rapport, en anglais.
- **Achats et ventes des dirigeants.** Sociétés américaines seulement. Les dirigeants, administrateurs et actionnaires de plus de 10 % déclarent chaque transaction à la SEC (formulaire 4) sous deux jours ouvrés.
  - **Ce qui compte.** Seules les opérations en bourse sont retenues : achats (code P) et ventes (code S). Attributions gratuites, levées d'options et retenues fiscales sont ignorées.
  - **Signal.** Un achat avec son propre argent est le signal le plus parlant : on vend pour mille raisons, on n'achète que pour une. « Achats groupés » signifie qu'au moins trois personnes distinctes ont acheté sur 12 mois. Ce signal remonte aussi au tableau de bord pour les lignes et la watchlist.
  - **Ventes programmées.** Les ventes décidées à l'avance (plan 10b5-1, indiqué depuis 2023) disent peu de choses.
  - **Lecture.** La première lecture prend 15 à 40 secondes, d'où un bouton ; ensuite, seuls les nouveaux formulaires sont lus.
  - **Limite.** Un achat de dirigeant est un indice, pas une preuve.
  - **Europe.** Les déclarations européennes (règlement MAR) sont publiées par chaque régulateur national, sans base commune.
- **Historique financier.** Neuf graphiques : chiffre d'affaires, free cash flow et rémunérations en actions, FCF par action, ROCE, marge brute, marge de FCF, actions diluées, dividende par action, trésorerie et dette. Chaque série part du plus ancien exercice disponible (Yahoo, prolongé par la SEC ou les rapports ESEF quand les chiffres concordent) et finit par les 12 derniers mois. Les croissances annuelles sur 5 et 10 ans ne s'affichent que si l'historique couvre toute la durée.

## Les six critères de qualité

Une grille simple, critère rempli ou non, affichée en cartes vertes ou rouges sur la fiche de chaque valeur :

| Critère | Mesure | Seuil |
|---|---|---|
| Croissance du chiffre d'affaires | Taux annuel sur 5 ans | Plus de 10 % |
| Croissance du free cash flow | Taux annuel sur 5 ans (flux d'exploitation − investissements) | Plus de 10 % |
| ROCE | Résultat opérationnel / (total du bilan − dettes courantes), moyenne sur 5 ans | Plus de 15 % |
| Dette nette / free cash flow | Dette nette au dernier trimestre / free cash flow des 12 derniers mois | Moins de 3 |
| Nombre d'actions en circulation | Évolution des actions diluées sur 5 ans | 0 % ou moins |
| Marge du free cash flow | Free cash flow / chiffre d'affaires, moyenne sur 5 ans | Plus de 10 % |

- **Historique.** Yahoo ne donne que 4 exercices, soit 3 ans de croissance. Pour les sociétés américaines, les comptes déposés à la SEC prolongent chaque série vers le passé, mais seulement avec un poste qui reproduit les chiffres Yahoo à 3 % près sur les exercices communs : un poste de périmètre différent n'allonge rien. Les sociétés européennes sont prolongées de la même façon par leurs rapports annuels ESEF, souvent de deux exercices, ce qui donne 5 ans de croissance. Sans rapport trouvé (Suisse, la plupart des sociétés allemandes), elles restent sur 3 ans. La fenêtre réellement utilisée est écrite sur chaque carte.
- **Cas particuliers.** Un free cash flow négatif en début ou en fin de période fait échouer le critère de croissance. Une société sans dette nette remplit le critère de dette même avec un flux négatif. Pour les banques, assureurs et holdings, seuls la croissance du chiffre d'affaires et le nombre d'actions sont évalués : les quatre autres critères supposent un bilan d'entreprise classique.
- **Usage.** Le screener affiche le décompte (« 5/6 »), les six valeurs, et permet d'exiger un nombre minimal de critères remplis. Les seuils se règlent dans `config/strategie.json` (`criteres`).
- **Hors score par défaut.** La grille recoupe les piliers qualité et croissance, et une grille de seuils sert surtout de filtre. Pour l'intégrer au score composite, donner un poids à `criteres` dans `poids_score` : le bloc vaut alors la part des critères remplis, sur 100, et la médiane de l'univers quand moins de quatre critères sont évalués.

## Les trois signaux de santé

Ils sont calculés sur les deux derniers exercices annuels et s'affichent dans le screener, la fiche valeur et la page Composition. Ils déclenchent une alerte et comptent dans le score, mais pas dans les filtres. Ils ne sont pas calculés pour les banques, assureurs et holdings, dont le bilan ne s'y prête pas.

- **Piotroski (0 à 9)** : la situation s'améliore-t-elle ? Un point par critère rempli : résultat positif, flux d'exploitation positif, rentabilité des actifs en hausse, flux supérieur au résultat, dette longue qui n'augmente pas, liquidité en hausse, pas de nouvelles actions, marge brute en hausse, rotation des actifs en hausse. Alerte à 2 ou moins. Si un critère manque, la note est ramenée sur 9.
- **Altman (Z-Score de 1968)** : risque de faillite. Sous 1,81 : zone fragile ; au-dessus de 2,99 : zone sûre. Pensé pour les industriels, il sous-note les entreprises aux gros actifs et celles dont les rachats d'actions ont réduit les réserves.
- **Beneish (M-Score à 8 variables)** : les comptes sont-ils crédibles ? Au-dessus de -1,78, le profil ressemble à celui des manipulateurs comptables. Ce n'est pas une preuve : une forte croissance ou une grosse acquisition déclenchent le même signal. Chaque indice est plafonné à 5 pour qu'une acquisition ou un paiement ponctuel n'écrase pas les autres variables. Les frais commerciaux manquent pour une partie des sociétés : leur indice est alors neutralisé.

## Le crible des quatre regards

La page « Quatre regards » note chaque action de la base de 1 à 5, exclues comprises, pour décider lesquelles méritent une analyse complète. Les notes figurent aussi dans le screener, la fiche valeur et l'export Excel. Les fonds ne sont pas notés. Les notes viennent de règles fixes :

- **Buffett** : 1 point de base, puis 1 point pour une rentabilité d'au moins 15 %, 1 pour 30 %, 1 pour un TRI implicite d'au moins 10 %, 1 pour 14 %.
- **Munger** : 5 points, moins 1 pour chaque fragilité : volatilité au-dessus de 45 %, perte de plus de 50 % en 3 ans, dette nette au-dessus de 2 fois l'EBITDA, marge instable, hausse de plus de 100 % sur un an, ou société financière.
- **Fisher** : 1 point de base, puis 1 point pour une croissance attendue d'au moins 6 %, 1 pour 10 %, 1 pour 16 %, 1 si le nombre d'actions baisse d'au moins 2 % par an.
- **Smith** : 1 point de base, puis 1 point pour une rentabilité d'au moins 15 %, 1 pour 30 %, 1 pour une conversion en cash d'au moins 100 %, 1 pour un rendement du flux de trésorerie d'au moins 5 % ; moins 1 si la marge opérationnelle est sous 15 %, moins 1 si elle est instable. Les financières sont plafonnées à 3.

Ces règles ne voient ni un pic de cycle, ni une menace réglementaire, ni un risque pays. `config/regards_ajustements.csv` les corrige à la main, avec un motif. Une correction est un jugement : seules celles datées reposent sur une vérification des publications récentes.

## 5. La sélection proposée par Claude (archivée)

> Depuis le 29/10/2026, l'outil suit votre portefeuille réel (`profil/portefeuille_modele.csv`). La sélection décrite ici est conservée dans `profil/selection_claude_2026-10.csv` : elle sert de point de comparaison (page « Backtest ») et de réservoir d'idées.

25 lignes choisies à partir du screener, puis examinées une à une : solidité de l'avantage concurrentiel, actualité récente (résultats, réglementation), diversification.

- **Poche cœur (environ 2/3)** : compounders de premier ordre (ASML, TSMC, Microsoft, Alphabet, Mastercard, Safran…), poids de 4 à 6,5 %.
- **Poche opportunités (environ 1/3)** : qualité décotée ou pari contrarien (Adobe, Wolters Kluwer, NVIDIA, GTT…), poids de 2,5 à 3,5 %, revue chaque semestre.
- **Barbell IA** : d'un côté les gagnants de l'IA (fonderie, lithographie, plateformes) ; de l'autre des leaders que la peur de l'IA a fait chuter (logiciels, données). Si l'IA détruit les seconds, les premiers en profitent ; sinon, les seconds se revalorisent.
- **PEA / compte-titres à 51 / 49** : tout ce qui est européen et éligible va dans le PEA (avantage fiscal), le compte-titres porte ce qui n'a pas d'équivalent européen.

Contraintes : 25 % maximum par secteur, aucune ligne au-delà de 6,5 % à l'achat.

## 6. Quand vendre

Il n'y a que trois bonnes raisons de vendre (règle de Li Lu, reprise par ai-berkshire) :

1. on s'est trompé sur l'entreprise ;
2. les faits invalident la thèse (chaque fiche contient sa **condition de vente**, décidée avant d'acheter) ;
3. une opportunité nettement meilleure apparaît (rendement attendu supérieur d'au moins 5 points à risque comparable).

La baisse du cours, le prix de revient ou le bruit macroéconomique n'en font pas partie. Distinguer **« à réexaminer »** (signal à comprendre : un trimestre décevant) et **« thèse invalidée »** (fait établi : perte du monopole, fraude, effondrement structurel). En cas de doute, alléger progressivement plutôt que tout vendre.

Une ligne qui dépasse le double de son poids cible peut être allégée, de préférence dans le PEA (pas d'impôt) ; sur le compte-titres, on laisse courir et on rééquilibre par les apports.

## 7. La routine

| Fréquence | Durée | Quoi |
|---|---|---|
| Chaque mois | 15 min | Mise à jour complète (les mises à jour rapides suffisent entre-temps), regarder les alertes du tableau de bord, investir l'apport (page « Apport du mois »), saisir les ordres exécutés |
| Chaque trimestre | 1 h | Après les publications : relire les conditions de vente, noter les faits marquants dans les fiches (commande Claude `/revue-portefeuille`) |
| Chaque semestre | 1 h | Revoir la poche opportunités au regard du score et du TRI implicite ; étudier les meilleurs scores hors portefeuille (`/analyse-valeur`) |
| Chaque année | 2 h | Bilan contre l'ETF MSCI World ; rééquilibrage si une ligne dépasse 2x sa cible ou un secteur 30 % ; mise à jour de l'univers |

## 8. Fiscalité française (repères)

- **PEA** : plafond de versements de 150 000 €, actions de sociétés européennes (UE et EEE) uniquement. Après 5 ans, les gains sont exonérés d'impôt sur le revenu, seuls les prélèvements sociaux restent dus ; les arbitrages internes ne sont jamais imposés. C'est l'enveloppe à remplir en priorité. Les retenues à la source étrangères sur dividendes (Allemagne, Suède, Belgique…) n'y sont pas récupérables : un coût modeste pour des valeurs de croissance.
- **Compte-titres** : plus-values (prix moyen pondéré) et dividendes au prélèvement forfaitaire unique, ou au barème sur option. Dividendes américains : retenue de 15 % (formulaire W-8BEN), imputable en France.
- La loi évolue : vérifiez les taux en vigueur sur impots.gouv.fr. L'IFU de votre courtier fait foi.
- **Accès aux marchés** : les actions nordiques (Stockholm, Copenhague, Oslo) sont éligibles au PEA, mais tous les courtiers ne les proposent pas dans cette enveloppe. La colonne « alternative » du portefeuille modèle propose un remplaçant.

## 9. Limites et honnêteté

- **Données gratuites (Yahoo Finance)** : elles sont parfois fausses ou incomplètes, et ne couvrent que 4 ans d'historique (davantage grâce à la SEC aux États-Unis et aux rapports ESEF en Europe, quand les chiffres concordent). Le recoupement SEC ne couvre que les sociétés américaines et le dernier exercice. Avant tout achat, vérifiez les chiffres clés dans les publications de l'entreprise.
- **Le backtest est flatteur par construction** : les valeurs ont été choisies en 2026, en connaissant leur succès passé.
- **La plupart des gérants actifs font moins bien que leur indice sur 10 ans** (études SPIVA). L'outil compare donc en permanence votre portefeuille au même argent placé dans un ETF MSCI World. Si l'écart reste négatif sur 3 à 5 ans, la décision rationnelle est de basculer vers l'ETF, ou d'adopter un cœur ETF avec une poche de stock-picking.
- **Ce n'est pas un conseil personnalisé** : la bonne allocation dépend de votre horizon, de votre épargne de précaution, de vos autres actifs et de votre capacité à supporter une baisse de 30 à 50 % sans vendre.
