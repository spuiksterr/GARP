"""Simulateur « et si j'ajoute cette ligne ? » : effet d'un ajout, d'un retrait ou d'un changement de poids sur
le portefeuille réel (ticket C-01).

Les autres lignes sont ajustées en proportion pour que le total reste à 100 %. Mesures du passé (3 ans de cours en
euros, poids d'aujourd'hui) : elles montrent où le risque se concentre, pas ce qui arrivera.
"""
from __future__ import annotations

import math

import pandas as pd

from . import risques
from .portfolio import breakdown, risk_profile


def nouveaux_poids(w: pd.Series, ticker: str, poids: float) -> pd.Series:
    """Poids après le changement : `ticker` à `poids` (0 = retrait), les autres lignes réduites en proportion."""
    w = w / w.sum()
    autres = w.drop(ticker, errors="ignore")
    if autres.sum() <= 0:
        return pd.Series({ticker: 1.0})
    poids = min(max(poids, 0.0), 1.0)
    out = autres / autres.sum() * (1 - poids)
    if poids > 0:
        out[ticker] = poids
    return out.sort_values(ascending=False)


def _mesures(w: pd.Series, r: pd.DataFrame, benchmark: str, est_fonds: dict[str, str]) -> dict:
    cols = [c for c in w.index if c in r.columns]
    poids = w[cols] / w[cols].sum() if cols else w
    r_p = (r[cols].fillna(0) @ poids) if cols else pd.Series(dtype="float64")
    conc = risques.concentration(w)
    sce = risques.scenarios(w, r, benchmark, est_fonds).set_index("scenario")["impact"]
    return {
        "Plus grosse ligne": conc["poids_plus_grosse"],
        "Trois premières lignes": conc["trois_premieres"],
        "Nombre effectif de lignes": conc["nombre_effectif"],
        "Volatilité annuelle": risk_profile(w, returns=r).get("volatilite", math.nan),
        "Perte maximale (3 ans)": risques.perte_maximale(r_p),
        "Corrélation moyenne entre lignes": risques.correlation_moyenne(r, list(w.index)),
        **{f"Scénario : {k}": float(v) for k, v in sce.items()},
    }


def simuler(w: pd.Series, ticker: str, poids: float, screener: pd.DataFrame, benchmark: str = "IWDA.AS",
            est_fonds: dict[str, str] | None = None, r: pd.DataFrame | None = None) -> dict:
    """Avant / après pour un changement de poids d'une ligne.

    Renvoie : "poids" (avant, après), "mesures" (indicateur -> avant, après), "secteurs" et "devises" (avant, après),
    "correlations" (corrélation de `ticker` avec chaque autre ligne, de la plus forte à la plus faible).
    """
    est_fonds = est_fonds or {}
    avant = w / w.sum()
    apres = nouveaux_poids(avant, ticker, poids)
    if r is None:
        _, r = risques.rendements(avant.add(apres, fill_value=0), benchmark=benchmark)

    def cote_a_cote(a, b) -> pd.DataFrame:
        return pd.DataFrame({"avant": a, "apres": b}).fillna(0.0).sort_values("apres", ascending=False)

    mesures = pd.DataFrame({"avant": _mesures(avant, r, benchmark, est_fonds),
                            "apres": _mesures(apres, r, benchmark, est_fonds)})
    autres = [t for t in avant.index if t != ticker and t in r.columns]
    correlations = (r[autres].corrwith(r[ticker]).sort_values(ascending=False) if ticker in r.columns and autres
                    else pd.Series(dtype="float64"))
    return {"poids": cote_a_cote(avant, apres), "mesures": mesures,
            "secteurs": cote_a_cote(breakdown(avant, screener, "secteur"), breakdown(apres, screener, "secteur")),
            "devises": cote_a_cote(risques.devises(avant), risques.devises(apres)),
            "correlations": correlations}
