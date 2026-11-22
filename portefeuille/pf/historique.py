"""Données des graphiques de la fiche valeur : un exercice par ligne, puis les 12 derniers mois.

Tout vient de l'historique commun (postes.py) : Yahoo, prolongé par les comptes déposés à la SEC (ou les rapports ESEF en Europe) pour les
sociétés américaines, poste par poste et seulement quand le raccord est vérifié. La dernière ligne, « 12 mois »,
reprend les comptes sur 12 mois glissants et le dernier bilan trimestriel.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import postes

DOUZE_MOIS = "12 mois"


def _div(a, b):
    """Division élément par élément ; NaN quand le dénominateur est nul ou négatif."""
    return a / b.where(b > 0) if isinstance(b, pd.Series) else (a / b if b and b > 0 else math.nan)


def tableau(fund: dict, sec_data: dict | None = None) -> pd.DataFrame:
    """Une ligne par exercice (libellé : année de clôture), plus « 12 mois » ; montants dans la devise des comptes."""
    h, _ = postes.historique(fund, sec_data)
    if h.empty:
        return pd.DataFrame()
    capital = h["assets"] - h["current_liabilities"]
    t = pd.DataFrame({
        "chiffre_affaires": h["revenue"],
        "fcf": h["fcf"],
        "sbc": h["sbc"],
        "fcf_action": h["fcf"] / h["shares"],
        "roce": _div(h["op_income"], capital),
        "marge_brute": _div(h["gross_profit"], h["revenue"]),
        "marge_fcf": _div(h["fcf"], h["revenue"]),
        "actions": h["shares"],
        "dividende_action": -h["dividends"] / h["shares"],  # dividendes versés : négatifs dans le tableau des flux
        "resultat_net": h["net_income"],
        "cash": h["cash"],
        "dette": h["debt"],
    })
    t.index = [str(d.year) for d in h.index]
    t = t[~t.index.duplicated(keep="last")]

    # 12 mois glissants : seulement s'ils sont plus récents que le dernier exercice.
    ttm_ca = postes.serie(fund, "revenue", "ttm_income")
    if len(ttm_ca) and ttm_ca.index[-1] > h.index[-1] + pd.Timedelta(days=20):
        actions = h["shares"].dropna().iloc[-1] if h["shares"].notna().any() else math.nan
        ca = float(ttm_ca.iloc[-1])
        fcf = postes.dernier(fund, "fcf", "ttm_cashflow")
        bilan_actifs = postes.dernier(fund, "assets", "balance_q")
        passifs = postes.dernier(fund, "current_liabilities", "balance_q")
        bilan = postes.dernier_bilan(fund)
        t.loc[DOUZE_MOIS] = {
            "chiffre_affaires": ca, "fcf": fcf, "sbc": postes.dernier(fund, "sbc", "ttm_cashflow"),
            "fcf_action": fcf / actions if actions else math.nan,
            "roce": _div(postes.dernier(fund, "op_income", "ttm_income"), bilan_actifs - passifs),
            "marge_brute": _div(postes.dernier(fund, "gross_profit", "ttm_income"), ca),
            "marge_fcf": _div(fcf, ca), "actions": actions,
            "dividende_action": -postes.dernier(fund, "dividends", "ttm_cashflow") / actions if actions else math.nan,
            "resultat_net": postes.dernier(fund, "net_income", "ttm_income"),
            "cash": bilan[1] if bilan else math.nan, "dette": bilan[0] if bilan else math.nan,
        }
    return t.replace([np.inf, -np.inf], np.nan)


def croissance(t: pd.DataFrame, col: str, annees: int) -> float:
    """Croissance annuelle sur exactement `annees` ans d'exercices clos (sans les 12 mois) ; NaN sinon."""
    s = t.loc[[i for i in t.index if i != DOUZE_MOIS], col].dropna()
    if s.empty:
        return math.nan
    s.index = pd.to_datetime([f"{i}-12-31" for i in s.index])
    w = postes.fenetre(s, annees)
    if w is None or w[2] < annees - 0.5 or not (w[0] > 0 and w[1] > 0):
        return math.nan
    return (w[1] / w[0]) ** (1 / w[2]) - 1


def taux_distribution(t: pd.DataFrame) -> float:
    """Dividendes versés / résultat net, sur la dernière ligne (12 mois si disponibles)."""
    if t.empty:
        return math.nan
    r = t.iloc[-1]
    return _div(r["dividende_action"] * r["actions"], r["resultat_net"])
