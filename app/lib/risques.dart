/// Risques et backtest du portefeuille, comme pf/risques.py, pf/simulation.py et pf/backtest.py, mais sur les
/// cours hebdomadaires en euros de l'export (l'application de bureau travaille en quotidien : les chiffres sont
/// proches, pas identiques). Les poids sont ceux d'aujourd'hui, appliqués au passé.
library;

import 'dart:math' as math;

import 'donnees.dart';

const semainesParAn = 52;

/// Rendements hebdomadaires {semaine: rendement} d'une série ; un trou de cotation est enjambé.
Map<int, double> rendementsDe(Cours? c, {int? depuis}) {
  final out = <int, double>{};
  if (c == null) return out;
  double? precedent;
  final debut = c.premiereSemaine;
  for (var i = 0; i < c.valeurs.length; i++) {
    final v = c.valeurs[i];
    if (v == null || v <= 0) continue;
    if (precedent != null && (depuis == null || debut + i >= depuis)) out[debut + i] = v / precedent - 1;
    precedent = v;
  }
  return out;
}

double _moyenne(Iterable<double> x) => x.isEmpty ? double.nan : x.reduce((a, b) => a + b) / x.length;

double _variance(List<double> x) {
  if (x.length < 2) return double.nan;
  final m = _moyenne(x);
  return x.fold<double>(0, (s, v) => s + (v - m) * (v - m)) / (x.length - 1);
}

/// Covariance de deux séries sur leurs semaines communes (NaN s'il y en a moins de 20).
double covariance(Map<int, double> a, Map<int, double> b) {
  final communes = a.keys.where(b.containsKey).toList();
  if (communes.length < 20) return double.nan;
  final ma = _moyenne(communes.map((s) => a[s]!)), mb = _moyenne(communes.map((s) => b[s]!));
  return communes.fold<double>(0, (s, k) => s + (a[k]! - ma) * (b[k]! - mb)) / (communes.length - 1);
}

double correlation(Map<int, double> a, Map<int, double> b) {
  final communes = a.keys.where(b.containsKey).toList();
  if (communes.length < 20) return double.nan;
  final va = _variance([for (final s in communes) a[s]!]), vb = _variance([for (final s in communes) b[s]!]);
  final c = covariance(a, b);
  return va > 0 && vb > 0 ? c / math.sqrt(va * vb) : double.nan;
}

/// Statistiques d'une suite de rendements hebdomadaires.
class Stats {
  Stats(Map<int, double> r) {
    final semaines = r.keys.toList()..sort();
    if (semaines.isEmpty) return;
    var valeur = 1.0, sommet = 1.0, creux = 0.0;
    final glissant = <double>[];
    for (final s in semaines) {
      valeur *= 1 + r[s]!;
      sommet = math.max(sommet, valeur);
      creux = math.min(creux, valeur / sommet - 1);
      courbe.add((dateDeSemaine(s), valeur * 100));
      // Pire période de quatre semaines : l'équivalent du « pire mois ».
      glissant.add(valeur);
      if (glissant.length > 4) {
        final perf = valeur / glissant[glissant.length - 5] - 1;
        if (pireMois == null || perf < pireMois!) {
          pireMois = perf;
          finPireMois = dateDeSemaine(s);
        }
      }
    }
    final annees = semaines.length / semainesParAn;
    rendementTotal = valeur - 1;
    rendementAnnuel = annees > 0 ? math.pow(valeur, 1 / annees).toDouble() - 1 : null;
    final v = _variance([for (final s in semaines) r[s]!]);
    volatilite = v.isNaN ? null : math.sqrt(v * semainesParAn);
    perteMaximale = creux;
  }

  /// Valeur d'un placement de 100, semaine après semaine.
  final courbe = <(DateTime, double)>[];
  double? rendementTotal;
  double? rendementAnnuel;
  double? volatilite;
  double? perteMaximale;
  double? pireMois;
  DateTime? finPireMois;
}

/// Mesures de risque d'un portefeuille de poids `poids` (somme 1) sur `annees` années.
class Risques {
  Risques(this.d, Map<String, double> poids, {double annees = 3, Set<String> or = const {}}) : poids = _normaliser(poids) {
    final derniere = d.reference == null
        ? semaineDe(DateTime.now())
        : d.reference!.premiereSemaine + d.reference!.valeurs.length - 1;
    final depuis = derniere - (annees * semainesParAn).round();
    indice = rendementsDe(d.reference, depuis: depuis);
    for (final t in this.poids.keys) {
      final r = rendementsDe(d.coursEur(t), depuis: depuis);
      if (r.length >= 20) lignes[t] = r;
    }
    // Portefeuille aux poids d'aujourd'hui : une ligne sans cours une semaine donnée compte pour zéro.
    final couvert = lignes.keys.fold<double>(0, (s, t) => s + this.poids[t]!);
    if (couvert > 0) {
      final semaines = <int>{for (final r in lignes.values) ...r.keys};
      for (final s in semaines) {
        portefeuille[s] = lignes.entries.fold<double>(0, (x, e) => x + this.poids[e.key]! / couvert * (e.value[s] ?? 0));
      }
    }
    partCouverte = couvert;
    final varIndice = _variance(indice.values.toList());
    for (final e in lignes.entries) {
      final c = covariance(e.value, indice);
      if (!c.isNaN && varIndice > 0) betas[e.key] = c / varIndice;
    }
    _or = or;
  }

  final Donnees d;
  final Map<String, double> poids;
  late final Set<String> _or;

  /// Rendements hebdomadaires en euros : indice, lignes connues, portefeuille.
  late final Map<int, double> indice;
  final lignes = <String, Map<int, double>>{};
  final portefeuille = <int, double>{};
  final betas = <String, double>{};

  /// Part du portefeuille dont on connaît les cours (les fonds et lignes hors des données n'en ont pas).
  double partCouverte = 0;

  static Map<String, double> _normaliser(Map<String, double> p) {
    final total = p.values.fold<double>(0, (s, v) => s + v);
    return total <= 0 ? {} : {for (final e in p.entries) e.key: e.value / total};
  }

  List<MapEntry<String, double>> get _tries => poids.entries.toList()..sort((a, b) => b.value.compareTo(a.value));

  double get plusGrosse => _tries.isEmpty ? 0 : _tries.first.value;
  String? get nomPlusGrosse => _tries.isEmpty ? null : _tries.first.key;
  double get troisPremieres => _tries.take(3).fold<double>(0, (s, e) => s + e.value);

  /// Nombre de lignes de même poids qui donneraient la même concentration (1 / somme des carrés).
  double get nombreEffectif {
    final s = poids.values.fold<double>(0, (x, v) => x + v * v);
    return s > 0 ? 1 / s : 0;
  }

  Stats get stats => Stats(portefeuille);
  Stats get statsIndice => Stats(indice);

  /// Moyenne des corrélations entre les lignes, deux à deux (null avec moins de deux lignes connues).
  double? get correlationMoyenne {
    final t = lignes.keys.toList();
    final c = <double>[];
    for (var i = 0; i < t.length; i++) {
      for (var j = i + 1; j < t.length; j++) {
        final x = correlation(lignes[t[i]]!, lignes[t[j]]!);
        if (!x.isNaN) c.add(x);
      }
    }
    return c.isEmpty ? null : _moyenne(c);
  }

  /// Corrélation de `ticker` avec chaque autre ligne, de la plus forte à la plus faible.
  List<(String, double)> correlationsAvec(String ticker) {
    final r = lignes[ticker] ?? rendementsDe(d.coursEur(ticker));
    final out = [
      for (final e in lignes.entries)
        if (e.key != ticker) (e.key, correlation(r, e.value)),
    ].where((x) => !x.$2.isNaN).toList();
    return out..sort((a, b) => b.$2.compareTo(a.$2));
  }

  String _devise(String ticker) {
    final dv = (d.valeurs[ticker]?.devise ?? 'EUR').toUpperCase();
    return dv.length >= 3 ? dv.substring(0, 3) : dv;
  }

  /// Poids par devise de cotation (les lignes hors des données comptent en euros).
  Map<String, double> get devises {
    final out = <String, double>{};
    poids.forEach((t, w) => out[_devise(t)] = (out[_devise(t)] ?? 0) + w);
    final tri = out.entries.toList()..sort((a, b) => b.value.compareTo(a.value));
    return {for (final e in tri) e.key: e.value};
  }

  /// Chocs simples : (scénario, perte estimée, ligne la plus touchée, sa contribution).
  List<(String, double, String?, double?)> get scenarios {
    final out = <(String, double, String?, double?)>[];
    void ajouter(String nom, Map<String, double> effets) {
      if (effets.values.every((x) => x == 0)) return;
      final pire = effets.entries.reduce((a, b) => a.value <= b.value ? a : b);
      out.add((nom, effets.values.fold<double>(0, (s, x) => s + x), pire.value < 0 ? pire.key : null,
          pire.value < 0 ? pire.value : null));
    }

    // Chaque ligne suit l'indice selon son bêta (1 quand il est inconnu).
    ajouter('Marché mondial -30 %', {for (final e in poids.entries) e.key: e.value * (betas[e.key] ?? 1.0) * -0.30});
    ajouter('Dollar -10 % face à l\'euro',
        {for (final e in poids.entries) e.key: _devise(e.key) == 'USD' ? -0.10 * e.value : 0.0});
    ajouter('Or -20 %', {for (final e in poids.entries) e.key: _or.contains(e.key) ? -0.20 * e.value : 0.0});
    return out;
  }
}

/// Poids après un changement : `ticker` à `poids` (0 : retrait), les autres lignes réduites en proportion.
Map<String, double> nouveauxPoids(Map<String, double> actuels, String ticker, double poids) {
  final total = actuels.values.fold<double>(0, (s, v) => s + v);
  final autres = {for (final e in actuels.entries) if (e.key != ticker) e.key: e.value / total};
  final somme = autres.values.fold<double>(0, (s, v) => s + v);
  if (somme <= 0) return {ticker: 1.0};
  final p = poids.clamp(0.0, 1.0).toDouble();
  return {
    for (final e in autres.entries) e.key: e.value / somme * (1 - p),
    if (p > 0) ticker: p,
  };
}
