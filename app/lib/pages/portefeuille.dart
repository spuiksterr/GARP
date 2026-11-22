/// « Composition » (poids cibles, vues/modele.py) et « Mon portefeuille » (titres détenus, vues/suivi.py).
library;

import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../calculs.dart';
import '../formats.dart';
import '../graphiques.dart';
import '../interface.dart';
import '../main.dart';
import '../stockage.dart';
import '../suivi.dart';
import '../widgets.dart';
import 'import.dart';

Future<void> _ajouter(BuildContext context) async {
  final choix = await choisirValeur(context, titre: 'Ajouter une valeur');
  if (choix is! ChoixValeur || !context.mounted) return;
  final poids = await demanderPoids(context, actuel: etat.poids(choix.valeur.ticker), titre: choix.valeur.nom);
  if (poids != null) await etat.reglerPoids(choix.valeur.ticker, poids);
}

Future<void> _reglerPoids(BuildContext context, Ligne l) async {
  final p = await demanderPoids(context, actuel: l.poids, titre: etat.nomLigne(l));
  if (p != null) await etat.reglerPoids(l.ticker, p, nom: l.nom);
}

/// Nombre de titres détenus et prix de revient unitaire en euros : pour la valeur, l'apport et les plus-values.
Future<void> _position(BuildContext context, Ligne l) async {
  final q = await demanderNombre(context, 'Nombre de titres : ${etat.nomLigne(l)}',
      actuel: l.quantite, decimales: 4, aide: 'Laissez vide si vous ne suivez pas les quantités.');
  if (q == null || !context.mounted) return;
  if (q.isNaN) return etat.reglerPosition(l.ticker, null, null);
  final pru = await demanderNombre(context, 'Prix de revient unitaire, en euros',
      actuel: l.prixRevient, suffixe: '€', aide: 'Facultatif : sert à calculer la plus-value latente.');
  if (pru == null) return;
  await etat.reglerPosition(l.ticker, q, pru.isNaN ? null : pru);
}

Future<void> _menu(BuildContext context, String action) async {
  switch (action) {
    case 'fichier':
      await importerPortefeuille(context, SourceImport.fichier);
    case 'coller':
      await importerPortefeuille(context, SourceImport.pressePapiers);
    case 'saisir':
      await importerPortefeuille(context, SourceImport.saisie);
    case 'copier':
      await Clipboard.setData(ClipboardData(text: etat.portefeuilleEnTexte()));
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Portefeuille copié : collez-le dans G.A.R.P sur un autre appareil, ou dans un tableur.'),
        ));
      }
    case 'vider':
      final ok = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Vider le portefeuille ?'),
          content: const Text('Toutes les lignes seront retirées de cet appareil.'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Vider')),
          ],
        ),
      );
      if (ok == true) await etat.viderPortefeuille();
  }
}

/// Bouton « Importer » et son menu (fichier du courtier, tableau collé, saisie, copie, vider).
class _BoutonImport extends StatelessWidget {
  const _BoutonImport();

  @override
  Widget build(BuildContext context) => MenuAnchor(
        builder: (context, menu, _) => bouton('Importer', () => menu.isOpen ? menu.close() : menu.open(),
            icone: Icons.upload_file),
        menuChildren: [
          MenuItemButton(
              leadingIcon: const Icon(Icons.upload_file),
              onPressed: () => _menu(context, 'fichier'),
              child: const Text('Importer un fichier du courtier')),
          MenuItemButton(
              leadingIcon: const Icon(Icons.content_paste),
              onPressed: () => _menu(context, 'coller'),
              child: const Text('Coller un tableau')),
          MenuItemButton(
              leadingIcon: const Icon(Icons.edit_note),
              onPressed: () => _menu(context, 'saisir'),
              child: const Text('Saisir mes lignes')),
          if (etat.portefeuille.isNotEmpty) ...[
            MenuItemButton(
                leadingIcon: const Icon(Icons.copy),
                onPressed: () => _menu(context, 'copier'),
                child: const Text('Copier le portefeuille')),
            MenuItemButton(
                leadingIcon: const Icon(Icons.delete_sweep_outlined),
                onPressed: () => _menu(context, 'vider'),
                child: const Text('Vider')),
          ],
        ],
      );
}

Widget _invitationImport(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Encadre('G.A.R.P reconnaît vos lignes (nom, ticker ou ISIN) et calcule les poids à partir des montants ou '
          'des quantités. Vous vérifiez avant d\'enregistrer. Rien ne quitte cet appareil.'),
      const SizedBox(height: 8),
      const ChoixImport(),
      const SizedBox(height: 4),
      TextButton.icon(
        icon: const Icon(Icons.add),
        label: const Text('Ou ajoutez les valeurs une à une'),
        onPressed: () => _ajouter(context),
      ),
    ]);

/// Texte cliquable d'une cellule de tableau (poids à modifier, par exemple).
Widget _cliquable(BuildContext context, String texte, VoidCallback action, {String? aide}) => Tooltip(
      message: aide ?? '',
      child: InkWell(
        borderRadius: BorderRadius.circular(6),
        onTap: action,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
          child: Text(texte,
              style: TextStyle(
                  fontSize: 14,
                  color: Teintes.de(context).primaire,
                  decoration: TextDecoration.underline,
                  decorationStyle: TextDecorationStyle.dotted)),
        ),
      ),
    );

// --------------------------------------------------------------------------------------------- composition

class PageComposition extends StatelessWidget {
  const PageComposition({super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        final lignes = etat.portefeuille;
        final actions = [
          bouton('Ajouter une valeur', () => _ajouter(context), icone: Icons.add),
          const _BoutonImport(),
        ];
        if (lignes.isEmpty) {
          return PageDefilante(titre: 'Composition du portefeuille', actions: actions, [_invitationImport(context)]);
        }
        final poids = poidsNormalises(lignes);
        final total = lignes.fold<double>(0, (s, l) => s + l.poids);
        final effectives = poids.isEmpty ? null : 1 / poids.values.fold<double>(0, (s, w) => s + w * w);
        final noms = {for (final l in lignes) l.ticker: etat.nomLigne(l)};
        final triees = [...lignes]..sort((a, b) => b.poids.compareTo(a.poids));
        return PageDefilante(
          titre: 'Composition du portefeuille',
          legende: '${lignes.length} lignes · total des poids ${nombre(total, 1)} %. Les poids cibles partent de vos '
              'poids actuels : les apports du mois les visent. Cliquez sur un poids pour le modifier, sur une valeur '
              'pour ouvrir sa fiche. Stocké seulement sur cet appareil.',
          actions: actions,
          [
            if (d != null)
              Metriques([
                Metrique('Rentabilité moyenne', pct(moyenne(poids, d, 'roic_moyen')),
                    aide: 'ROIC moyen pondéré par les poids : ce que rapporte chaque euro investi dans l\'activité.'),
                Metrique('Marge opérationnelle', pct(moyenne(poids, d, 'marge_operationnelle'))),
                Metrique('Croissance attendue', pct(moyenne(poids, d, 'croissance_attendue'))),
                Metrique('TRI implicite', pct(moyenne(poids, d, 'tri_implicite'))),
                Metrique('Lignes effectives', nombre(effectives, 1),
                    aide: 'Nombre de lignes de même poids qui donneraient la même concentration (1 / somme des '
                        'poids au carré).'),
              ]),
            Onglets([
              ('Lignes', (context) => _lignes(context, triees, poids)),
              if (d != null && poids.isNotEmpty)
                ('Répartition', (context) {
                  final alertes = gardeFous(poids, d, noms: noms, profil: etat.profil);
                  return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    for (final g in alertes) Encadre.avertissement(g),
                    if (alertes.isEmpty) const Encadre.succes('Aucun seuil de concentration dépassé.'),
                    Colonnes(minLargeur: 320, [
                      Carte('Secteurs', enfant: BarresParts(repartition(poids, d, (v) => v.secteur))),
                      Carte('Devises de cotation', enfant: BarresParts(repartition(poids, d, (v) => v.devise))),
                    ]),
                    Colonnes(minLargeur: 320, [
                      Carte('Comptes', enfant: BarresParts(repartition(poids, d, (v) => v.enveloppe))),
                      Carte('Pays', enfant: BarresParts(repartition(poids, d, (v) => v.pays))),
                    ]),
                  ]);
                }),
            ]),
            const AvertissementConseil(),
          ],
        );
      },
    );
  }

  Widget _lignes(BuildContext context, List<Ligne> triees, Map<String, double> poids) {
    final d = etat.donnees;
    return Tableau(
      largeurMin: 980,
      colonnes: const [
        Colonne('Ticker', largeur: 96),
        Colonne('Valeur', flex: 3),
        Colonne('Compte', largeur: 70),
        Colonne('Poids', largeur: 78, droite: true),
        Colonne('Score', largeur: 150),
        Colonne('Moat estimé', largeur: 96),
        Colonne('Critères', largeur: 70),
        Colonne('PER prosp.', largeur: 82, droite: true),
        Colonne('TRI implicite', largeur: 96, droite: true),
        Colonne('1 mois', largeur: 74, droite: true),
        Colonne('', largeur: 44),
      ],
      lignes: [
        for (final l in triees)
          () {
            final v = d?.valeurs[l.ticker];
            return <Object?>[
              l.ticker,
              etat.nomLigne(l),
              v?.enveloppe ?? '—',
              _cliquable(context, '${nombre(l.poids, 1)} %', () => _reglerPoids(context, l), aide: 'Modifier le poids'),
              v == null || v.fonds ? '' : BarreScore(v.n('score'), largeur: 80),
              v?.t('moat') ?? '—',
              v?.t('criteres') ?? '—',
              nombre(v?.n('per_prospectif'), 1),
              pct(v?.n('tri_implicite')),
              Text(pct(v?.n('perf_1m'), 1, true),
                  style: TextStyle(fontSize: 14, color: couleurSigne(context, v?.n('perf_1m')))),
              IconButton(
                tooltip: 'Retirer la ligne',
                iconSize: 18,
                visualDensity: VisualDensity.compact,
                icon: const Icon(Icons.close),
                onPressed: () => etat.reglerPoids(l.ticker, null),
              ),
            ];
          }(),
      ],
      surClic: (i) {
        if (d?.valeurs[triees[i].ticker] != null) ouvrirFiche(context, triees[i].ticker);
      },
    );
  }
}

// --------------------------------------------------------------------------------------------- mon portefeuille

class PageMonPortefeuille extends StatelessWidget {
  const PageMonPortefeuille({super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        final lignes = etat.portefeuille;
        if (lignes.isEmpty) {
          return PageDefilante(titre: 'Mon portefeuille', actions: const [_BoutonImport()], [_invitationImport(context)]);
        }
        final pos = positions(lignes, d);
        final valeur = valeurTotale(pos);
        final investi = pos.fold<double>(0, (s, x) => s + (x.valeur != null ? (x.investi ?? 0) : 0));
        final valeurAvecPru = pos.fold<double>(0, (s, x) => s + (x.investi != null ? (x.valeur ?? 0) : 0));
        final pv = valeurAvecPru - investi;
        final cibles = poidsNormalises(lignes);
        final sansQuantite = pos.where((x) => x.ligne.quantite == null).length;
        final triees = [...pos]..sort((a, b) => (b.valeur ?? -1).compareTo(a.valeur ?? -1));
        return PageDefilante(
          titre: 'Mon portefeuille',
          legende: 'Titres détenus et prix de revient, saisis sur cet appareil : cliquez sur une ligne pour les '
              'modifier. Le journal des opérations, la performance pondérée par le temps et la fiscalité restent dans '
              'l\'outil du PC.',
          actions: const [_BoutonImport()],
          [
            Metriques([
              Metrique('Valeur des titres', euros(valeur)),
              Metrique('Prix de revient', investi > 0 ? euros(investi) : '—'),
              Metrique('Plus-values latentes', investi > 0 ? euros(pv) : '—',
                  delta: investi > 0 ? pct(pv / investi, 1, true) : null, deltaPositif: investi > 0 ? pv >= 0 : null),
              Metrique('Lignes', '${lignes.length}',
                  delta: sansQuantite == 0 ? null : '$sansQuantite sans quantité', deltaPositif: null),
            ]),
            if (sansQuantite > 0)
              Encadre('$sansQuantite ligne${sansQuantite > 1 ? 's n\'ont' : ' n\'a'} pas de nombre de titres : '
                  'cliquez dessus pour le saisir. Sans lui, la valeur et l\'apport du mois se calculent sur les poids.'),
            const SizedBox(height: 8),
            Tableau(
              largeurMin: 1000,
              colonnes: const [
                Colonne('Compte', largeur: 70),
                Colonne('Valeur', flex: 3),
                Colonne('Quantité', largeur: 84, droite: true),
                Colonne('PRU €', largeur: 80, droite: true),
                Colonne('Coût €', largeur: 86, droite: true),
                Colonne('Cours €', largeur: 80, droite: true),
                Colonne('Valeur €', largeur: 90, droite: true),
                Colonne('+/- latente €', largeur: 100, droite: true),
                Colonne('+/- latente', largeur: 90, droite: true),
                Colonne('Poids réel', largeur: 84, droite: true),
                Colonne('Poids cible', largeur: 86, droite: true),
              ],
              lignes: [
                for (final x in triees)
                  [
                    d?.valeurs[x.ligne.ticker]?.enveloppe ?? '—',
                    '${etat.nomLigne(x.ligne)} (${x.ligne.ticker})',
                    x.ligne.quantite == null
                        ? _cliquable(context, 'saisir', () => _position(context, x.ligne))
                        : nombre(x.ligne.quantite, x.ligne.quantite! == x.ligne.quantite!.roundToDouble() ? 0 : 3),
                    nombre(x.ligne.prixRevient, 2),
                    nombre(x.investi, 0),
                    nombre(x.coursEur, 2),
                    nombre(x.valeur, 0),
                    Text(nombre(x.plusValue, 0),
                        style: TextStyle(fontSize: 14, color: couleurSigne(context, x.plusValue))),
                    Text(pct(x.performance, 1, true),
                        style: TextStyle(fontSize: 14, color: couleurSigne(context, x.performance))),
                    valeur > 0 && x.valeur != null ? pct(x.valeur! / valeur) : '—',
                    pct(cibles[x.ligne.ticker]),
                  ],
              ],
              surClic: (i) => _position(context, triees[i].ligne),
            ),
            if (valeur > 0) ...[
              const SousTitre('Poids réels et poids cibles'),
              _PoidsReelsCibles(triees, valeur, cibles),
              const Legende('Pour rééquilibrer sans payer d\'impôt, orientez les nouveaux apports vers les lignes en '
                  'retard (rubrique « Apport du mois ») plutôt que de vendre les gagnantes, surtout sur le compte-titres.'),
            ],
            const AvertissementConseil(),
          ],
        );
      },
    );
  }
}

/// Deux barres par ligne : poids réel (bleu) et poids cible (orange), comme le graphique de l'outil du PC.
class _PoidsReelsCibles extends StatelessWidget {
  const _PoidsReelsCibles(this.positions, this.valeur, this.cibles);

  final List<Position> positions;
  final double valeur;
  final Map<String, double> cibles;

  @override
  Widget build(BuildContext context) {
    final t = Teintes.de(context);
    final lignes = [
      for (final x in positions)
        (etat.nomLigne(x.ligne), (x.valeur ?? 0) / valeur, cibles[x.ligne.ticker] ?? 0),
    ];
    final max = lignes.fold<double>(0.01, (m, l) => math.max(m, math.max(l.$2, l.$3)));
    Widget barre(double v, Color c) => Row(children: [
          Flexible(
            child: FractionallySizedBox(
              widthFactor: (v / max).clamp(0.0, 1.0),
              alignment: Alignment.centerLeft,
              child: Container(
                height: 10,
                decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(3)),
              ),
            ),
          ),
          const SizedBox(width: 6),
          SizedBox(width: 48, child: Text(pct(v, 1), style: TextStyle(fontSize: 12.5, color: t.legende))),
        ]);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 16, children: [
        for (final (nom, c) in [('Réel', t.series[0]), ('Cible', t.series[1])])
          Row(mainAxisSize: MainAxisSize.min, children: [
            Container(width: 12, height: 12, decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(2))),
            const SizedBox(width: 6),
            Text(nom, style: TextStyle(fontSize: 14, color: t.legende)),
          ]),
      ]),
      const SizedBox(height: 10),
      for (final (nom, reel, cible) in lignes)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 5),
          child: Row(children: [
            SizedBox(
              width: 200,
              child: Text(nom, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: t.legende)),
            ),
            Expanded(
              child: Column(children: [barre(reel, t.series[0]), const SizedBox(height: 3), barre(cible, t.series[1])]),
            ),
          ]),
        ),
    ]);
  }
}
