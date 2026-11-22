/// Accès au dépôt GitHub privé : releases « donnees » (fichier de données) et « app-b… » (versions de l'application).
///
/// Le jeton (lecture seule, propre à cet appareil) n'est envoyé qu'à api.github.com : les téléchargements sont
/// redirigés vers un stockage de GitHub, que l'on suit à la main sans le jeton.
library;

import 'dart:convert';
import 'dart:io';

/// Page de création d'un jeton à grain fin, pré-remplie (nom, propriétaire, durée, lecture du contenu) :
/// il ne reste qu'à choisir le dépôt et valider.
Uri urlCreationJeton(String depot) => Uri.https('github.com', '/settings/personal-access-tokens/new', {
      'name': 'G.A.R.P',
      'description': 'Lecture des données de l\'application G.A.R.P',
      'target_name': depot.split('/').first,
      'expires_in': '365',
      'contents': 'read',
    });

class ErreurGitHub implements Exception {
  ErreurGitHub(this.message);

  final String message;

  @override
  String toString() => message;
}

class Asset {
  Asset(this.id, this.nom, this.taille);

  final int id;
  final String nom;
  final int taille;
}

class Release {
  Release(this.tag, this.titre, this.notes, this.assets);

  final String tag;
  final String titre;
  final String notes;
  final List<Asset> assets;

  /// Numéro de version des releases de l'application : « app-b42 » -> 42.
  int? get numero => tag.startsWith('app-b') ? int.tryParse(tag.substring(5)) : null;

  Asset? asset(bool Function(String nom) choix) {
    for (final a in assets) {
      if (choix(a.nom)) return a;
    }
    return null;
  }
}

class GitHub {
  GitHub(this.depot, this.jeton);

  final String depot; // « propriétaire/dépôt »
  final String jeton;

  static const _api = 'api.github.com';

  /// Le jeton n'est joint qu'aux requêtes vers api.github.com, jamais aux redirections vers le stockage.
  Future<HttpClientResponse> _envoyer(Uri uri, {Map<String, String> entetes = const {}, bool avecJeton = true}) async {
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 20);
    final requete = await client.getUrl(uri);
    requete.followRedirects = false;
    requete.headers.set('User-Agent', 'garp-app');
    if (avecJeton && uri.host == _api) requete.headers.set('Authorization', 'Bearer $jeton');
    entetes.forEach(requete.headers.set);
    return requete.close();
  }

  Future<List<int>> _octets(HttpClientResponse r) async {
    final morceaux = <int>[];
    await for (final m in r) {
      morceaux.addAll(m);
    }
    return morceaux;
  }

  Future<dynamic> _json(String chemin) async {
    final r = await _envoyer(Uri.https(_api, '/repos/$depot$chemin'), entetes: {
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    });
    final corps = utf8.decode(await _octets(r));
    if (r.statusCode == 401) throw ErreurGitHub('Jeton refusé par GitHub : vérifiez-le dans les réglages.');
    if (r.statusCode == 404) {
      throw ErreurGitHub('Introuvable sur GitHub ($depot$chemin) : dépôt mal saisi, ou jeton sans accès à ce dépôt.');
    }
    if (r.statusCode != 200) throw ErreurGitHub('GitHub a répondu ${r.statusCode}.');
    return jsonDecode(corps);
  }

  Release _release(Map<String, dynamic> j) => Release(
        j['tag_name'] as String,
        (j['name'] as String?) ?? (j['tag_name'] as String),
        (j['body'] as String?) ?? '',
        [
          for (final a in (j['assets'] as List))
            Asset((a['id'] as num).toInt(), a['name'] as String, (a['size'] as num).toInt()),
        ],
      );

  Future<Release> release(String tag) async =>
      _release(await _json('/releases/tags/$tag') as Map<String, dynamic>);

  /// Dernière version publiée de l'application (release `app-b<numéro>` la plus récente).
  Future<Release?> derniereVersionApp() async {
    final liste = await _json('/releases?per_page=30') as List;
    Release? meilleure;
    for (final j in liste) {
      final r = _release(j as Map<String, dynamic>);
      if (r.numero != null && (meilleure == null || r.numero! > meilleure.numero!)) meilleure = r;
    }
    return meilleure;
  }

  /// Contenu d'un fichier joint à une release (redirection suivie sans le jeton).
  Future<List<int>> telecharger(Asset asset, {void Function(double)? progression}) async {
    var r = await _envoyer(Uri.https(_api, '/repos/$depot/releases/assets/${asset.id}'),
        entetes: {'Accept': 'application/octet-stream'});
    for (var i = 0; i < 5 && r.isRedirect; i++) {
      final cible = r.headers.value(HttpHeaders.locationHeader);
      await r.drain<void>();
      if (cible == null) break;
      r = await _envoyer(Uri.parse(cible), avecJeton: false);
    }
    if (r.statusCode != 200) throw ErreurGitHub('Téléchargement refusé (${r.statusCode}).');
    final total = r.contentLength > 0 ? r.contentLength : asset.taille;
    final morceaux = <int>[];
    await for (final m in r) {
      morceaux.addAll(m);
      if (progression != null && total > 0) progression(morceaux.length / total);
    }
    return morceaux;
  }
}
