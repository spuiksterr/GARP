import 'dart:convert';
import 'dart:io';

import 'package:climax/calculs.dart';
import 'package:climax/donnees.dart';
import 'package:climax/formats.dart';
import 'package:climax/stockage.dart';
import 'package:flutter_test/flutter_test.dart';

Donnees _donnees() {
  final json = {
    'format': 1,
    'donnees_au': '2026-11-13',
    'nb_eligibles': 2,
    'valeurs': [
      {'ticker': 'AAA', 'nom': 'Alpha', 'secteur': 'Santé', 'statut': 'Éligible', 'rang': 1, 'score': 80.0,
       'tri_implicite': 0.12, 'per_prospectif': 20.0, 'perf_1m': -0.20},
      {'ticker': 'BBB', 'nom': 'Beta', 'secteur': 'Santé', 'statut': 'Exclu', 'score': 40.0,
       'motifs_exclusion': 'dette', 'per_prospectif': 10.0},
      {'ticker': 'CCC', 'nom': 'Gamma', 'secteur': 'Banques', 'statut': 'Éligible', 'rang': 2, 'score': 60.0},
    ],
    'cours': {'AAA': {'debut': '2026-01-02', 'c': [10.0, null, 12.0]}},
    'rangs': {'AAA': [['2026-11-01', 3], ['2026-11-08', 1]]},
  };
  return Donnees.depuisOctets(gzip.encode(utf8.encode(jsonEncode(json))));
}

void main() {
  test('nombres à la française', () {
    expect(nombre(1234.56, 1), '1 234,6');
    expect(pct(0.125), '12,5 %');
    expect(pct(0.05, 0, true), '+5 %');
    expect(pct(null), vide);
    expect(dateFr('2026-11-13'), '13/11/2026');
  });

  test('lecture du fichier publié', () {
    final d = _donnees();
    expect(d.valeurs.length, 3);
    expect(d.triees.first.ticker, 'AAA');
    expect(d.valeurs['AAA']!.eligible, isTrue);
    expect(d.cours('AAA')!.points().length, 2); // la semaine sans cours est sautée
    expect(d.rangs('AAA').last.$2, 1);
  });

  test('portefeuille : moyennes, garde-fous, vigilance', () {
    final d = _donnees();
    final poids = poidsNormalises([Ligne('AAA', 50), Ligne('BBB', 30), Ligne('CCC', 20)]);
    expect(moyenne(poids, d, 'score'), closeTo(0.5 * 80 + 0.3 * 40 + 0.2 * 60, 1e-9));
    // PER harmonique : 0,8 / (0,5/20 + 0,3/10) sur les lignes qui ont un PER.
    expect(moyenne(poids, d, 'per_prospectif', harmonique: true), closeTo(0.8 / (0.5 / 20 + 0.3 / 10), 1e-9));
    final alertes = gardeFous(poids, d);
    expect(alertes.where((a) => a.contains('Alpha')).length, 1); // 50 % > 25 %
    expect(alertes.any((a) => a.contains('Santé')), isTrue); // 80 % > 40 %
    final v = vigilance(poids, d);
    expect(v.any((x) => x.$1 == 'BBB' && x.$2 == 'Thèse à revoir'), isTrue);
    expect(v.any((x) => x.$1 == 'AAA' && x.$2 == 'Forte baisse'), isTrue);
  });
}
