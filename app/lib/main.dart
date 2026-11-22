import 'package:material_ui/material_ui.dart';

import 'etat.dart';
import 'interface.dart';
import 'navigation.dart';
import 'pages/bienvenue.dart';
import 'widgets.dart';

final etat = Etat();

// Couleurs de la marque (portefeuille/docs/MARQUE.md).
const anthracite = Color(0xFF18191C);
const graphite = Color(0xFF3A3C41);
const ocre = Color(0xFFC98B2E);
const ivoire = Color(0xFFEDE6D8);

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const GarpApp());
  etat.demarrer();
}

class GarpApp extends StatelessWidget {
  const GarpApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'G.A.R.P',
      debugShowCheckedModeBanner: false,
      // Toujours en sombre, avec les couleurs du thème sombre de l'outil du PC (.streamlit/config.toml).
      theme: themeGarp(Brightness.dark),
      darkTheme: themeGarp(Brightness.dark),
      themeMode: ThemeMode.dark,
      home: const Demarrage(),
    );
  }
}

/// Écran de lancement le temps de lire les réglages, puis l'accueil du premier lancement ou l'application.
class Demarrage extends StatelessWidget {
  const Demarrage({super.key});

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: etat,
        builder: (context, _) {
          if (!etat.pret) {
            return const Scaffold(body: Center(child: Logo(taille: 112)));
          }
          return etat.bienvenueVue ? const Coquille() : const Bienvenue();
        },
      );
}
