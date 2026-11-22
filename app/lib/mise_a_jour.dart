/// Mise à jour de l'application depuis les Releases GitHub, comme CloudStream : on compare son numéro de version à
/// celui de la dernière release `app-b<numéro>`, puis on télécharge l'APK (Android) ou l'installateur (Windows).
library;

import 'dart:io';

import 'package:open_filex/open_filex.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'github.dart';

/// Page des téléchargements (dernière version de l'application, dépôt public).
const pageTelechargement = 'https://github.com/spuiksterr/GARP/releases/latest';

class NouvelleVersion {
  NouvelleVersion(this.release, this.asset, this.actuelle);

  final Release release;
  final Asset asset;
  final int actuelle;
}

Future<int> numeroInstalle() async => int.tryParse((await PackageInfo.fromPlatform()).buildNumber) ?? 0;

/// Fichier à télécharger : l'APK sur Android ; sur Windows l'installateur, sinon le zip portable.
Asset? fichierPourCetAppareil(Release r) {
  if (Platform.isAndroid) return r.asset((nom) => nom.endsWith('.apk'));
  return r.asset((nom) => nom.startsWith('GARP-Setup') && nom.endsWith('.exe')) ??
      r.asset((nom) => nom.endsWith('.zip'));
}

/// La dernière version publiée si elle est plus récente que celle installée, sinon null.
Future<NouvelleVersion?> chercher(GitHub gh) async {
  final derniere = await gh.derniereVersionApp();
  final actuelle = await numeroInstalle();
  if (derniere == null || (derniere.numero ?? 0) <= actuelle) return null;
  final asset = fichierPourCetAppareil(derniere);
  return asset == null ? null : NouvelleVersion(derniere, asset, actuelle);
}

/// Télécharge la nouvelle version puis lance son installation. Renvoie un message pour l'utilisateur.
/// Sur Windows, l'installateur tourne en silencieux : il ferme G.A.R.P, le remplace et le relance.
Future<String> installer(GitHub gh, NouvelleVersion v, void Function(double) progression) async {
  final octets = await gh.telecharger(v.asset, progression: progression);
  if (Platform.isAndroid) {
    final fichier = File('${(await getTemporaryDirectory()).path}/${v.asset.nom}');
    await fichier.writeAsBytes(octets, flush: true);
    final r = await OpenFilex.open(fichier.path, type: 'application/vnd.android.package-archive');
    return r.type == ResultType.done
        ? 'Installation lancée : validez-la. La première fois, Android demande d\'autoriser G.A.R.P à installer '
            'des applications.'
        : 'Installation impossible : ${r.message}';
  }
  if (v.asset.nom.endsWith('.exe')) {
    final fichier = File('${(await getTemporaryDirectory()).path}${Platform.pathSeparator}${v.asset.nom}');
    await fichier.writeAsBytes(octets, flush: true);
    await Process.start(fichier.path, ['/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS'],
        mode: ProcessStartMode.detached);
    // L'installateur remplace les fichiers de G.A.R.P : on lui laisse la place.
    exit(0);
  }
  final dossier = await getDownloadsDirectory() ?? await getTemporaryDirectory();
  final fichier = File('${dossier.path}${Platform.pathSeparator}${v.asset.nom}');
  await fichier.writeAsBytes(octets, flush: true);
  await launchUrl(Uri.directory(dossier.path));
  return 'Nouvelle version enregistrée dans ${fichier.path}. Fermez G.A.R.P, décompressez ce fichier à la place '
      'de l\'ancien dossier, puis relancez.';
}
