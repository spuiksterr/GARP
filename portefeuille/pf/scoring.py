"""Filtres d'exclusion et score composite Qualité / Croissance / Valorisation / Momentum.

Étape 1 — exclure les entreprises qui ne sont pas de premier ordre (inspiré des 7 critères
« anti-médiocrité » d'ai-berkshire) : rentabilité, cash réel, solidité financière, pouvoir de prix,
respect de l'actionnaire.
Étape 2 — classer les survivantes par rangs centiles (0-100) au sein de l'univers, pilier par pilier,
puis combiner les piliers avec les poids de `config/strategie.json`.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import criteres
from .config import CACHE_DIR, METRICS_PARQUET, ecrire_json, ecriture_atomique, lire_json, load_strategy
from .formats import nombre, pct
from .metrics import compute_all, load_metrics, metrics_a_jour
from .regards import AJUSTEMENTS_CSV, notes_frame
from .sante import health_alerts, health_points

# Screener tout prêt, calculé par le flux de la nuit (pf export-outil) : la version installée l'ouvre en 0,05 s au
# lieu de 2 s de calcul. Il ne sert que si son empreinte correspond à ce qui est sur le poste.
SCREENER_PARQUET = CACHE_DIR / "screener.parquet"
SCREENER_META = CACHE_DIR / "screener.meta.json"
_CODE_DU_CALCUL = ("scoring.py", "regards.py", "criteres.py", "sante.py")

PILIERS = {
    "qualite": [
        ("rentabilite", +1), ("marge_brute", +1), ("marge_operationnelle", +1),
        ("conversion_fcf", +1), ("stabilite_marge", -1), ("dette_nette_ebitda", -1),
        ("evolution_actions", -1),
    ],
    "croissance": [
        ("croiss_ca", +1), ("croiss_bpa", +1), ("croiss_fcf_action", +1),
        ("croiss_bpa_estimee", +1), ("croiss_ca_estimee", +1),
    ],
    "valorisation": [
        ("rendement_fcf_hors_sbc", +1), ("rendement_benefices", +1), ("tri_implicite", +1),
        ("per_prospectif", -1),
    ],
    "momentum": [("mom_12_1", +1), ("perf_6m", +1), ("ecart_mm200", +1)],
}

LIBELLES_PILIERS = {
    "qualite": "Qualité", "croissance": "Croissance", "valorisation": "Valorisation", "momentum": "Momentum",
}


def _num(row: pd.Series, key: str) -> float:
    v = row.get(key)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return math.nan
    return v if np.isfinite(v) else math.nan


def exclusion_reasons(ticker: str, row: pd.Series, f: dict) -> list[str]:
    reasons = []
    fin = bool(row.get("financiere"))
    rent = _num(row, "rentabilite")
    gm = _num(row, "marge_brute")
    if not np.isfinite(rent):
        # Les filtres ne retiennent que les valeurs connues : sans ce motif, une rentabilité incalculable
        # (bilan ou résultat absents) passerait pour saine. Les autres motifs restent affichés.
        reasons.append("Données insuffisantes : rentabilité incalculable (bilan ou résultat absents)")
    if np.isfinite(rent) and rent < f["rentabilite_min"]:
        # Dérogation « devenue rentable » (exemption A d'ai-berkshire) : la moyenne est plombée par
        # une phase d'investissement terminée, l'activité génère désormais du cash.
        recent = _num(row, "rentabilite_derniere")
        devenue_rentable = (
            np.isfinite(recent) and recent >= 1.5 * f["rentabilite_min"]
            and (fin or (np.isfinite(gm) and gm >= 0.30))
            and bool(row.get("ocf_positif_2a"))
        )
        if not devenue_rentable:
            reasons.append(f"Rentabilité moyenne faible ({pct(rent, 2)} < {pct(f['rentabilite_min'], 0)})")
    if not fin:
        fcf_cum = _num(row, "fcf_cumule")
        if f.get("exiger_fcf_cumule_positif", True) and np.isfinite(fcf_cum) and fcf_cum <= 0:
            reasons.append("Flux de trésorerie disponible cumulé négatif")
        cov = _num(row, "couverture_interets")
        if np.isfinite(cov) and cov < f["couverture_interets_min"]:
            reasons.append(f"Couverture des intérêts faible ({nombre(cov, 1)}x)")
        nd = _num(row, "dette_nette_ebitda")
        if np.isfinite(nd) and nd > f["dette_nette_ebitda_max"]:
            reasons.append(f"Endettement élevé ({nombre(nd, 1)}x l'EBITDA)")
        if np.isfinite(gm) and gm < f["marge_brute_min"] and not (np.isfinite(rent) and rent >= f["exemption_marge_brute_roic"]):
            reasons.append(f"Marge brute faible ({pct(gm, 0)}) sans rotation du capital compensatoire")
    dil = _num(row, "evolution_actions")
    if np.isfinite(dil) and dil > f["dilution_max_par_an"] and ticker not in f.get("exemptions_dilution", {}):
        reasons.append(f"Dilution des actionnaires ({pct(dil, 1, signe=True)} d'actions par an sur 3 ans)")
    ni = _num(row, "benefice_ttm")
    if f.get("exiger_benefice_positif", True) and np.isfinite(ni) and ni <= 0:
        reasons.append("Perte sur les 12 derniers mois")
    return reasons


def alerts(row: pd.Series) -> list[str]:
    out = []
    mom = _num(row, "mom_12_1")
    if np.isfinite(mom) and mom < -0.30:
        out.append(f"Tendance très négative ({pct(mom, 0)} sur 12 mois)")
    tri = _num(row, "tri_implicite")
    if np.isfinite(tri) and tri < 0.06:
        out.append(f"Valorisation exigeante (TRI implicite {pct(tri)})")
    gi = _num(row, "croissance_implicite")
    if np.isfinite(gi) and gi > 0.20:
        out.append(f"Le cours suppose {pct(gi, 0)} de croissance annuelle sur 5 ans")
    nd = _num(row, "dette_nette_ebitda")
    if np.isfinite(nd) and 2.5 < nd <= 3.5 and not row.get("financiere"):
        out.append(f"Endettement à surveiller ({nombre(nd, 1)}x l'EBITDA)")
    if (row.get("nb_exercices") or 0) < 4:
        out.append("Historique financier court")
    if row.get("holding"):
        out.append("Holding : valoriser sur la décote à l'actif net")
    return out + health_alerts(row)


# Banques, assureurs et holdings ne se comparent pas aux industriels sur la qualité (ROE contre ROIC)
# ni sur la valorisation (PER contre VE/EBIT) : pour ces deux piliers, ils sont classés entre eux.
PILIERS_PAR_GROUPE = {"qualite", "valorisation"}


def pillar_scores(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    groups = df["financiere"].fillna(False).astype(bool) if "financiere" in df.columns else None
    for pilier, metrics in PILIERS.items():
        ranks = []
        for col, sign in metrics:
            if col not in df.columns:
                continue
            s = pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan) * sign
            if pilier in PILIERS_PAR_GROUPE and groups is not None:
                ranks.append(s.groupby(groups).rank(pct=True) * 100)
            else:
                ranks.append(s.rank(pct=True) * 100)
        out[pilier] = pd.concat(ranks, axis=1).mean(axis=1, skipna=True).fillna(50.0) if ranks else 50.0
    return out


# La valorisation a son propre bloc : dans le seul bloc Piliers, elle ne pesait que 5 % du score (25 % d'un
# bloc sur cinq), alors que les autres blocs mesurent surtout la qualité. La grille des six critères
# (criteres.py) recoupe les piliers qualité et croissance : poids nul par défaut. Les quatre regards non plus ne
# comptent pas (22/11/2026) : quatre grilles « qualité » additionnées doublaient le pilier qualité (corrélation de
# rang de 0,59) ; ils se lisent un par un (config.load_strategy force leur poids à 0).
POIDS_SCORE = {"piliers": 1, "valorisation": 1, "regards": 0, "piotroski": 1, "altman": 1, "beneish": 1, "criteres": 0}
LIBELLES_BLOCS = {"piliers": "Piliers", "valorisation": "Valorisation", "regards": "Regards", "piotroski": "Piotroski",
                  "altman": "Altman", "beneish": "Beneish", "criteres": "Six critères"}
CRITERES_MIN_EVALUES = 4  # en dessous (banques, assureurs, holdings), le bloc reçoit la médiane


def composite_score(df: pd.DataFrame, weights: dict | None = None) -> pd.DataFrame:
    """Score final : moyenne pondérée des analyses, chacune sur 100, et détail des points.

    Un signal absent (banques, assureurs, holdings) reçoit la médiane de l'univers : une moyenne limitée
    aux signaux disponibles avantagerait ou pénaliserait ces sociétés mécaniquement.
    """
    weights = weights or POIDS_SCORE
    pts = health_points(df)
    pts["pts_regards"] = df["regards_total"] * 5
    if "criteres_ok" in df.columns:
        evalues = pd.to_numeric(df["criteres_evalues"], errors="coerce")
        pts["pts_criteres"] = (pd.to_numeric(df["criteres_ok"], errors="coerce") / evalues * 100).where(
            evalues >= CRITERES_MIN_EVALUES)
    if "valorisation" in df.columns:
        pts["pts_valorisation"] = df["valorisation"]
    parts = pts.rename(columns=lambda c: c.removeprefix("pts_")).assign(piliers=df["score_piliers"])
    parts = parts.dropna(axis=1, how="all")
    parts = parts.fillna(parts.median())
    w = pd.Series(weights, dtype=float).reindex(parts.columns).fillna(0.0)
    pts["score"] = (parts * w).sum(axis=1) / w.sum()
    return pts


def _empreinte(strategy: dict) -> dict:
    """Ce dont dépend le screener : stratégie, indicateurs, corrections des regards et code du calcul. Les fins de
    ligne sont normalisées (GitHub construit sous Linux et sous Windows)."""
    def h(octets: bytes) -> str:
        return hashlib.sha1(octets.replace(b"\r\n", b"\n")).hexdigest()

    ici = Path(__file__).resolve().parent
    return {
        "strategie": h(json.dumps(strategy, sort_keys=True, ensure_ascii=False).encode("utf-8")),
        "indicateurs": h(METRICS_PARQUET.read_bytes()) if METRICS_PARQUET.exists() else "",
        "ajustements": h(AJUSTEMENTS_CSV.read_bytes()) if AJUSTEMENTS_CSV.exists() else "",
        "code": h(b"".join((ici / f).read_bytes() for f in _CODE_DU_CALCUL)),
    }


def enregistrer_screener(strategy: dict | None = None) -> pd.DataFrame:
    """Calcule le screener et l'enregistre avec son empreinte (flux de la nuit, avant l'archive de l'outil)."""
    strategy = strategy or load_strategy()
    sc = build_screener(strategy=strategy)
    ecriture_atomique(SCREENER_PARQUET, sc.to_parquet)
    ecrire_json(SCREENER_META, _empreinte(strategy), indent=1)
    return sc


def screener_prepare(strategy: dict | None = None) -> pd.DataFrame | None:
    """Le screener enregistré, s'il a été calculé avec exactement ce qui est sur le poste ; sinon None."""
    if not SCREENER_PARQUET.exists():
        return None
    meta = lire_json(SCREENER_META)
    if not meta or meta != _empreinte(strategy or load_strategy()):
        return None
    try:
        return pd.read_parquet(SCREENER_PARQUET)
    except (OSError, ValueError):
        return None


def build_screener(metrics: pd.DataFrame | None = None, strategy: dict | None = None) -> pd.DataFrame:
    """Tableau complet : indicateurs + scores par pilier + score composite + statut + motifs."""
    strategy = strategy or load_strategy()
    df = metrics if metrics is not None else load_metrics()
    if df.empty or (metrics is None and not metrics_a_jour(strategy)):
        # Paramètres de valorisation modifiés depuis le dernier calcul : TRI et croissance implicites à refaire.
        df = compute_all()
    df = criteres.reappliquer(df, strategy.get("criteres"))
    df = df[df.get("statut_donnees", "ok").astype(str).isin(["ok", "partielles"])].copy()
    # Les fonds (ETF, ETC) restent visibles avec leurs indicateurs de cours, hors classement.
    fonds = df["fonds"].fillna(False).astype(bool) if "fonds" in df.columns else pd.Series(False, index=df.index)
    funds, df = df[fonds].copy(), df[~fonds].copy()
    scores = pillar_scores(df)
    weights = strategy["poids_piliers"]
    total = sum(weights.values()) or 1.0
    df = df.join(scores)
    df["score_piliers"] = sum(scores[p] * w for p, w in weights.items()) / total
    filtres = strategy["filtres"]
    df["motifs_exclusion"] = [" ; ".join(exclusion_reasons(t, r, filtres)) for t, r in df.iterrows()]
    df["alertes"] = [" ; ".join(alerts(r)) for _, r in df.iterrows()]
    df["statut"] = np.where(df["motifs_exclusion"].str.len() > 0, "Exclu", "Éligible")
    df = df.join(notes_frame(df))
    df = df.join(composite_score(df, strategy.get("poids_score")))
    if not funds.empty:
        df = pd.concat([df, funds.assign(motifs_exclusion="", alertes="", statut="Fonds")])
    df = df.sort_values(["statut", "score"], ascending=[False, False])
    df["rang"] = np.nan
    elig = df["statut"] == "Éligible"
    df.loc[elig, "rang"] = np.arange(1, elig.sum() + 1)
    return df
