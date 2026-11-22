"""Note sur 5 selon quatre regards d'investisseurs, pour passer une longue liste au crible.

Chaque note part d'une règle fixe appliquée aux indicateurs, puis peut être corrigée à la main dans
config/regards_ajustements.csv pour ce que les chiffres ne voient pas : pic de cycle, réglementation,
risque pays. Ce n'est pas une analyse : seule /analyse-valeur vérifie les faits récents.
"""
from __future__ import annotations

import math

import pandas as pd

from .config import CONFIG_DIR, read_csv_fr

AJUSTEMENTS_CSV = CONFIG_DIR / "regards_ajustements.csv"
REGARDS = ["buffett", "munger", "fisher", "smith"]


def _v(row: pd.Series, key: str) -> float:
    try:
        v = float(row.get(key))
    except (TypeError, ValueError):
        return math.nan
    return v if math.isfinite(v) else math.nan


def base_notes(row: pd.Series) -> dict[str, int]:
    """Notes de 1 à 5 tirées des seuls chiffres. Une donnée absente ne rapporte aucun point."""
    fin = row.get("financiere")
    fin = False if pd.isna(fin) else bool(fin)
    rent, tri, g = _v(row, "rentabilite"), _v(row, "tri_implicite"), _v(row, "croissance_attendue")
    stab = _v(row, "stabilite_marge")
    # Buffett : une bonne entreprise, à un prix qui laisse une marge face aux 9 % exigés.
    buffett = 1 + (rent >= 0.15) + (rent >= 0.30) + (tri >= 0.10) + (tri >= 0.14)
    # Munger : on part de 5 et on retire ce qui peut faire perdre la moitié de la mise.
    munger = 5 - sum([_v(row, "volatilite") > 0.45, _v(row, "drawdown_max_3a") < -0.50, _v(row, "dette_nette_ebitda") > 2,
                      stab > 0.05, _v(row, "perf_12m") > 1.0, fin])
    # Fisher : la croissance à venir, et un capital rendu plutôt que dilué.
    fisher = 1 + (g >= 0.06) + (g >= 0.10) + (g >= 0.16) + (_v(row, "evolution_actions") <= -0.02)
    # Smith : rentabilité durable et transformée en cash ; il évite les bilans à effet de levier.
    if fin:
        smith = min(3, 1 + (rent >= 0.15) + (rent >= 0.30) + (_v(row, "per_prospectif") <= 12))
    else:
        smith = (1 + (rent >= 0.15) + (rent >= 0.30) + (_v(row, "conversion_fcf") >= 1) + (_v(row, "rendement_fcf") >= 0.05)
                 - (_v(row, "marge_operationnelle") < 0.15) - (stab > 0.05))
    notes = dict(zip(REGARDS, (buffett, munger, fisher, smith)))
    return {k: int(min(5, max(1, v))) for k, v in notes.items()}


def load_adjustments() -> pd.DataFrame:
    if not AJUSTEMENTS_CSV.exists():
        return pd.DataFrame(columns=[*REGARDS, "motif"])
    return read_csv_fr(AJUSTEMENTS_CSV, numeric=tuple(REGARDS)).set_index("ticker")


def notes_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Notes corrigées de chaque ligne de `df` : quatre colonnes, leur total sur 20 et le motif de correction."""
    adj = load_adjustments()
    rows = []
    for ticker, r in df.iterrows():
        notes = base_notes(r)
        motif = ""
        if ticker in adj.index:
            for k in REGARDS:
                delta = adj.at[ticker, k]
                notes[k] = int(min(5, max(1, notes[k] + (0 if pd.isna(delta) else delta))))
            motif = adj.at[ticker, "motif"]
        rows.append({**notes, "regards_total": sum(notes.values()), "regards_correction": motif})
    return pd.DataFrame(rows, index=df.index, columns=[*REGARDS, "regards_total", "regards_correction"])


def compute_regards(screener: pd.DataFrame, top: int | None = None, tous: bool = False) -> pd.DataFrame:
    """Tableau des notes dans l'ordre du classement : les éligibles, ou aussi les exclues avec `tous`."""
    keep = screener["statut"] != "Fonds" if tous else screener["statut"] == "Éligible"
    df = screener[keep].sort_values(["rang", "score"], ascending=[True, False], na_position="last")
    df = df.head(top) if top else df
    notes = notes_frame(df).rename(columns={"regards_total": "total", "regards_correction": "correction"})
    return df[["rang", "nom", "statut", "score"]].join(notes)
