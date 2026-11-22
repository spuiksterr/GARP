"""Acheter au bon prix : prix juste cohérent avec le TRI implicite, verdicts, réglages."""
import math

import numpy as np
import pandas as pd
import pytest

from pf import prix_achat as pa
from pf.config import load_strategy
from pf.scoring import build_screener


@pytest.fixture(scope="module")
def sc():
    return build_screener()


def test_au_rendement_egal_au_tri_le_prix_juste_est_le_cours(sc):
    vcfg = load_strategy()["valorisation"]
    verifiees = 0
    for t, r in sc.iterrows():
        tri = pd.to_numeric(pd.Series([r.get("tri_implicite")]), errors="coerce").iloc[0]
        if not (pd.notna(tri) and 0.04 < tri < 0.39):  # hors des bornes de la recherche du TRI
            continue
        juste = pa.prix_juste(r, vcfg, float(tri))
        assert juste == pytest.approx(float(r["cours"]), rel=0.01), t
        verifiees += 1
    assert verifiees >= 5


def test_verdicts():
    assert pa.verdict(80, 120, 96) == "Au bon prix"
    assert pa.verdict(100, 120, 96) == "Prix correct"
    assert pa.verdict(130, 120, 96) == "À attendre"
    assert pa.verdict(100, math.nan, math.nan) == "Non évalué"


def test_tableau_trie_et_prix_vise(sc):
    vcfg = load_strategy()["valorisation"]
    tickers = list(sc.index[:8])
    tab = pa.tableau(sc, {t: "Portefeuille" for t in tickers}, vcfg, 0.09, 0.2, {tickers[0]: 1e9})
    assert set(tab.index) <= set(tickers) and len(tab) == len(tickers)
    ordre = [list(pa.VERDICTS.values()).index(v) for v in tab["verdict"]]
    assert ordre == sorted(ordre)  # au bon prix d'abord, non évalué à la fin
    assert tab.loc[tickers[0], "vise_atteint"]  # prix visé très haut : atteint
    evaluees = tab[tab["prix_juste"].notna()]
    assert np.allclose(evaluees["prix_achat"], evaluees["prix_juste"] * 0.8)
    # Un rendement exigé plus élevé abaisse le prix juste.
    plus_exigeant = pa.tableau(sc, {t: "Portefeuille" for t in tickers}, vcfg, 0.12, 0.2)
    commun = evaluees.index.intersection(plus_exigeant[plus_exigeant["prix_juste"].notna()].index)
    assert (plus_exigeant.loc[commun, "prix_juste"] < evaluees.loc[commun, "prix_juste"]).all()


def test_reglages_retenus(tmp_path, monkeypatch):
    monkeypatch.setattr(pa, "REGLAGES_JSON", tmp_path / "prix_achat.json")
    strategie = load_strategy()
    assert pa.reglages(strategie) == {"rendement": strategie["valorisation"]["taux_actualisation"], "marge": 0.2}
    pa.enregistrer_reglages(0.1, 0.25)
    assert pa.reglages(strategie) == {"rendement": 0.1, "marge": 0.25}
