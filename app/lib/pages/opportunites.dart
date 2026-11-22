import 'package:material_ui/material_ui.dart';

import '../formats.dart';
import '../graphiques.dart';
import '../interface.dart';
import '../main.dart';
import '../navigation.dart';
import '../recherche.dart';
import '../widgets.dart';

(Color, Color) couleursVerdict(BuildContext context, Verdict v) {
  final s = Theme.of(context).colorScheme;
  return switch (v) {
    Verdict.bonPrix => (vert, Colors.white),
    Verdict.prixCorrect => (s.primaryContainer, s.onPrimaryContainer),
    Verdict.aAttendre => (s.surfaceContainerHighest, s.onSurfaceVariant),
    Verdict.nonEvalue => (s.surfaceContainerHighest, s.outline),
  };
}

class PastilleVerdict extends StatelessWidget {
  const PastilleVerdict(this.verdict, {super.key});

  final Verdict verdict;

  @override
  Widget build(BuildContext context) {
    final (fond, couleur) = couleursVerdict(context, verdict);
    return Tooltip(message: verdict.explication, child: Pastille(verdict.libelle, fond: fond, couleur: couleur));
  }
}

/// « Pour moi » : les valeurs qui conviennent au profil, avec leur prix juste et leur prix d'achat.
class PageOpportunites extends StatefulWidget {
  const PageOpportunites({super.key});

  @override
  State<PageOpportunites> createState() => _PageOpportunitesState();
}

class _PageOpportunitesState extends State<PageOpportunites> {
  Verdict? _filtre = Verdict.bonPrix;
  bool _horsPortefeuille = false;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        if (d == null) {
          return const PageDefilante(titre: 'Pour moi', [Vide('Aucune donnée : configurez l\'accès dans les réglages.')]);
        }
        final p = etat.profil;
        final m = d.methode(p.methode);
        final reglages = etat.reglagesValorisation;
        final toutes = opportunites(d, p, reglages);
        final compte = {for (final v in Verdict.values) v: toutes.where((o) => o.verdict == v).length};
        // Sans rien au bon prix, on montre ce qui s'en approche plutôt qu'une liste vide.
        final filtre = _filtre == Verdict.bonPrix && compte[Verdict.bonPrix] == 0 ? Verdict.prixCorrect : _filtre;
        final liste = toutes
            .where((o) => filtre == null || o.verdict == filtre)
            .where((o) => !_horsPortefeuille || etat.poids(o.v.ticker) == null)
            .take(80)
            .toList();
        final texte = Theme.of(context).textTheme;
        return PageDefilante(titre: 'Pour moi', legende: 'La bonne action au bon prix : les valeurs qui conviennent à votre profil, leur prix juste (le cours auquel elles rapportent votre rendement exigé) et votre prix d\'achat (marge de sécurité déduite).', [
          Card.filled(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(child: Text('La bonne action, au bon prix', style: texte.titleLarge)),
                  TextButton.icon(
                    icon: const Icon(Icons.tune),
                    label: const Text('Mon profil'),
                    onPressed: () => aller(context, Rubrique.profil),
                  ),
                ]),
                Text('${toutes.length} valeurs conviennent à votre profil : méthode ${m.libelle}'
                    '${p.enveloppe == 'Toutes' ? '' : ', ${p.enveloppe}'}'
                    '${p.criteresMin > 0 ? ', au moins ${p.criteresMin} critères sur 6' : ''}'
                    '${p.secteursExclus.isEmpty ? '' : ', ${p.secteursExclus.length} secteurs écartés'}.'),
                const SizedBox(height: 4),
                Text('Prix juste : le cours auquel l\'action rapporte ${pct(reglages.rendementExige, 1)} par an si la '
                    'croissance attendue se réalise. Prix d\'achat : ${pct(p.margeSecurite, 0)} en dessous, votre '
                    'marge de sécurité.', style: texte.bodySmall),
              ]),
            ),
          ),
          const SizedBox(height: 8),
          Wrap(spacing: 6, runSpacing: 4, children: [
            ChoiceChip(
              label: Text('Toutes · ${toutes.length}'),
              selected: filtre == null,
              onSelected: (_) => setState(() => _filtre = null),
            ),
            for (final v in [Verdict.bonPrix, Verdict.prixCorrect, Verdict.aAttendre])
              ChoiceChip(
                label: Text('${v.libelle} · ${compte[v]}'),
                selected: filtre == v,
                onSelected: (_) => setState(() => _filtre = v),
              ),
            FilterChip(
              label: const Text('Hors de mon portefeuille'),
              selected: _horsPortefeuille,
              onSelected: (s) => setState(() => _horsPortefeuille = s),
            ),
          ]),
          if (liste.isEmpty)
            const Padding(
              padding: EdgeInsets.all(24),
              child: Text('Aucune valeur ici. Assouplissez vos exigences ou votre marge de sécurité dans Mon profil.'),
            ),
          for (final o in liste)
            Card.outlined(
              margin: const EdgeInsets.only(top: 8),
              child: InkWell(
                borderRadius: BorderRadius.circular(12),
                onTap: () => ouvrirFiche(context, o.v.ticker),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Expanded(
                        child: Text(o.v.nom, style: texte.titleMedium, maxLines: 1, overflow: TextOverflow.ellipsis),
                      ),
                      if (etat.poids(o.v.ticker) != null)
                        const Padding(padding: EdgeInsets.only(right: 6), child: Icon(Icons.pie_chart, size: 16)),
                      if (etat.suivie(o.v.ticker))
                        const Padding(padding: EdgeInsets.only(right: 6), child: Icon(Icons.star, size: 16)),
                      PastilleVerdict(o.verdict),
                    ]),
                    Text('${o.v.ticker} · ${o.v.secteur} · ${o.v.enveloppe} · note ${nombre(o.note, 0)} selon '
                        '${m.libelle}', style: texte.bodySmall),
                    const SizedBox(height: 8),
                    Wrap(spacing: 18, runSpacing: 6, children: [
                      _Mesure('Cours', '${nombre(o.v.n('cours'), 2)} ${o.v.devise}'),
                      _Mesure('Prix juste', o.prixJuste == null ? vide : '${nombre(o.prixJuste, 2)} ${o.v.devise}'),
                      _Mesure('Prix d\'achat', o.prixAchat == null ? vide : '${nombre(o.prixAchat, 2)} ${o.v.devise}'),
                      _Mesure('Écart au prix juste', pct(o.ecart, 0, true),
                          couleur: o.ecart == null ? null : couleurSigne(context, -o.ecart!)),
                      _Mesure('Rendement implicite', pct(o.tri, 1)),
                      _Mesure('Qualité', o.v.t('criteres') == null ? vide : '${o.v.t('criteres')} critères'),
                    ]),
                  ]),
                ),
              ),
            ),
          const AvertissementConseil(),
        ]);
      },
    );
  }
}

class _Mesure extends StatelessWidget {
  const _Mesure(this.libelle, this.valeur, {this.couleur});

  final String libelle;
  final String valeur;
  final Color? couleur;

  @override
  Widget build(BuildContext context) {
    final texte = Theme.of(context).textTheme;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
      Text(libelle, style: texte.labelSmall),
      Text(valeur, style: texte.bodyLarge?.copyWith(color: couleur, fontWeight: FontWeight.w600)),
    ]);
  }
}
