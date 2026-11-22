/// Suivi du portefeuille réel : valeur des positions, plus-values, apport du mois (pf/tracker.py,
/// `contribution_plan`) et conditions de vente chiffrées (pf/regles.py).
library;

import 'dart:math' as math;

import 'donnees.dart';
import 'formats.dart';
import 'stockage.dart';

class Position {
  Position(this.ligne, this.coursEur);

  final Ligne ligne;

  /// Dernier cours en euros (null pour une ligne hors des données).
  final double? coursEur;

  double? get valeur => ligne.quantite == null || coursEur == null ? null : ligne.quantite! * coursEur!;

  double? get investi =>
      ligne.quantite == null || ligne.prixRevient == null ? null : ligne.quantite! * ligne.prixRevient!;

  double? get plusValue => valeur == null || investi == null ? null : valeur! - investi!;

  double? get performance => plusValue == null || investi! <= 0 ? null : plusValue! / investi!;
}

List<Position> positions(List<Ligne> lignes, Donnees? d) =>
    [for (final l in lignes) Position(l, d?.valeurs[l.ticker]?.n('cours_eur'))];

/// Valeur totale des positions dont on connaît la quantité et le cours.
double valeurTotale(List<Position> p) => p.fold<double>(0, (s, x) => s + (x.valeur ?? 0));

class Ordre {
  Ordre(this.ticker, this.quantite, this.coursEur, this.poidsCible, this.valeurAvant);

  final String ticker;
  double quantite;
  final double coursEur;
  final double poidsCible;
  final double valeurAvant;

  double get montant => quantite * coursEur;
}

class PlanApport {
  PlanApport(this.ordres, this.reste, this.poidsApres);

  final List<Ordre> ordres;

  /// Somme non investie (aucune ligne achetable avec ce qui reste).
  final double reste;
  final Map<String, double> poidsApres;
}

/// Répartit un apport sur les lignes les plus en retard sur leur cible, sans rien vendre.
///
/// `cibles` : poids cibles (somme libre) des lignes achetables ; `detenu` : valeur détenue en euros ;
/// `cours` : cours en euros. On achète toujours la ligne la plus en retard, pour au moins `ordreMin` euros ;
/// une action plus chère que le besoin n'est achetée que si elle ne le dépasse pas de plus de moitié.
PlanApport planApport(double montant, Map<String, double> cibles, Map<String, double> detenu, Map<String, double> cours,
    {double ordreMin = 300, bool fractions = false}) {
  final total = cibles.values.fold<double>(0, (s, v) => s + v);
  if (montant <= 0 || total <= 0) return PlanApport([], montant, {});
  final w = {for (final e in cibles.entries) e.key: e.value / total};
  final avant = {for (final t in w.keys) t: detenu[t] ?? 0.0};
  final valeurCible = avant.values.fold<double>(0, (s, v) => s + v) + montant;
  final prevu = Map<String, double>.of(avant);
  final quantites = {for (final t in w.keys) t: 0.0};
  var budget = montant;
  while (true) {
    final retards = [for (final t in w.keys) (t, w[t]! * valeurCible - prevu[t]!)]..sort((a, b) => b.$2.compareTo(a.$2));
    var achete = false;
    for (final (t, retard) in retards) {
      final prix = cours[t];
      if (retard <= 0 || prix == null || prix <= 0 || prix > budget) continue;
      final besoin = math.max(retard, quantites[t] == 0 ? ordreMin : 0.0);
      var q = fractions ? besoin / prix : (besoin / prix).floorToDouble();
      if (q == 0) {
        if (prix > 1.5 * besoin) continue;
        q = 1.0;
      }
      q = math.min(q, fractions ? budget / prix : (budget / prix).floorToDouble());
      final cout = q * prix;
      if (q <= 0 || (quantites[t] == 0 && cout < 0.5 * ordreMin)) continue;
      quantites[t] = quantites[t]! + q;
      prevu[t] = prevu[t]! + cout;
      budget -= cout;
      achete = true;
      break;
    }
    if (!achete || budget <= 0.01) break;
  }
  final ordres = [
    for (final t in w.keys)
      if (quantites[t]! > 0) Ordre(t, quantites[t]!, cours[t]!, w[t]!, avant[t]!),
  ]..sort((a, b) => b.montant.compareTo(a.montant));
  final somme = prevu.values.fold<double>(0, (s, v) => s + v);
  return PlanApport(ordres, budget, {for (final e in prevu.entries) e.key: somme > 0 ? e.value / somme : 0.0});
}

// ------------------------------------------------------------------------------ conditions de vente chiffrées

/// Indicateur : (libellé, unité). « pct » : ratio affiché en %, « x » : multiple, « n » : nombre.
const indicateursRegles = <String, (String, String)>{
  'evol_ca_12m': ('CA des 12 derniers mois, par rapport au dernier exercice', 'pct'),
  'croiss_ca': ('Croissance annuelle du chiffre d\'affaires', 'pct'),
  'rentabilite': ('Rentabilité du capital moyenne (ROIC, ou ROE pour une financière)', 'pct'),
  'marge_operationnelle': ('Marge opérationnelle', 'pct'),
  'marge_fcf': ('Marge de flux de trésorerie disponible', 'pct'),
  'evolution_actions': ('Évolution annuelle du nombre d\'actions (dilution si positive)', 'pct'),
  'dette_nette_ebitda': ('Dette nette / EBITDA', 'x'),
  'couverture_interets': ('Couverture des intérêts', 'x'),
  'criteres_ok': ('Critères de qualité remplis (sur 6)', 'n'),
  'piotroski': ('Score de Piotroski (sur 9)', 'n'),
  'per': ('PER', 'x'),
  'p_fcf': ('P/FCF', 'x'),
  'ecart_p_fcf_historique': ('P/FCF par rapport à sa médiane historique', 'pct'),
  'tri_implicite': ('TRI implicite', 'pct'),
  'perf_12m': ('Performance sur 12 mois', 'pct'),
  'ecart_plus_haut_52s': ('Écart au plus haut de 52 semaines', 'pct'),
  'cours': ('Cours (devise de cotation)', 'n'),
};

const texteOperateurs = {'<': 'sous', '<=': 'au plus', '>': 'au-dessus de', '>=': 'au moins'};

String _affiche(double? valeur, String unite, [int? decimales]) => valeur == null
    ? vide
    : unite == 'pct'
        ? pct(valeur, decimales ?? 1)
        : unite == 'x'
            ? '${nombre(valeur, decimales ?? 1)}x'
            : nombre(valeur, decimales ?? (valeur == valeur.roundToDouble() ? 0 : 2));

/// « Marge opérationnelle sous 15 % ».
String texteRegle(Regle r) {
  final (libelle, unite) = indicateursRegles[r.indicateur] ?? (r.indicateur, 'n');
  final d = r.seuil == r.seuil.roundToDouble() ? 0 : 1;
  return '$libelle ${texteOperateurs[r.operateur] ?? r.operateur} '
      '${_affiche(unite == 'pct' ? r.seuil / 100 : r.seuil, unite, d)}';
}

/// (valeur actuelle en texte, statut : « Atteinte », « Respectée » ou « Donnée absente »).
(String, String) evaluerRegle(Regle r, Donnees? d) {
  final (_, unite) = indicateursRegles[r.indicateur] ?? (r.indicateur, 'n');
  final valeur = d?.valeurs[r.ticker]?.n(r.indicateur);
  if (valeur == null) return (vide, 'Donnée absente');
  final seuil = unite == 'pct' ? r.seuil / 100 : r.seuil;
  final atteinte = switch (r.operateur) {
    '<' => valeur < seuil,
    '<=' => valeur <= seuil,
    '>' => valeur > seuil,
    _ => valeur >= seuil,
  };
  return (_affiche(valeur, unite), atteinte ? 'Atteinte' : 'Respectée');
}
