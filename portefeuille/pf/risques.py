"""Risques du portefeuille réel : concentration, devises, corrélations, pertes passées et scénarios de choc.

Poids : les positions du journal (valeur de marché du jour), à défaut les poids cibles. Historique : 3 ans de
cours en euros, avec les poids d'aujourd'hui (le portefeuille réel n'a pas forcément eu ces poids).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import load_strategy
from .data import currency_map, split_currency
from .portfolio import model_weights, returns_eur

ANNEES = 3


def poids_actuels() -> tuple[pd.Series, str]:
    """(poids par ticker, source) : positions réelles si le journal en contient, sinon poids cibles."""
    try:
        from .tracker import positions

        p = positions()
        if not p.empty and p["valeur_eur"].sum() > 0:
            w = p.groupby("ticker")["valeur_eur"].sum()
            return (w / w.sum()).sort_values(ascending=False), "positions réelles (valeur de marché du jour)"
    except Exception:
        pass
    w = model_weights()
    return (w / w.sum()).sort_values(ascending=False), "poids cibles (aucune position enregistrée)"


def concentration(w: pd.Series) -> dict:
    w = w.sort_values(ascending=False)
    return {"plus_grosse": w.index[0], "poids_plus_grosse": float(w.iloc[0]), "trois_premieres": float(w.head(3).sum()),
            "nombre_effectif": float(1 / (w ** 2).sum()), "lignes_au_dessus_10": int((w > 0.10).sum())}


def devises(w: pd.Series) -> pd.Series:
    """Poids par devise de cotation (pence ramenés à la livre)."""
    cur = currency_map(list(w.index))
    return w.groupby(lambda t: split_currency(cur.get(t, "EUR"))[0]).sum().sort_values(ascending=False)


def rendements(w: pd.Series, annees: float = ANNEES, benchmark: str | None = None) -> tuple[pd.Series, pd.DataFrame]:
    """(rendements quotidiens du portefeuille aux poids d'aujourd'hui, rendements des lignes et de l'indice)."""
    bench = benchmark or load_strategy().get("suivi", {}).get("benchmark", "IWDA.AS")
    r = returns_eur(list(w.index) + [bench], annees)
    cols = [c for c in w.index if c in r.columns]
    if not cols:
        return pd.Series(dtype="float64"), r
    poids = w[cols] / w[cols].sum()
    return (r[cols].fillna(0) @ poids).rename("portefeuille"), r


def perte_maximale(r: pd.Series) -> float:
    if r.empty:
        return math.nan
    valeur = (1 + r).cumprod()
    return float((valeur / valeur.cummax() - 1).min())


def pire_mois(r: pd.Series) -> tuple[pd.Timestamp | None, float]:
    if r.empty:
        return None, math.nan
    mois = (1 + r).resample("ME").prod() - 1
    return mois.idxmin(), float(mois.min())


def betas(r: pd.DataFrame, lignes: list[str], benchmark: str) -> pd.Series:
    """Sensibilité de chaque ligne à l'indice : 1,2 = varie en moyenne de 12 % quand l'indice varie de 10 %."""
    if benchmark not in r.columns:
        return pd.Series(dtype="float64")
    b = r[benchmark]
    var = b.var()
    return pd.Series({t: float(r[t].cov(b) / var) if t in r.columns and var > 0 else math.nan for t in lignes})


def scenarios(w: pd.Series, r: pd.DataFrame, benchmark: str, est_fonds: dict[str, str]) -> pd.DataFrame:
    """Pertes estimées sous quelques chocs simples, avec la contribution de chaque ligne.

    - marché mondial -30 % : chaque ligne bouge selon son bêta (sensibilité passée à l'indice) ;
    - dollar -10 % face à l'euro : les lignes cotées en dollar perdent 10 % en euros, le reste est inchangé ;
    - or -20 % : les fonds d'or perdent 20 %.
    """
    bt = betas(r, list(w.index), benchmark)
    dev = currency_map(list(w.index))
    lignes = []
    choc_marche = (w * bt.reindex(w.index).fillna(1.0) * -0.30)
    lignes.append(("Marché mondial -30 %", float(choc_marche.sum()), choc_marche))
    usd = pd.Series({t: -0.10 * w[t] if split_currency(dev.get(t, "EUR"))[0] == "USD" else 0.0 for t in w.index})
    lignes.append(("Dollar -10 % face à l'euro", float(usd.sum()), usd))
    or_ = pd.Series({t: -0.20 * w[t] if est_fonds.get(t) == "or" else 0.0 for t in w.index})
    if or_.abs().sum() > 0:
        lignes.append(("Or -20 %", float(or_.sum()), or_))
    out = []
    for nom, total, contrib in lignes:
        principal = contrib.idxmin() if contrib.min() < 0 else None
        out.append({"scenario": nom, "impact": total, "ligne": principal,
                    "effet_ligne": float(contrib[principal]) if principal else math.nan})
    return pd.DataFrame(out)


# Seuils par défaut, réglables dans config/strategie.json (suivi.garde_fous).
GARDE_FOUS = {"ligne_max": 0.25, "trois_premieres_max": 0.60, "secteur_max": 0.40, "correlation_moyenne_max": 0.50}
EPS = 1e-9  # 3 x 20 % ne dépasse pas un seuil de 60 %


def seuils_garde_fous(strat: dict | None = None) -> dict:
    strat = strat if strat is not None else load_strategy()
    return {**GARDE_FOUS, **strat.get("suivi", {}).get("garde_fous", {})}


def garde_fous(w: pd.Series, secteurs: pd.Series, r: pd.DataFrame | None = None,
               seuils: dict | None = None) -> list[tuple[str, str]]:
    """Seuils de concentration dépassés : (ticker concerné, ou "" pour le portefeuille, message).

    `secteurs` : secteur par ticker. `r` : rendements des lignes, pour la corrélation moyenne (sautée sans eux).
    """
    from .formats import nombre, pct
    s = seuils or seuils_garde_fous()
    w = (w / w.sum()).sort_values(ascending=False)
    out = []
    for t, p in w[w > s["ligne_max"] + EPS].items():
        out.append((t, f"pèse {pct(p, 0)} du portefeuille (seuil {pct(s['ligne_max'], 0)}) : une mauvaise nouvelle "
                       "sur cette seule valeur se verrait sur l'ensemble."))
    if len(w) > 3 and w.head(3).sum() > s["trois_premieres_max"] + EPS:
        out.append(("", f"Les trois premières lignes font {pct(w.head(3).sum(), 0)} du portefeuille "
                        f"(seuil {pct(s['trois_premieres_max'], 0)})."))
    par_secteur = w.groupby(lambda t: secteurs.get(t, "Autre")).sum()
    for sec, p in par_secteur[par_secteur > s["secteur_max"] + EPS].items():
        out.append(("", f"Le secteur {sec} fait {pct(p, 0)} du portefeuille (seuil {pct(s['secteur_max'], 0)})."))
    if r is not None:
        c = correlation_moyenne(r, list(w.index))
        if not math.isnan(c) and c > s["correlation_moyenne_max"] + EPS:
            out.append(("", f"Corrélation moyenne de {nombre(c, 2)} entre les lignes (seuil "
                            f"{nombre(s['correlation_moyenne_max'], 2)}) : elles montent et baissent ensemble."))
    return out


def correlation_moyenne(r: pd.DataFrame, lignes: list[str]) -> float:
    cols = [c for c in lignes if c in r.columns]
    if len(cols) < 2:
        return math.nan
    c = r[cols].corr().values
    return float(c[np.triu_indices_from(c, k=1)].mean())
