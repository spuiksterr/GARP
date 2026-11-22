"""Chaque page de l'interface s'affiche sans erreur, sur le jeu d'essai (voir conftest.py), sans réseau.

Lent (une minute environ) : à lancer après une modification de vues/ ou de pf/ui.py, avec
    .venv/Scripts/python.exe -m pytest tests -q -m pages
Sur les données réelles du poste : variable d'environnement PF_TESTS_REELS=1.
Aucun bouton n'est cliqué : les tests ne modifient ni la watchlist ni la configuration.
"""
import os
import warnings
from pathlib import Path

import pytest

pytestmark = pytest.mark.pages
RACINE = Path(__file__).resolve().parent.parent
PAGES = sorted(p.stem for p in (RACINE / "vues").glob("*.py"))
SECTIONS = ["Résumé", "Prix juste", "Activité", "Historique", "Valorisation", "Thèse"]
# Une valeur américaine, une européenne, une banque et un fonds : des chemins différents dans la fiche.
VALEURS = ["ADBE", "MC.PA", "JPM", "NUKL.DE"]


def _app(page: str):
    from streamlit.testing.v1 import AppTest

    warnings.filterwarnings("ignore")
    os.chdir(RACINE)
    return AppTest.from_file(str(RACINE / "vues" / f"{page}.py"), default_timeout=300)


@pytest.mark.parametrize("page", PAGES)
def test_page_sans_erreur(page):
    at = _app(page)
    at.run()
    assert not at.exception, [str(e.value)[:300] for e in at.exception]


@pytest.mark.parametrize("valeur", VALEURS)
def test_sections_de_la_fiche(valeur):
    at = _app("fiche")
    at.run()
    if not any(str(o).endswith(f"({valeur})") for o in at.selectbox[0].options):  # libellés « Nom (TICKER) »
        pytest.skip(f"{valeur} absente des données")
    at.selectbox[0].set_value(valeur)
    at.run()
    for section in SECTIONS:
        at.get("segmented_control")[0].set_value(section)
        at.run()
        assert not at.exception, (section, [str(e.value)[:300] for e in at.exception])


def test_simulation_page_risques():
    at = _app("risques")
    at.run()
    choix = [s for s in at.selectbox if s.label == "Ligne à simuler"]
    assert choix, "sélecteur de la simulation absent"
    choix[0].set_value("GOOGL")
    at.run()
    assert not at.exception, [str(e.value)[:300] for e in at.exception]
    assert any("Alphabet" in m.value and "→" in m.value for m in at.markdown)
    assert any("Nombre effectif de lignes" in df.value.to_string() for df in at.dataframe)


def test_import_d_un_portefeuille_colle():
    """Lignes collées, lues puis présentées pour vérification (sans enregistrer)."""
    at = _app("importer")
    at.run()
    at.text_area[0].set_value("Air Liquide 30\nMSFT 50\nAXA 20\nSociété inconnue 5")
    [b for b in at.button if b.label == "Lire mes lignes"][0].click()
    at.run()
    assert not at.exception, [str(e.value)[:300] for e in at.exception]
    metriques = {m.label: m.value for m in at.metric}
    assert metriques["Lignes retenues"] == "4" and metriques["Hors des données"] == "1"
    assert any(b.label.startswith("Enregistrer (3 lignes)") for b in at.button)


def test_vigilance_homme_cle(monkeypatch):
    """Une ligne relue au risque homme-clé élevé, les autres sans note (cases vides) : le tableau de bord le signale."""
    import yfinance

    from pf import homme_cle

    class Faux:
        def __init__(self, ticker):
            self.info = {"companyOfficers": [{"name": "Test Fondateur", "title": "Founder, Chairman & CEO", "age": 71}],
                         "heldPercentInsiders": 0.4}

    monkeypatch.setattr(yfinance, "Ticker", Faux)
    homme_cle.relire(["MSFT"], pause=0)
    at = _app("accueil")
    at.run()
    assert not at.exception, [str(e.value)[:300] for e in at.exception]
    assert any("Homme-clé" in df.value.to_string() for df in at.dataframe)


def test_import_avec_quantites_propose_la_photo():
    """Lignes avec quantités : l'enregistrement de la photo du portefeuille est proposé, pour toutes les lignes."""
    at = _app("importer")
    at.run()
    at.text_area[0].set_value("Nom;Quantité\nAir Liquide;10\nAlphabet;5\nLVMH;2")
    [b for b in at.button if b.label == "Lire mes lignes"][0].click()
    at.run()
    assert not at.exception, [str(e.value)[:300] for e in at.exception]
    bascule = [t for t in at.toggle if t.label.startswith("Enregistrer aussi mes quantités")][0]
    assert "(3 lignes)" in bascule.label  # la photo remplace tout : rien n'est écarté
    assert bascule.value


def test_mon_portefeuille_analyse_et_equilibre_propose():
    """Analyse des lignes (verdict de prix, qualité) et onglet « Équilibre » : poids réels du journal face aux cibles."""
    at = _app("modele")
    at.run()
    assert not at.exception, [str(e.value)[:300] for e in at.exception]
    assert any(m.label == "Hors des filtres" for m in at.metric)
    assert any("verdict" in df.value.columns for df in at.dataframe)  # analyse des lignes
    assert any(m.label == "Lignes loin de leur cible" for m in at.metric)  # onglet Équilibre (journal du jeu d'essai)
    assert any("a_ajuster_eur" in df.value.columns for df in at.dataframe)


def test_la_bonne_action_au_bon_prix_dans_tout_l_univers():
    at = _app("prix_achat")
    at.run()
    assert not at.exception, [str(e.value)[:300] for e in at.exception]
    assert at.segmented_control[0].value == "Toutes les actions de qualité" or any(
        s.value == "Toutes les actions de qualité" for s in at.get("segmented_control"))
    assert any(m.label == "Au bon prix" for m in at.metric)
    # Classement par la note GARP, sans choix de style ; boutons d'action au-dessus du tableau.
    assert not [s for s in at.get("segmented_control") if s.label == "Classer selon le style"]
    assert any("score" in df.value.columns for df in at.dataframe)
    libelles = [b.label for b in at.button]
    assert "Ouvrir la fiche" in libelles and "Ajouter à la watchlist (0)" in libelles



def test_grands_investisseurs_dans_la_version_installee(monkeypatch):
    """Version installée : pas de bouton de mise à jour des 13F (ils arrivent avec les données de la nuit)."""
    monkeypatch.setenv("PF_AUTONOME", "1")
    at = _app("investisseurs")
    at.run()
    assert not at.exception, [str(e.value)[:300] for e in at.exception]
    assert not any(b.label == "Mettre à jour" for b in at.button)
    assert any("chaque nuit par GitHub" in c.value for c in at.caption)

def test_barre_laterale_de_la_version_installee(monkeypatch):
    """Version installée sans jeton (dépôt public) : ni mise à jour Yahoo ni SEC, les données de la nuit sans
    jeton, et le jeton proposé en option."""
    from streamlit.testing.v1 import AppTest

    from pf import autonome

    monkeypatch.setenv("PF_AUTONOME", "1")
    monkeypatch.setattr(autonome, "jeton", lambda: None)
    monkeypatch.setattr(autonome, "etat_local", lambda: {"archive": "2026-11-18T00:18:59Z"})
    lancees = []
    monkeypatch.setattr(autonome, "chercher_en_arriere_plan", lambda tache, jeton_: lancees.append(jeton_))
    warnings.filterwarnings("ignore")
    os.chdir(RACINE)
    at = AppTest.from_file(str(RACINE / "app.py"), default_timeout=300)
    at.run()
    assert not at.exception, [str(e.value)[:300] for e in at.exception]
    libelles = [b.label for b in at.sidebar.button]
    assert "Données de la nuit" in libelles and "Jeton GitHub (facultatif)" in libelles
    assert "Mise à jour rapide" not in libelles and "Relier à GitHub" not in libelles
    assert lancees == [None]  # recherche anonyme


def test_nouvelles_donnees_proposees_sans_attendre(monkeypatch):
    """Version installée avec des données : la page s'affiche aussitôt, la recherche part en arrière-plan, et des
    données téléchargées entre-temps sont proposées au chargement."""
    from streamlit.testing.v1 import AppTest

    from pf import autonome, ui

    monkeypatch.setenv("PF_AUTONOME", "1")
    monkeypatch.setattr(autonome, "jeton", lambda: "jeton")
    monkeypatch.setattr(autonome, "etat_local", lambda: {"archive": "2026-11-18T00:18:59Z"})
    lancees = []

    def recherche_simulee(tache, jeton_):
        lancees.append(jeton_)
        tache.statut, tache.archive = "pret", {"id": 1, "taille": 1, "date": "2026-11-19T00:18:59Z"}
        tache.fichier = Path("inutile.zip")

    monkeypatch.setattr(autonome, "chercher_en_arriere_plan", recherche_simulee)
    ui._tache_nuit.clear()
    warnings.filterwarnings("ignore")
    os.chdir(RACINE)
    at = AppTest.from_file(str(RACINE / "app.py"), default_timeout=300)
    at.run()
    assert not at.exception, [str(e.value)[:300] for e in at.exception]
    assert lancees == ["jeton"]
    assert any(b.label == "Charger les nouvelles données" for b in at.sidebar.button)
    ui._tache_nuit.clear()


def test_application_complete():
    """app.py : configuration de la page (icône), navigation et barre latérale."""
    from streamlit.testing.v1 import AppTest

    warnings.filterwarnings("ignore")
    os.chdir(RACINE)
    at = AppTest.from_file(str(RACINE / "app.py"), default_timeout=300)
    at.run()
    assert not at.exception, [str(e.value)[:300] for e in at.exception]


def test_ponderation_garp_depuis_le_tableau_de_bord():
    """Les curseurs du tableau de bord règlent les poids de la note GARP (rétablis à la fin du test)."""
    from pf import scoring

    try:
        at = _app("accueil")
        at.run()
        assert not at.exception, [str(e.value)[:300] for e in at.exception]
        assert any(e.label.startswith("Pondération de la note GARP : Croissance 40 %") for e in at.expander)
        at.slider(key="garp_croissance").set_value(0)
        at.run()
        assert not at.exception, [str(e.value)[:300] for e in at.exception]
        assert scoring.poids_garp()["croissance"] == 0
        assert any(e.label.startswith("Pondération de la note GARP : Croissance 0 %") for e in at.expander)
    finally:
        scoring.enregistrer_poids_garp(None)
