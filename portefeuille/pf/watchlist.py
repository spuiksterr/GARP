"""Watchlist personnelle (profil/watchlist.csv) : valeurs suivies, avec la date et le cours de leur ajout, et le prix
d'achat visé quand on en a fixé un (module « Quel est le prix juste ? » de la fiche).

L'ordre des lignes du fichier est celui de la liste, choisi par l'utilisateur (une valeur ajoutée va à la fin).

Distincte de profil/surveillance.csv, qui garde les conditions d'entrée décidées lors d'une analyse et ne
se modifie qu'avec accord : la watchlist se remplit d'un clic depuis la fiche, le screener ou sa page.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from .config import PROFIL_DIR, read_csv_fr, write_csv_fr

WATCHLIST_CSV = PROFIL_DIR / "watchlist.csv"
COLONNES = ["ticker", "ajoute_le", "cours_ajout", "note", "prix_cible", "objectif"]


def load_watchlist() -> pd.DataFrame:
    """Une ligne par valeur suivie, index ticker ; vide si le fichier n'existe pas encore."""
    if not WATCHLIST_CSV.exists():
        return pd.DataFrame(columns=COLONNES[1:], index=pd.Index([], name="ticker"))
    df = read_csv_fr(WATCHLIST_CSV, numeric=("cours_ajout", "prix_cible"))
    for col in COLONNES:
        if col not in df.columns:  # fichier d'une version antérieure
            df[col] = float("nan") if col == "prix_cible" else ""
    return df[COLONNES].drop_duplicates("ticker", keep="last").set_index("ticker")


def contient(ticker: str) -> bool:
    return ticker in load_watchlist().index


def ajouter(ticker: str, cours: float | None = None, note: str = "") -> None:
    """Ajoute une valeur (sans effet si elle y est déjà : sa date et son cours d'ajout sont conservés)."""
    wl = load_watchlist()
    if ticker in wl.index:
        return
    ligne = pd.DataFrame([{"ajoute_le": date.today().isoformat(), "cours_ajout": "" if cours is None else round(float(cours), 4),
                           "note": note}], index=pd.Index([ticker], name="ticker"))
    write_csv_fr(pd.concat([wl, ligne]).reset_index(), WATCHLIST_CSV)


def fixer_cible(ticker: str, prix_cible: float, objectif: str = "", cours: float | None = None) -> None:
    """Prix d'achat visé (devise de cotation) et ce qui l'a fixé, par exemple « P/FCF 20 ».

    Une valeur absente de la watchlist y est ajoutée, au cours `cours`.
    """
    if not contient(ticker):
        ajouter(ticker, cours)
    wl = load_watchlist()
    wl.loc[ticker, "prix_cible"] = round(float(prix_cible), 4)
    wl.loc[ticker, "objectif"] = objectif
    write_csv_fr(wl.reset_index(), WATCHLIST_CSV)


def prix_vises_atteints(cours: pd.Series, liste: pd.DataFrame | None = None) -> pd.DataFrame:
    """Valeurs dont le cours (devise de cotation, indexé par ticker) est au prix visé ou en dessous."""
    liste = load_watchlist() if liste is None else liste
    c = pd.to_numeric(cours.reindex(liste.index), errors="coerce")
    ok = liste["prix_cible"].notna() & c.notna() & (c <= liste["prix_cible"])
    return liste[ok].assign(cours=c[ok])


def retirer(ticker: str) -> None:
    wl = load_watchlist()
    if ticker in wl.index:
        write_csv_fr(wl.drop(index=ticker).reset_index(), WATCHLIST_CSV)


def placer(ticker: str, position: int) -> int:
    """Déplace une valeur à `position` (0 = en tête), bornée à la liste ; renvoie sa nouvelle position."""
    wl = load_watchlist()
    if ticker not in wl.index:
        return -1
    ordre = [t for t in wl.index if t != ticker]
    position = max(0, min(int(position), len(ordre)))
    ordre.insert(position, ticker)
    write_csv_fr(wl.loc[ordre].reset_index(), WATCHLIST_CSV)
    return position
