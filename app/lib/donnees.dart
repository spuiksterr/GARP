/// Données de marché publiées chaque nuit par GitHub (pf/export_app.py) : valeurs, cours hebdomadaires, changes,
/// indice de référence, rangs, méthodes, réglages de la stratégie.
library;

import 'dart:convert';
import 'dart:io';

import 'formats.dart';
import 'methodes.dart';
import 'valorisation.dart';

class Valeur {
  Valeur(this.donnees);

  final Map<String, dynamic> donnees;

  String get ticker => donnees['ticker'] as String;
  String get nom => (donnees['nom'] as String?) ?? ticker;
  String get secteur => (donnees['secteur'] as String?) ?? 'Autre';
  String get enveloppe => (donnees['enveloppe'] as String?) ?? '';
  String get pays => (donnees['pays'] as String?) ?? '';
  String get statut => (donnees['statut'] as String?) ?? '';
  String get devise => (donnees['devise'] as String?) ?? '';
  String? get profil => donnees['profil'] as String?;
  String? get motifsExclusion => donnees['motifs_exclusion'] as String?;
  String? get alertes => donnees['alertes'] as String?;
  bool get eligible => statut == 'Éligible';
  bool get fonds => statut == 'Fonds' || donnees['fonds'] == true;
  bool get financiere => donnees['financiere'] == true;
  bool get holding => donnees['holding'] == true;
  bool get americaine => !ticker.contains('.');
  int? get rang => nombreOuNul(donnees['rang'])?.round();

  /// Valeur numérique d'un indicateur (null si absent).
  double? n(String cle) => nombreOuNul(donnees[cle]);

  /// Texte d'un indicateur (null si absent).
  String? t(String cle) => donnees[cle]?.toString();
}

/// Numéro de la semaine d'une date (semaines entières depuis le vendredi 2 janvier 1970).
int semaineDe(DateTime d) => DateTime.utc(d.year, d.month, d.day).difference(DateTime.utc(1970, 1, 2)).inDays ~/ 7;

DateTime dateDeSemaine(int semaine) => DateTime.utc(1970, 1, 2).add(Duration(days: 7 * semaine));

/// Série hebdomadaire : une valeur par vendredi à partir de `debut` (null : pas de cotation cette semaine).
class Cours {
  Cours(this.debut, this.valeurs);

  static Cours? depuisJson(Map<String, dynamic>? c) {
    if (c == null || c['debut'] == null || c['c'] == null) return null;
    return Cours(DateTime.parse(c['debut'] as String), [for (final v in (c['c'] as List)) nombreOuNul(v)]);
  }

  final DateTime debut;
  final List<double?> valeurs;

  int get premiereSemaine => semaineDe(debut);

  /// Valeur de la semaine `semaine` (numéro absolu), null hors de la série.
  double? a(int semaine) {
    final i = semaine - premiereSemaine;
    return i < 0 || i >= valeurs.length ? null : valeurs[i];
  }

  /// Points (date, cours) des `semaines` dernières semaines (toutes si null).
  List<(DateTime, double)> points([int? semaines]) {
    final depart = semaines == null ? 0 : (valeurs.length - semaines).clamp(0, valeurs.length);
    final out = <(DateTime, double)>[];
    for (var i = depart; i < valeurs.length; i++) {
      final v = valeurs[i];
      if (v != null) out.add((debut.add(Duration(days: 7 * i)), v));
    }
    return out;
  }
}

/// Seuils de concentration proposés par la stratégie (suivi.garde_fous).
class GardeFous {
  const GardeFous({
    this.ligneMax = 0.25,
    this.troisPremieresMax = 0.60,
    this.secteurMax = 0.40,
    this.correlationMax = 0.5,
  });

  factory GardeFous.depuisJson(Map<String, dynamic>? j) => GardeFous(
        ligneMax: (j?['ligne_max'] as num?)?.toDouble() ?? 0.25,
        troisPremieresMax: (j?['trois_premieres_max'] as num?)?.toDouble() ?? 0.60,
        secteurMax: (j?['secteur_max'] as num?)?.toDouble() ?? 0.40,
        correlationMax: (j?['correlation_moyenne_max'] as num?)?.toDouble() ?? 0.5,
      );

  final double ligneMax;
  final double troisPremieresMax;
  final double secteurMax;
  final double correlationMax;
}

class Donnees {
  Donnees._(this.meta, this.valeurs, this._cours, this._rangs, this.methodes, this.criteres, this._changes,
      this.reference, this.tickerReference, this.valorisation, this.gardeFous, this.construction);

  final Map<String, dynamic> meta;
  final Map<String, Valeur> valeurs;
  final Map<String, dynamic> _cours;
  final Map<String, dynamic> _rangs;

  /// Méthodes d'évaluation publiées avec les données (au moins le score composite).
  final List<Methode> methodes;

  /// Les six critères de qualité et leurs seuils (vide avec un fichier ancien).
  final List<Critere> criteres;

  /// Euros pour une unité de chaque devise, semaine par semaine.
  final Map<String, Cours> _changes;

  /// Indice de référence (ETF monde, en euros) et son ticker.
  final Cours? reference;
  final String tickerReference;

  /// Réglages de la stratégie publiés avec les données.
  final ReglagesValorisation valorisation;
  final GardeFous gardeFous;
  final Map<String, dynamic> construction;

  final _notes = <String, Map<String, double>>{};
  final _classements = <String, List<Valeur>>{};
  final _coursEur = <String, Cours?>{};

  String? get donneesAu => meta['donnees_au'] as String?;
  String? get genereLe => meta['genere_le'] as String?;
  int get nbEligibles => (meta['nb_eligibles'] as num?)?.toInt() ?? 0;

  /// Lit le fichier compressé publié par GitHub (à appeler hors du fil principal : quelques Mo de JSON).
  static Donnees depuisOctets(List<int> octetsGzip) {
    final json = jsonDecode(utf8.decode(gzip.decode(octetsGzip))) as Map<String, dynamic>;
    final valeurs = <String, Valeur>{
      for (final v in (json['valeurs'] as List)) (v['ticker'] as String): Valeur(v as Map<String, dynamic>),
    };
    final strategie = (json['strategie'] as Map<String, dynamic>?) ?? <String, dynamic>{};
    final reference = (json['reference'] as Map<String, dynamic>?) ?? <String, dynamic>{};
    final changes = <String, Cours>{};
    ((json['changes'] as Map<String, dynamic>?) ?? <String, dynamic>{}).forEach((devise, c) {
      final serie = Cours.depuisJson(c as Map<String, dynamic>);
      if (serie != null) changes[devise] = serie;
    });
    return Donnees._(
      {for (final e in json.entries) if (e.value is! List && e.value is! Map) e.key: e.value},
      valeurs,
      (json['cours'] as Map<String, dynamic>?) ?? {},
      (json['rangs'] as Map<String, dynamic>?) ?? {},
      [
        for (final m in (json['methodes'] as List?) ?? const []) Methode.depuisJson(m as Map<String, dynamic>),
      ].ifEmpty(const [composite]),
      [for (final c in (json['criteres'] as List?) ?? const []) Critere.depuisJson(c as Map<String, dynamic>)],
      changes,
      Cours.depuisJson(reference),
      (reference['ticker'] as String?) ?? 'IWDA.AS',
      ReglagesValorisation.depuisJson(strategie['valorisation'] as Map<String, dynamic>?),
      GardeFous.depuisJson(strategie['garde_fous'] as Map<String, dynamic>?),
      (strategie['construction'] as Map<String, dynamic>?) ?? <String, dynamic>{},
    );
  }

  /// Cours hebdomadaires dans la devise de cotation.
  Cours? cours(String ticker) => Cours.depuisJson(_cours[ticker] as Map<String, dynamic>?);

  /// Cours hebdomadaires convertis en euros au change de chaque semaine (calculés une fois par valeur).
  Cours? coursEur(String ticker) => _coursEur.putIfAbsent(ticker, () {
        final c = cours(ticker);
        if (c == null) return null;
        final devise = (valeurs[ticker]?.devise ?? 'EUR').toUpperCase();
        final code = devise.length >= 3 ? devise.substring(0, 3) : devise;
        if (code == 'EUR') return c;
        final change = _changes[code];
        if (change == null) return null;
        final debut = c.premiereSemaine;
        final out = <double?>[];
        double? taux;
        for (var i = 0; i < c.valeurs.length; i++) {
          taux = change.a(debut + i) ?? taux;
          final v = c.valeurs[i];
          out.add(v == null || taux == null ? null : v * taux);
        }
        return Cours(c.debut, out);
      });

  /// Historique du rang : [(date, rang)].
  List<(DateTime, int)> rangs(String ticker) {
    final r = _rangs[ticker] as List?;
    if (r == null) return [];
    return [for (final p in r) (DateTime.parse(p[0] as String), (p[1] as num).toInt())];
  }

  Methode methode(String id) => methodes.firstWhere((m) => m.id == id, orElse: () => methodes.first);

  /// Note de 0 à 100 de chaque valeur selon la méthode (calculée une fois).
  Map<String, double> notes(Methode m) => _notes.putIfAbsent(m.id, () => notesSelon(valeurs.values, m));

  /// Toutes les valeurs, de la meilleure note à la moins bonne selon la méthode (sans note : à la fin).
  List<Valeur> classees(Methode m) => _classements.putIfAbsent(m.id, () {
        final n = notes(m);
        return valeurs.values.toList()..sort((a, b) => (n[b.ticker] ?? -1).compareTo(n[a.ticker] ?? -1));
      });

  /// Rang d'une valeur éligible parmi les éligibles, selon la méthode (null si exclue ou sans note).
  int? rangSelon(Methode m, String ticker) {
    final n = notes(m);
    if (n[ticker] == null) return null;
    var rang = 0;
    for (final v in classees(m)) {
      if (!v.eligible || n[v.ticker] == null) continue;
      rang++;
      if (v.ticker == ticker) return rang;
    }
    return null;
  }

  List<Valeur> get triees {
    final l = valeurs.values.toList();
    l.sort((a, b) => (a.rang ?? 1 << 30).compareTo(b.rang ?? 1 << 30));
    return l;
  }
}

/// Fichiers complémentaires (pf/export_fiches.py) : détail des fiches, grands investisseurs et élus.
class Complements {
  Complements(this.fiches, this.investisseurs);

  /// {ticker: {h: historique, r: repères des multiples, desc, d: dirigeants, v: ventilation, src}}.
  final Map<String, dynamic> fiches;

  /// {investisseurs, partages, elus, operations, maj_13f, maj_elus}.
  final Map<String, dynamic> investisseurs;

  static Map<String, dynamic> lire(List<int>? octetsGzip) => octetsGzip == null
      ? <String, dynamic>{}
      : jsonDecode(utf8.decode(gzip.decode(octetsGzip))) as Map<String, dynamic>;

  static Complements depuisOctets(List<int>? fiches, List<int>? investisseurs) => Complements(
        (lire(fiches)['fiches'] as Map<String, dynamic>?) ?? <String, dynamic>{},
        lire(investisseurs),
      );

  Map<String, dynamic>? fiche(String ticker) => fiches[ticker] as Map<String, dynamic>?;

  List<Map<String, dynamic>> get listeInvestisseurs =>
      [for (final i in (investisseurs['investisseurs'] as List?) ?? const []) i as Map<String, dynamic>];

  /// Investisseurs suivis qui détiennent le titre à leur dernier trimestre déclaré.
  List<String> detenteurs(String ticker) => [
        for (final i in listeInvestisseurs)
          if ((i['lignes'] as List).any((l) => l['ticker'] == ticker && ((l['poids'] as num?) ?? 0) > 0))
            i['investisseur'] as String,
      ];
}
