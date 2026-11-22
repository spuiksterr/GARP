import 'package:material_ui/material_ui.dart';
import 'package:url_launcher/url_launcher.dart';

import '../actualites.dart';
import '../formats.dart';
import '../graphiques.dart';
import '../interface.dart';
import '../main.dart';
import '../widgets.dart';

// Articles lus pendant la session : {ticker: articles}. La presse n'est pas relue à chaque affichage.
final _presse = <String, List<Article>>{};

/// Actualités des lignes et de la watchlist : signaux de l'outil, puis presse.
class PageActualites extends StatefulWidget {
  const PageActualites({super.key});

  @override
  State<PageActualites> createState() => _PageActualitesState();
}

class _PageActualitesState extends State<PageActualites> {
  bool _lecture = false;
  String? _erreur;
  int _faits = 0;
  String? _filtre;

  Future<void> _lirePresse() async {
    final d = etat.donnees;
    if (d == null || _lecture) return;
    final tickers = tickersSuivis(etat);
    setState(() {
      _lecture = true;
      _erreur = null;
      _faits = 0;
    });
    for (final t in tickers) {
      try {
        _presse[t] = await presse(d.valeurs[t]!.nom, ticker: t);
      } catch (_) {
        _erreur = 'Presse injoignable pour certaines valeurs (connexion ?).';
      }
      if (!mounted) return;
      setState(() => _faits++);
      // Une requête à la fois, sans presser le service.
      await Future<void>.delayed(const Duration(milliseconds: 400));
    }
    if (mounted) setState(() => _lecture = false);
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        final texte = Theme.of(context).textTheme;
        final suivis = tickersSuivis(etat);
        final tous = signaux(etat);
        final aSurveiller = tous.where((a) => a.type == 'À surveiller').toList();
        final fil = [
          ...tous.where((a) => a.type == 'Signal'),
          for (final t in suivis) ...?_presse[t],
        ].where((a) => _filtre == null || a.ticker == _filtre).toList()
          ..sort((a, b) => b.date.compareTo(a.date));
        const titre = 'Actualités';
        if (d == null || suivis.isEmpty) {
          return const PageDefilante(titre: titre, [
            Vide('Ajoutez des lignes à votre portefeuille ou des valeurs à votre watchlist : leurs '
                'actualités s\'afficheront ici.', icone: Icons.newspaper),
          ]);
        }
        return PageDefilante(
                titre: titre,
                legende: 'Signaux tirés des données de la nuit et presse de vos lignes et de votre watchlist.',
                actions: [
                  bouton('Lire la presse', _lecture ? null : _lirePresse, icone: Icons.refresh),
                ],
                [
                  if (_lecture) LinearProgressIndicator(value: _faits / suivis.length),
                  if (aSurveiller.isNotEmpty)
                    Carte(
                      'À surveiller',
                      enfant: Column(children: [
                        for (final a in aSurveiller)
                          ListTile(
                            dense: true,
                            contentPadding: EdgeInsets.zero,
                            leading: const Icon(Icons.flag_outlined),
                            title: Text(a.titre),
                            subtitle: Text([a.source, if (a.detail.isNotEmpty) a.detail].join(' · ')),
                            onTap: a.ticker == null ? null : () => ouvrirFiche(context, a.ticker!),
                          ),
                      ]),
                    ),
                  const SizedBox(height: 12),
                  if (_presse.isEmpty && !_lecture)
                    Card.filled(
                      child: ListTile(
                        leading: const Icon(Icons.newspaper),
                        title: const Text('Lire la presse de mes valeurs'),
                        subtitle: Text('Google Actualités, en français, pour vos ${suivis.length} valeurs. La recherche '
                            'envoie le nom de chaque société, jamais votre portefeuille.'),
                        trailing: const Icon(Icons.download),
                        onTap: _lirePresse,
                      ),
                    ),
                  if (_erreur != null) Text(_erreur!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(children: [
                      ChoiceChip(
                        label: const Text('Toutes'),
                        selected: _filtre == null,
                        onSelected: (_) => setState(() => _filtre = null),
                      ),
                      for (final t in suivis)
                        Padding(
                          padding: const EdgeInsets.only(left: 6),
                          child: ChoiceChip(
                            label: Text(d.valeurs[t]!.nom),
                            selected: _filtre == t,
                            onSelected: (_) => setState(() => _filtre = t),
                          ),
                        ),
                    ]),
                  ),
                  if (fil.isEmpty)
                    Padding(
                      padding: const EdgeInsets.all(24),
                      child: Text(_presse.isEmpty ? 'La presse n\'est pas encore lue.' : 'Rien de récent pour ce choix.'),
                    ),
                  for (final a in fil.take(150))
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(a.type == 'Presse' ? Icons.article_outlined : Icons.insights),
                      title: Text(a.titre),
                      subtitle: Text('${dateFr(a.date.toIso8601String())} · ${a.source}'
                          '${a.ticker == null ? '' : ' · ${d.valeurs[a.ticker]?.nom ?? a.ticker}'}'
                          '${a.detail.isEmpty ? '' : ' · ${a.detail}'}'),
                      trailing: a.lien.isEmpty ? null : const Icon(Icons.open_in_new, size: 18),
                      onTap: a.lien.isNotEmpty
                          ? () => launchUrl(Uri.parse(a.lien), mode: LaunchMode.externalApplication)
                          : (a.ticker == null ? null : () => ouvrirFiche(context, a.ticker!)),
                    ),
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text('Presse : titres de Google Actualités, lus à la demande. Signaux : tirés des données '
                        'de la nuit. Une actualité n\'est pas une raison d\'acheter ou de vendre.', style: texte.bodySmall),
                  ),
                ]);
      },
    );
  }
}
