"""Construction de portefeuille : sélection sous contraintes, pondération, caractéristiques ex ante."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from .config import MODELE_CSV, load_model_portfolio, load_strategy
from .data import currency_map, load_fx, load_prices, prices_in_eur

METHODES = {
    "score_vol": "Note × 1/volatilité (recommandé)",
    "egal": "Équipondéré",
    "variance_min": "Variance minimale (contrainte)",
}

# Secteurs dont les résultats suivent le cycle (prix de l'énergie et des matières premières, crédit) : au
# sommet du cycle, leurs multiples paraissent bas et le score les favorise. Leur part est plafonnée.
CYCLIQUES = {"Infrastructures & Énergie", "Matériaux & Chimie", "Banques"}

# Notes qui peuvent classer les candidats. Chacune est ramenée à son rang centile dans l'univers (0 à 100) :
# une note de 1 à 5 (un regard) et un score sur 100 deviennent comparables, et se combinent.
COMPOSANTES = {
    "score": "Score composite",
    "pts_regards": "Quatre regards",
    "buffett": "Buffett",
    "munger": "Munger",
    "fisher": "Fisher",
    "smith": "Terry Smith",
    "qualite": "Qualité",
    "croissance": "Croissance",
    "valorisation": "Valorisation",
    "momentum": "Momentum",
    "criteres_part": "Six critères",
}
# Méthodes de notation proposées : (libellé, description, poids des composantes).
NOTATIONS = {
    "composite": ("Score composite", "La note de l'outil : piliers, valorisation, Piotroski, Altman, Beneish. "
                  "Équilibrée, mais sensible aux valeurs bon marché.", {"score": 1}),
    # Plus de moyenne des quatre regards (22/11/2026) : chacun reste une méthode à part, sans être additionné.
    "garp": ("GARP", "La croissance, sans la surpayer : croissance, valorisation et qualité, la croissance d'abord.",
             {"croissance": 0.4, "valorisation": 0.35, "qualite": 0.25}),
    "buffett": ("Buffett", "Avantage durable, rentabilité élevée sans dette excessive, prix raisonnable.", {"buffett": 1}),
    "munger": ("Munger", "Éviter les erreurs : solidité financière, simplicité, pas de comptabilité douteuse.",
               {"munger": 1}),
    "fisher": ("Fisher", "Croissance de long terme portée par l'innovation et les marges.", {"fisher": 1}),
    "smith": ("Terry Smith", "Acheter de bonnes entreprises, ne pas surpayer, ne rien faire : rentabilité du capital, "
                             "marges élevées, croissance autofinancée.", {"smith": 1}),
    "qualite": ("Qualité d'abord", "Rentabilité du capital, marges et solidité, puis les six critères.",
                {"qualite": 0.6, "criteres_part": 0.4}),
    "croissance": ("Croissance", "Croissance passée et attendue du chiffre d'affaires et des bénéfices.",
                   {"croissance": 1}),
    "valeur": ("Valeur", "Les moins chères par rapport à leurs flux, avec un minimum de qualité.",
               {"valorisation": 0.7, "qualite": 0.3}),
    "momentum": ("Momentum", "Les actions qui montent le plus sur 12 mois (hors dernier mois).", {"momentum": 1}),
    "criteres": ("Six critères", "La part des six critères de qualité remplis : croissance du chiffre d'affaires "
                 "et du free cash flow, ROCE, dette, nombre d'actions, marge de FCF.", {"criteres_part": 1}),
}

# Indicateurs moyens affichés pour un portefeuille (moyenne pondérée)
CARACTERISTIQUES = {
    "rentabilite": "Rentabilité (ROIC/ROE) moyenne",
    "marge_operationnelle": "Marge opérationnelle",
    "croissance_attendue": "Croissance attendue",
    "tri_implicite": "TRI implicite",
    "rendement_fcf": "Rendement FCF",
    "per_prospectif": "PER prospectif",
    "rendement_dividende": "Rendement du dividende",
    "mom_12_1": "Momentum 12-1 mois",
}


def returns_eur(tickers: list[str], years: float = 3.0) -> pd.DataFrame:
    """Rendements quotidiens en euros (jours ouvrés communs), sur `years` années."""
    prices = load_prices()
    cols = [t for t in tickers if t in prices.columns]
    if not cols:
        return pd.DataFrame()
    eur = prices_in_eur(prices[cols], currency_map(cols), load_fx())
    eur = eur[eur.index >= eur.index.max() - pd.Timedelta(days=int(365.25 * years))]
    eur = eur.ffill(limit=5)
    # Fermetures de marchés différentes selon les places : on ne garde que les jours ouvrés « pleins ».
    eur = eur[eur.notna().sum(axis=1) >= 0.8 * len(cols)]
    return eur.pct_change(fill_method=None).iloc[1:]


def _cap_weights(w: pd.Series, w_min: float, w_max: float, iterations: int = 50) -> pd.Series:
    """Projette des poids positifs sur {somme = 1, w_min ≤ w ≤ w_max} par remplissage itératif."""
    w = w.clip(lower=0).astype(float)
    w = w / w.sum() if w.sum() > 0 else pd.Series(1 / len(w), index=w.index)
    n = len(w)
    w_min = min(w_min, 1 / n)
    w_max = max(w_max, 1 / n)
    for _ in range(iterations):
        low, high = w < w_min - 1e-12, w > w_max + 1e-12
        if not low.any() and not high.any():
            break
        fixed = low | high
        w[low], w[high] = w_min, w_max
        free = ~fixed
        remaining = 1 - w[fixed].sum()
        if free.any() and w[free].sum() > 0:
            w[free] = w[free] / w[free].sum() * remaining
    return w / w.sum()


def _cap_sectors(w: pd.Series, sectors: pd.Series, cap: float, w_max: float, iterations: int = 50) -> pd.Series:
    """Ramène chaque secteur sous `cap` en redistribuant l'excédent aux autres secteurs."""
    w = w.copy()
    for _ in range(iterations):
        tot = w.groupby(sectors).sum()
        over = tot[tot > cap + 1e-9]
        if over.empty:
            break
        excess = 0.0
        for sec, val in over.items():
            members = sectors[sectors == sec].index
            w[members] *= cap / val
            excess += val - cap
        under = sectors[~sectors.isin(over.index)].index
        room = (w_max - w[under]).clip(lower=0)
        if room.sum() <= 0:
            break
        w[under] += room / room.sum() * min(excess, room.sum())
    return w / w.sum()


def note_construction(screener: pd.DataFrame, poids: dict[str, float] | None = None) -> pd.Series:
    """Note de 0 à 100 qui classe les candidats : moyenne pondérée des rangs centiles des composantes choisies.

    Une composante absente pour une valeur (regard non calculé, banque sans six critères) est ignorée et son poids
    reporté sur les autres. Le score composite départage les ex aequo (fréquents avec des notes de 1 à 5).
    """
    poids = {k: float(v) for k, v in (poids or {"score": 1}).items() if float(v) > 0}
    if not poids:
        poids = {"score": 1.0}
    df = screener.copy()
    remplis = pd.to_numeric(df.get("criteres_ok"), errors="coerce")
    evalues = pd.to_numeric(df.get("criteres_evalues"), errors="coerce")
    df["criteres_part"] = (remplis / evalues).where(evalues >= 2)
    if "pts_regards" not in df.columns and "regards_total" in df.columns:
        df["pts_regards"] = pd.to_numeric(df["regards_total"], errors="coerce") * 5
    somme = pd.Series(0.0, index=df.index)
    total = pd.Series(0.0, index=df.index)
    for col, p in poids.items():
        if col not in df.columns:
            continue
        rang = pd.to_numeric(df[col], errors="coerce").rank(pct=True) * 100
        somme += rang.fillna(0) * p
        total += rang.notna() * p
    note = (somme / total).where(total > 0)
    departage = pd.to_numeric(df.get("score"), errors="coerce").fillna(0) / 1e4
    return (note + departage).rename("note")


def qualite_suffisante(screener: pd.DataFrame, criteres_min: int = 0, exclure_moat_faible: bool = False) -> pd.Series:
    """Plancher de qualité : part des critères remplis au moins égale à `criteres_min` sur 6, sur au moins deux
    critères évalués (une banque n'en a que deux), et, si demandé, pas de moat estimé « Faible ».

    Une valeur sans critère évalué ne passe pas un plancher non nul ; une valeur sans moat (banque, assureur) n'est
    pas écartée pour cette raison.
    """
    ok = pd.Series(True, index=screener.index)
    if criteres_min > 0:
        remplis = pd.to_numeric(screener.get("criteres_ok"), errors="coerce")
        evalues = pd.to_numeric(screener.get("criteres_evalues"), errors="coerce")
        ok &= (evalues >= 2) & (remplis / evalues >= criteres_min / 6 - 1e-9)
    if exclure_moat_faible and "moat" in screener.columns:
        ok &= screener["moat"].astype(str) != "Faible"
    return ok.fillna(False)


def select(
    screener: pd.DataFrame,
    n: int,
    max_per_sector: int = 5,
    part_pea: float | None = 0.5,
    exclude: list[str] | None = None,
    criteres_min: int = 0,
    exclure_moat_faible: bool = False,
    cycliques_max: float | None = None,
    note: pd.Series | None = None,
) -> list[str]:
    """Meilleures notes éligibles, avec un nombre maximal de lignes par secteur et un ratio PEA/CTO.

    `note` classe les candidats (par défaut : le score composite). Options : plancher de qualité
    (`qualite_suffisante`) et part maximale des lignes dans les secteurs cycliques.
    """
    elig = screener[screener["statut"] == "Éligible"]
    elig = elig[qualite_suffisante(elig, criteres_min, exclure_moat_faible)]
    cle = (note if note is not None else pd.to_numeric(elig["score"], errors="coerce")).reindex(elig.index)
    elig = elig.loc[cle.dropna().sort_values(ascending=False).index]
    if exclude:
        elig = elig.drop(index=[t for t in exclude if t in elig.index])
    max_cycliques = int(math.floor(n * cycliques_max + 1e-9)) if cycliques_max is not None else n
    nb_cycliques = 0
    quotas = None
    if part_pea is not None:
        n_pea = int(round(n * part_pea))
        quotas = {"PEA": n_pea, "CTO": n - n_pea}
    chosen: list[str] = []
    per_sector: dict[str, int] = {}
    per_env: dict[str, int] = {}
    for t, row in elig.iterrows():
        sec, env = row.get("secteur"), row.get("enveloppe")
        if per_sector.get(sec, 0) >= max_per_sector:
            continue
        if quotas and per_env.get(env, 0) >= quotas.get(env, n):
            continue
        if sec in CYCLIQUES:
            if nb_cycliques >= max_cycliques:
                continue
            nb_cycliques += 1
        chosen.append(t)
        per_sector[sec] = per_sector.get(sec, 0) + 1
        per_env[env] = per_env.get(env, 0) + 1
        if len(chosen) >= n:
            break
    return chosen


def _cap_groupe(w: pd.Series, membres: pd.Series, cap: float, w_max: float) -> pd.Series:
    """Ramène le poids total d'un groupe de lignes sous `cap`, l'excédent allant aux autres lignes (sous `w_max`)."""
    w = w.copy()
    total = w[membres].sum()
    if total <= cap + 1e-9 or not (~membres).any():
        return w
    w[membres] *= cap / total
    room = (w_max - w[~membres]).clip(lower=0)
    if room.sum() > 0:
        w[~membres] += room / room.sum() * min(total - cap, room.sum())
    return w / w.sum()


def weight(
    tickers: list[str],
    screener: pd.DataFrame,
    method: str = "score_vol",
    w_min: float = 0.02,
    w_max: float = 0.08,
    sector_max: float = 0.25,
    returns: pd.DataFrame | None = None,
    cycliques_max: float | None = None,
    note: pd.Series | None = None,
) -> pd.Series:
    tickers = list(tickers)
    sectors = screener.reindex(tickers)["secteur"].fillna("Autre")
    if method == "egal":
        w = pd.Series(1.0, index=tickers)
    elif method == "score_vol":
        score = (note.reindex(tickers) if note is not None else screener.reindex(tickers)["score"]).fillna(50)
        vol = screener.reindex(tickers)["volatilite"].astype(float)
        vol = vol.fillna(vol.median()).clip(lower=0.12)
        w = (score / 50) ** 2 / vol
    elif method == "variance_min":
        r = returns if returns is not None else returns_eur(tickers)
        r = r.reindex(columns=tickers).dropna(axis=1, how="all").fillna(0)
        cov = r.cov().values * 252
        names = list(r.columns)
        n = len(names)
        bounds = [(min(w_min, 1 / n), max(w_max, 1 / n))] * n
        cons = [{"type": "eq", "fun": lambda x: x.sum() - 1}]
        sec = sectors.reindex(names)
        for s in sec.unique():
            mask = (sec == s).values.astype(float)
            cons.append({"type": "ineq", "fun": lambda x, m=mask: sector_max - x @ m})
        from scipy.optimize import minimize  # import différé (démarrage)

        res = minimize(lambda x: x @ cov @ x, np.full(n, 1 / n), bounds=bounds, constraints=cons,
                       method="SLSQP", options={"maxiter": 500})
        w = pd.Series(res.x if res.success else np.full(n, 1 / n), index=names).reindex(tickers).fillna(w_min)
    else:
        raise ValueError(f"Méthode inconnue : {method}")
    w = _cap_weights(w, w_min, w_max)
    w = _cap_sectors(w, sectors, sector_max, w_max)
    w = _cap_weights(w, w_min, w_max)
    if cycliques_max is not None:
        w = _cap_groupe(w, sectors.isin(CYCLIQUES), cycliques_max, w_max)
    return w.rename("poids")


def build_quant_portfolio(screener: pd.DataFrame, strategy: dict | None = None, **overrides) -> pd.Series:
    """Portefeuille 100 % systématique à partir des paramètres de `strategie.json` (surchargeables)."""
    c = dict((strategy or load_strategy())["construction"])
    c.update({k: v for k, v in overrides.items() if v is not None})
    part_pea = c.get("part_pea")
    notation = c.get("notation") or {"score": 1}
    if isinstance(notation, str):  # nom d'une méthode proposée (ligne de commande)
        notation = NOTATIONS[notation][2]
    note = note_construction(screener, notation)
    tickers = select(screener, int(c["nb_lignes"]), int(c["max_par_secteur"]), part_pea,
                     criteres_min=int(c.get("criteres_min", 0)), exclure_moat_faible=bool(c.get("exclure_moat_faible")),
                     cycliques_max=c.get("cycliques_max"), note=note)
    w = weight(tickers, screener, c["methode"], c["poids_min"], c["poids_max"], c["secteur_max"],
               cycliques_max=c.get("cycliques_max"), note=note)
    if part_pea is not None and 0 < part_pea < 1:
        env = screener.reindex(w.index)["enveloppe"]
        for e, target in (("PEA", part_pea), ("CTO", 1 - part_pea)):
            m = env == e
            if m.any() and w[m].sum() > 0:
                w[m] = w[m] / w[m].sum() * target
        w = w / w.sum()
    return w.sort_values(ascending=False)


def model_weights(path: Path = MODELE_CSV) -> pd.Series:
    mp = load_model_portfolio(path)
    if mp.empty:
        return pd.Series(dtype=float)
    w = mp["poids_cible"].astype(float)  # saisis en % ou en fraction : la normalisation couvre les deux
    return (w / w.sum()).rename("poids")


COLONNES_MODELE = ["ticker", "nom", "enveloppe", "poche", "conviction", "poids_cible", "these", "risque_principal",
                   "condition_vente", "alternative"]


def nouvelle_composition(existant: pd.DataFrame, lignes: list[tuple[str, str, str, float]],
                         noms: dict[str, str] | None = None) -> pd.DataFrame:
    """Composition modifiée dans l'outil : `lignes` = (ticker, compte, poche, poids). Les poids sont ramenés à 100 %
    (deux décimales) ; une valeur citée deux fois cumule ses poids ; les colonnes déjà remplies d'une valeur (thèse,
    condition de vente…) sont gardées. Lève ValueError si aucune ligne n'a de poids positif."""
    cumul: dict[str, list] = {}
    for ticker, compte, poche, poids in lignes:
        if not ticker or not (isinstance(poids, (int, float)) and math.isfinite(poids)) or poids <= 0:
            continue
        if ticker in cumul:
            cumul[ticker][2] += float(poids)
        else:
            cumul[ticker] = [compte or "CTO", poche or "Cœur", float(poids)]
    total = sum(v[2] for v in cumul.values())
    if total <= 0:
        raise ValueError("aucune ligne avec un poids positif")
    anciennes = existant.reset_index() if existant.index.name == "ticker" else existant
    colonnes = COLONNES_MODELE + [c for c in anciennes.columns if c not in COLONNES_MODELE]
    deja = anciennes.set_index("ticker") if "ticker" in anciennes.columns else pd.DataFrame()
    rangs = []
    for ticker, (compte, poche, poids) in sorted(cumul.items(), key=lambda x: -x[1][2]):
        r = {c: "" for c in colonnes}
        if ticker in deja.index:
            r.update({c: ("" if pd.isna(v) else v) for c, v in deja.loc[ticker].items() if c in r})
        r.update(ticker=ticker, enveloppe=compte, poche=poche, poids_cible=round(poids / total * 100, 2))
        r["nom"] = r["nom"] or (noms or {}).get(ticker, ticker)
        rangs.append(r)
    return pd.DataFrame(rangs, columns=colonnes)


def compte_principal(w: pd.Series | None = None, mp: pd.DataFrame | None = None) -> str:
    """Enveloppe qui porte le plus de poids cible : compte proposé par défaut pour un apport ou une saisie."""
    w = model_weights() if w is None else w
    mp = load_model_portfolio() if mp is None else mp
    return w.groupby(mp["enveloppe"]).sum().idxmax() if not w.empty else "PEA"


def lignes_a_ecarter(screener: pd.DataFrame, tickers) -> dict[str, str]:
    """Lignes à ne pas renforcer : sorties des filtres de qualité, ou en chute marquée (thèse à réexaminer).

    Les fonds n'ont ni filtres ni alertes fondamentales : ils ne sont jamais écartés.
    """
    out = {}
    for t in tickers:
        if t not in screener.index:
            continue
        r = screener.loc[t]
        if r.get("statut") == "Exclu":
            out[t] = "sortie des filtres : " + str(r.get("motifs_exclusion") or "").split(" ; ")[0]
        elif "Tendance très négative" in str(r.get("alertes") or ""):
            out[t] = "tendance très négative, thèse à réexaminer avant de renforcer"
    return out


def characteristics(weights: pd.Series, screener: pd.DataFrame) -> dict:
    """Moyennes pondérées des indicateurs (sur les lignes où l'indicateur existe)."""
    out = {}
    df = screener.reindex(weights.index)
    for col, label in CARACTERISTIQUES.items():
        if col not in df.columns:
            continue
        v = pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
        m = v.notna()
        if col == "per_prospectif":
            # Moyenne harmonique : la seule correcte pour un ratio prix / bénéfice.
            m &= v > 0
            out[label] = weights[m].sum() / (weights[m] / v[m]).sum() if m.any() else math.nan
        else:
            out[label] = (v[m] * weights[m]).sum() / weights[m].sum() if m.any() else math.nan
    return out


def risk_profile(weights: pd.Series, returns: pd.DataFrame | None = None, years: float = 3.0) -> dict:
    r = returns if returns is not None else returns_eur(list(weights.index), years)
    cols = [c for c in weights.index if c in r.columns]
    if not cols:
        return {}
    w = weights[cols] / weights[cols].sum()
    rr = r[cols].fillna(0)
    cov = rr.cov() * 252
    vol_p = float(np.sqrt(w @ cov @ w))
    vols = np.sqrt(np.diag(cov))
    contrib = w * (cov @ w) / vol_p**2 if vol_p > 0 else w * 0
    return {
        "volatilite": vol_p,
        "ratio_diversification": float((w * vols).sum() / vol_p) if vol_p > 0 else math.nan,
        "nombre_effectif": float(1 / (w**2).sum()),
        "contribution_risque": contrib.sort_values(ascending=False),
        "correlation": rr.corr(),
    }


def breakdown(weights: pd.Series, screener: pd.DataFrame, by: str) -> pd.Series:
    labels = screener.reindex(weights.index)[by].fillna("Autre")
    return weights.groupby(labels).sum().sort_values(ascending=False)
