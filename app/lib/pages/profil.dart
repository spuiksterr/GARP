import 'package:material_ui/material_ui.dart';

import '../formats.dart';
import '../graphiques.dart';
import '../import_portefeuille.dart';
import '../main.dart';
import '../methodes.dart';
import '../recherche.dart';
import '../widgets.dart';
import 'methodes.dart';

/// Profil de l'investisseur : sa méthode, son exigence de prix, ses critères de recherche, ses enveloppes et ses
/// limites de concentration. Tout reste sur l'appareil.
class PageProfil extends StatefulWidget {
  const PageProfil({super.key});

  @override
  State<PageProfil> createState() => _PageProfilState();
}

class _PageProfilState extends State<PageProfil> {
  late final _prenom = TextEditingController(text: etat.profil.prenom);
  late final _apport =
      TextEditingController(text: etat.profil.apportMensuel > 0 ? nombre(etat.profil.apportMensuel, 0) : '');

  @override
  void dispose() {
    _prenom.dispose();
    _apport.dispose();
    super.dispose();
  }

  /// Trois questions pour proposer une méthode d'évaluation.
  Future<void> _questionnaire() async {
    var priorite = 'qualite', horizon = 'long', prix = 'souple';
    final id = await showDialog<String>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, majour) {
          Widget question(String titre, Map<String, String> choix, String valeur, void Function(String) regler) =>
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Padding(
                  padding: const EdgeInsets.only(top: 12, bottom: 4),
                  child: Text(titre, style: Theme.of(context).textTheme.titleSmall),
                ),
                Wrap(spacing: 6, runSpacing: 4, children: [
                  for (final e in choix.entries)
                    ChoiceChip(
                      label: Text(e.value),
                      selected: valeur == e.key,
                      onSelected: (_) => majour(() => regler(e.key)),
                    ),
                ]),
              ]);
          final propose = methodeConseillee(priorite: priorite, horizon: horizon, prix: prix);
          final m = etat.donnees?.methode(propose);
          return AlertDialog(
            title: const Text('Trouver ma méthode'),
            content: SingleChildScrollView(
              child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                question('Ce que je cherche d\'abord', const {
                  'qualite': 'Des entreprises d\'exception',
                  'croissance': 'De la croissance',
                  'prix': 'Des prix bas',
                  'solidite': 'Ne pas perdre',
                  'equilibre': 'Un peu de tout',
                }, priorite, (x) => priorite = x),
                question('Mon horizon', const {'long': 'Dix ans et plus', 'moyen': 'Trois à cinq ans'}, horizon,
                    (x) => horizon = x),
                question('Face au prix', const {
                  'strict': 'Je n\'achète qu\'avec une décote',
                  'souple': 'Je paie le prix d\'une belle entreprise',
                }, prix, (x) => prix = x),
                const SizedBox(height: 16),
                Text('Méthode proposée : ${m?.libelle ?? propose}', style: Theme.of(context).textTheme.titleMedium),
                if (m != null) Text(m.description),
              ]),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
              FilledButton(onPressed: () => Navigator.pop(context, propose), child: const Text('Choisir cette méthode')),
            ],
          );
        },
      ),
    );
    if (id != null) await etat.reglerProfil((p) => p.methode = id);
  }

  @override
  Widget build(BuildContext context) {
    final texte = Theme.of(context).textTheme;
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final p = etat.profil;
        final d = etat.donnees;
        final methodes = d?.methodes ?? const [composite];
        final m = methodes.firstWhere((m) => m.id == p.methode, orElse: () => methodes.first);
        final rendement = etat.reglagesValorisation.rendementExige;
        final secteurs = d == null ? <String>[] : ({for (final v in d.valeurs.values) v.secteur}.toList()..sort());
        final nb = d == null ? null : opportunites(d, p, etat.reglagesValorisation);
        Widget curseur(String libelle, String aide, double valeur, double min, double max, double pas, String affiche,
                void Function(double) regler) =>
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Curseur(libelle, valeur, min, max, pas, affiche, (v) => etat.reglerProfil((p) => regler(v))),
              Text(aide, style: texte.bodySmall),
              const SizedBox(height: 10),
            ]);
        return PageDefilante(
            titre: 'Mon profil investisseur',
            legende: 'Votre profil règle toute l\'application : l\'ordre du screener, la recherche « Pour moi », le '
                'prix juste des fiches et les alertes de votre portefeuille. Il reste sur cet appareil.',
            [
            if (nb != null)
              Card.filled(
                margin: const EdgeInsets.only(top: 12),
                child: ListTile(
                  leading: const Icon(Icons.person_search_outlined),
                  title: Text('${nb.length} valeurs conviennent à ce profil'),
                  subtitle: Text('${nb.where((o) => o.verdict == Verdict.bonPrix).length} au bon prix · '
                      '${nb.where((o) => o.verdict == Verdict.prixCorrect).length} à un prix correct · '
                      '${nb.where((o) => o.verdict == Verdict.aAttendre).length} à attendre'),
                ),
              ),
            const SizedBox(height: 12),
            TextField(
              controller: _prenom,
              decoration: const InputDecoration(
                  labelText: 'Prénom ou pseudo (facultatif)', border: OutlineInputBorder(), isDense: true),
              onChanged: (t) => etat.reglerProfil((p) => p.prenom = t.trim()),
            ),
            Carte(
              'La bonne action : ma méthode',
              action: TextButton.icon(
                icon: const Icon(Icons.quiz_outlined),
                label: const Text('M\'aider à choisir'),
                onPressed: _questionnaire,
              ),
              enfant: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.insights),
                  title: Text(m.libelle),
                  subtitle: Text(m.description),
                  trailing: const Icon(Icons.expand_more),
                  onTap: () async {
                    final id = await choisirMethode(context, actuelle: m.id);
                    if (id != null) await etat.reglerProfil((p) => p.methode = id);
                  },
                ),
                curseur('Critères de qualité exigés (sur 6)', 'Croissance, ROCE, dette, dilution, marge : 0 pour ne rien exiger.',
                    p.criteresMin.toDouble(), 0, 6, 1, '${p.criteresMin}', (v) => p.criteresMin = v.round()),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Écarter les avantages concurrentiels faibles'),
                  subtitle: const Text('Moat estimé « Faible » d\'après les comptes.'),
                  value: p.exclureMoatFaible,
                  onChanged: (v) => etat.reglerProfil((p) => p.exclureMoatFaible = v),
                ),
                curseur('Capitalisation minimale', 'En milliards d\'euros. 0 : toutes les tailles de l\'univers.',
                    p.capitalisationMin.clamp(0.0, 50.0), 0, 50, 1, '${nombre(p.capitalisationMin, 0)} Md€',
                    (v) => p.capitalisationMin = v),
              ]),
            ),
            Carte(
              'Le bon prix : mon exigence',
              enfant: Column(children: [
                curseur('Rendement annuel exigé',
                    'Le prix juste est le cours auquel l\'action rapporte ce rendement si la croissance attendue se '
                        'réalise. Plus vous exigez, plus le prix juste baisse. La stratégie propose '
                        '${pct(d?.valorisation.rendementExige ?? 0.09, 0)}.',
                    rendement, 0.06, 0.14, 0.005, pct(rendement, 1), (v) => p.rendementExige = v),
                curseur('Marge de sécurité', 'Décote demandée sous le prix juste avant d\'acheter : elle absorbe les '
                    'erreurs de prévision.', p.margeSecurite, 0, 0.5, 0.05, pct(p.margeSecurite, 0),
                    (v) => p.margeSecurite = v),
              ]),
            ),
            Carte(
              'Où j\'investis',
              enfant: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'Toutes', label: Text('PEA et CTO')),
                    ButtonSegment(value: 'PEA', label: Text('PEA')),
                    ButtonSegment(value: 'CTO', label: Text('CTO')),
                  ],
                  selected: {p.enveloppe},
                  onSelectionChanged: (s) => etat.reglerProfil((p) => p.enveloppe = s.first),
                ),
                const SizedBox(height: 12),
                Text('Secteurs que j\'écarte', style: texte.titleSmall),
                const SizedBox(height: 4),
                Wrap(spacing: 6, runSpacing: 4, children: [
                  for (final s in secteurs)
                    FilterChip(
                      label: Text(s),
                      selected: p.secteursExclus.contains(s),
                      onSelected: (x) =>
                          etat.reglerProfil((p) => x ? p.secteursExclus.add(s) : p.secteursExclus.remove(s)),
                    ),
                ]),
              ]),
            ),
            Carte(
              'Mes apports',
              enfant: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                TextField(
                  controller: _apport,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                      labelText: 'Apport mensuel habituel', suffixText: '€', border: OutlineInputBorder(), isDense: true),
                  onChanged: (t) => etat.reglerProfil((p) => p.apportMensuel = lireNombre(t) ?? 0),
                ),
                const SizedBox(height: 10),
                curseur('Ordre minimal', 'En dessous, les frais de courtage pèsent trop : l\'apport du mois regroupe les '
                    'achats.', p.ordreMin.clamp(50.0, 2000.0), 50, 2000, 50, euros(p.ordreMin), (v) => p.ordreMin = v),
              ]),
            ),
            Carte(
              'Mes limites de concentration',
              action: TextButton(
                onPressed: () => etat.reglerProfil((p) {
                  p.ligneMax = 0.25;
                  p.troisPremieresMax = 0.60;
                  p.secteurMax = 0.40;
                }),
                child: const Text('Par défaut'),
              ),
              enfant: Column(children: [
                curseur('Une ligne au plus', 'Au-delà, l\'accueil et la page Portefeuille vous préviennent.', p.ligneMax,
                    0.05, 0.50, 0.05, pct(p.ligneMax, 0), (v) => p.ligneMax = v),
                curseur('Les trois premières lignes au plus', 'Part cumulée des trois plus grosses lignes.',
                    p.troisPremieresMax, 0.20, 1.0, 0.05, pct(p.troisPremieresMax, 0), (v) => p.troisPremieresMax = v),
                curseur('Un secteur au plus', 'Poids cumulé des lignes d\'un même secteur.', p.secteurMax, 0.10, 1.0, 0.05,
                    pct(p.secteurMax, 0), (v) => p.secteurMax = v),
              ]),
            ),
            const AvertissementConseil(),
          ]);
      },
    );
  }
}
