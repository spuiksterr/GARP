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
