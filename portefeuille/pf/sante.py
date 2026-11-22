"""Trois signaux de santé tirés des comptes annuels : Piotroski, Altman et Beneish.

Ils alertent et s'affichent comme repères, hors note GARP et hors filtres. Leurs formules supposent
un bilan d'entreprise classique, ils ne sont donc pas calculés pour les banques, assureurs et holdings.
"""
from __future__ import annotations

import math

import pandas as pd

from . import postes
from .formats import nombre

SEUIL_PIOTROSKI_FAIBLE = 2  # sur 9
SEUIL_ALTMAN_DANGER = 1.81
SEUIL_ALTMAN_SUR = 2.99
SEUIL_BENEISH = -1.78  # au-dessus : profil proche des manipulateurs comptables (Beneish, Lee et Nichols, 2013)
BENEISH_SAIN = -2.22
PLAFOND_INDICE_BENEISH = 5.0  # une acquisition ou un paiement ponctuel ne doit pas écraser les autres variables

# Postes utiles (voir postes.py). « shares » est ici le nombre d'actions en fin d'exercice, et non la
# moyenne diluée : Piotroski compte les actions émises dans l'année.
LIGNES = ("net_income", "revenue", "gross_profit", "ebit", "sga", "depreciation", "ocf", "assets", "current_assets",
          "current_liabilities", "liabilities", "long_term_debt", "retained", "receivables", "ppe", "shares")


def statements(fund: dict) -> pd.DataFrame:
    """Lignes utiles par exercice, du plus ancien au plus récent (comptes Yahoo seuls : deux exercices suffisent)."""
    df = postes.table(fund, [c if c != "shares" else "shares_outstanding" for c in LIGNES])
    df = df.rename(columns={"shares_outstanding": "shares"})
    if df.empty:
        return df
    return df.dropna(subset=["assets", "revenue"], how="any")


def _div(a: float, b: float) -> float:
    return a / b if b and math.isfinite(a) and math.isfinite(b) else math.nan


def _test(ok: bool, *values: float) -> float:
    """1 ou 0 selon le critère, NaN si une donnée manque."""
    return float(ok) if all(math.isfinite(v) for v in values) else math.nan


def piotroski(cur: pd.Series, prev: pd.Series) -> float:
    """F-Score de 0 à 9 : la situation s'améliore-t-elle ? NaN s'il manque plus d'un critère."""
    roa, roa0 = _div(cur.net_income, cur.assets), _div(prev.net_income, prev.assets)
    # Pas de ligne de dette longue : l'entreprise n'en a pas.
    debt, debt0 = [0.0 if math.isnan(x) else x for x in (cur.long_term_debt, prev.long_term_debt)]
    lev, lev0 = _div(debt, cur.assets), _div(debt0, prev.assets)
    liq, liq0 = _div(cur.current_assets, cur.current_liabilities), _div(prev.current_assets, prev.current_liabilities)
    gm, gm0 = _div(cur.gross_profit, cur.revenue), _div(prev.gross_profit, prev.revenue)
    turn, turn0 = _div(cur.revenue, cur.assets), _div(prev.revenue, prev.assets)
    criteres = [
        _test(roa > 0, roa),
        _test(cur.ocf > 0, cur.ocf),
        _test(roa > roa0, roa, roa0),
        _test(cur.ocf > cur.net_income, cur.ocf, cur.net_income),
        _test(lev <= lev0, lev, lev0),
        _test(liq > liq0, liq, liq0),
        _test(cur.shares <= prev.shares * 1.005, cur.shares, prev.shares),  # tolérance : arrondis et plans salariés
        _test(gm > gm0, gm, gm0),
        _test(turn > turn0, turn, turn0),
    ]
    connus = [c for c in criteres if not math.isnan(c)]
    return float(round(sum(connus) * 9 / len(connus))) if len(connus) >= 8 else math.nan


def altman(cur: pd.Series, market_cap: float) -> float:
    """Z-Score d'origine (1968), avec la capitalisation boursière dans la devise des comptes."""
    wc = _div(cur.current_assets - cur.current_liabilities, cur.assets)
    return (1.2 * wc + 1.4 * _div(cur.retained, cur.assets) + 3.3 * _div(cur.ebit, cur.assets)
            + 0.6 * _div(market_cap, cur.liabilities) + _div(cur.revenue, cur.assets))


def beneish(cur: pd.Series, prev: pd.Series) -> float:
    """M-Score à 8 variables, les charges à payer étant mesurées par (résultat net - flux d'exploitation) / actifs.

    Les frais commerciaux manquent souvent chez Yahoo : leur indice, le moins pesant, vaut alors 1 (neutre).
    """
    def rec(s):
        return _div(s.receivables, s.revenue)

    def gm(s):
        return _div(s.gross_profit, s.revenue)

    def soft_assets(s):
        return 1 - _div(s.current_assets + s.ppe, s.assets)

    def dep_rate(s):
        return _div(s.depreciation, s.depreciation + s.ppe)

    def sga(s):
        return _div(s.sga, s.revenue)

    def lev(s):
        debt = 0.0 if math.isnan(s.long_term_debt) else s.long_term_debt
        return _div(debt + s.current_liabilities, s.assets)

    dsri, gmi, aqi = _div(rec(cur), rec(prev)), _div(gm(prev), gm(cur)), _div(soft_assets(cur), soft_assets(prev))
    sgi, depi = _div(cur.revenue, prev.revenue), _div(dep_rate(prev), dep_rate(cur))
    sgai, lvgi = _div(sga(cur), sga(prev)), _div(lev(cur), lev(prev))
    sgai = 1.0 if math.isnan(sgai) else sgai
    dsri, gmi, aqi, sgi, depi, sgai, lvgi = [x if math.isnan(x) else min(max(x, 0.0), PLAFOND_INDICE_BENEISH)
                                             for x in (dsri, gmi, aqi, sgi, depi, sgai, lvgi)]
    tata = _div(cur.net_income - cur.ocf, cur.assets)
    return (-4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi
            - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)


def health_points(df: pd.DataFrame) -> pd.DataFrame:
    """Les trois signaux ramenés sur 100 ; NaN quand le signal n'existe pas.

    Altman et Beneish servent de jauges, pas de classements : au-delà de la zone sûre, un Z plus élevé
    ne dit rien de plus. Beneish vaut 100 à -2,22 ou moins (autre seuil usuel) et 0 à -1,78 ou plus.
    """
    def col(name):
        return pd.to_numeric(df[name], errors="coerce") if name in df.columns else pd.Series(math.nan, index=df.index)

    return pd.DataFrame({
        "pts_piotroski": col("piotroski") * 100 / 9,
        "pts_altman": ((col("altman_z") - SEUIL_ALTMAN_DANGER) / (SEUIL_ALTMAN_SUR - SEUIL_ALTMAN_DANGER)).clip(0, 1) * 100,
        "pts_beneish": ((SEUIL_BENEISH - col("beneish_m")) / (SEUIL_BENEISH - BENEISH_SAIN)).clip(0, 1) * 100,
    }, index=df.index)


def health_alerts(row: pd.Series) -> list[str]:
    def v(key):
        x = pd.to_numeric(row.get(key), errors="coerce")
        return math.nan if pd.isna(x) else float(x)

    out = []
    if v("piotroski") <= SEUIL_PIOTROSKI_FAIBLE:
        out.append(f"Fondamentaux en dégradation (Piotroski {nombre(v('piotroski'), 0)}/9)")
    if v("altman_z") < SEUIL_ALTMAN_DANGER:
        out.append(f"Zone de fragilité financière (Altman {nombre(v('altman_z'), 1)})")
    if v("beneish_m") > SEUIL_BENEISH:
        out.append(f"Comptes à examiner (Beneish {nombre(v('beneish_m'), 2)})")
    if row.get("verif_sec") == "Écart":
        out.append(f"Données Yahoo contredites par la SEC ({row.get('sec_ecarts')})")
    if pd.notna(row.get("sec_retard")) and bool(row.get("sec_retard")):
        out.append("Yahoo n'a pas encore intégré le dernier rapport annuel déposé à la SEC")
    return out


def health_scores(fund: dict, market_cap: float, financial: bool) -> dict[str, float]:
    out = dict.fromkeys(["piotroski", "altman_z", "beneish_m"], math.nan)
    if financial:
        return out
    df = statements(fund)
    if df.empty:
        return out
    cur = df.iloc[-1]
    out["altman_z"] = altman(cur, market_cap)
    if len(df) >= 2:
        prev = df.iloc[-2]
        out["piotroski"] = piotroski(cur, prev)
        out["beneish_m"] = beneish(cur, prev)
    return {k: v if math.isfinite(v) else math.nan for k, v in out.items()}
