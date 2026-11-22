/// Watchlist, présentée comme celle de l'outil du PC (vues/watchlist.py) : un tableau des valeurs suivies, avec
/// prix visé, écart au cours, verdict de la recherche personnalisée et score.
library;

import 'package:material_ui/material_ui.dart';

import '../formats.dart';
import '../graphiques.dart';
import '../interface.dart';
import '../main.dart';
import '../recherche.dart';
import '../stockage.dart';
import '../widgets.dart';
import 'opportunites.dart';

class PageWatchlist extends StatelessWidget {
  const PageWatchlist({super.key});

  Future<void> _ajouter(BuildContext context) async {
    final choix = await choisirValeur(context, titre: 'Ajouter une valeur');
    if (choix is ChoixValeur && !etat.suivie(choix.valeur.ticker)) await etat.basculerWatchlist(choix.valeur);
  }

  Future<void> _prixVise(BuildContext context, Suivie s) async {
    final v = etat.donnees?.valeurs[s.ticker];
    if (v == null) return;
    final prix = await demanderNombre(context, 'Prix visé : ${v.nom}',
        actuel: s.prixVise, suffixe: v.devise, aide: 'En devise de cotation. Laissez vide pour retirer le prix visé.');
    if (prix == null) return;
    await etat.fixerPrixVise(v, prix.isNaN ? null : prix, objectif: s.objectif ?? 'saisi à la main');
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        // Écart au prix visé : négatif quand le cours est passé dessous (prix atteint).
        double? ecart(Suivie s) {
          final cours = d?.valeurs[s.ticker]?.n('cours');
          return s.prixVise == null || cours == null ? null : cours / s.prixVise! - 1;
        }

        final liste = [...etat.watchlist]
          ..sort((a, b) => (ecart(a) ?? double.infinity).compareTo(ecart(b) ?? double.infinity));
        final atteints = etat.prixVisesAtteints.length;
        final actions = [bouton('Ajouter une valeur', () => _ajouter(context), icone: Icons.add)];
        const legende = 'Cliquez sur une valeur pour ouvrir sa fiche, sur un prix visé pour le modifier. On ajoute une '
            'valeur ici, depuis sa fiche ou depuis le screener. Le prix visé se fixe aussi dans la fiche, onglet '
            '« Prix juste ». Triée de la plus proche de son prix visé à la plus éloignée.';
        if (liste.isEmpty) {
          return PageDefilante(titre: 'Watchlist', legende: legende, actions: actions, const [
            Encadre('Aucune valeur suivie : touchez l\'étoile d\'une fiche ou du screener, ou le bouton « Ajouter une '
                'valeur ».'),
          ]);
        }
        return PageDefilante(
          titre: 'Watchlist',
          legende: legende,
          actions: actions,
          [
            if (atteints > 0)
              Encadre.succes('$atteints valeur${atteints > 1 ? 's ont' : ' a'} atteint votre prix visé : relisez la '
                  'thèse avant de décider.'),
            Onglets([
              ('Ma watchlist (${liste.length})', (context) => Tableau(
                    largeurMin: 1180,
                    colonnes: const [
                      Colonne('N°', largeur: 44, droite: true),
                      Colonne('Valeur', flex: 3),
                      Colonne('Ticker', largeur: 88),
                      Colonne('Cours', largeur: 82, droite: true),
                      Colonne('Devise', largeur: 58),
                      Colonne('Prix visé', largeur: 92, droite: true),
                      Colonne('Écart au prix visé', largeur: 120, droite: true),
                      Colonne('Objectif', flex: 2),
                      Colonne('Pour moi', largeur: 120),
                      Colonne('Statut', largeur: 80),
                      Colonne('Score', largeur: 140),
                      Colonne('Depuis l\'ajout', largeur: 104, droite: true),
                      Colonne('', largeur: 44),
                    ],
                    lignes: [
                      for (final (i, s) in liste.indexed)
                        () {
                          final v = d?.valeurs[s.ticker];
                          final cours = v?.n('cours');
                          final depuis = cours != null && (s.coursAjout ?? 0) > 0 ? cours / s.coursAjout! - 1 : null;
                          final e = ecart(s);
                          final verdict = v == null || v.fonds
                              ? null
                              : evaluer(v, 0, etat.profil, etat.reglagesValorisation).verdict;
                          return <Object?>[
                            '${i + 1}',
                            v?.nom ?? s.ticker,
                            s.ticker,
                            nombre(cours, 2),
                            v?.devise ?? '',
                            Builder(
                              builder: (context) => InkWell(
                                onTap: () => _prixVise(context, s),
                                child: Text(s.prixVise == null ? 'fixer' : nombre(s.prixVise, 2),
                                    style: TextStyle(
                                        fontSize: 14,
                                        color: Teintes.de(context).primaire,
                                        decoration: TextDecoration.underline,
                                        decorationStyle: TextDecorationStyle.dotted)),
                              ),
                            ),
                            e == null
                                ? '—'
                                : Text(e <= 0 ? 'atteint' : pct(e, 1, true),
                                    style: TextStyle(
                                        fontSize: 14,
                                        color: e <= 0 ? vert : null,
                                        fontWeight: e <= 0 ? FontWeight.w600 : null)),
                            s.objectif ?? '',
                            verdict == null ? '—' : PastilleVerdict(verdict),
                            v?.statut ?? '—',
                            v == null || v.fonds ? '' : BarreScore(v.n('score'), largeur: 76),
                            Text(pct(depuis, 1, true),
                                style: TextStyle(fontSize: 14, color: couleurSigne(context, depuis))),
                            IconButton(
                              tooltip: 'Retirer de la watchlist',
                              iconSize: 18,
                              visualDensity: VisualDensity.compact,
                              icon: const Icon(Icons.close),
                              onPressed: v == null ? null : () => etat.basculerWatchlist(v),
                            ),
                          ];
                        }(),
                    ],
                    surClic: (i) {
                      if (d?.valeurs[liste[i].ticker] != null) ouvrirFiche(context, liste[i].ticker);
                    },
                  )),
            ]),
            const AvertissementConseil(),
          ],
        );
      },
    );
  }
}
