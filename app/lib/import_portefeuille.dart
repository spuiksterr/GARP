/// Import d'un portefeuille depuis ce que l'utilisateur a sous la main : export CSV du courtier, tableau copié
/// d'Excel ou du site du courtier, ou simple liste « ticker ; poids ».
///
/// Trois étapes, sans réseau : lire le tableau (séparateur et ligne d'en-tête devinés), reconnaître chaque ligne
/// parmi les valeurs des données (ISIN déjà vu, ticker, puis nom), calculer les poids (poids donnés, sinon montants,
/// sinon quantités × cours en euros). L'utilisateur vérifie ensuite le résultat avant de l'enregistrer.
library;

import 'donnees.dart';

enum Confiance { sure, probable, aucune }

class LigneImportee {
  LigneImportee({required this.libelle, this.isin, this.tickerFichier, this.taille, this.quantite, this.prix});

  /// Nom de la ligne tel qu'écrit dans le fichier (ou son ticker, ou son ISIN).
  final String libelle;
  final String? isin;
  final String? tickerFichier;

  /// Poids ou montant (proportionnels au poids), s'ils figurent dans le fichier.
  final double? taille;
  final double? quantite;

  /// Cours donné par le fichier (même devise pour toutes les lignes, en pratique l'euro).
  final double? prix;

  /// Valeur des données retenue (null : ligne gardée hors des données, par exemple un fonds ou de l'or).
  String? ticker;
  Confiance confiance = Confiance.aucune;
  bool ignoree = false;

  /// Poids en % du portefeuille importé, calculé par [calculerPoids].
  double poids = 0;

  /// Clé sous laquelle l'appareil retient la correspondance choisie (ISIN, sinon nom normalisé).
  String get cle => isin ?? normaliser(libelle);

  /// Identifiant de la ligne dans le portefeuille : le ticker, sinon l'ISIN, sinon le libellé.
  String get identifiant => ticker ?? isin ?? libelle.toUpperCase();
}

class ResultatImport {
  ResultatImport(this.lignes, this.methode);

  final List<LigneImportee> lignes;

  /// Comment les poids ont été obtenus, pour l'expliquer à l'utilisateur.
  final String methode;

  Iterable<LigneImportee> get retenues => lignes.where((l) => !l.ignoree);
}

// ---------------------------------------------------------------------------------------------- lecture du tableau

final _isin = RegExp(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$');

/// Minuscules sans accents ni ponctuation, espaces simples.
String normaliser(String s) {
  const avec = 'àâäáãåçéèêëíìîïñóòôöõúùûüýÿœæ';
  const sans = 'aaaaaaceeeeiiiinooooouuuuyyoa';
  final b = StringBuffer();
  for (final c in s.toLowerCase().split('')) {
    final i = avec.indexOf(c);
    b.write(i >= 0 ? sans[i] : c);
  }
  return b.toString().replaceAll(RegExp(r'[^a-z0-9%]+'), ' ').trim();
}

/// Nombre écrit à la française ou à l'anglaise : « 1 234,56 € », « 1,234.56 », « 34,5 % », « 1’234.5 ».
double? lireNombre(String brut) {
  // \s couvre aussi les espaces insécables qui séparent les milliers.
  var s = brut.trim().replaceAll(RegExp(r"[\s’'€$£%]|EUR|USD|GBP|CHF", caseSensitive: false), '');
  if (s.isEmpty || !RegExp(r'^[-+(]?[0-9.,]+\)?$').hasMatch(s)) return null;
  final negatif = s.startsWith('-') || s.startsWith('(');
  s = s.replaceAll(RegExp(r'[-+()]'), '');
  final virgule = s.lastIndexOf(','), point = s.lastIndexOf('.');
  if (virgule >= 0 && point >= 0) {
    // Le dernier des deux sépare les décimales.
    s = virgule > point ? s.replaceAll('.', '').replaceAll(',', '.') : s.replaceAll(',', '');
  } else if (virgule >= 0) {
    s = ','.allMatches(s).length > 1 ? s.replaceAll(',', '') : s.replaceAll(',', '.');
  } else if ('.'.allMatches(s).length > 1) {
    s = s.replaceAll('.', '');
  }
  final v = double.tryParse(s);
  return v == null ? null : (negatif ? -v : v);
}

List<String> _decouper(String ligne, String sep) {
  final out = <String>[];
  final b = StringBuffer();
  var guillemets = false;
  for (var i = 0; i < ligne.length; i++) {
    final c = ligne[i];
    if (c == '"') {
      if (guillemets && i + 1 < ligne.length && ligne[i + 1] == '"') {
        b.write('"');
        i++;
      } else {
        guillemets = !guillemets;
      }
    } else if (c == sep && !guillemets) {
      out.add(b.toString().trim());
      b.clear();
    } else {
      b.write(c);
    }
  }
  out.add(b.toString().trim());
  return out;
}

/// Découpe le texte en lignes et cellules. Séparateur deviné parmi tabulation, point-virgule, barre et virgule ;
/// à défaut (liste tapée à la main), chaque ligne devient « libellé, nombre ».
List<List<String>> lireTableau(String texte) {
  final lignes = texte.replaceAll('﻿', '').split(RegExp(r'\r\n|\r|\n')).where((l) => l.trim().isNotEmpty).toList();
  if (lignes.isEmpty) return [];
  final echantillon = lignes.take(30).toList();
  String? meilleur;
  var meilleurScore = 0.0;
  for (final sep in ['\t', ';', '|', ',']) {
    final comptes = [for (final l in echantillon) _decouper(l, sep).length - 1];
    final avec = comptes.where((n) => n > 0).length;
    // Part des lignes découpées ; la virgule, qui sert aussi aux décimales, ne gagne qu'à défaut d'autre.
    final score = avec / echantillon.length - (sep == ',' ? 0.3 : 0);
    if (avec > 0 && score > meilleurScore) {
      meilleur = sep;
      meilleurScore = score;
    }
  }
  if (meilleur != null && meilleurScore >= 0.5) {
    return [for (final l in lignes) _decouper(l, meilleur)];
  }
  final libre = RegExp(r'^(.*?)[\s:=]+([-+]?[0-9][0-9  .,’]*\s*%?)$');
  return [
    for (final l in lignes)
      if (libre.firstMatch(l.trim()) case final m?) [m.group(1)!.trim(), m.group(2)!.trim()] else [l.trim()],
  ];
}

// ---------------------------------------------------------------------------------------------- colonnes

enum Role { isin, ticker, nom, poids, montant, quantite, prix }

bool _contient(String entete, List<String> mots) => mots.any((m) => entete == m || entete.contains(m));

/// Rôle d'une colonne d'après son en-tête (null si inutile pour l'import).
Role? roleColonne(String entete) {
  final e = normaliser(entete);
  if (e.isEmpty) return null;
  if (e.contains('isin')) return Role.isin;
  // Performances, plus-values et prix de revient ne disent rien du poids actuel.
  if (RegExp(r'\+\s*/?\s*[-−]').hasMatch(entete) || _contient(e, ['plus value', 'plus ou moins', 'perf', 'variation', 'var ', 'gain', 'latent',
    'revient', 'pru', 'prix moyen', 'achat', 'investi', 'frais', 'date', 'devise'])) {
    return null;
  }
  if (_contient(e, ['ticker', 'symbole', 'symbol', 'mnemo', 'code valeur', 'code'])) return Role.ticker;
  if (_contient(e, ['poids', 'weight', 'repartition', 'allocation', 'part du portefeuille', '% du', 'pourcentage']) ||
      e == '%' || e == 'part') {
    return Role.poids;
  }
  if (_contient(e, ['quantite', 'qte', 'qty', 'quantity', 'nombre de', 'nombre', 'nb titres', 'shares', 'parts'])) {
    return Role.quantite;
  }
  if (_contient(e, ['montant', 'valorisation', 'valeur en', 'valeur eur', 'valeur totale', 'valeur actuelle',
    'valeur de marche', 'market value', 'evaluation', 'encours', 'total', 'solde', 'value'])) {
    return Role.montant;
  }
  if (_contient(e, ['cours', 'prix', 'price', 'dernier', 'cloture', 'close'])) return Role.prix;
  if (_contient(e, ['nom', 'libelle', 'produit', 'instrument', 'designation', 'name', 'titre', 'actif', 'support',
    'societe', 'entreprise', 'description']) || e == 'valeur' || e == 'valeurs') {
    return Role.nom;
  }
  return null;
}

/// Ligne d'en-tête : la première (parmi les 15 premières) dont au moins deux colonnes ont un rôle.
(int, Map<Role, int>)? enTete(List<List<String>> tableau) {
  for (var i = 0; i < tableau.length && i < 15; i++) {
    final roles = <Role, int>{};
    for (var j = 0; j < tableau[i].length; j++) {
      final r = roleColonne(tableau[i][j]);
      if (r == null || lireNombre(tableau[i][j]) != null) continue;
      // Montant : préférer la colonne en euros quand il y en a plusieurs.
      if (r == Role.montant && roles.containsKey(r) && !normaliser(tableau[i][j]).contains('eur')) continue;
      if (roles.containsKey(r) && r != Role.montant) continue;
      roles[r] = j;
    }
    final identifie = roles.containsKey(Role.nom) || roles.containsKey(Role.ticker) || roles.containsKey(Role.isin);
    if (roles.length >= 2 && identifie) return (i, roles);
  }
  return null;
}

bool _total(String s) => RegExp(r'^(sous )?total|^totaux|^ensemble').hasMatch(normaliser(s));

bool _liquidites(String s) =>
    RegExp(r'liquidit|especes|^cash|solde|compte espece|fonds disponibles').hasMatch(normaliser(s));

/// Lignes du fichier, avant reconnaissance.
List<LigneImportee> lignesDuTableau(List<List<String>> tableau) {
  final out = <LigneImportee>[];
  final entete = enTete(tableau);
  if (entete != null) {
    final (debut, roles) = entete;
    String? cellule(List<String> l, Role r) {
      final j = roles[r];
      return j == null || j >= l.length || l[j].isEmpty ? null : l[j];
    }

    for (final l in tableau.skip(debut + 1)) {
      // Un ISIN peut aussi être dans la colonne « Symbole/ISIN » ou ailleurs.
      final isin = [cellule(l, Role.isin), ...l].whereType<String>().map((c) => c.trim().toUpperCase())
          .where(_isin.hasMatch).firstOrNull;
      final tickerBrut = cellule(l, Role.ticker)?.toUpperCase();
      final ticker = tickerBrut != null && !_isin.hasMatch(tickerBrut) ? tickerBrut : null;
      final nom = cellule(l, Role.nom);
      final libelle = nom ?? ticker ?? isin;
      if (libelle == null || _total(libelle)) continue;
      final ligne = LigneImportee(
        libelle: libelle,
        isin: isin,
        tickerFichier: ticker,
        taille: lireNombre(cellule(l, Role.poids) ?? '') ?? lireNombre(cellule(l, Role.montant) ?? ''),
        quantite: lireNombre(cellule(l, Role.quantite) ?? ''),
        prix: lireNombre(cellule(l, Role.prix) ?? ''),
      );
      // Notes de bas de tableau : ni identifiant ni chiffre.
      if (isin == null && ticker == null && ligne.taille == null && ligne.quantite == null) continue;
      if (_liquidites(libelle) && isin == null) ligne.ignoree = true;
      out.add(ligne);
    }
    return out;
  }
  // Sans en-tête : le premier texte est le libellé, le dernier nombre le poids (ou le montant).
  for (final l in tableau) {
    final textes = <String>[];
    double? nombre;
    String? isin;
    for (final c in l) {
      if (c.isEmpty) continue;
      final n = lireNombre(c);
      if (n != null) {
        nombre = n;
      } else if (_isin.hasMatch(c.toUpperCase())) {
        isin = c.toUpperCase();
      } else {
        textes.add(c);
      }
    }
    final libelle = textes.firstOrNull ?? isin;
    if (libelle == null || _total(libelle)) continue;
    final ticker = RegExp(r'^[A-Za-z0-9]{1,6}([.-][A-Za-z]{1,3})?$').hasMatch(libelle) ? libelle.toUpperCase() : null;
    final ligne = LigneImportee(libelle: libelle, isin: isin, tickerFichier: ticker, taille: nombre);
    if (_liquidites(libelle) && isin == null) ligne.ignoree = true;
    out.add(ligne);
  }
  return out;
}

// ---------------------------------------------------------------------------------------------- reconnaissance

/// Pays d'immatriculation d'après les deux lettres de l'ISIN, dans les noms des données.
const paysIsin = {
  'US': 'États-Unis', 'FR': 'France', 'DE': 'Allemagne', 'GB': 'Royaume-Uni', 'CH': 'Suisse', 'NL': 'Pays-Bas',
  'IT': 'Italie', 'ES': 'Espagne', 'SE': 'Suède', 'DK': 'Danemark', 'NO': 'Norvège', 'FI': 'Finlande',
  'BE': 'Belgique', 'IE': 'Irlande', 'AT': 'Autriche', 'PT': 'Portugal', 'PL': 'Pologne', 'GR': 'Grèce',
  'LU': 'Luxembourg', 'JE': 'Jersey', 'GG': 'Guernesey', 'BM': 'Bermudes', 'KY': 'Îles Caïmans', 'CA': 'Canada',
  'IL': 'Israël', 'CN': 'Chine', 'HK': 'Hong Kong', 'TW': 'Taïwan', 'SG': 'Singapour', 'JP': 'Japon',
  'KR': 'Corée du Sud', 'IN': 'Inde', 'AU': 'Australie', 'BR': 'Brésil', 'AR': 'Argentine', 'UY': 'Uruguay',
  'MX': 'Mexique', 'CY': 'Chypre',
};

/// Mots qui ne distinguent pas une société d'une autre.
const _vides = {
  'inc', 'incorporated', 'corp', 'corporation', 'co', 'company', 'cie', 'sa', 'se', 'plc', 'ag', 'nv', 'spa',
  'ltd', 'limited', 'holding', 'holdings', 'group', 'groupe', 'the', 'de', 'du', 'des', 'la', 'le', 'les', 'et',
  'and', 'of', 'cl', 'class', 'classe', 'ord', 'shs', 'reg', 'registered', 'act', 'action', 'actions', 'adr',
  'sca', 'asa', 'ab', 'as', 'oyj', 'bv', 'kgaa', 'llc', 'lp', 'publ', 'a', 'b', 'c', 'com', 'new', 'eo', 'ns',
};

/// Fonds et matières premières : à ne pas confondre avec une société (« Amundi MSCI World » n'est pas Amundi).
final _motsFonds = RegExp(
    r'\b(etf|etc|etn|ucits|sicav|fcp|opcvm|ishares|xtrackers|lyxor|vanguard|spdr|wisdomtree|invesco|vaneck|'
    r'global x|amundi (msci|index|stoxx|s ?p|nasdaq|etf)|msci|s ?p 500|stoxx|nasdaq 100|physical|tracker)\b');

Set<String> _mots(String nom) => {
      for (final m in normaliser(nom).split(' '))
        if (m.isNotEmpty && !_vides.contains(m)) m,
    };

bool _memeMot(String a, String b) =>
    a == b || (a.length >= 4 && b.length >= 4 && (a.startsWith(b) || b.startsWith(a)));

/// Ressemblance de deux noms entre 0 et 1 : part des mots significatifs communs.
double ressemblance(String a, String b) {
  final ma = _mots(a), mb = _mots(b);
  if (ma.isEmpty || mb.isEmpty) return 0;
  final communs = ma.where((x) => mb.any((y) => _memeMot(x, y))).length;
  return communs / (ma.length > mb.length ? ma.length : mb.length);
}

class Reconnaissance {
  Reconnaissance(this.donnees, {this.correspondances = const {}});

  final Donnees donnees;

  /// Choix déjà faits sur cet appareil : clé de ligne -> ticker ('' : garder hors des données).
  final Map<String, String> correspondances;

  late final Map<String, List<Valeur>> _parBase = () {
    final m = <String, List<Valeur>>{};
    for (final v in donnees.valeurs.values) {
      m.putIfAbsent(v.ticker.split('.').first.replaceAll('-', '.'), () => []).add(v);
      m.putIfAbsent(v.ticker.split('.').first, () => []).add(v);
    }
    return m;
  }();

  Valeur? _parPays(List<Valeur> candidats, String? pays) {
    if (candidats.length == 1) return candidats.first;
    final memePays = candidats.where((v) => pays != null && v.pays == pays).toList();
    return memePays.length == 1 ? memePays.first : null;
  }

  void reconnaitre(LigneImportee l) {
    final deja = correspondances[l.cle];
    if (deja != null) {
      l.ticker = deja.isEmpty || !donnees.valeurs.containsKey(deja) ? null : deja;
      l.confiance = l.ticker == null ? Confiance.aucune : Confiance.sure;
      return;
    }
    final pays = l.isin == null ? null : paysIsin[l.isin!.substring(0, 2)];
    for (final t in [l.tickerFichier, l.libelle.toUpperCase()].whereType<String>()) {
      if (donnees.valeurs.containsKey(t)) {
        l.ticker = t;
        l.confiance = Confiance.sure;
        return;
      }
    }
    // Ticker sans la place de cotation (« AI » pour « AI.PA ») : départagé par le pays de l'ISIN.
    final base = l.tickerFichier?.split(RegExp(r'[.:\s]')).first;
    if (base != null && base.isNotEmpty) {
      final v = _parPays((_parBase[base] ?? []).toSet().toList(), pays);
      if (v != null) {
        l.ticker = v.ticker;
        l.confiance = pays != null && v.pays == pays ? Confiance.sure : Confiance.probable;
        return;
      }
    }
    final fonds = _motsFonds.hasMatch(normaliser(l.libelle));
    Valeur? meilleure;
    var score = 0.0, second = 0.0;
    for (final v in donnees.valeurs.values) {
      if (fonds != v.fonds) continue;
      var s = ressemblance(l.libelle, v.nom);
      if (s == 0) continue;
      if (pays != null) s += v.pays == pays ? 0.15 : -0.15;
      if (s > score) {
        second = score;
        score = s;
        meilleure = v;
      } else if (s > second) {
        second = s;
      }
    }
    if (meilleure != null && score >= 0.5) {
      l.ticker = meilleure.ticker;
      l.confiance = score >= 0.99 && score - second >= 0.3 ? Confiance.sure : Confiance.probable;
    }
  }
}

// ---------------------------------------------------------------------------------------------- poids

/// Poids en % des lignes retenues : poids ou montants du fichier, sinon quantités × cours (du fichier, sinon
/// cours en euros des données), sinon parts égales. Renvoie la méthode employée.
String calculerPoids(List<LigneImportee> lignes, Donnees? donnees) {
  final retenues = lignes.where((l) => !l.ignoree).toList();
  final tailles = <LigneImportee, double>{};
  String methode;
  if (retenues.any((l) => l.taille != null && l.taille! > 0)) {
    methode = 'poids ou montants du fichier';
    for (final l in retenues) {
      tailles[l] = l.taille ?? 0;
    }
  } else if (retenues.any((l) => l.quantite != null)) {
    methode = 'quantités × derniers cours';
    for (final l in retenues) {
      final cours = l.prix ?? (l.ticker == null ? null : donnees?.valeurs[l.ticker!]?.n('cours_eur'));
      tailles[l] = l.quantite != null && cours != null ? l.quantite! * cours : 0;
    }
  } else {
    methode = 'parts égales (le fichier ne donne ni poids ni montant)';
    for (final l in retenues) {
      tailles[l] = 1;
    }
  }
  final total = tailles.values.fold<double>(0, (s, x) => s + (x > 0 ? x : 0));
  for (final l in lignes) {
    final t = tailles[l] ?? 0;
    l.poids = total > 0 && t > 0 ? t / total * 100 : 0;
  }
  return methode;
}

/// Tout le trajet : texte -> lignes reconnues et pondérées. Les doublons (même valeur dans deux comptes) sont
/// regroupés quand le fichier donne des montants ou des quantités.
ResultatImport importer(String texte, Donnees? donnees, {Map<String, String> correspondances = const {}}) {
  final lignes = lignesDuTableau(lireTableau(texte));
  if (donnees != null) {
    final r = Reconnaissance(donnees, correspondances: correspondances);
    lignes.forEach(r.reconnaitre);
  }
  return ResultatImport(lignes, calculerPoids(lignes, donnees));
}
