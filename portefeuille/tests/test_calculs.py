"""Tests des calculs sensibles : valorisation, change, poids, backtest, suivi (PRU, TRI), filtres."""
import math
import warnings

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")

from pf import backtest as bt  # noqa: E402
from pf import criteres, indices, postes, regards, sante, sec, tracker, ui  # noqa: E402
from pf import data as pf_data  # noqa: E402
from pf import moat as pf_moat  # noqa: E402
from pf import portfolio as pfo  # noqa: E402
from pf.data import fx_rate, prices_in_eur, split_currency  # noqa: E402
from pf.metrics import historical_multiple  # noqa: E402
from pf.scoring import POIDS_GARP, build_screener, exclusion_reasons, note_garp, pillar_scores  # noqa: E402
from pf.valuation import implied_growth, implied_irr, value_driver_ev  # noqa: E402

FILTRES = {"rentabilite_min": 0.08, "couverture_interets_min": 3.0, "dette_nette_ebitda_max": 3.5,
           "dilution_max_par_an": 0.03, "marge_brute_min": 0.15, "exemption_marge_brute_roic": 0.2,
           "exiger_fcf_cumule_positif": True, "exiger_benefice_positif": True,
           "exemptions_dilution": {"FUSION": "fusion payée en actions"}}


# ------------------------------------------------------------------ valorisation

def test_value_driver_croissance_nulle_egale_rente_perpetuelle():
    # g = 0 partout : la valeur vaut NOPAT / r (aucun réinvestissement nécessaire).
    ev = value_driver_ev(100.0, 0.0, 0.10, g_term=0.0, roic=0.2)
    assert ev == pytest.approx(1000.0, rel=1e-9)


def test_croissance_implicite_et_tri_sont_les_inverses_du_modele():
    ev = value_driver_ev(100.0, 0.12, 0.09, g_term=0.03, roic=0.25)
    assert implied_growth(ev, 100.0, r=0.09, g_term=0.03, roic=0.25) == pytest.approx(0.12, abs=1e-4)
    assert implied_irr(ev, 100.0, 0.12, g_term=0.03, roic=0.25) == pytest.approx(0.09, abs=1e-4)


def test_croissance_sans_rentabilite_ne_cree_pas_de_valeur():
    # ROIC = rendement exigé : la valeur vaut NOPAT_1 / r, quelle que soit la croissance ultérieure
    # (la croissance de l'année 1 est financée par les investissements déjà faits).
    for g in (0.02, 0.15, 0.30):
        assert value_driver_ev(100.0, g, 0.10, g_term=0.02, roic=0.10) == pytest.approx(100 * (1 + g) / 0.10, rel=1e-9)


def test_la_croissance_cree_de_la_valeur_seulement_si_roic_superieur():
    rentable = [value_driver_ev(100.0, g, 0.09, roic=0.30) for g in (0.05, 0.15)]
    peu_rentable = [value_driver_ev(100.0, g, 0.09, roic=0.06) for g in (0.05, 0.15)]
    assert rentable[1] > rentable[0]
    assert peu_rentable[1] / 1.15 < peu_rentable[0] / 1.05  # hors effet de l'année 1, la croissance détruit


def test_valorisation_inapplicable_si_pertes():
    assert math.isnan(implied_growth(1000.0, -5.0))
    assert math.isnan(implied_irr(1000.0, -5.0, 0.1))


# ------------------------------------------------------------------ devises

FX = pd.DataFrame({"USD": [1.10, 1.20], "GBP": [0.85, 0.80], "EUR": [1.0, 1.0]},
                  index=pd.to_datetime(["2026-01-02", "2026-01-05"]))


def test_pence_et_conversion():
    assert split_currency("GBp") == ("GBP", 0.01)
    assert fx_rate(FX, "GBp", "EUR") == pytest.approx(0.01 / 0.80)
    assert fx_rate(FX, "USD", "EUR", "2026-01-02") == pytest.approx(1 / 1.10)
    assert fx_rate(FX, "USD", "GBP") == pytest.approx(0.80 / 1.20)


def test_cours_en_euros_au_taux_du_jour():
    prices = pd.DataFrame({"AAA": [110.0, 120.0], "BBB.L": [1000.0, 1000.0]}, index=FX.index)
    eur = prices_in_eur(prices, {"AAA": "USD", "BBB.L": "GBp"}, FX)
    assert eur["AAA"].tolist() == pytest.approx([100.0, 100.0])
    assert eur["BBB.L"].tolist() == pytest.approx([10 / 0.85, 10 / 0.80])


# ------------------------------------------------------------------ poids

def test_bornes_des_poids():
    w = pfo._cap_weights(pd.Series([10.0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]), 0.02, 0.15)
    assert w.sum() == pytest.approx(1.0)
    assert w.max() <= 0.15 + 1e-9 and w.min() >= 0.02 - 1e-9


def test_plafond_sectoriel():
    w = pd.Series(1 / 6, index=list("abcdef"))
    sectors = pd.Series(["Tech", "Tech", "Tech", "Santé", "Banque", "Luxe"], index=w.index)
    out = pfo._cap_sectors(w, sectors, cap=0.30, w_max=0.4)
    assert out.groupby(sectors).sum()["Tech"] <= 0.30 + 1e-6
    assert out.sum() == pytest.approx(1.0)


# ------------------------------------------------------------------ backtest

def _synthetic_prices(days=300):
    idx = pd.bdate_range("2020-01-01", periods=days)
    a = pd.Series(100 * 1.001 ** np.arange(days), index=idx)
    b = pd.Series(50 * 1.002 ** np.arange(days), index=idx)
    return pd.DataFrame({"A": a, "B": b})


def test_reequilibrage_sans_journee_perdue():
    # Deux actifs à croissance constante : avec ou sans rééquilibrage, aucune séance ne doit disparaître.
    px = _synthetic_prices()
    w = pd.Series({"A": 0.5, "B": 0.5})
    hold = bt.run_backtest(w, px.index[0], rebalance=None, cost_bps=0, prices=px)["valeur"]
    reb = bt.run_backtest(w, px.index[0], rebalance="QS", cost_bps=0, prices=px)["valeur"]
    n = len(px) - 1
    assert hold.iloc[-1] == pytest.approx(50 * 1.001 ** n + 50 * 1.002 ** n, rel=1e-9)
    assert len(reb) == len(px) and reb.index.is_unique
    # Rééquilibrer vers 50/50 un actif qui monte plus vite coûte un peu de performance, jamais une séance.
    assert 100 * 1.001 ** n < reb.iloc[-1] < hold.iloc[-1]


def test_statistiques_de_performance():
    idx = pd.bdate_range("2020-01-01", periods=600)
    s = pd.Series(100 * (1.10 ** ((idx - idx[0]).days / 365.25)), index=idx)
    stats = bt.perf_stats(s)
    assert stats["Rendement annualisé"] == pytest.approx(0.10, abs=1e-3)
    assert stats["Perte maximale"] == pytest.approx(0.0, abs=1e-12)


# ------------------------------------------------------------------ suivi

@pytest.fixture
def journal(tmp_path, monkeypatch):
    idx = pd.bdate_range("2025-01-01", "2025-12-31")
    prices = pd.DataFrame({"AAA.PA": 10.0, "USX": 20.0}, index=idx)
    fx = pd.DataFrame({"USD": 1.25, "EUR": 1.0}, index=idx)
    monkeypatch.setattr(tracker, "TRANSACTIONS_CSV", tmp_path / "transactions.csv")
    monkeypatch.setattr(tracker, "load_prices", lambda: prices)
    monkeypatch.setattr(tracker, "load_fx", lambda: fx)
    monkeypatch.setattr(tracker, "currency_map", lambda ts: {"AAA.PA": "EUR", "USX": "USD"})
    (tmp_path / "transactions.csv").write_text(
        "date;compte;type;ticker;quantite;prix_unitaire;devise;frais_eur;montant_eur;taux_change;note\n"
        "2025-01-02;PEA;VERSEMENT;;;;;;1000;;\n"
        "2025-01-03;PEA;ACHAT;AAA.PA;50;8;EUR;2;;;\n"
        "2025-03-03;PEA;ACHAT;AAA.PA;50;12;EUR;2;;;\n"
        "2025-06-02;PEA;VENTE;AAA.PA;40;11;EUR;2;;;\n"
        "2025-07-01;CTO;ACHAT;USX;10;25;USD;0;;;\n"
        "2025-08-01;CTO;DIVIDENDE;USX;;;;;4,5;;\n",
        encoding="utf-8-sig")
    return tracker.load_transactions()


def test_pru_au_prix_moyen_pondere_et_plus_value(journal):
    pos = tracker.positions(journal).set_index("ticker")
    pru = (50 * 8 + 2 + 50 * 12 + 2) / 100  # 10,04 € frais inclus
    assert pos.loc["AAA.PA", "quantite"] == pytest.approx(60)
    assert pos.loc["AAA.PA", "pru_eur"] == pytest.approx(pru)
    assert pos.loc["AAA.PA", "pv_realisee_eur"] == pytest.approx(40 * 11 - 2 - 40 * pru)
    assert pos.loc["USX", "pru_eur"] == pytest.approx(25 / 1.25)  # 25 $ à 1,25 $/€
    assert pos.loc["USX", "dividendes_eur"] == pytest.approx(4.5)  # virgule décimale acceptée


def test_apports_implicites_quand_les_especes_manquent(journal):
    h = tracker.history(journal)
    # PEA : 1000 versés, 402 puis 602 achetés -> 4 € apportés implicitement ; CTO : 200 € implicites.
    assert h["apports_cumules"].iloc[-1] == pytest.approx(1000 + 4 + 200)
    especes = 438 + 4.5  # produit de la vente + dividende
    assert h["especes"].iloc[-1] == pytest.approx(especes)
    assert h["valeur_totale"].iloc[-1] == pytest.approx(60 * 10 + 10 * 20 / 1.25 + especes)



def test_reprise_au_pru_du_courtier_sans_performance_fictive(tmp_path, monkeypatch, journal):
    # Ligne déjà détenue : coût du courtier (800 €) mais valeur de marché 10 € x 100 = 1 000 € le jour de la reprise.
    (tmp_path / "transactions.csv").write_text(
        "date;compte;type;ticker;quantite;prix_unitaire;devise;frais_eur;montant_eur;taux_change;note\n"
        "2025-06-02;CTO;REPRISE;AAA.PA;100;8;EUR;;800;;\n", encoding="utf-8-sig")
    tx = tracker.load_transactions()
    pos = tracker.positions(tx).set_index("ticker")
    assert pos.loc["AAA.PA", "pru_eur"] == pytest.approx(8)
    assert pos.loc["AAA.PA", "pv_latente_eur"] == pytest.approx(200)
    h = tracker.history(tx)
    assert h["apports_cumules"].iloc[-1] == pytest.approx(1000)  # entre à sa valeur de marché
    assert h["especes"].iloc[-1] == pytest.approx(0)
    assert tracker.twr(h).iloc[-1] == pytest.approx(100)  # les 200 € de plus-value passée ne sont pas une performance

def test_tri_annualise():
    d0, d1 = pd.Timestamp("2024-01-01"), pd.Timestamp("2025-01-01")
    assert tracker.xirr([d0, d1], [-100, 110]) == pytest.approx(0.10, abs=2e-3)


def test_plan_apport_sans_vente_et_valeur_chere_differee():
    targets = pd.Series({"CHERE": 0.2, "A": 0.4, "B": 0.4})
    env = pd.Series("PEA", index=targets.index)
    prices = pd.Series({"CHERE": 1500.0, "A": 50.0, "B": 20.0})
    plan = tracker.contribution_plan(1000, "PEA", targets, env, pos=pd.DataFrame(), min_order=300, prices_eur=prices)
    assert plan["montant_eur"].sum() <= 1000 + 1e-9
    assert "CHERE" not in set(plan["ticker"])  # 1 500 € pour un besoin de 200 € : attend
    assert (plan["montant_eur"] >= 150).all()
    big = tracker.contribution_plan(10_000, "PEA", targets, env, pos=pd.DataFrame(), min_order=300, prices_eur=prices)
    assert "CHERE" in set(big["ticker"])


# ------------------------------------------------------------------ filtres et scores

def _row(**kw):
    base = {"financiere": False, "rentabilite": 0.20, "rentabilite_derniere": 0.20, "marge_brute": 0.5,
            "ocf_positif_2a": True, "fcf_cumule": 1e9, "couverture_interets": 20, "dette_nette_ebitda": 1.0,
            "evolution_actions": 0.0, "benefice_ttm": 1e8}
    base.update(kw)
    return pd.Series(base)


def test_filtres_exclusion_et_derogations():
    assert exclusion_reasons("X", _row(), FILTRES) == []
    assert any("Rentabilité" in m for m in exclusion_reasons("X", _row(rentabilite=0.04, rentabilite_derniere=0.05), FILTRES))
    # Devenue rentable : moyenne faible mais dernière année solide, marge brute > 30 %, cash positif.
    assert exclusion_reasons("X", _row(rentabilite=0.04, rentabilite_derniere=0.15), FILTRES) == []
    assert any("Dilution" in m for m in exclusion_reasons("X", _row(evolution_actions=0.08), FILTRES))
    assert exclusion_reasons("FUSION", _row(evolution_actions=0.08), FILTRES) == []
    # Rotation du capital élevée : marge brute faible tolérée si ROIC > 20 %.
    assert exclusion_reasons("X", _row(marge_brute=0.12, rentabilite=0.25), FILTRES) == []
    # Financières : pas de filtre de dette ni de couverture des intérêts.
    assert exclusion_reasons("X", _row(financiere=True, dette_nette_ebitda=9, couverture_interets=0.5), FILTRES) == []


def test_financieres_classees_entre_elles_sur_la_valorisation():
    df = pd.DataFrame({
        "financiere": [True, True, False, False],
        "rendement_benefices": [0.12, 0.08, 0.04, 0.02],
    }, index=["ASSUREUR_CHER", "ASSUREUR", "INDUS", "INDUS2"])
    df.loc["ASSUREUR_CHER", "rendement_benefices"] = 0.06
    s = pillar_scores(df)["valorisation"]
    assert s["ASSUREUR"] == pytest.approx(100) and s["INDUS"] == pytest.approx(100)


def test_fonds_hors_classement_et_booleens_a_trous():
    strat = {"filtres": FILTRES}
    rows = {t: _row(rentabilite=r, marge_brute=0.5) for t, r in (("A", 0.30), ("B", 0.20), ("C", 0.10))}
    df = pd.DataFrame(rows).T
    df.loc["ETF"] = np.nan
    df["fonds"] = pd.array([pd.NA, pd.NA, pd.NA, True], dtype="boolean")
    df["financiere"] = pd.array([False, False, False, pd.NA], dtype="boolean")  # relu du cache avec un trou
    df["statut_donnees"] = "ok"
    sc = build_screener(df, strat)
    assert sc.loc["ETF", "statut"] == "Fonds" and pd.isna(sc.loc["ETF", "rang"])
    assert sc.loc["A", "rang"] == 1 and sc.loc["C", "rang"] == 3
    assert sc.loc["A", "qualite"] > sc.loc["B", "qualite"] > sc.loc["C", "qualite"]
    assert pd.isna(sc.loc["ETF", "buffett"]) and sc.loc["A", "buffett"] >= 1  # notes pour les actions, pas pour les fonds


# ------------------------------------------------------------------ données

def test_une_paire_refusee_par_yahoo_n_efface_pas_son_historique(tmp_path, monkeypatch):
    idx = pd.bdate_range("2026-01-01", periods=10)
    monkeypatch.setattr(pf_data, "FX_PARQUET", tmp_path / "fx.parquet")
    monkeypatch.setattr(pf_data.time, "sleep", lambda s: None)
    pd.DataFrame({"GBP": 0.85, "USD": 1.10, "EUR": 1.0}, index=idx).to_parquet(tmp_path / "fx.parquet")
    new = idx.append(pd.bdate_range(idx[-1] + pd.Timedelta(days=1), periods=2))

    def download(tickers, start):
        cols = [t for t in tickers if t != "EURGBP=X"]  # Yahoo ne renvoie jamais la livre
        return pd.DataFrame({t: 1.12 for t in cols}, index=new) if cols else pd.DataFrame()

    monkeypatch.setattr(pf_data, "_download_close", download)
    monkeypatch.setattr(pf_data, "CONTROLES_JSON", tmp_path / "controles.json")
    monkeypatch.setattr(pf_data, "fetch_ecb_fx", lambda cur, start="": pd.DataFrame())  # BCE injoignable
    fx = pf_data.update_fx({"USD", "GBP"})
    assert fx["GBP"].notna().all() and fx["GBP"].iloc[-1] == pytest.approx(0.85)
    assert fx["USD"].iloc[-1] == pytest.approx(1.12)
    assert pf_data.load_controles()["change"]["resultat"]["source"].startswith("Yahoo")

    # BCE joignable : ses cours priment, Yahoo ne comble que la devise qu'elle ne publie pas.
    monkeypatch.setattr(pf_data, "fetch_ecb_fx", lambda cur, start="": pd.DataFrame({"USD": 1.15}, index=new))
    pd.DataFrame({"GBP": 0.85, "USD": 1.10, "EUR": 1.0}, index=idx).to_parquet(tmp_path / "fx.parquet")
    fx = pf_data.update_fx({"USD", "GBP", "TWD"})
    assert fx["USD"].iloc[-1] == pytest.approx(1.15) and fx["TWD"].iloc[-1] == pytest.approx(1.12)
    ctl = pf_data.load_controles()["change"]["resultat"]
    assert ctl["source"] == "BCE" and ctl["absentes_bce"] == ["CHF", "GBP", "TWD"]  # CHF est toujours demandé


def test_conversion_des_tickers_ishares_vers_yahoo():
    assert indices.to_yahoo("BRKB", "New York Stock Exchange Inc.") == "BRK-B"
    assert indices.to_yahoo("BP.", "London Stock Exchange") == "BP.L"
    assert indices.to_yahoo("BT/A", "London Stock Exchange") == "BT-A.L"
    assert indices.to_yahoo("VOLV B", "Nasdaq Omx Nordic") == "VOLV-B.ST"
    assert indices.to_yahoo("-", "Nasdaq Omx Helsinki Ltd.") == "UPM.HE"
    assert indices.to_yahoo("XXX", "NO MARKET (E.G. UNLISTED)") is None


def test_renouvellement_par_roulement_lignes_detenues_d_abord(tmp_path, monkeypatch):
    ages = {"VIEILLE": 90.0, "RECENTE": 2.0, "MOYENNE": 30.0, "DETENUE": 8.0, "ABSENTE": None}
    monkeypatch.setattr(pf_data, "FUND_DIR", tmp_path)
    monkeypatch.setattr(pf_data, "fundamentals_age_days", ages.get)
    monkeypatch.setattr(pf_data, "fundamentals_path", lambda t: tmp_path / f"{t}.json")
    monkeypatch.setattr(pf_data, "fetch_fundamentals", lambda t: {"ticker": t})
    res = pf_data.update_fundamentals(list(ages), max_refresh=3, priority={"DETENUE"})
    assert set(res["ok"]) == {"DETENUE", "ABSENTE", "VIEILLE"}  # RECENTE n'a pas 7 jours, MOYENNE attendra


# ------------------------------------------------------------------ quatre regards

def test_regards_recompensent_la_qualite_et_penalisent_la_fragilite():
    solide = pd.Series({"financiere": False, "rentabilite": 0.35, "tri_implicite": 0.15, "croissance_attendue": 0.17,
                        "evolution_actions": -0.03, "conversion_fcf": 1.2, "rendement_fcf": 0.06, "marge_operationnelle": 0.3,
                        "stabilite_marge": 0.01, "volatilite": 0.25, "drawdown_max_3a": -0.2, "perf_12m": 0.1})
    assert regards.base_notes(solide) == {"buffett": 5, "munger": 5, "fisher": 5, "smith": 5}
    pic = solide.copy()
    pic[["volatilite", "drawdown_max_3a", "stabilite_marge", "perf_12m"]] = [0.8, -0.6, 0.4, 2.5]
    assert regards.base_notes(pic)["munger"] == 1
    banque = solide.copy()
    banque["financiere"] = True
    assert regards.base_notes(banque)["smith"] <= 3


def test_regards_donnee_absente_sans_point_et_correction_bornee(tmp_path, monkeypatch):
    vide = pd.Series({"financiere": False})
    assert regards.base_notes(vide) == {"buffett": 1, "munger": 5, "fisher": 1, "smith": 1}
    path = tmp_path / "ajustements.csv"
    path.write_text("ticker;buffett;munger;fisher;smith;motif\nA;-9;;2;;essai\n", encoding="utf-8-sig")
    monkeypatch.setattr(regards, "AJUSTEMENTS_CSV", path)
    sc = pd.DataFrame({"statut": "Éligible", "rang": [1.0], "nom": ["A"], "score": [80.0], "rentabilite": [0.35]}, index=["A"])
    r = regards.compute_regards(sc).loc["A"]
    assert r["buffett"] == 1 and r["fisher"] == 3 and r["correction"] == "essai"


def test_la_version_du_cache_suit_les_fichiers(tmp_path):
    import os
    fichier = tmp_path / "strategie.json"
    fichier.write_text("{}", encoding="utf-8")
    os.utime(fichier, (1000, 1000))
    avant = ui.data_version([fichier, tmp_path / "absent.csv"])
    os.utime(fichier, (2000, 2000))
    assert avant == 1000 and ui.data_version([fichier, tmp_path / "absent.csv"]) == 2000


# ------------------------------------------------------------------ signaux de santé

def _exercice(**kw):
    base = dict.fromkeys(sante.LIGNES, 100.0)
    base.update(assets=1000.0, revenue=500.0, gross_profit=250.0, net_income=50.0, ocf=50.0, current_assets=300.0,
                current_liabilities=150.0, long_term_debt=200.0, ppe=200.0, depreciation=20.0, sga=100.0, shares=100.0)
    base.update(kw)
    return pd.Series(base)


def test_beneish_exercices_identiques_donne_la_constante():
    # Tous les indices valent 1 et les charges à payer 0 : -4,84 + 0,92 + 0,528 + 0,404 + 0,892 + 0,115 - 0,172 - 0,327.
    a = _exercice()
    assert sante.beneish(a, a) == pytest.approx(-2.48)
    sans_frais = _exercice(sga=math.nan)
    assert sante.beneish(sans_frais, sans_frais) == pytest.approx(-2.48)  # indice neutralisé
    # Un chiffre d'affaires multiplié par 100 compte comme un indice de 5, pas de 100.
    assert sante.beneish(_exercice(revenue=50000.0, gross_profit=25000.0, receivables=10000.0, sga=10000.0), a) == pytest.approx(
        sante.beneish(_exercice(revenue=2500.0, gross_profit=1250.0, receivables=500.0, sga=500.0), a))


def test_altman_formule_d_origine():
    a = _exercice(assets=100.0, current_assets=50.0, current_liabilities=30.0, retained=30.0, ebit=10.0, liabilities=50.0, revenue=150.0)
    assert sante.altman(a, market_cap=200.0) == pytest.approx(0.24 + 0.42 + 0.33 + 2.4 + 1.5)


def test_piotroski_de_zero_a_neuf_et_donnees_manquantes():
    prev = _exercice()
    bon = _exercice(net_income=80.0, ocf=120.0, long_term_debt=150.0, current_assets=400.0, shares=98.0,
                    gross_profit=330.0, revenue=600.0)
    assert sante.piotroski(bon, prev) == 9
    mauvais = _exercice(net_income=-80.0, ocf=-120.0, long_term_debt=300.0, current_assets=200.0, shares=120.0,
                        gross_profit=150.0, revenue=400.0)
    assert sante.piotroski(mauvais, prev) == 0
    assert sante.piotroski(_exercice(gross_profit=math.nan, net_income=80.0, ocf=120.0), prev) >= 0  # un critère manquant : calculé
    trous = _exercice(gross_profit=math.nan, shares=math.nan)
    assert math.isnan(sante.piotroski(trous, prev))  # deux critères manquants : non noté


def test_signaux_absents_pour_les_financieres_et_alertes_seuils():
    res = sante.health_scores({"income": {}}, 1e9, financial=True)
    assert all(math.isnan(v) for v in res.values())
    assert sante.health_alerts(pd.Series({"piotroski": 2.0, "altman_z": 1.0, "beneish_m": -1.0})) != []
    assert len(sante.health_alerts(pd.Series({"piotroski": 2.0, "altman_z": 1.0, "beneish_m": -1.0}))) == 3
    assert sante.health_alerts(pd.Series({"piotroski": 8.0, "altman_z": 4.0, "beneish_m": -2.5})) == []
    assert sante.health_alerts(pd.Series(dtype=float)) == []


# ------------------------------------------------------------------ note GARP

def test_la_note_garp_pese_croissance_valorisation_qualite():
    df = pd.DataFrame({"croissance": [100.0, 0.0, 50.0], "valorisation": [0.0, 100.0, 50.0],
                       "qualite": [0.0, 0.0, 100.0], "momentum": [100.0, 0.0, 0.0]}, index=["CROIT", "PAS_CHER", "QUALITE"])
    n = note_garp(df)
    assert n["CROIT"] == pytest.approx(40) and n["PAS_CHER"] == pytest.approx(35)
    assert n["QUALITE"] == pytest.approx(50 * 0.40 + 50 * 0.35 + 100 * 0.25)
    assert sum(POIDS_GARP.values()) == pytest.approx(1)


def test_la_note_garp_ignore_regards_criteres_sante_et_momentum():
    """Repères, hors note : changer les regards, les critères, les signaux de santé ou le momentum ne change rien."""
    sc = build_screener()
    actions = sc[sc["statut"] != "Fonds"]
    attendu = (actions["croissance"] * 0.40 + actions["valorisation"] * 0.35 + actions["qualite"] * 0.25)
    assert np.allclose(actions["score"], attendu)
    autre = actions.assign(buffett=1, munger=1, fisher=1, smith=1, criteres_ok=0, piotroski=0, momentum=0)
    assert np.allclose(note_garp(autre), actions["score"])
    elig = sc[sc["statut"] == "Éligible"]
    assert list(elig.sort_values("score", ascending=False).index) == list(elig.sort_values("rang").index)


def test_altman_et_beneish_sont_des_jauges():
    df = pd.DataFrame({"altman_z": [1.0, 2.4, 3.0, 50.0], "beneish_m": [-1.0, -2.0, -2.22, -5.0]})
    p = sante.health_points(df)
    assert list(p["pts_altman"].round()) == [0, 50, 100, 100]  # au-delà de la zone sûre, rien de plus
    assert list(p["pts_beneish"].round()) == [0, 50, 100, 100]


# ------------------------------------------------------------------ moat et PER historique

def test_moat_estime_recompense_la_duree_pas_le_pic():
    stable = pd.Series([0.30, 0.31, 0.29, 0.30])
    gm, om = pd.Series([0.70, 0.71, 0.70, 0.71]), pd.Series([0.35, 0.35, 0.36, 0.35])
    assert pf_moat.moat_points(stable, gm, om) == 6 and pf_moat.moat_label(6.0) == "Large"
    pic = pd.Series([-0.05, 0.02, 0.10, 0.90])  # moyenne élevée sur une seule année
    marges = pd.Series([0.20, 0.25, 0.30, 0.80])
    assert pf_moat.moat_label(pf_moat.moat_points(pic, marges, marges - 0.1)) == "Faible"
    erosion = pd.Series([0.40, 0.30, 0.20, 0.13])
    assert pf_moat.moat_points(erosion, gm, om) == 5  # seule l'érosion du ROIC manque


def test_moat_estime_donnees_courtes_ou_manquantes():
    vide = pd.Series(dtype=float)
    assert math.isnan(pf_moat.moat_points(pd.Series([0.3, 0.3]), vide, vide))  # moins de 3 exercices
    assert pf_moat.moat_label(math.nan) is None
    # Sans marge brute, 4 critères restent : la note est ramenée sur 6.
    assert pf_moat.moat_points(pd.Series([0.3, 0.3, 0.3]), vide, pd.Series([0.2, 0.2, 0.2])) == 6


def test_per_historique_median_et_multi_classes():
    idx = pd.to_datetime(["2023-12-31", "2024-12-31", "2025-12-31"])
    a = pd.DataFrame({"shares": [10.0, 10.0, 10.0], "net_income": [10.0, 10.0, 10.0]}, index=idx)
    px = pd.Series([20.0, 30.0, 40.0, 25.0], index=[*idx, pd.Timestamp("2026-06-30")])
    fx = pd.DataFrame({"EUR": 1.0}, index=idx)
    # Capitalisation actuelle double de cours x actions (autre classe) : k = 2, PER de 40, 60 et 80.
    assert historical_multiple(a, px, 500.0, fx, "EUR", "EUR") == pytest.approx(60)
    assert math.isnan(historical_multiple(a.assign(net_income=-1.0), px, 500.0, fx, "EUR", "EUR"))
    # Même calcul sur le flux de trésorerie disponible : deux fois plus de FCF, multiple deux fois plus bas.
    assert historical_multiple(a.assign(fcf=20.0), px, 500.0, fx, "EUR", "EUR", col="fcf") == pytest.approx(30)


def test_change_bce_recoupe_avec_yahoo():
    idx = pd.bdate_range("2026-08-03", periods=40)
    ref = pd.DataFrame({"USD": 1.10, "GBP": 0.85}, index=idx)
    autre = pd.DataFrame({"USD": 1.10 * 1.002, "GBP": 0.85}, index=idx)
    autre.iloc[5, 1] = 0.95  # un point aberrant isolé ne doit pas peser sur l'écart médian
    ecarts = pf_data.fx_crosscheck(ref, autre)
    assert ecarts["USD"] == pytest.approx(0.002) and ecarts["GBP"] == pytest.approx(0.0)


def _faits(concept, valeurs, debut=True):
    return [{"start": f"{a - 1}-01-01" if debut else None, "end": f"{a - 1}-12-31", "val": v, "form": "10-K", "fy": a}
            for a, v in valeurs]


def test_sec_extraction_garde_les_exercices_annuels():
    facts = {"entityName": "Exemple", "facts": {"us-gaap": {
        "Revenues": {"units": {"USD": _faits("Revenues", [(2025, 100.0), (2026, 120.0)])
                               + [{"start": "2025-10-01", "end": "2025-12-31", "val": 30.0, "form": "10-K"}]}},
        "Assets": {"units": {"USD": [{"end": "2025-12-31", "val": 500.0, "form": "10-K"},
                                     {"end": "2025-12-31", "val": 510.0, "form": "10-K/A"}]}},
    }}}
    out = sec.extract(facts)
    assert out["devise"] == "USD"
    assert out["postes"]["revenue"] == {"2024-12-31": [100.0], "2025-12-31": [120.0]}  # le trimestre est écarté
    assert out["postes"]["assets"]["2025-12-31"] == [500.0, 510.0]  # chiffre initial et chiffre retraité


def test_sec_recoupement_confirme_ou_signale_un_ecart():
    fund = {"info": {"financialCurrency": "USD"},
            "income": {"Total Revenue": {"2025-12-31": 120.0}, "Net Income": {"2025-12-31": 20.0}},
            "cashflow": {"Operating Cash Flow": {"2025-12-31": 30.0}, "Capital Expenditure": {"2025-12-31": -10.0}},
            "balance": {"Total Assets": {"2025-12-31": 510.0}}}
    postes = {"revenue": {"2025-12-31": [120.0]}, "net_income": {"2025-12-31": [20.0]}, "ocf": {"2025-12-31": [30.0]},
              "capex": {"2025-12-31": [7.0]}, "assets": {"2025-12-31": [500.0, 510.0]}}
    ok = sec.recoupement(fund, {"devise": "USD", "postes": postes})
    # Investissements à +43 % : visibles dans la fiche, mais hors verdict (périmètre différent chez Yahoo).
    assert ok["verif_sec"] == "Confirmé" and ok["sec_postes"] == 4 and ok["sec_ecarts"] == ""
    faux = sec.recoupement(fund, {"devise": "USD", "postes": {**postes, "revenue": {"2025-12-31": [100.0]}}})
    assert faux["verif_sec"] == "Écart" and faux["sec_ecart_max"] == pytest.approx(0.20)
    retard = sec.recoupement(fund, {"devise": "USD", "postes": {**postes, "revenue": {"2025-12-31": [120.0], "2026-12-31": [130.0]}}})
    assert retard["sec_retard"] is True
    assert sec.recoupement(fund, {"devise": "EUR", "postes": postes})["verif_sec"] == "Non comparable"
    assert sec.recoupement(fund, None)["verif_sec"] is None
    # Banque : revenus sans définition commune, l'écart de CA est montré dans la fiche mais hors verdict.
    banque = sec.recoupement(fund, {"devise": "USD", "postes": {**postes, "revenue": {"2025-12-31": [20.0]}}}, sans_ca=True)
    assert banque["verif_sec"] == "Confirmé" and "CA" not in banque["sec_ecarts"]
    # SEC sans le dernier exercice de Yahoo : comparaison sur l'exercice précédent, commun aux deux.
    fund2 = {**fund, "income": {"Total Revenue": {"2025-12-31": 120.0, "2026-12-31": 150.0},
                                "Net Income": {"2025-12-31": 20.0, "2026-12-31": 25.0}}}
    assert sec.exercice_commun(fund2, {"postes": postes}) == "2025-12-31"
    assert sec.recoupement(fund2, {"devise": "USD", "postes": postes})["verif_sec"] == "Confirmé"


def _fiche_criteres():
    ans = ["2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"]
    par_an = lambda *v: dict(zip(ans, v))  # noqa: E731
    return {
        "income": {"Total Revenue": par_an(130.0, 150.0, 170.0, 200.0), "Operating Income": par_an(26.0, 30.0, 34.0, 40.0),
                   "Diluted Average Shares": par_an(10.0, 9.8, 9.6, 9.5)},
        "cashflow": {"Operating Cash Flow": par_an(30.0, 35.0, 40.0, 45.0), "Capital Expenditure": par_an(-10.0, -10.0, -10.0, -10.0),
                     "Free Cash Flow": par_an(20.0, 25.0, 30.0, 35.0)},
        "balance": {"Total Assets": par_an(200.0, 200.0, 200.0, 200.0), "Current Liabilities": par_an(50.0, 50.0, 50.0, 50.0),
                    "Total Debt": par_an(70.0, 70.0, 70.0, 70.0), "Cash And Cash Equivalents": par_an(10.0, 10.0, 10.0, 10.0)},
        "balance_q": {"Total Debt": {"2026-06-30": 50.0, "2026-09-30": 60.0}, "Cash And Cash Equivalents": {"2026-09-30": 20.0}},
        "ttm_cashflow": {"Free Cash Flow": {"2026-09-30": 40.0}},
    }


SEC_CRITERES = {"series": {
    "revenue": {"Revenues": {"2020-12-31": 100.0, "2021-12-31": 115.0, "2022-12-31": 130.0, "2023-12-31": 150.0,
                             "2024-12-31": 170.0, "2025-12-31": 200.0}},
    "ocf": {"NetCash": {"2020-12-31": 22.0, "2021-12-31": 26.0, "2022-12-31": 30.0, "2023-12-31": 35.0,
                        "2024-12-31": 40.0, "2025-12-31": 45.0}},
    # La SEC compte les investissements en positif, Yahoo en négatif : le raccord aligne le signe.
    "capex": {"Payments": {"2020-12-31": 8.0, "2021-12-31": 9.0, "2022-12-31": 10.0, "2023-12-31": 10.0,
                           "2024-12-31": 10.0, "2025-12-31": 10.0}},
    "shares": {"Diluted": {"2020-12-31": 10.4, "2021-12-31": 10.2, "2022-12-31": 10.0, "2023-12-31": 9.8,
                           "2024-12-31": 9.6, "2025-12-31": 9.5}},
}}


def test_criteres_sur_cinq_ans_grace_a_la_sec():
    crits = {c.cle: c for c in criteres.evaluer(_fiche_criteres(), SEC_CRITERES)}
    assert crits["ca"].valeur == pytest.approx(2 ** (1 / 5) - 1, abs=1e-4) and crits["ca"].periode.endswith("5 dernières années")
    assert crits["fcf"].valeur == pytest.approx((35 / 14) ** (1 / 5) - 1, abs=1e-4)  # 2020 : 22 - 8 = 14
    assert crits["actions"].valeur == pytest.approx(9.5 / 10.4 - 1) and crits["actions"].rempli
    # Pas de résultat opérationnel à la SEC : le ROCE reste sur les 4 exercices Yahoo.
    assert crits["roce"].valeur == pytest.approx(130 / 600) and crits["roce"].periode == "en moyenne sur 4 ans"
    assert crits["marge"].valeur == pytest.approx(np.mean([17 / 115, 20 / 130, 25 / 150, 30 / 170, 35 / 200]))
    # Dette nette du dernier trimestre (60 - 20) sur le FCF des 12 derniers mois (40).
    assert crits["dette"].valeur == pytest.approx(1.0) and crits["dette"].periode == "au dernier trimestre"
    assert all(c.rempli for c in crits.values())
    assert criteres.resume(list(crits.values()))["criteres"] == "6/6"
    assert postes.historique(_fiche_criteres(), SEC_CRITERES)[1] is True
    assert postes.historique(_fiche_criteres(), {"series": {"shares": SEC_CRITERES["series"]["shares"]}})[1] is False


def test_criteres_division_d_action_coupe_le_prolongement():
    # Exercices 2022-2025 retraités après une division par 6 ; 2020 et 2021 restent en actions d'avant.
    sec_div = {"series": {"shares": {"Diluted": {"2020-12-31": 1.75, "2021-12-31": 1.72, "2022-12-31": 10.0,
                                                 "2023-12-31": 9.8, "2024-12-31": 9.6, "2025-12-31": 9.5}}}}
    actions = criteres.evaluer(_fiche_criteres(), sec_div)[4]
    assert actions.valeur == pytest.approx(9.5 / 10.0 - 1) and actions.periode.endswith("3 dernières années")


def test_criteres_sans_raccord_sec_restent_sur_trois_ans():
    decale = {"series": {"revenue": {"Revenues": {d: v * 1.05 for d, v in SEC_CRITERES["series"]["revenue"]["Revenues"].items()}}}}
    ca = criteres.evaluer(_fiche_criteres(), decale)[0]
    assert ca.periode.endswith("3 dernières années") and ca.valeur == pytest.approx((200 / 130) ** (1 / 3) - 1, abs=1e-3)
    s = pd.Series([-10.0, -12.0], index=pd.to_datetime(["2024-12-31", "2025-12-31"]))
    plus_long = postes.prolonger(s, {"Payments": {"2023-12-31": 9.0, "2024-12-31": 10.0, "2025-12-31": 12.0}})
    assert plus_long.iloc[0] == -9.0 and len(plus_long) == 3


def test_criteres_cas_limites():
    fiche = _fiche_criteres()
    fiche["cashflow"]["Free Cash Flow"]["2022-12-31"] = -5.0
    fcf = criteres.evaluer(fiche)[1]
    assert fcf.rempli is False and "négatif" in fcf.note
    banque = criteres.evaluer(_fiche_criteres(), financiere=True)
    assert [c.cle for c in banque if c.rempli is not None] == ["ca", "actions"]
    # Fonds des clients dans les flux (paiement, bourse) : pas de critère fondé sur le free cash flow.
    paiement = criteres.evaluer(_fiche_criteres(), tresorerie_clients=True)
    assert [c.cle for c in paiement if c.rempli is not None] == ["ca", "roce", "actions"]
    # Ligne de dette absente du dernier trimestre : on se place au trimestre où elle est connue.
    fiche = _fiche_criteres()
    fiche["balance_q"] = {"Total Debt": {"2026-06-30": 50.0}, "Cash And Cash Equivalents": {"2026-09-30": 20.0}}
    assert criteres.evaluer(fiche)[3].valeur == pytest.approx(50 / 40)
    # Flux négatif mais trésorerie nette : rempli, sans ratio.
    fiche["ttm_cashflow"] = {"Free Cash Flow": {"2026-09-30": -5.0}}
    fiche["balance_q"] = {"Total Debt": {"2026-09-30": 10.0}, "Cash And Cash Equivalents": {"2026-09-30": 30.0}}
    dette = criteres.evaluer(fiche)[3]
    assert dette.rempli is True and math.isnan(dette.valeur)


# ------------------------------------------------------------------ robustesse (audit du 04/11/2026)

def test_ecriture_atomique_garde_l_ancien_fichier_si_l_ecriture_echoue(tmp_path):
    from pf.config import ecrire_texte, ecriture_atomique, lire_json
    f = tmp_path / "journal.csv"
    ecrire_texte(f, "ancien")

    def coupure(p):
        p.write_text("début tronqué", encoding="utf-8")
        raise KeyboardInterrupt  # fenêtre fermée en pleine écriture

    with pytest.raises(KeyboardInterrupt):
        ecriture_atomique(f, coupure)
    assert f.read_text(encoding="utf-8") == "ancien" and list(tmp_path.iterdir()) == [f]
    (tmp_path / "casse.json").write_text('{"tronqué', encoding="utf-8")
    assert lire_json(tmp_path / "casse.json", {}) == {}


def test_section_refusee_par_yahoo_garde_sa_version_precedente(tmp_path, monkeypatch):
    monkeypatch.setattr(pf_data, "fundamentals_path", lambda t: tmp_path / f"{t}.json")
    complet = {"fetched": "2026-11-01T10:00:00", "info": {}, "income": {"Total Revenue": {"2025-12-31": 1.0}},
               "balance": {"Total Assets": {"2025-12-31": 2.0}}, "cashflow": {"Free Cash Flow": {"2025-12-31": 3.0}}}
    pf_data.save_fundamentals("CARR", dict(complet, manquantes=[]))
    a_trous = {**complet, "fetched": "2026-11-04T10:00:00", "balance": {}, "cashflow": {}, "manquantes": ["balance", "cashflow"]}
    pf_data.save_fundamentals("CARR", a_trous)
    relu = pf_data.load_fundamentals("CARR")
    assert relu["balance"] == complet["balance"] and relu["sections_reprises"] == ["balance", "cashflow"]
    assert pf_data.incomplete({"fetched": "x", "income": {"a": 1}, "balance": {}, "cashflow": {"b": 2}})
    (tmp_path / "ILLISIBLE.json").write_text("{", encoding="utf-8")
    assert pf_data.load_fundamentals("ILLISIBLE") is None  # retéléchargée, au lieu d'arrêter tout le calcul


def test_dette_inconnue_n_est_pas_une_dette_nulle():
    assert postes.dernier_bilan({"income": {"Total Revenue": {"2025-12-31": 1.0}}}) is None
    sans_ligne_de_dette = {"balance": {"Cash And Cash Equivalents": {"2025-12-31": 50.0}}}
    assert postes.dernier_bilan(sans_ligne_de_dette) == (0.0, 50.0, "au dernier exercice")
    assert exclusion_reasons("CARR", pd.Series({"rentabilite": math.nan, "financiere": False}), FILTRES)[0].startswith(
        "Données insuffisantes")


def _tx(*lignes):
    cols = ["date", "compte", "type", "ticker", "quantite", "prix_unitaire", "devise", "frais_eur", "montant_eur", "taux_change", "note"]
    return pd.DataFrame([dict(zip(cols, valeurs)) for valeurs in lignes])


def test_vente_ramenee_a_la_quantite_detenue():
    tx = _tx((pd.Timestamp("2026-01-05"), "CTO", "ACHAT", "ADBE", 10.0, 300.0, "USD", 2.0, 2600.0, math.nan, ""),
             (pd.Timestamp("2026-02-05"), "CTO", "VENTE", "ADBE", 15.0, 320.0, "USD", 3.0, 4200.0, math.nan, ""),
             (pd.Timestamp("2026-02-06"), "PEA", "VENTE", "ADBE", 1.0, 320.0, "USD", 0.0, 300.0, math.nan, ""))
    corrige, anomalies = tracker.controle_ventes(tx)
    assert corrige.loc[1, "quantite"] == 10 and corrige.loc[1, "montant_eur"] == pytest.approx(2800.0)
    assert len(anomalies) == 2 and "sans position" in anomalies[1]
    p = tracker.positions(tx)
    assert (p["quantite"] >= 0).all() and p["pv_realisee_eur"].sum() == pytest.approx(2800.0 - 2600.0)
    assert tracker.quantite_detenue(tx.iloc[:1], "CTO", "ADBE") == 10


def test_le_journal_est_copie_avant_chaque_ecriture(tmp_path, monkeypatch):
    monkeypatch.setattr(tracker, "TRANSACTIONS_CSV", tmp_path / "transactions.csv")
    monkeypatch.setattr(tracker, "SAUVEGARDES_DIR", tmp_path / "sauvegardes")
    ligne = {"date": pd.Timestamp("2026-11-04"), "compte": "CTO", "type": "VERSEMENT", "prix_unitaire": 100.0}
    tracker.append_transaction(ligne)  # premier enregistrement : rien à sauvegarder
    tracker.append_transaction(ligne)
    assert len(list((tmp_path / "sauvegardes").glob("transactions-*.csv"))) == 1


def test_rendement_court_non_annualise():
    idx = pd.bdate_range("2026-10-29", periods=5)
    hist = pd.DataFrame({"valeur_totale": [1000.0, 1002, 1004, 1006, 1008.2], "flux_externes": [1000.0, 0, 0, 0, 0]}, index=idx)
    rdt, annualise = tracker.rendement_argent(hist)
    assert not annualise and rdt == pytest.approx(0.0082, abs=1e-4)


def test_ordres_d_apport_deja_enregistres():
    tx = _tx((pd.Timestamp("2026-11-04"), "CTO", "ACHAT", "GOOGL", 1.0, 258.0, "USD", math.nan, 258.0, math.nan,
              "Apport du mois (prix de clôture)"))
    plan = pd.DataFrame({"ticker": ["GOOGL", "NUKL.DE"], "quantite": [1.0, 18.0]})
    assert tracker.ordres_deja_saisis(tx, plan, "CTO", "2026-11-04") == {"GOOGL"}
    assert tracker.ordres_deja_saisis(tx, plan, "CTO", "2026-11-05") == set()


def test_seuils_des_criteres_reappliques_sans_recalcul():
    df = pd.DataFrame({"crit_ca": [0.12, math.nan], "crit_ca_ok": pd.array([True, False], dtype="boolean")})
    for cle in ("fcf", "roce", "dette", "actions", "marge"):
        df[f"crit_{cle}"] = math.nan
        df[f"crit_{cle}_ok"] = pd.array([pd.NA, pd.NA], dtype="boolean")
    plus_dur = criteres.reappliquer(df, {"croissance_ca_min": 0.15})
    assert list(plus_dur["crit_ca_ok"]) == [False, False]  # 12 % < 15 % ; la seconde (flux négatif) garde son verdict
    assert list(plus_dur["criteres"]) == ["0/1", "0/1"]


def test_apport_ecarte_les_lignes_sorties_des_filtres():
    sc = pd.DataFrame({"statut": ["Éligible", "Exclu", "Éligible", "Fonds"],
                       "motifs_exclusion": ["", "Endettement élevé (4.0x l'EBITDA) ; Perte", "", ""],
                       "alertes": ["", "", "Tendance très négative (-45% sur 12 mois)", ""]}, index=["A", "B", "C", "ETF"])
    ecartees = pfo.lignes_a_ecarter(sc, ["A", "B", "C", "ETF"])
    assert set(ecartees) == {"B", "C"} and ecartees["B"] == "sortie des filtres : Endettement élevé (4.0x l'EBITDA)"
    w = pd.Series({"A": 0.3, "B": 0.7})
    assert pfo.compte_principal(w, pd.DataFrame({"enveloppe": ["PEA", "CTO"]}, index=["A", "B"])) == "CTO"


def test_watchlist_ajout_sans_doublon_et_retrait(tmp_path, monkeypatch):
    from pf import watchlist as wl
    monkeypatch.setattr(wl, "WATCHLIST_CSV", tmp_path / "watchlist.csv")
    assert wl.load_watchlist().empty
    wl.ajouter("DECK", 90.2)
    wl.ajouter("ZTS")
    wl.ajouter("DECK", 120.0)  # déjà suivie : date et cours d'ajout conservés
    liste = wl.load_watchlist()
    assert list(liste.index) == ["DECK", "ZTS"] and liste.loc["DECK", "cours_ajout"] == pytest.approx(90.2)
    wl.ajouter("MC.PA")
    assert wl.placer("MC.PA", 0) == 0 and list(wl.load_watchlist().index) == ["MC.PA", "DECK", "ZTS"]
    assert wl.placer("MC.PA", 99) == 2 and list(wl.load_watchlist().index) == ["DECK", "ZTS", "MC.PA"]
    assert wl.load_watchlist().loc["DECK", "cours_ajout"] == pytest.approx(90.2)  # le déplacement garde les données
    wl.retirer("DECK")
    assert not wl.contient("DECK") and wl.contient("ZTS")


def test_p_fcf_jour_par_jour():
    from pf.metrics import serie_multiple
    jours = pd.bdate_range("2024-01-01", "2026-10-30")
    px = pd.Series(10.0, index=jours)
    fx = pd.DataFrame({"EUR": 1.0}, index=jours)
    actions = pd.Series([100.0, 100.0], index=pd.to_datetime(["2023-12-31", "2024-12-31"]))
    fcf = pd.Series([50.0, 100.0], index=pd.to_datetime(["2023-12-31", "2024-12-31"]))
    s = serie_multiple(px, 1000.0, fx, "EUR", "EUR", actions, fcf, (pd.Timestamp("2026-09-30"), 125.0))
    assert s["2024-06-03"] == pytest.approx(20.0)  # exercice 2023 publié (clôture + 60 jours)
    assert s["2025-06-02"] == pytest.approx(10.0)  # exercice 2024
    assert s.iloc[-1] == pytest.approx(1000.0 / 125.0)  # dernier point : 12 mois glissants, comme le P/FCF actuel
    negatif = serie_multiple(px, 1000.0, fx, "EUR", "EUR", actions, fcf * -1, None)
    assert negatif.dropna().empty  # flux négatif : pas de multiple


def test_ventilation_du_chiffre_d_affaires_dans_un_10k():
    from pf import ventilation

    def ctx(i, dim=None, membre=None):
        seg = (f'<xbrli:segment><xbrldi:explicitMember dimension="{dim}">{membre}</xbrldi:explicitMember></xbrli:segment>'
               if dim else "")
        return (f'<xbrli:context id="{i}"><xbrli:entity>{seg}</xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01'
                f'</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>')

    def fait(i, v):
        return f'<ix:nonFraction name="us-gaap:Revenues" contextRef="{i}" scale="6" decimals="-6">{v}</ix:nonFraction>'

    p, g = "srt:ProductOrServiceAxis", "srt:StatementGeographicalAxis"
    doc = (ctx("t") + ctx("a", p, "x:CompanionAnimalMember") + ctx("b", p, "x:DogsAndCatsMember") + ctx("c", p, "x:HorsesMember")
           + ctx("d", p, "x:LivestockMember") + ctx("u", g, "country:US")
           + "<table>" + fait("a", "700") + fait("b", "650") + fait("c", "50") + fait("d", "250") + "</table>"
           + "<table>" + fait("u", "540") + "</table>" + fait("t", "1,000"))
    r = ventilation.analyser(doc, "2025-12-31")
    assert r["total"] == pytest.approx(1e9)
    # Le sous-total « Companion animal » (= chiens et chats + chevaux) est écarté ; les 5 % non ventilés deviennent « Autres ».
    assert r["activites"] == pytest.approx({"Dogs and Cats": 650e6, "Livestock": 250e6, "Horses": 50e6, "Autres": 50e6})
    assert r["geographie"] == pytest.approx({"États-Unis": 540e6, "International": 460e6})
    assert ventilation.libelle("aapl:IPhoneMember") == "IPhone"


def _fiche_prix_juste() -> dict:
    """Deux exercices et 12 mois glissants : CA 400 puis 500 puis 625, FCF 50 puis 100 puis 125, SBC 10, 20, 25."""
    ex = ["2023-12-31", "2024-12-31"]
    return {"income": {"Total Revenue": dict(zip(ex, [400.0, 500.0])), "Net Income": dict(zip(ex, [40.0, 50.0])),
                       "Diluted Average Shares": dict(zip(ex, [100.0, 100.0]))},
            "cashflow": {"Free Cash Flow": dict(zip(ex, [50.0, 100.0])),
                         "Stock Based Compensation": dict(zip(ex, [10.0, 20.0]))},
            "ttm_income": {"Total Revenue": {"2026-09-30": 625.0}},
            "ttm_cashflow": {"Free Cash Flow": {"2026-09-30": 125.0}, "Stock Based Compensation": {"2026-09-30": 25.0}}}


def test_prix_juste_series_des_ratios():
    from pf import prix_juste as pj
    jours = pd.bdate_range("2024-01-01", "2026-10-30")
    px, fx = pd.Series(10.0, index=jours), pd.DataFrame({"EUR": 1.0}, index=jours)
    fund = _fiche_prix_juste()
    h, _ = postes.historique(fund)

    def serie(ratio):
        return pj.serie(ratio, fund, h, px, 1000.0, fx, "EUR", "EUR")

    assert pj.actuel(serie("P/FCF")) == pytest.approx(1000 / 125)
    assert pj.actuel(serie("P/FCF hors SBC")) == pytest.approx(1000 / (125 - 25))
    assert pj.actuel(serie("P/CA")) == pytest.approx(1000 / 625)
    assert serie("P/CA")["2024-06-03"] == pytest.approx(1000 / 400)  # exercice 2023 publié
    assert serie("P/FCF hors SBC")["2025-06-02"] == pytest.approx(1000 / (100 - 20))  # exercice 2024, SBC retirées
    assert pj.ratios_pour(financiere=True, holding=False) == ["PER"]
    assert pj.ratios_pour(financiere=False, holding=True) == []
    assert "P/CA" in pj.ratios_pour(financiere=False, holding=False)


def test_prix_cible_proportionnel_au_multiple():
    from pf import prix_juste as pj
    assert pj.prix_cible(100.0, 25.0, 20.0) == pytest.approx(80.0)  # P/FCF 25 -> 20 : cours x 20 / 25
    assert pj.prix_cible(100.0, 25.0, 30.0) == pytest.approx(120.0)
    for actuel in (math.nan, -5.0, 0.0):  # flux négatif ou nul : pas de prix cible
        assert math.isnan(pj.prix_cible(100.0, actuel, 20.0))
    assert pj.ecart(80.0, 100.0) == pytest.approx(-0.2) and math.isnan(pj.ecart(80.0, math.nan))


def test_mediane_du_multiple_seulement_sur_un_historique_complet():
    from pf import prix_juste as pj
    jours = pd.bdate_range("2020-06-01", "2026-10-30")
    s = pd.Series(np.linspace(10.0, 30.0, len(jours)), index=jours)
    cinq_ans = s[s.index >= jours[-1] - pd.DateOffset(years=5)]
    assert pj.mediane(s, 5) == pytest.approx(cinq_ans.median())
    assert math.isnan(pj.mediane(s, 10))  # six ans d'historique : pas de médiane sur 10 ans
    presque = s[s.index >= "2021-12-15"]  # 4 ans et 10 mois : couverture à 5 % près, la médiane est donnée
    assert pj.mediane(presque, 5) == pytest.approx(presque.median())
    trou = s.copy()
    trou[trou.index < "2022-06-01"] = np.nan  # exercices en perte au début de la période : couverture incomplète
    assert math.isnan(pj.mediane(trou, 5)) and math.isnan(pj.mediane(pd.Series(dtype="float64"), 5))
    assert pj.mediane(trou) == pytest.approx(trou.dropna().median())  # tout l'historique disponible
    assert [lab for lab, _ in pj.reperes(trou)] == ["Sur 5 ans", "Sur 10 ans", "Depuis 2022"]
    assert pj.cible_par_defaut(trou) == pytest.approx(trou.dropna().median())  # ni 5 ni 10 ans : tout l'historique
    assert pj.cible_par_defaut(s) == pytest.approx(cinq_ans.median())


def test_watchlist_prix_vise(tmp_path, monkeypatch):
    from pf import watchlist as wl
    monkeypatch.setattr(wl, "WATCHLIST_CSV", tmp_path / "watchlist.csv")
    wl.ajouter("DECK", 90.0)
    wl.fixer_cible("ZTS", 120.0, "P/FCF 20,0", cours=150.0)  # absente : ajoutée au passage, au cours du jour
    wl.fixer_cible("DECK", 85.0, "PER 15,0")
    liste = wl.load_watchlist()
    assert list(liste.index) == ["DECK", "ZTS"]
    assert liste.loc["ZTS", "prix_cible"] == pytest.approx(120.0) and liste.loc["ZTS", "cours_ajout"] == pytest.approx(150.0)
    assert liste.loc["DECK", "cours_ajout"] == pytest.approx(90.0) and liste.loc["DECK", "objectif"] == "PER 15,0"
    wl.ajouter("MC.PA")  # sans prix visé
    atteints = wl.prix_vises_atteints(pd.Series({"DECK": 84.0, "ZTS": 121.0, "MC.PA": 500.0}))
    assert list(atteints.index) == ["DECK"] and atteints.loc["DECK", "cours"] == pytest.approx(84.0)
    assert wl.placer("ZTS", 0) == 0 and wl.load_watchlist().loc["ZTS", "prix_cible"] == pytest.approx(120.0)


def _fait(concept, periode, valeur, unite="iso4217:EUR", **dims):
    return {"value": str(valeur), "dimensions": {"concept": concept, "entity": "scheme:LEI", "period": periode,
                                                 "unit": unite, **dims}}


def test_esef_lecture_d_un_rapport_annuel():
    from pf import esef
    an21, an20 = "2021-01-01T00:00:00/2022-01-01T00:00:00", "2020-01-01T00:00:00/2021-01-01T00:00:00"
    rapport = {"facts": {
        "a": _fait("ifrs-full:Revenue", an21, 64215e6), "b": _fait("ifrs-full:Revenue", an20, 44651e6),
        "c": _fait("ifrs-full:Revenue", an21, 30000e6, **{"ifrs-full:SegmentsAxis": "x:ModeMember"}),  # ventilation : écartée
        "d": _fait("ifrs-full:Revenue", "2021-07-01T00:00:00/2022-01-01T00:00:00", 35000e6),  # semestre : écarté
        "e": _fait("ifrs-full:Revenue", an21, 75000e6, "iso4217:USD"),  # autre devise : écartée
        "f": _fait("ifrs-full:Assets", "2022-01-01T00:00:00", 125e9),  # bilan au 31/12/2021
        "g": _fait("ifrs-full:CashFlowsFromUsedInOperatingActivities", an21, 18648e6),
        "h": _fait("ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", an21, 2000e6),
        "i": _fait("lvm:PurchaseOfIntangibleAssetsAndOther", an21, 664e6),  # poste propre à la société
        "j": _fait("lvm:PurchaseAndProceedsFromSaleOfInvestments", an21, 13e9),  # net de cessions : écarté
        "k": _fait("ifrs-full:AdjustedWeightedAverageShares", an21, 504e6, "xbrli:shares"),
    }}
    s, devise = esef.extraire(rapport, "EUR")
    assert devise == "EUR"
    assert s["revenue"]["Revenue"] == {"2021-12-31": 64215e6, "2020-12-31": 44651e6}
    assert s["assets"]["Assets"] == {"2021-12-31": 125e9}
    assert s["shares"]["AdjustedWeightedAverageShares"] == {"2021-12-31": 504e6}
    capex = s["capex"]
    assert "lvm:PurchaseAndProceedsFromSaleOfInvestments" not in capex
    somme = "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities+lvm:PurchaseOfIntangibleAssetsAndOther"
    assert capex[somme] == {"2021-12-31": 2664e6}  # corporels + incorporels, comme Yahoo
    assert s["fcf"][f"ocf-{somme}"] == {"2021-12-31": 18648e6 - 2664e6}
    assert esef.extraire(rapport)[1] == "EUR"  # sans devise imposée : la plus fréquente


def test_esef_recherche_par_nom_et_raccord():
    from pf import esef
    assert esef.mots_du_nom("LVMH Moët Hennessy - Louis Vuitton, Société Européenne") == [
        "lvmh", "moet", "hennessy", "louis", "vuitton"]
    assert esef.mots_du_nom("SAP SE") == ["sap"]
    assert esef.couvert("MC.PA") and esef.couvert("ULVR.L") and not esef.couvert("NESN.SW") and not esef.couvert("AAPL")
    fund = {"income": {"Total Revenue": {"2022-12-31": 100.0, "2023-12-31": 110.0}}}
    assert esef._concorde({"revenue": {"Revenue": {"2023-12-31": 108.0}}}, fund)  # 1,8 % d'écart
    assert not esef._concorde({"revenue": {"Revenue": {"2023-12-31": 150.0}}}, fund)  # une autre société
    # Avec les comptes européens, l'historique s'allonge comme avec la SEC (raccord sur deux exercices).
    fund["income"]["Total Revenue"].update({"2024-12-31": 120.0, "2025-12-31": 130.0})
    comptes = {"series": {"revenue": {"Revenue": {"2020-12-31": 80.0, "2021-12-31": 90.0, "2022-12-31": 100.0,
                                                  "2023-12-31": 110.0}}}}
    h, prolonge = postes.historique(fund, comptes)
    assert prolonge and h["revenue"].dropna().index.min() == pd.Timestamp("2020-12-31")


def test_esef_fusion_le_rapport_recent_l_emporte():
    from pf import esef
    series = {}
    esef._fusionner(series, {"revenue": {"Revenue": {"2020-12-31": 100.0, "2021-12-31": 110.0}}})
    esef._fusionner(series, {"revenue": {"Revenue": {"2021-12-31": 112.0, "2022-12-31": 120.0}}})  # 2021 retraité
    assert series["revenue"]["Revenue"] == {"2020-12-31": 100.0, "2021-12-31": 112.0, "2022-12-31": 120.0}


FORMULAIRE_4 = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>DOE JANE</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>1</isOfficer>
      <officerTitle>Chief Financial Officer</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>0</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-05-13</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>75.5</value></transactionPricePerShare></transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>21000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-05-13</value></transactionDate>
      <transactionCoding><transactionCode>F</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>300</value></transactionShares></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_dirigeants_lecture_d_un_formulaire_4():
    from pf import dirigeants as dg
    lignes = dg.analyser(FORMULAIRE_4)
    assert len(lignes) == 1  # la retenue fiscale (code F) est ignorée
    x = lignes[0]
    assert (x["code"], x["nom"], x["fonction"]) == ("P", "Doe Jane", "Chief Financial Officer, Administrateur")
    assert x["montant"] == pytest.approx(75500.0) and x["detenues_apres"] == 21000 and not x["plan_10b5_1"]


def test_dirigeants_synthese_et_achats_groupes():
    from pf import dirigeants as dg
    tx = pd.DataFrame([
        {"date": "2026-05-13", "nom": n, "code": "P", "montant": m, "plan_10b5_1": False}
        for n, m in [("A", 500e3), ("B", 150e3), ("C", 230e3), ("A", 20e3)]]
        + [{"date": "2026-02-17", "nom": "D", "code": "S", "montant": 2e6, "plan_10b5_1": True},
           {"date": "2026-03-01", "nom": "E", "code": "S", "montant": 1e6, "plan_10b5_1": False}])
    s = dg.synthese(tx)
    assert s["signal"] == "Achats groupés" and s["acheteurs"] == 3 and s["achats"] == 4
    assert s["montant_achats"] == pytest.approx(900e3) and s["part_ventes_programmees"] == pytest.approx(2 / 3)
    assert dg.synthese(tx[tx["nom"].isin(["A", "D"])])["signal"] == "Achat d'un dirigeant"
    assert dg.synthese(tx[tx["code"] == "S"])["signal"] == "Ventes seulement"
    assert dg.synthese(None)["signal"] == "Aucune transaction en bourse"


TABLE_13F = """<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip>
    <value>1000</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
  <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip>
    <value>500</value><shrsOrPrnAmt><sshPrnamt>5</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
  <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>CALL</titleOfClass><cusip>037833100</cusip>
    <value>99</value><shrsOrPrnAmt><sshPrnamt>1</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <putCall>Call</putCall></infoTable>
  <infoTable><nameOfIssuer>KRAFT HEINZ</nameOfIssuer><titleOfClass>NOTE</titleOfClass><cusip>500754AA0</cusip>
    <value>77</value><shrsOrPrnAmt><sshPrnamt>77</sshPrnamt><sshPrnamtType>PRN</sshPrnamtType></shrsOrPrnAmt></infoTable>
</informationTable>"""


def test_13f_lecture_de_la_table_d_information():
    from pf import investisseurs as inv
    lignes = inv.analyser_table(TABLE_13F)
    assert len(lignes) == 1  # option et obligation écartées, deux lignes du même titre additionnées
    assert lignes[0]["cusip"] == "037833100" and lignes[0]["valeur"] == 1500 and lignes[0]["actions"] == 15
    assert inv.analyser_table(TABLE_13F, en_milliers=True)[0]["valeur"] == 1_500_000  # avant 2023 : milliers de dollars


def test_13f_mouvements_et_positions(tmp_path, monkeypatch):
    from pf import investisseurs as inv
    assert inv.mouvement(150, 100) == ("Renforcée", pytest.approx(0.5))
    assert inv.mouvement(100, 101)[0] == "Inchangée" and inv.mouvement(50, 100)[0] == "Allégée"
    assert inv.mouvement(10, 0)[0] == "Nouvelle" and inv.mouvement(0, 10)[0] == "Soldée"
    monkeypatch.setattr(inv, "CACHE", tmp_path)
    monkeypatch.setattr(inv, "TICKERS_JSON", tmp_path / "tickers.json")
    ligne = lambda c, v, a: {"cusip": c, "nom": c, "classe": "COM", "valeur": v, "actions": a}  # noqa: E731
    from pf.config import ecrire_json
    ecrire_json(tmp_path / "1.json", {"format": inv.FORMAT, "periodes": {
        "2026-03-31": {"depose_le": "2026-05-15", "lignes": [ligne("A", 100, 10), ligne("B", 50, 5), ligne("C", 30, 3)]},
        "2026-06-30": {"depose_le": "2026-08-14", "lignes": [ligne("A", 300, 20), ligne("C", 30, 3), ligne("D", 70, 7)]},
    }})
    p = inv.positions(1)
    assert p.attrs["periode"] == "2026-06-30" and p.attrs["total"] == 400
    assert p.loc["A", "poids"] == pytest.approx(0.75) and p.loc["A", "mouvement"] == "Renforcée"
    assert p.loc["B", "mouvement"] == "Soldée" and p.loc["B", "valeur"] == 0
    assert p.loc["D", "mouvement"] == "Nouvelle" and p.loc["D", "depuis"] == "2026-06-30"
    assert p.loc["C", "depuis"] == "2026-03-31" and p.loc["C", "depuis_debut_fenetre"]


RAPPORT_ELU = """Name: Hon. Nancy Pelosi
ID Owner Asset Transaction
Type
Date Notification
Date
Amount Cap.
Gains >
$200?
SP Alphabet Inc. - Class A Common
Stock (GOOGL) [OP]
P 12/30/2025 12/30/2025 $250,001 -
$500,000
F\x00\x00S\x00\x00: New
D\x00\x00\x00: Purchased 20 call options with a strike price of $150 and an expiration date of 1/15/27.
SP Tempus AI, Inc. - Class A Common P 01/16/2026 01/16/2026 $50,001 -
Filing ID #20033725
ID Owner Asset Transaction
Type
Date Notification
Date
Amount Cap.
Gains >
$200?
Stock (TEM) [ST] $100,000
F\x00\x00S\x00\x00: New
D\x00\x00\x00: Exercised 50 call options purchased 1/14/25 (5,000 shares) at a strike price of $20 with an expiration date of
1/16/26.
JT US Treasury Bill [GS] S (partial) 02/03/2026 02/05/2026 $1,001 - $15,000
F\x00\x00S\x00\x00: New
* For the complete list of asset type abbreviations, please visit https://fd.house.gov/reference/asset-type-codes.aspx.
"""


def test_congres_lecture_d_un_rapport_de_transactions():
    from pf import congres
    ops = congres.analyser(RAPPORT_ELU)
    assert len(ops) == 3
    a, b, c = ops
    assert (a["detenteur"], a["ticker"], a["type"], a["operation"], a["date"]) == ("SP", "GOOGL", "OP", "P", "2025-12-30")
    assert a["montant_min"] == 250001 and a["montant_max"] == 500000 and a["description"].startswith("Purchased 20 call")
    # Opération coupée par un saut de page : l'opération et le ticker sont réunis, la description suit.
    assert (b["ticker"], b["operation"], b["montant_max"]) == ("TEM", "P", 100000)
    assert b["actif"] == "Tempus AI, Inc. - Class A Common Stock (TEM)" and b["description"].endswith("1/16/26.")
    assert (c["detenteur"], c["ticker"], c["type"], c["operation"]) == ("JT", None, "GS", "S (partial)")


def test_idees_plancher_de_qualite_et_cycliques_plafonnes():
    rows = []
    for i in range(12):  # 12 pétrolières très bien notées, puis 12 valeurs de qualité un peu moins bien notées
        rows.append({"ticker": f"PET{i}", "statut": "Éligible", "score": 95 - i, "secteur": "Infrastructures & Énergie",
                     "enveloppe": "CTO", "criteres_ok": 5, "criteres_evalues": 6, "moat": "Étroit", "volatilite": 0.3})
    for i in range(12):
        rows.append({"ticker": f"QUA{i}", "statut": "Éligible", "score": 80 - i, "secteur": f"Secteur {i % 6}",
                     "enveloppe": "PEA", "criteres_ok": 4 + (i % 3 == 0), "criteres_evalues": 6, "moat": "Large",
                     "volatilite": 0.2})
    rows += [{"ticker": "FAIBLE", "statut": "Éligible", "score": 99, "secteur": "Santé", "enveloppe": "PEA",
              "criteres_ok": 6, "criteres_evalues": 6, "moat": "Faible", "volatilite": 0.2},
             {"ticker": "BANQUE", "statut": "Éligible", "score": 98, "secteur": "Banques", "enveloppe": "PEA",
              "criteres_ok": 2, "criteres_evalues": 2, "moat": None, "volatilite": 0.2},
             {"ticker": "MEDIOCRE", "statut": "Éligible", "score": 97, "secteur": "Santé", "enveloppe": "PEA",
              "criteres_ok": 2, "criteres_evalues": 6, "moat": "Large", "volatilite": 0.2}]
    sc = pd.DataFrame(rows).set_index("ticker")
    choix = pfo.select(sc, 10, max_per_sector=10, part_pea=None, criteres_min=4, exclure_moat_faible=True,
                       cycliques_max=0.3)
    assert "FAIBLE" not in choix and "MEDIOCRE" not in choix and "BANQUE" in choix  # 2/2 : plancher passé
    cycliques = [t for t in choix if sc.loc[t, "secteur"] in pfo.CYCLIQUES]
    assert len(cycliques) == 3 and len(choix) == 10  # 30 % de 10 lignes, banque comprise
    w = pfo.weight(choix, sc, "egal", 0.02, 0.2, 0.5, cycliques_max=0.2)
    assert w[cycliques].sum() == pytest.approx(0.2, abs=1e-6) and w.sum() == pytest.approx(1.0)
    assert pfo.select(sc, 10, 10, None) [0] == "FAIBLE"  # sans plancher : le meilleur score passe


def test_note_de_construction_selon_la_methode():
    sc = pd.DataFrame({
        "statut": ["Éligible"] * 4, "secteur": ["A", "B", "C", "D"], "enveloppe": ["PEA"] * 4,
        "score": [90.0, 80.0, 70.0, 60.0], "buffett": [1, 5, 3, 5], "valorisation": [10.0, 20.0, 90.0, None],
        "criteres_ok": [6, 2, 4, 1], "criteres_evalues": [6, 2, 6, 1], "moat": ["Large"] * 4,
    }, index=["W", "X", "Y", "Z"])
    defaut = pfo.note_construction(sc)
    assert list(defaut.sort_values(ascending=False).index) == ["W", "X", "Y", "Z"]  # note GARP
    assert list(pfo.NOTATIONS) == ["garp"] and pfo.NOTATIONS["garp"][2] == {"score": 1}
    b = pfo.note_construction(sc, {"buffett": 1})  # une autre composante reste possible par code
    assert b["X"] > b["Z"] > b["Y"] > b["W"]  # ex aequo X et Z (5/5) départagés par la note GARP
    mix = pfo.note_construction(sc, {"valorisation": 0.5, "criteres_part": 0.5})
    assert mix["Z"] != mix["Z"]  # ni valorisation ni critères (un seul évalué) : pas de note
    assert mix["Y"] > mix["W"]
    assert pfo.select(sc, 2, part_pea=None, note=b) == ["X", "Z"]
    assert pfo.select(sc, 2, part_pea=None) == ["W", "X"]


def test_etalement_stable_et_reparti():
    from pf.config import etalement
    assert etalement("AAPL") == etalement("AAPL")
    valeurs = [etalement(f"T{i}") for i in range(2000)]
    assert 0 <= min(valeurs) and max(valeurs) < 1
    assert 0.2 < sum(v < 0.5 for v in valeurs) / len(valeurs) < 0.8  # ni tout d'un côté, ni tout de l'autre


def test_raccord_vectorise_meme_regle():
    d = pd.to_datetime(["2022-12-31", "2023-12-31", "2024-12-31"])
    y = pd.Series([100.0, 110.0, 120.0], index=d)
    s = pd.Series([-100.5, -110.2, -119.0], index=pd.to_datetime(["2022-12-28", "2023-12-31", "2025-01-05"]))
    assert postes._signe_concordant(y, s, 0.03) == -1.0  # au signe près, à 10 jours près
    assert postes._signe_concordant(y, s.iloc[:1], 0.03) is None  # un seul exercice commun
    ecart = s.copy()
    ecart.iloc[1] = -150.0
    assert postes._signe_concordant(y, ecart, 0.03) is None  # un écart suffit à rejeter
    nulle = s.copy()
    nulle.iloc[0] = 0.0
    assert postes._signe_concordant(y, nulle, 0.03) is None


def test_bilan_affiche_les_durees():
    from pf.maj import bilan
    res = {"rapide": True, "derniere_date": "2026-11-06", "fondamentaux_ok": 0, "fondamentaux_deja_a_jour": 0,
           "erreurs": {}, "sans_cours": [], "durees": {"Cours": 42.0, "Indicateurs et scores": 75.0, "Changes": 0.4},
           "duree_totale": 118.0}
    lignes = bilan(res, pd.DataFrame())
    assert lignes[0].startswith("Mise à jour rapide")
    assert lignes[1] == "Durée : 1 min 58 s (indicateurs et scores 1 min 15 s, cours 42 s)."


def test_cours_relances_groupees_et_bornees(monkeypatch):
    jours = pd.bdate_range("2026-10-01", "2026-11-05")
    appels = []
    refus = {"premier": True}

    def telecharge(tickers, start):
        appels.append(list(tickers))
        if refus["premier"] and len(tickers) > 1:  # Yahoo surchargé : le premier lot revient vide
            refus["premier"] = False
            return pd.DataFrame()
        return pd.DataFrame({t: 1.0 for t in tickers if t != "RADIEE"}, index=jours)

    monkeypatch.setattr(pf_data, "_download_close", telecharge)
    monkeypatch.setattr(pf_data.time, "sleep", lambda s: None)
    tickers = [f"T{i}" for i in range(25)] + ["RADIEE"]
    out = pf_data._download_batch(tickers, "2026-10-01", chunk=100)
    assert set(out.columns) == set(tickers) - {"RADIEE"}
    assert len(appels[1]) == 26  # le lot refusé est relancé d'un bloc, pas valeur par valeur
    assert all(len(a) == 1 for a in appels[2:]) and len(appels) <= 4  # seule la valeur radiée est relancée seule


def test_regles_de_vente(tmp_path, monkeypatch):
    from pf import regles
    monkeypatch.setattr(regles, "REGLES_CSV", tmp_path / "regles.csv")
    regles.ajouter("ADBE", "evol_ca_12m", "<", 0, "CA en baisse")
    regles.ajouter("ADBE", "dette_nette_ebitda", ">", 2.5)
    regles.ajouter("XYZ", "per", ">", 30)
    sc = pd.DataFrame({"evol_ca_12m": [-0.02], "dette_nette_ebitda": [1.0], "per": [40.0]}, index=["ADBE"])
    ev = regles.evaluer(sc)
    assert list(ev["statut"]) == ["Atteinte", "Respectée", "Donnée absente"]
    assert ev.loc[0, "regle"] == "CA des 12 derniers mois, par rapport au dernier exercice sous 0 %"
    assert ev.loc[0, "valeur"] == "-2,0 %" and ev.loc[1, "regle"].endswith("au-dessus de 2,5x")
    regles.retirer(1)
    assert len(regles.load_regles()) == 2


def test_risques_concentration_et_pertes():
    from pf import risques
    w = pd.Series({"A": 0.5, "B": 0.3, "C": 0.2})
    c = risques.concentration(w)
    assert c["plus_grosse"] == "A" and c["trois_premieres"] == pytest.approx(1.0)
    assert c["nombre_effectif"] == pytest.approx(1 / (0.25 + 0.09 + 0.04)) and c["lignes_au_dessus_10"] == 3
    r = pd.Series([0.10, -0.20, 0.05], index=pd.bdate_range("2026-01-01", periods=3))
    assert risques.perte_maximale(r) == pytest.approx(-0.20)  # sommet après +10 %, puis -20 %
    jours = pd.bdate_range("2024-01-01", periods=300)
    b = pd.Series(np.random.default_rng(0).normal(0, 0.01, 300), index=jours)
    rr = pd.DataFrame({"IDX": b, "X": 2 * b, "Y": 0.5 * b})
    bt = risques.betas(rr, ["X", "Y"], "IDX")
    assert bt["X"] == pytest.approx(2.0) and bt["Y"] == pytest.approx(0.5)


def test_scenarios_prix_dans_5_ans(tmp_path, monkeypatch):
    from pf import scenarios as scn
    r = pd.Series({"cours": 100.0, "capitalisation_comptes": 1000.0, "p_ca": 2.0, "marge_fcf": 0.20,
                   "p_fcf_historique": 25.0, "croissance_attendue": 0.10, "evolution_actions": 0.0, "devise": "EUR",
                   "financiere": False})
    assert scn.chiffre_affaires(r) == pytest.approx(500.0)
    # CA 500 × 1,1^5 × 20 % × 20 = valeur ; cours × valeur / capitalisation
    attendu = 100 * 500 * 1.1 ** 5 * 0.20 * 20 / 1000
    assert scn.prix_futur(r, 0.10, 0.20, 20) == pytest.approx(attendu)
    assert scn.rendement_annuel(attendu, 100) == pytest.approx((attendu / 100) ** 0.2 - 1)
    depart = scn.hypotheses_initiales(r)
    assert depart["Central"] == {"croissance": 0.10, "marge": 0.20, "multiple": 25.0}  # médiane seule connue
    assert depart["Pessimiste"]["multiple"] < 25 < depart["Optimiste"]["multiple"]
    assert scn.base_de(pd.Series({"financiere": True, "marge_fcf": 0.2})) == "resultat"
    monkeypatch.setattr(scn, "SCENARIOS_CSV", tmp_path / "scenarios.csv")
    scn.enregistrer("X", r, depart)
    sc = pd.DataFrame([{**r.to_dict(), "cours": 10_000.0}], index=["X"])  # cours très au-dessus de l'optimiste
    assert scn.alertes(sc)[0][0] == "X" and "optimiste" in scn.alertes(sc)[0][1]


def test_formats_printf_vers_francais():
    df = pd.DataFrame({"a": [1.234], "b": [5.0], "c": [12.5]})
    cfg = {"a": {"type_config": {"type": "number", "format": "%.2f"}},
           "b": {"type_config": {"type": "number", "format": "%d ex."}},  # un point qui n'est pas une précision
           "c": {"type_config": {"type": "number", "format": "%.1f %%"}}}
    out, nouveau = ui._a_la_francaise(df, cfg)
    assert out["a"].iloc[0] == 1.23 and out["b"].iloc[0] == 5 and out["c"].iloc[0] == pytest.approx(0.125)
    assert nouveau["b"]["type_config"]["format"] == "localized" and nouveau["c"]["type_config"]["format"] == "percent"


def test_backtest_a_date_divisions_et_publication():
    from pf import backtest_pit as bp
    ans = pd.to_datetime(["2016-12-31", "2017-12-31", "2018-12-31", "2019-12-31", "2020-12-31"])
    actions = pd.Series([100.0, 98.0, 392.0, 380.0, 370.0], index=ans)  # division par 4 en 2018, rachats ensuite
    corr = bp.actions_corrigees(actions)
    assert corr["2016-12-31"] == pytest.approx(400.0) and corr["2017-12-31"] == pytest.approx(392.0)
    assert corr["2020-12-31"] == 370.0
    assert bp.actions_corrigees(pd.Series([100.0, 110.0], index=ans[:2]))["2016-12-31"] == 100.0  # +10 % : pas une division
    comptes = pd.DataFrame({"revenue": [100.0, 110, 120, 130, 140], "net_income": [10.0, 11, 12, 13, 14],
                            "equity": [50.0] * 5, "op_income": [15.0] * 5, "ocf": [20.0] * 5, "capex": [5.0] * 5},
                           index=ans)
    jours = pd.bdate_range("2015-01-01", "2021-12-31")
    prix = pd.Series(np.linspace(10, 20, len(jours)), index=jours)
    # Le 1er mars 2020, les comptes 2019 (clos le 31/12, publiés fin mars) ne sont pas encore connus : 2018 sert.
    x = bp.indicateurs_a_date(pd.Timestamp("2020-03-02"), comptes, corr, prix, 1000.0)
    assert x["marge_fcf"] == pytest.approx(15 / 120)
    y = bp.indicateurs_a_date(pd.Timestamp("2020-04-01"), comptes, corr, prix, 1000.0)
    assert y["marge_fcf"] == pytest.approx(15 / 130) and y["croissance_ca_3a"] == pytest.approx((130 / 100) ** (1 / 3) - 1)
    assert bp.indicateurs_a_date(pd.Timestamp("2016-02-01"), comptes, corr, prix, 1000.0) is None  # aucun compte publié
    indic = pd.DataFrame({"roe": [0.3, 0.1], "marge_op": [0.3, 0.1], "marge_fcf": [0.2, 0.1], "sobriete": [0.0, -0.1],
                          "croissance_ca_3a": [0.05, 0.2], "rendement_fcf": [0.02, 0.08], "rendement_benefices": [0.02, 0.06],
                          "mom_12_1": [0.1, 0.3]}, index=["Q", "V"])
    assert bp.note(indic, {"qualite": 1})["Q"] > bp.note(indic, {"qualite": 1})["V"]
    assert bp.note(indic, {"valeur": 1})["V"] > bp.note(indic, {"valeur": 1})["Q"]


def test_sec_postes_ifrs_d_un_deposant_etranger():
    """Un 20-F en IFRS (On Holding) : chiffre d'affaires et fonds propres sous leurs noms ifrs-full."""
    def fait(val, end, start=None):
        x = {"val": val, "end": end, "form": "20-F", "filed": "2026-03-01"}
        if start:
            x["start"] = start
        return x
    facts = {"entityName": "Exemple", "facts": {"ifrs-full": {
        "RevenueFromContractsWithCustomers": {"units": {"CHF": [fait(2.3e9, "2025-12-31", "2025-01-01")]}},
        "Equity": {"units": {"CHF": [fait(1.6e9, "2025-12-31")]}},
    }}}
    d = sec.extract(facts)
    assert d["devise"] == "CHF"
    assert d["postes"]["revenue"] == {"2025-12-31": [2.3e9]}
    assert d["postes"]["equity"] == {"2025-12-31": [1.6e9]}


def test_nasdaq_annuaire_et_tri():
    texte = "\n".join([
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares",
        "STRL|Sterling Infrastructure, Inc. - Common Stock|Q|N|N|100|N|N",
        "LBRDA|Liberty Broadband Corporation - Class A Common Stock|Q|N|N|100|N|N",
        "LBRDK|Liberty Broadband Corporation - Class C Common Stock|Q|N|N|100|N|N",
        "ABCW|Abc Corp - Warrant|Q|N|N|100|N|N",
        "XYZ|Xyz Acquisition Corp - Class A Ordinary Shares|Q|N|N|100|N|N",
        "PETIT|Petite Cap Inc - Common Stock|S|N|N|100|N|N",
        "DEF|Defaillante Inc - Common Stock|Q|N|D|100|N|N",
        "QQQ|Invesco QQQ Trust|G|N|N|100|Y|N",
        "File Creation Time: 1111202612:00|||||||",
    ])
    df = indices.parse_nasdaq(texte)
    assert list(df["ticker"]) == ["STRL", "LBRDA"]
    info = {"quoteType": "EQUITY", "marketCap": 8.8e9, "longName": "Sterling Infrastructure, Inc.",
            "country": "United States", "sector": "Industrials", "industry": "Engineering & Construction"}
    ligne, _ = indices.ligne_nasdaq("STRL", info)
    assert ligne == {"ticker": "STRL", "nom": "Sterling Infrastructure", "pays": "États-Unis", "enveloppe": "CTO",
                     "secteur": "Industrie & Électrification", "profil": ""}
    assert indices.ligne_nasdaq("STRL", {**info, "marketCap": 5e8})[0] is None
    assert indices.ligne_nasdaq("STRL", {**info, "industry": "Shell Companies"})[0] is None
    assert indices.ligne_nasdaq("STRL", {**info, "quoteType": "ETF"})[0] is None
    assert indices.ligne_nasdaq("ARM", {**info, "country": "United Kingdom", "longName": "Arm Holdings plc"})[0][
        "pays"] == "Royaume-Uni"


def test_renouvellement_proportionnel_a_l_univers():
    from pf.config import renouvellement
    assert renouvellement(200) == 100
    assert renouvellement(1757) == 440


def test_profil_cree_depuis_l_exemple_sans_ecraser_un_profil_existant(tmp_path):
    from pf.config import PROFIL_EXEMPLE_DIR, load_model_portfolio, preparer_profil, read_csv_fr
    profil = tmp_path / "profil"
    assert preparer_profil(profil, PROFIL_EXEMPLE_DIR)
    modele = load_model_portfolio(profil / "portefeuille_modele.csv")
    assert abs(modele["poids_cible"].sum() - 100) < 1e-9
    univers = set(read_csv_fr(PROFIL_EXEMPLE_DIR.parent / "config" / "univers.csv")["ticker"])
    for nom in ("portefeuille_modele.csv", "surveillance.csv", "regles_vente.csv", "watchlist.csv"):
        assert set(read_csv_fr(profil / nom)["ticker"]) <= univers, nom
    # Un profil existant n'est jamais remplacé.
    (profil / "watchlist.csv").write_text("ticker;ajoute_le;cours_ajout;note;prix_cible;objectif\n", encoding="utf-8")
    assert not preparer_profil(profil, PROFIL_EXEMPLE_DIR)
    assert read_csv_fr(profil / "watchlist.csv").empty


def test_verifier_jeu_d_essai_sans_erreur():
    from pf.verifier import verifier
    assert [c.message for c in verifier() if c.gravite == "erreur"] == []


def test_verifier_csv_ligne_mal_formee_et_colonne_absente(tmp_path):
    from pf.verifier import verifier_csv
    f = tmp_path / "watchlist.csv"
    f.write_text("ticker;ajoute_le\nMSFT;2026-11-01\nADBE;2026-11-02;note; en trop\n", encoding="utf-8")
    messages = [c.message for c in verifier_csv(f)]
    assert any("ligne 3 : 4 champs au lieu de 2" in m for m in messages)
    assert any("colonnes absentes cours_ajout" in m for m in messages)


def test_verifier_univers_doublons_secteur_enveloppe():
    from pf.verifier import verifier_univers
    u = pd.DataFrame([
        ["ASML", "ASML Holding", "Pays-Bas", "CTO", "Semi-conducteurs"],
        ["ASML.AS", "ASML", "Pays-Bas", "PEA", "Semi-conducteurs"],
        ["EQT", "EQT", "États-Unis", "CTO", "Infrastructures & Énergie"],  # paire connue : sociétés distinctes
        ["EQT.ST", "EQT", "Suède", "CTO", "Services financiers"],
        ["DG", "Dollar General", "États-Unis", "CTO", "Distribution"],  # même racine, autre société
        ["DG.PA", "Vinci", "France", "PEA", "Industrie & Électrification"],
        ["XYZ", "Xyz", "France", "AV", "Secteur inventé"],
        ["XYZ", "Xyz", "France", "PEA", "Santé"],
    ], columns=["ticker", "nom", "pays", "enveloppe", "secteur"])
    messages = [c.message for c in verifier_univers(u)]
    assert sum("probablement la même société" in m for m in messages) == 1
    assert any(m.startswith("ASML (ASML Holding) et ASML.AS") for m in messages)
    assert any("XYZ figure plusieurs fois" in m for m in messages)
    assert any("secteur inconnu" in m for m in messages) and any("enveloppe « AV »" in m for m in messages)


def test_meme_societe_cotee_deux_fois():
    from pf.indices import meme_societe
    assert meme_societe("ASML", "ASML Holding", "ASML.AS", "ASML")
    assert not meme_societe("DG", "Dollar General", "DG.PA", "Vinci")  # même racine, autre société
    assert not meme_societe("EQT", "EQT", "EQT.ST", "EQT")  # paire vérifiée : sociétés distinctes
    assert not meme_societe("SAN.PA", "Sanofi", "SAN.MC", "Banco Santander")  # deux places européennes


def test_fiches_de_these_creees_sans_ecraser_et_journal(tmp_path, monkeypatch):
    from pf import theses
    from pf.scoring import build_screener
    monkeypatch.setattr(theses, "THESES_DIR", tmp_path)
    (tmp_path / "MSFT.md").write_text("# Fiche existante\n", encoding="utf-8")
    creees = theses.ensure_thesis_files(build_screener())
    # Profil d'exemple : ASML.AS, AI.PA, MSFT, COST ; la fiche existante n'est pas remplacée.
    assert sorted(creees) == ["AI.PA", "ASML.AS", "COST"]
    assert theses.read_thesis("MSFT") == "# Fiche existante\n"
    texte = theses.read_thesis("ASML.AS")
    assert "ASML" in texte and "Exemple fictif" in texte
    theses.append_journal("ASML.AS", "Note de test")
    assert "Note de test" in theses.read_thesis("ASML.AS")
    assert theses.read_thesis("INCONNU") is None


def test_photos_du_screener(tmp_path, monkeypatch):
    from pf import photos
    # Jeu d'essai : deux photos, MSFT passée d'« Exclu » à son statut actuel.
    chg = photos.changements_de_statut(["MSFT", "ADBE"])
    assert [(t, ancien) for t, ancien, _, _ in chg] == [("MSFT", "Exclu")]
    assert len(photos.evolution("ADBE")) == 2
    # Une photo à la même date remplace la précédente ; une autre date s'ajoute.
    monkeypatch.setattr(photos, "PHOTOS_PARQUET", tmp_path / "scores.parquet")
    sc = pd.DataFrame({"statut": ["Éligible", "Exclu"], "score": [80.0, 40.0], "rang": [1, 2]},
                      index=pd.Index(["AAA", "BBB"], name="ticker"))
    assert photos.enregistrer(sc, "2026-01-05") == 2
    photos.enregistrer(sc.assign(rang=[2, 1]), "2026-01-05")
    assert len(photos.charger()) == 2
    photos.enregistrer(sc.assign(statut=["Exclu", "Exclu"]), "2026-01-12")
    assert photos.evolution("AAA")["rang"].tolist() == [2, 1]
    assert photos.changements_de_statut(["AAA", "BBB"]) == [("AAA", "Éligible", "Exclu", pd.Timestamp("2026-01-05"))]


def test_sauvegarde_archive_datee_et_rotation(tmp_path, monkeypatch):
    import zipfile
    from datetime import datetime

    from pf import config, sauvegarde
    monkeypatch.setattr(sauvegarde, "PRIVE_JSON", tmp_path / "prive.json")
    monkeypatch.setattr(config, "PRIVE_JSON", tmp_path / "prive.json")
    (tmp_path / "prive.json").write_text('{"contact_sec": "Test test@exemple.fr"}', encoding="utf-8")
    dest = tmp_path / "sauvegardes"
    sauvegarde.memoriser_dossier(dest)
    assert sauvegarde.dossier_configure() == dest
    assert config.load_prive()["contact_sec"] == "Test test@exemple.fr"  # réglage existant conservé
    archive = sauvegarde.creer(maintenant=datetime(2026, 1, 1))
    noms = zipfile.ZipFile(archive).namelist()
    assert {"profil/portefeuille_modele.csv", "theses/MSFT.md", "data/transactions.csv",
            "data/historique/scores.parquet"} <= set(noms)
    monkeypatch.setattr(sauvegarde, "GARDER", 2)
    for jour in (2, 3, 4):
        sauvegarde.creer(maintenant=datetime(2026, 1, jour))
    assert sorted(p.name for p in dest.glob("*.zip")) == ["garp-donnees-2026-01-03.zip",
                                                          "garp-donnees-2026-01-04.zip"]
    # Sauvegardes de l'ancien nom : comptées dans la rotation, par date.
    (dest / "climax-donnees-2026-01-05.zip").write_bytes(b"")
    sauvegarde.creer(maintenant=datetime(2026, 1, 6))
    assert sorted(p.name for p in dest.glob("*.zip")) == ["climax-donnees-2026-01-05.zip",
                                                          "garp-donnees-2026-01-06.zip"]


def test_simulation_ajout_retrait_d_une_ligne():
    from pf import simulation
    w = pd.Series({"ASML.AS": 0.30, "AI.PA": 0.25, "MSFT": 0.30, "COST": 0.15})
    apres = simulation.nouveaux_poids(w, "GOOGL", 0.10)
    assert apres.sum() == pytest.approx(1) and apres["GOOGL"] == pytest.approx(0.10)
    assert apres["MSFT"] == pytest.approx(0.27)  # 30 % réduit en proportion
    retrait = simulation.nouveaux_poids(w, "COST", 0)
    assert "COST" not in retrait and retrait.sum() == pytest.approx(1)

    sc = build_screener()
    res = simulation.simuler(w, "GOOGL", 0.10, sc)
    m = res["mesures"]
    assert m.loc["Nombre effectif de lignes", "apres"] > m.loc["Nombre effectif de lignes", "avant"]
    assert m.loc["Plus grosse ligne", "apres"] == pytest.approx(0.27)
    assert res["poids"].loc["GOOGL", "avant"] == 0 and res["poids"]["apres"].sum() == pytest.approx(1)
    assert res["devises"]["apres"].sum() == pytest.approx(1)
    assert set(res["correlations"].index) == {"ASML.AS", "AI.PA", "MSFT", "COST"}
    assert res["correlations"].between(-1, 1).all()


def test_garde_fous_de_concentration():
    from pf import risques
    secteurs = pd.Series({"A": "Santé", "B": "Santé", "C": "Banques", "D": "Banques", "E": "Distribution"})
    w = pd.Series({"A": 0.30, "B": 0.25, "C": 0.20, "D": 0.15, "E": 0.10})
    seuils = {"ligne_max": 0.25, "trois_premieres_max": 0.60, "secteur_max": 0.40, "correlation_moyenne_max": 0.5}
    alertes = risques.garde_fous(w, secteurs, seuils=seuils)
    assert [t for t, _ in alertes] == ["A", "", ""]  # A > 25 %, trois premières 75 %, Santé 55 %
    assert "Santé" in alertes[2][1] and "55 %" in alertes[2][1]
    assert risques.garde_fous(pd.Series(0.2, index=list("ABCDE")), pd.Series("x", index=list("ABCDE")),
                              seuils={**seuils, "secteur_max": 1.0}) == []
    assert risques.seuils_garde_fous({})["ligne_max"] == 0.25  # valeurs par défaut sans réglage


def test_mobile_adresse_tailscale():
    from pf import mobile
    assert mobile.adresse({"BackendState": "Running", "Self": {"DNSName": "pc-maison.tail1234.ts.net."}}) \
        == "https://pc-maison.tail1234.ts.net"
    assert mobile.adresse({"BackendState": "NeedsLogin", "Self": {"DNSName": "pc.tail1234.ts.net."}}) is None
    assert mobile.adresse({}) is None


def test_export_application_sans_donnee_personnelle(tmp_path):
    import gzip
    import json

    from pf.export_app import exporter
    chemin = exporter(tmp_path)
    d = json.load(gzip.open(chemin, "rt", encoding="utf-8"))
    assert d["format"] == 1 and d["nb_valeurs"] == len(d["valeurs"]) == 16
    adbe = next(v for v in d["valeurs"] if v["ticker"] == "ADBE")
    assert adbe["statut"] == "Éligible" and isinstance(adbe["score"], float) and adbe["devise"] == "USD"
    assert 0.5 < adbe["cours_eur"] / adbe["cours"] < 1.2  # dollar converti en euros
    assert len(d["cours"]["ADBE"]["c"]) > 200 and d["rangs"]["ADBE"][0][0] == "2026-11-01"
    # Méthodes d'évaluation et six critères, que l'application recalcule.
    ids = [m["id"] for m in d["methodes"]]
    assert ids == ["garp"] and d["methodes"][0]["poids"] == {"score": 1}
    assert [c["cle"] for c in d["criteres"]] == ["ca", "fcf", "roce", "dette", "actions", "marge"]
    assert {"criteres_ok", "criteres_evalues"} <= set(adbe)
    # Valorisation recalculable par l'application : mêmes entrées que metrics.py, ramenées à la capitalisation.
    from pf.valuation import implied_irr
    v = d["strategie"]["valorisation"]
    tri = implied_irr(1 + adbe["val_dette_cap"], adbe["val_base_cap"], adbe["croissance_attendue"],
                      g_term=v["croissance_terminale"], roic=adbe["val_roic"], years_high=v["annees_croissance"],
                      years_fade=v["annees_convergence"])
    assert abs(tri - adbe["tri_implicite"]) < 1e-3
    assert len(d["changes"]["USD"]["c"]) > 200 and 0.5 < d["changes"]["USD"]["c"][-1] < 1.2
    assert d["strategie"]["garde_fous"]["ligne_max"] > 0 and "notation" not in d["strategie"]["construction"]
    # Fichiers complémentaires : fiches (historique, repères des multiples) et investisseurs.
    fiches = json.load(gzip.open(tmp_path / "garp-fiches.json.gz", "rt", encoding="utf-8"))["fiches"]
    h = fiches["ADBE"]["h"]
    assert len(h["an"]) == len(h["chiffre_affaires"]) >= 4 and h["chiffre_affaires"][-1] > 1e9
    assert fiches["ADBE"]["r"]["PER"]["actuel"] > 0 and len(fiches["ADBE"]["r"]["PER"]["v"]) >= 4
    inv = json.load(gzip.open(tmp_path / "garp-investisseurs.json.gz", "rt", encoding="utf-8"))
    assert {"investisseurs", "partages", "elus", "operations"} <= set(inv)
    texte = gzip.open(chemin, "rt", encoding="utf-8").read()
    for interdit in ("poids_cible", "transactions", "quantite", "contact_sec", "Exemple fictif"):
        assert interdit not in texte, interdit


def test_13f_sans_contact_sec_l_echec_se_voit(monkeypatch, capsys):
    """Sans adresse de contact SEC, la commande échoue (étape en orange dans le flux de la nuit) au lieu d'annoncer
    « 0 trimestres lus » : c'est ainsi que les 13F sont restés figés dans l'ancien dépôt."""
    import argparse

    from pf import __main__ as cli
    from pf import congres, sec

    monkeypatch.setattr(sec, "contact", lambda: "")
    monkeypatch.setattr(congres, "mettre_a_jour", lambda **k: {"nouveaux": 0, "scannes": 0, "erreurs": {}})
    with pytest.raises(SystemExit, match="SEC_CONTACT"):
        cli.cmd_investisseurs(argparse.Namespace(force=False))
    assert "Non lus" in capsys.readouterr().out
