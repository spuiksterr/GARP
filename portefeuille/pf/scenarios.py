"""Valorisation par scénarios : le prix de l'action dans 5 ans selon trois jeux d'hypothèses.

Pour chaque scénario (pessimiste, central, optimiste) :
    chiffre d'affaires dans 5 ans = CA des 12 derniers mois × (1 + croissance)^5
    flux de l'année 5 = CA × marge (de FCF, ou nette pour une banque, un assureur)
    valeur dans 5 ans = flux × multiple de sortie (P/FCF ou PER)
    prix dans 5 ans = cours × valeur / capitalisation actuelle, corrigé de l'évolution du nombre d'actions
    rendement annuel = (prix dans 5 ans / cours)^(1/5) − 1, hors dividendes
Les hypothèses de départ viennent des données (croissance attendue, marge, multiple médian) ; elles se modifient.
Les scénarios enregistrés (profil/scenarios.csv) sont datés : on suit ensuite le cours par rapport à eux.
"""
from __future__ import annotations

import math
from datetime import date

import pandas as pd

from .config import PROFIL_DIR, read_csv_fr, write_csv_fr
from .formats import nombre

SCENARIOS_CSV = PROFIL_DIR / "scenarios.csv"
COLONNES = ["ticker", "date", "scenario", "base", "croissance", "marge", "multiple", "prix_5ans", "cours", "devise"]
NOMS = ["Pessimiste", "Central", "Optimiste"]
HORIZON = 5
CROISSANCE_MAX = 0.15  # croissance centrale proposée au plus : au-delà de 5 ans, 15 % par an est déjà rare


def _fini(v) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v)


def _num(r: pd.Series, col: str) -> float:
    v = pd.to_numeric(pd.Series([r.get(col)]), errors="coerce").iloc[0]
    return float(v) if pd.notna(v) else math.nan


def base_de(r: pd.Series) -> str:
    """« fcf » en général ; « resultat » pour une banque ou un assureur, ou sans marge de FCF positive."""
    if bool(r.get("financiere")) or not (_fini(_num(r, "marge_fcf")) and _num(r, "marge_fcf") > 0):
        return "resultat"
    return "fcf"


def hypotheses_initiales(r: pd.Series) -> dict[str, dict[str, float]]:
    """Point de départ prudent, à ajuster selon votre analyse.

    - Central : croissance attendue (à défaut, celle des 5 dernières années) plafonnée à 15 %, marge actuelle,
      et le plus bas du multiple actuel et du multiple médian de la valeur : pas de revalorisation supposée.
    - Pessimiste : croissance moitié moindre, marge -15 %, multiple -25 %.
    - Optimiste : croissance +30 % (30 % par an au plus), marge +10 %, et retour au multiple médian s'il est plus
      haut (sinon multiple +15 %).
    """
    base = base_de(r)
    marge = _num(r, "marge_fcf" if base == "fcf" else "marge_nette")
    marge = marge if _fini(marge) and marge > 0 else 0.10
    actuel = _num(r, "p_fcf" if base == "fcf" else "per")
    mediane = _num(r, "p_fcf_historique" if base == "fcf" else "per_historique")
    valides = [m for m in (actuel, mediane) if _fini(m) and 3 <= m <= 80]
    central = min(valides) if valides else 15.0
    optimiste = max(central * 1.15, mediane if _fini(mediane) and 3 <= mediane <= 80 else 0)
    g = next((x for x in (_num(r, "croissance_attendue"), _num(r, "croiss_ca")) if _fini(x)), 0.05)
    g = min(max(g, -0.10), CROISSANCE_MAX)
    return {
        "Pessimiste": {"croissance": round(g * 0.5 if g > 0 else g * 1.5, 4), "marge": round(marge * 0.85, 4),
                       "multiple": round(central * 0.75, 1)},
        "Central": {"croissance": round(g, 4), "marge": round(marge, 4), "multiple": round(central, 1)},
        "Optimiste": {"croissance": round(min(g * 1.3, 0.30) if g > 0 else g * 0.5, 4), "marge": round(marge * 1.1, 4),
                      "multiple": round(optimiste, 1)},
    }


def chiffre_affaires(r: pd.Series) -> float:
    """CA des 12 derniers mois, dans la devise des comptes : capitalisation / (prix / chiffre d'affaires)."""
    capi, p_ca = _num(r, "capitalisation_comptes"), _num(r, "p_ca")
    return capi / p_ca if _fini(capi) and _fini(p_ca) and p_ca > 0 else math.nan


def prix_futur(r: pd.Series, croissance: float, marge: float, multiple: float, horizon: int = HORIZON) -> float:
    cours, capi, ca = _num(r, "cours"), _num(r, "capitalisation_comptes"), chiffre_affaires(r)
    if not all(_fini(x) and x > 0 for x in (cours, capi, ca)):
        return math.nan
    valeur = ca * (1 + croissance) ** horizon * marge * multiple
    dilution = _num(r, "evolution_actions")
    dilution = min(max(dilution, -0.10), 0.10) if _fini(dilution) else 0.0
    return cours * valeur / capi / (1 + dilution) ** horizon


def rendement_annuel(prix: float, cours: float, horizon: int = HORIZON) -> float:
    if not (_fini(prix) and _fini(cours) and cours > 0) or prix <= 0:
        return math.nan if not _fini(prix) else -1.0
    return (prix / cours) ** (1 / horizon) - 1


# --------------------------------------------------------------------------- scénarios enregistrés

def load() -> pd.DataFrame:
    if not SCENARIOS_CSV.exists():
        return pd.DataFrame(columns=COLONNES)
    return read_csv_fr(SCENARIOS_CSV, numeric=("croissance", "marge", "multiple", "prix_5ans", "cours"))


def enregistrer(ticker: str, r: pd.Series, hypotheses: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Ajoute le jeu de scénarios du jour (remplace celui déjà enregistré aujourd'hui pour cette valeur)."""
    jour = date.today().isoformat()
    base = base_de(r)
    lignes = [{"ticker": ticker, "date": jour, "scenario": nom, "base": base, **h,
               "prix_5ans": round(prix_futur(r, h["croissance"], h["marge"], h["multiple"]), 4),
               "cours": round(_num(r, "cours"), 4), "devise": str(r.get("devise") or "")}
              for nom, h in hypotheses.items()]
    df = load()
    df = df[~((df["ticker"] == ticker) & (df["date"] == jour))]
    nouveau = pd.DataFrame(lignes)
    write_csv_fr(pd.concat([df, nouveau], ignore_index=True)[COLONNES], SCENARIOS_CSV)
    return nouveau


def derniers(ticker: str, df: pd.DataFrame | None = None) -> pd.DataFrame:
    df = load() if df is None else df
    d = df[df["ticker"] == ticker]
    return d[d["date"] == d["date"].max()] if len(d) else d


def alertes(sc: pd.DataFrame) -> list[tuple[str, str]]:
    """(ticker, message) quand le cours dépasse votre prix optimiste à 5 ans, ou tombe sous le pessimiste."""
    df = load()
    out = []
    for t in df["ticker"].unique():
        d = derniers(t, df).set_index("scenario")
        if t not in sc.index or not {"Pessimiste", "Optimiste"} <= set(d.index):
            continue
        cours, dev = _num(sc.loc[t], "cours"), str(sc.loc[t].get("devise") or "")
        bas, haut = float(d.loc["Pessimiste", "prix_5ans"]), float(d.loc["Optimiste", "prix_5ans"])
        quand = pd.Timestamp(d["date"].iloc[0]).strftime("%d/%m/%Y")
        if _fini(cours) and _fini(haut) and cours > haut:
            out.append((t, f"Cours ({nombre(cours, 2)} {dev}) au-dessus de votre prix optimiste à 5 ans "
                           f"({nombre(haut, 2)}, scénarios du {quand}) : le marché paie plus que votre meilleur cas."))
        elif _fini(cours) and _fini(bas) and cours < bas:
            out.append((t, f"Cours ({nombre(cours, 2)} {dev}) sous votre prix pessimiste à 5 ans "
                           f"({nombre(bas, 2)}, scénarios du {quand}) : même le pire cas promet un gain."))
    return out
