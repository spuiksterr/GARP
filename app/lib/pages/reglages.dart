import 'dart:io';

import 'package:material_ui/material_ui.dart';
import 'package:url_launcher/url_launcher.dart';

import '../formats.dart';
import '../github.dart';
import '../graphiques.dart';
import '../main.dart';
import '../mise_a_jour.dart' as maj;
import '../navigation.dart';
import '../widgets.dart';
import 'bienvenue.dart';

class Reglages extends StatefulWidget {
  const Reglages({super.key});

  @override
  State<Reglages> createState() => _ReglagesState();
}

class _ReglagesState extends State<Reglages> {
  final _jeton = TextEditingController();
  final _depot = TextEditingController();
  bool _masque = true;
  String? _messageMaj;
  double? _progression;
  int? _version;

  @override
  void initState() {
    super.initState();
    _jeton.text = etat.jeton ?? '';
    _depot.text = etat.depot;
    maj.numeroInstalle().then((n) => setState(() => _version = n));
  }

  Future<void> _enregistrer() async {
    await etat.reglerAcces(_jeton.text, _depot.text);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(etat.erreur ?? 'Accès enregistré, données téléchargées.'),
    ));
  }

  Future<void> _verifierMiseAJour() async {
    if (!etat.configure) return;
    setState(() => _messageMaj = 'Recherche d\'une nouvelle version…');
    try {
      final gh = GitHub(etat.depot, etat.jeton!);
      final nouvelle = await maj.chercher(gh);
      if (nouvelle == null) {
        setState(() => _messageMaj = 'G.A.R.P est à jour.');
        return;
      }
      setState(() => _messageMaj = '${nouvelle.release.titre} disponible : téléchargement…');
      final message = await maj.installer(gh, nouvelle, (p) => setState(() => _progression = p));
      setState(() {
        _progression = null;
        _messageMaj = message;
      });
    } catch (e) {
      setState(() {
        _progression = null;
        _messageMaj = 'Mise à jour impossible : $e';
      });
    }
  }

  Future<void> _effacer() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Tout effacer de cet appareil ?'),
        content: const Text('Portefeuille, watchlist et jeton GitHub seront supprimés de cet appareil.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Effacer')),
        ],
      ),
    );
    if (ok == true) {
      await etat.toutEffacer();
      _jeton.clear();
    }
  }

  @override
  Widget build(BuildContext context) {
    final texte = Theme.of(context).textTheme;
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) => PageDefilante(titre: 'Réglages', [
          Card.filled(
            margin: const EdgeInsets.only(bottom: 16),
            child: ListTile(
              leading: const Icon(Icons.person_outline),
              title: const Text('Mon profil investisseur'),
              subtitle: Text('Méthode : ${etat.donnees?.methode(etat.profil.methode).libelle ?? 'score composite'}'
                  ' · ${etat.profil.enveloppe == 'Toutes' ? 'PEA et CTO' : etat.profil.enveloppe}'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => aller(context, Rubrique.profil),
            ),
          ),
          Text('Accès aux données', style: texte.titleMedium),
          const SizedBox(height: 6),
          const Text('Les données sont publiées chaque nuit dans votre dépôt GitHub privé. Il faut un jeton en '
              'lecture seule, limité à ce dépôt : il reste stocké, chiffré, sur cet appareil.'),
          TextButton.icon(
            icon: const Icon(Icons.open_in_new),
            label: const Text('Créer un jeton sur GitHub'),
            onPressed: () => launchUrl(urlCreationJeton(_depot.text), mode: LaunchMode.externalApplication),
          ),
          TextField(
            controller: _depot,
            decoration: const InputDecoration(labelText: 'Dépôt', border: OutlineInputBorder(), isDense: true),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _jeton,
            obscureText: _masque,
            decoration: InputDecoration(
              labelText: 'Jeton GitHub (github_pat_…)',
              border: const OutlineInputBorder(),
              isDense: true,
              suffixIcon: IconButton(
                icon: Icon(_masque ? Icons.visibility : Icons.visibility_off),
                onPressed: () => setState(() => _masque = !_masque),
              ),
            ),
          ),
          const SizedBox(height: 8),
          FilledButton.icon(
            icon: const Icon(Icons.download),
            label: const Text('Enregistrer et télécharger les données'),
            onPressed: etat.enCours ? null : _enregistrer,
          ),
          if (etat.donnees != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text('Données au ${dateFr(etat.donnees!.donneesAu)}, publiées le '
                  '${dateFr(etat.donnees!.genereLe)}.', style: texte.bodySmall),
            ),
          const Divider(height: 32),
          Text('Application', style: texte.titleMedium),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Logo(taille: 44),
            title: Text('G.A.R.P, version ${_version ?? '…'}'),
            subtitle: const Text('Investir sur le temps long, avec méthode.'),
          ),
          TextButton.icon(
            icon: const Icon(Icons.waving_hand_outlined),
            label: const Text('Revoir l\'accueil'),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const Bienvenue())),
          ),
          const Divider(height: 32),
          Text('Installer G.A.R.P sur un autre appareil', style: texte.titleMedium),
          const SizedBox(height: 6),
          if (!Platform.isAndroid) ...[
            const Text('Visez ce code avec l\'appareil photo du téléphone : il ouvre la page de téléchargement '
                '(connectez-vous à GitHub), où se trouvent le fichier .apk pour Android et l\'installateur Windows.'),
            const SizedBox(height: 8),
            Image.asset('assets/qr-telechargement.png', width: 180, height: 180, semanticLabel: 'QR code'),
          ] else
            const Text('L\'installateur Windows et le fichier .apk sont sur la page de téléchargement '
                '(connectez-vous à GitHub).'),
          TextButton.icon(
            icon: const Icon(Icons.open_in_new),
            label: const Text('Page de téléchargement'),
            onPressed: () => launchUrl(Uri.parse(maj.pageTelechargement), mode: LaunchMode.externalApplication),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            icon: const Icon(Icons.system_update),
            label: const Text('Rechercher une mise à jour'),
            onPressed: etat.configure ? _verifierMiseAJour : null,
          ),
          if (_progression != null) LinearProgressIndicator(value: _progression),
          if (_messageMaj != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_messageMaj!)),
          const Divider(height: 32),
          Text('Données personnelles', style: texte.titleMedium),
          const Text('Le portefeuille et la watchlist ne quittent jamais cet appareil.'),
          TextButton.icon(
            icon: const Icon(Icons.delete_outline),
            label: const Text('Tout effacer de cet appareil'),
            onPressed: _effacer,
          ),
        ]),
    );
  }
}
