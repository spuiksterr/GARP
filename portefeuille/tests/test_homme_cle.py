"""Risque homme-clé : note, niveaux, corrections manuelles et relecture des dirigeants (Yahoo simulé)."""
import math

import pandas as pd
import pytest

from pf import homme_cle
from pf.config import METRICS_PARQUET


def _info(dirigeants, inities=None, conseil=None, effectif=50000):
    return {"dirigeants": dirigeants, "heldPercentInsiders": inities, "boardRisk": conseil,
            "fullTimeEmployees": effectif}


def test_fondateur_aux_commandes_risque_eleve():
    e = homme_cle.evaluer(_info([{"nom": "Elon R. Musk", "fonction": "Co-Founder, Technoking of Tesla, CEO & Director",
                                  "age": 54}], inities=0.178, conseil=10))
    assert e["homme_cle"] == 6 and e["homme_cle_niveau"] == "Élevé"
    assert "fondateur dirige" in e["homme_cle_facteurs"] and "18 % du capital" in e["homme_cle_facteurs"]


def test_pdg_age_et_famille_risque_modere():
    e = homme_cle.evaluer(_info([{"nom": "Bernard Arnault", "fonction": "Chairman & CEO", "age": 76}], inities=0.50))
    assert e["homme_cle"] == 5.5 and e["homme_cle_niveau"] == "Modéré"
    assert e["homme_cle_dirigeant"] == "Bernard Arnault (Chairman & CEO, 76 ans)"


def test_directoire_et_president_executif_ne_sont_pas_un_cumul():
    # « Chair of the Board of Management » : le directoire, pas le conseil.
    asml = homme_cle.evaluer(_info([{"nom": "C. Fouquet", "fonction": "President, CEO and Chair of the Board of Management",
                                     "age": 52}]))
    assert asml["homme_cle"] == 0 and asml["homme_cle_niveau"] == "Faible"
    # Président exécutif listé avant le directeur général : le dirigeant principal reste le directeur général.
    ferrari = homme_cle.evaluer(_info([{"nom": "John Elkann", "fonction": "Executive Chairman", "age": 49},
                                       {"nom": "Benedetto Vigna", "fonction": "CEO & Executive Director", "age": 56}]))
    assert ferrari["homme_cle_dirigeant"].startswith("Benedetto Vigna")


def test_fondateur_president_du_conseil():
    e = homme_cle.evaluer(_info([{"nom": "Andrew R. Jassy", "fonction": "President, CEO & Director", "age": 57},
                                 {"nom": "Jeffrey P. Bezos", "fonction": "Founder & Executive Chairman", "age": 61}]))
    assert e["homme_cle"] == 3 and "fondateur préside" in e["homme_cle_facteurs"]


def test_correction_bornes_et_donnees_absentes():
    rien = homme_cle.evaluer({"fullTimeEmployees": 120})
    assert math.isnan(rien["homme_cle"]) and rien["homme_cle_niveau"] == "Inconnu"
    corrige = homme_cle.evaluer({"boardRisk": 10}, 4, "fondateur absent de la liste")
    # Cas de NVIDIA : conseil ISS 10/10 (1 point) et correction de 4 points.
    assert corrige["homme_cle"] == 5 and "correction manuelle +4 : fondateur absent" in corrige["homme_cle_facteurs"]
    sature = homme_cle.evaluer(_info([{"nom": "X", "fonction": "Founder, Chairman & CEO", "age": 80}], inities=0.6,
                                     conseil=9, effectif=200), 3)
    assert sature["homme_cle"] == 10


def test_liste_de_yahoo_reduite():
    d = homme_cle.dirigeants_yahoo([{"name": "Mr. Bernard  Arnault", "title": "Chairman & CEO", "yearBorn": 1949},
                                    {"name": "Ms. Aude  Rodriguez", "title": "Head of Investor Relations"}, {"title": "?"}])
    assert d[0]["nom"] == "Bernard Arnault" and d[0]["age"] == pd.Timestamp.today().year - 1949
    assert d[1] == {"nom": "Aude Rodriguez", "fonction": "Head of Investor Relations", "age": None}
    assert len(d) == 2


def test_relecture_reportee_dans_les_indicateurs(monkeypatch):
    class Faux:
        def __init__(self, ticker):
            self.info = {"companyOfficers": [{"name": "Mr. Test Fondateur", "title": "Founder & CEO", "age": 72}],
                         "heldPercentInsiders": 0.35, "boardRisk": 3}

    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", Faux)
    notes = homme_cle.relire(["MSFT", "INCONNU"], pause=0)
    assert list(notes) == ["MSFT"]  # une valeur sans fiche en cache est ignorée
    assert notes["MSFT"]["homme_cle"] == 8 and notes["MSFT"]["homme_cle_niveau"] == "Élevé"
    m = pd.read_parquet(METRICS_PARQUET)
    assert m.loc["MSFT", "homme_cle"] == 8 and m.loc["MSFT", "homme_cle_niveau"] == "Élevé"
    from pf.data import load_fundamentals
    assert load_fundamentals("MSFT")["info"]["dirigeants"][0]["nom"] == "Test Fondateur"


@pytest.mark.parametrize("ligne, attendu", [("NVDA;4;fondateur", (4.0, "fondateur")), ("AAA;;", (0.0, ""))])
def test_lecture_des_corrections(tmp_path, monkeypatch, ligne, attendu):
    f = tmp_path / "homme_cle.csv"
    f.write_text("ticker;ajustement;motif\n" + ligne + "\n", encoding="utf-8")
    monkeypatch.setattr(homme_cle, "AJUSTEMENTS_CSV", f)
    assert homme_cle.load_ajustements()[ligne.split(";")[0]] == attendu
