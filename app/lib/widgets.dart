/// Briques communes de l'interface : statut, indicateurs, graphique de cours.
library;

import 'package:fl_chart/fl_chart.dart';
import 'package:material_ui/material_ui.dart';

import 'donnees.dart';
import 'formats.dart';
import 'import_portefeuille.dart';
import 'interface.dart';
import 'main.dart';
import 'navigation.dart';

/// Ouvre la fiche d'une valeur (rubrique « Fiche valeur »).
void ouvrirFiche(BuildContext context, String ticker) => ouvrirFicheValeur(context, ticker);

/// Logo de G.A.R.P : l'icône arrondie, ou l'emblème seul (sur fond coloré).
class Logo extends StatelessWidget {
  const Logo({this.taille = 40, this.embleme = false, super.key});

  final double taille;
  final bool embleme;

  @override
  Widget build(BuildContext context) => Image.asset(embleme ? 'assets/embleme.png' : 'assets/logo.png',
      width: taille, height: taille, filterQuality: FilterQuality.medium, semanticLabel: 'G.A.R.P');
}

/// Demande un poids en % (0 pour retirer la ligne). Null si l'utilisateur annule.
Future<double?> demanderPoids(BuildContext context, {double? actuel, String titre = 'Poids dans le portefeuille'}) {
  final champ = TextEditingController(text: actuel == null ? '' : nombre(actuel, 1));
  return showDialog<double?>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(titre),
      content: TextField(
        controller: champ,
        autofocus: true,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: const InputDecoration(suffixText: '%', helperText: '0 pour retirer la ligne'),
        onSubmitted: (t) => Navigator.pop(context, lireNombre(t) ?? 0),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
        FilledButton(onPressed: () => Navigator.pop(context, lireNombre(champ.text) ?? 0), child: const Text('Enregistrer')),
      ],
    ),
  );
}

/// Réponse de [choisirValeur].
sealed class Choix {}

class ChoixValeur extends Choix {
  ChoixValeur(this.valeur);

  final Valeur valeur;
}

class ChoixHorsDonnees extends Choix {}

class ChoixIgnorer extends Choix {}

/// Valeurs qui répondent à une recherche : ticker exact ou qui commence par, nom qui contient, nom ressemblant.
List<Valeur> rechercherValeurs(Donnees d, String recherche, {int max = 40}) {
  final r = recherche.trim();
  if (r.isEmpty) return d.triees.take(max).toList();
  final haut = r.toUpperCase(), bas = normaliser(r);
  final notes = <(double, Valeur)>[];
  for (final v in d.valeurs.values) {
    double note;
    if (v.ticker == haut) {
      note = 3;
    } else if (v.ticker.startsWith(haut)) {
      note = 2;
    } else if (normaliser(v.nom).contains(bas)) {
      note = 1.5;
    } else {
      note = ressemblance(r, v.nom);
    }
    if (note >= 0.5) notes.add((note, v));
  }
  notes.sort((a, b) => b.$1.compareTo(a.$1));
  return [for (final (_, v) in notes.take(max)) v];
}

/// Fenêtre de recherche d'une valeur des données. Avec `pourImport`, propose aussi de garder la ligne hors des
/// données (fonds, or, valeur non suivie) ou de l'ignorer.
Future<Choix?> choisirValeur(BuildContext context, {String recherche = '', String? titre, bool pourImport = false}) {
  final d = etat.donnees;
  final champ = TextEditingController(text: recherche);
  return showDialog<Choix>(
    context: context,
    builder: (context) => StatefulBuilder(builder: (context, majour) {
      final resultats = d == null ? <Valeur>[] : rechercherValeurs(d, champ.text);
      return Dialog(
        insetPadding: const EdgeInsets.all(16),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560, maxHeight: 640),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                if (titre != null) Text(titre, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                TextField(
                  controller: champ,
                  autofocus: true,
                  onChanged: (_) => majour(() {}),
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.search),
                    hintText: 'Nom ou ticker (Alphabet, GOOGL, Air Liquide, AI.PA…)',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ]),
            ),
            if (d == null)
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text('Les données ne sont pas encore téléchargées : configurez l\'accès dans les réglages.'),
              ),
            Flexible(
              child: ListView(shrinkWrap: true, children: [
                for (final v in resultats)
                  ListTile(
                    dense: true,
                    title: Text(v.nom),
                    subtitle: Text([v.ticker, v.pays, v.secteur].where((s) => s.isNotEmpty).join(' · ')),
                    trailing: BadgeStatut(v.statut),
                    onTap: () => Navigator.pop(context, ChoixValeur(v)),
                  ),
              ]),
            ),
            OverflowBar(alignment: MainAxisAlignment.end, spacing: 4, children: [
              if (pourImport) ...[
                TextButton(onPressed: () => Navigator.pop(context, ChoixIgnorer()), child: const Text('Ignorer la ligne')),
                TextButton(
                  onPressed: () => Navigator.pop(context, ChoixHorsDonnees()),
                  child: const Text('Garder hors des données'),
                ),
              ],
              TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
            ]),
            const SizedBox(height: 8),
          ]),
        ),
      );
    }),
  );
}

class BadgeStatut extends StatelessWidget {
  const BadgeStatut(this.statut, {super.key});

  final String statut;

  @override
  Widget build(BuildContext context) {
    final s = Theme.of(context).colorScheme;
    final (fond, texte) = switch (statut) {
      'Éligible' => (vert.withValues(alpha: 0.2), const Color(0xFF5FD35F)),
      'Exclu' => (rouge.withValues(alpha: 0.2), const Color(0xFFFF8A8A)),
      _ => (s.surfaceContainerHighest, s.onSurfaceVariant),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: fond, borderRadius: BorderRadius.circular(8)),
      child: Text(statut, style: Theme.of(context).textTheme.labelSmall?.copyWith(color: texte)),
    );
  }
}

/// Couleur d'une variation : verte si positive, rouge si négative.
Color? couleurSigne(BuildContext context, double? v) {
  if (v == null || v == 0) return null;
  return v > 0 ? vert : rouge;
}

class Indicateur extends StatelessWidget {
  const Indicateur(this.libelle, this.valeur, {this.aide, this.couleur, super.key});

  final String libelle;
  final String valeur;
  final String? aide;
  final Color? couleur;

  @override
  Widget build(BuildContext context) {
    // Carte de chiffre de l'outil du PC (st.metric encadré).
    return SizedBox(width: 200, child: Metrique(libelle, valeur, aide: aide, couleur: couleur));
  }
}

class Section extends StatelessWidget {
  const Section(this.titre, this.enfants, {super.key});

  final String titre;
  final List<Widget> enfants;

  @override
  Widget build(BuildContext context) {
    // Des indicateurs seuls deviennent un bloc « libellé … valeur » (pf/ui.py : bloc_chiffres).
    if (enfants.isNotEmpty && enfants.every((e) => e is Indicateur)) {
      return Padding(
        padding: const EdgeInsets.only(top: 16),
        child: BlocChiffres(titre, [for (final e in enfants.cast<Indicateur>()) (e.libelle, e.valeur)],
            couleurs: {
              for (final e in enfants.cast<Indicateur>())
                if (e.couleur != null) e.libelle: e.couleur!,
            }),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(titre, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Wrap(spacing: 12, runSpacing: 12, children: enfants),
      ]),
    );
  }
}

/// Courbe d'une série datée (cours ou rang).
class Courbe extends StatelessWidget {
  const Courbe(this.points, {this.decimales = 2, this.hauteur = 220, super.key});

  final List<(DateTime, double)> points;
  final int decimales;
  final double hauteur;

  @override
  Widget build(BuildContext context) {
    if (points.length < 2) return const SizedBox.shrink();
    final s = Theme.of(context).colorScheme;
    final petit = Theme.of(context).textTheme.labelSmall;
    final spots = [for (final (d, v) in points) FlSpot(d.millisecondsSinceEpoch.toDouble(), v)];
    final debut = spots.first.x;
    final fin = spots.last.x;
    return SizedBox(
      height: hauteur,
      child: LineChart(LineChartData(
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            color: s.primary,
            barWidth: 2,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(show: true, color: s.primary.withValues(alpha: 0.08)),
          ),
        ],
        gridData: const FlGridData(show: true, drawVerticalLine: false),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 48,
              getTitlesWidget: (valeur, meta) => Text(nombre(valeur, valeur.abs() >= 100 ? 0 : 1), style: petit),
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 24,
              interval: (fin - debut) / 4,
              getTitlesWidget: (valeur, meta) {
                final d = DateTime.fromMillisecondsSinceEpoch(valeur.toInt());
                return Text('${d.month.toString().padLeft(2, '0')}/${d.year % 100}', style: petit);
              },
            ),
          ),
        ),
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipItems: (touches) => [
              for (final t in touches)
                LineTooltipItem(
                  '${dateFr(DateTime.fromMillisecondsSinceEpoch(t.x.toInt()).toIso8601String())}\n'
                  '${nombre(t.y, decimales)}',
                  TextStyle(color: s.onInverseSurface),
                ),
            ],
          ),
        ),
      )),
    );
  }
}

/// Rappel affiché quand une décision d'achat ou de vente est en jeu.
class AvertissementConseil extends StatelessWidget {
  const AvertissementConseil({super.key});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Text(
          'Mesures et scores tirés des données publiques : ce n\'est pas un conseil d\'investissement. '
          'Un rang élevé ne remplace pas l\'analyse de l\'entreprise.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      );
}
