/// Briques d'interface des écrans d'analyse : cartes, barres annuelles, courbes comparées, répartitions, curseurs.
library;

import 'package:fl_chart/fl_chart.dart';
import 'package:material_ui/material_ui.dart';

import 'formats.dart';
import 'import_portefeuille.dart';
import 'interface.dart';

/// Montant abrégé : 886 342 -> « 886 k », 2 540 964 -> « 2,5 M », 3,2e9 -> « 3,2 Md ».
String montantCourt(double? v, [String devise = '']) {
  if (v == null) return vide;
  final suffixe = devise.isEmpty ? '' : ' $devise';
  for (final (seuil, unite, d) in [(1e12, 'Bn', 1), (1e9, 'Md', 1), (1e6, 'M', 1), (1e3, 'k', 0)]) {
    if (v.abs() >= seuil) return '${nombre(v / seuil, d)} $unite$suffixe';
  }
  return '${nombre(v, v.abs() < 10 ? 2 : 0)}$suffixe';
}

/// Demande un nombre ; null si l'utilisateur annule, NaN s'il vide le champ.
Future<double?> demanderNombre(BuildContext context, String titre,
    {double? actuel, String? suffixe, String? aide, int decimales = 2}) {
  final champ = TextEditingController(text: actuel == null ? '' : nombre(actuel, decimales));
  double lu() => champ.text.trim().isEmpty ? double.nan : (lireNombre(champ.text) ?? double.nan);
  return showDialog<double?>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(titre),
      content: TextField(
        controller: champ,
        autofocus: true,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: InputDecoration(suffixText: suffixe, helperText: aide, helperMaxLines: 3),
        onSubmitted: (_) => Navigator.pop(context, lu()),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
        FilledButton(onPressed: () => Navigator.pop(context, lu()), child: const Text('Enregistrer')),
      ],
    ),
  );
}

/// Carte titrée, au contenu libre.
class Carte extends StatelessWidget {
  const Carte(this.titre, {required this.enfant, this.sousTitre, this.action, super.key});

  final String titre;
  final String? sousTitre;
  final Widget enfant;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final texte = Theme.of(context).textTheme;
    final t = Teintes.de(context);
    // Conteneur encadré de Streamlit (st.container(border=True)) : titre en gras, contenu libre.
    return Container(
      margin: const EdgeInsets.only(top: 16),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
      decoration: BoxDecoration(border: Border.all(color: t.bordure), borderRadius: BorderRadius.circular(8)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(titre, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600))),
          ?action,
        ]),
        if (sousTitre != null) Padding(padding: const EdgeInsets.only(top: 2), child: Text(sousTitre!, style: texte.bodySmall)),
        const SizedBox(height: 12),
        enfant,
      ]),
    );
  }
}

/// Étiquette colorée courte (verdict, mouvement, statut).
class Pastille extends StatelessWidget {
  const Pastille(this.texte, {this.fond, this.couleur, super.key});

  final String texte;
  final Color? fond;
  final Color? couleur;

  @override
  Widget build(BuildContext context) {
    final s = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: fond ?? s.surfaceContainerHighest, borderRadius: BorderRadius.circular(8)),
      child: Text(texte, style: Theme.of(context).textTheme.labelSmall?.copyWith(color: couleur ?? s.onSurfaceVariant)),
    );
  }
}

/// Chiffre clé : libellé au-dessus, valeur en grand, détail en dessous.
class Chiffre extends StatelessWidget {
  const Chiffre(this.libelle, this.valeur, {this.detail, this.couleur, this.largeur = 170, super.key});

  final String libelle;
  final String valeur;
  final String? detail;
  final Color? couleur;
  final double largeur;

  @override
  Widget build(BuildContext context) {
    final texte = Theme.of(context).textTheme;
    final t = Teintes.de(context);
    // Chiffre de st.metric sans cadre : libellé, valeur en grand, détail en gris.
    return SizedBox(
      width: largeur,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(libelle, style: texte.labelMedium),
        const SizedBox(height: 2),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: Text(valeur, style: TextStyle(fontSize: 30, height: 1.2, color: couleur ?? t.texte)),
        ),
        if (detail != null) Text(detail!, style: texte.bodySmall),
      ]),
    );
  }
}

/// Répartition en barres horizontales : {libellé: part de 0 à 1}.
class BarresParts extends StatelessWidget {
  const BarresParts(this.parts, {this.largeurLibelle = 150, super.key});

  final Map<String, double> parts;
  final double largeurLibelle;

  @override
  Widget build(BuildContext context) => Column(children: [
        for (final e in parts.entries)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Row(children: [
              SizedBox(width: largeurLibelle, child: Text(e.key, maxLines: 1, overflow: TextOverflow.ellipsis)),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(value: e.value.clamp(0, 1), minHeight: 14),
                ),
              ),
              SizedBox(width: 56, child: Text(pct(e.value, 0), textAlign: TextAlign.end)),
            ]),
          ),
      ]);
}

/// Curseur avec son libellé et sa valeur affichée.
class Curseur extends StatelessWidget {
  const Curseur(this.libelle, this.valeur, this.min, this.max, this.pas, this.texte, this.onChanged, {super.key});

  final String libelle;
  final double valeur;
  final double min;
  final double max;
  final double pas;
  final String texte;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(libelle)),
          Text(texte, style: Theme.of(context).textTheme.titleSmall),
        ]),
        Slider(
          value: valeur.clamp(min, max),
          min: min,
          max: max,
          divisions: ((max - min) / pas).round(),
          label: texte,
          onChanged: onChanged,
        ),
      ]);
}

// Palette de l'outil du PC (pf/ui.py, ordre fixe) : bleu, orange, vert, ambre.
const _couleursSeries = [Color(0xFF2A78D6), Color(0xFFEB6834), Color(0xFF1BAF7A), Color(0xFFEDA100)];

Widget _legende(BuildContext context, List<String> noms) => Wrap(spacing: 12, children: [
      for (final (i, nom) in noms.indexed)
        Row(mainAxisSize: MainAxisSize.min, children: [
          Container(width: 10, height: 10, color: _couleursSeries[i % _couleursSeries.length]),
          const SizedBox(width: 4),
          Text(nom, style: Theme.of(context).textTheme.labelSmall),
        ]),
    ]);

/// Barres par exercice : `series` = {nom: une valeur par libellé (null : absente)}.
class BarresAnnuelles extends StatelessWidget {
  const BarresAnnuelles(this.libelles, this.series, {this.hauteur = 190, this.montants = true, super.key});

  final List<String> libelles;
  final Map<String, List<double?>> series;
  final double hauteur;

  /// Montants abrégés (« 2,5 Md ») sur l'axe ; sinon nombres à deux décimales.
  final bool montants;

  @override
  Widget build(BuildContext context) {
    final petit = Theme.of(context).textTheme.labelSmall;
    final noms = series.keys.toList();
    final toutes = [for (final s in series.values) ...s.whereType<double>()];
    if (toutes.isEmpty) return const Text('Donnée absente.');
    final largeur = libelles.length > 9 ? 5.0 : 9.0;
    String format(double v) => montants ? montantCourt(v) : nombre(v, 2);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SizedBox(
        height: hauteur,
        child: BarChart(BarChartData(
          barGroups: [
            for (final (i, _) in libelles.indexed)
              BarChartGroupData(x: i, barsSpace: 2, barRods: [
                for (final (k, nom) in noms.indexed)
                  BarChartRodData(
                    toY: series[nom]![i] ?? 0,
                    width: largeur,
                    color: _couleursSeries[k % _couleursSeries.length],
                    borderRadius: BorderRadius.circular(2),
                  ),
              ]),
          ],
          gridData: const FlGridData(show: true, drawVerticalLine: false),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 56,
                getTitlesWidget: (v, meta) => Text(format(v), style: petit),
              ),
            ),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 22,
                getTitlesWidget: (v, meta) {
                  final i = v.round();
                  if (i < 0 || i >= libelles.length) return const SizedBox.shrink();
                  // Un libellé sur deux quand ils sont nombreux ; le dernier (« 12 mois ») toujours.
                  if (libelles.length > 8 && i.isOdd != (libelles.length - 1).isOdd) return const SizedBox.shrink();
                  final l = libelles[i];
                  return Text(l.length == 4 ? "'${l.substring(2)}" : '12 m', style: petit);
                },
              ),
            ),
          ),
          barTouchData: BarTouchData(
            touchTooltipData: BarTouchTooltipData(
              getTooltipItem: (groupe, i, barre, k) => BarTooltipItem(
                '${libelles[groupe.x]} · ${noms[k]}\n${format(barre.toY)}',
                TextStyle(color: Theme.of(context).colorScheme.onInverseSurface),
              ),
            ),
          ),
        )),
      ),
      if (noms.length > 1) _legende(context, noms),
    ]);
  }
}

/// Courbes datées superposées : {nom: [(date, valeur)]}. `pourcentage` affiche l'axe en %.
class Courbes extends StatelessWidget {
  const Courbes(this.series, {this.hauteur = 220, this.decimales = 0, this.pourcentage = false, super.key});

  final Map<String, List<(DateTime, double)>> series;
  final double hauteur;
  final int decimales;
  final bool pourcentage;

  @override
  Widget build(BuildContext context) {
    final s = Theme.of(context).colorScheme;
    final petit = Theme.of(context).textTheme.labelSmall;
    final noms = [for (final e in series.entries) if (e.value.length >= 2) e.key];
    if (noms.isEmpty) return const Text('Historique insuffisant.');
    final x = [for (final n in noms) ...series[n]!.map((p) => p.$1.millisecondsSinceEpoch.toDouble())];
    final debut = x.reduce((a, b) => a < b ? a : b), fin = x.reduce((a, b) => a > b ? a : b);
    String format(double v) => pourcentage ? pct(v, decimales) : nombre(v, decimales);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SizedBox(
        height: hauteur,
        child: LineChart(LineChartData(
          lineBarsData: [
            for (final (i, n) in noms.indexed)
              LineChartBarData(
                spots: [for (final (d, v) in series[n]!) FlSpot(d.millisecondsSinceEpoch.toDouble(), v)],
                color: _couleursSeries[i % _couleursSeries.length],
                barWidth: 2,
                dotData: const FlDotData(show: false),
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
                reservedSize: 52,
                getTitlesWidget: (v, meta) => Text(format(v), style: petit),
              ),
            ),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 24,
                interval: (fin - debut) / 4,
                getTitlesWidget: (v, meta) {
                  final d = DateTime.fromMillisecondsSinceEpoch(v.toInt());
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
                    '${noms[t.barIndex]} · ${dateFr(DateTime.fromMillisecondsSinceEpoch(t.x.toInt()).toIso8601String())}'
                    '\n${format(t.y)}',
                    TextStyle(color: s.onInverseSurface),
                  ),
              ],
            ),
          ),
        )),
      ),
      if (noms.length > 1) _legende(context, noms),
    ]);
  }
}

/// Liste centrée et bornée en largeur : lisible sur un grand écran comme sur un téléphone.
class PageDefilante extends StatelessWidget {
  const PageDefilante(this.enfants, {this.largeurMax = 1180, this.titre, this.legende, this.actions = const [],
      super.key});

  final List<Widget> enfants;
  final double largeurMax;

  /// Grand titre de la page (st.title) et sa légende, comme dans l'outil du PC.
  final String? titre;
  final String? legende;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) =>
      PageGarp(titre: titre, legende: legende, actions: actions, largeurMax: largeurMax, enfants: enfants);
}

/// Message d'attente ou d'absence, centré.
class Vide extends StatelessWidget {
  const Vide(this.message, {this.icone = Icons.inbox_outlined, this.action, super.key});

  final String message;
  final IconData icone;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(icone, size: 48, color: Theme.of(context).colorScheme.outline),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            if (action != null) Padding(padding: const EdgeInsets.only(top: 12), child: action),
          ]),
        ),
      );
}
