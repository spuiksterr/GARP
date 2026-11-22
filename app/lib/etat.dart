/// État de l'application : données de marché (cache local, mise à jour depuis GitHub), portefeuille, watchlist,
/// profil, notes personnelles.
library;

import 'dart:io';
import 'dart:isolate';

import 'package:material_ui/material_ui.dart';
import 'package:path_provider/path_provider.dart';

import 'donnees.dart';
import 'formats.dart';
import 'github.dart';
import 'import_portefeuille.dart';
import 'stockage.dart';
import 'valorisation.dart';

const nomFichierDonnees = 'garp-donnees.json.gz';
const nomFichierFiches = 'garp-fiches.json.gz';
const nomFichierInvestisseurs = 'garp-investisseurs.json.gz';

class Etat extends ChangeNotifier {
  final stockage = Stockage();

  Donnees? donnees;

  /// Détail des fiches, grands investisseurs et élus (null tant qu'ils ne sont pas lus).
  Complements? complements;
  List<Ligne> portefeuille = [];
  List<Suivie> watchlist = [];
  Profil profil = Profil();
  Map<String, String> theses = {};
  Map<String, dynamic> scenarios = {};
  List<Regle> regles = [];
  String? jeton;
  String depot = Stockage.depotParDefaut;
  bool enCours = false;
  String? erreur;

  /// Réglages et données personnelles lus (l'écran d'accueil peut s'afficher).
  bool pret = false;
  bool bienvenueVue = true;
  Map<String, String> correspondances = {};

  bool get configure => jeton != null && jeton!.isNotEmpty;

  /// Réglages de valorisation : ceux de la stratégie publiée, avec le rendement exigé du profil.
  ReglagesValorisation get reglagesValorisation =>
      (donnees?.valorisation ?? const ReglagesValorisation()).avec(rendementExige: profil.rendementExige);

  Future<File> _fichier(String nom) async => File('${(await getApplicationSupportDirectory()).path}/$nom');

  Future<List<int>?> _octets(String nom) async {
    final f = await _fichier(nom);
    return await f.exists() ? await f.readAsBytes() : null;
  }

  Future<void> _lireComplements() async {
    final fiches = await _octets(nomFichierFiches), investisseurs = await _octets(nomFichierInvestisseurs);
    if (fiches == null && investisseurs == null) return;
    try {
      complements = await Isolate.run(() => Complements.depuisOctets(fiches, investisseurs));
    } catch (_) {
      complements = null; // fichier abîmé : il sera retéléchargé
    }
    notifyListeners();
  }

  /// Au démarrage : réglages, données personnelles et derniers fichiers téléchargés.
  Future<void> demarrer() async {
    jeton = await stockage.jeton();
    depot = await stockage.depot();
    portefeuille = await stockage.portefeuille();
    watchlist = await stockage.watchlist();
    profil = await stockage.profil();
    theses = await stockage.theses();
    scenarios = await stockage.scenarios();
    regles = await stockage.regles();
    correspondances = await stockage.correspondances();
    // Un appareil déjà configuré avant l'écran d'accueil n'a pas à le revoir.
    bienvenueVue = await stockage.bienvenueVue() || configure;
    pret = true;
    notifyListeners();
    final octets = await _octets(nomFichierDonnees);
    if (octets != null) {
      try {
        donnees = await Isolate.run(() => Donnees.depuisOctets(octets));
      } catch (_) {
        donnees = null;
      }
      notifyListeners();
      await _lireComplements();
    }
    if (configure) await telechargerDonnees(siAnciennes: true);
  }

  /// Télécharge les données de la nuit (si `siAnciennes`, seulement quand le cache a plus de 12 heures).
  Future<void> telechargerDonnees({bool siAnciennes = false}) async {
    if (!configure || enCours) return;
    final cache = await _fichier(nomFichierDonnees);
    if (siAnciennes && await cache.exists() && await (await _fichier(nomFichierFiches)).exists()) {
      final age = DateTime.now().difference(await cache.lastModified());
      if (age.inHours < 12) return;
    }
    enCours = true;
    erreur = null;
    notifyListeners();
    try {
      final gh = GitHub(depot, jeton!);
      final release = await gh.release('donnees');
      final asset = release.asset((nom) => nom == nomFichierDonnees);
      if (asset == null) throw ErreurGitHub('Le fichier de données n\'est pas encore publié sur GitHub.');
      final octets = await gh.telecharger(asset);
      donnees = await Isolate.run(() => Donnees.depuisOctets(octets));
      await cache.parent.create(recursive: true);
      await cache.writeAsBytes(octets, flush: true);
      notifyListeners();
      // Fichiers complémentaires : absents d'une publication ancienne, l'application s'en passe.
      for (final nom in [nomFichierFiches, nomFichierInvestisseurs]) {
        final complement = release.asset((n) => n == nom);
        if (complement == null) continue;
        await (await _fichier(nom)).writeAsBytes(await gh.telecharger(complement), flush: true);
      }
      await _lireComplements();
    } on ErreurGitHub catch (e) {
      erreur = e.message;
    } on SocketException {
      erreur = 'Pas de connexion à Internet : les dernières données téléchargées restent affichées.';
    } catch (e) {
      erreur = 'Échec du téléchargement : $e';
    } finally {
      enCours = false;
      notifyListeners();
    }
  }

  Future<void> reglerAcces(String nouveauJeton, String nouveauDepot) async {
    await stockage.enregistrerJeton(nouveauJeton);
    await stockage.enregistrerDepot(nouveauDepot);
    jeton = nouveauJeton.trim();
    depot = nouveauDepot.trim();
    notifyListeners();
    await telechargerDonnees();
  }

  // ------------------------------------------------------------------ profil
  Future<void> reglerProfil(void Function(Profil p) modifier) async {
    modifier(profil);
    await stockage.enregistrerProfil(profil);
    notifyListeners();
  }

  // ------------------------------------------------------------------ watchlist
  Suivie? suivi(String ticker) {
    for (final s in watchlist) {
      if (s.ticker == ticker) return s;
    }
    return null;
  }

  bool suivie(String ticker) => suivi(ticker) != null;

  Future<void> basculerWatchlist(Valeur v) async {
    if (suivie(v.ticker)) {
      watchlist.removeWhere((s) => s.ticker == v.ticker);
    } else {
      watchlist.add(Suivie(v.ticker, _aujourdhui(), v.n('cours')));
    }
    await stockage.enregistrerWatchlist(watchlist);
    notifyListeners();
  }

  /// Enregistre un prix visé (la valeur entre dans la watchlist si elle n'y est pas) ; null le retire.
  Future<void> fixerPrixVise(Valeur v, double? prix, {String? objectif}) async {
    var s = suivi(v.ticker);
    if (s == null) {
      s = Suivie(v.ticker, _aujourdhui(), v.n('cours'));
      watchlist.add(s);
    }
    s.prixVise = prix;
    s.objectif = prix == null ? null : objectif;
    await stockage.enregistrerWatchlist(watchlist);
    notifyListeners();
  }

  /// Valeurs suivies dont le cours est passé sous le prix visé.
  List<(Suivie, Valeur)> get prixVisesAtteints => [
        for (final s in watchlist)
          if (donnees?.valeurs[s.ticker] case final v?)
            if (s.prixVise != null && (v.n('cours') ?? double.infinity) <= s.prixVise!) (s, v),
      ];

  String _aujourdhui() => DateTime.now().toIso8601String().substring(0, 10);

  // ------------------------------------------------------------------ portefeuille
  Ligne? ligne(String ticker) {
    for (final l in portefeuille) {
      if (l.ticker == ticker) return l;
    }
    return null;
  }

  double? poids(String ticker) => ligne(ticker)?.poids;

  Future<void> _enregistrerPortefeuille() async {
    portefeuille.sort((a, b) => b.poids.compareTo(a.poids));
    await stockage.enregistrerPortefeuille(portefeuille);
    notifyListeners();
  }

  Future<void> reglerPoids(String ticker, double? poids, {String? nom}) async {
    final ancienne = ligne(ticker);
    portefeuille.removeWhere((l) => l.ticker == ticker);
    if (poids != null && poids > 0) {
      portefeuille.add(Ligne(ticker, poids,
          nom: nom ?? ancienne?.nom, quantite: ancienne?.quantite, prixRevient: ancienne?.prixRevient));
    }
    await _enregistrerPortefeuille();
  }

  /// Nombre de titres détenus et prix de revient unitaire en euros d'une ligne.
  Future<void> reglerPosition(String ticker, double? quantite, double? prixRevient) async {
    final l = ligne(ticker);
    if (l == null) return;
    l.quantite = quantite != null && quantite > 0 ? quantite : null;
    l.prixRevient = prixRevient != null && prixRevient > 0 ? prixRevient : null;
    await _enregistrerPortefeuille();
  }

  /// Nom à afficher d'une ligne : celui des données, sinon le libellé importé, sinon l'identifiant.
  String nomLigne(Ligne l) => donnees?.valeurs[l.ticker]?.nom ?? l.nom ?? l.ticker;

  /// Lit un export de courtier, un tableau copié ou une liste « ticker ; poids », sans rien enregistrer.
  ResultatImport preparerImport(List<String> textes) {
    final lignes = <LigneImportee>[];
    for (final t in textes) {
      lignes.addAll(importer(t, donnees, correspondances: correspondances).lignes);
    }
    return ResultatImport(lignes, calculerPoids(lignes, donnees));
  }

  /// Remplace le portefeuille par les lignes vérifiées ; retient les correspondances pour le prochain import.
  Future<void> appliquerImport(ResultatImport r) async {
    final parId = <String, Ligne>{};
    for (final l in r.retenues) {
      if (l.poids <= 0) continue;
      final id = l.identifiant;
      final deja = parId[id];
      final quantite = (deja?.quantite ?? 0) + (l.quantite ?? 0);
      parId[id] = Ligne(id, (deja?.poids ?? 0) + l.poids,
          nom: l.ticker == null ? l.libelle : null, quantite: quantite > 0 ? quantite : null);
      correspondances[l.cle] = l.ticker ?? '';
    }
    portefeuille = parId.values.toList();
    await stockage.enregistrerCorrespondances(correspondances);
    await _enregistrerPortefeuille();
  }

  /// Remplace les poids cibles par ceux d'un portefeuille construit par des règles (fractions de 1).
  Future<void> adopterPortefeuille(Map<String, double> poids) async {
    portefeuille = [
      for (final e in poids.entries)
        Ligne(e.key, e.value * 100, quantite: ligne(e.key)?.quantite, prixRevient: ligne(e.key)?.prixRevient),
    ];
    await _enregistrerPortefeuille();
  }

  /// Le portefeuille en texte « ticker;poids », à coller dans G.A.R.P sur un autre appareil ou dans un tableur.
  String portefeuilleEnTexte() => [
        'ticker;nom;poids;quantite',
        for (final l in portefeuille)
          '${l.ticker};${nomLigne(l).replaceAll(';', ',')};${nombre(l.poids, 2)};'
              '${l.quantite == null ? '' : nombre(l.quantite, 4)}',
      ].join('\n');

  Future<void> viderPortefeuille() async {
    portefeuille = [];
    await _enregistrerPortefeuille();
  }

  // ------------------------------------------------------------------ notes, scénarios, règles de vente
  Future<void> enregistrerThese(String ticker, String texte) async {
    if (texte.trim().isEmpty) {
      theses.remove(ticker);
    } else {
      theses[ticker] = texte.trim();
    }
    await stockage.enregistrerTheses(theses);
    notifyListeners();
  }

  /// Scénarios à 5 ans d'une valeur, datés, avec le cours du jour.
  Future<void> enregistrerScenarios(Valeur v, Map<String, Hypotheses> hypotheses) async {
    scenarios[v.ticker] = {
      'date': _aujourdhui(),
      'cours': v.n('cours'),
      'hypotheses': {for (final e in hypotheses.entries) e.key: e.value.versJson()},
    };
    await stockage.enregistrerScenarios(scenarios);
    notifyListeners();
  }

  Future<void> ajouterRegle(Regle r) async {
    regles.add(r);
    await stockage.enregistrerRegles(regles);
    notifyListeners();
  }

  Future<void> retirerRegle(Regle r) async {
    regles.remove(r);
    await stockage.enregistrerRegles(regles);
    notifyListeners();
  }

  Future<void> terminerBienvenue() async {
    bienvenueVue = true;
    await stockage.marquerBienvenueVue();
    notifyListeners();
  }

  Future<void> toutEffacer() async {
    await stockage.toutEffacer();
    portefeuille = [];
    watchlist = [];
    profil = Profil();
    theses = {};
    scenarios = {};
    regles = [];
    correspondances = {};
    jeton = null;
    bienvenueVue = false;
    notifyListeners();
  }
}
