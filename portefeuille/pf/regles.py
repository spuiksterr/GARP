"""Conditions de vente chiffrées, vérifiées à chaque mise à jour.

La condition de vente de chaque ligne est d'abord un texte (profil/portefeuille_modele.csv). Quand elle se mesure,
on la traduit en règle : un indicateur de l'outil, une comparaison et un seuil (profil/regles_vente.csv). Une
règle atteinte s'affiche au tableau de bord et dans la fiche : c'est le moment de relire la thèse, pas un ordre
de vente automatique.

Seuils en unités d'affichage : un pourcentage s'écrit en % (« -5 » pour -5 %), un multiple tel quel (« 3 »).
"""
from __future__ import annotations

import math
import operator

import pandas as pd

from .config import PROFIL_DIR, read_csv_fr, write_csv_fr
from .formats import nombre, pct

REGLES_CSV = PROFIL_DIR / "regles_vente.csv"
COLONNES = ["ticker", "indicateur", "operateur", "seuil", "note"]

# Indicateur : (libellé, unité). « pct » : ratio affiché en %, « x » : multiple, « n » : nombre.
INDICATEURS = {
    "evol_ca_12m": ("CA des 12 derniers mois, par rapport au dernier exercice", "pct"),
    "croiss_ca": ("Croissance annuelle du chiffre d'affaires (5 ans)", "pct"),
    "rentabilite": ("Rentabilité du capital moyenne (ROIC, ou ROE pour une financière)", "pct"),
    "rentabilite_derniere": ("Rentabilité du capital du dernier exercice", "pct"),
    "marge_operationnelle": ("Marge opérationnelle", "pct"),
    "marge_fcf": ("Marge de flux de trésorerie disponible", "pct"),
    "evolution_actions": ("Évolution annuelle du nombre d'actions (dilution si positive)", "pct"),
    "dette_nette_ebitda": ("Dette nette / EBITDA", "x"),
    "couverture_interets": ("Couverture des intérêts", "x"),
    "criteres_ok": ("Critères de qualité remplis (sur 6)", "n"),
    "piotroski": ("Score de Piotroski (sur 9)", "n"),
    "per": ("PER", "x"),
    "p_fcf": ("P/FCF", "x"),
    "ecart_p_fcf_historique": ("P/FCF par rapport à sa médiane historique", "pct"),
    "tri_implicite": ("TRI implicite", "pct"),
    "perf_12m": ("Performance sur 12 mois", "pct"),
    "ecart_plus_haut_52s": ("Écart au plus haut de 52 semaines", "pct"),
    "cours": ("Cours (devise de cotation)", "n"),
}
OPERATEURS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}
TEXTE_OPERATEURS = {"<": "sous", "<=": "au plus", ">": "au-dessus de", ">=": "au moins"}


def load_regles() -> pd.DataFrame:
    if not REGLES_CSV.exists():
        return pd.DataFrame(columns=COLONNES)
    df = read_csv_fr(REGLES_CSV, numeric=("seuil",))
    for c in COLONNES:
        if c not in df.columns:
            df[c] = ""
    return df[COLONNES].reset_index(drop=True)


def ajouter(ticker: str, indicateur: str, operateur: str, seuil: float, note: str = "") -> None:
    if indicateur not in INDICATEURS or operateur not in OPERATEURS:
        raise ValueError("indicateur ou opérateur inconnu")
    df = load_regles()
    ligne = {"ticker": ticker, "indicateur": indicateur, "operateur": operateur, "seuil": float(seuil),
             "note": str(note or "").replace(";", ",").strip()}
    write_csv_fr(pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)[COLONNES], REGLES_CSV)


def retirer(index: int) -> None:
    df = load_regles()
    if 0 <= index < len(df):
        write_csv_fr(df.drop(index=index)[COLONNES], REGLES_CSV)


def _affiche(valeur: float, unite: str) -> str:
    if not (isinstance(valeur, (int, float)) and math.isfinite(valeur)):
        return "n.d."
    return pct(valeur, 1) if unite == "pct" else f"{nombre(valeur, 1)}x" if unite == "x" else nombre(valeur, 1)


def texte(regle: pd.Series) -> str:
    """« Marge opérationnelle sous 15 % »."""
    lib, unite = INDICATEURS.get(regle["indicateur"], (regle["indicateur"], "n"))
    seuil = float(regle["seuil"])
    d = 0 if seuil == int(seuil) else 1  # « 0 % », « 2,5x » : le seuil tel que saisi
    seuil_aff = pct(seuil / 100, d) if unite == "pct" else f"{nombre(seuil, d)}x" if unite == "x" else nombre(seuil, d)
    return f"{lib} {TEXTE_OPERATEURS.get(regle['operateur'], regle['operateur'])} {seuil_aff}"


def evaluer(sc: pd.DataFrame, regles: pd.DataFrame | None = None) -> pd.DataFrame:
    """Une ligne par règle : valeur actuelle et statut (« Atteinte », « Respectée » ou « Donnée absente »)."""
    regles = load_regles() if regles is None else regles
    lignes = []
    for i, r in regles.iterrows():
        lib, unite = INDICATEURS.get(r["indicateur"], (r["indicateur"], "n"))
        brute = sc.loc[r["ticker"], r["indicateur"]] if r["ticker"] in sc.index and r["indicateur"] in sc.columns \
            else math.nan
        valeur = pd.to_numeric(pd.Series([brute]), errors="coerce").iloc[0]
        seuil = float(r["seuil"]) / 100 if unite == "pct" else float(r["seuil"])
        if pd.isna(valeur) or r["operateur"] not in OPERATEURS:
            statut = "Donnée absente"
        else:
            statut = "Atteinte" if OPERATEURS[r["operateur"]](float(valeur), seuil) else "Respectée"
        lignes.append({"index": i, "ticker": r["ticker"], "regle": texte(r), "valeur": _affiche(valeur, unite),
                       "statut": statut, "note": r["note"] or ""})
    return pd.DataFrame(lignes, columns=["index", "ticker", "regle", "valeur", "statut", "note"])
