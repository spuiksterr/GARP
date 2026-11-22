import 'package:material_ui/material_ui.dart';

import '../calculs.dart';
import '../donnees.dart';
import '../formats.dart';
import '../graphiques.dart';
import '../main.dart';
import '../risques.dart';
import '../widgets.dart';

final _motOr = RegExp(r'\b(or|gold)\b', caseSensitive: false);

/// Lignes d'or du portefeuille (fonds ou ETC dont le nom cite l'or) : pour le scénario « or -20 % ».
Set<String> lignesOr() => {
      for (final l in etat.portefeuille)
        if ((etat.donnees?.valeurs[l.ticker]?.fonds ?? true) && _motOr.hasMatch(etat.nomLigne(l))) l.ticker,
    };

String _nom(String ticker) {
  for (final l in etat.portefeuille) {
    if (l.ticker == ticker) return etat.nomLigne(l);
  }
  return etat.donnees?.valeurs[ticker]?.nom ?? ticker;
}

/// Risques du portefeuille : concentration, devises, corrélations, pertes passées, chocs, simulation d'un changement.
class OngletRisques extends StatefulWidget {
  const OngletRisques({super.key});

  @override
  State<OngletRisques> createState() => _OngletRisquesState();
}

class _OngletRisquesState extends State<OngletRisques> {
  Valeur? _simulee;
  double _poidsSimule = 0.05;

  Future<void> _choisir() async {
    final choix = await choisirValeur(context, titre: 'Simuler un changement de poids');
    if (choix is ChoixValeur) {
      setState(() {
        _simulee = choix.valeur;
        _poidsSimule = ((etat.poids(choix.valeur.ticker) ?? 5) / 100).clamp(0.0, 0.5);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        final poids = poidsNormalises(etat.portefeuille);
        if (d == null || poids.isEmpty) {
          return const PageDefilante(titre: 'Risques du portefeuille', [Vide('Importez votre portefeuille dans la rubrique Composition pour mesurer ses risques.',
              icone: Icons.shield_outlined)]);
        }
        final texte = Theme.of(context).textTheme;
        final r = Risques(d, poids, or: lignesOr());
        final stats = r.stats;
        final correlation = r.correlationMoyenne;
        final seuil = d.gardeFous.correlationMax;
        final alertes = [
          ...gardeFous(poids, d, noms: {for (final t in poids.keys) t: _nom(t)}, profil: etat.profil),
          if (correlation != null && correlation > seuil + 1e-9)
            'Corrélation moyenne de ${nombre(correlation, 2)} entre les lignes (seuil ${nombre(seuil, 2)}) : elles '
                'montent et baissent ensemble.',
        ];
        return PageDefilante(titre: 'Risques du portefeuille', legende: 'Mesures du passé et scénarios simplifiés : ils montrent où sont les risques, pas ce qui arrivera.', [
          Text('Mesuré sur 3 ans de cours hebdomadaires en euros, avec les poids d\'aujourd\'hui. '
              '${r.partCouverte < 0.999 ? 'Cours connus pour ${pct(r.partCouverte, 0)} du portefeuille : les autres lignes (fonds, valeurs hors des données) ne comptent pas dans la volatilité.' : ''}',
              style: texte.bodySmall),
          for (final a in alertes)
            Card(
              color: Theme.of(context).colorScheme.errorContainer,
              margin: const EdgeInsets.only(top: 8),
              child: ListTile(leading: const Icon(Icons.warning_amber_outlined), title: Text(a)),
            ),
          if (alertes.isEmpty)
            const Card(
              margin: EdgeInsets.only(top: 8),
              child: ListTile(leading: Icon(Icons.verified_outlined), title: Text('Aucun garde-fou dépassé.')),
            ),
          Carte(
            'Concentration',
            enfant: Wrap(spacing: 12, runSpacing: 10, children: [
              Chiffre('Plus grosse ligne', pct(r.plusGrosse, 0), detail: r.nomPlusGrosse == null ? null : _nom(r.nomPlusGrosse!)),
              Chiffre('Trois premières lignes', pct(r.troisPremieres, 0)),
              Chiffre('Nombre effectif de lignes', nombre(r.nombreEffectif, 1),
                  detail: 'sur ${poids.length} lignes'),
              Chiffre('Corrélation moyenne', correlation == null ? vide : nombre(correlation, 2),
                  detail: 'entre les lignes'),
            ]),
          ),
          Carte(
            'Pertes passées',
            enfant: Wrap(spacing: 12, runSpacing: 10, children: [
              Chiffre('Volatilité annuelle', pct(stats.volatilite, 0)),
              Chiffre('Perte maximale', pct(stats.perteMaximale, 0), detail: 'du sommet au creux'),
              Chiffre('Pires 4 semaines', pct(stats.pireMois, 0),
                  detail: stats.finPireMois == null ? null : 'fin ${dateFr(stats.finPireMois!.toIso8601String())}'),
              Chiffre('Indice ${d.tickerReference}', pct(r.statsIndice.perteMaximale, 0), detail: 'sa perte maximale'),
            ]),
          ),
          Carte(
            'Scénarios de choc',
            sousTitre: 'Estimations simples : chaque ligne suit l\'indice selon sa sensibilité passée (bêta).',
            enfant: Column(children: [
              for (final (nom, impact, ligne, effet) in r.scenarios)
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text(nom),
                  subtitle: ligne == null ? null : Text('Ligne la plus touchée : ${_nom(ligne)} (${pct(effet, 1)})'),
                  trailing: Text(pct(impact, 1), style: texte.titleMedium?.copyWith(color: couleurSigne(context, impact))),
                ),
            ]),
          ),
          Carte('Devises de cotation', enfant: BarresParts(r.devises, largeurLibelle: 70)),
          Carte(
            'Sensibilité au marché',
            sousTitre: 'Bêta : 1,2 veut dire que la ligne varie en moyenne de 12 % quand l\'indice varie de 10 %.',
            enfant: Wrap(spacing: 6, runSpacing: 6, children: [
              for (final e in (r.betas.entries.toList()..sort((a, b) => b.value.compareTo(a.value))))
                Chip(label: Text('${_nom(e.key)} ${nombre(e.value, 2)}')),
            ]),
          ),
          Carte(
            'Simuler un changement',
            sousTitre: 'Ajoutez, renforcez ou allégez une ligne : les autres sont réduites en proportion.',
            action: FilledButton.tonal(onPressed: _choisir, child: Text(_simulee == null ? 'Choisir une valeur' : 'Changer')),
            enfant: _simulee == null
                ? const Text('Choisissez une valeur pour voir le portefeuille avant et après.')
                : _simulation(context, d, poids, r),
          ),
          const AvertissementConseil(),
        ]);
      },
    );
  }

  Widget _simulation(BuildContext context, Donnees d, Map<String, double> poids, Risques avant) {
    final v = _simulee!;
    final apres = Risques(d, nouveauxPoids(poids, v.ticker, _poidsSimule), or: lignesOr());
    final sa = avant.stats, sb = apres.stats;
    final lignes = <(String, String, String)>[
      ('Plus grosse ligne', pct(avant.plusGrosse, 0), pct(apres.plusGrosse, 0)),
      ('Trois premières lignes', pct(avant.troisPremieres, 0), pct(apres.troisPremieres, 0)),
      ('Nombre effectif de lignes', nombre(avant.nombreEffectif, 1), nombre(apres.nombreEffectif, 1)),
      ('Volatilité annuelle', pct(sa.volatilite, 1), pct(sb.volatilite, 1)),
      ('Perte maximale (3 ans)', pct(sa.perteMaximale, 0), pct(sb.perteMaximale, 0)),
      ('Corrélation moyenne', nombre(avant.correlationMoyenne, 2), nombre(apres.correlationMoyenne, 2)),
      for (final (i, s) in apres.scenarios.indexed)
        (s.$1, i < avant.scenarios.length ? pct(avant.scenarios[i].$2, 1) : vide, pct(s.$2, 1)),
    ];
    final correlations = apres.correlationsAvec(v.ticker).take(5).toList();
    final petit = Theme.of(context).textTheme.labelMedium;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Curseur('${v.nom} : poids visé', _poidsSimule, 0, 0.5, 0.005, pct(_poidsSimule, 1),
          (x) => setState(() => _poidsSimule = x)),
      Text('Poids actuel : ${pct(poids[v.ticker] ?? 0, 1)}.', style: Theme.of(context).textTheme.bodySmall),
      const SizedBox(height: 8),
      Table(columnWidths: const {0: FlexColumnWidth(2.2), 1: FlexColumnWidth(), 2: FlexColumnWidth()}, children: [
        TableRow(children: [
          const SizedBox.shrink(),
          Text('Avant', textAlign: TextAlign.end, style: petit),
          Text('Après', textAlign: TextAlign.end, style: petit),
        ]),
        for (final (libelle, a, b) in lignes)
          TableRow(children: [
            Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text(libelle)),
            Text(a, textAlign: TextAlign.end),
            Text(b, textAlign: TextAlign.end, style: const TextStyle(fontWeight: FontWeight.w600)),
          ]),
      ]),
      if (correlations.isNotEmpty) ...[
        const SizedBox(height: 10),
        Text('Lignes les plus corrélées à ${v.nom}', style: Theme.of(context).textTheme.titleSmall),
        Wrap(spacing: 6, runSpacing: 6, children: [
          for (final (t, c) in correlations) Chip(label: Text('${_nom(t)} ${nombre(c, 2)}')),
        ]),
      ],
      const SizedBox(height: 8),
      Align(
        alignment: Alignment.centerLeft,
        child: OutlinedButton.icon(
          icon: const Icon(Icons.check),
          label: Text('Appliquer ${pct(_poidsSimule, 1)} à mon portefeuille'),
          onPressed: () async {
            // Les autres lignes sont réduites en proportion, comme dans la simulation.
            final cible = nouveauxPoids(poids, v.ticker, _poidsSimule);
            for (final e in cible.entries) {
              await etat.reglerPoids(e.key, e.value * 100);
            }
            if (_poidsSimule == 0) await etat.reglerPoids(v.ticker, null);
          },
        ),
      ),
    ]);
  }
}

/// Backtest : le portefeuille d'aujourd'hui, appliqué au passé, face à l'indice de référence.
class OngletBacktest extends StatefulWidget {
  const OngletBacktest({super.key});

  @override
  State<OngletBacktest> createState() => _OngletBacktestState();
}

class _OngletBacktestState extends State<OngletBacktest> {
  double _annees = 3;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        final poids = poidsNormalises(etat.portefeuille);
        if (d == null || poids.isEmpty) {
          return const PageDefilante(titre: 'Backtest', [Vide('Importez votre portefeuille dans la rubrique Composition pour le comparer à l\'indice.',
              icone: Icons.history)]);
        }
        return PageDefilante(titre: 'Backtest', [
          SegmentedButton<double>(
            segments: const [
              ButtonSegment(value: 1, label: Text('1 an')),
              ButtonSegment(value: 3, label: Text('3 ans')),
              ButtonSegment(value: 5, label: Text('5 ans')),
            ],
            selected: {_annees},
            onSelectionChanged: (s) => setState(() => _annees = s.first),
          ),
          Comparaison(d, poids, annees: _annees, nom: 'Mon portefeuille'),
        ]);
      },
    );
  }
}

/// Courbe et statistiques d'un portefeuille de poids fixes face à l'indice de référence.
class Comparaison extends StatelessWidget {
  const Comparaison(this.d, this.poids, {this.annees = 3, this.nom = 'Portefeuille', super.key});

  final Donnees d;
  final Map<String, double> poids;
  final double annees;
  final String nom;

  @override
  Widget build(BuildContext context) {
    final r = Risques(d, poids, annees: annees);
    final a = r.stats, b = r.statsIndice;
    final texte = Theme.of(context).textTheme;
    final lignes = <(String, String, String)>[
      ('Rendement annuel', pct(a.rendementAnnuel, 1, true), pct(b.rendementAnnuel, 1, true)),
      ('Rendement total', pct(a.rendementTotal, 0, true), pct(b.rendementTotal, 0, true)),
      ('Volatilité annuelle', pct(a.volatilite, 0), pct(b.volatilite, 0)),
      ('Perte maximale', pct(a.perteMaximale, 0), pct(b.perteMaximale, 0)),
      ('Pires 4 semaines', pct(a.pireMois, 0), pct(b.pireMois, 0)),
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Carte(
        '$nom et indice ${d.tickerReference}',
        sousTitre: 'Valeur d\'un placement de 100, en euros, poids rééquilibrés chaque semaine.',
        enfant: Courbes({nom: a.courbe, 'Indice': b.courbe}),
      ),
      Carte(
        'Chiffres',
        enfant: Table(columnWidths: const {0: FlexColumnWidth(2), 1: FlexColumnWidth(), 2: FlexColumnWidth()}, children: [
          TableRow(children: [
            const SizedBox.shrink(),
            Text(nom, textAlign: TextAlign.end, style: texte.labelMedium),
            Text('Indice', textAlign: TextAlign.end, style: texte.labelMedium),
          ]),
          for (final (libelle, x, y) in lignes)
            TableRow(children: [
              Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text(libelle)),
              Text(x, textAlign: TextAlign.end, style: const TextStyle(fontWeight: FontWeight.w600)),
              Text(y, textAlign: TextAlign.end),
            ]),
        ]),
      ),
      Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Text(
            'À lire avec prudence : ce sont les poids d\'aujourd\'hui appliqués au passé. Des valeurs choisies '
            'aujourd\'hui pour leur qualité ont souvent déjà bien monté : ce backtest flatte le portefeuille et ne '
            'prédit rien. ${r.partCouverte < 0.999 ? 'Cours connus pour ${pct(r.partCouverte, 0)} du portefeuille seulement.' : ''}',
            style: texte.bodySmall),
      ),
    ]);
  }
}
