/// Apparence de l'outil du PC (portefeuille/.streamlit/config.toml, pf/ui.py) reprise dans l'application :
/// mêmes couleurs, même police (Source Sans 3), mêmes titres, cartes de chiffres, encadrés, onglets et tableaux.
library;

import 'package:material_ui/material_ui.dart';

/// Couleurs d'un mode (clair ou sombre), celles du thème Streamlit de l'outil du PC.
class Teintes {
  const Teintes({
    required this.fond,
    required this.fondSecondaire,
    required this.texte,
    required this.bordure,
    required this.primaire,
    required this.series,
  });

  final Color fond;
  final Color fondSecondaire;
  final Color texte;
  final Color bordure;
  final Color primaire;

  /// Palette des graphiques, dans l'ordre fixe de pf/ui.py (jamais recyclée).
  final List<Color> series;

  Color get legende => texte.withValues(alpha: 0.6);
  Color get trait => const Color(0x38898781);
  Color get traitFort => const Color(0x73898781);

  static const clair = Teintes(
    fond: Color(0xFFFCFCFB),
    fondSecondaire: Color(0xFFF3F2EE),
    texte: Color(0xFF0B0B0B),
    bordure: Color(0xFFD8D7D0),
    primaire: Color(0xFF2A78D6),
    series: [
      Color(0xFF2A78D6), Color(0xFFEB6834), Color(0xFF1BAF7A), Color(0xFFEDA100),
      Color(0xFFE87BA4), Color(0xFF008300), Color(0xFF6250D6), Color(0xFFE34948),
    ],
  );

  static const sombre = Teintes(
    fond: Color(0xFF1A1A19),
    fondSecondaire: Color(0xFF242422),
    texte: Color(0xFFF0EFEC),
    bordure: Color(0xFF3A3A37),
    primaire: Color(0xFF3987E5),
    series: [
      Color(0xFF3987E5), Color(0xFFD95926), Color(0xFF199E70), Color(0xFFC98500),
      Color(0xFFD55181), Color(0xFF008300), Color(0xFF9085E9), Color(0xFFE66767),
    ],
  );

  static Teintes de(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? sombre : clair;
}

/// Couleurs d'état, identiques dans les deux modes (pf/ui.py : GOOD, CRITICAL).
const vert = Color(0xFF0CA30C);
const rouge = Color(0xFFD03B3B);
const orange = Color(0xFFE07B00);

const police = 'SourceSans3';

ThemeData themeGarp(Brightness luminosite) {
  final t = luminosite == Brightness.dark ? Teintes.sombre : Teintes.clair;
  final schema = ColorScheme.fromSeed(seedColor: t.primaire, brightness: luminosite).copyWith(
    primary: t.primaire,
    onPrimary: Colors.white,
    surface: t.fond,
    onSurface: t.texte,
    onSurfaceVariant: t.legende,
    surfaceContainerLowest: t.fond,
    surfaceContainerLow: t.fondSecondaire,
    surfaceContainer: t.fondSecondaire,
    surfaceContainerHigh: t.fondSecondaire,
    surfaceContainerHighest: Color.alphaBlend(t.texte.withValues(alpha: 0.06), t.fondSecondaire),
    outline: t.bordure,
    outlineVariant: t.bordure,
    error: rouge,
  );
  final base = ThemeData(colorScheme: schema, useMaterial3: true, fontFamily: police);
  final texte = base.textTheme.apply(bodyColor: t.texte, displayColor: t.texte);
  final arrondi = RoundedRectangleBorder(borderRadius: BorderRadius.circular(8));
  return base.copyWith(
    scaffoldBackgroundColor: t.fond,
    canvasColor: t.fond,
    dividerColor: t.trait,
    dividerTheme: DividerThemeData(color: t.trait, space: 1, thickness: 1),
    textTheme: texte.copyWith(
      // st.title, st.header, st.subheader, texte courant et légendes (st.caption) de Streamlit.
      displaySmall: texte.displaySmall?.copyWith(fontSize: 44, fontWeight: FontWeight.w700, height: 1.2),
      headlineMedium: texte.headlineMedium?.copyWith(fontSize: 34, fontWeight: FontWeight.w600, height: 1.2),
      headlineSmall: texte.headlineSmall?.copyWith(fontSize: 28, fontWeight: FontWeight.w600, height: 1.2),
      titleLarge: texte.titleLarge?.copyWith(fontSize: 21, fontWeight: FontWeight.w600),
      titleMedium: texte.titleMedium?.copyWith(fontSize: 17, fontWeight: FontWeight.w600),
      titleSmall: texte.titleSmall?.copyWith(fontSize: 15, fontWeight: FontWeight.w600),
      bodyLarge: texte.bodyLarge?.copyWith(fontSize: 16, height: 1.5),
      bodyMedium: texte.bodyMedium?.copyWith(fontSize: 15, height: 1.45),
      bodySmall: texte.bodySmall?.copyWith(fontSize: 14, height: 1.45, color: t.legende),
      labelLarge: texte.labelLarge?.copyWith(fontSize: 15, fontWeight: FontWeight.w400),
      labelMedium: texte.labelMedium?.copyWith(fontSize: 14, fontWeight: FontWeight.w400),
      labelSmall: texte.labelSmall?.copyWith(fontSize: 12.5, fontWeight: FontWeight.w400),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: t.fond,
      foregroundColor: t.texte,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      titleTextStyle: TextStyle(fontFamily: police, fontSize: 18, fontWeight: FontWeight.w600, color: t.texte),
    ),
    cardTheme: CardThemeData(
      color: t.fond,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: const EdgeInsets.symmetric(vertical: 6),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8), side: BorderSide(color: t.bordure)),
    ),
    listTileTheme: ListTileThemeData(
      iconColor: t.legende,
      subtitleTextStyle: TextStyle(fontFamily: police, fontSize: 14, color: t.legende),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: t.primaire,
        foregroundColor: Colors.white,
        shape: arrondi,
        minimumSize: const Size(0, 40),
        textStyle: const TextStyle(fontFamily: police, fontSize: 15),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: t.texte,
        backgroundColor: t.fond,
        side: BorderSide(color: t.bordure),
        shape: arrondi,
        minimumSize: const Size(0, 40),
        textStyle: const TextStyle(fontFamily: police, fontSize: 15),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: t.primaire, shape: arrondi),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: t.fondSecondaire,
      isDense: true,
      hintStyle: TextStyle(color: t.legende),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
      focusedBorder:
          OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: t.primaire)),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: t.fond,
      selectedColor: t.primaire.withValues(alpha: 0.1),
      side: BorderSide(color: t.bordure),
      shape: arrondi,
      labelStyle: TextStyle(fontFamily: police, fontSize: 14, color: t.texte),
      showCheckmark: false,
    ),
    tabBarTheme: TabBarThemeData(
      labelColor: t.primaire,
      unselectedLabelColor: t.texte,
      indicatorColor: t.primaire,
      dividerColor: t.trait,
      labelStyle: const TextStyle(fontFamily: police, fontSize: 15),
      unselectedLabelStyle: const TextStyle(fontFamily: police, fontSize: 15),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: t.fond,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    popupMenuTheme: PopupMenuThemeData(color: t.fond, surfaceTintColor: Colors.transparent),
    drawerTheme: DrawerThemeData(backgroundColor: t.fondSecondaire, surfaceTintColor: Colors.transparent),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: SegmentedButton.styleFrom(
        backgroundColor: t.fond,
        foregroundColor: t.texte,
        selectedBackgroundColor: t.primaire.withValues(alpha: 0.1),
        selectedForegroundColor: t.primaire,
        side: BorderSide(color: t.bordure),
        shape: arrondi,
        textStyle: const TextStyle(fontFamily: police, fontSize: 15),
      ),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? Colors.white : t.bordure),
      trackColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? t.primaire : t.fondSecondaire),
      trackOutlineColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? t.primaire : t.bordure),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: t.primaire, linearTrackColor: t.trait),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
    tooltipTheme: TooltipThemeData(
      waitDuration: const Duration(milliseconds: 300),
      textStyle: TextStyle(fontFamily: police, fontSize: 13, color: t.fond),
      decoration: BoxDecoration(color: t.texte.withValues(alpha: 0.92), borderRadius: BorderRadius.circular(6)),
    ),
  );
}

/// Marges de page de Streamlit en disposition large : 6 rem en haut, 5 rem sur les côtés (moins sur un téléphone).
EdgeInsets margesPage(double largeur, {double largeurMax = 1180}) {
  final cotes = largeur >= 700 ? 56.0 : 16.0;
  final reste = largeur - 2 * cotes;
  final centrage = reste > largeurMax ? (reste - largeurMax) / 2 : 0.0;
  return EdgeInsets.fromLTRB(cotes + centrage, largeur >= 700 ? 56 : 16, cotes + centrage, 48);
}

/// Une page de l'outil : grand titre (st.title), légende, puis le contenu.
class PageGarp extends StatelessWidget {
  const PageGarp({
    required this.enfants,
    this.titre,
    this.legende,
    this.avantTitre,
    this.actions = const [],
    this.largeurMax = 1180,
    this.controleur,
    super.key,
  });

  final String? titre;
  final String? legende;

  /// Contrôle placé au-dessus du titre, comme le choix de la valeur sur la fiche.
  final Widget? avantTitre;

  /// Boutons à droite du titre.
  final List<Widget> actions;
  final List<Widget> enfants;
  final double largeurMax;
  final ScrollController? controleur;

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, c) {
        final texte = Theme.of(context).textTheme;
        final etroit = c.maxWidth < 700;
        final integree = IntegreDansPage.dans(context);
        Widget liste(List<Widget> enfants) => integree
            ? Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: enfants)
            : ListView(
                controller: controleur,
                padding: margesPage(c.maxWidth, largeurMax: largeurMax),
                children: [IntegreDansPage(child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: enfants))],
              );
        return SelectionArea(
          child: liste(
            [
              if (avantTitre != null) Padding(padding: const EdgeInsets.only(bottom: 16), child: avantTitre),
              if (titre != null)
                Wrap(
                  alignment: WrapAlignment.spaceBetween,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  spacing: 12,
                  runSpacing: 8,
                  children: [
                    Text(titre!,
                        style: etroit ? texte.displaySmall?.copyWith(fontSize: 34) : texte.displaySmall),
                    if (actions.isNotEmpty) Wrap(spacing: 8, runSpacing: 8, children: actions),
                  ],
                ),
              if (legende != null)
                Padding(padding: const EdgeInsets.only(top: 14), child: Text(legende!, style: texte.bodySmall)),
              if (titre != null || legende != null) const SizedBox(height: 8),
              ...enfants,
            ],
          ),
        );
      });
}

/// Sous-titre de section (st.subheader).
class SousTitre extends StatelessWidget {
  const SousTitre(this.texte, {this.action, this.aide, super.key});

  final String texte;
  final Widget? action;
  final String? aide;

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.headlineSmall;
    final etroit = MediaQuery.sizeOf(context).width < 700;
    return Padding(
      padding: const EdgeInsets.only(top: 28, bottom: 12),
      child: Row(children: [
        Flexible(child: Text(texte, style: etroit ? style?.copyWith(fontSize: 23) : style)),
        if (aide != null) ...[const SizedBox(width: 8), Aide(aide!)],
        if (action != null) ...[const Spacer(), action!],
      ]),
    );
  }
}

/// Titre court en gras (st.markdown("**…**")).
class Intertitre extends StatelessWidget {
  const Intertitre(this.texte, {super.key});

  final String texte;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 16, bottom: 8),
        child: Text(texte, style: Theme.of(context).textTheme.titleMedium),
      );
}

/// Légende grise (st.caption).
class Legende extends StatelessWidget {
  const Legende(this.texte, {this.haut = 6, super.key});

  final String texte;
  final double haut;

  @override
  Widget build(BuildContext context) => Padding(
        padding: EdgeInsets.only(top: haut, bottom: 6),
        child: Text(texte, style: Theme.of(context).textTheme.bodySmall),
      );
}

/// Point d'interrogation qui affiche une explication (le « help » de Streamlit).
class Aide extends StatelessWidget {
  const Aide(this.texte, {super.key});

  final String texte;

  @override
  Widget build(BuildContext context) => Tooltip(
        message: texte,
        triggerMode: TooltipTriggerMode.tap,
        showDuration: const Duration(seconds: 8),
        child: Icon(Icons.help_outline, size: 16, color: Teintes.de(context).legende),
      );
}

/// Carte de chiffre encadrée (st.metric(border=True)) : libellé, valeur en grand, variation sur pastille.
class Metrique extends StatelessWidget {
  const Metrique(this.libelle, this.valeur, {this.delta, this.deltaPositif, this.aide, this.couleur, super.key});

  final String libelle;
  final String valeur;

  /// Variation affichée sous la valeur, verte si [deltaPositif], rouge sinon, grise si null.
  final String? delta;
  final bool? deltaPositif;
  final String? aide;
  final Color? couleur;

  @override
  Widget build(BuildContext context) {
    final t = Teintes.de(context);
    final texte = Theme.of(context).textTheme;
    final teinteDelta = deltaPositif == null ? t.legende : (deltaPositif! ? vert : rouge);
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
      decoration: BoxDecoration(
        color: t.fond,
        border: Border.all(color: t.bordure),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        Row(children: [
          Flexible(child: Text(libelle, style: texte.labelMedium, maxLines: 2, overflow: TextOverflow.ellipsis)),
          if (aide != null) ...[const SizedBox(width: 6), Aide(aide!)],
        ]),
        const SizedBox(height: 6),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: Text(valeur, style: TextStyle(fontSize: 34, height: 1.15, color: couleur ?? t.texte)),
        ),
        if (delta != null) ...[
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: teinteDelta.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              if (deltaPositif != null)
                Icon(deltaPositif! ? Icons.arrow_upward : Icons.arrow_downward, size: 13, color: teinteDelta),
              if (deltaPositif != null) const SizedBox(width: 3),
              Text(delta!, style: TextStyle(fontSize: 13, color: teinteDelta)),
            ]),
          ),
        ],
      ]),
    );
  }
}

/// Colonnes de même largeur (st.columns) : côte à côte sur un grand écran, deux par rangée sur un téléphone.
class Colonnes extends StatelessWidget {
  const Colonnes(this.enfants, {this.espace = 16, this.minLargeur = 200, this.memeHauteur = false, super.key});

  /// Cartes d'une rangée à la même hauteur (pas avec un graphique ou un tableau, qui ne le supportent pas).
  final bool memeHauteur;

  final List<Widget> enfants;
  final double espace;

  /// Largeur minimale d'une colonne : en dessous, les colonnes passent à la ligne.
  final double minLargeur;

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, c) {
        if (enfants.isEmpty) return const SizedBox.shrink();
        var parRangee = enfants.length;
        while (parRangee > 1 && (c.maxWidth - espace * (parRangee - 1)) / parRangee < minLargeur) {
          parRangee = parRangee > 2 && parRangee.isOdd ? parRangee - 1 : (parRangee / 2).ceil();
        }
        final rangees = <Widget>[];
        for (var i = 0; i < enfants.length; i += parRangee) {
          final bloc = enfants.sublist(i, (i + parRangee).clamp(0, enfants.length));
          final rangee = Row(
              crossAxisAlignment: memeHauteur ? CrossAxisAlignment.stretch : CrossAxisAlignment.start,
              children: [
              for (final (j, e) in bloc.indexed) ...[
                if (j > 0) SizedBox(width: espace),
                Expanded(child: e),
              ],
              for (var k = bloc.length; k < parRangee; k++) ...[SizedBox(width: espace), const Spacer()],
            ]);
          rangees.add(memeHauteur ? IntrinsicHeight(child: rangee) : rangee);
        }
        return Column(children: [
          for (final (i, r) in rangees.indexed) ...[if (i > 0) SizedBox(height: espace), r],
        ]);
      });
}

/// Rangée de cartes de chiffres (st.columns + st.metric), de même hauteur.
class Metriques extends StatelessWidget {
  const Metriques(this.metriques, {this.minLargeur = 170, super.key});

  final List<Widget> metriques;
  final double minLargeur;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Colonnes(metriques, minLargeur: minLargeur, memeHauteur: true),
      );
}

enum NatureEncadre { info, succes, avertissement, erreur }

/// Encadré coloré (st.info, st.success, st.warning, st.error).
class Encadre extends StatelessWidget {
  const Encadre(this.texte, {this.nature = NatureEncadre.info, this.icone, this.action, this.enfant, super.key});

  const Encadre.succes(this.texte, {this.icone, this.action, this.enfant, super.key}) : nature = NatureEncadre.succes;

  const Encadre.avertissement(this.texte, {this.icone, this.action, this.enfant, super.key})
      : nature = NatureEncadre.avertissement;

  const Encadre.erreur(this.texte, {this.icone, this.action, this.enfant, super.key}) : nature = NatureEncadre.erreur;

  final String texte;
  final NatureEncadre nature;
  final IconData? icone;
  final Widget? action;
  final Widget? enfant;

  @override
  Widget build(BuildContext context) {
    final sombre = Theme.of(context).brightness == Brightness.dark;
    final (teinte, iconeParDefaut) = switch (nature) {
      NatureEncadre.info => (const Color(0xFF1C83E1), Icons.info_outline),
      NatureEncadre.succes => (const Color(0xFF21C354), Icons.check_circle_outline),
      NatureEncadre.avertissement => (const Color(0xFFFFBD45), Icons.warning_amber_outlined),
      NatureEncadre.erreur => (const Color(0xFFFF4B4B), Icons.error_outline),
    };
    final encre = switch (nature) {
      NatureEncadre.info => sombre ? const Color(0xFFC7EBFF) : const Color(0xFF004280),
      NatureEncadre.succes => sombre ? const Color(0xFFDFFDE9) : const Color(0xFF177233),
      NatureEncadre.avertissement => sombre ? const Color(0xFFFFFFC2) : const Color(0xFF926C05),
      NatureEncadre.erreur => sombre ? const Color(0xFFFFDEDE) : const Color(0xFF7D353B),
    };
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: teinte.withValues(alpha: sombre ? 0.2 : 0.1),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icone ?? iconeParDefaut, size: 20, color: encre),
        const SizedBox(width: 10),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(texte, style: TextStyle(color: encre, fontSize: 15, height: 1.45)),
            ?enfant,
          ]),
        ),
        if (action != null) ...[const SizedBox(width: 8), action!],
      ]),
    );
  }
}

/// Marque un contenu déjà placé dans une page qui défile : une [PageDefilante] y devient une simple colonne.
class IntegreDansPage extends InheritedWidget {
  const IntegreDansPage({required super.child, super.key});

  static bool dans(BuildContext context) => context.dependOnInheritedWidgetOfExactType<IntegreDansPage>() != null;

  @override
  bool updateShouldNotify(IntegreDansPage oldWidget) => false;
}

/// Onglets de l'outil (st.tabs) : titres soulignés, l'actif en bleu, contenu en dessous.
class Onglets extends StatefulWidget {
  const Onglets(this.onglets, {this.initial = 0, this.surChangement, this.segments = false, super.key});

  /// Boutons groupés (st.segmented_control, comme sur la fiche) plutôt que titres soulignés.
  final bool segments;

  /// Titre et constructeur de chaque onglet (construit seulement quand il est affiché).
  final List<(String, WidgetBuilder)> onglets;
  final int initial;
  final ValueChanged<int>? surChangement;

  @override
  State<Onglets> createState() => _OngletsState();
}

class _OngletsState extends State<Onglets> {
  late int _actif = widget.initial;

  @override
  Widget build(BuildContext context) {
    final actif = _actif.clamp(0, widget.onglets.length - 1);
    final t = Teintes.de(context);
    void choisir(int i) {
      setState(() => _actif = i);
      widget.surChangement?.call(i);
    }

    if (widget.segments) {
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Padding(
          padding: const EdgeInsets.only(top: 12, bottom: 16),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Segments([for (final (titre, _) in widget.onglets) titre], {actif}, choisir),
          ),
        ),
        IntegreDansPage(child: Builder(builder: widget.onglets[actif].$2)),
      ]);
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Container(
        margin: const EdgeInsets.only(top: 12, bottom: 16),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: t.trait, width: 2))),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(children: [
            for (final (i, (titre, _)) in widget.onglets.indexed)
              InkWell(
                onTap: () => choisir(i),
                child: Container(
                  padding: const EdgeInsets.fromLTRB(2, 8, 2, 8),
                  margin: const EdgeInsets.only(right: 18),
                  decoration: BoxDecoration(
                    border: Border(
                        bottom: BorderSide(color: i == actif ? t.primaire : Colors.transparent, width: 2)),
                  ),
                  child: Text(titre, style: TextStyle(fontSize: 15, color: i == actif ? t.primaire : t.texte)),
                ),
              ),
          ]),
        ),
      ),
      IntegreDansPage(child: Builder(builder: widget.onglets[actif].$2)),
    ]);
  }
}

/// Boutons groupés (st.segmented_control / st.pills) : les choisis en bleu.
class Segments extends StatelessWidget {
  const Segments(this.libelles, this.choisis, this.surChoix, {this.titre, super.key});

  final List<String> libelles;
  final Set<int> choisis;
  final ValueChanged<int> surChoix;
  final String? titre;

  @override
  Widget build(BuildContext context) {
    final t = Teintes.de(context);
    final rangee = Wrap(runSpacing: 6, children: [
      for (final (i, l) in libelles.indexed)
        Builder(builder: (context) {
          final choisi = choisis.contains(i);
          final premier = i == 0, dernier = i == libelles.length - 1;
          final rayon = BorderRadius.horizontal(
            left: premier ? const Radius.circular(8) : Radius.zero,
            right: dernier ? const Radius.circular(8) : Radius.zero,
          );
          return Material(
            color: choisi ? t.primaire.withValues(alpha: 0.1) : t.fond,
            shape: RoundedRectangleBorder(
              borderRadius: rayon,
              side: BorderSide(color: choisi ? t.primaire : t.bordure),
            ),
            child: InkWell(
              borderRadius: rayon,
              onTap: () => surChoix(i),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: Text(l, style: TextStyle(fontSize: 15, color: choisi ? t.primaire : t.texte)),
              ),
            ),
          );
        }),
    ]);
    if (titre == null) return rangee;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
      Text(titre!, style: Theme.of(context).textTheme.labelMedium),
      const SizedBox(height: 6),
      rangee,
    ]);
  }
}

/// Barre de score dans un tableau (ProgressColumn de Streamlit) : barre bleue et nombre.
class BarreScore extends StatelessWidget {
  const BarreScore(this.valeur, {this.max = 100, this.decimales = 0, this.largeur = 90, super.key});

  final double? valeur;
  final double max;
  final int decimales;
  final double largeur;

  @override
  Widget build(BuildContext context) {
    final t = Teintes.de(context);
    final v = valeur;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      SizedBox(
        width: largeur,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: v == null ? 0 : (v / max).clamp(0, 1),
            minHeight: 8,
            color: t.primaire,
            backgroundColor: t.trait,
          ),
        ),
      ),
      const SizedBox(width: 10),
      SizedBox(
        width: 28,
        child: Text(v == null ? '—' : v.toStringAsFixed(decimales),
            textAlign: TextAlign.end, style: TextStyle(fontSize: 13, color: t.legende)),
      ),
    ]);
  }
}

/// Colonne d'un [Tableau].
class Colonne {
  const Colonne(this.titre, {this.largeur, this.flex = 1, this.droite = false, this.aide});

  final String titre;

  /// Largeur fixe ; sans elle, la colonne prend sa part ([flex]) de la place restante.
  final double? largeur;
  final int flex;
  final bool droite;
  final String? aide;
}

/// Tableau de données (st.dataframe) : en-tête gris, lignes séparées par un trait, encadré, défilement horizontal
/// quand l'écran est trop étroit. Les cellules sont du texte ou des widgets.
class Tableau extends StatelessWidget {
  const Tableau({
    required this.colonnes,
    required this.lignes,
    this.surClic,
    this.largeurMin = 760,
    this.hauteurLigne = 38,
    super.key,
  });

  final List<Colonne> colonnes;
  final List<List<Object?>> lignes;
  final ValueChanged<int>? surClic;

  /// Largeur sous laquelle le tableau défile horizontalement plutôt que de se tasser.
  final double largeurMin;
  final double hauteurLigne;

  @override
  Widget build(BuildContext context) {
    final t = Teintes.de(context);
    final petit = TextStyle(fontSize: 14, color: t.texte);
    Widget cellule(Object? c, Colonne col, {bool entete = false}) {
      final Widget contenu = switch (c) {
        Widget w => w,
        _ => Text(c?.toString() ?? '—',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: col.droite ? TextAlign.end : TextAlign.start,
            style: entete ? TextStyle(fontSize: 14, color: t.legende) : petit),
      };
      final boite = Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Align(alignment: col.droite ? Alignment.centerRight : Alignment.centerLeft, child: contenu),
      );
      return col.largeur != null ? SizedBox(width: col.largeur, child: boite) : Expanded(flex: col.flex, child: boite);
    }

    Widget rangee(List<Object?> cellules, {bool entete = false, VoidCallback? clic}) {
      final r = Container(
        height: entete ? 36 : hauteurLigne,
        decoration: BoxDecoration(
          color: entete ? t.fondSecondaire.withValues(alpha: 0.6) : null,
          border: Border(bottom: BorderSide(color: t.trait)),
        ),
        child: Row(children: [
          for (final (i, col) in colonnes.indexed)
            cellule(i < cellules.length ? cellules[i] : null, col, entete: entete),
        ]),
      );
      return clic == null ? r : InkWell(onTap: clic, child: r);
    }

    final contenu = Column(mainAxisSize: MainAxisSize.min, children: [
      rangee([
        for (final c in colonnes)
          c.aide == null
              ? c.titre
              : Row(mainAxisSize: MainAxisSize.min, children: [
                  Flexible(
                      child: Text(c.titre,
                          overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 14, color: t.legende))),
                  const SizedBox(width: 4),
                  Aide(c.aide!),
                ]),
      ], entete: true),
      for (final (i, l) in lignes.indexed) rangee(l, clic: surClic == null ? null : () => surClic!(i)),
    ]);
    return LayoutBuilder(builder: (context, c) {
      final cadre = Container(
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(border: Border.all(color: t.bordure), borderRadius: BorderRadius.circular(8)),
        child: contenu,
      );
      if (c.maxWidth >= largeurMin) return cadre;
      return SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: SizedBox(width: largeurMin, child: cadre),
      );
    });
  }
}

/// Bloc titré de lignes « libellé … valeur » (pf/ui.py : bloc_chiffres), valeurs alignées à droite.
class BlocChiffres extends StatelessWidget {
  const BlocChiffres(this.titre, this.lignes, {this.forts = const {}, this.couleurs = const {}, super.key});

  final String titre;
  final List<(String, String)> lignes;
  final Set<String> forts;

  /// Couleur de certaines valeurs (variation positive ou négative), par libellé.
  final Map<String, Color> couleurs;

  @override
  Widget build(BuildContext context) {
    final t = Teintes.de(context);
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      decoration: BoxDecoration(border: Border.all(color: t.traitFort), borderRadius: BorderRadius.circular(10)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Text(titre, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
        ),
        for (final (libelle, valeur) in lignes)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 5),
            decoration: BoxDecoration(border: Border(top: BorderSide(color: t.trait))),
            child: Row(children: [
              Expanded(
                child: Text(libelle,
                    style: TextStyle(
                        fontSize: 15,
                        color: forts.contains(libelle) ? t.texte : t.texte.withValues(alpha: 0.72),
                        fontWeight: forts.contains(libelle) ? FontWeight.w600 : null)),
              ),
              const SizedBox(width: 12),
              Text(valeur,
                  style: TextStyle(
                      fontSize: 15,
                      color: couleurs[libelle],
                      fontFeatures: const [FontFeature.tabularFigures()],
                      fontWeight: forts.contains(libelle) ? FontWeight.w600 : null)),
            ]),
          ),
      ]),
    );
  }
}

/// Bouton secondaire encadré, avec ou sans icône (st.button).
Widget bouton(String libelle, VoidCallback? action, {IconData? icone, bool primaire = false}) {
  if (primaire) {
    return icone == null
        ? FilledButton(onPressed: action, child: Text(libelle))
        : FilledButton.icon(onPressed: action, icon: Icon(icone, size: 18), label: Text(libelle));
  }
  return icone == null
      ? OutlinedButton(onPressed: action, child: Text(libelle))
      : OutlinedButton.icon(onPressed: action, icon: Icon(icone, size: 18), label: Text(libelle));
}
