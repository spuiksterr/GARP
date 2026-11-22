/// Mise en forme des nombres à la française, comme pf/formats.py : « 12,5 % », « 1 234,5 », « 12 345 € ».
library;

const String _espace = ' '; // espace fine insécable, séparateur des milliers
const String vide = '—';

double? nombreOuNul(Object? v) {
  if (v == null) return null;
  if (v is num) return v.isFinite ? v.toDouble() : null;
  return double.tryParse(v.toString());
}

String _milliers(String entier) {
  final negatif = entier.startsWith('-');
  final chiffres = negatif ? entier.substring(1) : entier;
  final morceaux = <String>[];
  for (var i = chiffres.length; i > 0; i -= 3) {
    morceaux.insert(0, chiffres.substring(i - 3 < 0 ? 0 : i - 3, i));
  }
  return (negatif ? '-' : '') + morceaux.join(_espace);
}

String nombre(Object? v, [int decimales = 1, String suffixe = '']) {
  final x = nombreOuNul(v);
  if (x == null) return vide;
  final texte = x.toStringAsFixed(decimales);
  final parties = texte.split('.');
  final entier = _milliers(parties[0]);
  final resultat = parties.length > 1 ? '$entier,${parties[1]}' : entier;
  return suffixe.isEmpty ? resultat : '$resultat$_espace$suffixe';
}

/// Fraction en pourcentage : 0.125 -> « 12,5 % ».
String pct(Object? v, [int decimales = 1, bool signe = false]) {
  final x = nombreOuNul(v);
  if (x == null) return vide;
  final texte = nombre(x * 100, decimales, '%');
  return signe && x > 0 ? '+$texte' : texte;
}

String euros(Object? v, [int decimales = 0]) => nombre(v, decimales, '€');

/// Montant en milliards d'euros : « 12,3 Md€ ».
String milliards(Object? v) {
  final x = nombreOuNul(v);
  return x == null ? vide : nombre(x / 1e9, 1, 'Md€');
}

/// Date ISO « 2026-11-13 » -> « 13/11/2026 ».
String dateFr(String? iso) {
  if (iso == null || iso.length < 10) return vide;
  return '${iso.substring(8, 10)}/${iso.substring(5, 7)}/${iso.substring(0, 4)}';
}
