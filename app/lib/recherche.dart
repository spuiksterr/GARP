/// Recherche personnalisée : « la bonne action au bon prix », selon le profil de l'investisseur.
///
/// - La bonne action : éligible (filtres de qualité de l'outil), bien notée par la méthode du profil, et conforme
///   à ses exigences (critères remplis, moat, taille, secteurs écartés, enveloppe).
/// - Le bon prix : le cours comparé au prix juste, c'est-à-dire le cours auquel l'action rapporte le rendement
///   exigé du profil si la croissance attendue se réalise (modèle des « value drivers », valorisation.dart). Le
///   prix d'achat laisse en plus la marge de sécurité du profil.
/// Ce classement est un point de départ pour étudier l'entreprise, jamais une recommandation.
library;

import 'donnees.dart';
import 'methodes.dart';
import 'stockage.dart';
import 'valorisation.dart';

enum Verdict {
  /// Cours sous le prix d'achat (prix juste moins la marge de sécurité).
  bonPrix('Au bon prix', 'Le cours est sous votre prix d\'achat.'),

  /// Cours entre le prix d'achat et le prix juste.
  prixCorrect('Prix correct', 'Sous le prix juste, mais sans votre marge de sécurité.'),

  /// Cours au-dessus du prix juste.
  aAttendre('À attendre', 'Bonne entreprise, mais le cours dépasse votre prix juste.'),

  /// Le modèle ne s'applique pas (holding, pertes, données absentes).
  nonEvalue('Prix non évalué', 'Le modèle de valorisation ne s\'applique pas à cette société.');

  const Verdict(this.libelle, this.explication);

  final String libelle;
  final String explication;
}

class Opportunite {
  Opportunite(this.v, this.note, this.prixJuste, this.prixAchat, this.verdict, this.tri);

  final Valeur v;

  /// Note de 0 à 100 selon la méthode du profil.
  final double note;

  /// Prix juste et prix d'achat (marge de sécurité déduite), dans la devise de cotation.
  final double? prixJuste;
  final double? prixAchat;
  final Verdict verdict;

  /// Rendement annuel implicite au cours actuel.
  final double? tri;

  /// Écart du cours au prix juste : −0,20 veut dire 20 % sous le prix juste.
  double? get ecart {
    final cours = v.n('cours');
    return cours == null || prixJuste == null ? null : cours / prixJuste! - 1;
  }

  /// Potentiel jusqu'au prix juste.
  double? get potentiel {
    final cours = v.n('cours');
    return cours == null || cours <= 0 || prixJuste == null ? null : prixJuste! / cours - 1;
  }
}

/// Une valeur satisfait-elle les exigences du profil (hors prix) ? Renvoie la première raison de l'écarter.
String? raisonEcartee(Valeur v, Profil p) {
  if (!v.eligible) return v.motifsExclusion ?? 'Ne passe pas les filtres de qualité';
  if (p.enveloppe != 'Toutes' && v.enveloppe != p.enveloppe) return 'Hors de votre enveloppe (${p.enveloppe})';
  if (p.secteursExclus.contains(v.secteur)) return 'Secteur écarté dans votre profil';
  final capi = v.n('capitalisation_eur');
  if (p.capitalisationMin > 0 && (capi == null || capi < p.capitalisationMin * 1e9)) {
    return 'Capitalisation sous votre minimum';
  }
  if (p.criteresMin > 0) {
    final ok = v.n('criteres_ok'), evalues = v.n('criteres_evalues');
    if (ok == null || evalues == null || evalues < 2 || ok / evalues < p.criteresMin / 6 - 1e-9) {
      return 'Moins de ${p.criteresMin} critères de qualité sur 6';
    }
  }
  if (p.exclureMoatFaible && v.t('moat') == 'Faible') return 'Avantage concurrentiel estimé faible';
  return null;
}

/// Jugement du prix d'une valeur pour un profil.
Opportunite evaluer(Valeur v, double note, Profil p, ReglagesValorisation reglages) {
  final valo = Valorisation(v, reglages);
  final juste = valo.prixJuste();
  final achat = juste == null ? null : juste * (1 - p.margeSecurite);
  final cours = v.n('cours');
  final verdict = juste == null || cours == null
      ? Verdict.nonEvalue
      : cours <= achat!
          ? Verdict.bonPrix
          : cours <= juste
              ? Verdict.prixCorrect
              : Verdict.aAttendre;
  return Opportunite(v, note, juste, achat, verdict, valo.tri());
}

/// Les valeurs qui conviennent au profil, de la mieux notée à la moins bien notée par sa méthode.
List<Opportunite> opportunites(Donnees d, Profil p, ReglagesValorisation reglages, {Methode? methode}) {
  final m = methode ?? d.methode(p.methode);
  final notes = d.notes(m);
  return [
    for (final v in d.classees(m))
      if (notes[v.ticker] != null && raisonEcartee(v, p) == null) evaluer(v, notes[v.ticker]!, p, reglages),
  ];
}

/// Méthode conseillée d'après trois réponses (questionnaire du profil) : ce que l'on cherche d'abord.
String methodeConseillee({required String priorite, required String horizon, required String prix}) {
  if (priorite == 'croissance') return horizon == 'long' ? 'fisher' : 'croissance';
  if (priorite == 'solidite') return 'munger';
  if (priorite == 'prix') return prix == 'strict' ? 'valeur' : 'buffett';
  if (priorite == 'qualite') return prix == 'strict' ? 'buffett' : 'smith';
  return 'regards';
}
