/// Construction d'un portefeuille par des règles, comme pf/portfolio.py (`select`, `weight`,
/// `build_quant_portfolio`) : les meilleures notes éligibles selon une méthode, un plancher de qualité, des
/// plafonds par ligne, par secteur et pour les secteurs cycliques. La pondération « variance minimale » de
/// l'application de bureau (optimiseur) n'est pas reprise.
library;

import 'dart:math' as math;

import 'donnees.dart';
import 'methodes.dart';

/// Secteurs dont les résultats suivent le cycle : au sommet, leurs multiples paraissent bas.
const cycliques = {'Infrastructures & Énergie', 'Matériaux & Chimie', 'Banques'};

class ReglagesConstruction {
  ReglagesConstruction({
    this.nbLignes = 22,
    this.poidsMax = 0.08,
    this.poidsMin = 0.02,
    this.secteurMax = 0.25,
    this.maxParSecteur = 5,
    this.ponderation = 'score_vol',
    this.partPea,
    this.criteresMin = 4,
    this.exclureMoatFaible = true,
    this.cycliquesMax = 0.25,
    this.secteursExclus = const {},
    this.exclus = const {},
  });

  factory ReglagesConstruction.depuisJson(Map<String, dynamic> j) => ReglagesConstruction(
        nbLignes: (j['nb_lignes'] as num?)?.toInt() ?? 22,
        poidsMax: (j['poids_max'] as num?)?.toDouble() ?? 0.08,
        poidsMin: (j['poids_min'] as num?)?.toDouble() ?? 0.02,
        secteurMax: (j['secteur_max'] as num?)?.toDouble() ?? 0.25,
        maxParSecteur: (j['max_par_secteur'] as num?)?.toInt() ?? 5,
        ponderation: j['methode'] == 'egal' ? 'egal' : 'score_vol',
        partPea: (j['part_pea'] as num?)?.toDouble(),
        criteresMin: (j['criteres_min'] as num?)?.toInt() ?? 4,
        exclureMoatFaible: (j['exclure_moat_faible'] as bool?) ?? true,
        cycliquesMax: (j['cycliques_max'] as num?)?.toDouble() ?? 0.25,
      );

  int nbLignes;
  double poidsMax;
  double poidsMin;
  double secteurMax;
  int maxParSecteur;

  /// « score_vol » (note × 1/volatilité) ou « egal ».
  String ponderation;

  /// Part visée en PEA (null : sans contrainte ; 1 : tout en PEA ; 0 : tout en CTO).
  double? partPea;
  int criteresMin;
  bool exclureMoatFaible;
  double? cycliquesMax;
  Set<String> secteursExclus;
  Set<String> exclus;
}

/// Plancher de qualité : part des six critères remplis (sur au moins deux évalués) et moat non « Faible ».
bool qualiteSuffisante(Valeur v, int criteresMin, bool exclureMoatFaible) {
  if (criteresMin > 0) {
    final ok = v.n('criteres_ok'), evalues = v.n('criteres_evalues');
    if (ok == null || evalues == null || evalues < 2 || ok / evalues < criteresMin / 6 - 1e-9) return false;
  }
  return !(exclureMoatFaible && v.t('moat') == 'Faible');
}

/// Projette des poids positifs sur {somme 1, min ≤ poids ≤ max} par remplissage itératif.
Map<String, double> plafonner(Map<String, double> poids, double min, double max) {
  final n = poids.length;
  if (n == 0) return {};
  var total = poids.values.fold<double>(0, (s, v) => s + math.max(v, 0));
  final w = {for (final e in poids.entries) e.key: total > 0 ? math.max(e.value, 0) / total : 1 / n};
  final bas = math.min(min, 1 / n), haut = math.max(max, 1 / n);
  for (var i = 0; i < 50; i++) {
    final fixes = <String>{};
    w.forEach((t, v) {
      if (v < bas - 1e-12 || v > haut + 1e-12) fixes.add(t);
    });
    if (fixes.isEmpty) break;
    for (final t in fixes) {
      w[t] = w[t]! < bas ? bas : haut;
    }
    final reste = 1 - fixes.fold<double>(0, (s, t) => s + w[t]!);
    final libres = w.keys.where((t) => !fixes.contains(t)).toList();
    final somme = libres.fold<double>(0, (s, t) => s + w[t]!);
    if (libres.isNotEmpty && somme > 0) {
      for (final t in libres) {
        w[t] = w[t]! / somme * reste;
      }
    }
  }
  total = w.values.fold<double>(0, (s, v) => s + v);
  return {for (final e in w.entries) e.key: e.value / total};
}

/// Ramène le poids d'un groupe sous `plafond`, l'excédent allant aux autres lignes (sous `max`).
Map<String, double> _plafonnerGroupe(Map<String, double> w, bool Function(String) membre, double plafond, double max) {
  final total = w.entries.where((e) => membre(e.key)).fold<double>(0, (s, e) => s + e.value);
  final autres = w.keys.where((t) => !membre(t)).toList();
  if (total <= plafond + 1e-9 || autres.isEmpty) return w;
  final out = {for (final e in w.entries) e.key: membre(e.key) ? e.value * plafond / total : e.value};
  final place = {for (final t in autres) t: math.max(max - out[t]!, 0.0)};
  final sommePlace = place.values.fold<double>(0, (s, v) => s + v);
  if (sommePlace > 0) {
    final aRepartir = math.min(total - plafond, sommePlace);
    for (final t in autres) {
      out[t] = out[t]! + place[t]! / sommePlace * aRepartir;
    }
  }
  final somme = out.values.fold<double>(0, (s, v) => s + v);
  return {for (final e in out.entries) e.key: e.value / somme};
}

/// Portefeuille construit par les règles : {ticker: poids}, du plus gros au plus petit.
Map<String, double> construire(Donnees d, Methode m, ReglagesConstruction c) {
  final notes = d.notes(m);
  final n = c.nbLignes;
  final maxCycliques = c.cycliquesMax == null ? n : (n * c.cycliquesMax! + 1e-9).floor();
  final quotas = c.partPea == null ? null : {'PEA': (n * c.partPea!).round(), 'CTO': n - (n * c.partPea!).round()};
  final choisis = <Valeur>[];
  final parSecteur = <String, int>{}, parEnveloppe = <String, int>{};
  var nbCycliques = 0;
  for (final v in d.classees(m)) {
    if (choisis.length >= n) break;
    if (!v.eligible || notes[v.ticker] == null || c.exclus.contains(v.ticker)) continue;
    if (c.secteursExclus.contains(v.secteur) || !qualiteSuffisante(v, c.criteresMin, c.exclureMoatFaible)) continue;
    if ((parSecteur[v.secteur] ?? 0) >= c.maxParSecteur) continue;
    if (quotas != null && (parEnveloppe[v.enveloppe] ?? 0) >= (quotas[v.enveloppe] ?? n)) continue;
    if (cycliques.contains(v.secteur)) {
      if (nbCycliques >= maxCycliques) continue;
      nbCycliques++;
    }
    choisis.add(v);
    parSecteur[v.secteur] = (parSecteur[v.secteur] ?? 0) + 1;
    parEnveloppe[v.enveloppe] = (parEnveloppe[v.enveloppe] ?? 0) + 1;
  }
  if (choisis.isEmpty) return {};

  // Pondération brute, puis plafonds par ligne, par secteur et pour les cycliques.
  Map<String, double> w;
  if (c.ponderation == 'egal') {
    w = {for (final v in choisis) v.ticker: 1.0};
  } else {
    final vols = [for (final v in choisis) if (v.n('volatilite') != null) v.n('volatilite')!]..sort();
    final mediane = vols.isEmpty ? 0.25 : vols[vols.length ~/ 2];
    w = {
      for (final v in choisis)
        v.ticker: math.pow((notes[v.ticker] ?? 50) / 50, 2) / math.max(v.n('volatilite') ?? mediane, 0.12),
    };
  }
  w = plafonner(w, c.poidsMin, c.poidsMax);
  final secteur = {for (final v in choisis) v.ticker: v.secteur};
  for (var i = 0; i < 50; i++) {
    final totaux = <String, double>{};
    w.forEach((t, x) => totaux[secteur[t]!] = (totaux[secteur[t]!] ?? 0) + x);
    final trop = totaux.entries.where((e) => e.value > c.secteurMax + 1e-9).map((e) => e.key).toSet();
    if (trop.isEmpty) break;
    var excedent = 0.0;
    for (final s in trop) {
      excedent += totaux[s]! - c.secteurMax;
      for (final t in w.keys.where((t) => secteur[t] == s).toList()) {
        w[t] = w[t]! * c.secteurMax / totaux[s]!;
      }
    }
    final sous = w.keys.where((t) => !trop.contains(secteur[t])).toList();
    final place = {for (final t in sous) t: math.max(c.poidsMax - w[t]!, 0.0)};
    final sommePlace = place.values.fold<double>(0, (s, v) => s + v);
    if (sommePlace <= 0) break;
    for (final t in sous) {
      w[t] = w[t]! + place[t]! / sommePlace * math.min(excedent, sommePlace);
    }
  }
  w = plafonner(w, c.poidsMin, c.poidsMax);
  if (c.cycliquesMax != null) {
    w = _plafonnerGroupe(w, (t) => cycliques.contains(secteur[t]), c.cycliquesMax!, c.poidsMax);
  }
  final tri = w.entries.toList()..sort((a, b) => b.value.compareTo(a.value));
  return {for (final e in tri) e.key: e.value};
}
