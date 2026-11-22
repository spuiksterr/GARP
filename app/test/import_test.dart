import 'dart:convert';
import 'dart:io';

import 'package:garp/donnees.dart';
import 'package:garp/import_portefeuille.dart';
import 'package:flutter_test/flutter_test.dart';

Donnees _donnees() {
  final json = {
    'format': 1,
    'valeurs': [
      {'ticker': 'GOOGL', 'nom': 'Alphabet Inc.', 'pays': 'États-Unis', 'cours': 180.0, 'cours_eur': 150.0},
      {'ticker': 'AI.PA', 'nom': 'Air Liquide', 'pays': 'France', 'cours': 160.0, 'cours_eur': 160.0},
      {'ticker': 'AMUN.PA', 'nom': 'Amundi', 'pays': 'France', 'cours': 70.0, 'cours_eur': 70.0},
      {'ticker': 'ASML.AS', 'nom': 'ASML Holding', 'pays': 'Pays-Bas', 'cours': 700.0, 'cours_eur': 700.0},
      {'ticker': 'AI', 'nom': 'C3.ai', 'pays': 'États-Unis', 'cours': 25.0, 'cours_eur': 21.0},
      {'ticker': 'NUKL.DE', 'nom': 'VanEck Uranium and Nuclear Technologies UCITS ETF', 'fonds': true,
       'statut': 'Fonds', 'cours': 40.0, 'cours_eur': 40.0},
    ],
  };
  return Donnees.depuisOctets(gzip.encode(utf8.encode(jsonEncode(json))));
}

void main() {
  final d = _donnees();

  test('nombres français et anglais', () {
    expect(lireNombre('1 234,56 €'), 1234.56);
    expect(lireNombre('1,234.56'), 1234.56);
    expect(lireNombre('34,5 %'), 34.5);
    expect(lireNombre('1’234.5'), 1234.5);
    expect(lireNombre('1.234.567'), 1234567);
    expect(lireNombre('-12,3'), -12.3);
    expect(lireNombre('Alphabet'), isNull);
  });

  test('export de type Boursorama : point-virgule, en-tête, ISIN, montants, total et liquidités', () {
    const csv = 'Portefeuille au 14/11/2026\n'
        'Libellé;Code ISIN;Quantité;Cours;Montant;+/- value %\n'
        'ALPHABET INC-CL A;US02079K3059;10;180,50;1 500,00;+12,5\n'
        'AIR LIQUIDE;FR0000120073;15;160,00;2 400,00;-3,1\n'
        'AMUNDI MSCI WORLD UCITS ETF;LU1681043599;20;30,00;600,00;+1,0\n'
        'Liquidités;;;;500,00;\n'
        'Total;;;;5 000,00;\n';
    final r = importer(csv, d);
    expect(r.lignes.map((l) => l.libelle), [
      'ALPHABET INC-CL A', 'AIR LIQUIDE', 'AMUNDI MSCI WORLD UCITS ETF', 'Liquidités',
    ]);
    expect(r.lignes[0].ticker, 'GOOGL');
    expect(r.lignes[1].ticker, 'AI.PA');
    expect(r.lignes[1].confiance, Confiance.sure); // nom identique, pays de l'ISIN concordant
    // Un ETF Amundi n'est pas la société Amundi.
    expect(r.lignes[2].ticker, isNull);
    expect(r.lignes[3].ignoree, isTrue);
    expect(r.methode, contains('montants'));
    expect(r.lignes[0].poids, closeTo(1500 / 4500 * 100, 1e-9));
    expect(r.lignes[3].poids, 0);
  });

  test('export de type Degiro : virgule, guillemets, Symbole/ISIN, valeur en EUR préférée', () {
    const csv = 'Produit,Symbole/ISIN,Quantité,Clôture,Devise,Montant local,Valeur en EUR\n'
        '"ALPHABET INC. - CLASS A","US02079K3059","10","180,50","USD","1805,00","1550,00"\n'
        '"ASML HOLDING","NL0010273215","2","700,00","EUR","1400,00","1400,00"\n'
        '"CASH & CASH FUND & FTX CASH (EUR)","","","","EUR","50,00","50,00"\n';
    final r = importer(csv, d);
    final retenues = r.retenues.toList();
    expect(retenues.map((l) => l.ticker), ['GOOGL', 'ASML.AS']);
    expect(retenues[0].poids, closeTo(1550 / 2950 * 100, 1e-9));
  });

  test('liste simple et saisie libre', () {
    final r = importer('GOOGL;20\nNUKL.DE;5\nAI;10', d);
    expect(r.lignes.map((l) => l.ticker), ['GOOGL', 'NUKL.DE', 'AI']); // le ticker exact prime
    expect(r.lignes[0].poids, closeTo(20 / 35 * 100, 1e-9));
    final libre = importer('Alphabet 50\nAir Liquide 50 %', d);
    expect(libre.lignes.map((l) => l.ticker), ['GOOGL', 'AI.PA']);
    expect(libre.lignes[1].poids, 50);
  });

  test('quantités seules : poids d\'après les cours en euros des données', () {
    final r = importer('Nom;Quantité\nAlphabet;10\nAir Liquide;5', d);
    expect(r.methode, contains('quantités'));
    expect(r.lignes[0].poids, closeTo(1500 / 2300 * 100, 1e-9));
  });

  test('ticker sans place de cotation, départagé par l\'ISIN', () {
    final r = importer('Ticker;ISIN;Poids\nASML;NL0010273215;100', d);
    expect(r.lignes.single.ticker, 'ASML.AS');
    expect(r.lignes.single.confiance, Confiance.sure);
  });

  test('correspondances retenues sur l\'appareil', () {
    final r = importer('Libellé;ISIN;Montant\nMa ligne bizarre;US02079K3059;100', d,
        correspondances: {'US02079K3059': 'GOOGL'});
    expect(r.lignes.single.ticker, 'GOOGL');
    final hors = importer('Libellé;ISIN;Montant\nOr physique;FR0013416716;100', d,
        correspondances: {'FR0013416716': ''});
    expect(hors.lignes.single.ticker, isNull);
    expect(hors.lignes.single.identifiant, 'FR0013416716');
  });

  test('aucun chiffre : parts égales', () {
    final r = importer('Alphabet\nAir Liquide', d);
    expect(r.lignes.every((l) => l.poids == 50), isTrue);
  });
}
