/// Le « bon prix » : mêmes calculs que l'application de bureau (pf/valuation.py, pf/prix_juste.py,
/// pf/scenarios.py), refaits sur l'appareil avec les hypothèses de l'utilisateur.
///
/// Modèle des « value drivers » : flux libre = résultat × (1 − croissance / ROIC). La croissance coûte du capital,
/// d'autant moins que l'entreprise est rentable. L'export donne, par valeur, le résultat et la dette rapportés à
/// la capitalisation (`val_base_cap`, `val_dette_cap`) et le ROIC retenu (`val_roic`) :
///     valeur intrinsèque / cours = val_base_cap × VE(1, croissance, rendement exigé, ROIC) − val_dette_cap
library;

import 'dart:math' as math;

import 'donnees.dart';

/// Réglages du modèle (config/strategie.json, bloc « valorisation »).
class ReglagesValorisation {
  const ReglagesValorisation({
    this.rendementExige = 0.09,
    this.croissanceTerminale = 0.03,
    this.anneesCroissance = 5,
    this.anneesConvergence = 5,
  });

  factory ReglagesValorisation.depuisJson(Map<String, dynamic>? j) => ReglagesValorisation(
        rendementExige: (j?['taux_actualisation'] as num?)?.toDouble() ?? 0.09,
        croissanceTerminale: (j?['croissance_terminale'] as num?)?.toDouble() ?? 0.03,
        anneesCroissance: (j?['annees_croissance'] as num?)?.toInt() ?? 5,
        anneesConvergence: (j?['annees_convergence'] as num?)?.toInt() ?? 5,
      );

  final double rendementExige;
  final double croissanceTerminale;
  final int anneesCroissance;
  final int anneesConvergence;

  ReglagesValorisation avec({double? rendementExige, double? croissanceTerminale}) => ReglagesValorisation(
        rendementExige: rendementExige ?? this.rendementExige,
        croissanceTerminale: croissanceTerminale ?? this.croissanceTerminale,
        anneesCroissance: anneesCroissance,
        anneesConvergence: anneesConvergence,
      );
}

/// Valeur d'entreprise actualisée d'un résultat `base` (12 derniers mois) : `value_driver_ev` de pf/valuation.py.
double valeurEntreprise(double base, double croissance, double rendement,
    {double croissanceTerminale = 0.03, double roic = 0.20, int anneesCroissance = 5, int anneesConvergence = 5}) {
  if (rendement <= croissanceTerminale) return double.infinity;
  final n = anneesCroissance + anneesConvergence;
  double g(int t) {
    if (t <= anneesCroissance) return croissance;
    if (t <= n) {
      return croissance +
          (croissanceTerminale - croissance) * (t - anneesCroissance) / math.max(anneesConvergence, 1);
    }
    return croissanceTerminale;
  }

  var resultat = base, valeur = 0.0;
  for (var t = 1; t <= n; t++) {
    resultat *= 1 + g(t);
    final reinvesti = math.max(g(t + 1) / roic, -0.5);
    valeur += resultat * (1 - reinvesti) / math.pow(1 + rendement, t);
  }
  final terminale =
      resultat * (1 + croissanceTerminale) * (1 - croissanceTerminale / roic) / (rendement - croissanceTerminale);
  return valeur + terminale / math.pow(1 + rendement, n);
}

/// Racine de `f` entre `bas` et `haut` par dichotomie (f change de signe sur l'intervalle).
double _racine(double Function(double) f, double bas, double haut) {
  var a = bas, b = haut, fa = f(a);
  for (var i = 0; i < 60 && (b - a) > 1e-6; i++) {
    final m = (a + b) / 2, fm = f(m);
    if ((fa < 0) == (fm < 0)) {
      a = m;
      fa = fm;
    } else {
      b = m;
    }
  }
  return (a + b) / 2;
}

/// Valorisation d'une valeur selon des hypothèses ; `disponible` est faux pour une holding, une société en perte
/// ou un fonds (le modèle ne s'applique pas).
class Valorisation {
  Valorisation(this.v, this.reglages)
      : _base = v.n('val_base_cap'),
        _dette = v.n('val_dette_cap') ?? 0,
        roicRetenu = v.n('val_roic') ?? 0.12,
        croissanceRetenue = v.n('croissance_attendue') ?? 0.05;

  final Valeur v;
  final ReglagesValorisation reglages;
  final double? _base;
  final double _dette;

  /// ROIC des nouveaux investissements et croissance des années 1 à 5 proposés par l'outil.
  final double roicRetenu;
  final double croissanceRetenue;

  bool get disponible => _base != null && _base > 0 && 1 + _dette > 0;

  double _ve(double croissance, double rendement, {double? roic, double? terminale}) => valeurEntreprise(
        _base!, croissance, rendement,
        croissanceTerminale: terminale ?? reglages.croissanceTerminale,
        roic: roic ?? roicRetenu,
        anneesCroissance: reglages.anneesCroissance,
        anneesConvergence: reglages.anneesConvergence,
      );

  /// Valeur intrinsèque rapportée au cours (1,2 : l'action vaut 20 % de plus que son prix).
  double? valeurSurCours({double? croissance, double? rendement, double? roic, double? terminale}) {
    if (!disponible) return null;
    final x = _ve(croissance ?? croissanceRetenue, rendement ?? reglages.rendementExige,
            roic: roic, terminale: terminale) -
        _dette;
    return x.isFinite ? x : null;
  }

  /// Prix juste dans la devise de cotation : le cours auquel l'action rapporte exactement le rendement exigé.
  double? prixJuste({double? croissance, double? rendement, double? roic, double? terminale}) {
    final cours = v.n('cours');
    final x = valeurSurCours(croissance: croissance, rendement: rendement, roic: roic, terminale: terminale);
    return cours == null || x == null || x <= 0 ? null : cours * x;
  }

  /// Croissance annuelle (années 1 à 5) que le cours actuel suppose, au rendement exigé.
  double? croissanceImplicite({double? rendement, double? roic, double? terminale}) {
    if (!disponible) return null;
    final r = rendement ?? reglages.rendementExige;
    double ecart(double g) => _ve(g, r, roic: roic, terminale: terminale) - (1 + _dette);
    if (ecart(-0.20) > 0) return -0.20;
    if (ecart(0.80) < 0) return 0.80;
    return _racine(ecart, -0.20, 0.80);
  }

  /// Rendement annuel implicite (TRI) si la croissance se réalise, au cours actuel.
  double? tri({double? croissance, double? roic, double? terminale}) {
    if (!disponible) return null;
    final g = croissance ?? croissanceRetenue;
    final t = terminale ?? reglages.croissanceTerminale;
    double ecart(double r) => _ve(g, r, roic: roic, terminale: t) - (1 + _dette);
    final bas = t + 0.005;
    if (ecart(bas) < 0) return bas;
    if (ecart(0.40) > 0) return 0.40;
    return _racine(ecart, bas, 0.40);
  }
}

/// Cours auquel l'action se paierait `cible` fois ses résultats des 12 derniers mois (pf/prix_juste.py).
double? prixAuMultiple(double? cours, double? multipleActuel, double? cible) {
  if (cours == null || multipleActuel == null || cible == null) return null;
  if (cours <= 0 || multipleActuel <= 0 || cible <= 0) return null;
  return cours * cible / multipleActuel;
}

// ----------------------------------------------------------------------------------------- scénarios à 5 ans

const nomsScenarios = ['Pessimiste', 'Central', 'Optimiste'];
const horizonScenarios = 5;

class Hypotheses {
  Hypotheses(this.croissance, this.marge, this.multiple);

  factory Hypotheses.depuisJson(Map<String, dynamic> j) => Hypotheses(
      (j['croissance'] as num).toDouble(), (j['marge'] as num).toDouble(), (j['multiple'] as num).toDouble());

  double croissance;
  double marge;
  double multiple;

  Map<String, dynamic> versJson() => {'croissance': croissance, 'marge': marge, 'multiple': multiple};
}

/// « fcf » en général ; « resultat » pour une banque ou un assureur, ou sans marge de FCF positive.
String baseScenarios(Valeur v) =>
    v.donnees['financiere'] == true || (v.n('marge_fcf') ?? 0) <= 0 ? 'resultat' : 'fcf';

double _puissance(double x, num exposant) => math.pow(x, exposant).toDouble();

double _arrondi(double x, int decimales) {
  final p = math.pow(10, decimales);
  return (x * p).round() / p;
}

/// Point de départ prudent des trois scénarios (`hypotheses_initiales` de pf/scenarios.py).
Map<String, Hypotheses> hypothesesInitiales(Valeur v) {
  final base = baseScenarios(v);
  var marge = v.n(base == 'fcf' ? 'marge_fcf' : 'marge_nette') ?? 0;
  if (marge <= 0) marge = 0.10;
  final actuel = v.n(base == 'fcf' ? 'p_fcf' : 'per');
  final mediane = v.n(base == 'fcf' ? 'p_fcf_historique' : 'per_historique');
  bool valide(double? m) => m != null && m >= 3 && m <= 80;
  final valides = [actuel, mediane].where(valide).cast<double>().toList();
  final central = valides.isEmpty ? 15.0 : valides.reduce(math.min);
  final optimiste = math.max(central * 1.15, valide(mediane) ? mediane! : 0.0);
  final g = ((v.n('croissance_attendue') ?? v.n('croiss_ca') ?? 0.05).clamp(-0.10, 0.15)).toDouble();
  return {
    'Pessimiste': Hypotheses(_arrondi(g > 0 ? g * 0.5 : g * 1.5, 4), _arrondi(marge * 0.85, 4), _arrondi(central * 0.75, 1)),
    'Central': Hypotheses(_arrondi(g, 4), _arrondi(marge, 4), _arrondi(central, 1)),
    'Optimiste': Hypotheses(_arrondi(g > 0 ? math.min(g * 1.3, 0.30) : g * 0.5, 4), _arrondi(marge * 1.1, 4),
        _arrondi(optimiste, 1)),
  };
}

/// Prix de l'action dans 5 ans : chiffre d'affaires × marge × multiple de sortie, ramené à une action.
double? prixFutur(Valeur v, Hypotheses h) {
  final cours = v.n('cours'), pCa = v.n('p_ca');
  if (cours == null || cours <= 0 || pCa == null || pCa <= 0) return null;
  // Chiffre d'affaires / capitalisation = 1 / (prix / chiffre d'affaires).
  final valeurSurCapi = _puissance(1 + h.croissance, horizonScenarios) * h.marge * h.multiple / pCa;
  final dilution = (v.n('evolution_actions') ?? 0).clamp(-0.10, 0.10).toDouble();
  return cours * valeurSurCapi / _puissance(1 + dilution, horizonScenarios);
}

/// Rendement annuel, hors dividendes, d'un achat au cours actuel revendu à `prix` dans 5 ans.
double? rendementAnnuel(double? prix, double? cours) {
  if (prix == null || cours == null || cours <= 0) return null;
  if (prix <= 0) return -1;
  return _puissance(prix / cours, 1 / horizonScenarios) - 1;
}
