import 'package:material_ui/material_ui.dart';

import '../donnees.dart';
import '../formats.dart';
import '../graphiques.dart';
import '../interface.dart';
import '../main.dart';
import '../methodes.dart';
import '../navigation.dart';
import '../widgets.dart';

/// Taille de la tête de classement retenue pour le consensus des méthodes.
const teteDeClassement = 50;

/// Choix d'une méthode d'évaluation dans une feuille du bas ; renvoie son identifiant.
Future<String?> choisirMethode(BuildContext context, {required String actuelle}) {
  final d = etat.donnees;
  if (d == null) return Future.value();
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (context) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.75,
      maxChildSize: 0.95,
      builder: (context, defilement) => ListView(controller: defilement, children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
          child: Text('Méthode d\'évaluation', style: Theme.of(context).textTheme.titleLarge),
        ),
        for (final m in d.methodes)
          ListTile(
            leading: Icon(m.id == actuelle ? Icons.radio_button_checked : Icons.radio_button_unchecked),
            title: Text(m.libelle),
            subtitle: Text(m.description),
            onTap: () => Navigator.pop(context, m.id),
          ),
        ListTile(
          leading: const Icon(Icons.menu_book_outlined),
          title: const Text('Comprendre les méthodes'),
          onTap: () {
            Navigator.pop(context);
            aller(context, Rubrique.methodes);
          },
        ),
      ]),
    ),
  );
}

/// Valeur d'un critère et seuil, en texte (« 12 % », « > 10 % », « 2,1 fois »).
String texteCritere(Critere c, double? valeur) {
  if (c.cle == 'dette') return valeur == null ? vide : '${nombre(valeur, 1)} fois';
  return pct(valeur, 1, c.cle == 'actions');
}

String seuilCritere(Critere c) {
  final signe = switch (c.sens) { '<' => '<', '<=' => '≤', _ => '>' };
  return c.cle == 'dette' ? '$signe ${nombre(c.seuil, 1)} fois' : '$signe ${pct(c.seuil, 0)}';
}

/// Valeurs éligibles présentes dans la tête de classement d'au moins `minimum` méthodes (hors score composite),
/// avec les méthodes qui les retiennent.
List<(Valeur, List<Methode>)> consensus(Donnees d, {int minimum = 4}) {
  final parValeur = <String, List<Methode>>{};
  for (final m in d.methodes.where((m) => m.id != 'composite')) {
    final n = d.notes(m);
    var pris = 0;
    for (final v in d.classees(m)) {
      if (pris >= teteDeClassement) break;
      if (!v.eligible || n[v.ticker] == null) continue;
      pris++;
      parValeur.putIfAbsent(v.ticker, () => []).add(m);
    }
  }
  final out = [
    for (final e in parValeur.entries)
      if (e.value.length >= minimum) (d.valeurs[e.key]!, e.value),
  ];
  out.sort((a, b) => b.$2.length != a.$2.length
      ? b.$2.length.compareTo(a.$2.length)
      : (a.$1.rang ?? 1 << 30).compareTo(b.$1.rang ?? 1 << 30));
  return out;
}

/// Les méthodes d'évaluation expliquées, les six critères, et les valeurs que plusieurs méthodes retiennent.
class PageMethodes extends StatelessWidget {
  const PageMethodes({super.key});

  @override
  Widget build(BuildContext context) {
    final d = etat.donnees;
    return d == null
          ? const PageDefilante(titre: 'Méthodes d\'évaluation', [
              Encadre('Aucune donnée : configurez l\'accès dans la rubrique Réglages.'),
            ])
          : PageDefilante(titre: 'Méthodes d\'évaluation', [
              const Text('Chaque méthode classe les mêmes valeurs selon une autre façon de juger une entreprise. '
                  'Une note sur 100 est le rang centile dans l\'univers : 90 veut dire « mieux placée que 90 % des '
                  'valeurs » selon cette méthode. Votre méthode préférée se règle dans Mon profil.'),
              for (final m in d.methodes)
                Card(
                  margin: const EdgeInsets.only(top: 10),
                  child: ListTile(
                    title: Row(children: [
                      Expanded(child: Text(m.libelle)),
                      if (m.id == etat.profil.methode) const Chip(label: Text('Ma méthode')),
                    ]),
                    subtitle: Text([
                      m.description,
                      if (m.composantes.isNotEmpty) 'Composantes : ${m.composantes.join(', ')}.',
                    ].join('\n')),
                    onTap: () => etat.reglerProfil((p) => p.methode = m.id),
                  ),
                ),
              if (d.criteres.isNotEmpty) ...[
                const SousTitre('Les six critères de qualité'),
                const Text('Une grille « réussi ou échoué », mesurée sur l\'historique des comptes. Une banque ou un '
                    'assureur n\'en a que deux d\'applicables.'),
                for (final c in d.criteres)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    leading: const Icon(Icons.check_circle_outline),
                    title: Text(c.titre),
                    trailing: Text(seuilCritere(c)),
                  ),
              ],
              const SousTitre('Les quatre regards'),
              const Text('Une note de 1 à 5 par investisseur, tirée des chiffres :\n'
                  '• Buffett : une rentabilité élevée, à un prix qui laisse une marge de sécurité.\n'
                  '• Munger : on part de 5 et on retire ce qui peut faire perdre la moitié de la mise (volatilité, '
                  'chute passée, dette, marges instables, euphorie).\n'
                  '• Fisher : la croissance à venir, et un capital rendu aux actionnaires plutôt que dilué.\n'
                  '• Terry Smith : une rentabilité durable transformée en cash, sans effet de levier.'),
              const SousTitre('Retenues par plusieurs méthodes'),
              const Text('Valeurs éligibles dans les $teteDeClassement premières d\'au moins 4 méthodes (hors score '
                  'composite). Un consensus n\'est pas une recommandation : seule une analyse de l\'entreprise peut '
                  'justifier un achat.'),
              for (final (v, ms) in consensus(d))
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(v.nom),
                  subtitle: Text(ms.map((m) => m.libelle).join(' · ')),
                  trailing: CircleAvatar(child: Text('${ms.length}')),
                  onTap: () => ouvrirFiche(context, v.ticker),
                ),
              const AvertissementConseil(),
            ]);
  }
}

/// Notes d'une valeur selon chaque méthode, et détail des six critères (fiche valeur).
class NotesDesMethodes extends StatelessWidget {
  const NotesDesMethodes(this.v, {super.key});

  final Valeur v;

  @override
  Widget build(BuildContext context) {
    final d = etat.donnees!;
    final texte = Theme.of(context).textTheme;
    final regards = {'buffett': 'Buffett', 'munger': 'Munger', 'fisher': 'Fisher', 'smith': 'Terry Smith'};
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(
        padding: const EdgeInsets.only(top: 16, bottom: 4),
        child: Row(children: [
          Expanded(child: Text('Selon chaque méthode', style: texte.titleMedium)),
          TextButton(
            onPressed: () => aller(context, Rubrique.methodes),
            child: const Text('Comprendre'),
          ),
        ]),
      ),
      for (final m in d.methodes)
        Builder(builder: (context) {
          final note = d.notes(m)[v.ticker];
          final rang = v.eligible ? d.rangSelon(m, v.ticker) : null;
          return ListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            title: Text(m.libelle,
                style: m.id == etat.profil.methode ? const TextStyle(fontWeight: FontWeight.bold) : null),
            subtitle: rang == null ? null : Text('rang $rang sur ${d.nbEligibles}'),
            trailing: SizedBox(
              width: 120,
              child: Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                if (note != null)
                  SizedBox(width: 60, child: LinearProgressIndicator(value: (note / 100).clamp(0, 1))),
                const SizedBox(width: 8),
                Text(note == null ? vide : nombre(note, 0)),
              ]),
            ),
          );
        }),
      Wrap(spacing: 8, runSpacing: 4, children: [
        for (final e in regards.entries)
          if (v.n(e.key) != null) Chip(label: Text('${e.value} ${nombre(v.n(e.key), 0)}/5')),
      ]),
      if (d.criteres.isNotEmpty) ...[
        Padding(
          padding: const EdgeInsets.only(top: 16, bottom: 4),
          child: Text('Six critères de qualité : ${v.t('criteres') ?? 'non évalués'}', style: texte.titleMedium),
        ),
        for (final c in d.criteres)
          Builder(builder: (context) {
            final (valeur, ok) = c.pour(v);
            final couleurs = Theme.of(context).colorScheme;
            return ListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              leading: Icon(
                ok == null ? Icons.remove_circle_outline : (ok ? Icons.check_circle : Icons.cancel),
                color: ok == null ? couleurs.outline : (ok ? couleurs.primary : couleurs.error),
                semanticLabel: ok == null ? 'non évalué' : (ok ? 'rempli' : 'non rempli'),
              ),
              title: Text(c.titre),
              subtitle: Text('Seuil ${seuilCritere(c)}'),
              trailing: Text(ok == null && valeur == null ? 'non évalué' : texteCritere(c, valeur)),
            );
          }),
      ],
    ]);
  }
}
