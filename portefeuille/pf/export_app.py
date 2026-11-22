"""Export des données de marché pour l'application G.A.R.P (Android et Windows), sans aucune donnée personnelle.

`garp-donnees.json.gz` : les valeurs du screener avec leurs indicateurs, les cours hebdomadaires sur 5 ans
(devise de cotation), les changes hebdomadaires et l'indice de référence (risques, backtest), le dernier cours
en euros, l'historique des rangs, les méthodes de notation et les réglages de la stratégie (valorisation,
garde-fous, construction). Deux fichiers complémentaires viennent de pf/export_fiches.py. Publiés chaque nuit
par GitHub (.github/workflows/donnees.yml) dans la release `donnees` du dépôt ; l'application les télécharge.
"""
from __future__ import annotations

import gzip
import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

FORMAT = 1
NOM_FICHIER = "garp-donnees.json.gz"
# Colonnes du screener reprises dans l'application (noms inchangés).
COLONNES = [
    "nom", "pays", "enveloppe", "secteur", "profil", "devise", "statut", "rang", "score", "qualite", "croissance",
    "valorisation", "momentum", "motifs_exclusion", "alertes", "moat", "criteres", "cours", "perf_1m", "perf_12m",
    "perf_annu_5a", "volatilite", "drawdown_max_3a", "capitalisation_eur", "per", "per_prospectif",
    "per_historique", "ecart_per_historique", "p_fcf", "rendement_fcf", "rendement_dividende", "tri_implicite",
    "croissance_implicite", "croissance_attendue", "roic_moyen", "marge_operationnelle", "marge_fcf",
    "dette_nette_ebitda", "croiss_ca", "croiss_bpa", "evolution_actions", "piotroski", "altman_z", "beneish_m",
    "regards_total", "buffett", "munger", "fisher", "smith", "nb_exercices", "financiere", "fonds",
    "criteres_ok", "criteres_evalues",
    "crit_ca", "crit_ca_ok", "crit_fcf", "crit_fcf_ok", "crit_roce", "crit_roce_ok", "crit_dette", "crit_dette_ok",
    "crit_actions", "crit_actions_ok", "crit_marge", "crit_marge_ok",
    # Fiche complète, prix juste, scénarios, construction.
    "industrie", "devise_comptes", "holding", "roe_moyen", "marge_brute", "marge_nette", "conversion_fcf",
    "croiss_bpa_estimee", "croiss_ca_estimee", "rendement_benefices", "mom_12_1", "ecart_mm200", "perf_3m",
    "perf_6m", "objectif_analystes", "p_fcf_historique", "ecart_p_fcf_historique", "p_fcf_net",
    "p_fcf_net_historique", "ecart_p_fcf_net_historique", "rendement_fcf_hors_sbc", "p_ca", "rentabilite",
    "score_piliers", "pts_valorisation", "pts_piotroski", "pts_altman", "pts_beneish", "pts_criteres",
    "regards_correction", "verif_sec", "rendement_actionnaire", "stabilite_marge", "couverture_interets",
    "nb_analystes", "evol_ca_12m", "ecart_plus_haut_52s",
]
# Les six critères de qualité (pf/criteres.py) : clé, titre, seuil de strategie.json, sens de la comparaison.
CRITERES = [
    ("ca", "Croissance du chiffre d'affaires", "croissance_ca_min"),
    ("fcf", "Croissance du free cash flow", "croissance_fcf_min"),
    ("roce", "ROCE (rentabilité du capital employé)", "roce_min"),
    ("dette", "Dette nette / free cash flow", "dette_nette_fcf_max"),
    ("actions", "Évolution du nombre d'actions", "evolution_actions_max"),
    ("marge", "Marge du free cash flow", "marge_fcf_min"),
]
ANNEES_COURS = 5


def _propre(v):
    """Valeur JSON : nombres arrondis, NaN et infinis en null."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int | float):
        if isinstance(v, float) and not math.isfinite(v):
            return None
        return round(float(v), 6) if isinstance(v, float) else int(v)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):  # nombres numpy
        return _propre(v.item())
    return str(v) if str(v) != "" else None


def _valorisation(r: pd.Series, vcfg: dict) -> dict:
    """Entrées du modèle des « value drivers » (pf/valuation.py), ramenées à la capitalisation : l'application
    recalcule la valeur intrinsèque avec le rendement exigé et la croissance de l'utilisateur.
        valeur / cours = val_base_cap × VE(1, croissance, rendement, ROIC) − val_dette_cap
    Banque ou assureur : base = résultat net, sans dette. Rien pour une holding ou une société en perte."""
    def num(c):
        v = pd.to_numeric(pd.Series([r.get(c)]), errors="coerce").iloc[0]
        return float(v) if pd.notna(v) else math.nan

    def vrai(c):
        return bool(r.get(c)) if pd.notna(r.get(c)) else False

    fin = vrai("financiere")
    base = num("benefice_ttm") if fin else num("nopat_ttm")
    capi, dette = num("capitalisation_comptes"), num("dette_nette")
    if vrai("holding") or not (base > 0 and capi > 0) or (not fin and not math.isfinite(dette)):
        return {}
    if not fin and capi + dette <= 0:
        return {}
    rmin, rmax = vcfg.get("roic_incremental_min", 0.12), vcfg.get("roic_incremental_max", 0.4)
    roic = num("rentabilite")
    return {"val_base_cap": round(base / capi, 5), "val_dette_cap": 0.0 if fin else round(dette / capi, 5),
            "val_roic": round(min(max(roic if math.isfinite(roic) else rmin, rmin), rmax), 4)}


def valeurs(sc: pd.DataFrame, fx: pd.DataFrame | None = None, vcfg: dict | None = None) -> list[dict]:
    from .data import fx_rate

    cols = [c for c in COLONNES if c in sc.columns]
    out = []
    for t, r in sc.iterrows():
        d = {"ticker": t}
        d.update({c: _propre(r[c]) for c in cols if _propre(r[c]) is not None})
        if vcfg:
            d.update(_valorisation(r, vcfg))
        if fx is not None and isinstance(d.get("cours"), float) and d.get("devise"):
            taux = fx_rate(fx, str(d["devise"]), "EUR")
            if math.isfinite(taux):
                d["cours_eur"] = _propre(round(d["cours"] * taux, 4))
        out.append(d)
    return out


def cours_hebdomadaires(prix: pd.DataFrame, tickers) -> dict:
    """{ticker: {"debut": date du premier vendredi, "c": [cours...]}} : un cours par semaine, null si absent."""
    if prix.empty:
        return {}
    depuis = prix.index.max() - pd.DateOffset(years=ANNEES_COURS)
    hebdo = prix[prix.index >= depuis].resample("W-FRI").last()
    out = {}
    for t in tickers:
        if t not in hebdo.columns:
            continue
        s = hebdo[t]
        s = s.loc[s.first_valid_index():] if s.first_valid_index() is not None else s.iloc[0:0]
        if len(s) >= 2:
            out[t] = {"debut": f"{s.index[0]:%Y-%m-%d}", "c": [_propre(round(v, 4)) for v in s.tolist()]}
    return out


def changes_hebdomadaires(fx: pd.DataFrame | None, prix: pd.DataFrame) -> dict:
    """{devise: {"debut", "c": euros pour une unité de la devise, un par semaine}} sur la période des cours."""
    if fx is None or fx.empty or prix.empty:
        return {}
    depuis = prix.index.max() - pd.DateOffset(years=ANNEES_COURS)
    hebdo = fx[fx.index >= depuis].resample("W-FRI").last().ffill()
    return {c: {"debut": f"{hebdo.index[0]:%Y-%m-%d}",
                "c": [_propre(round(1 / v, 6)) if v and v == v else None for v in hebdo[c].tolist()]}
            for c in hebdo.columns if c != "EUR" and hebdo[c].notna().any()}


def rangs(photos: pd.DataFrame) -> dict:
    """{ticker: [[date, rang], ...]} d'après les photos du screener."""
    if photos.empty:
        return {}
    p = photos.dropna(subset=["rang"]).sort_values("date")
    return {t: [[f"{pd.Timestamp(d):%Y-%m-%d}", int(r)] for d, r in zip(g["date"], g["rang"])]
            for t, g in p.groupby("ticker")}


def methodes() -> list[dict]:
    """Méthodes de notation (pf/portfolio.py) : l'application les recalcule à l'identique (rangs centiles pondérés)."""
    from .portfolio import COMPOSANTES, NOTATIONS

    return [{"id": k, "libelle": lib, "description": desc, "poids": poids,
             "composantes": [COMPOSANTES.get(c, c) for c in poids]} for k, (lib, desc, poids) in NOTATIONS.items()]


def criteres(seuils: dict | None = None) -> list[dict]:
    """Définition des six critères, avec les seuils en vigueur."""
    from .criteres import REGLES, SEUILS

    s = SEUILS | (seuils or {})
    return [{"cle": cle, "titre": titre, "seuil": s[nom], "sens": REGLES[cle][1]} for cle, titre, nom in CRITERES]


def construire(sc: pd.DataFrame, prix: pd.DataFrame, photos: pd.DataFrame, date_donnees: str | None,
               fx: pd.DataFrame | None = None, seuils: dict | None = None, strategie: dict | None = None) -> dict:
    strategie = strategie or {}
    vcfg = strategie.get("valorisation") or {}
    reference = (strategie.get("suivi") or {}).get("benchmark") or "IWDA.AS"
    return {
        "format": FORMAT,
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "donnees_au": date_donnees,
        "nb_valeurs": len(sc),
        "nb_eligibles": int((sc["statut"] == "Éligible").sum()) if "statut" in sc.columns else 0,
        "valeurs": valeurs(sc, fx, vcfg),
        "cours": cours_hebdomadaires(prix, sc.index),
        "changes": changes_hebdomadaires(fx, prix),
        "reference": {"ticker": reference, **(cours_hebdomadaires(prix, [reference]).get(reference) or {})},
        "strategie": {"valorisation": vcfg, "garde_fous": (strategie.get("suivi") or {}).get("garde_fous") or {},
                      "construction": {k: v for k, v in (strategie.get("construction") or {}).items()
                                       if k != "notation"}},
        "rangs": rangs(photos),
        "methodes": methodes(),
        "criteres": criteres(seuils),
    }


def _ecrire(chemin: Path, donnees: dict) -> Path:
    with gzip.open(chemin, "wt", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, separators=(",", ":"))
    return chemin


def exporter(dossier: Path) -> Path:
    """Calcule le screener à partir du cache et écrit les fichiers de l'application dans `dossier` ; renvoie le
    fichier principal."""
    from . import export_fiches, photos
    from .config import load_strategy
    from .data import load_fx, load_prices
    from .scoring import build_screener

    sc = build_screener()
    prix = load_prices()
    date = f"{prix.index.max():%Y-%m-%d}" if not prix.empty else None
    strategie, fx = load_strategy(), load_fx()
    donnees = construire(sc, prix, photos.charger(), date, fx, strategie.get("criteres"), strategie)
    dossier.mkdir(parents=True, exist_ok=True)
    entete = {"format": FORMAT, "genere_le": donnees["genere_le"], "donnees_au": date}
    _ecrire(dossier / export_fiches.NOM_FICHES, {**entete, "fiches": export_fiches.fiches(sc, prix, fx)})
    _ecrire(dossier / export_fiches.NOM_INVESTISSEURS, {**entete, **export_fiches.investisseurs_et_elus()})
    return _ecrire(dossier / NOM_FICHIER, donnees)
