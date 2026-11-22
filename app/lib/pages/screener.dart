/// Screener, présenté comme celui de l'outil du PC (vues/screener.py) : filtres en boutons groupés, puis le
/// tableau des valeurs classées, avec barres de score.
library;

import 'package:material_ui/material_ui.dart';

import '../donnees.dart';
import '../formats.dart';
import '../graphiques.dart';
import '../interface.dart';
import '../main.dart';
import '../methodes.dart';
import '../widgets.dart';
import 'methodes.dart';

/// Tris proposés en plus de la note de la méthode choisie.
const _tris = {
  'Note de la méthode': 'note',
  'TRI implicite': 'tri_implicite',
  'Rendement du FCF': 'rendement_fcf',
  'Performance 12 mois': 'perf_12m',
  'Qualité': 'qualite',
  'Croissance': 'croissance',
};

const _comptes = ['PEA', 'CTO'];
const _statuts = ['Éligible', 'Exclu'];
const _moats = ['Large', 'Étroit', 'Faible'];

class Screener extends StatefulWidget {
  const Screener({super.key});

  @override
  State<Screener> createState() => _ScreenerState();
}

class _ScreenerState extends State<Screener> {
  String _recherche = '';
  late Set<int> _compte = {
    for (final (i, c) in _comptes.indexed)
      if (etat.profil.enveloppe == 'Toutes' || etat.profil.enveloppe == c) i,
  };
  Set<int> _statut = {0};
  Set<int> _moat = {};
  String? _secteur;
  String _tri = 'Note de la méthode';
  int _affichees = 100;

  /// Méthode affichée : celle du profil, sauf si on en choisit une autre ici.
  String? _methode;

  Set<int> _basculer(Set<int> s, int i) => s.contains(i) ? ({...s}..remove(i)) : {...s, i};

  List<Valeur> _filtrer(Donnees d, Methode m) {
    final r = _recherche.toLowerCase();
    final comptes = {for (final i in _compte) _comptes[i]};
    final statuts = {for (final i in _statut) _statuts[i]};
    final moats = {for (final i in _moat) _moats[i]};
    final out = d.classees(m).where((v) {
      if (statuts.isNotEmpty && !statuts.contains(v.statut)) return false;
      if (comptes.isNotEmpty && !comptes.contains(v.enveloppe)) return false;
      if (moats.isNotEmpty && !moats.contains(v.t('moat'))) return false;
      if (_secteur != null && v.secteur != _secteur) return false;
      return r.isEmpty || v.nom.toLowerCase().contains(r) || v.ticker.toLowerCase().contains(r);
    }).toList();
    final cle = _tris[_tri]!;
    if (cle != 'note') {
      out.sort((a, b) => (b.n(cle) ?? double.negativeInfinity).compareTo(a.n(cle) ?? double.negativeInfinity));
    }
    return out;
  }

  Future<void> _changerMethode(Methode actuelle) async {
    final id = await choisirMethode(context, actuelle: actuelle.id);
    if (id != null) setState(() => _methode = id);
  }

  Widget _libelle(String texte, Widget enfant, {String? aide}) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(mainAxisSize: MainAxisSize.min, children: [
            Text(texte, style: Theme.of(context).textTheme.labelMedium),
            if (aide != null) ...[const SizedBox(width: 6), Aide(aide)],
          ]),
          const SizedBox(height: 6),
          enfant,
        ],
      );

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        if (d == null) {
          return const PageDefilante(titre: 'Screener', [
            Encadre('Aucune donnée : configurez l\'accès dans la rubrique Réglages.'),
          ]);
        }
        final m = d.methode(_methode ?? etat.profil.methode);
        final notes = d.notes(m);
        final secteurs = {for (final v in d.valeurs.values) v.secteur}.toList()..sort();
        final liste = _filtrer(d, m);
        final cleTri = _tris[_tri]!;
        final visibles = liste.take(_affichees).toList();
        return PageDefilante(
          titre: 'Screener',
          legende: 'Étape 1 : les filtres d\'exclusion écartent les entreprises qui ne sont pas de premier ordre. '
              'Étape 2 : les survivantes sont classées selon la méthode choisie (${m.libelle}) : ${m.description}',
          [
            Wrap(spacing: 28, runSpacing: 16, crossAxisAlignment: WrapCrossAlignment.end, children: [
              _libelle('Compte', Segments(_comptes, _compte, (i) => setState(() => _compte = _basculer(_compte, i)))),
              _libelle('Statut', Segments(_statuts, _statut, (i) => setState(() => _statut = _basculer(_statut, i)))),
              _libelle('Moat estimé', Segments(_moats, _moat, (i) => setState(() => _moat = _basculer(_moat, i))),
                  aide: 'Avantage concurrentiel estimé d\'après la rentabilité et sa stabilité. Aucun choix : tous.'),
              SizedBox(
                width: 280,
                child: _libelle(
                  'Recherche',
                  TextField(
                    decoration: const InputDecoration(hintText: 'Nom ou ticker'),
                    onChanged: (t) => setState(() {
                      _recherche = t;
                      _affichees = 100;
                    }),
                  ),
                ),
              ),
            ]),
            const SizedBox(height: 16),
            Wrap(spacing: 16, runSpacing: 16, crossAxisAlignment: WrapCrossAlignment.end, children: [
              SizedBox(
                width: 240,
                child: _libelle(
                  'Secteurs',
                  DropdownButtonFormField<String?>(
                    initialValue: _secteur,
                    isExpanded: true,
                    items: [
                      const DropdownMenuItem<String?>(value: null, child: Text('Tous les secteurs')),
                      for (final s in secteurs) DropdownMenuItem<String?>(value: s, child: Text(s)),
                    ],
                    onChanged: (s) => setState(() => _secteur = s),
                  ),
                ),
              ),
              SizedBox(
                width: 240,
                child: _libelle(
                  'Tri',
                  DropdownButtonFormField<String>(
                    initialValue: _tri,
                    isExpanded: true,
                    items: [for (final t in _tris.keys) DropdownMenuItem(value: t, child: Text(t))],
                    onChanged: (t) => setState(() => _tri = t ?? 'Note de la méthode'),
                  ),
                ),
              ),
              _libelle('Méthode d\'évaluation', bouton(m.libelle, () => _changerMethode(m), icone: Icons.insights)),
              if (m.id != etat.profil.methode)
                TextButton(
                  onPressed: () => etat.reglerProfil((p) => p.methode = m.id),
                  child: const Text('En faire ma méthode'),
                ),
            ]),
            Padding(
              padding: const EdgeInsets.only(top: 22, bottom: 4),
              child: Text('${liste.length} valeurs', style: Theme.of(context).textTheme.titleMedium),
            ),
            const Legende('Cliquez sur une valeur pour ouvrir sa fiche. L\'étoile l\'ajoute à la watchlist (pleine = '
                'suivie) ; touchez-la de nouveau pour la retirer.', haut: 0),
            const SizedBox(height: 8),
            Tableau(
              largeurMin: 1060,
              colonnes: [
                const Colonne('', largeur: 44),
                const Colonne('Ticker', largeur: 88),
                const Colonne('Rang', largeur: 54, droite: true),
                const Colonne('Valeur', flex: 3),
                const Colonne('Compte', largeur: 68),
                const Colonne('Secteur', flex: 2),
                Colonne(cleTri == 'note' ? 'Note' : _tri, largeur: 150, aide: 'Note sur 100 selon ${m.libelle}'),
                const Colonne('Score', largeur: 150, aide: 'Score composite de l\'outil, sur 100'),
                const Colonne('Moat estimé', largeur: 96),
                const Colonne('Critères', largeur: 70),
              ],
              lignes: [
                for (final (i, v) in visibles.indexed)
                  [
                    IconButton(
                      tooltip: etat.suivie(v.ticker) ? 'Retirer de la watchlist' : 'Ajouter à la watchlist',
                      iconSize: 18,
                      visualDensity: VisualDensity.compact,
                      icon: Icon(etat.suivie(v.ticker) ? Icons.star : Icons.star_border,
                          color: etat.suivie(v.ticker) ? Teintes.de(context).primaire : null),
                      onPressed: () => etat.basculerWatchlist(v),
                    ),
                    v.ticker,
                    cleTri == 'note' && notes[v.ticker] != null ? '${i + 1}' : (v.rang?.toString() ?? '—'),
                    v.nom,
                    v.enveloppe,
                    v.secteur,
                    switch (cleTri) {
                      'note' => BarreScore(notes[v.ticker], largeur: 80),
                      'qualite' || 'croissance' => BarreScore(v.n(cleTri), largeur: 80),
                      _ => pct(v.n(cleTri)),
                    },
                    v.fonds ? '' : BarreScore(v.n('score'), largeur: 80),
                    v.t('moat') ?? '—',
                    v.t('criteres') ?? '—',
                  ],
              ],
              surClic: (i) => ouvrirFiche(context, visibles[i].ticker),
            ),
            if (liste.length > visibles.length)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: bouton('Afficher ${(liste.length - visibles.length).clamp(0, 100)} de plus '
                      '(${visibles.length} sur ${liste.length})', () => setState(() => _affichees += 100),
                      icone: Icons.expand_more),
                ),
              ),
            const AvertissementConseil(),
          ],
        );
      },
    );
  }
}
