"""Moat estimé : une approximation chiffrée de l'avantage concurrentiel.

Le moat de Morningstar est un jugement d'analystes sous licence. Celui-ci ne mesure que les traces
d'un avantage dans les comptes : une rentabilité élevée, tenue dans le temps, et des prix défendus.
Quatre exercices sont courts pour juger de la durabilité, et il ne dit rien de la cause de l'avantage.
Non calculé pour les banques, assureurs et holdings : leur rentabilité suit surtout les taux et les marchés.
"""
from __future__ import annotations

import math

import pandas as pd

ROIC_MOYEN_MIN = 0.15  # nettement au-dessus du coût du capital (9 %)
ROIC_PIRE_ANNEE_MIN = 0.12
MARGE_BRUTE_MIN = 0.40
ECART_MARGE_OP_MAX = 0.03
EROSION_MARGE_BRUTE_MAX = 0.02
EROSION_ROIC_MAX = 0.20  # le dernier ROIC doit rester à au moins 80 % du premier
CRITERES = 6


def moat_points(roic: pd.Series, gross_margin: pd.Series, op_margin: pd.Series) -> float:
    """Points de 0 à 6, ramenés sur 6 s'il manque des critères. NaN sous 3 exercices ou 4 critères."""
    r, gm, om = roic.dropna(), gross_margin.dropna(), op_margin.dropna()
    if len(r) < 3:
        return math.nan
    # Rebondir après une année de pertes n'est pas tenir ses positions : pas de point « sans érosion ».
    sans_perte = r.min() >= 0
    criteres = [r.mean() >= ROIC_MOYEN_MIN, r.min() >= ROIC_PIRE_ANNEE_MIN,
                sans_perte and r.iloc[-1] >= (1 - EROSION_ROIC_MAX) * r.iloc[0]]
    if len(gm) >= 3:
        criteres += [gm.mean() >= MARGE_BRUTE_MIN, sans_perte and gm.iloc[-1] >= gm.iloc[0] - EROSION_MARGE_BRUTE_MAX]
    if len(om) >= 3:
        criteres.append(om.std() <= ECART_MARGE_OP_MAX)
    if len(criteres) < 4:
        return math.nan
    return float(round(sum(bool(c) for c in criteres) * CRITERES / len(criteres)))


def moat_label(points: float) -> str | None:
    if math.isnan(points):
        return None
    return "Large" if points >= 5 else "Étroit" if points >= 3 else "Faible"
