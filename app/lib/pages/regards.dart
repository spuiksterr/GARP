/// Quatre regards (vues/regards.py) : une note sur 5 par regard (Buffett, Munger, Fisher, Smith) pour toutes les
/// actions de la base.
library;

import 'package:material_ui/material_ui.dart';

import '../donnees.dart';
import '../graphiques.dart';
import '../interface.dart';
import '../main.dart';
import '../widgets.dart';

const _statuts = ['Éligible', 'Exclu'];

class PageRegards extends StatefulWidget {
  const PageRegards({super.key});

  @override
  State<PageRegards> createState() => _PageRegardsState();
}

class _PageRegardsState extends State<PageRegards> {
  Set<int> _statut = {0, 1};
  String _recherche = '';
  bool _detenues = false;
  int _affichees = 100;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        const titre = 'Quatre regards';
        if (d == null) {
          return const PageDefilante(titre: titre, [Encadre('Aucune donnée : configurez l\'accès dans les réglages.')]);
        }
        final statuts = {for (final i in _statut) _statuts[i]};
        final r = _recherche.toLowerCase();
        final detenues = {for (final l in etat.portefeuille) l.ticker};
        final liste = d.valeurs.values.where((v) {
          if (v.fonds || v.n('regards_total') == null) return false;
          if (statuts.isNotEmpty && !statuts.contains(v.statut)) return false;
          if (_detenues && !detenues.contains(v.ticker)) return false;
          return r.isEmpty || v.nom.toLowerCase().contains(r) || v.ticker.toLowerCase().contains(r);
        }).toList()
          ..sort((a, b) {
            final c = (b.n('regards_total') ?? 0).compareTo(a.n('regards_total') ?? 0);
            return c != 0 ? c : (b.n('score') ?? 0).compareTo(a.n('score') ?? 0);
          });
        final visibles = liste.take(_affichees).toList();
        Widget note(Valeur v, String cle) => BarreScore(v.n(cle), max: 5, largeur: 52);
        return PageDefilante(
          titre: titre,
          [
            const Text('Une note sur 5 par regard, pour toutes les actions de la base :'),
            const SizedBox(height: 6),
            for (final (qui, quoi) in const [
              ('Buffett', 'une bonne entreprise à un prix qui laisse une marge.'),
              ('Munger', 'ce qui peut faire perdre la moitié de la mise (plus la note est haute, moins c\'est fragile).'),
              ('Fisher', 'la croissance à venir et l\'usage du capital.'),
              ('Smith', 'une rentabilité durable, transformée en cash.'),
            ])
              Padding(
                padding: const EdgeInsets.only(left: 8, top: 2),
                child: Text.rich(TextSpan(children: [
                  const TextSpan(text: '•  '),
                  TextSpan(text: qui, style: const TextStyle(fontWeight: FontWeight.w600)),
                  TextSpan(text: ' : $quoi'),
                ])),
              ),
            const Legende('Notes issues de règles fixes sur les indicateurs, avec les corrections manuelles de l\'outil '
                'du PC pour ce que les chiffres ne voient pas. Sans correction, un pic de cycle ou un risque '
                'réglementaire n\'est pas pris en compte. Les fonds ne sont pas notés. Ce crible désigne quoi analyser, '
                'pas quoi acheter.', haut: 12),
            const SizedBox(height: 10),
            Wrap(spacing: 24, runSpacing: 14, crossAxisAlignment: WrapCrossAlignment.end, children: [
              Segments(_statuts, _statut, titre: 'Statut', (i) {
                setState(() => _statut = _statut.contains(i) ? ({..._statut}..remove(i)) : {..._statut, i});
              }),
              SizedBox(
                width: 320,
                child: TextField(
                  decoration: const InputDecoration(hintText: 'Nom ou ticker', prefixIcon: Icon(Icons.search, size: 20)),
                  onChanged: (t) => setState(() {
                    _recherche = t;
                    _affichees = 100;
                  }),
                ),
              ),
              Row(mainAxisSize: MainAxisSize.min, children: [
                Switch(value: _detenues, onChanged: (b) => setState(() => _detenues = b)),
                const SizedBox(width: 6),
                const Text('Mes lignes'),
              ]),
            ]),
            Padding(
              padding: const EdgeInsets.only(top: 20, bottom: 10),
              child: Text('${liste.length} valeurs', style: Theme.of(context).textTheme.titleMedium),
            ),
            Tableau(
              largeurMin: 1000,
              colonnes: const [
                Colonne('Rang', largeur: 56, droite: true),
                Colonne('Valeur', flex: 3),
                Colonne('Détenue', largeur: 70),
                Colonne('Filtres', largeur: 80),
                Colonne('Score', largeur: 140),
                Colonne('Buffett', largeur: 96),
                Colonne('Munger', largeur: 96),
                Colonne('Fisher', largeur: 96),
                Colonne('Smith', largeur: 96),
                Colonne('Total / 20', largeur: 78, droite: true),
              ],
              lignes: [
                for (final v in visibles)
                  [
                    v.rang?.toString() ?? '—',
                    '${v.nom} (${v.ticker})',
                    detenues.contains(v.ticker) ? const Icon(Icons.check, size: 18) : '',
                    v.statut,
                    BarreScore(v.n('score'), largeur: 70),
                    note(v, 'buffett'),
                    note(v, 'munger'),
                    note(v, 'fisher'),
                    note(v, 'smith'),
                    v.n('regards_total')?.round().toString() ?? '—',
                  ],
              ],
              surClic: (i) => ouvrirFiche(context, visibles[i].ticker),
            ),
            if (liste.length > visibles.length)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: bouton('Afficher 100 de plus (${visibles.length} sur ${liste.length})',
                      () => setState(() => _affichees += 100), icone: Icons.expand_more),
                ),
              ),
            const AvertissementConseil(),
          ],
        );
      },
    );
  }
}
