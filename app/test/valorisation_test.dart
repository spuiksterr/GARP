// Les valeurs attendues viennent de l'application de bureau (pf/valuation.py, pf/scenarios.py, pf/tracker.py).
import 'dart:convert';
import 'dart:io';

import 'package:garp/construction.dart';
import 'package:garp/donnees.dart';
import 'package:garp/formats.dart';
import 'package:garp/recherche.dart';
import 'package:garp/risques.dart';
import 'package:garp/stockage.dart';
import 'package:garp/suivi.dart';
import 'package:garp/valorisation.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _valeur(String ticker, Map<String, dynamic> plus) => {
      'ticker': ticker, 'nom': ticker, 'statut': 'Éligible', 'secteur': 'Santé', 'enveloppe': 'CTO', 'devise': 'USD',
      'cours': 100.0, 'score': 60.0, 'volatilite': 0.25, 'criteres_ok': 5, 'criteres_evalues': 6, ...plus,
    };

Donnees _donnees() {
  // 60 semaines : A monte de 1 % par semaine, B alterne, l'indice suit A à moitié ; le dollar est stable à 0,9 €.
  final a = [for (var i = 0; i < 60; i++) 100.0 * (1 + 0.01 * i + (i.isEven ? 0.5 : 0))];
  final b = [for (var i = 0; i < 60; i++) 50.0 + (i % 3) * 2.0];
  final json = {
    'format': 1,
    'nb_eligibles': 3,
    'valeurs': [
      _valeur('A', {'val_base_cap': 0.05, 'val_dette_cap': 0.10, 'val_roic': 0.25, 'croissance_attendue': 0.12,
        'score': 90.0, 'marge_fcf': 0.20, 'marge_nette': 0.15, 'p_fcf': 30.0, 'per': 35.0, 'p_fcf_historique': 24.0,
        'per_historique': 28.0, 'croiss_ca': 0.10, 'p_ca': 6.0, 'evolution_actions': -0.01, 'cours_eur': 90.0}),
      _valeur('B', {'score': 70.0, 'secteur': 'Banques', 'cours_eur': 45.0}),
      _valeur('C', {'score': 50.0, 'criteres_ok': 1, 'cours_eur': 630.0}),
    ],
    'cours': {
      'A': {'debut': '2025-09-05', 'c': a},
      'B': {'debut': '2025-09-05', 'c': b},
    },
    'changes': {'USD': {'debut': '2025-09-05', 'c': [for (var i = 0; i < 60; i++) 0.9]}},
    'reference': {'ticker': 'IWDA.AS', 'debut': '2025-09-05', 'c': [for (var i = 0; i < 60; i++) 100.0 + a[i] / 2]},
    'strategie': {
      'valorisation': {'taux_actualisation': 0.09, 'croissance_terminale': 0.03, 'annees_croissance': 5,
        'annees_convergence': 5},
    },
  };
  return Donnees.depuisOctets(gzip.encode(utf8.encode(jsonEncode(json))));
}

void main() {
  test('valeur d\'entreprise des value drivers', () {
    expect(valeurEntreprise(1, 0.10, 0.09), closeTo(19.539250628554296, 1e-9));
    expect(valeurEntreprise(1, -0.02, 0.08, croissanceTerminale: 0.02, roic: 0.12), closeTo(12.657812359654455, 1e-9));
  });

  test('prix juste, croissance implicite et TRI d\'une valeur', () {
    final d = _donnees();
    final valo = Valorisation(d.valeurs['A']!, d.valorisation);
    expect(valo.valeurSurCours(), closeTo(1.037170813178053, 1e-9));
    expect(valo.prixJuste(), closeTo(103.7170813178053, 1e-6));
    expect(valo.croissanceImplicite(), closeTo(0.11282035325834155, 1e-4));
    expect(valo.tri(), closeTo(0.09174002656514786, 1e-4));
    expect(Valorisation(d.valeurs['B']!, d.valorisation).disponible, isFalse);
    expect(prixAuMultiple(100, 30, 24), 80);
  });

  test('scénarios à 5 ans', () {
    final v = _donnees().valeurs['A']!;
    final h = hypothesesInitiales(v);
    expect([h['Pessimiste']!.croissance, h['Pessimiste']!.marge, h['Pessimiste']!.multiple], [0.06, 0.17, 18.0]);
    expect([h['Optimiste']!.croissance, h['Optimiste']!.marge, h['Optimiste']!.multiple], [0.156, 0.22, 27.6]);
    final central = prixFutur(v, h['Central']!);
    expect(central, closeTo(148.2532174451514, 1e-6));
    expect(rendementAnnuel(central, 100), closeTo(0.08193414117660769, 1e-9));
    expect(rendementAnnuel(prixFutur(v, h['Pessimiste']!), 100), closeTo(-0.06419641225313588, 1e-9));
  });

  test('recherche personnalisée : exigences du profil et verdict sur le prix', () {
    final d = _donnees();
    final p = Profil(criteresMin: 4, margeSecurite: 0.20);
    final liste = opportunites(d, p, d.valorisation);
    expect(liste.map((o) => o.v.ticker), ['A', 'B']); // C : un seul critère
    expect(liste.first.verdict, Verdict.prixCorrect); // 100 sous 103,7 mais au-dessus de 83
    expect(liste.first.prixAchat, closeTo(103.7170813178053 * 0.8, 1e-6));
    expect(liste.last.verdict, Verdict.nonEvalue);
    expect(evaluer(d.valeurs['A']!, 90, Profil(rendementExige: 0.12), d.valorisation.avec(rendementExige: 0.12)).verdict,
        Verdict.aAttendre);
    expect(raisonEcartee(d.valeurs['B']!, Profil(secteursExclus: {'Banques'})), contains('Secteur'));
  });

  test('risques sur les cours hebdomadaires en euros', () {
    final d = _donnees();
    expect(d.coursEur('A')!.valeurs.first, closeTo(150 * 0.9, 1e-9));
    final r = Risques(d, {'A': 60, 'B': 40});
    expect(r.poids['A'], closeTo(0.6, 1e-12));
    expect(r.troisPremieres, closeTo(1, 1e-12));
    expect(r.nombreEffectif, closeTo(1 / (0.36 + 0.16), 1e-9));
    expect(r.devises['USD'], closeTo(1, 1e-12));
    expect(r.betas['A']! > 1, isTrue); // l'indice ne suit A qu'à moitié
    expect(r.stats.perteMaximale! <= 0, isTrue);
    expect(r.scenarios.first.$1, 'Marché mondial -30 %');
    expect(r.scenarios[1].$2, closeTo(-0.10, 1e-12)); // tout est en dollars
    expect(nouveauxPoids({'A': 0.6, 'B': 0.4}, 'B', 0.5)['A'], closeTo(0.5, 1e-12));
  });

  test('construction par les règles : plancher de qualité, plafonds', () {
    final d = _donnees();
    final w = construire(d, d.methode('composite'), ReglagesConstruction(nbLignes: 5, poidsMax: 0.7, poidsMin: 0.1, secteurMax: 1, cycliquesMax: null));
    expect(w.keys, ['A', 'B']); // C écartée par le plancher de qualité
    expect(w.values.reduce((a, b) => a + b), closeTo(1, 1e-9));
    expect(w['A']! <= 0.7 + 1e-9 && w['A']! > w['B']!, isTrue);
    expect(plafonner({'x': 9, 'y': 1}, 0.2, 0.6)['y'], closeTo(0.25, 1e-9)); // comme _cap_weights
  });

  test('apport du mois : la ligne la plus en retard d\'abord, sans vendre', () {
    final plan = planApport(1000, {'A': 0.5, 'B': 0.3, 'C': 0.2}, {'A': 2000, 'B': 500}, {'A': 50, 'B': 120, 'C': 700});
    expect([for (final o in plan.ordres) (o.ticker, o.quantite, o.montant)], [('C', 1.0, 700.0), ('B', 2.0, 240.0)]);
    expect(plan.reste, closeTo(60, 1e-9));
  });

  test('conditions de vente chiffrées', () {
    final d = _donnees();
    final r = Regle('A', 'marge_fcf', '<', 25);
    expect(texteRegle(r), 'Marge de flux de trésorerie disponible sous ${pct(0.25, 0)}');
    expect(evaluerRegle(r, d), (pct(0.2), 'Atteinte'));
    expect(evaluerRegle(Regle('A', 'per', '>', 40), d).$2, 'Respectée');
    expect(evaluerRegle(Regle('B', 'per', '>', 40), d).$2, 'Donnée absente');
  });
}
