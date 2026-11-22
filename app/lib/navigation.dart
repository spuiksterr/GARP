/// Navigation de l'outil du PC (portefeuille/app.py) : mêmes rubriques, mêmes groupes, même ordre, dans une
/// barre latérale à gauche (dans un tiroir sur un téléphone). S'y ajoutent les pages propres à l'application :
/// « Pour moi », les méthodes d'évaluation, le profil et les réglages.
library;

import 'package:material_ui/material_ui.dart';

import 'formats.dart';
import 'interface.dart';
import 'main.dart';
import 'pages/accueil.dart';
import 'pages/actualites.dart';
import 'pages/apport.dart';
import 'pages/construction.dart';
import 'pages/fiche.dart';
import 'pages/guide.dart';
import 'pages/investisseurs.dart';
import 'pages/methodes.dart';
import 'pages/opportunites.dart';
import 'pages/portefeuille.dart';
import 'pages/profil.dart';
import 'pages/regards.dart';
import 'pages/reglages.dart';
import 'pages/risques.dart';
import 'pages/screener.dart';
import 'pages/watchlist.dart';
import 'widgets.dart';

enum Rubrique {
  tableauDeBord('Investir', 'Tableau de bord', Icons.dashboard_outlined, Icons.dashboard),
  actualites('Investir', 'Actualités', Icons.feed_outlined, Icons.feed),
  composition('Investir', 'Composition', Icons.pie_chart_outline, Icons.pie_chart),
  apport('Investir', 'Apport du mois', Icons.savings_outlined, Icons.savings),
  monPortefeuille('Investir', 'Mon portefeuille', Icons.account_balance_wallet_outlined,
      Icons.account_balance_wallet),
  risques('Investir', 'Risques', Icons.shield_outlined, Icons.shield),
  pourMoi('Analyser', 'Pour moi', Icons.travel_explore_outlined, Icons.travel_explore),
  screener('Analyser', 'Screener', Icons.filter_alt_outlined, Icons.filter_alt),
  watchlist('Analyser', 'Watchlist', Icons.star_outline, Icons.star),
  fiche('Analyser', 'Fiche valeur', Icons.query_stats, Icons.query_stats),
  regards('Analyser', 'Quatre regards', Icons.visibility_outlined, Icons.visibility),
  investisseurs('Analyser', 'Grands investisseurs', Icons.groups_outlined, Icons.groups),
  construction('Analyser', 'Construction de portefeuille', Icons.tune_outlined, Icons.tune),
  backtest('Analyser', 'Backtest', Icons.history_outlined, Icons.history),
  guide('Comprendre', 'Méthode et routine', Icons.menu_book_outlined, Icons.menu_book),
  methodes('Comprendre', 'Méthodes d\'évaluation', Icons.insights_outlined, Icons.insights),
  profil('Mon compte', 'Mon profil', Icons.person_outline, Icons.person),
  reglages('Mon compte', 'Réglages', Icons.settings_outlined, Icons.settings);

  const Rubrique(this.groupe, this.libelle, this.icone, this.iconeChoisie);

  final String groupe;
  final String libelle;
  final IconData icone;
  final IconData iconeChoisie;

  Widget page() => switch (this) {
        tableauDeBord => const TableauDeBord(),
        actualites => const PageActualites(),
        composition => const PageComposition(),
        apport => const OngletApport(),
        monPortefeuille => const PageMonPortefeuille(),
        risques => const OngletRisques(),
        pourMoi => const PageOpportunites(),
        screener => const Screener(),
        watchlist => const PageWatchlist(),
        fiche => const PageFicheValeur(),
        regards => const PageRegards(),
        investisseurs => const OngletInvestisseurs(),
        construction => const OngletConstruction(),
        backtest => const OngletBacktest(),
        guide => const PageGuide(),
        methodes => const PageMethodes(),
        profil => const PageProfil(),
        reglages => const Reglages(),
      };
}

/// Rubrique affichée.
final rubrique = ValueNotifier<Rubrique>(Rubrique.tableauDeBord);

/// Valeur montrée par la rubrique « Fiche valeur ».
final tickerFiche = ValueNotifier<String?>(null);

/// Affiche une rubrique : referme d'abord les pages ouvertes par-dessus (portefeuille 13F, import…) et le tiroir.
void aller(BuildContext? context, Rubrique r) {
  if (context != null && context.mounted) Navigator.of(context).popUntil((route) => route.isFirst);
  rubrique.value = r;
}

/// Ouvre la fiche d'une valeur dans la rubrique « Fiche valeur », comme la recherche de l'outil du PC.
void ouvrirFicheValeur(BuildContext? context, String ticker) {
  tickerFiche.value = ticker;
  aller(context, Rubrique.fiche);
}

/// Cadre de l'application : barre latérale à gauche sur un grand écran, tiroir sur un téléphone.
class Coquille extends StatelessWidget {
  const Coquille({super.key});

  static const largeurBarre = 300.0;

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<Rubrique>(
        valueListenable: rubrique,
        builder: (context, r, _) {
          final page = KeyedSubtree(key: ValueKey(r), child: r.page());
          if (MediaQuery.sizeOf(context).width >= 900) {
            return Scaffold(
              body: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                const SizedBox(width: largeurBarre, child: BarreLaterale()),
                Expanded(child: page),
              ]),
            );
          }
          return Scaffold(
            appBar: AppBar(
              titleSpacing: 0,
              title: Row(children: [
                const Logo(taille: 26),
                const SizedBox(width: 10),
                Flexible(child: Text(r.libelle, overflow: TextOverflow.ellipsis)),
              ]),
              bottom: PreferredSize(
                preferredSize: const Size.fromHeight(1),
                child: Container(height: 1, color: Teintes.de(context).trait),
              ),
            ),
            drawer: const Drawer(width: largeurBarre, shape: RoundedRectangleBorder(), child: BarreLaterale()),
            body: page,
          );
        },
      );
}

/// Barre latérale de l'outil du PC : rubriques par groupe, recherche d'une valeur, date des cours, mise à jour.
class BarreLaterale extends StatelessWidget {
  const BarreLaterale({super.key});

  @override
  Widget build(BuildContext context) {
    final t = Teintes.de(context);
    final dansTiroir = Scaffold.maybeOf(context)?.hasDrawer ?? false;
    void choisir(Rubrique r) {
      if (dansTiroir) Scaffold.of(context).closeDrawer();
      aller(context, r);
    }

    return ListenableBuilder(
      listenable: Listenable.merge([etat, rubrique]),
      builder: (context, _) {
        final groupes = <String, List<Rubrique>>{};
        for (final r in Rubrique.values) {
          groupes.putIfAbsent(r.groupe, () => []).add(r);
        }
        final d = etat.donnees;
        final legende = TextStyle(fontSize: 14, color: t.legende, height: 1.45);
        return Material(
          color: t.fondSecondaire,
          child: SafeArea(
            right: false,
            child: ListView(padding: const EdgeInsets.fromLTRB(20, 20, 20, 28), children: [
              Row(children: [
                const Logo(taille: 34),
                const SizedBox(width: 10),
                Text('G.A.R.P', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: t.texte)),
              ]),
              const SizedBox(height: 18),
              for (final MapEntry(key: groupe, value: rubriques) in groupes.entries) ...[
                Padding(
                  padding: const EdgeInsets.fromLTRB(0, 10, 0, 6),
                  child: Text(groupe,
                      style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: t.texte.withValues(alpha: 0.8))),
                ),
                for (final r in rubriques) _Entree(r, choisie: rubrique.value == r, surClic: () => choisir(r)),
              ],
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 18),
                child: Divider(color: t.bordure, height: 1),
              ),
              Material(
                color: t.fond,
                borderRadius: BorderRadius.circular(8),
                child: InkWell(
                  borderRadius: BorderRadius.circular(8),
                  onTap: d == null
                      ? null
                      : () async {
                          final choix = await choisirValeur(context, titre: 'Rechercher une valeur');
                          if (choix is ChoixValeur && context.mounted) {
                            if (dansTiroir) Scaffold.of(context).closeDrawer();
                            ouvrirFicheValeur(context, choix.valeur.ticker);
                          }
                        },
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                    child: Row(children: [
                      Expanded(child: Text('Nom ou ticker…', style: legende)),
                      Icon(Icons.keyboard_arrow_down, size: 20, color: t.texte),
                    ]),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(d == null ? 'Aucune donnée téléchargée' : 'Cours au ${dateFr(d.donneesAu)}', style: legende),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  icon: etat.enCours
                      ? const SizedBox(
                          width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.bolt, size: 18),
                  label: Text(etat.enCours ? 'Téléchargement…' : 'Données de la nuit'),
                  onPressed: etat.enCours || !etat.configure ? null : etat.telechargerDonnees,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                etat.configure
                    ? 'Les données sont recalculées chaque nuit sur GitHub par l\'outil du PC. Ce bouton télécharge '
                        'la dernière version.'
                    : 'Accès aux données à configurer : rubrique Réglages.',
                style: etat.configure ? legende : legende.copyWith(color: orange),
              ),
              if (etat.erreur != null) ...[
                const SizedBox(height: 8),
                Text(etat.erreur!, style: legende.copyWith(color: orange)),
              ],
              const SizedBox(height: 14),
              Text('Outil d\'aide à la décision, pas un conseil en investissement personnalisé.', style: legende),
            ]),
          ),
        );
      },
    );
  }
}

class _Entree extends StatelessWidget {
  const _Entree(this.r, {required this.choisie, required this.surClic});

  final Rubrique r;
  final bool choisie;
  final VoidCallback surClic;

  @override
  Widget build(BuildContext context) {
    final t = Teintes.de(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Material(
        color: choisie ? t.texte.withValues(alpha: 0.07) : Colors.transparent,
        borderRadius: BorderRadius.circular(6),
        child: InkWell(
          borderRadius: BorderRadius.circular(6),
          onTap: surClic,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            child: Row(children: [
              Icon(choisie ? r.iconeChoisie : r.icone, size: 17, color: t.texte.withValues(alpha: choisie ? 1 : 0.75)),
              const SizedBox(width: 12),
              Expanded(
                child: Text(r.libelle,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontSize: 15,
                        color: t.texte.withValues(alpha: choisie ? 1 : 0.85),
                        fontWeight: choisie ? FontWeight.w600 : FontWeight.w400)),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}
