/// Tableau de bord, dans l'ordre de celui de l'outil du PC (vues/accueil.py) : mon portefeuille, profil du
/// portefeuille et courbe face à l'indice, points de vigilance, dernières actualités, lignes du portefeuille.
library;

import 'package:material_ui/material_ui.dart';

import '../actualites.dart';
import '../calculs.dart';
import '../formats.dart';
import '../graphiques.dart';
import '../interface.dart';
import '../main.dart';
import '../navigation.dart';
import '../recherche.dart';
import '../risques.dart';
import '../suivi.dart';
import '../widgets.dart';

class TableauDeBord extends StatelessWidget {
  const TableauDeBord({super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        final lignes = etat.portefeuille;
        final enfants = <Widget>[];
        if (!etat.configure) {
          enfants.add(Encadre('Accès aux données à configurer : collez votre jeton GitHub en lecture seule.',
              icone: Icons.key_outlined,
              action: bouton('Réglages', () => aller(context, Rubrique.reglages))));
        }
        if (etat.erreur != null) enfants.add(Encadre.erreur(etat.erreur!));
        if (d == null) {
          enfants.add(Encadre(etat.enCours
              ? 'Téléchargement des données de la nuit…'
              : 'Aucune donnée téléchargée pour l\'instant.'));
          return PageDefilante(titre: 'Tableau de bord', enfants);
        }
        final poids = poidsNormalises(lignes);

        // ------------------------------------------------------------ mon portefeuille (titres détenus)
        final pos = positions(lignes, d);
        final valeur = valeurTotale(pos);
        final investi = pos.fold<double>(0, (s, x) => s + (x.valeur != null ? (x.investi ?? 0) : 0));
        final valeurAvecPru = pos.fold<double>(0, (s, x) => s + (x.investi != null ? (x.valeur ?? 0) : 0));
        if (lignes.isEmpty) {
          enfants.add(Encadre(
              'Aucun portefeuille sur cet appareil : importez le fichier de votre courtier ou saisissez vos lignes.',
              action: bouton('Composition', () => aller(context, Rubrique.composition))));
        } else if (valeur > 0) {
          final perf1m = moyenne(poids, d, 'perf_1m');
          enfants.addAll([
            const SousTitre('Mon portefeuille'),
            Metriques([
              Metrique('Valeur totale', euros(valeur)),
              Metrique('Plus-values latentes', investi > 0 ? euros(valeurAvecPru - investi) : '—',
                  delta: investi > 0 ? pct(valeurAvecPru / investi - 1, 1, true) : null,
                  deltaPositif: investi > 0 ? valeurAvecPru >= investi : null),
              Metrique('Performance 1 mois', pct(perf1m, 1, true),
                  aide: 'Moyenne pondérée des variations sur un mois, en devise de cotation.',
                  couleur: couleurSigne(context, perf1m)),
              Metrique('Lignes', '${lignes.length}'),
            ]),
          ]);
        } else {
          enfants.add(Encadre('Aucun nombre de titres saisi : ce tableau de bord suit les poids cibles. Saisissez '
              'vos titres dans « Mon portefeuille » pour suivre leur valeur.',
              action: bouton('Mon portefeuille', () => aller(context, Rubrique.monPortefeuille))));
        }

        // ------------------------------------------------------------ profil du portefeuille et courbe
        if (poids.isNotEmpty) {
          final r1 = Risques(d, poids, annees: 1);
          final r3 = Risques(d, poids, annees: 3);
          final a = r1.stats, b = r1.statsIndice;
          enfants.addAll([
            const SousTitre('Profil du portefeuille'),
            Metriques([
              Metrique('TRI implicite moyen', pct(moyenne(poids, d, 'tri_implicite')),
                  aide: 'Rendement annuel attendu si la croissance prévue se réalise, au prix actuel (modèle de flux '
                      'actualisés). Moyenne sur les actions bénéficiaires : fonds et sociétés en perte n\'en ont pas.'),
              Metrique('Croissance attendue', pct(moyenne(poids, d, 'croissance_attendue')),
                  aide: 'Médiane, par ligne, du consensus (BPA, CA) et de la croissance historique, pondérée par les '
                      'poids.'),
              Metrique('PER prospectif', nombre(moyenne(poids, d, 'per_prospectif', harmonique: true), 1, 'x'),
                  aide: 'Moyenne harmonique pondérée des PER sur les bénéfices attendus.'),
              Metrique('Volatilité attendue', pct(r3.stats.volatilite),
                  aide: 'Écart-type annualisé des rendements hebdomadaires en euros sur 3 ans, corrélations '
                      'comprises.'),
            ]),
            Padding(
              padding: const EdgeInsets.only(top: 12, bottom: 4),
              child: Text.rich(TextSpan(children: [
                const TextSpan(
                    text: 'Sur un an glissant (simulation, poids actuels)', style: TextStyle(fontWeight: FontWeight.w600)),
                TextSpan(text: ' : portefeuille ${pct(a.rendementTotal, 1, true)}, indice ${d.tickerReference} '
                    '${pct(b.rendementTotal, 1, true)}'),
              ])),
            ),
            Courbes({'Portefeuille': a.courbe, 'Indice ${d.tickerReference}': b.courbe}, hauteur: 280, decimales: 1),
          ]);
        }

        // ------------------------------------------------------------ « Pour moi »
        final pourMoi = opportunites(d, etat.profil, etat.reglagesValorisation);
        final auBonPrix = pourMoi.where((o) => o.verdict == Verdict.bonPrix).length;
        enfants.add(Padding(
          padding: const EdgeInsets.only(top: 16),
          child: Encadre(
            auBonPrix == 0
                ? 'Aucune valeur sous votre prix d\'achat aujourd\'hui, parmi les ${pourMoi.length} qui conviennent à '
                    'votre profil.'
                : '$auBonPrix valeur${auBonPrix > 1 ? 's' : ''} au bon prix pour vous, parmi les ${pourMoi.length} qui '
                    'conviennent à votre profil (prix juste à ${pct(etat.reglagesValorisation.rendementExige, 1)} par '
                    'an, marge de sécurité ${pct(etat.profil.margeSecurite, 0)}).',
            icone: Icons.travel_explore,
            nature: auBonPrix == 0 ? NatureEncadre.info : NatureEncadre.succes,
            action: bouton('Pour moi', () => aller(context, Rubrique.pourMoi)),
          ),
        ));

        // ------------------------------------------------------------ points de vigilance
        final noms = {for (final l in lignes) l.ticker: etat.nomLigne(l)};
        final alertes = <(String, String?, String)>[
          for (final (t, type, message) in vigilance(poids, d)) (type, t, message),
          for (final g in gardeFous(poids, d, noms: noms, profil: etat.profil)) ('Concentration', null, g),
          for (final a in signaux(etat).where((a) => a.type == 'À surveiller'))
            (a.titre, a.ticker, a.detail.isEmpty ? a.source : a.detail),
        ];
        enfants.add(const SousTitre('Points de vigilance'));
        if (alertes.isEmpty) {
          enfants.add(const Encadre.succes('Aucune alerte : toutes les lignes passent les filtres, sans mouvement '
              'extrême.'));
        } else {
          enfants.add(Tableau(
            largeurMin: 700,
            hauteurLigne: 44,
            colonnes: const [
              Colonne('Type', largeur: 190),
              Colonne('Valeur', flex: 2),
              Colonne('Détail', flex: 5),
            ],
            lignes: [
              for (final (type, t, detail) in alertes)
                [
                  type,
                  t == null ? 'Portefeuille' : (d.valeurs[t]?.nom ?? noms[t] ?? t),
                  Tooltip(
                    message: detail,
                    child: Text(detail, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14)),
                  ),
                ],
            ],
            surClic: (i) {
              final t = alertes[i].$2;
              if (t != null && d.valeurs[t] != null) ouvrirFiche(context, t);
            },
          ));
        }

        // ------------------------------------------------------------ dernières actualités
        final dernieres = signaux(etat).where((a) => a.type != 'À surveiller').toList()
          ..sort((a, b) => b.date.compareTo(a.date));
        if (dernieres.isNotEmpty) {
          enfants.add(const SousTitre('Dernières actualités'));
          for (final a in dernieres.take(5)) {
            enfants.add(Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: InkWell(
                onTap: a.ticker == null ? null : () => ouvrirFiche(context, a.ticker!),
                child: Text.rich(TextSpan(children: [
                  TextSpan(
                      text: a.ticker == null ? '' : '${d.valeurs[a.ticker]?.nom ?? a.ticker} ',
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  TextSpan(text: '· ${dateFr(a.date.toIso8601String())} · ${a.source} · ${a.titre}'),
                ])),
              ),
            ));
          }
          enfants.add(Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              icon: const Icon(Icons.feed_outlined, size: 18),
              label: const Text('Toutes les actualités'),
              onPressed: () => aller(context, Rubrique.actualites),
            ),
          ));
        }

        // ------------------------------------------------------------ lignes du portefeuille
        if (lignes.isNotEmpty) {
          final triees = [...lignes]..sort((a, b) => b.poids.compareTo(a.poids));
          enfants.addAll([
            const SousTitre('Lignes du portefeuille'),
            Tableau(
              largeurMin: 860,
              colonnes: const [
                Colonne('Valeur', flex: 3),
                Colonne('Compte', largeur: 70),
                Colonne('Poids', largeur: 72, droite: true),
                Colonne('Score', largeur: 150,
                    aide: 'Moyenne pondérée des analyses, chacune sur 100 : piliers, valorisation, quatre regards, '
                        'Piotroski, Altman, Beneish.'),
                Colonne('1 mois', largeur: 74, droite: true),
                Colonne('12 mois', largeur: 78, droite: true),
                Colonne('TRI implicite', largeur: 96, droite: true),
                Colonne('PER prosp.', largeur: 82, droite: true),
              ],
              lignes: [
                for (final l in triees)
                  () {
                    final v = d.valeurs[l.ticker];
                    return <Object?>[
                      etat.nomLigne(l),
                      v?.enveloppe ?? '—',
                      pct(poids[l.ticker]),
                      v == null || v.fonds ? '' : BarreScore(v.n('score'), largeur: 80),
                      Text(pct(v?.n('perf_1m'), 1, true),
                          style: TextStyle(fontSize: 14, color: couleurSigne(context, v?.n('perf_1m')))),
                      Text(pct(v?.n('perf_12m'), 1, true),
                          style: TextStyle(fontSize: 14, color: couleurSigne(context, v?.n('perf_12m')))),
                      pct(v?.n('tri_implicite')),
                      nombre(v?.n('per_prospectif'), 1),
                    ];
                  }(),
              ],
              surClic: (i) {
                if (d.valeurs[triees[i].ticker] != null) ouvrirFiche(context, triees[i].ticker);
              },
            ),
          ]);
        }
        enfants.add(const AvertissementConseil());
        return PageDefilante(
          titre: 'Tableau de bord',
          legende: 'Cours au ${dateFr(d.donneesAu)} · univers de ${d.valeurs.length} valeurs dont ${d.nbEligibles} '
              'passent les filtres de qualité${lignes.isEmpty ? '' : ' · portefeuille de ${lignes.length} lignes'}',
          enfants,
        );
      },
    );
  }
}
