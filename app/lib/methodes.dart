/// Méthodes d'évaluation des actions : même règle que l'application de bureau (pf/portfolio.py, note_construction).
///
/// Chaque méthode pondère des composantes (score composite, regards de Buffett, Munger, Fisher, Terry Smith, six
/// critères, piliers qualité, croissance, valorisation, momentum). Chaque composante est ramenée à son rang centile
/// dans l'univers (0 à 100), pour qu'une note de 1 à 5 et un score sur 100 se combinent ; une composante absente est
/// ignorée et son poids reporté sur les autres. Le score composite départage les ex aequo.
library;

import 'donnees.dart';

class Methode {
  const Methode(this.id, this.libelle, this.description, this.poids, [this.composantes = const []]);

  factory Methode.depuisJson(Map<String, dynamic> j) => Methode(
        j['id'] as String,
        j['libelle'] as String,
        (j['description'] as String?) ?? '',
        {for (final e in (j['poids'] as Map<String, dynamic>).entries) e.key: (e.value as num).toDouble()},
        [for (final c in (j['composantes'] as List?) ?? const []) c as String],
      );

  final String id;
  final String libelle;
  final String description;
  final Map<String, double> poids;
  final List<String> composantes;
}

/// Méthode par défaut, et seule disponible avec un fichier de données publié avant la liste des méthodes.
const composite = Methode('composite', 'Score composite',
    'La note de l\'outil : piliers, valorisation, quatre regards, Piotroski, Altman, Beneish.', {'score': 1});

/// Les six critères de qualité (pf/criteres.py), avec le seuil en vigueur.
class Critere {
  const Critere(this.cle, this.titre, this.seuil, this.sens);

  factory Critere.depuisJson(Map<String, dynamic> j) => Critere(
      j['cle'] as String, j['titre'] as String, (j['seuil'] as num).toDouble(), (j['sens'] as String?) ?? '>');

  final String cle;
  final String titre;
  final double seuil;
  final String sens; // '>', '<' ou '<='

  /// Valeur mesurée, et rempli (true), échoué (false) ou non évalué (null) pour une valeur.
  (double?, bool?) pour(Valeur v) {
    final ok = v.donnees['crit_${cle}_ok'];
    return (v.n('crit_$cle'), ok is bool ? ok : null);
  }
}

/// Valeur d'une composante pour une valeur (null si absente).
double? composante(Valeur v, String cle) {
  switch (cle) {
    case 'criteres_part':
      final ok = v.n('criteres_ok'), evalues = v.n('criteres_evalues');
      if (ok == null || evalues == null || evalues < 2) return null;
      return ok / evalues;
    case 'pts_regards':
      final r = v.n('regards_total');
      return r == null ? null : r * 5;
    default:
      return v.n(cle);
  }
}

/// Rang centile de 0 à 100, comme pandas `rank(pct=True)` : les ex aequo reçoivent leur rang moyen.
Map<String, double> rangsCentiles(Map<String, double> valeurs) {
  final tri = valeurs.entries.toList()..sort((a, b) => a.value.compareTo(b.value));
  final n = tri.length;
  final out = <String, double>{};
  var i = 0;
  while (i < n) {
    var j = i;
    while (j + 1 < n && tri[j + 1].value == tri[i].value) {
      j++;
    }
    final rangMoyen = (i + j) / 2 + 1;
    for (var k = i; k <= j; k++) {
      out[tri[k].key] = rangMoyen / n * 100;
    }
    i = j + 1;
  }
  return out;
}

extension SiVide<T> on List<T> {
  /// La liste, ou `defaut` si elle est vide.
  List<T> ifEmpty(List<T> defaut) => isEmpty ? defaut : this;
}

/// Note de 0 à 100 de chaque valeur selon la méthode (absente si aucune composante n'est connue).
Map<String, double> notesSelon(Iterable<Valeur> valeurs, Methode m) {
  final liste = valeurs.toList();
  final somme = <String, double>{}, total = <String, double>{};
  m.poids.forEach((cle, p) {
    if (p <= 0) return;
    final rangs = rangsCentiles({
      for (final v in liste) v.ticker: ?composante(v, cle),
    });
    rangs.forEach((t, r) {
      somme[t] = (somme[t] ?? 0) + r * p;
      total[t] = (total[t] ?? 0) + p;
    });
  });
  return {
    for (final v in liste)
      if ((total[v.ticker] ?? 0) > 0) v.ticker: somme[v.ticker]! / total[v.ticker]! + (v.n('score') ?? 0) / 1e4,
  };
}
