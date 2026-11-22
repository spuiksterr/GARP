/// Calculs sur le portefeuille saisi dans l'appareil, mêmes règles que l'application de bureau
/// (pf/portfolio.py, pf/risques.py : caractéristiques pondérées, garde-fous, points de vigilance).
library;

import 'donnees.dart';
import 'formats.dart';
import 'stockage.dart';


/// Poids normalisés (somme 1) des lignes connues des données.
Map<String, double> poidsNormalises(List<Ligne> lignes) {
  final total = lignes.fold<double>(0, (s, l) => s + l.poids);
  if (total <= 0) return {};
  return {for (final l in lignes) l.ticker: l.poids / total};
}

/// Moyenne pondérée d'un indicateur sur les lignes qui l'ont (null si aucune).
double? moyenne(Map<String, double> poids, Donnees d, String cle, {bool harmonique = false}) {
  var somme = 0.0, poidsUtiles = 0.0;
  poids.forEach((t, w) {
    final x = d.valeurs[t]?.n(cle);
    if (x == null || (harmonique && x <= 0)) return;
    somme += harmonique ? w / x : w * x;
    poidsUtiles += w;
  });
  if (poidsUtiles == 0) return null;
  return harmonique ? poidsUtiles / somme : somme / poidsUtiles;
}

Map<String, double> repartition(Map<String, double> poids, Donnees d, String Function(Valeur) cle) {
  final out = <String, double>{};
  poids.forEach((t, w) {
    final v = d.valeurs[t];
    final k = v == null ? 'Hors des données' : cle(v);
    out[k] = (out[k] ?? 0) + w;
  });
  final triee = out.entries.toList()..sort((a, b) => b.value.compareTo(a.value));
  return {for (final e in triee) e.key: e.value};
}

/// Seuils de concentration dépassés, d'après le profil (seuils par défaut sinon). `noms` : libellés des lignes
/// hors des données.
List<String> gardeFous(Map<String, double> poids, Donnees d, {Map<String, String> noms = const {}, Profil? profil}) {
  final p = profil ?? Profil();
  final ligneMax = p.ligneMax, troisPremieresMax = p.troisPremieresMax, secteurMax = p.secteurMax;
  final out = <String>[];
  final tries = poids.entries.toList()..sort((a, b) => b.value.compareTo(a.value));
  for (final e in tries) {
    if (e.value > ligneMax + 1e-9) {
      out.add('${d.valeurs[e.key]?.nom ?? noms[e.key] ?? e.key} pèse ${pct(e.value, 0)} du portefeuille (seuil ${pct(ligneMax, 0)}).');
    }
  }
  final trois = tries.take(3).fold<double>(0, (s, e) => s + e.value);
  if (tries.length > 3 && trois > troisPremieresMax + 1e-9) {
    out.add('Les trois premières lignes font ${pct(trois, 0)} du portefeuille (seuil ${pct(troisPremieresMax, 0)}).');
  }
  repartition(poids, d, (v) => v.secteur).forEach((secteur, w) {
    if (w > secteurMax + 1e-9) out.add('Le secteur $secteur fait ${pct(w, 0)} du portefeuille (seuil ${pct(secteurMax, 0)}).');
  });
  return out;
}

/// Points de vigilance par ligne : (ticker, type, message).
List<(String, String, String)> vigilance(Map<String, double> poids, Donnees d) {
  final out = <(String, String, String)>[];
  for (final t in poids.keys) {
    final v = d.valeurs[t];
    if (v == null) continue; // fonds, or, valeur non suivie : pas d'indicateurs à surveiller
    if (v.statut == 'Exclu') out.add((t, 'Thèse à revoir', 'Ne passe plus les filtres : ${v.motifsExclusion ?? ''}'));
    final p1 = v.n('perf_1m');
    if (p1 != null && p1 <= -0.15) out.add((t, 'Forte baisse', '${pct(p1, 0, true)} sur un mois : la thèse est-elle touchée ?'));
    if (p1 != null && p1 >= 0.25) out.add((t, 'Forte hausse', '${pct(p1, 0, true)} sur un mois : le poids dérive.'));
    final tri = v.n('tri_implicite');
    if (tri != null && tri < 0.06) {
      out.add((t, 'Valorisation', 'TRI implicite de ${pct(tri)} : beaucoup de croissance déjà dans le prix.'));
    }
  }
  return out;
}
