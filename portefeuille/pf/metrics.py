"""Indicateurs par valeur : qualité, croissance, valorisation, momentum, risque.

Tous les ratios sont calculés dans la devise des comptes (sans effet de change) ;
la capitalisation est convertie de la devise de cotation vers celle des comptes.
"""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from . import criteres, homme_cle, postes, sec
from .config import (
    METRICS_META,
    METRICS_PARQUET,
    all_tracked_tickers,
    ecrire_json,
    ecriture_atomique,
    fund_tickers,
    lire_json,
    load_cas_particuliers,
    load_strategy,
    load_universe,
)
from .data import currency_map, fx_rate, load_fundamentals, load_fx, load_prices, split_currency
from .moat import moat_label, moat_points
from .sante import health_scores
from .valuation import implied_growth, implied_irr

# Postes utilisés par les indicateurs (définitions dans postes.py).
COLONNES = ["revenue", "gross_profit", "op_income", "ebit", "ebitda", "net_income", "interest", "tax_rate", "shares",
            "equity", "debt", "cash", "ocf", "capex", "fcf", "sbc", "dividends", "buybacks"]


def is_financial(ticker: str, info: dict, cas: dict[str, set[str]] | None = None) -> bool:
    """Banque, assureur, gérant d'actifs ou holding (config/cas_particuliers.csv pour les exceptions)."""
    cas = cas if cas is not None else load_cas_particuliers()
    if ticker in cas["holding"] or ticker in cas["financiere"]:
        return True
    industry = (info or {}).get("industry") or ""
    if "Broker" in industry:
        return False
    return bool(re.search(r"Bank|Insurance|Reinsurance|Asset Management|Capital Markets|Financial Conglomerates", industry))


def annual_table(fund: dict, sec_data: dict | None = None, h: pd.DataFrame | None = None) -> pd.DataFrame:
    """Six derniers exercices au plus (cinq ans de croissance), Yahoo prolongé par la SEC (postes.historique)."""
    h = postes.historique(fund, sec_data)[0] if h is None else h
    return h.reindex(columns=COLONNES).tail(6)


def _safe_div(a: float, b: float) -> float:
    try:
        if b is None or a is None or not np.isfinite(a) or not np.isfinite(b) or b == 0:
            return math.nan
        return a / b
    except TypeError:
        return math.nan


def price_metrics(s: pd.Series) -> dict:
    s = s.dropna()
    s = s[s > 0]
    out = dict.fromkeys(
        ["cours", "perf_1m", "perf_3m", "perf_6m", "perf_12m", "mom_12_1", "ecart_mm200",
         "ecart_plus_haut_52s", "volatilite", "drawdown_max_3a", "perf_annu_5a"],
        math.nan,
    )
    if len(s) < 30:
        return out
    last = s.iloc[-1]
    n = len(s)

    def back(k):
        return s.iloc[-1 - k] if n > k else math.nan

    out["cours"] = last
    out["perf_1m"] = last / back(21) - 1
    out["perf_3m"] = last / back(63) - 1
    out["perf_6m"] = last / back(126) - 1
    out["perf_12m"] = last / back(252) - 1
    out["mom_12_1"] = back(21) / back(252) - 1
    out["ecart_mm200"] = last / s.iloc[-200:].mean() - 1
    out["ecart_plus_haut_52s"] = last / s.iloc[-252:].max() - 1
    lr = np.log(s).diff().dropna()
    out["volatilite"] = lr.iloc[-252:].std() * math.sqrt(252)
    w = s.iloc[-756:]
    out["drawdown_max_3a"] = (w / w.cummax() - 1).min()
    if n > 1260:
        out["perf_annu_5a"] = (last / s.iloc[-1261]) ** (1 / 5) - 1
    return out


def expected_growth(m: dict, cap: float) -> float:
    """Croissance attendue = médiane de deux signaux prospectifs (consensus BPA et CA) et de la
    croissance historique du CA, bornée. Deux signaux sur trois regardent devant : un passé
    exceptionnel (cycle, rattrapage post-Covid) ne suffit pas à gonfler l'estimation."""
    signals = [m.get(k) for k in ("croiss_bpa_estimee", "croiss_ca_estimee", "croiss_ca")]
    signals = [x for x in signals if x is not None and np.isfinite(x)]
    if not signals:
        return math.nan
    return float(min(max(np.median(signals), 0.0), cap))


def historical_multiple(a: pd.DataFrame, px: pd.Series, mcap_now: float, fx: pd.DataFrame, quote: str, fin_cur: str,
                        col: str = "net_income") -> float:
    """Multiple médian aux dernières clôtures annuelles : capitalisation de l'époque / `col` de l'exercice.

    `col` vaut « net_income » pour le PER, « fcf » pour le prix sur flux de trésorerie disponible.
    Le cours est ajusté des dividendes : le multiple passé est un peu sous-estimé, ce qui reste prudent.
    Le coefficient `k` recale le calcul sur la capitalisation actuelle (plusieurs classes d'actions).
    """
    px = px.dropna()
    shares = a["shares"].dropna()
    if px.empty or shares.empty or not np.isfinite(mcap_now):
        return math.nan
    k = _safe_div(mcap_now, px.iloc[-1] * shares.iloc[-1] * fx_rate(fx, quote, fin_cur))
    pers = []
    for d in shares.index:
        price, ni = px.asof(d), a.at[d, col]
        if np.isfinite(price) and np.isfinite(ni) and ni > 0:
            per = price * shares[d] * fx_rate(fx, quote, fin_cur, d) * k / ni
            if 0 < per < 250:
                pers.append(per)
    return float(np.median(pers)) if len(pers) >= 2 else math.nan


PUBLICATION = pd.Timedelta(days=60)  # délai moyen entre la clôture d'un exercice et la publication de ses comptes
MULTIPLE_MAX = 500  # au-delà, le flux est trop proche de zéro pour que le multiple dise quelque chose


def serie_multiple(px: pd.Series, mcap_now: float, fx: pd.DataFrame, quote: str, fin_cur: str, shares: pd.Series,
                   denominateur: pd.Series, ttm: tuple | None = None) -> pd.Series:
    """Multiple jour par jour : capitalisation du jour / `denominateur` (flux annuel) en vigueur ce jour-là.

    Chaque exercice compte à partir de sa publication (clôture + 60 jours) ; le dernier chiffre sur 12 mois
    glissants (`ttm` = (date, valeur)) prend le relais au plus tard au dernier cours, si bien que le dernier
    point vaut le multiple actuel. Capitalisation : cours (ajusté des dividendes, donc un peu sous-estimée
    dans le passé) x actions de l'exercice x change, recalée sur la capitalisation actuelle. Un flux négatif
    ou nul laisse un trou : le multiple n'a pas de sens.
    """
    px = px.dropna()
    px = px[px > 0]
    d = denominateur.dropna()
    sh = shares.dropna()
    if px.empty or sh.empty or (d.empty and not ttm) or not np.isfinite(mcap_now):
        return pd.Series(dtype="float64")
    points = pd.Series(d.values, index=d.index + PUBLICATION, dtype="float64")
    if ttm and np.isfinite(ttm[1]):
        points.loc[min(pd.Timestamp(ttm[0]) + pd.Timedelta(days=45), px.index[-1])] = ttm[1]
    points = points[~points.index.duplicated(keep="last")].sort_index()

    def au_jour(s: pd.Series) -> pd.Series:
        return s.reindex(s.index.union(px.index)).ffill().reindex(px.index)

    den = au_jour(points)
    actions = au_jour(pd.Series(sh.values, index=sh.index + PUBLICATION)).bfill()
    a, b = split_currency(quote)[0], split_currency(fin_cur)[0]
    change = au_jour(fx[b] / fx[a]).bfill() if a != b and a in fx.columns and b in fx.columns else 1.0
    cap = px * change * actions
    cap = cap / cap.iloc[-1] * mcap_now
    m = cap / den.where(den > 0)
    return m.where((m > 0) & (m < MULTIPLE_MAX))


def compute_one(ticker: str, fund: dict, prices: pd.DataFrame, fx: pd.DataFrame, strat: dict,
                cas: dict[str, set[str]] | None = None) -> dict:
    info = fund.get("info", {})
    cas = cas if cas is not None else load_cas_particuliers()
    clients = ticker in cas["tresorerie_clients"]
    fin_flag = is_financial(ticker, info, cas)
    quote_cur = info.get("currency") or "EUR"
    fin_cur = info.get("financialCurrency") or split_currency(quote_cur)[0]
    sec_data = sec.comptes_officiels(ticker)  # SEC ou ESEF ; le recoupement ne porte que sur la SEC
    h, _ = postes.historique(fund, sec_data)
    a = annual_table(fund, h=h)
    if clients:
        a["cash"] = 0.0
    # Moyennes sur cinq exercices ; les croissances prennent six exercices (cinq ans d'écart).
    a5 = a.tail(5)
    m: dict = {"ticker": ticker, "financiere": fin_flag, "devise": quote_cur, "devise_comptes": fin_cur,
               "nb_exercices": len(a5), "date_donnees": fund.get("fetched", "")[:10],
               # Exercices de l'historique complet (Yahoo prolongé par la SEC ou l'ESEF) : 4 = Yahoo seul.
               "exercices_historique": int(h["revenue"].notna().sum()) if "revenue" in h.columns else 0}

    # ---------------------------------------------------------------- historique annuel
    taux_connus = a5["tax_rate"].clip(0.05, 0.40).dropna()
    tax_rate = float(taux_connus.mean()) if len(taux_connus) else 0.25
    tax = a5["tax_rate"].clip(0.05, 0.40).fillna(tax_rate)
    a = a.copy()
    # Exercices au bilan connu seulement : la SEC ne prolonge ni la dette ni la trésorerie.
    bilan_connu = a5["debt"].notna() | a5["cash"].notna()
    ic = (a5["equity"] + a5["debt"].fillna(0) - a5["cash"].fillna(0)).where(bilan_connu)
    ic_avg = (ic + ic.shift(1)) / 2
    ic_avg = ic_avg.fillna(ic)
    rev = a5["revenue"].where(a5["revenue"] != 0)  # un CA nul donnerait des marges infinies
    # Plancher à 10 % du CA : une trésorerie supérieure aux fonds propres ne doit pas produire un ROIC infini.
    ic_eff = np.maximum(ic_avg, 0.10 * rev.abs()).where(rev.notna() & ic_avg.notna(), ic_avg.where(ic_avg > 0))
    nopat = a5["ebit"] * (1 - tax)
    roic = (nopat / ic_eff).clip(-1.0, 1.0)
    roe = (a5["net_income"] / a5["equity"].where(a5["equity"] > 0)).clip(-1, 1.5)
    m["roic_moyen"] = roic.mean() if not fin_flag else math.nan
    m["roic_dernier"] = roic.dropna().iloc[-1] if roic.notna().any() and not fin_flag else math.nan
    m["roe_moyen"] = roe.mean()
    m["roe_dernier"] = roe.dropna().iloc[-1] if roe.notna().any() else math.nan
    m["rentabilite"] = m["roe_moyen"] if fin_flag else m["roic_moyen"]
    m["rentabilite_derniere"] = m["roe_dernier"] if fin_flag else m["roic_dernier"]
    ocf = a["ocf"].dropna()
    m["ocf_positif_2a"] = bool(len(ocf) >= 2 and (ocf.iloc[-2:] > 0).all())
    m["marge_brute"] = (a5["gross_profit"] / rev).mean() if not fin_flag else math.nan
    op_margin = a5["op_income"] / rev
    m["marge_operationnelle"] = op_margin.mean() if not fin_flag else math.nan
    m["stabilite_marge"] = op_margin.std() if (not fin_flag and op_margin.notna().sum() >= 3) else math.nan
    m["marge_nette"] = (a5["net_income"] / rev).mean()
    fcf = a["fcf"]
    # Même calcul que le critère « marge du free cash flow » (criteres.py) : une seule valeur à l'écran.
    marges_fcf = postes.derniers((fcf / a["revenue"].where(a["revenue"] > 0)).replace([np.inf, -np.inf], np.nan))
    m["marge_fcf"] = float(marges_fcf.mean()) if not fin_flag and len(marges_fcf) else math.nan
    m["fcf_cumule"] = a5["fcf"].sum(min_count=1)
    ni_sum = a5["net_income"].sum(min_count=1)
    m["conversion_fcf"] = min(max(_safe_div(m["fcf_cumule"], ni_sum), -1), 3) if ni_sum and ni_sum > 0 else math.nan
    last = a.iloc[-1] if len(a) else pd.Series(dtype=float)
    ebit_last = last.get("ebit", math.nan)
    interest = abs(last.get("interest", math.nan)) if np.isfinite(last.get("interest", math.nan)) else math.nan
    m["couverture_interets"] = (999.0 if (interest == 0 or not np.isfinite(interest)) and ebit_last > 0
                                else _safe_div(ebit_last, interest))
    # Dette nette au dernier bilan publié (trimestriel s'il existe). Inconnue sans bilan : jamais nulle par défaut.
    bilan = postes.dernier_bilan(fund, tresorerie_clients=clients)
    net_debt = bilan[0] - bilan[1] if bilan else math.nan
    # EBITDA du dernier exercice complet : celui des 12 derniers mois intègre les charges exceptionnelles
    # (dépréciations, recherche acquise) et ferait basculer le filtre d'endettement sur un événement ponctuel.
    ebitda = last.get("ebitda", math.nan)
    m["dette_nette_ebitda"] = _safe_div(net_debt, ebitda) if ebitda and ebitda > 0 else math.nan
    m["dette_nette_date"] = bilan[2] if bilan else None
    # Croissances : même fenêtre (cinq ans au plus) que les critères, sur l'historique prolongé. La dilution
    # du filtre et du pilier qualité juge le comportement récent (trois ans) : une fusion payée en actions
    # il y a cinq ans ne dit plus rien de la façon dont la direction traite ses actionnaires aujourd'hui.
    m["evolution_actions"] = postes.taux_annuel(a["shares"], annees=3)
    m["croiss_ca"] = postes.taux_annuel(a["revenue"])
    m["croiss_ebit"] = postes.taux_annuel(a["op_income"])
    m["croiss_bpa"] = postes.taux_annuel(a["net_income"] / a["shares"])
    m["croiss_fcf_action"] = postes.taux_annuel(fcf / a["shares"])

    # ---------------------------------------------------------------- consensus
    est = fund.get("eps_estimate", {})
    g_eps = [est.get(p, {}).get("growth") for p in ("0y", "+1y")]
    g_eps = [g for g in g_eps if g is not None and np.isfinite(g)]
    m["croiss_bpa_estimee"] = float(np.clip(np.mean(g_eps), -0.5, 1.0)) if g_eps else math.nan
    rest = fund.get("revenue_estimate", {}).get("+1y", {}).get("growth")
    m["croiss_ca_estimee"] = float(np.clip(rest, -0.5, 1.0)) if rest is not None and np.isfinite(rest) else math.nan
    m["nb_analystes"] = info.get("numberOfAnalystOpinions")
    m["reco_analystes"] = info.get("recommendationMean")

    # ---------------------------------------------------------------- 12 mois glissants
    rev_ttm = postes.dernier(fund, "revenue", "ttm_income")
    ebit_ttm = postes.dernier(fund, "ebit", "ttm_income")
    ni_ttm = postes.dernier(fund, "net_income", "ttm_income")
    fcf_ttm = postes.dernier(fund, "fcf", "ttm_cashflow")
    sbc_ttm = postes.dernier(fund, "sbc", "ttm_cashflow")
    if not np.isfinite(rev_ttm):
        rev_ttm = last.get("revenue", math.nan)
    if not np.isfinite(ebit_ttm):
        ebit_ttm = ebit_last
    if not np.isfinite(ni_ttm):
        ni_ttm = last.get("net_income", math.nan)
    if not np.isfinite(fcf_ttm):
        fcf_ttm = fcf.iloc[-1] if len(fcf) else math.nan
    nopat_ttm = ebit_ttm * (1 - tax_rate)
    m["benefice_ttm"] = ni_ttm
    m["nopat_ttm"] = nopat_ttm

    # ---------------------------------------------------------------- valorisation
    px = prices[ticker].dropna() if ticker in prices.columns else pd.Series(dtype=float)
    pm = price_metrics(px)
    m.update(pm)
    info_px = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    mcap_quote = info.get("marketCap") or math.nan
    # La fiche Yahoo date de son téléchargement (jusqu'à une semaine) : tout ce qui dépend du cours
    # (capitalisation, PER prospectif, objectif des analystes) est remis au dernier cours.
    recalage = pm["cours"] / info_px if np.isfinite(pm["cours"]) and info_px else 1.0
    mcap_quote = mcap_quote * recalage
    quote_major = split_currency(quote_cur)[0]
    mcap_fin = mcap_quote * fx_rate(fx, quote_major, fin_cur)
    m["capitalisation_eur"] = mcap_quote * fx_rate(fx, quote_major, "EUR")
    ev = mcap_fin + net_debt
    m["valeur_entreprise"] = ev
    m["dette_nette"] = net_debt
    m["rendement_fcf"] = _safe_div(fcf_ttm, mcap_fin) if not fin_flag else math.nan
    m["rendement_fcf_hors_sbc"] = (_safe_div(fcf_ttm - (sbc_ttm if np.isfinite(sbc_ttm) else 0), mcap_fin)
                                   if not fin_flag else math.nan)
    m["rendement_benefices"] = _safe_div(ni_ttm, mcap_fin) if fin_flag else _safe_div(ebit_ttm, ev)
    m["per"] = _safe_div(mcap_fin, ni_ttm) if ni_ttm and ni_ttm > 0 else math.nan
    m.update(health_scores(fund, mcap_fin, fin_flag))
    m["moat_points"] = (moat_points(roic, a5["gross_profit"] / rev, op_margin) if not fin_flag and len(a5) else math.nan)
    m["moat"] = moat_label(m["moat_points"])
    m.update(criteres.resume(criteres.evaluer(fund, sec_data, financiere=fin_flag, seuils=strat.get("criteres"),
                                              tresorerie_clients=clients, h=h)))
    m.update(sec.recoupement(fund, sec_data, sans_ca=fin_flag or "REIT" in str(info.get("industry"))))
    m["per_historique"] = (historical_multiple(a, prices[ticker], mcap_fin, fx, quote_cur, fin_cur)
                           if ticker in prices.columns and len(a) else math.nan)
    m["ecart_per_historique"] = _safe_div(m["per"], m["per_historique"]) - 1
    # Prix / flux de trésorerie disponible : sans objet pour les financières (leur « flux » mêle dépôts et crédits).
    m["p_fcf"] = _safe_div(mcap_fin, fcf_ttm) if not fin_flag and fcf_ttm > 0 else math.nan
    m["p_fcf_historique"] = (historical_multiple(a.assign(fcf=fcf), prices[ticker], mcap_fin, fx, quote_cur, fin_cur, col="fcf")
                             if not fin_flag and ticker in prices.columns and len(a) else math.nan)
    m["ecart_p_fcf_historique"] = _safe_div(m["p_fcf"], m["p_fcf_historique"]) - 1
    # P/FCF hors rémunérations en actions (SBC) : ces actions gratuites sont un vrai coût, payé en dilution
    # plutôt qu'en cash. Sans SBC publiées pour la société (fréquent hors des États-Unis), elles comptent pour 0.
    fcf_net = fcf - a["sbc"] if a["sbc"].notna().any() else fcf
    fcf_net_ttm = fcf_ttm - (sbc_ttm if np.isfinite(sbc_ttm) else 0)
    m["p_fcf_net"] = _safe_div(mcap_fin, fcf_net_ttm) if not fin_flag and fcf_net_ttm > 0 else math.nan
    m["p_fcf_net_historique"] = (historical_multiple(a.assign(fcf_net=fcf_net), prices[ticker], mcap_fin, fx, quote_cur, fin_cur,
                                                     col="fcf_net")
                                 if not fin_flag and ticker in prices.columns and len(a) else math.nan)
    m["ecart_p_fcf_net_historique"] = _safe_div(m["p_fcf_net"], m["p_fcf_net_historique"]) - 1
    m["capitalisation_comptes"] = mcap_fin  # dans la devise des comptes : base des multiples
    m["p_ca"] = _safe_div(mcap_fin, rev_ttm) if rev_ttm and rev_ttm > 0 else math.nan  # prix / chiffre d'affaires
    # CA des 12 derniers mois comparé au dernier exercice clos, quand il couvre une période plus récente : Yahoo ne
    # donne qu'un point « 12 mois », d'où cette approximation de la tendance récente (règles de vente).
    ca_12m = postes.serie(fund, "revenue", "ttm_income")
    ca_an = postes.serie(fund, "revenue")
    recent = len(ca_12m) and len(ca_an) and (ca_12m.index[-1] - ca_an.index[-1]).days >= 80
    m["evol_ca_12m"] = _safe_div(float(ca_12m.iloc[-1]), float(ca_an.iloc[-1])) - 1 if recent and ca_an.iloc[-1] > 0         else math.nan
    fpe = info.get("forwardPE")
    fpe = fpe * recalage if fpe else fpe
    m["per_prospectif"] = fpe if fpe and 0 < fpe < 250 else math.nan
    # Yahoo divise parfois le cours par un bénéfice d'avant division d'actions, ou d'une autre devise :
    # un PER prospectif très bas que la croissance attendue n'explique pas est écarté.
    g_bpa = m.get("croiss_bpa_estimee")
    g_bpa = max(g_bpa, -0.5) if g_bpa is not None and math.isfinite(g_bpa) else 0.0
    if fpe and fpe < 6 and math.isfinite(m["per"]) and m["per"] > 3 * fpe * (1 + g_bpa):
        m["per_prospectif"] = math.nan
    m["holding"] = ticker in cas["holding"]
    if m["holding"]:
        # Le résultat d'une holding mélange plus-values latentes et dividendes : il ne dit rien du prix
        # payé. La valorisation se juge sur la décote par rapport à l'actif net (hors de portée de Yahoo).
        m["rendement_benefices"] = m["per"] = m["per_prospectif"] = math.nan
    div = abs(last.get("dividends", math.nan)) if np.isfinite(last.get("dividends", math.nan)) else 0.0
    buy = abs(last.get("buybacks", math.nan)) if np.isfinite(last.get("buybacks", math.nan)) else 0.0
    m["rendement_dividende"] = _safe_div(div, mcap_fin)
    m["rendement_actionnaire"] = _safe_div(div + buy, mcap_fin)

    vcfg = strat["valorisation"]
    r, g_term = vcfg["taux_actualisation"], vcfg["croissance_terminale"]
    # Le ROIC comptable inclut les écarts d'acquisition : il sous-estime la rentabilité des nouveaux
    # investissements des groupes acquéreurs (SAP, Air Liquide…). D'où un plancher, et un plafond prudent.
    roic_used = m["rentabilite"]
    roic_used = min(max(roic_used if np.isfinite(roic_used) else vcfg.get("roic_incremental_min", 0.12),
                        vcfg.get("roic_incremental_min", 0.12)), vcfg["roic_incremental_max"])
    base = ni_ttm if fin_flag else nopat_ttm
    target = mcap_fin if fin_flag else ev
    kw = dict(g_term=g_term, roic=roic_used, years_high=vcfg["annees_croissance"], years_fade=vcfg["annees_convergence"])
    m["croissance_attendue"] = expected_growth(m, vcfg["croissance_max"])
    if base and base > 0 and target and target > 0 and not m["holding"]:
        m["croissance_implicite"] = implied_growth(target, base, r=r, **kw)
        g = m["croissance_attendue"] if np.isfinite(m["croissance_attendue"]) else 0.05
        m["tri_implicite"] = implied_irr(target, base, g, **kw)
    else:
        m["croissance_implicite"] = math.nan
        m["tri_implicite"] = math.nan
    m["marge_securite_croissance"] = m["croissance_attendue"] - m["croissance_implicite"]
    cours = pm["cours"] if np.isfinite(pm["cours"]) else info_px
    m["objectif_analystes"] = _safe_div(info.get("targetMeanPrice"), cours) - 1 if cours else math.nan
    return m


def compute_all(tickers: list[str] | None = None, save: bool = True) -> pd.DataFrame:
    universe = load_universe()
    tickers = tickers or all_tracked_tickers()  # univers + lignes détenues hors univers
    prices, fx, strat = load_prices(), load_fx(), load_strategy()
    funds, cas = fund_tickers(), load_cas_particuliers()
    corrections = homme_cle.load_ajustements()
    rows = []
    for t in tickers:
        if t in funds:
            pm = price_metrics(prices[t]) if t in prices.columns else {}
            rows.append({"ticker": t, "fonds": True, "financiere": False, "holding": False, "devise": currency_map([t])[t],
                         "statut_donnees": "ok" if np.isfinite(pm.get("cours", np.nan)) else "absentes", **pm})
            continue
        fund = load_fundamentals(t)  # None aussi pour une fiche illisible : elle sera retéléchargée
        if not fund:
            rows.append({"ticker": t, "statut_donnees": "absentes"})
            continue
        try:
            m = compute_one(t, fund, prices, fx, strat, cas)
            m["statut_donnees"] = "ok" if m["nb_exercices"] >= 3 else "partielles"
        except Exception as exc:  # une valeur en erreur ne doit pas arrêter le calcul des autres
            m = {"ticker": t, "statut_donnees": f"erreur : {exc}"[:120]}
        info = fund.get("info", {})
        m["nom_yahoo"] = info.get("shortName") or info.get("longName")
        m["industrie"] = info.get("industry")
        m.update(homme_cle.evaluer(info, *corrections.get(t, (0.0, ""))))
        rows.append(m)
    df = pd.DataFrame(rows).set_index("ticker")
    meta = universe.reindex(df.index)[["nom", "pays", "enveloppe", "secteur", "profil"]]
    df = meta.join(df)
    df["nom"] = df["nom"].where(df["nom"].astype(str).str.len() > 0, df.get("nom_yahoo"))
    if save:
        out = df.copy()
        for col in out.columns:
            if out[col].dtype == object:
                # Un indicateur vrai/faux avec des trous (fonds, données absentes) reste booléen :
                # converti en texte, « False » serait évalué comme vrai.
                vals = out[col].dropna()
                is_bool = len(vals) > 0 and vals.map(lambda v: isinstance(v, (bool, np.bool_))).all()
                out[col] = out[col].astype("boolean" if is_bool else "string")
        ecriture_atomique(METRICS_PARQUET, out.to_parquet)
        ecrire_json(METRICS_META, {"valorisation": strat["valorisation"]}, indent=1)
    return df


def load_metrics() -> pd.DataFrame:
    try:
        return pd.read_parquet(METRICS_PARQUET) if METRICS_PARQUET.exists() else pd.DataFrame()
    except (OSError, ValueError):
        return pd.DataFrame()


def metrics_a_jour(strat: dict | None = None) -> bool:
    """Vrai si les indicateurs ont été calculés avec les paramètres de valorisation actuels."""
    meta = lire_json(METRICS_META, {}) or {}
    return meta.get("valorisation") == (strat or load_strategy())["valorisation"]
