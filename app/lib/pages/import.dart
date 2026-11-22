/// Importer son portefeuille en quelques gestes : fichier du courtier, presse-papiers ou saisie, puis vérification
/// ligne par ligne avant d'enregistrer.
library;

import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../formats.dart';
import '../import_portefeuille.dart';
import '../interface.dart';
import '../main.dart';
import '../widgets.dart';

enum SourceImport { fichier, pressePapiers, saisie }

/// Texte d'un fichier : UTF-8, sinon l'encodage Windows des exports de courtiers français.
String decoderTexte(List<int> octets) {
  try {
    return utf8.decode(octets);
  } on FormatException {
    return latin1.decode(octets).replaceAll('\u0080', '€').replaceAll('\u0092', '’').replaceAll(' ', ' ');
  }
}

void _message(BuildContext context, String texte) =>
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(texte), duration: const Duration(seconds: 6)));

Future<String?> _saisir(BuildContext context, {String? explication}) {
  final champ = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Saisir ou coller mon portefeuille'),
      content: SizedBox(
        width: 460,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(explication ??
              'Une ligne par valeur : nom, ticker ou ISIN, puis le poids en %, le montant ou la quantité. '
                  'Un tableau copié depuis Excel ou le site du courtier convient aussi.'),
          const SizedBox(height: 12),
          TextField(
            controller: champ,
            maxLines: 10,
            autofocus: true,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              hintText: 'Alphabet 20\nAir Liquide 12\nUS0378331005 8\nNUKL.DE 5',
            ),
          ),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
        FilledButton(onPressed: () => Navigator.pop(context, champ.text), child: const Text('Continuer')),
      ],
    ),
  );
}

/// Lit le portefeuille depuis la source choisie et ouvre l'écran de vérification.
Future<void> importerPortefeuille(BuildContext context, SourceImport source) async {
  final textes = <String>[];
  switch (source) {
    case SourceImport.fichier:
      final fichiers = await FilePicker.pickFiles(
        dialogTitle: 'Export du portefeuille (CSV ou texte), un ou plusieurs comptes',
        // Android filtre mal les types CSV : tout est proposé, le contenu est vérifié ensuite.
        type: Platform.isAndroid ? FileType.any : FileType.custom,
        allowedExtensions: Platform.isAndroid ? null : ['csv', 'txt', 'tsv'],
      );
      for (final f in fichiers) {
        final octets = await f.readAsBytes();
        if (octets.length > 2 && octets[0] == 0x50 && octets[1] == 0x4B) {
          if (context.mounted) {
            _message(context, '${f.name} est un classeur Excel : ouvrez-le, sélectionnez le tableau, copiez-le, '
                'puis choisissez « Coller ». Ou enregistrez-le au format CSV.');
          }
          continue;
        }
        textes.add(decoderTexte(octets));
      }
    case SourceImport.pressePapiers:
      final texte = (await Clipboard.getData(Clipboard.kTextPlain))?.text ?? '';
      if (texte.trim().isEmpty) {
        if (!context.mounted) return;
        final saisi = await _saisir(context,
            explication: 'Le presse-papiers est vide. Copiez le tableau de vos positions (site du courtier, Excel), '
                'ou tapez vos lignes ici.');
        if (saisi != null) textes.add(saisi);
      } else {
        textes.add(texte);
      }
    case SourceImport.saisie:
      final saisi = await _saisir(context);
      if (saisi != null) textes.add(saisi);
  }
  if (textes.every((t) => t.trim().isEmpty) || !context.mounted) return;
  final r = etat.preparerImport(textes);
  if (r.lignes.isEmpty) {
    _message(context, 'Aucune ligne reconnue. Il faut au moins un nom, un ticker ou un ISIN par ligne.');
    return;
  }
  final enregistre = await Navigator.of(context).push<bool>(
    MaterialPageRoute(builder: (_) => VerificationImport(resultat: r), fullscreenDialog: true),
  );
  if (enregistre == true && context.mounted) {
    _message(context, 'Portefeuille enregistré : ${etat.portefeuille.length} lignes.');
  }
}

/// Les trois façons d'importer, en grandes cartes (portefeuille vide, écran d'accueil).
class ChoixImport extends StatelessWidget {
  const ChoixImport({this.apres, super.key});

  /// Appelé après un import (pour passer à l'étape suivante de l'accueil).
  final VoidCallback? apres;

  @override
  Widget build(BuildContext context) {
    Widget carte(IconData icone, String titre, String texte, SourceImport source) => Card.outlined(
          child: ListTile(
            leading: Icon(icone, size: 32, color: Theme.of(context).colorScheme.primary),
            title: Text(titre),
            subtitle: Text(texte),
            onTap: () async {
              await importerPortefeuille(context, source);
              if (etat.portefeuille.isNotEmpty) apres?.call();
            },
          ),
        );
    return Column(children: [
      carte(Icons.upload_file, 'Fichier de mon courtier',
          'Export CSV des positions (Boursorama, Degiro, Fortuneo, Saxo…), un ou plusieurs comptes.',
          SourceImport.fichier),
      carte(Icons.content_paste, 'Coller un tableau',
          'Copié depuis Excel ou la page « positions » du site du courtier.', SourceImport.pressePapiers),
      carte(Icons.edit_note, 'Saisir mes lignes',
          'Une ligne par valeur : nom ou ticker, puis poids, montant ou quantité.', SourceImport.saisie),
    ]);
  }
}

class VerificationImport extends StatefulWidget {
  const VerificationImport({required this.resultat, super.key});

  final ResultatImport resultat;

  @override
  State<VerificationImport> createState() => _VerificationImportState();
}

class _VerificationImportState extends State<VerificationImport> {
  late String _methode = widget.resultat.methode;

  List<LigneImportee> get _lignes => widget.resultat.lignes;

  void _recalculer() => setState(() => _methode = calculerPoids(_lignes, etat.donnees));

  Future<void> _corriger(LigneImportee l) async {
    final choix = await choisirValeur(context,
        recherche: l.tickerFichier ?? l.libelle, titre: 'Quelle valeur est « ${l.libelle} » ?', pourImport: true);
    if (choix == null) return;
    switch (choix) {
      case ChoixValeur(:final valeur):
        l.ticker = valeur.ticker;
        l.confiance = Confiance.sure;
        l.ignoree = false;
      case ChoixHorsDonnees():
        l.ticker = null;
        l.confiance = Confiance.aucune;
        l.ignoree = false;
      case ChoixIgnorer():
        l.ignoree = true;
    }
    _recalculer();
  }

  Future<void> _enregistrer() async {
    final remplace = etat.portefeuille.isNotEmpty;
    if (remplace) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Remplacer le portefeuille ?'),
          content: Text('Les ${etat.portefeuille.length} lignes actuelles seront remplacées par celles-ci.'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remplacer')),
          ],
        ),
      );
      if (ok != true) return;
    }
    await etat.appliquerImport(widget.resultat);
    if (mounted) Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    final s = Theme.of(context).colorScheme;
    final texte = Theme.of(context).textTheme;
    final d = etat.donnees;
    final retenues = _lignes.where((l) => !l.ignoree).toList();
    final reconnues = retenues.where((l) => l.confiance == Confiance.sure).length;
    final aVerifier = retenues.where((l) => l.confiance == Confiance.probable).length;
    final hors = retenues.where((l) => l.ticker == null).length;
    final total = retenues.fold<double>(0, (t, l) => t + l.poids);
    return Scaffold(
      appBar: AppBar(title: const Text('Vérifier l\'import')),
      body: ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 96), children: [
        Card(
          color: s.secondaryContainer,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${retenues.length} lignes : $reconnues reconnues, $aVerifier à vérifier, $hors hors des données',
                  style: texte.titleSmall),
              const SizedBox(height: 4),
              Text('Poids calculés d\'après les $_methode. Touchez une ligne pour la corriger : la correction est '
                  'retenue pour les prochains imports.'),
              if (d == null)
                const Padding(
                  padding: EdgeInsets.only(top: 6),
                  child: Text('Données pas encore téléchargées : les lignes ne peuvent pas être reconnues.'),
                ),
            ]),
          ),
        ),
        for (final l in _lignes)
          Builder(builder: (context) {
            final v = l.ticker == null ? null : d?.valeurs[l.ticker!];
            final (icone, couleur, etiquette) = l.ignoree
                ? (Icons.block, s.outline, 'Ignorée')
                : switch (l.confiance) {
                    Confiance.sure => (Icons.check_circle, vert, 'Reconnue'),
                    Confiance.probable => (Icons.help, Colors.amber.shade700, 'À vérifier'),
                    Confiance.aucune => (Icons.do_not_disturb_on_outlined, s.outline, 'Hors des données'),
                  };
            return ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Tooltip(message: etiquette, child: Icon(icone, color: couleur)),
              title: Text(v?.nom ?? l.libelle,
                  style: l.ignoree ? const TextStyle(decoration: TextDecoration.lineThrough) : null),
              subtitle: Text([
                if (v != null) v.ticker else etiquette,
                if (v != null && normaliser(v.nom) != normaliser(l.libelle)) 'fichier : ${l.libelle}',
                if (l.isin != null) l.isin!,
              ].join(' · ')),
              trailing: Text(l.ignoree ? '' : '${nombre(l.poids, 1)} %', style: texte.titleSmall),
              onTap: () => _corriger(l),
            );
          }),
        if ((total - 100).abs() > 0.5 && total > 0)
          Text('Total : ${nombre(total, 1)} % (certaines lignes n\'ont pas de montant).', style: texte.bodySmall),
      ]),
      floatingActionButton: FloatingActionButton.extended(
        icon: const Icon(Icons.check),
        label: Text('Enregistrer (${retenues.where((l) => l.poids > 0).length} lignes)'),
        onPressed: retenues.any((l) => l.poids > 0) ? _enregistrer : null,
      ),
    );
  }
}
