import 'dart:convert';
import 'dart:io';

import 'package:garp/donnees.dart';
import 'package:garp/methodes.dart';
import 'package:flutter_test/flutter_test.dart';

Donnees _donnees({bool avecMethodes = true}) {
  final json = {
    'format': 1,
    'nb_eligibles': 3,
    'valeurs': [
      {'ticker': 'A', 'statut': 'Éligible', 'score': 80.0, 'buffett': 5, 'criteres_ok': 5, 'criteres_evalues': 6,
       'crit_roce': 0.22, 'crit_roce_ok': true, 'crit_dette_ok': false},
      {'ticker': 'B', 'statut': 'Éligible', 'score': 60.0, 'buffett': 3, 'criteres_ok': 2, 'criteres_evalues': 6},
      {'ticker': 'C', 'statut': 'Éligible', 'score': 70.0, 'buffett': 5, 'criteres_ok': 1, 'criteres_evalues': 1},
      {'ticker': 'D', 'statut': 'Exclu', 'score': 50.0},
    ],
    if (avecMethodes) ...{
      'methodes': [
        {'id': 'composite', 'libelle': 'Score composite', 'description': '', 'poids': {'score': 1}},
        {'id': 'buffett', 'libelle': 'Buffett', 'description': '', 'poids': {'buffett': 1}},
        {'id': 'mixte', 'libelle': 'Mixte', 'description': '', 'poids': {'buffett': 1, 'criteres_part': 1}},
      ],
      'criteres': [
        {'cle': 'roce', 'titre': 'ROCE', 'seuil': 0.15, 'sens': '>'},
        {'cle': 'dette', 'titre': 'Dette nette / FCF', 'seuil': 3.0, 'sens': '<'},
      ],
    },
  };
  return Donnees.depuisOctets(gzip.encode(utf8.encode(jsonEncode(json))));
}

void main() {
  test('rang centile comme pandas rank(pct=True) : ex aequo au rang moyen', () {
    final r = rangsCentiles({'a': 5, 'b': 3, 'c': 5});
    expect(r['b'], closeTo(100 / 3, 1e-9));
    expect(r['a'], closeTo(2.5 / 3 * 100, 1e-9));
    expect(r['c'], r['a']);
  });

  test('notes selon une méthode : composante absente ignorée, score en départage', () {
    final d = _donnees();
    final n = d.notes(d.methode('buffett'));
    expect(n.containsKey('D'), isFalse); // pas de note Buffett
    expect(n['B'], closeTo(100 / 3 + 60 / 1e4, 1e-9));
    expect(n['A']! > n['C']!, isTrue); // même note Buffett, meilleur score
    expect(d.classees(d.methode('buffett')).map((v) => v.ticker).take(3), ['A', 'C', 'B']);
    expect(d.rangSelon(d.methode('buffett'), 'B'), 3);
    expect(d.rangSelon(d.methode('buffett'), 'D'), isNull);
  });

  test('méthode mixte : six critères en part des critères évalués (au moins deux)', () {
    final d = _donnees();
    final n = d.notes(d.methode('mixte'));
    // A : Buffett 83,3 et critères 100 ; B : 33,3 et 50 ; C : critères non comptés (un seul évalué).
    expect(n['A'], closeTo((250 / 3 + 100) / 2 + 80 / 1e4, 1e-9));
    expect(n['B'], closeTo((100 / 3 + 50) / 2 + 60 / 1e4, 1e-9));
    expect(n['C'], closeTo(250 / 3 + 70 / 1e4, 1e-9));
  });

  test('six critères lus dans les données', () {
    final d = _donnees();
    final a = d.valeurs['A']!;
    expect(d.criteres.first.pour(a), (0.22, true));
    expect(d.criteres.last.pour(a).$2, isFalse);
    expect(d.criteres.first.pour(d.valeurs['B']!), (null, null));
  });

  test('fichier publié avant les méthodes : score composite seul', () {
    final d = _donnees(avecMethodes: false);
    expect(d.methodes.map((m) => m.id), ['composite']);
    expect(d.methode('buffett').id, 'composite');
    expect(d.criteres, isEmpty);
  });
}
