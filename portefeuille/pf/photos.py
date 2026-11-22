"""Historique daté des scores : une photo du screener à chaque mise à jour normale ou complète (ticket D-03).

Sert à suivre l'évolution d'un rang (fiche valeur), à signaler un changement de statut (tableau de bord), et
plus tard à tester la méthode sans biais rétrospectif : une photo ne contient que ce que l'outil savait ce jour-là.
Stockée hors du cache (data/historique/), qu'un nettoyage ne doit pas effacer.
"""
from __future__ import annotations

import pandas as pd

from .config import DATA_DIR, ecriture_atomique

PHOTOS_PARQUET = DATA_DIR / "historique" / "scores.parquet"
COLONNES = ["statut", "score", "rang", "qualite", "croissance", "valorisation", "momentum", "criteres", "cours",
            "devise", "per", "per_prospectif", "croiss_bpa_estimee", "croiss_ca_estimee", "tri_implicite"]


def charger() -> pd.DataFrame:
    """Toutes les photos : une ligne par (date, ticker)."""
    if not PHOTOS_PARQUET.exists():
        return pd.DataFrame(columns=["date", "ticker", *COLONNES])
    return pd.read_parquet(PHOTOS_PARQUET)


def enregistrer(sc: pd.DataFrame, date=None) -> int:
    """Ajoute la photo du jour (remplace celle de la même date). Renvoie le nombre de valeurs photographiées."""
    jour = pd.Timestamp(date or pd.Timestamp.today()).normalize()
    photo = sc.reindex(columns=COLONNES).rename_axis("ticker").reset_index()
    photo.insert(0, "date", jour)
    anciennes = charger()
    anciennes = anciennes[pd.to_datetime(anciennes["date"]) != jour] if not anciennes.empty else anciennes
    tout = pd.concat([anciennes, photo], ignore_index=True) if not anciennes.empty else photo
    tout["date"] = pd.to_datetime(tout["date"])
    for col in ("statut", "devise"):
        tout[col] = tout[col].astype("string")
    ecriture_atomique(PHOTOS_PARQUET, lambda tmp: tout.to_parquet(tmp, index=False))
    return len(photo)


def evolution(ticker: str, photos: pd.DataFrame | None = None) -> pd.DataFrame:
    """Rang, score et statut d'une valeur, photo par photo (index : date)."""
    photos = charger() if photos is None else photos
    p = photos[photos["ticker"] == ticker]
    return p.set_index("date").sort_index()[["rang", "score", "statut"]]


def changements_de_statut(tickers, photos: pd.DataFrame | None = None) -> list[tuple[str, str, str, pd.Timestamp]]:
    """(ticker, ancien statut, nouveau statut, date de l'avant-dernière photo) entre les deux dernières photos."""
    photos = charger() if photos is None else photos
    dates = sorted(pd.to_datetime(photos["date"]).unique())
    if len(dates) < 2:
        return []
    avant, apres = (photos[pd.to_datetime(photos["date"]) == d].set_index("ticker")["statut"] for d in dates[-2:])
    out = []
    for t in tickers:
        a, b = avant.get(t), apres.get(t)
        if pd.notna(a) and pd.notna(b) and a != b:
            out.append((t, str(a), str(b), pd.Timestamp(dates[-2])))
    return out
