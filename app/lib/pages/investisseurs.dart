import 'package:material_ui/material_ui.dart';
import 'package:url_launcher/url_launcher.dart';

import '../formats.dart';
import '../graphiques.dart';
import '../interface.dart';
import '../main.dart';
import '../widgets.dart';

/// « 2026-09-30 » -> « T3 2026 ».
String trimestre(String? periode) {
  if (periode == null || periode.length < 7) return 'n.d.';
  final mois = int.tryParse(periode.substring(5, 7)) ?? 1;
  return 'T${(mois - 1) ~/ 3 + 1} ${periode.substring(0, 4)}';
}

String _dollars(Object? v) => montantCourt(nombreOuNul(v), '\$');

/// Ticker des données pour un ticker de déclaration (13F ou élu), s'il est dans l'univers.
String? _connu(Object? ticker) {
  if (ticker is! String) return null;
  for (final t in ticker.split(', ')) {
    if (etat.donnees?.valeurs.containsKey(t) ?? false) return t;
  }
  return null;
}

Color? _couleurMouvement(BuildContext context, String mouvement) => switch (mouvement) {
      'Nouvelle' || 'Renforcée' => vert,
      'Allégée' || 'Soldée' => Theme.of(context).colorScheme.error,
      _ => null,
    };

/// Grands investisseurs (déclarations 13F) et élus américains (STOCK Act).
class OngletInvestisseurs extends StatefulWidget {
  const OngletInvestisseurs({super.key});

  @override
  State<OngletInvestisseurs> createState() => _OngletInvestisseursState();
}

class _OngletInvestisseursState extends State<OngletInvestisseurs> {
  String _vue = 'partages';
  String _mouvement = 'Nouvelle';
  String? _elu;
  bool _univers = false;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final c = etat.complements;
        if (c == null) {
          return const PageDefilante(titre: 'Grands investisseurs', [Vide('Les portefeuilles des grands investisseurs ne sont pas encore téléchargés : actualisez '
              'les données depuis l\'accueil.', icone: Icons.groups_outlined)]);
        }
        final texte = Theme.of(context).textTheme;
        final investisseurs = c.listeInvestisseurs;
        return PageDefilante(titre: 'Grands investisseurs', [
          const Text('Ce que détiennent et achètent des investisseurs reconnus et des élus américains, d\'après leurs '
              'déclarations officielles. Pour trouver des idées à étudier, pas pour copier : ces déclarations '
              'arrivent avec des semaines de retard, sans le prix payé ni la raison de l\'achat.'),
          const SizedBox(height: 10),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'partages', label: Text('Titres partagés')),
                ButtonSegment(value: 'portefeuilles', label: Text('Portefeuilles')),
                ButtonSegment(value: 'mouvements', label: Text('Mouvements')),
                ButtonSegment(value: 'elus', label: Text('Élus')),
              ],
              selected: {_vue},
              onSelectionChanged: (s) => setState(() => _vue = s.first),
            ),
          ),
          if (_vue != 'elus' && investisseurs.isEmpty)
            const Card(
              margin: EdgeInsets.only(top: 12),
              child: ListTile(
                leading: Icon(Icons.info_outline),
                title: Text('Portefeuilles 13F pas encore publiés'),
                subtitle: Text('La SEC exige une adresse de contact pour lire ses déclarations. Enregistrez-la dans '
                    'le secret SEC_CONTACT du dépôt GitHub : le flux de nuit publiera alors les portefeuilles.'),
              ),
            )
          else if (_vue == 'partages')
            ..._partages(context, c.investisseurs['partages'] as List? ?? const [], investisseurs.length)
          else if (_vue == 'portefeuilles')
            for (final i in investisseurs)
              Card.outlined(
                margin: const EdgeInsets.only(top: 8),
                child: ListTile(
                  title: Text('${i['investisseur']} · ${i['societe']}'),
                  subtitle: Text('${i['style']}\n${trimestre(i['periode'] as String?)} · ${i['nb_lignes']} lignes · '
                      '${_dollars(i['total'])}'),
                  isThreeLine: true,
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => Navigator.of(context)
                      .push(MaterialPageRoute<void>(builder: (_) => PagePortefeuille13F(i))),
                ),
              )
          else if (_vue == 'mouvements')
            ..._mouvements(context, investisseurs)
          else
            ..._elus(context, c.investisseurs),
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(
                _vue == 'elus'
                    ? 'Source : greffe de la Chambre des représentants (STOCK Act). Montants déclarés par tranches, '
                        'jusqu\'à 45 jours après l\'opération ; Sénat non couvert. Mis à jour le '
                        '${dateFr(c.investisseurs['maj_elus'] as String?)}.'
                    : 'Source : formulaires 13F déposés à la SEC. Positions longues en actions américaines seulement, '
                        'publiées jusqu\'à 45 jours après la fin du trimestre. Mis à jour le '
                        '${dateFr(c.investisseurs['maj_13f'] as String?)}.',
                style: texte.bodySmall),
          ),
        ]);
      },
    );
  }

  List<Widget> _partages(BuildContext context, List partages, int nb) => [
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: FilterChip(
            label: const Text('Dans l\'univers de G.A.R.P seulement'),
            selected: _univers,
            onSelected: (s) => setState(() => _univers = s),
          ),
        ),
        for (final p in partages.where((p) => !_univers || _connu(p['ticker']) != null).take(60))
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: CircleAvatar(child: Text('${p['detenteurs']}')),
            title: Text('${p['nom']}${p['ticker'] == null ? '' : ' (${p['ticker']})'}',
                maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text('${(p['qui'] as List).join(', ')}\nPoids moyen ${pct(p['poids_moyen'], 1)} · au plus '
                '${pct(p['poids_max'], 1)} · détenu par ${p['detenteurs']} des $nb investisseurs suivis',
                maxLines: 3, overflow: TextOverflow.ellipsis),
            isThreeLine: true,
            trailing: _connu(p['ticker']) == null ? null : const Icon(Icons.chevron_right),
            onTap: _connu(p['ticker']) == null ? null : () => ouvrirFiche(context, _connu(p['ticker'])!),
          ),
      ];

  List<Widget> _mouvements(BuildContext context, List<Map<String, dynamic>> investisseurs) {
    final lignes = [
      for (final i in investisseurs)
        for (final l in i['lignes'] as List)
          if (l['mouvement'] == _mouvement) (i, l as Map<String, dynamic>),
    ]..sort((a, b) => ((b.$2['valeur'] as num?) ?? 0).compareTo((a.$2['valeur'] as num?) ?? 0));
    return [
      Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Wrap(spacing: 6, children: [
          for (final m in ['Nouvelle', 'Renforcée', 'Allégée', 'Soldée'])
            ChoiceChip(label: Text(m), selected: _mouvement == m, onSelected: (_) => setState(() => _mouvement = m)),
        ]),
      ),
      if (lignes.isEmpty) const Padding(padding: EdgeInsets.all(24), child: Text('Aucun mouvement de ce type au dernier trimestre.')),
      for (final (i, l) in lignes.take(80))
        ListTile(
          dense: true,
          contentPadding: EdgeInsets.zero,
          title: Text('${l['nom']}${l['ticker'] == null ? '' : ' (${l['ticker']})'}', maxLines: 1, overflow: TextOverflow.ellipsis),
          subtitle: Text('${i['investisseur']} · ${trimestre(i['periode'] as String?)}'
              '${l['variation'] == null || _mouvement == 'Soldée' ? '' : ' · ${pct(l['variation'], 0, true)} d\'actions'}'),
          trailing: Text(_mouvement == 'Soldée' ? 'soldée' : '${pct(l['poids'], 1)} · ${_dollars(l['valeur'])}',
              style: TextStyle(color: _couleurMouvement(context, _mouvement))),
          onTap: _connu(l['ticker']) == null ? null : () => ouvrirFiche(context, _connu(l['ticker'])!),
        ),
    ];
  }

  List<Widget> _elus(BuildContext context, Map<String, dynamic> donnees) {
    final elus = [for (final e in donnees['elus'] as List? ?? const []) e as Map<String, dynamic>];
    final operations = [
      for (final o in donnees['operations'] as List? ?? const [])
        if (_elu == null || o['elu'] == _elu) o as Map<String, dynamic>,
    ];
    return [
      Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Wrap(spacing: 6, runSpacing: 4, children: [
          ChoiceChip(label: const Text('Tous'), selected: _elu == null, onSelected: (_) => setState(() => _elu = null)),
          for (final e in elus)
            ChoiceChip(
              label: Text('${e['elu']}'),
              selected: _elu == e['elu'],
              onSelected: (_) => setState(() => _elu = e['elu'] as String),
            ),
        ]),
      ),
      if (operations.isEmpty)
        const Padding(padding: EdgeInsets.all(24), child: Text('Aucune opération lue pour l\'instant.')),
      for (final o in operations.take(120))
        ListTile(
          dense: true,
          contentPadding: EdgeInsets.zero,
          leading: Icon(
            o['operation'] == 'P' ? Icons.add_circle : Icons.remove_circle_outline,
            color: o['operation'] == 'P' ? vert : Theme.of(context).colorScheme.outline,
            semanticLabel: o['operation'] == 'P' ? 'achat' : 'vente',
          ),
          title: Text('${o['actif']}', maxLines: 1, overflow: TextOverflow.ellipsis),
          subtitle: Text('${o['elu']} (${o['parti']}) · ${o['operation'] == 'P' ? 'achat' : 'vente'} le '
              '${dateFr(o['date'] as String?)} · déclaré ${o['retard'] ?? '?'} jours après · ${o['montant']}'),
          trailing: IconButton(
            tooltip: 'Ouvrir la déclaration',
            icon: const Icon(Icons.open_in_new, size: 18),
            onPressed: () => launchUrl(Uri.parse(o['lien'] as String), mode: LaunchMode.externalApplication),
          ),
          onTap: _connu(o['ticker']) == null ? null : () => ouvrirFiche(context, _connu(o['ticker'])!),
        ),
    ];
  }
}

/// Portefeuille déclaré d'un investisseur, ligne par ligne, avec les mouvements du trimestre.
class PagePortefeuille13F extends StatelessWidget {
  const PagePortefeuille13F(this.investisseur, {super.key});

  final Map<String, dynamic> investisseur;

  @override
  Widget build(BuildContext context) {
    final i = investisseur;
    final lignes = [for (final l in i['lignes'] as List) l as Map<String, dynamic>];
    final texte = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: Text('${i['investisseur']}')),
      body: PageDefilante([
        Text('${i['societe']} · ${i['style']}', style: texte.bodyMedium),
        const SizedBox(height: 4),
        Text('${trimestre(i['periode'] as String?)}, déposé le ${dateFr(i['depose_le'] as String?)} · '
            '${i['nb_lignes']} lignes · ${_dollars(i['total'])}'
            '${i['precedente'] == null ? '' : ' · mouvements depuis ${trimestre(i['precedente'] as String?)}'}',
            style: texte.bodySmall),
        const SizedBox(height: 8),
        for (final l in lignes)
          ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            leading: SizedBox(
              width: 52,
              child: Text(((l['poids'] as num?) ?? 0) > 0 ? pct(l['poids'], 1) : vide, style: texte.titleSmall),
            ),
            title: Text('${l['nom']}${l['ticker'] == null ? '' : ' (${l['ticker']})'}',
                maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text('${_dollars(l['valeur'])}${l['depuis'] == null ? '' : ' · depuis ${trimestre(l['depuis'] as String?)}'}'),
            trailing: (l['mouvement'] as String? ?? '').isEmpty || l['mouvement'] == 'Inchangée'
                ? null
                : Pastille(
                    '${l['mouvement']}${l['variation'] == null || l['mouvement'] == 'Soldée' ? '' : ' ${pct(l['variation'], 0, true)}'}',
                    couleur: _couleurMouvement(context, l['mouvement'] as String)),
            onTap: _connu(l['ticker']) == null ? null : () => ouvrirFiche(context, _connu(l['ticker'])!),
          ),
        const AvertissementConseil(),
      ]),
    );
  }
}
