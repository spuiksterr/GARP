"""Photo du portefeuille : les quantités de chaque ligne, prises au dernier import (profil/positions.csv).

Chaque import avec quantités remplace la photo en entier : réimporter son portefeuille la met à jour, sans rien
saisir à la main. Elle sert à mesurer le poids réel des lignes (onglet « Équilibre », tableau de bord, risques).
Performance et fiscalité restent chez le courtier, qui les tient de façon complète.

Le journal des opérations (data/transactions.csv) n'est plus tenu par l'interface. S'il existe et que la photo
manque, ses positions servent de photo de départ, en lecture seule.
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import pandas as pd

from .config import (
    PORTEFEUILLE_DEFAUT,
    PROFIL_DIR,
    chemin_positions,
    portefeuille_actif,
    read_csv_fr,
    write_csv_fr,
)

POSITIONS_CSV = PROFIL_DIR / "positions.csv"
COLONNES = ["ticker", "compte", "quantite", "date"]


def _chemin() -> Path:
    return POSITIONS_CSV if portefeuille_actif() == PORTEFEUILLE_DEFAUT else chemin_positions()


def enregistrer(lignes: list[dict], jour: date | None = None) -> int:
    """Remplace la photo par `lignes` (ticker, compte, quantite) ; une valeur citée deux fois sur le même compte
    cumule ses quantités. Renvoie le nombre de lignes enregistrées."""
    cumul: dict[tuple[str, str], float] = {}
    for li in lignes:
        q = li.get("quantite")
        if not li.get("ticker") or not isinstance(q, (int, float)) or not math.isfinite(q) or q <= 0:
            continue
        cle = (li["ticker"], li.get("compte") or "CTO")
        cumul[cle] = cumul.get(cle, 0.0) + float(q)
    jour = jour or date.today()
    df = pd.DataFrame([{"ticker": t, "compte": c, "quantite": round(q, 6), "date": jour.isoformat()}
                       for (t, c), q in sorted(cumul.items())], columns=COLONNES)
    write_csv_fr(df, _chemin())
    return len(df)


def photo() -> pd.DataFrame:
    """Quantités par ligne (ticker, compte, quantite, date) : la photo du dernier import, sinon le journal."""
    cible = _chemin()
    if cible.exists():
        df = read_csv_fr(cible, numeric=("quantite",))
        return df[df["quantite"] > 0].reset_index(drop=True) if not df.empty else df
    try:
        from .tracker import positions as positions_journal

        p = positions_journal()
    except Exception:  # journal illisible : pas de photo
        return pd.DataFrame(columns=COLONNES)
    if p.empty:
        return pd.DataFrame(columns=COLONNES)
    p = p[p["quantite"] > 0]
    return pd.DataFrame({"ticker": p["ticker"], "compte": p["compte"], "quantite": p["quantite"],
                         "date": "journal"}).reset_index(drop=True)


def positions() -> pd.DataFrame:
    """Lignes valorisées au dernier cours en euros : compte, ticker, quantite, cours_eur, valeur_eur, poids."""
    from .data import currency_map, load_fx, load_prices, prices_in_eur

    p = photo()
    if p.empty:
        return pd.DataFrame(columns=["compte", "ticker", "quantite", "cours_eur", "valeur_eur", "poids"])
    tickers = sorted(set(p["ticker"]))
    prix = load_prices()
    eur = prices_in_eur(prix[[t for t in tickers if t in prix.columns]], currency_map(tickers), load_fx())
    dernier = eur.ffill().iloc[-1] if not eur.empty else pd.Series(dtype=float)
    out = p.assign(cours_eur=[float(dernier.get(t, math.nan)) for t in p["ticker"]])
    out["valeur_eur"] = (out["quantite"] * out["cours_eur"]).fillna(0.0)
    total = out["valeur_eur"].sum()
    out["poids"] = out["valeur_eur"] / total if total else 0.0
    return out[["compte", "ticker", "quantite", "cours_eur", "valeur_eur", "poids", "date"]].sort_values(
        "valeur_eur", ascending=False).reset_index(drop=True)


def date_photo() -> str | None:
    p = photo()
    if p.empty:
        return None
    d = str(p["date"].iloc[0])
    return None if d == "journal" else d
