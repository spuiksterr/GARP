/// Premier lancement, en trois étapes : ce que fait G.A.R.P, l'accès aux données (jeton GitHub), le portefeuille.
library;

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';
import 'package:url_launcher/url_launcher.dart';

import '../github.dart';
import '../main.dart';
import '../navigation.dart';
import '../widgets.dart';
import 'import.dart';

class Bienvenue extends StatefulWidget {
  const Bienvenue({super.key});

  @override
  State<Bienvenue> createState() => _BienvenueState();
}

class _BienvenueState extends State<Bienvenue> {
  final _pages = PageController();
  int _etape = 0;

  void _suivante() => _pages.nextPage(duration: const Duration(milliseconds: 350), curve: Curves.easeOutCubic);

  Future<void> _terminer() async {
    rubrique.value = etat.portefeuille.isEmpty ? Rubrique.tableauDeBord : Rubrique.composition;
    // Rouvert depuis les réglages : on revient simplement à l'application.
    if (Navigator.of(context).canPop()) Navigator.of(context).pop();
    await etat.terminerBienvenue();
  }

  @override
  void dispose() {
    _pages.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          Expanded(
            child: PageView(
              controller: _pages,
              onPageChanged: (i) => setState(() => _etape = i),
              children: [
                _Presentation(suite: _suivante),
                _Acces(suite: _suivante),
                _Portefeuille(terminer: _terminer),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
            child: Row(children: [
              for (var i = 0; i < 3; i++)
                AnimatedContainer(
                  duration: const Duration(milliseconds: 250),
                  margin: const EdgeInsets.only(right: 6),
                  width: i == _etape ? 22 : 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: i == _etape ? Theme.of(context).colorScheme.primary : Theme.of(context).colorScheme.outlineVariant,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              const Spacer(),
              if (_etape > 0) TextButton(onPressed: _terminer, child: const Text('Passer')),
            ]),
          ),
        ]),
      ),
    );
  }
}

/// Une étape : contenu centré, limité en largeur sur un grand écran.
class _Etape extends StatelessWidget {
  const _Etape({required this.enfants});

  final List<Widget> enfants;

  @override
  Widget build(BuildContext context) => Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: enfants),
          ),
        ),
      );
}

class _Presentation extends StatelessWidget {
  const _Presentation({required this.suite});

  final VoidCallback suite;

  @override
  Widget build(BuildContext context) {
    final texte = Theme.of(context).textTheme;
    Widget point(IconData icone, String titre, String detail) => ListTile(
          contentPadding: EdgeInsets.zero,
          leading: CircleAvatar(
            backgroundColor: Theme.of(context).colorScheme.primaryContainer,
            child: Icon(icone, color: Theme.of(context).colorScheme.onPrimaryContainer),
          ),
          title: Text(titre, style: texte.titleMedium),
          subtitle: Text(detail),
        );
    // Fenêtre basse (Windows en 1280 × 720, téléphone à l'horizontale) : logo réduit pour garder « Commencer » visible.
    final bas = MediaQuery.sizeOf(context).height < 820;
    return _Etape(enfants: [
      Center(
        child: Container(
          padding: EdgeInsets.all(bas ? 14 : 28),
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            gradient: LinearGradient(colors: [anthracite, graphite], begin: Alignment.topLeft, end: Alignment.bottomRight),
          ),
          child: Logo(taille: bas ? 56 : 112, embleme: true),
        ),
      ),
      SizedBox(height: bas ? 8 : 20),
      Center(
        child: Text('G.A.R.P',
            style: (bas ? texte.headlineMedium : texte.displaySmall)?.copyWith(fontWeight: FontWeight.w700)),
      ),
      Center(child: Text('Investir sur le temps long, avec méthode.', style: texte.titleMedium)),
      SizedBox(height: bas ? 8 : 24),
      point(Icons.filter_alt_outlined, '1 760 actions passées au crible',
          'S&P 500, STOXX 600 et Nasdaq : qualité, croissance, valorisation. Recalculé chaque nuit.'),
      point(Icons.shield_outlined, 'Votre portefeuille sous contrôle',
          'Concentration, secteurs, devises, points de vigilance, ligne par ligne.'),
      point(Icons.lock_outline, 'Vos lignes restent chez vous',
          'Le portefeuille et la watchlist ne quittent jamais cet appareil.'),
      SizedBox(height: bas ? 12 : 24),
      SizedBox(
        width: double.infinity,
        child: FilledButton(onPressed: suite, child: const Text('Commencer')),
      ),
    ]);
  }
}

class _Acces extends StatefulWidget {
  const _Acces({required this.suite});

  final VoidCallback suite;

  @override
  State<_Acces> createState() => _AccesState();
}

class _AccesState extends State<_Acces> {
  final _jeton = TextEditingController();

  Future<void> _coller() async {
    final t = (await Clipboard.getData(Clipboard.kTextPlain))?.text?.trim() ?? '';
    setState(() => _jeton.text = t);
  }

  Future<void> _verifier() async {
    if (_jeton.text.trim().isEmpty) return;
    await etat.reglerAcces(_jeton.text, etat.depot);
    if (mounted && etat.erreur == null && etat.donnees != null) widget.suite();
  }

  @override
  Widget build(BuildContext context) {
    final texte = Theme.of(context).textTheme;
    Widget etape(int n, String titre, Widget? suite) => Padding(
          padding: const EdgeInsets.only(top: 14),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            CircleAvatar(radius: 13, child: Text('$n', style: texte.labelLarge)),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(titre),
                ?suite,
              ]),
            ),
          ]),
        );
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) => _Etape(enfants: [
        Text('Accès aux données', style: texte.headlineSmall),
        const SizedBox(height: 8),
        const Text('Chaque nuit, GitHub recalcule les données et les range dans le dépôt privé de G.A.R.P. '
            'Pour les lire, l\'application a besoin d\'un jeton GitHub en lecture seule, à créer une fois par '
            'appareil (deux minutes).'),
        etape(
          1,
          'Ouvrez la page de création du jeton, connecté au compte propriétaire du dépôt.',
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              icon: const Icon(Icons.open_in_new),
              label: const Text('Créer le jeton sur GitHub'),
              onPressed: () => launchUrl(urlCreationJeton(etat.depot), mode: LaunchMode.externalApplication),
            ),
          ),
        ),
        etape(2, 'Repository access : « Only select repositories », puis ${etat.depot.split('/').last}. '
            'Permissions : Contents en « Read-only ». Puis « Generate token ».', null),
        etape(
          3,
          'Copiez le jeton (github_pat_…) et collez-le ici.',
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: TextField(
              controller: _jeton,
              obscureText: true,
              decoration: InputDecoration(
                border: const OutlineInputBorder(),
                isDense: true,
                hintText: 'github_pat_…',
                suffixIcon: IconButton(tooltip: 'Coller', icon: const Icon(Icons.content_paste), onPressed: _coller),
              ),
              onSubmitted: (_) => _verifier(),
            ),
          ),
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            icon: etat.enCours
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.cloud_download_outlined),
            label: Text(etat.enCours ? 'Téléchargement des données…' : 'Vérifier et télécharger les données'),
            onPressed: etat.enCours ? null : _verifier,
          ),
        ),
        if (etat.erreur != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(etat.erreur!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        if (etat.donnees != null && etat.erreur == null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Row(children: [
              const Icon(Icons.check_circle, color: Colors.green),
              const SizedBox(width: 8),
              Expanded(child: Text('Données reçues : ${etat.donnees!.valeurs.length} valeurs.')),
              TextButton(onPressed: widget.suite, child: const Text('Suite')),
            ]),
          ),
        const SizedBox(height: 8),
        Text('Le jeton est chiffré sur l\'appareil et n\'est envoyé qu\'à GitHub. Il ne permet que de lire ce dépôt.',
            style: texte.bodySmall),
      ]),
    );
  }
}

class _Portefeuille extends StatelessWidget {
  const _Portefeuille({required this.terminer});

  final Future<void> Function() terminer;

  @override
  Widget build(BuildContext context) {
    final texte = Theme.of(context).textTheme;
    return ListenableBuilder(
      listenable: etat,
      builder: (context, _) => _Etape(enfants: [
        Text('Votre portefeuille', style: texte.headlineSmall),
        const SizedBox(height: 8),
        const Text('Importez vos positions : G.A.R.P reconnaît les valeurs par leur nom, leur ticker ou leur ISIN, '
            'calcule les poids, et vous laisse vérifier avant d\'enregistrer.'),
        const SizedBox(height: 12),
        if (etat.portefeuille.isEmpty)
          const ChoixImport()
        else
          Card(
            child: ListTile(
              leading: const Icon(Icons.check_circle, color: Colors.green),
              title: Text('${etat.portefeuille.length} lignes enregistrées'),
              subtitle: const Text('Vous pourrez les modifier dans l\'onglet Portefeuille.'),
            ),
          ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            onPressed: terminer,
            child: Text(etat.portefeuille.isEmpty ? 'Plus tard' : 'Découvrir G.A.R.P'),
          ),
        ),
      ]),
    );
  }
}
