import 'package:material_ui/material_ui.dart';

import '../donnees.dart';
import '../formats.dart';
import '../graphiques.dart';
import '../interface.dart';
import '../main.dart';
import '../navigation.dart';
import '../recherche.dart';
import '../stockage.dart';
import '../suivi.dart';
import '../valorisation.dart';
import '../widgets.dart';
import 'methodes.dart';
import 'opportunites.dart';

const _periodes = {'1 an': 52, '3 ans': 156, '5 ans': null};
const _definitions = {
  'P/FCF': 'Capitalisation / flux de trésorerie disponible',
  'P/FCF hors SBC': 'Capitalisation / (flux de trésorerie disponible − rémunérations en actions)',
  'PER': 'Capitalisation / résultat net',
  'P/CA': 'Capitalisation / chiffre d\'affaires',
};

class Fiche extends StatefulWidget {
  const Fiche({required this.ticker, super.key});

  final String ticker;

  @override
  State<Fiche> createState() => _FicheState();
}

class _FicheState extends State<Fiche> {
  String _periode = '3 ans';
  String _periodeHistorique = 'Tout';
  String? _ratio;
  final _cibles = <String, double>{};

  // Hypothèses de valorisation : null tant que l'utilisateur n'y a pas touché (valeurs proposées).
  double? _rendement, _croissance, _terminale, _roic;
  Map<String, Hypotheses>? _scenarios;
  late final _these = TextEditingController(text: etat.theses[widget.ticker] ?? '');

  @override
  void dispose() {
    _these.dispose();
    super.dispose();
  }

  Future<void> _reglerPoids(BuildContext context) async {
    final poids = await demanderPoids(context, actuel: etat.poids(widget.ticker));
    if (poids != null) await etat.reglerPoids(widget.ticker, poids);
  }

  void _message(String texte) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(texte)));

  Future<void> _viser(Valeur v, double prix, String objectif) async {
    await etat.fixerPrixVise(v, prix, objectif: objectif);
    _message('Prix visé enregistré dans la watchlist : ${nombre(prix, 2)} ${v.devise}.');
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) {
        final d = etat.donnees;
        final v = d?.valeurs[widget.ticker];
        if (d == null || v == null) {
          return PageClimax(avantTitre: const SelecteurValeur(null), titre: widget.ticker, enfants: const [
            Encadre('Valeur absente des données de la nuit.'),
          ]);
        }
        final f = etat.complements?.fiche(v.ticker);
        final poids = etat.poids(v.ticker);
        final onglets = <(String, WidgetBuilder)>[
          ('Résumé', (context) => _resume(context, d, v)),
          if (!v.fonds) ...[
            ('Prix juste', (context) => _prixJuste(context, v, f)),
            ('Activité', (context) => _activite(context, v, f)),
            ('Historique', (context) => _historique(context, v, f)),
            ('Valorisation', (context) => _valorisation(context, v)),
          ],
          ('Notes', (context) => _notes(context, d, v)),
        ];
        final suivie = etat.suivie(v.ticker);
        return PageClimax(
          avantTitre: SelecteurValeur(v),
          titre: v.nom,
          actions: [
            bouton(suivie ? 'Retirer de la watchlist' : 'Ajouter à la watchlist', () => etat.basculerWatchlist(v),
                icone: suivie ? Icons.star : Icons.star_border),
            bouton(poids == null ? 'Ajouter au portefeuille' : 'Poids : ${nombre(poids, 1)} %',
                () => _reglerPoids(context), icone: poids == null ? Icons.add_chart : Icons.pie_chart_outline),
          ],
          legende: [
            [v.ticker, v.secteur, v.t('industrie'), v.pays, v.enveloppe].whereType<String>().where((s) => s.isNotEmpty)
                .join(' · '),
            if (poids != null) 'En portefeuille : cible ${nombre(poids, 1)} %',
            'cours du ${dateFr(d.donneesAu)}',
          ].join(' · '),
          enfants: [
            if (v.profil != null)
              Padding(
                padding: const EdgeInsets.only(top: 4, bottom: 4),
                child: Text(v.profil!, style: const TextStyle(fontStyle: FontStyle.italic, fontSize: 16)),
              ),
            if (v.fonds)
              const Encadre('Fonds : ni score ni critères, seulement le cours et le risque.')
            else if (v.eligible)
              Encadre.succes('Éligible${v.rang == null ? '' : ', rang ${v.rang} sur ${d.nbEligibles}'}',
                  icone: Icons.verified_outlined)
            else
              Encadre.erreur('Exclue par les filtres de qualité${v.motifsExclusion == null ? '' : ' : ${v.motifsExclusion}'}'),
            if (v.alertes != null) Encadre.avertissement('Alertes : ${v.alertes}'),
            Onglets(onglets, segments: true),
          ],
        );
      },
    );
  }

  // ------------------------------------------------------------------------------------------- résumé
  Widget _resume(BuildContext context, Donnees d, Valeur v) {
    final texte = Theme.of(context).textTheme;
    final cours = d.cours(v.ticker);
    final rangs = d.rangs(v.ticker);
    final dev = v.devise;
    final p1 = v.n('perf_1m'), p12 = v.n('perf_12m');
    return PageDefilante([
      Metriques([
        Metrique('Cours', '${nombre(v.n('cours'), 2)} $dev'),
        Metrique('1 mois', pct(p1, 1, true), couleur: couleurSigne(context, p1)),
        Metrique('12 mois', pct(p12, 1, true), couleur: couleurSigne(context, p12)),
        if (!v.fonds)
          Metrique('Score composite', '${nombre(v.n('score'), 0)} / 100',
              aide: 'Moyenne pondérée des analyses, chacune sur 100 : piliers, valorisation, quatre regards, '
                  'Piotroski, Altman, Beneish.')
        else
          Metrique('Volatilité', pct(v.n('volatilite'), 0)),
      ]),
      if (!v.fonds) _pourMoi(context, d, v),
      if (cours != null) ...[
        const SizedBox(height: 12),
        SegmentedButton<String>(
          segments: [for (final p in _periodes.keys) ButtonSegment(value: p, label: Text(p))],
          selected: {_periode},
          onSelectionChanged: (s) => setState(() => _periode = s.first),
        ),
        const SizedBox(height: 8),
        Courbe(cours.points(_periodes[_periode])),
        Text('Cours hebdomadaires en $dev, dividendes réinvestis.', style: texte.bodySmall),
      ],
      if (!v.fonds) ...[
        Section('Score composite : ${nombre(v.n('score'), 0)} / 100', [
          Indicateur('Piliers', nombre(v.n('score_piliers'), 0), aide: 'Qualité, croissance, valorisation, momentum.'),
          Indicateur('Qualité', nombre(v.n('qualite'), 0), aide: 'Rang centile dans l\'univers (100 : meilleur).'),
          Indicateur('Croissance', nombre(v.n('croissance'), 0)),
          Indicateur('Valorisation', nombre(v.n('valorisation'), 0)),
          Indicateur('Momentum', nombre(v.n('momentum'), 0)),
          Indicateur('Quatre regards', nombre(v.n('regards_total'), 0, '/ 20'),
              aide: 'Buffett, Munger, Fisher, Smith : somme des notes sur 5.'),
        ]),
        if (v.t('regards_correction') != null)
          Text('Correction manuelle des regards : ${v.t('regards_correction')}.', style: texte.bodySmall),
        NotesDesMethodes(v),
        Colonnes(minLargeur: 300, [
        Section('Qualité', [
          Indicateur('ROIC moyen', pct(v.n('roic_moyen'))),
          Indicateur('ROE moyen', pct(v.n('roe_moyen'))),
          Indicateur('Marge brute', pct(v.n('marge_brute'))),
          Indicateur('Marge opérationnelle', pct(v.n('marge_operationnelle'))),
          Indicateur('Conversion en cash', pct(v.n('conversion_fcf'), 0)),
          Indicateur('Dette nette / EBITDA', nombre(v.n('dette_nette_ebitda'), 1, 'x')),
          Indicateur('Actions, par an', pct(v.n('evolution_actions'), 1, true),
              aide: 'Négatif : rachats d\'actions ; positif : dilution.'),
          Indicateur('Moat estimé', v.t('moat') ?? vide,
              aide: 'Traces d\'un avantage concurrentiel dans les comptes : rentabilité élevée et tenue, marges '
                  'fortes et stables. Estimation chiffrée.'),
        ]),
        Section('Croissance', [
          Indicateur('Chiffre d\'affaires, par an', pct(v.n('croiss_ca'))),
          Indicateur('Bénéfice par action, par an', pct(v.n('croiss_bpa'))),
          Indicateur('Consensus BPA', pct(v.n('croiss_bpa_estimee'))),
          Indicateur('Consensus CA', pct(v.n('croiss_ca_estimee'))),
          Indicateur('Croissance retenue', pct(v.n('croissance_attendue')),
              aide: 'Celle que retiennent le prix juste et le TRI implicite.'),
        ]),
        ]),
        Colonnes(minLargeur: 300, [
        Section('Valorisation', [
          Indicateur('PER (12 mois)', nombre(v.n('per'), 1)),
          Indicateur('PER prospectif', nombre(v.n('per_prospectif'), 1)),
          Indicateur('PER habituel', nombre(v.n('per_historique'), 1),
              aide: 'PER médian des dernières clôtures annuelles. Écart : ${pct(v.n('ecart_per_historique'), 0, true)}.'),
          Indicateur('P/FCF', nombre(v.n('p_fcf'), 1)),
          Indicateur('P/FCF habituel', nombre(v.n('p_fcf_historique'), 1),
              aide: 'Écart : ${pct(v.n('ecart_p_fcf_historique'), 0, true)}.'),
          Indicateur('P/FCF hors SBC', nombre(v.n('p_fcf_net'), 1),
              aide: 'Flux de trésorerie diminué des rémunérations en actions, un vrai coût payé en dilution.'),
          Indicateur('Rendement du FCF', pct(v.n('rendement_fcf'))),
          Indicateur('EBIT / valeur d\'entreprise', pct(v.n('rendement_benefices'))),
          Indicateur('Dividende', pct(v.n('rendement_dividende'))),
          Indicateur('Croissance implicite', pct(v.n('croissance_implicite')),
              aide: 'Croissance que le prix actuel suppose (DCF inversé).'),
          Indicateur('TRI implicite', pct(v.n('tri_implicite')),
              aide: 'Rendement annuel attendu si la croissance prévue se réalise, au prix actuel.'),
        ]),
        Section('Cours et risque', [
          Indicateur('Momentum 12-1 mois', pct(v.n('mom_12_1'), 1, true)),
          Indicateur('Écart à la moyenne 200 jours', pct(v.n('ecart_mm200'), 1, true)),
          Indicateur('Volatilité', pct(v.n('volatilite'), 0)),
          Indicateur('Perte max 3 ans', pct(v.n('drawdown_max_3a'), 0)),
          Indicateur('Objectif des analystes', pct(v.n('objectif_analystes'), 1, true)),
          Indicateur('Capitalisation', milliards(v.n('capitalisation_eur'))),
        ]),
        ]),
        Section('Santé financière', [
          Indicateur('Piotroski', nombre(v.n('piotroski'), 0, '/ 9'),
              aide: 'Neuf critères sur le dernier exercice. 0 à 2 : faible ; 8 ou 9 : forte.'),
          Indicateur('Altman', nombre(v.n('altman_z'), 1), aide: 'Sous 1,8 : zone fragile ; au-dessus de 3 : sûre.'),
          Indicateur('Beneish', nombre(v.n('beneish_m'), 2), aide: 'Au-dessus de -1,78 : comptes à examiner.'),
        ]),
        if (v.financiere)
          Text('Ces trois signaux ne sont pas calculés pour les banques, assureurs et holdings.', style: texte.bodySmall),
      ] else
        Section('Risque', [
          Indicateur('Volatilité', pct(v.n('volatilite'), 0)),
          Indicateur('Perte max 3 ans', pct(v.n('drawdown_max_3a'), 0)),
          Indicateur('Performance 5 ans', pct(v.n('perf_annu_5a'), 1, true)),
        ]),
      if (rangs.length >= 2) ...[
        Padding(padding: const EdgeInsets.only(top: 16), child: Text('Rang dans le screener', style: texte.titleMedium)),
        Courbe([for (final (date, r) in rangs) (date, r.toDouble())], decimales: 0, hauteur: 160),
      ],
      const AvertissementConseil(),
    ]);
  }

  /// Le jugement personnalisé : la valeur convient-elle au profil, et à quel prix ?
  Widget _pourMoi(BuildContext context, Donnees d, Valeur v) {
    final p = etat.profil;
    final m = d.methode(p.methode);
    final note = d.notes(m)[v.ticker];
    final raison = raisonEcartee(v, p);
    final o = evaluer(v, note ?? 0, p, etat.reglagesValorisation);
    return Carte(
      'Pour moi',
      sousTitre: 'Selon votre profil : méthode ${m.libelle}, rendement exigé '
          '${pct(etat.reglagesValorisation.rendementExige, 1)}, marge de sécurité ${pct(p.margeSecurite, 0)}.',
      action: PastilleVerdict(o.verdict),
      enfant: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(raison == null ? Icons.check_circle : Icons.info_outline,
              size: 18, color: raison == null ? vert : Theme.of(context).colorScheme.outline),
          const SizedBox(width: 6),
          Expanded(
            child: Text(raison == null
                ? 'Convient à vos exigences de qualité · note ${nombre(note, 0)} / 100 selon ${m.libelle}'
                : 'Hors de votre recherche : $raison'),
          ),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 12, runSpacing: 8, children: [
          Chiffre('Prix juste', o.prixJuste == null ? vide : '${nombre(o.prixJuste, 2)} ${v.devise}',
              detail: o.ecart == null ? null : 'cours ${pct(o.ecart, 0, true)}'),
          Chiffre('Votre prix d\'achat', o.prixAchat == null ? vide : '${nombre(o.prixAchat, 2)} ${v.devise}'),
          Chiffre('Rendement implicite', pct(o.tri, 1), detail: 'au cours actuel'),
        ]),
        if (o.prixAchat != null)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              icon: const Icon(Icons.star_outline),
              label: Text(etat.suivi(v.ticker)?.prixVise == null ? 'Viser ce prix d\'achat' : 'Mettre à jour mon prix visé'),
              onPressed: () => _viser(v, o.prixAchat!,
                  'prix juste à ${pct(etat.reglagesValorisation.rendementExige, 1)}, marge ${pct(p.margeSecurite, 0)}'),
            ),
          ),
      ]),
    );
  }

  // --------------------------------------------------------------------------------------- prix juste
  Widget _prixJuste(BuildContext context, Valeur v, Map<String, dynamic>? f) {
    final texte = Theme.of(context).textTheme;
    if (v.holding) {
      return const Vide('Holding : son prix se juge sur la décote par rapport à la valeur de ses participations '
          '(actif net), que les données ne fournissent pas.');
    }
    // Repères des multiples : ceux du fichier des fiches, à défaut ceux du screener.
    final reperes = <String, Map<String, dynamic>>{
      for (final e in ((f?['r'] as Map<String, dynamic>?) ?? const <String, dynamic>{}).entries)
        e.key: e.value as Map<String, dynamic>,
    };
    if (reperes.isEmpty) {
      if (v.n('per') != null) reperes['PER'] = {'actuel': v.n('per'), 'tout': v.n('per_historique')};
      if (!v.financiere && v.n('p_fcf') != null) {
        reperes['P/FCF'] = {'actuel': v.n('p_fcf'), 'tout': v.n('p_fcf_historique')};
      }
    }
    if (reperes.isEmpty) return const Vide('Multiples indisponibles pour cette valeur (pertes ou données absentes).');
    final ratio = reperes.containsKey(_ratio) ? _ratio! : reperes.keys.first;
    final r = reperes[ratio]!;
    double? n(String cle) => nombreOuNul(r[cle]);
    final actuel = n('actuel');
    final defaut = n('m5') ?? n('m10') ?? n('tout') ?? actuel ?? 15;
    final cible = _cibles[ratio] ?? (defaut * 10).round() / 10;
    final cours = v.n('cours');
    final prix = prixAuMultiple(cours, actuel, cible);
    final ecart = prix == null || cours == null ? null : cours / prix - 1;
    final serie = [
      if (r['debut'] != null)
        for (final (i, x) in (r['v'] as List).indexed)
          if (nombreOuNul(x) case final y?)
            (DateTime.parse(r['debut'] as String).add(Duration(days: (91.31 * i).round())), y),
    ];
    final valo = Valorisation(v, etat.reglagesValorisation);
    return PageDefilante([
      Text('Quel est le prix juste pour ${v.nom} ?', style: texte.titleLarge),
      const SizedBox(height: 4),
      const Text('Deux façons de le chercher : le multiple que vous jugez raisonnable, d\'après l\'histoire de la '
          'valeur, ou le rendement que vous exigez (onglet Valorisation).'),
      Carte(
        'Au multiple que je juge raisonnable',
        sousTitre: _definitions[ratio],
        enfant: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 6, children: [
            for (final k in reperes.keys)
              ChoiceChip(label: Text(k), selected: k == ratio, onSelected: (_) => setState(() => _ratio = k)),
          ]),
          const SizedBox(height: 8),
          Curseur('Mon $ratio cible', cible.clamp(1.0, _maxCible(actuel, defaut)), 1, _maxCible(actuel, defaut),
              ratio == 'P/CA' ? 0.1 : 0.5, nombre(cible, 1), (x) => setState(() => _cibles[ratio] = x)),
          Wrap(spacing: 12, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.end, children: [
            Chiffre('Prix cible', prix == null ? vide : '${nombre(prix, 2)} ${v.devise}',
                detail: ecart == null ? null : 'cours ${pct(ecart, 0, true)}',
                couleur: ecart == null ? null : couleurSigne(context, -ecart)),
            Chiffre('Cours', '${nombre(cours, 2)} ${v.devise}', detail: '$ratio actuel ${nombre(actuel, 1)}'),
            FilledButton.icon(
              icon: const Icon(Icons.star),
              label: Text(etat.suivi(v.ticker)?.prixVise == null ? 'Viser ce prix' : 'Mettre à jour'),
              onPressed: prix == null ? null : () => _viser(v, prix, '$ratio ${nombre(cible, 1)}'),
            ),
          ]),
          if (etat.suivi(v.ticker)?.prixVise != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('Prix visé actuel : ${nombre(etat.suivi(v.ticker)!.prixVise, 2)} ${v.devise} '
                  '(${etat.suivi(v.ticker)!.objectif ?? 'objectif non précisé'})', style: texte.bodySmall),
            ),
          const SizedBox(height: 8),
          Text('Repères du $ratio : actuel ${nombre(actuel, 1)} · médiane sur 5 ans ${nombre(n('m5'), 1)} · sur 10 ans '
              '${nombre(n('m10'), 1)} · médiane${r['depuis'] == null ? '' : ' depuis ${r['depuis']}'} '
              '${nombre(n('tout'), 1)} · minimum ${nombre(n('min'), 1)}. Le prix cible suppose des résultats '
              'inchangés. Un multiple tombé sous sa médiane peut traduire des perspectives dégradées plutôt '
              'qu\'une aubaine.', style: texte.bodySmall),
        ]),
      ),
      if (serie.length >= 2)
        Carte('$ratio dans le temps',
            sousTitre: 'Un point par trimestre ; les trous correspondent aux exercices à résultat négatif.',
            enfant: Courbes({ratio: serie}, decimales: 1)),
      Carte(
        'Au rendement que j\'exige',
        sousTitre: 'Modèle des « value drivers », avec la croissance attendue de ${pct(valo.croissanceRetenue, 1)}.',
        enfant: valo.disponible
            ? Wrap(spacing: 12, runSpacing: 8, children: [
                for (final rdt in {0.08, etat.reglagesValorisation.rendementExige, 0.10, 0.12}.toList()..sort())
                  Chiffre('À ${pct(rdt, 1)} par an',
                      valo.prixJuste(rendement: rdt) == null ? vide : '${nombre(valo.prixJuste(rendement: rdt), 2)} ${v.devise}',
                      detail: rdt == etat.reglagesValorisation.rendementExige ? 'votre exigence' : null),
              ])
            : const Text('Modèle non applicable (holding, pertes ou données manquantes).'),
      ),
      const AvertissementConseil(),
    ]);
  }

  double _maxCible(double? actuel, double defaut) {
    final haut = [actuel ?? 0, defaut, 20.0].reduce((a, b) => a > b ? a : b) * 1.6;
    return (haut / 5).ceil() * 5.0;
  }

  // ----------------------------------------------------------------------------------------- activité
  Widget _activite(BuildContext context, Valeur v, Map<String, dynamic>? f) {
    final texte = Theme.of(context).textTheme;
    final dir = f?['d'] as Map<String, dynamic>?;
    final vent = f?['v'] as Map<String, dynamic>?;
    final detenteurs = etat.complements?.detenteurs(v.ticker) ?? const <String>[];
    Map<String, double> parts(Object? brut) {
      final m = (brut as Map<String, dynamic>?) ?? const <String, dynamic>{};
      final total = m.values.fold<double>(0, (s, x) => s + ((x as num?)?.toDouble() ?? 0));
      final tri = m.entries.toList()..sort((a, b) => ((b.value as num?) ?? 0).compareTo((a.value as num?) ?? 0));
      return {for (final e in tri) if (total > 0) e.key: ((e.value as num?)?.toDouble() ?? 0) / total};
    }

    return PageDefilante([
      if (etat.complements == null)
        const Card(child: ListTile(leading: Icon(Icons.downloading), title: Text('Détail des fiches en cours de lecture…'))),
      Carte(
        'Achats et ventes des dirigeants',
        sousTitre: 'Formulaires 4 déposés à la SEC, 12 derniers mois : achats (P) et ventes (S) en bourse.',
        enfant: !v.americaine
            ? const Text('Disponible pour les sociétés américaines. En Europe, les déclarations des dirigeants ne '
                'sont pas réunies dans une source unique.')
            : dir == null
                ? const Text('Pas encore lues pour cette valeur : le flux de nuit lit les déclarations des valeurs '
                    'éligibles peu à peu, une fois l\'adresse de contact SEC enregistrée dans GitHub.')
                : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Wrap(spacing: 12, runSpacing: 8, children: [
                      Chiffre('Signal', dir['signal'] as String? ?? vide, largeur: 220),
                      Chiffre('Achats', '${dir['achats']}',
                          detail: '${dir['acheteurs']} dirigeants · ${montantCourt(nombreOuNul(dir['montant_achats']), 'USD')}'),
                      Chiffre('Ventes', '${dir['ventes']}',
                          detail: '${montantCourt(nombreOuNul(dir['montant_ventes']), 'USD')} · '
                              '${pct(nombreOuNul(dir['part_ventes_programmees']), 0)} programmées'),
                    ]),
                    const SizedBox(height: 6),
                    for (final t in (dir['transactions'] as List? ?? const []))
                      ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        leading: Icon(t['code'] == 'P' ? Icons.add_circle : Icons.remove_circle_outline,
                            color: t['code'] == 'P' ? vert : Theme.of(context).colorScheme.outline),
                        title: Text('${t['nom']} · ${t['fonction'] ?? ''}', maxLines: 1, overflow: TextOverflow.ellipsis),
                        subtitle: Text('${dateFr(t['date'] as String?)} · ${t['code'] == 'P' ? 'achat' : 'vente'} de '
                            '${nombre(t['actions'], 0)} actions à ${nombre(t['prix'], 2)} USD'
                            '${t['plan'] == true ? ' · vente programmée' : ''}'),
                        trailing: Text(montantCourt(nombreOuNul(t['montant']), 'USD')),
                      ),
                    Text('On vend pour mille raisons, on n\'achète que pour une : un achat avec son propre argent '
                        'est le signal le plus parlant.', style: texte.bodySmall),
                  ]),
      ),
      Carte(
        'D\'où vient le chiffre d\'affaires',
        sousTitre: vent == null ? null : 'Rapport ${vent['formulaire'] ?? '10-K'} de l\'exercice clos le '
            '${dateFr(vent['exercice'] as String?)}.',
        enfant: !v.americaine
            ? const Text('Répartition disponible pour les sociétés américaines : elle est lue dans leur rapport annuel '
                'déposé à la SEC.')
            : vent == null
                ? const Text('Pas encore lue pour cette valeur (rapport sans étiquettes, ou lecture de nuit à venir).')
                : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    if (parts(vent['activites']).isNotEmpty) ...[
                      Text('Par activité', style: texte.titleSmall),
                      BarresParts(parts(vent['activites']), largeurLibelle: 190),
                    ],
                    if (parts(vent['geographie']).isNotEmpty) ...[
                      const SizedBox(height: 10),
                      Text('Par géographie', style: texte.titleSmall),
                      BarresParts(parts(vent['geographie']), largeurLibelle: 190),
                    ],
                  ]),
      ),
      Carte(
        'Grands investisseurs',
        sousTitre: 'Investisseurs suivis qui détiennent le titre à leur dernier trimestre déclaré (13F).',
        enfant: detenteurs.isEmpty
            ? const Text('Aucun des investisseurs suivis ne le détient, ou les déclarations ne sont pas encore publiées.')
            : Wrap(spacing: 6, runSpacing: 6, children: [for (final nom in detenteurs) Chip(label: Text(nom))]),
      ),
      if (f?['desc'] != null)
        Carte('Description de l\'activité',
            sousTitre: 'Yahoo Finance, en anglais.', enfant: Text(f!['desc'] as String)),
    ]);
  }

  // --------------------------------------------------------------------------------------- historique
  Widget _historique(BuildContext context, Valeur v, Map<String, dynamic>? f) {
    final h = f?['h'] as Map<String, dynamic>?;
    if (h == null) {
      return Vide(etat.complements == null
          ? 'Historique financier en cours de lecture, ou pas encore téléchargé : actualisez les données.'
          : 'États financiers indisponibles pour cette valeur.');
    }
    final tous = [for (final a in h['an'] as List) a as String];
    final clos = tous.where((a) => a != '12 mois').length;
    final n = {'5 ans': 5, '10 ans': 10}[_periodeHistorique];
    final debut = n == null ? 0 : (clos - n).clamp(0, clos);
    final ans = tous.sublist(debut);
    List<double?> col(String c) => [for (final x in (h[c] as List? ?? const []).skip(debut)) nombreOuNul(x)];
    // Croissance annuelle sur n exercices clos (sans les 12 mois), entre deux valeurs positives.
    double? croissance(String c, int annees) {
      final s = [for (final x in (h[c] as List? ?? const []).take(clos)) nombreOuNul(x)];
      if (s.length <= annees) return null;
      final fin = s.last, depart = s[s.length - 1 - annees];
      if (fin == null || depart == null || fin <= 0 || depart <= 0) return null;
      return _racine(fin / depart, annees) - 1;
    }

    Widget carte(String titre, Widget graphique, {String? sousTitre, String? croissanceDe}) => Carte(
          titre,
          sousTitre: sousTitre,
          action: croissanceDe == null
              ? null
              : Text('5 ans ${pct(croissance(croissanceDe, 5), 1, true)} · 10 ans '
                  '${pct(croissance(croissanceDe, 10), 1, true)} par an', style: Theme.of(context).textTheme.labelSmall),
          enfant: graphique,
        );
    Widget ligne(String c) => BarresAnnuelles(ans, {'': [for (final x in col(c)) x == null ? null : x * 100]}, montants: false);
    final distribution = () {
      final div = col('dividende_action').lastOrNull, actions = col('actions').lastOrNull, res = col('resultat_net').lastOrNull;
      return div == null || actions == null || res == null || res <= 0 ? null : div * actions / res;
    }();
    return PageDefilante([
      SegmentedButton<String>(
        segments: const [
          ButtonSegment(value: '5 ans', label: Text('5 ans')),
          ButtonSegment(value: '10 ans', label: Text('10 ans')),
          ButtonSegment(value: 'Tout', label: Text('Tout')),
        ],
        selected: {_periodeHistorique},
        onSelectionChanged: (s) => setState(() => _periodeHistorique = s.first),
      ),
      const SizedBox(height: 6),
      Text('Montants en ${v.t('devise_comptes') ?? v.devise}. Exercices clos, puis les 12 derniers mois. '
          '${f?['src'] == 'prolonge' ? 'Comptes Yahoo prolongés par les comptes officiels (SEC ou rapports ESEF).' : 'Comptes Yahoo : quatre exercices au plus.'}',
          style: Theme.of(context).textTheme.bodySmall),
      carte('Chiffre d\'affaires', BarresAnnuelles(ans, {'Chiffre d\'affaires': col('chiffre_affaires')}),
          croissanceDe: 'chiffre_affaires'),
      carte('Free cash flow et SBC', BarresAnnuelles(ans, {'Free cash flow': col('fcf'), 'SBC': col('sbc')}),
          sousTitre: 'SBC : rémunérations en actions.', croissanceDe: 'fcf'),
      carte('Free cash flow par action', BarresAnnuelles(ans, {'FCF par action': col('fcf_action')}, montants: false),
          croissanceDe: 'fcf_action'),
      carte('ROCE, en %', ligne('roce'), sousTitre: 'Résultat opérationnel / capitaux employés.'),
      carte('Marge brute, en %', ligne('marge_brute')),
      carte('Marge du free cash flow, en %', ligne('marge_fcf')),
      carte('Actions en circulation, diluées', BarresAnnuelles(ans, {'Actions': col('actions')})),
      carte('Dividendes par action',
          BarresAnnuelles(ans, {'Dividende par action': col('dividende_action')}, montants: false),
          sousTitre: 'Rendement : ${pct(v.n('rendement_dividende'), 2)} · taux de distribution : ${pct(distribution, 0)}.'),
      carte('Trésorerie et dette', BarresAnnuelles(ans, {'Trésorerie': col('cash'), 'Dette': col('dette')}),
          sousTitre: 'Dette : loyers capitalisés compris.'),
      if (v.t('verif_sec') != null)
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text('Recoupement avec les comptes déposés à la SEC : ${v.t('verif_sec')!.toLowerCase()}.',
              style: Theme.of(context).textTheme.bodySmall),
        ),
    ]);
  }

  double _racine(double x, int n) {
    // x^(1/n) par la méthode de Newton (évite d'importer dart:math pour une seule puissance).
    var r = x > 1 ? 1 + (x - 1) / n : x;
    for (var i = 0; i < 40; i++) {
      var p = 1.0;
      for (var k = 0; k < n - 1; k++) {
        p *= r;
      }
      r = ((n - 1) * r + x / p) / n;
    }
    return r;
  }

  // ------------------------------------------------------------------------------------- valorisation
  Widget _valorisation(BuildContext context, Valeur v) {
    final texte = Theme.of(context).textTheme;
    final reglages = etat.reglagesValorisation;
    final valo = Valorisation(v, reglages);
    final rr = _rendement ?? reglages.rendementExige;
    final g = _croissance ?? ((valo.croissanceRetenue * 200).round() / 200).clamp(-0.05, 0.40);
    final gt = _terminale ?? reglages.croissanceTerminale;
    final roic = _roic ?? valo.roicRetenu;
    final ecart = valo.valeurSurCours(croissance: g, rendement: rr, roic: roic, terminale: gt);
    final base = baseScenarios(v);
    final enregistres = etat.scenarios[v.ticker] as Map<String, dynamic>?;
    final scenarios = _scenarios ??= enregistres == null
        ? hypothesesInitiales(v)
        : {
            for (final e in (enregistres['hypotheses'] as Map<String, dynamic>).entries)
              e.key: Hypotheses.depuisJson(e.value as Map<String, dynamic>),
          };
    Future<void> modifier(String titre, double actuel, String suffixe, void Function(double) regler) async {
      final x = await demanderNombre(context, titre, actuel: actuel, suffixe: suffixe, decimales: 1);
      if (x != null && !x.isNaN) setState(() => regler(x));
    }

    return PageDefilante([
      Text('Que suppose le cours ?', style: texte.titleLarge),
      const SizedBox(height: 4),
      const Text('Modèle des « value drivers » : flux libre = résultat × (1 − croissance / ROIC). La croissance coûte '
          'du capital, d\'autant moins que l\'entreprise est rentable. Ajustez les hypothèses pour juger du prix.'),
      if (!valo.disponible)
        const Card(
          margin: EdgeInsets.only(top: 12),
          child: ListTile(
            leading: Icon(Icons.info_outline),
            title: Text('Modèle non applicable (holding, pertes ou données manquantes). Pour une holding, comparez '
                'le cours à l\'actif net publié.'),
          ),
        )
      else ...[
        Carte(
          'Mes hypothèses',
          action: TextButton(
            onPressed: () => setState(() => _rendement = _croissance = _terminale = _roic = null),
            child: const Text('Revenir au départ'),
          ),
          enfant: Column(children: [
            Curseur('Rendement exigé', rr, 0.06, 0.14, 0.005, pct(rr, 1), (x) => setState(() => _rendement = x)),
            Curseur('Croissance des années 1 à 5', g.toDouble(), -0.05, 0.40, 0.005, pct(g, 1),
                (x) => setState(() => _croissance = x)),
            Curseur('Croissance perpétuelle', gt, 0, 0.04, 0.005, pct(gt, 1), (x) => setState(() => _terminale = x)),
            Curseur('ROIC des nouveaux investissements', roic, 0.06, 0.60, 0.01, pct(roic, 0),
                (x) => setState(() => _roic = x)),
          ]),
        ),
        Carte(
          'Ce que cela donne',
          enfant: Wrap(spacing: 12, runSpacing: 10, children: [
            Chiffre('Valeur intrinsèque / prix', ecart == null ? vide : pct(ecart - 1, 0, true),
                couleur: ecart == null ? null : couleurSigne(context, ecart - 1), largeur: 210),
            Chiffre('Prix juste',
                '${nombre(valo.prixJuste(croissance: g.toDouble(), rendement: rr, roic: roic, terminale: gt), 2)} ${v.devise}'),
            Chiffre('Croissance que suppose le cours',
                pct(valo.croissanceImplicite(rendement: rr, roic: roic, terminale: gt), 1), largeur: 240),
            Chiffre('TRI si mon scénario se réalise', pct(valo.tri(croissance: g.toDouble(), roic: roic, terminale: gt), 1),
                largeur: 220),
          ]),
        ),
        Carte(
          'Sensibilité : écart valeur / prix',
          sousTitre: 'En lignes le rendement exigé, en colonnes la croissance des années 1 à 5.',
          enfant: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Table(
              defaultColumnWidth: const FixedColumnWidth(84),
              children: [
                TableRow(children: [
                  const SizedBox.shrink(),
                  for (final dg in [-0.04, -0.02, 0.0, 0.02, 0.04])
                    Padding(
                      padding: const EdgeInsets.all(4),
                      child: Text(pct(g + dg, 0), textAlign: TextAlign.end, style: texte.labelMedium),
                    ),
                ]),
                for (final dr in [-0.01, 0.0, 0.01])
                  TableRow(children: [
                    Padding(padding: const EdgeInsets.all(4), child: Text(pct(rr + dr, 1), style: texte.labelMedium)),
                    for (final dg in [-0.04, -0.02, 0.0, 0.02, 0.04])
                      Builder(builder: (context) {
                        final x = valo.valeurSurCours(croissance: g + dg, rendement: rr + dr, roic: roic, terminale: gt);
                        return Padding(
                          padding: const EdgeInsets.all(4),
                          child: Text(x == null ? vide : pct(x - 1, 0, true),
                              textAlign: TextAlign.end,
                              style: TextStyle(
                                  color: x == null ? null : couleurSigne(context, x - 1),
                                  fontWeight: dr == 0 && dg == 0 ? FontWeight.bold : null)),
                        );
                      }),
                  ]),
              ],
            ),
          ),
        ),
      ],
      Carte(
        'Scénarios à 5 ans',
        sousTitre: '${base == 'fcf' ? 'Flux de trésorerie disponible' : 'Résultat net'} dans 5 ans × multiple de sortie, '
            'ramené à une action, hors dividendes. Touchez une hypothèse pour la modifier.',
        action: TextButton(
          onPressed: () => setState(() => _scenarios = hypothesesInitiales(v)),
          child: const Text('Proposer'),
        ),
        enfant: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 10, runSpacing: 10, children: [
            for (final nom in nomsScenarios)
              if (scenarios[nom] case final h?)
                SizedBox(
                  width: 280,
                  child: Card.filled(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(nom, style: texte.titleSmall),
                        Wrap(spacing: 6, children: [
                          ActionChip(
                            label: Text('Croissance ${pct(h.croissance, 1)}'),
                            onPressed: () => modifier('Croissance annuelle du chiffre d\'affaires', h.croissance * 100, '%',
                                (x) => h.croissance = x / 100),
                          ),
                          ActionChip(
                            label: Text('Marge ${pct(h.marge, 1)}'),
                            onPressed: () => modifier(base == 'fcf' ? 'Marge de FCF' : 'Marge nette', h.marge * 100, '%',
                                (x) => h.marge = x / 100),
                          ),
                          ActionChip(
                            label: Text('${base == 'fcf' ? 'P/FCF' : 'PER'} ${nombre(h.multiple, 1)}'),
                            onPressed: () => modifier('Multiple de sortie', h.multiple, 'x', (x) => h.multiple = x),
                          ),
                        ]),
                        const SizedBox(height: 6),
                        Text('${nombre(prixFutur(v, h), 2)} ${v.devise} dans 5 ans', style: texte.titleMedium),
                        Builder(builder: (context) {
                          final tri = rendementAnnuel(prixFutur(v, h), v.n('cours'));
                          return Text('${pct(tri, 1, true)} par an',
                              style: TextStyle(color: couleurSigne(context, tri), fontWeight: FontWeight.w600));
                        }),
                      ]),
                    ),
                  ),
                ),
          ]),
          const SizedBox(height: 8),
          Row(children: [
            FilledButton.tonalIcon(
              icon: const Icon(Icons.save_outlined),
              label: const Text('Enregistrer ces scénarios'),
              onPressed: () async {
                await etat.enregistrerScenarios(v, scenarios);
                _message('Scénarios enregistrés : l\'accueil signalera un cours hors de vos bornes.');
              },
            ),
            const SizedBox(width: 12),
            if (enregistres != null)
              Expanded(
                child: Text('Enregistrés le ${dateFr(enregistres['date'] as String?)} (cours d\'alors : '
                    '${nombre(enregistres['cours'], 2)} ${v.devise}).', style: texte.bodySmall),
              ),
          ]),
        ]),
      ),
      const AvertissementConseil(),
    ]);
  }

  // -------------------------------------------------------------------------------------------- notes
  Widget _notes(BuildContext context, Donnees d, Valeur v) {
    final texte = Theme.of(context).textTheme;
    final suivi = etat.suivi(v.ticker);
    final regles = etat.regles.where((r) => r.ticker == v.ticker).toList();
    return PageDefilante([
      Carte(
        'Ma thèse d\'investissement',
        sousTitre: 'Pourquoi cette valeur, ce qui la rend durable, ce qui me ferait vendre. Reste sur cet appareil.',
        enfant: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
          TextField(
            controller: _these,
            minLines: 4,
            maxLines: 14,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              hintText: 'Avantage concurrentiel, moteurs de croissance, risques, prix payé…',
            ),
          ),
          const SizedBox(height: 8),
          FilledButton.tonal(
            onPressed: () async {
              await etat.enregistrerThese(v.ticker, _these.text);
              _message('Thèse enregistrée.');
            },
            child: const Text('Enregistrer la thèse'),
          ),
        ]),
      ),
      Carte(
        'Mon prix visé',
        enfant: Row(children: [
          Expanded(
            child: Text(suivi?.prixVise == null
                ? 'Aucun prix visé. Fixez-le depuis l\'onglet Prix juste, ou saisissez-le ici.'
                : '${nombre(suivi!.prixVise, 2)} ${v.devise} (${suivi.objectif ?? 'objectif non précisé'}) · cours '
                    '${pct((v.n('cours') ?? 0) / suivi.prixVise! - 1, 0, true)} par rapport à ce prix'),
          ),
          TextButton(
            onPressed: () async {
              final x = await demanderNombre(context, 'Prix visé (${v.devise})',
                  actuel: suivi?.prixVise, suffixe: v.devise, aide: 'Laissez vide pour retirer le prix visé.');
              if (x == null) return;
              await etat.fixerPrixVise(v, x.isNaN ? null : x, objectif: 'saisi à la main');
            },
            child: Text(suivi?.prixVise == null ? 'Saisir' : 'Modifier'),
          ),
        ]),
      ),
      Carte(
        'Mes conditions de vente',
        sousTitre: 'Une règle atteinte invite à relire la thèse : ce n\'est pas un ordre de vente automatique.',
        action: IconButton(
          tooltip: 'Ajouter une règle',
          icon: const Icon(Icons.add),
          onPressed: () => _ajouterRegle(context, v),
        ),
        enfant: regles.isEmpty
            ? const Text('Aucune règle chiffrée. Exemple : « marge opérationnelle sous 15 % », « dette nette / '
                'EBITDA au-dessus de 3 ».')
            : Column(children: [
                for (final r in regles)
                  Builder(builder: (context) {
                    final (valeur, statut) = evaluerRegle(r, d);
                    return ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(
                        statut == 'Atteinte' ? Icons.warning_amber : Icons.check_circle_outline,
                        color: statut == 'Atteinte' ? Theme.of(context).colorScheme.error : vert,
                      ),
                      title: Text(texteRegle(r)),
                      subtitle: Text('Actuellement $valeur · $statut'),
                      trailing: IconButton(
                        tooltip: 'Retirer',
                        icon: const Icon(Icons.delete_outline),
                        onPressed: () => etat.retirerRegle(r),
                      ),
                    );
                  }),
              ]),
      ),
      Text('Les notes, prix visés et règles restent sur cet appareil.', style: texte.bodySmall),
    ]);
  }

  Future<void> _ajouterRegle(BuildContext context, Valeur v) async {
    var indicateur = 'marge_operationnelle', operateur = '<';
    final seuil = TextEditingController();
    final regle = await showDialog<Regle>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, majour) => AlertDialog(
          title: const Text('Nouvelle condition de vente'),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            DropdownButton<String>(
              isExpanded: true,
              value: indicateur,
              items: [
                for (final e in indicateursRegles.entries)
                  DropdownMenuItem(value: e.key, child: Text(e.value.$1, overflow: TextOverflow.ellipsis)),
              ],
              onChanged: (x) => majour(() => indicateur = x ?? indicateur),
            ),
            Row(children: [
              DropdownButton<String>(
                value: operateur,
                items: [for (final e in texteOperateurs.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
                onChanged: (x) => majour(() => operateur = x ?? operateur),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: seuil,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                  decoration: InputDecoration(
                    labelText: 'Seuil',
                    suffixText: switch (indicateursRegles[indicateur]!.$2) { 'pct' => '%', 'x' => 'x', _ => '' },
                    helperText: 'Actuellement : ${nombre(_actuel(v, indicateur), 1)}',
                  ),
                ),
              ),
            ]),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
            FilledButton(
              onPressed: () {
                final x = double.tryParse(seuil.text.trim().replaceAll(',', '.'));
                if (x != null) Navigator.pop(context, Regle(v.ticker, indicateur, operateur, x));
              },
              child: const Text('Ajouter'),
            ),
          ],
        ),
      ),
    );
    if (regle != null) await etat.ajouterRegle(regle);
  }

  /// Valeur actuelle d'un indicateur, en unités d'affichage (un ratio en %).
  double? _actuel(Valeur v, String indicateur) {
    final x = v.n(indicateur);
    return x == null ? null : (indicateursRegles[indicateur]!.$2 == 'pct' ? x * 100 : x);
  }
}

/// Choix de la valeur en haut de la fiche (la liste déroulante de l'outil du PC).
class SelecteurValeur extends StatelessWidget {
  const SelecteurValeur(this.v, {super.key});

  final Valeur? v;

  @override
  Widget build(BuildContext context) {
    final t = Teintes.de(context);
    return Material(
      color: t.fondSecondaire,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () async {
          final choix = await choisirValeur(context, titre: 'Fiche valeur');
          if (choix is ChoixValeur) tickerFiche.value = choix.valeur.ticker;
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Row(children: [
            Expanded(
              child: Text(v == null ? 'Nom ou ticker…' : '${v!.nom} (${v!.ticker})',
                  style: TextStyle(fontSize: 15, color: v == null ? t.legende : t.texte)),
            ),
            Icon(Icons.keyboard_arrow_down, size: 20, color: t.texte),
          ]),
        ),
      ),
    );
  }
}

/// Rubrique « Fiche valeur » : la valeur choisie (recherche, clic dans un tableau), sinon la première ligne du
/// portefeuille, sinon la mieux classée.
class PageFicheValeur extends StatelessWidget {
  const PageFicheValeur({super.key});

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<String?>(
        valueListenable: tickerFiche,
        builder: (context, choisi, _) {
          final d = etat.donnees;
          if (d == null) {
            return const PageClimax(titre: 'Fiche valeur', enfants: [
              Encadre('Aucune donnée : configurez l\'accès dans la rubrique Réglages.'),
            ]);
          }
          final lignes = [...etat.portefeuille]..sort((a, b) => b.poids.compareTo(a.poids));
          final ticker = choisi ??
              lignes.map((l) => l.ticker).where(d.valeurs.containsKey).firstOrNull ??
              d.triees.firstOrNull?.ticker;
          if (ticker == null) {
            return const PageClimax(titre: 'Fiche valeur', avantTitre: SelecteurValeur(null), enfants: []);
          }
          return Fiche(key: ValueKey(ticker), ticker: ticker);
        },
      );
}
