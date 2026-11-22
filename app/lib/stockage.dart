/// Ce qui reste dans l'appareil : le jeton GitHub (stockage chiffré), le portefeuille, la watchlist, le profil,
/// les notes de thèse, les scénarios et les règles de vente. Rien de cela n'est envoyé nulle part.
library;

import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

class Ligne {
  Ligne(this.ticker, this.poids, {this.nom, this.quantite, this.prixRevient});

  /// Ticker des données, ou ISIN / libellé pour une ligne hors des données (fonds, or, valeur non suivie).
  final String ticker;

  /// Poids cible, en %.
  double poids;

  /// Libellé d'une ligne hors des données, tel qu'importé.
  final String? nom;

  /// Nombre de titres détenus et prix de revient unitaire en euros (facultatifs : suivi et apport du mois).
  double? quantite;
  double? prixRevient;

  Map<String, dynamic> versJson() => {
        'ticker': ticker,
        'poids': poids,
        'nom': ?nom,
        'quantite': ?quantite,
        'prix_revient': ?prixRevient,
      };

  static Ligne depuisJson(Map<String, dynamic> j) => Ligne(
        j['ticker'] as String,
        (j['poids'] as num).toDouble(),
        nom: j['nom'] as String?,
        quantite: (j['quantite'] as num?)?.toDouble(),
        prixRevient: (j['prix_revient'] as num?)?.toDouble(),
      );
}

class Suivie {
  Suivie(this.ticker, this.ajouteLe, this.coursAjout, {this.prixVise, this.objectif});

  final String ticker;
  final String ajouteLe; // AAAA-MM-JJ
  final double? coursAjout;

  /// Prix visé (devise de cotation) et ce qui le justifie (« PER 18 », « prix juste à 10 % »).
  double? prixVise;
  String? objectif;

  Map<String, dynamic> versJson() => {
        'ticker': ticker,
        'ajoute_le': ajouteLe,
        'cours_ajout': coursAjout,
        'prix_vise': ?prixVise,
        'objectif': ?objectif,
      };

  static Suivie depuisJson(Map<String, dynamic> j) => Suivie(
        j['ticker'] as String,
        j['ajoute_le'] as String,
        (j['cours_ajout'] as num?)?.toDouble(),
        prixVise: (j['prix_vise'] as num?)?.toDouble(),
        objectif: j['objectif'] as String?,
      );
}

/// Condition de vente chiffrée : un indicateur, une comparaison, un seuil (en unités d'affichage : % ou multiple).
class Regle {
  Regle(this.ticker, this.indicateur, this.operateur, this.seuil);

  final String ticker;
  final String indicateur;
  final String operateur; // '<', '<=', '>', '>='
  final double seuil;

  Map<String, dynamic> versJson() =>
      {'ticker': ticker, 'indicateur': indicateur, 'operateur': operateur, 'seuil': seuil};

  static Regle depuisJson(Map<String, dynamic> j) => Regle(
      j['ticker'] as String, j['indicateur'] as String, j['operateur'] as String, (j['seuil'] as num).toDouble());
}

/// Profil de l'investisseur : sa façon d'évaluer les actions, son exigence de prix, ses enveloppes et ses limites.
class Profil {
  Profil({
    this.prenom = '',
    this.methode = 'composite',
    this.enveloppe = 'Toutes',
    this.ligneMax = 0.25,
    this.troisPremieresMax = 0.60,
    this.secteurMax = 0.40,
    this.rendementExige,
    this.margeSecurite = 0.20,
    this.criteresMin = 0,
    this.exclureMoatFaible = false,
    this.capitalisationMin = 0,
    Set<String>? secteursExclus,
    this.apportMensuel = 0,
    this.ordreMin = 300,
  }) : secteursExclus = secteursExclus ?? {};

  /// Prénom ou pseudo affiché sur l'accueil (facultatif).
  String prenom;

  /// Méthode d'évaluation qui classe le screener (identifiant de pf/portfolio.py : composite, buffett…).
  String methode;

  /// Enveloppe où l'on investit : « Toutes », « PEA » ou « CTO ».
  String enveloppe;

  /// Garde-fous de concentration.
  double ligneMax;
  double troisPremieresMax;
  double secteurMax;

  /// Rendement annuel exigé pour le prix juste (null : celui de la stratégie publiée, 9 %).
  double? rendementExige;

  /// Marge de sécurité demandée sous le prix juste avant d'acheter.
  double margeSecurite;

  /// Exigences de qualité de la recherche personnalisée.
  int criteresMin;
  bool exclureMoatFaible;

  /// Capitalisation minimale, en milliards d'euros.
  double capitalisationMin;
  Set<String> secteursExclus;

  /// Apport mensuel habituel et montant minimal d'un ordre, en euros.
  double apportMensuel;
  double ordreMin;

  Map<String, dynamic> versJson() => {
        'prenom': prenom,
        'methode': methode,
        'enveloppe': enveloppe,
        'ligne_max': ligneMax,
        'trois_premieres_max': troisPremieresMax,
        'secteur_max': secteurMax,
        'rendement_exige': ?rendementExige,
        'marge_securite': margeSecurite,
        'criteres_min': criteresMin,
        'exclure_moat_faible': exclureMoatFaible,
        'capitalisation_min': capitalisationMin,
        'secteurs_exclus': secteursExclus.toList(),
        'apport_mensuel': apportMensuel,
        'ordre_min': ordreMin,
      };

  static Profil depuisJson(Map<String, dynamic> j) {
    final d = Profil();
    double nombre(String cle, double defaut) => (j[cle] as num?)?.toDouble() ?? defaut;
    return Profil(
      prenom: (j['prenom'] as String?) ?? d.prenom,
      methode: (j['methode'] as String?) ?? d.methode,
      enveloppe: (j['enveloppe'] as String?) ?? d.enveloppe,
      ligneMax: nombre('ligne_max', d.ligneMax),
      troisPremieresMax: nombre('trois_premieres_max', d.troisPremieresMax),
      secteurMax: nombre('secteur_max', d.secteurMax),
      rendementExige: (j['rendement_exige'] as num?)?.toDouble(),
      margeSecurite: nombre('marge_securite', d.margeSecurite),
      criteresMin: (j['criteres_min'] as num?)?.toInt() ?? d.criteresMin,
      exclureMoatFaible: (j['exclure_moat_faible'] as bool?) ?? d.exclureMoatFaible,
      capitalisationMin: nombre('capitalisation_min', d.capitalisationMin),
      secteursExclus: {for (final s in (j['secteurs_exclus'] as List?) ?? const []) s as String},
      apportMensuel: nombre('apport_mensuel', d.apportMensuel),
      ordreMin: nombre('ordre_min', d.ordreMin),
    );
  }
}

class Stockage {
  static const _securise = FlutterSecureStorage();
  static const depotParDefaut = 'spuiksterr/GARP';

  /// Adresses enregistrées par les versions d'avant le dépôt public, remplacées par celle par défaut.
  static const _anciensDepots = {'spuiksterr/Climax', 'spuiksterr/Climax-public'};

  /// Clés des données personnelles (hors jeton), effacées par « Tout effacer ».
  static const _cles = [
    'portefeuille', 'watchlist', 'correspondances', 'bienvenue_vue', 'profil', 'theses', 'scenarios', 'regles',
    'actualites_vues',
  ];

  Future<String?> jeton() => _securise.read(key: 'jeton_github');

  Future<void> enregistrerJeton(String jeton) => _securise.write(key: 'jeton_github', value: jeton.trim());

  Future<String> depot() async {
    final enregistre = (await SharedPreferences.getInstance()).getString('depot');
    return enregistre == null || _anciensDepots.contains(enregistre) ? depotParDefaut : enregistre;
  }

  Future<void> enregistrerDepot(String depot) async =>
      (await SharedPreferences.getInstance()).setString('depot', depot.trim());

  Future<Object?> _lire(String cle) async {
    final texte = (await SharedPreferences.getInstance()).getString(cle);
    return texte == null ? null : jsonDecode(texte);
  }

  Future<void> _ecrire(String cle, Object valeur) async =>
      (await SharedPreferences.getInstance()).setString(cle, jsonEncode(valeur));

  Future<List<Ligne>> portefeuille() async =>
      [for (final j in (await _lire('portefeuille') as List?) ?? const []) Ligne.depuisJson(j as Map<String, dynamic>)];

  Future<void> enregistrerPortefeuille(List<Ligne> lignes) =>
      _ecrire('portefeuille', [for (final l in lignes) l.versJson()]);

  Future<List<Suivie>> watchlist() async =>
      [for (final j in (await _lire('watchlist') as List?) ?? const []) Suivie.depuisJson(j as Map<String, dynamic>)];

  Future<void> enregistrerWatchlist(List<Suivie> liste) =>
      _ecrire('watchlist', [for (final s in liste) s.versJson()]);

  /// Correspondances retenues lors des imports : ISIN ou nom du courtier -> ticker ('' : hors des données).
  Future<Map<String, String>> correspondances() async =>
      ((await _lire('correspondances') as Map<String, dynamic>?) ?? {}).map((k, v) => MapEntry(k, v as String));

  Future<void> enregistrerCorrespondances(Map<String, String> c) => _ecrire('correspondances', c);

  Future<Profil> profil() async {
    final j = await _lire('profil') as Map<String, dynamic>?;
    return j == null ? Profil() : Profil.depuisJson(j);
  }

  Future<void> enregistrerProfil(Profil p) => _ecrire('profil', p.versJson());

  /// Notes de thèse par valeur : pourquoi je la détiens ou la suis, ce qui me ferait vendre.
  Future<Map<String, String>> theses() async =>
      ((await _lire('theses') as Map<String, dynamic>?) ?? {}).map((k, v) => MapEntry(k, v as String));

  Future<void> enregistrerTheses(Map<String, String> t) => _ecrire('theses', t);

  /// Scénarios à 5 ans enregistrés : {ticker: {date, cours, hypotheses: {nom: {croissance, marge, multiple}}}}.
  Future<Map<String, dynamic>> scenarios() async => (await _lire('scenarios') as Map<String, dynamic>?) ?? {};

  Future<void> enregistrerScenarios(Map<String, dynamic> s) => _ecrire('scenarios', s);

  Future<List<Regle>> regles() async =>
      [for (final j in (await _lire('regles') as List?) ?? const []) Regle.depuisJson(j as Map<String, dynamic>)];

  Future<void> enregistrerRegles(List<Regle> r) => _ecrire('regles', [for (final x in r) x.versJson()]);

  Future<bool> bienvenueVue() async => (await SharedPreferences.getInstance()).getBool('bienvenue_vue') ?? false;

  Future<void> marquerBienvenueVue() async => (await SharedPreferences.getInstance()).setBool('bienvenue_vue', true);

  /// Efface toutes les données personnelles et le jeton de cet appareil.
  Future<void> toutEffacer() async {
    final p = await SharedPreferences.getInstance();
    for (final cle in _cles) {
      await p.remove(cle);
    }
    await _securise.delete(key: 'jeton_github');
  }
}
