import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../graphiques.dart';

/// Texte avec **gras** et `code` ; les liens [texte](adresse) gardent leur texte.
TextSpan _enLigne(String texte, TextStyle? style) {
  final sansLiens = texte.replaceAllMapped(RegExp(r'\[([^\]]+)\]\([^)]*\)'), (m) => m.group(1)!);
  final morceaux = <TextSpan>[];
  var reste = sansLiens;
  final marque = RegExp(r'\*\*(.+?)\*\*|`([^`]+)`');
  while (true) {
    final m = marque.firstMatch(reste);
    if (m == null) break;
    if (m.start > 0) morceaux.add(TextSpan(text: reste.substring(0, m.start)));
    if (m.group(1) != null) {
      morceaux.add(TextSpan(text: m.group(1), style: const TextStyle(fontWeight: FontWeight.w700)));
    } else {
      morceaux.add(TextSpan(text: m.group(2), style: const TextStyle(fontFamily: 'monospace')));
    }
    reste = reste.substring(m.end);
  }
  morceaux.add(TextSpan(text: reste));
  return TextSpan(style: style, children: morceaux);
}

/// Rendu simple d'un document Markdown : titres, paragraphes, listes, tableaux, blocs de code.
List<Widget> rendreMarkdown(BuildContext context, String source) {
  final texte = Theme.of(context).textTheme;
  final out = <Widget>[];
  final paragraphe = <String>[];
  final tableau = <List<String>>[];
  void vider() {
    if (paragraphe.isNotEmpty) {
      out.add(Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text.rich(_enLigne(paragraphe.join(' '), texte.bodyMedium)),
      ));
      paragraphe.clear();
    }
    if (tableau.isNotEmpty) {
      out.add(Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Table(
            defaultColumnWidth: const IntrinsicColumnWidth(),
            border: TableBorder(horizontalInside: BorderSide(color: Theme.of(context).dividerColor)),
            children: [
              for (final (i, ligne) in tableau.indexed)
                TableRow(children: [
                  for (final cellule in ligne)
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 380),
                        child: Text.rich(_enLigne(cellule, i == 0 ? texte.labelLarge : texte.bodySmall)),
                      ),
                    ),
                ]),
            ],
          ),
        ),
      ));
      tableau.clear();
    }
  }

  var code = false;
  for (final brute in source.split('\n')) {
    final l = brute.trimRight();
    if (l.trimLeft().startsWith('```')) {
      vider();
      code = !code;
      continue;
    }
    if (code) {
      out.add(Text(l, style: texte.bodySmall?.copyWith(fontFamily: 'monospace')));
      continue;
    }
    final t = l.trimLeft();
    if (t.startsWith('|')) {
      if (paragraphe.isNotEmpty) vider();
      final cellules = [for (final c in t.substring(1, t.endsWith('|') ? t.length - 1 : t.length).split('|')) c.trim()];
      if (!cellules.every((c) => RegExp(r'^:?-+:?$').hasMatch(c))) tableau.add(cellules);
      continue;
    }
    if (tableau.isNotEmpty) vider();
    if (t.isEmpty) {
      vider();
    } else if (t.startsWith('#')) {
      vider();
      final niveau = t.indexOf(' ');
      final style = switch (niveau) { 1 => texte.headlineSmall, 2 => texte.titleLarge, _ => texte.titleMedium };
      out.add(Padding(
        padding: EdgeInsets.only(top: niveau <= 2 ? 18 : 10, bottom: 6),
        child: Text(t.substring(niveau + 1), style: style),
      ));
    } else if (RegExp(r'^([-*]|\d+\.)\s').hasMatch(t)) {
      vider();
      final espace = t.indexOf(' ');
      out.add(Padding(
        padding: EdgeInsets.only(left: 8.0 + (l.length - t.length) * 6, bottom: 4),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 22, child: Text(t.startsWith(RegExp(r'\d')) ? t.substring(0, espace) : '•')),
          Expanded(child: Text.rich(_enLigne(t.substring(espace + 1), texte.bodyMedium))),
        ]),
      ));
    } else if (t.startsWith('>')) {
      vider();
      out.add(Padding(
        padding: const EdgeInsets.only(left: 12, bottom: 8),
        child: Text.rich(_enLigne(t.substring(1).trim(), texte.bodyMedium?.copyWith(fontStyle: FontStyle.italic))),
      ));
    } else if (!t.startsWith('![')) {
      paragraphe.add(t);
    }
  }
  vider();
  return out;
}

/// La méthode de l'outil et la routine d'investissement (docs/METHODE.md, embarqué dans l'application).
class PageGuide extends StatelessWidget {
  const PageGuide({super.key});

  @override
  Widget build(BuildContext context) => FutureBuilder<String>(
        future: rootBundle.loadString('assets/methode.md'),
        builder: (context, lu) => lu.hasData
            ? PageDefilante(rendreMarkdown(context, lu.data!), largeurMax: 900)
            : const Center(child: CircularProgressIndicator()),
      );
}
