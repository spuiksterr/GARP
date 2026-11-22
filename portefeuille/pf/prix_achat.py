"""Acheter au bon prix : prix juste, prix d'achat et verdict pour les valeurs suivies (page « Acheter au bon prix »).

Prix juste : le cours auquel l'action rapporterait exactement votre rendement exigé si la croissance attendue se
réalise (modèle des « value drivers » de pf/valuation.py, entrées ramenées à la capitalisation par
`entrees_valorisation`). Prix d'achat : le prix juste diminué de votre marge de sécurité, qui couvre l'erreur
d'estimation.

Verdict : au bon prix (cours au plus au prix d'achat), prix correct (entre le prix d'achat et le prix juste),
à attendre (au-dessus du prix juste), non évalué (holding, société en perte, fonds : le modèle ne s'applique pas).
Un prix visé saisi dans la watchlist reste le vôtre : il est affiché à côté, sans changer le verdict.
"""
from __future__ import annotations

import math

import pandas as pd

from .config import PROFIL_DIR, ecrire_json, lire_json
from .valuation import value_driver_ev

REGLAGES_JSON = PROFIL_DIR / "prix_achat.json"


def entrees_valorisation(r: pd.Series, vcfg: dict) -> dict:
    """Entrées du modèle des « value drivers » (pf/valuation.py), ramenées à la capitalisation :
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
MARGE_DEFAUT = 0.20
VERDICTS = {
    "bon": "Au bon prix",
    "correct": "Prix correct",
    "attendre": "À attendre",
    "nd": "Non évalué",
}
EXPLICATIONS = {
    "Au bon prix": "Le cours est au plus à votre prix d'achat : la marge de sécurité est là.",
    "Prix correct": "Sous le prix juste, mais sans toute votre marge de sécurité.",
    "À attendre": "Le cours dépasse le prix juste : bonne entreprise, peut-être, mais trop chère pour votre rendement exigé.",
    "Non évalué": "Holding, société en perte ou fonds : le modèle ne s'applique pas.",
}


def reglages(strategie: dict) -> dict:
    """Rendement exigé et marge de sécurité choisis par l'utilisateur (sinon ceux de la stratégie)."""
    v = strategie["valorisation"]
    enregistres = lire_json(REGLAGES_JSON, {}) or {}
    return {"rendement": float(enregistres.get("rendement", v["taux_actualisation"])),
            "marge": float(enregistres.get("marge", MARGE_DEFAUT))}


def enregistrer_reglages(rendement: float, marge: float) -> None:
    ecrire_json(REGLAGES_JSON, {"rendement": round(rendement, 4), "marge": round(marge, 4)}, indent=1)


def prix_juste(r: pd.Series, vcfg: dict, rendement: float, croissance: float | None = None) -> float:
    """Prix juste dans la devise de cotation ; NaN quand le modèle ne s'applique pas."""
    e = entrees_valorisation(r, vcfg)
    cours = pd.to_numeric(pd.Series([r.get("cours")]), errors="coerce").iloc[0]
    if not e or not (pd.notna(cours) and cours > 0):
        return math.nan
    g = croissance
    if g is None:
        g = pd.to_numeric(pd.Series([r.get("croissance_attendue")]), errors="coerce").iloc[0]
        g = float(g) if pd.notna(g) else 0.05
    ve = value_driver_ev(1.0, g, rendement, g_term=vcfg["croissance_terminale"], roic=e["val_roic"],
                         years_high=vcfg["annees_croissance"], years_fade=vcfg["annees_convergence"])
    x = e["val_base_cap"] * ve - e["val_dette_cap"]
    return float(cours) * x if math.isfinite(x) and x > 0 else math.nan


def verdict(cours: float, juste: float, achat: float) -> str:
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (cours, juste, achat)):
        return VERDICTS["nd"]
    if cours <= achat:
        return VERDICTS["bon"]
    return VERDICTS["correct"] if cours <= juste else VERDICTS["attendre"]


def tableau(sc: pd.DataFrame, sources: dict[str, str], vcfg: dict, rendement: float, marge: float,
            prix_vises: dict[str, float] | None = None) -> pd.DataFrame:
    """Une ligne par valeur de `sources` (ticker -> « Portefeuille », « Watchlist »…) présente dans le screener.

    À verdict égal, la note GARP (colonne `score`) classe les valeurs. Le prix d'achat et le verdict n'en dépendent
    pas : ils jugent le prix, pas l'entreprise."""
    prix_vises = prix_vises or {}
    lignes = []
    for t, source in sources.items():
        if t not in sc.index:
            continue
        r = sc.loc[t]
        cours = pd.to_numeric(pd.Series([r.get("cours")]), errors="coerce").iloc[0]
        cours = float(cours) if pd.notna(cours) else math.nan
        juste = prix_juste(r, vcfg, rendement)
        achat = juste * (1 - marge) if math.isfinite(juste) else math.nan
        vise = prix_vises.get(t, math.nan)
        lignes.append({
            "ticker": t, "nom": r.get("nom"), "source": source, "devise": r.get("devise"), "cours": cours,
            "prix_achat": achat, "prix_juste": juste,
            "ecart_achat": cours / achat - 1 if math.isfinite(achat) and achat > 0 and math.isfinite(cours) else math.nan,
            "verdict": verdict(cours, juste, achat), "prix_vise": vise,
            "vise_atteint": bool(math.isfinite(vise) and math.isfinite(cours) and cours <= vise),
            "croissance_attendue": r.get("croissance_attendue"), "tri_implicite": r.get("tri_implicite"),
            "score": r.get("score"), "secteur": r.get("secteur"), "enveloppe": r.get("enveloppe"),
            "moat": r.get("moat"), "criteres": r.get("criteres"), "criteres_ok": r.get("criteres_ok"),
            "statut": r.get("statut"),
        })
    out = pd.DataFrame(lignes)
    if out.empty:
        return out
    # Au bon prix d'abord ; à verdict égal, la meilleure note GARP en premier.
    ordre = {v: i for i, v in enumerate(VERDICTS.values())}
    score = pd.to_numeric(out["score"], errors="coerce").fillna(-1)
    return (out.assign(_o=out["verdict"].map(ordre), _s=-score).sort_values(["_o", "_s", "ecart_achat"])
            .drop(columns=["_o", "_s"]).set_index("ticker"))
