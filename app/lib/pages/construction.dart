import 'package:material_ui/material_ui.dart';

import '../calculs.dart';
import '../construction.dart';
import '../formats.dart';
import '../graphiques.dart';
import '../main.dart';
import '../widgets.dart';
import 'methodes.dart';
import 'risques.dart';

/// Construction de portefeuille : un portefeuille bâti uniquement par des règles, comme source d'idées et point
/// de comparaison.
class OngletConstruction extends StatefulWidget {
  const OngletConstruction({super.key});

  @override
  State<OngletConstruction> createState() => _OngletConstructionState();
}

class _OngletConstructionState extends State<OngletConstruction> {
  ReglagesConstruction? _reglages;
  String? _methode;

  ReglagesConstruction _depart() {
    final c = ReglagesConstruction.depuisJson(etat.donnees?.construction ?? const {});
    final p = etat.profil;
    // Le profil prime : enveloppe, secteurs écartés, exigences de qualité.
    c.partPea = switch (p.enveloppe) { 'PEA' => 1.0, 'CTO' => 0.0, _ => c.partPea };
    c.secteursExclus = {...p.secteursExclus};
    if (p.criteresMin > 0) c.criteresMin = p.criteresMin;
    return c;
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        if (d == null) {
          return const PageDefilante(titre: 'Construction de portefeuille', [Vide('Aucune donnée : configurez l\'accès dans les réglages.')]);
        }
        final texte = Theme.of(context).textTheme;
        final c = _reglages ??= _depart();
        final m = d.methode(_methode ?? etat.profil.methode);
        final w = construire(d, m, c);
        final notes = d.notes(m);
        final communes = w.keys.where((t) => etat.poids(t) != null).length;
        void regler(void Function() f) => setState(f);
        return PageDefilante(titre: 'Construction de portefeuille', [
          const Text('Un portefeuille diversifié construit uniquement par des règles, à partir de votre méthode : les '
              'meilleures notes éligibles, un plancher de qualité, des plafonds par ligne et par secteur. Une source '
              'd\'idées et un point de comparaison, pas un portefeuille à copier.'),
          Carte(
            'Règles',
            action: TextButton(onPressed: () => setState(() => _reglages = _depart()), child: const Text('Par défaut')),
            enfant: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Wrap(spacing: 8, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
                ActionChip(
                  avatar: const Icon(Icons.insights, size: 18),
                  label: Text('Méthode : ${m.libelle}'),
                  onPressed: () async {
                    final id = await choisirMethode(context, actuelle: m.id);
                    if (id != null) setState(() => _methode = id);
                  },
                ),
                for (final (libelle, valeur) in [('Note × 1/volatilité', 'score_vol'), ('Équipondéré', 'egal')])
                  ChoiceChip(
                    label: Text(libelle),
                    selected: c.ponderation == valeur,
                    onSelected: (_) => regler(() => c.ponderation = valeur),
                  ),
                for (final (libelle, part) in <(String, double?)>[('PEA et CTO', null), ('Tout en PEA', 1.0), ('Tout en CTO', 0.0)])
                  ChoiceChip(
                    label: Text(libelle),
                    selected: c.partPea == part,
                    onSelected: (_) => regler(() => c.partPea = part),
                  ),
                FilterChip(
                  label: const Text('Écarter les moats faibles'),
                  selected: c.exclureMoatFaible,
                  onSelected: (s) => regler(() => c.exclureMoatFaible = s),
                ),
              ]),
              const SizedBox(height: 8),
              Curseur('Nombre de lignes', c.nbLignes.toDouble(), 5, 40, 1, '${c.nbLignes}',
                  (x) => regler(() => c.nbLignes = x.round())),
              Curseur('Poids maximal d\'une ligne', c.poidsMax, 0.03, 0.25, 0.01, pct(c.poidsMax, 0),
                  (x) => regler(() => c.poidsMax = x)),
              Curseur('Poids maximal d\'un secteur', c.secteurMax, 0.10, 0.60, 0.05, pct(c.secteurMax, 0),
                  (x) => regler(() => c.secteurMax = x)),
              Curseur('Lignes au plus par secteur', c.maxParSecteur.toDouble(), 1, 10, 1, '${c.maxParSecteur}',
                  (x) => regler(() => c.maxParSecteur = x.round())),
              Curseur('Critères de qualité exigés (sur 6)', c.criteresMin.toDouble(), 0, 6, 1, '${c.criteresMin}',
                  (x) => regler(() => c.criteresMin = x.round())),
              Curseur('Part maximale des secteurs cycliques', c.cycliquesMax ?? 1.0, 0, 1, 0.05, pct(c.cycliquesMax ?? 1.0, 0),
                  (x) => regler(() => c.cycliquesMax = x >= 1 ? null : x)),
              Text('Cycliques : ${cycliques.join(', ')}. Au sommet du cycle, leurs multiples paraissent bas.'
                  '${c.secteursExclus.isEmpty ? '' : ' Secteurs écartés par votre profil : ${c.secteursExclus.join(', ')}.'}',
                  style: texte.bodySmall),
            ]),
          ),
          if (w.isEmpty)
            const Padding(padding: EdgeInsets.all(24), child: Text('Aucune valeur ne passe ces règles : assouplissez-les.'))
          else ...[
            Carte(
              'Portefeuille construit : ${w.length} lignes',
              sousTitre: communes == 0
                  ? 'Aucune ligne en commun avec votre portefeuille.'
                  : '$communes lignes en commun avec votre portefeuille.',
              action: TextButton.icon(
                icon: const Icon(Icons.swap_horiz),
                label: const Text('Adopter'),
                onPressed: () => _adopter(context, w),
              ),
              enfant: Column(children: [
                Wrap(spacing: 12, runSpacing: 8, children: [
                  Chiffre('TRI implicite moyen', pct(moyenne(w, d, 'tri_implicite'))),
                  Chiffre('PER prospectif', nombre(moyenne(w, d, 'per_prospectif', harmonique: true), 1)),
                  Chiffre('Rentabilité moyenne', pct(moyenne(w, d, 'rentabilite'))),
                  Chiffre('Croissance attendue', pct(moyenne(w, d, 'croissance_attendue'))),
                ]),
                const SizedBox(height: 8),
                for (final e in w.entries)
                  Builder(builder: (context) {
                    final v = d.valeurs[e.key]!;
                    return ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      leading: etat.poids(v.ticker) == null ? const Icon(Icons.circle_outlined, size: 16) : const Icon(Icons.pie_chart, size: 16),
                      title: Text(v.nom, maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: Text('${v.ticker} · ${v.secteur} · ${v.enveloppe} · note ${nombre(notes[v.ticker], 0)}'),
                      trailing: Text(pct(e.value, 1), style: texte.titleSmall),
                      onTap: () => ouvrirFiche(context, v.ticker),
                    );
                  }),
              ]),
            ),
            Carte('Secteurs', enfant: BarresParts(repartition(w, d, (v) => v.secteur), largeurLibelle: 190)),
            Comparaison(d, w, nom: 'Portefeuille construit'),
          ],
          const AvertissementConseil(),
        ]);
      },
    );
  }

  Future<void> _adopter(BuildContext context, Map<String, double> w) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remplacer mes poids cibles ?'),
        content: Text('Votre portefeuille de ${etat.portefeuille.length} lignes sera remplacé par ces ${w.length} '
            'lignes et leurs poids. Les titres déjà saisis sont gardés pour les lignes communes. Un portefeuille '
            'construit par des règles ne remplace pas l\'analyse de chaque entreprise.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remplacer')),
        ],
      ),
    );
    if (ok == true) await etat.adopterPortefeuille(w);
  }
}
