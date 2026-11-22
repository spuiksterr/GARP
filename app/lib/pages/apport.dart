import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../formats.dart';
import '../graphiques.dart';
import '../import_portefeuille.dart';
import '../main.dart';
import '../recherche.dart';
import '../suivi.dart';
import '../widgets.dart';

/// Apport du mois : les ordres qui rapprochent le portefeuille de ses poids cibles, sans rien vendre.
class OngletApport extends StatefulWidget {
  const OngletApport({super.key});

  @override
  State<OngletApport> createState() => _OngletApportState();
}

class _OngletApportState extends State<OngletApport> {
  late final _montant =
      TextEditingController(text: etat.profil.apportMensuel > 0 ? nombre(etat.profil.apportMensuel, 0) : '');
  bool _fractions = false;
  bool _ecarterAlertes = true;

  @override
  void dispose() {
    _montant.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        final lignes = etat.portefeuille;
        if (d == null || lignes.isEmpty) {
          return const PageDefilante(titre: 'Apport du mois', [
            Vide('Importez votre portefeuille dans la rubrique Composition pour préparer un apport.',
                icone: Icons.savings_outlined),
          ]);
        }
        final texte = Theme.of(context).textTheme;
        final p = etat.profil;
        final montant = lireNombre(_montant.text) ?? 0;
        final pos = positions(lignes, d);
        final sansQuantite = lignes.where((l) => l.quantite == null && d.valeurs[l.ticker] != null).length;
        // Lignes achetables : dans les données, avec un cours ; celles qui ne passent plus les filtres sont écartées.
        final ecartees = <String, String>{};
        final cibles = <String, double>{}, cours = <String, double>{}, detenu = <String, double>{};
        for (final x in pos) {
          final v = d.valeurs[x.ligne.ticker];
          if (v == null || x.coursEur == null) continue;
          if (_ecarterAlertes && v.statut == 'Exclu') {
            ecartees[v.nom] = 'ne passe plus les filtres de qualité';
            continue;
          }
          cibles[v.ticker] = x.ligne.poids;
          cours[v.ticker] = x.coursEur!;
          detenu[v.ticker] = x.valeur ?? 0;
        }
        final plan = planApport(montant, cibles, detenu, cours, ordreMin: p.ordreMin, fractions: _fractions);
        final reglages = etat.reglagesValorisation;
        return PageDefilante(titre: 'Apport du mois', legende: 'Investir régulièrement, sans jamais vendre pour rééquilibrer : chaque apport va aux lignes les plus en retard sur leur poids cible. Sur le compte-titres, cela évite de payer l\'impôt sur les plus-values ; sur le PEA, cela évite des frais inutiles.', [
          const Text('Les ordres qui rapprochent le portefeuille de ses poids cibles sans rien vendre : on achète '
              'd\'abord les lignes les plus en retard.'),
          const SizedBox(height: 12),
          Wrap(spacing: 12, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
            SizedBox(
              width: 220,
              child: TextField(
                controller: _montant,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(
                    labelText: 'Somme à investir', suffixText: '€', border: OutlineInputBorder(), isDense: true),
                onChanged: (_) => setState(() {}),
              ),
            ),
            FilterChip(
              label: const Text('Fractions d\'actions'),
              selected: _fractions,
              onSelected: (s) => setState(() => _fractions = s),
            ),
            FilterChip(
              label: const Text('Écarter les lignes exclues'),
              selected: _ecarterAlertes,
              onSelected: (s) => setState(() => _ecarterAlertes = s),
            ),
          ]),
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text('Ordre minimal : ${euros(p.ordreMin)} (réglable dans Mon profil).', style: texte.bodySmall),
          ),
          if (sansQuantite > 0)
            Card(
              margin: const EdgeInsets.only(top: 10),
              child: ListTile(
                leading: const Icon(Icons.info_outline),
                title: Text('$sansQuantite lignes sans nombre de titres : elles comptent comme non détenues. '
                    'Saisissez vos titres dans la rubrique Composition (crayon) pour un plan exact.'),
              ),
            ),
          for (final e in ecartees.entries)
            ListTile(
              dense: true,
              leading: const Icon(Icons.block),
              title: Text('${e.key} écartée : ${e.value}'),
            ),
          if (montant <= 0)
            const Padding(padding: EdgeInsets.all(24), child: Text('Saisissez la somme à investir.'))
          else if (plan.ordres.isEmpty)
            const Padding(
              padding: EdgeInsets.all(24),
              child: Text('Aucun ordre possible avec cette somme : elle ne couvre pas une action des lignes en retard, '
                  'ou reste sous l\'ordre minimal.'),
            )
          else
            Carte(
              'Ordres proposés',
              sousTitre: 'Reste non investi : ${euros(plan.reste)}.',
              action: IconButton(
                tooltip: 'Copier les ordres',
                icon: const Icon(Icons.copy),
                onPressed: () async {
                  await Clipboard.setData(ClipboardData(text: [
                    'ticker;nom;quantite;cours_eur;montant_eur',
                    for (final o in plan.ordres)
                      '${o.ticker};${d.valeurs[o.ticker]?.nom ?? ''};${nombre(o.quantite, _fractions ? 4 : 0)};'
                          '${nombre(o.coursEur, 2)};${nombre(o.montant, 2)}',
                  ].join('\n')));
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Ordres copiés.')));
                  }
                },
              ),
              enfant: Column(children: [
                for (final o in plan.ordres)
                  Builder(builder: (context) {
                    final v = d.valeurs[o.ticker]!;
                    final prix = evaluer(v, 0, p, reglages);
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text('${nombre(o.quantite, _fractions ? 3 : 0)} × ${v.nom}'),
                      subtitle: Text('à ${euros(o.coursEur, 2)} · cible ${pct(o.poidsCible, 1)} · après l\'apport '
                          '${pct(plan.poidsApres[o.ticker], 1)} · ${prix.verdict.libelle.toLowerCase()}'),
                      trailing: Text(euros(o.montant), style: texte.titleMedium),
                      onTap: () => ouvrirFiche(context, o.ticker),
                    );
                  }),
                Align(
                  alignment: Alignment.centerLeft,
                  child: FilledButton.tonalIcon(
                    icon: const Icon(Icons.playlist_add_check),
                    label: const Text('J\'ai passé ces ordres : mettre à jour mes titres'),
                    onPressed: () async {
                      for (final o in plan.ordres) {
                        final l = etat.ligne(o.ticker);
                        if (l == null) continue;
                        final avant = l.quantite ?? 0;
                        final revient = l.prixRevient == null && avant > 0
                            ? null
                            : ((l.prixRevient ?? 0) * avant + o.montant) / (avant + o.quantite);
                        await etat.reglerPosition(o.ticker, avant + o.quantite, revient);
                      }
                    },
                  ),
                ),
              ]),
            ),
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text('Ce plan applique vos poids cibles : il ne dit pas si le moment ou le prix sont bons. Vérifiez '
                'chaque ordre, les frais de votre courtier et la fiscalité de votre enveloppe. Ce n\'est pas un '
                'conseil d\'investissement.', style: texte.bodySmall),
          ),
        ]);
      },
    );
  }
}
