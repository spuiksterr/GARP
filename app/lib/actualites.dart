/// Fil d'actualité des valeurs suivies (lignes et watchlist), comme pf/actualites.py :
/// - presse : Google Actualités en français (flux RSS public, usage personnel), recherché sur le nom de la
///   société ; seuls les titres qui citent ce nom sont gardés. Titre, journal, date et lien : pas le texte.
///   La recherche envoie à Google le nom d'une société, jamais le portefeuille ni ses montants ;
/// - signaux tirés des données, sans accès réseau : prix visé atteint, forte variation, sortie des filtres,
///   condition de vente atteinte, cours hors des scénarios, achats de dirigeants, mouvements des grands
///   investisseurs.
library;

import 'dart:convert';
import 'dart:io';

import 'etat.dart';
import 'formats.dart';
import 'suivi.dart';
import 'valorisation.dart';

class Article {
  Article(this.date, this.source, this.titre, this.lien, {this.ticker, this.type = 'Presse', this.detail = ''});

  final DateTime date;
  final String source;
  final String titre;
  final String lien;
  final String? ticker;

  /// « Presse », « Signal » (daté) ou « À surveiller » (état du jour).
  final String type;
  final String detail;
}

final _pageDeCours = RegExp(r"cours (de l'|de l’)?action|cotation|\| cours|stock price|share price", caseSensitive: false);

String _texte(String html) => html
    .replaceAll('<![CDATA[', '')
    .replaceAll(']]>', '')
    .replaceAll('&amp;', '&')
    .replaceAll('&quot;', '"')
    .replaceAll('&#39;', "'")
    .replaceAll('&apos;', "'")
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .trim();

/// Articles d'un flux RSS Google Actualités dont le titre cite l'un des `mots` (en minuscules).
List<Article> analyserRss(String xml, List<String> mots, {String? ticker}) {
  final articles = <Article>[];
  for (final item in RegExp(r'<item>(.*?)</item>', dotAll: true).allMatches(xml)) {
    String champ(String balise) =>
        _texte(RegExp('<$balise[^>]*>(.*?)</$balise>', dotAll: true).firstMatch(item.group(1)!)?.group(1) ?? '');
    var titre = champ('title');
    final source = champ('source');
    // Google ajoute « - Journal » à la fin du titre.
    if (source.isNotEmpty && titre.endsWith(' - $source')) titre = titre.substring(0, titre.length - source.length - 3);
    if (!mots.any(titre.toLowerCase().contains) || _pageDeCours.hasMatch(titre)) continue;
    DateTime date;
    try {
      date = HttpDate.parse(champ('pubDate'));
    } catch (_) {
      continue;
    }
    articles.add(Article(date, source.isEmpty ? 'Presse' : source, titre, champ('link'), ticker: ticker));
  }
  return articles;
}

const _contexte = '(action OR bourse OR résultats OR actionnaires OR "chiffre d\'affaires" OR cours OR analystes)';

/// Nom à chercher dans la presse : sans la forme sociale ni la classe d'actions.
String nomDePresse(String nom) => nom
    .replaceAll(RegExp(r'\s+(SA|SE|AG|NV|N\.V\.|PLC|Inc\.?|Corp\.?|Corporation|Co\.?|Ltd\.?|Holdings?|Group|S\.p\.A\.|AB|ASA|A/S)\b\.?',
        caseSensitive: false), '')
    .replaceAll(RegExp(r'\s+\(?(Class|Classe|Cl\.?)\s+[A-C]\)?$', caseSensitive: false), '')
    .trim();

/// Articles des 30 derniers jours sur une société (un appel au flux RSS de Google Actualités).
Future<List<Article>> presse(String nom, {String? ticker, int jours = 30}) async {
  final cherche = nomDePresse(nom);
  final uri = Uri.https('news.google.com', '/rss/search',
      {'q': '"$cherche" $_contexte when:${jours}d', 'hl': 'fr', 'gl': 'FR', 'ceid': 'FR:fr'});
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 20);
  try {
    final requete = await client.getUrl(uri);
    requete.headers.set('User-Agent', 'Mozilla/5.0 (compatible; climax-app/1.0)');
    final reponse = await requete.close();
    if (reponse.statusCode != 200) return [];
    final xml = await utf8.decoder.bind(reponse).join();
    return analyserRss(xml, [cherche.toLowerCase()], ticker: ticker);
  } finally {
    client.close();
  }
}

/// Valeurs suivies présentes dans les données : lignes du portefeuille, puis watchlist.
List<String> tickersSuivis(Etat e) => {
      for (final l in e.portefeuille) l.ticker,
      for (final s in e.watchlist) s.ticker,
    }.where((t) => e.donnees?.valeurs.containsKey(t) ?? false).toList();

/// Signaux tirés des données pour les valeurs suivies (aucun accès réseau).
List<Article> signaux(Etat e) {
  final d = e.donnees;
  if (d == null) return [];
  final out = <Article>[];
  final maintenant = DateTime.now();
  final suivis = tickersSuivis(e);
  String nom(String t) => d.valeurs[t]?.nom ?? t;
  void surveiller(String t, String source, String titre, [String detail = '']) =>
      out.add(Article(maintenant, source, '${nom(t)} : $titre', '', ticker: t, type: 'À surveiller', detail: detail));

  for (final (s, v) in e.prixVisesAtteints) {
    surveiller(v.ticker, 'Watchlist',
        'prix visé atteint, cours ${nombre(v.n('cours'), 2)} pour ${nombre(s.prixVise, 2)} visé', s.objectif ?? '');
  }
  for (final r in e.regles) {
    final (valeur, statut) = evaluerRegle(r, d);
    if (statut == 'Atteinte') {
      surveiller(r.ticker, 'Condition de vente', '${texteRegle(r)} (actuellement $valeur)', 'Relisez votre thèse.');
    }
  }
  for (final t in suivis) {
    final v = d.valeurs[t]!;
    final p1 = v.n('perf_1m');
    if (p1 != null && p1.abs() >= 0.15) {
      surveiller(t, 'Cours', '${p1 > 0 ? 'forte hausse' : 'forte baisse'}, ${pct(p1, 0, true)} sur un mois');
    }
    if (v.statut == 'Exclu') surveiller(t, 'Filtres', 'hors des filtres de qualité', v.motifsExclusion ?? '');
    // Cours hors des bornes de vos scénarios enregistrés (prix à 5 ans, pessimiste et optimiste).
    final sc = e.scenarios[t] as Map<String, dynamic>?;
    final cours = v.n('cours');
    if (sc != null && cours != null) {
      final h = sc['hypotheses'] as Map<String, dynamic>;
      double? prix(String n) => h[n] == null ? null : prixFutur(v, Hypotheses.depuisJson(h[n] as Map<String, dynamic>));
      final haut = prix('Optimiste'), bas = prix('Pessimiste');
      if (haut != null && cours > haut) surveiller(t, 'Scénarios', 'cours au-dessus de votre prix optimiste à 5 ans');
      if (bas != null && cours < bas) surveiller(t, 'Scénarios', 'cours sous votre prix pessimiste à 5 ans');
    }
    final dir = e.complements?.fiche(t)?['d'] as Map<String, dynamic>?;
    for (final x in (dir?['transactions'] as List?) ?? const []) {
      if (x['code'] != 'P') continue;
      out.add(Article(DateTime.tryParse('${x['date']}') ?? maintenant, 'Dirigeants (SEC)',
          '${nom(t)} : achat en bourse par ${x['nom']} (${x['fonction'] ?? 'dirigeant'})', '',
          ticker: t, type: 'Signal'));
    }
  }
  const verbes = {'Nouvelle': 'entre sur', 'Renforcée': 'renforce', 'Allégée': 'allège', 'Soldée': 'sort de'};
  for (final i in e.complements?.listeInvestisseurs ?? const <Map<String, dynamic>>[]) {
    for (final l in i['lignes'] as List) {
      final t = l['ticker'];
      if (t is! String || !suivis.contains(t) || !verbes.containsKey(l['mouvement'])) continue;
      out.add(Article(DateTime.tryParse('${i['periode']}') ?? maintenant, 'Grands investisseurs (13F)',
          '${i['investisseur']} ${verbes[l['mouvement']]} ${nom(t)}', '',
          ticker: t, type: 'Signal', detail: 'trimestre clos le ${dateFr(i['periode'] as String?)}'));
    }
  }
  return out;
}
