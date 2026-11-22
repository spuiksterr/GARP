"""Valorisation par les « value drivers » : la croissance coûte du capital.

Flux disponible de l'année t : FCF_t = NOPAT_t × (1 − g_{t+1} / ROIC_incrémental)
(l'investissement d'une année finance la croissance de l'année suivante ; il peut dépasser le
résultat, le flux devient alors négatif et l'entreprise doit lever des fonds)
- années 1..N  : croissance g (phase de croissance)
- années N+1..N+M : convergence linéaire vers la croissance terminale
- valeur terminale : NOPAT_{n+1} × (1 − g_term / ROIC) / (r − g_term)

Avec ROIC = r, la valeur vaut NOPAT_1 / r quelle que soit la croissance future : croître sans
rentabilité supérieure au coût du capital ne crée rien (formule de McKinsey, « Valuation »).

Deux usages inverses :
- croissance implicite : quelle croissance le cours actuel suppose-t-il ? (DCF inversé, à la Mauboussin)
- TRI implicite : quel rendement annuel obtient-on si la croissance attendue se réalise ?
"""
from __future__ import annotations

import math


def value_driver_ev(
    base: float,
    g_high: float,
    r: float,
    g_term: float = 0.03,
    roic: float = 0.20,
    years_high: int = 5,
    years_fade: int = 5,
) -> float:
    """Valeur d'entreprise actualisée d'un flux de NOPAT `base` (12 derniers mois)."""
    if r <= g_term:
        return math.inf
    n = years_high + years_fade

    def growth(t: int) -> float:
        if t <= years_high:
            return g_high
        if t <= n:
            return g_high + (g_term - g_high) * (t - years_high) / max(years_fade, 1)
        return g_term

    nopat = base
    pv = 0.0
    for t in range(1, n + 1):
        nopat *= 1 + growth(t)
        reinvest = max(growth(t + 1) / roic, -0.5)  # une activité en déclin libère du capital, sans excès
        pv += nopat * (1 - reinvest) / (1 + r) ** t
    terminal = nopat * (1 + g_term) * (1 - g_term / roic) / (r - g_term)
    return pv + terminal / (1 + r) ** n


def implied_growth(
    target_ev: float,
    base: float,
    r: float = 0.09,
    g_term: float = 0.03,
    roic: float = 0.20,
    years_high: int = 5,
    years_fade: int = 5,
    bounds: tuple[float, float] = (-0.20, 0.80),
) -> float:
    """Croissance annuelle (phase 1) qui justifie exactement la valeur d'entreprise actuelle."""
    if not (base > 0 and target_ev > 0):
        return math.nan

    def gap(g):
        return value_driver_ev(base, g, r, g_term, roic, years_high, years_fade) - target_ev

    lo, hi = bounds
    if gap(lo) > 0:
        return lo
    if gap(hi) < 0:
        return hi
    from scipy.optimize import brentq  # import différé : scipy pèse 3 s au démarrage

    return brentq(gap, lo, hi, xtol=1e-5)


def implied_irr(
    target_ev: float,
    base: float,
    g_high: float,
    g_term: float = 0.03,
    roic: float = 0.20,
    years_high: int = 5,
    years_fade: int = 5,
    r_max: float = 0.40,
) -> float:
    """Rendement annuel implicite (TRI) si la croissance `g_high` se matérialise."""
    if not (base > 0 and target_ev > 0):
        return math.nan
    lo = g_term + 0.005

    def gap(r):
        return value_driver_ev(base, g_high, r, g_term, roic, years_high, years_fade) - target_ev

    if gap(lo) < 0:
        return lo
    if gap(r_max) > 0:
        return r_max
    from scipy.optimize import brentq

    return brentq(gap, lo, r_max, xtol=1e-5)


def fair_value_per_share(
    base: float,
    g_high: float,
    r: float,
    net_debt: float,
    shares: float,
    g_term: float = 0.03,
    roic: float = 0.20,
    years_high: int = 5,
    years_fade: int = 5,
) -> float:
    """Valeur intrinsèque par action (devise des comptes) = (VE modélisée − dette nette) / actions."""
    if not (base > 0 and shares > 0):
        return math.nan
    ev = value_driver_ev(base, g_high, r, g_term, roic, years_high, years_fade)
    return (ev - net_debt) / shares
