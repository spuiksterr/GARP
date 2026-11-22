"""Risque homme-clé (« key man risk ») : à quel point la société dépend d'une seule personne.

Note de 0 à 10 (10 : dépendance la plus forte), calculée sur des faits publiés par Yahoo (liste des dirigeants avec
leur fonction et leur âge, part du capital détenue par les initiés, note de risque du conseil d'ISS, effectif) :

| Facteur | Points |
|---|---|
| Le fondateur dirige encore la société (directeur général) | 4 |
| Le fondateur préside le conseil, sans être directeur général | 3 |
| Le directeur général préside aussi le conseil (PDG) | 1,5 |
| Directeur général de 70 ans ou plus (succession à préparer) ; de 65 à 69 ans | 2 ; 1 |
| Initiés (dirigeants, familles fondatrices) détenant 30 % du capital ou plus ; de 10 à 30 % | 2 ; 1 |
| Conseil d'administration peu indépendant (risque du conseil ISS de 8 ou plus, sur 10) | 1 |
| Petite équipe : moins de 3 000 salariés | 1 |

Puis la correction manuelle de config/homme_cle.csv (« ticker;ajustement;motif »), pour ce que les données ne disent
pas : un fondateur absent de la liste de Yahoo, une succession déjà organisée. Le total est borné à 0-10.
Niveaux : faible sous 3, modéré de 3 à 5,5, élevé à partir de 6.

La note est un signal à lire, pas une sanction : un fondateur aux commandes est aussi souvent une force (vision longue,
intérêts alignés). Elle n'entre ni dans la note GARP ni dans les filtres d'exclusion.
"""
from __future__ import annotations

import math
import re

import pandas as pd

from .config import CONFIG_DIR, read_csv_fr

AJUSTEMENTS_CSV = CONFIG_DIR / "homme_cle.csv"
SEUIL_MODERE, SEUIL_ELEVE = 3.0, 6.0
MAX_DIRIGEANTS = 6  # gardés dans le cache des fondamentaux

_FONDATEUR = re.compile(r"found|fondat", re.I)
_DG = re.compile(r"\bCEO\b|chief executive|\bPDG\b|directeur g[ée]n[ée]ral|managing director", re.I)
_PRESIDENT_EXECUTIF = re.compile(r"executive chair", re.I)
_PRESIDENT = re.compile(r"chair|pr[ée]sident du conseil|\bPDG\b", re.I)
# « Chair of the Board of Management » (directoire néerlandais ou allemand) n'est pas la présidence du conseil.
_DIRECTOIRE = re.compile(r"board of management|management board|executive board|supervisory", re.I)
_CIVILITE = re.compile(r"^(mr|mrs|ms|dr|prof|sir)\.?\s+", re.I)


def dirigeants_yahoo(officers) -> list[dict]:
    """Liste des dirigeants de Yahoo (companyOfficers) réduite à nom, fonction et âge, pour le cache."""
    out = []
    for o in (officers or [])[:MAX_DIRIGEANTS]:
        if not isinstance(o, dict) or not o.get("name"):
            continue
        age = o.get("age")
        if not isinstance(age, (int, float)) and isinstance(o.get("yearBorn"), (int, float)):
            age = pd.Timestamp.today().year - int(o["yearBorn"])
        out.append({"nom": " ".join(_CIVILITE.sub("", str(o["name"])).split()),
                    "fonction": " ".join(str(o.get("title") or "").split()),
                    "age": int(age) if isinstance(age, (int, float)) and math.isfinite(age) else None})
    return out


def dirigeant_principal(dirigeants: list[dict]) -> dict | None:
    """Le directeur général ; à défaut le président exécutif, puis le premier de la liste."""
    for motif in (_DG, _PRESIDENT_EXECUTIF):
        for d in dirigeants:
            if motif.search(d.get("fonction", "")):
                return d
    return dirigeants[0] if dirigeants else None


def _nombre(v) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return math.nan
    return v if math.isfinite(v) else math.nan


def niveau(note: float) -> str:
    if not math.isfinite(note):
        return "Inconnu"
    return "Élevé" if note >= SEUIL_ELEVE else "Modéré" if note >= SEUIL_MODERE else "Faible"


def evaluer(info: dict, ajustement: float = 0.0, motif: str = "") -> dict:
    """Note, niveau, facteurs retenus (texte) et dirigeant principal, d'après les infos Yahoo d'une société."""
    dirigeants = info.get("dirigeants") or []
    initie = _nombre(info.get("heldPercentInsiders"))
    conseil = _nombre(info.get("boardRisk"))
    effectif = _nombre(info.get("fullTimeEmployees"))
    vide = {"homme_cle": math.nan, "homme_cle_niveau": "Inconnu", "homme_cle_facteurs": "",
            "homme_cle_dirigeant": ""}
    if not dirigeants and not math.isfinite(initie) and not ajustement:
        return vide  # rien de propre à la société : l'effectif seul ne dit pas grand-chose
    points: list[tuple[float, str]] = []
    dg = dirigeant_principal(dirigeants)
    if dg is not None:
        fonction = dg.get("fonction", "")
        if _FONDATEUR.search(fonction):
            points.append((4, f"le fondateur dirige la société ({dg['nom']})"))
        else:
            fondateur_president = next((d for d in dirigeants if _FONDATEUR.search(d.get("fonction", ""))
                                        and _PRESIDENT.search(d["fonction"]) and not _DIRECTOIRE.search(d["fonction"])),
                                       None)
            if fondateur_president is not None:
                points.append((3, f"le fondateur préside le conseil ({fondateur_president['nom']})"))
        if _DG.search(fonction) and _PRESIDENT.search(fonction) and not _DIRECTOIRE.search(fonction):
            points.append((1.5, "directeur général et président du conseil à la fois"))
        age = dg.get("age")
        if isinstance(age, (int, float)) and age >= 70:
            points.append((2, f"dirigeant de {int(age)} ans : succession à préparer"))
        elif isinstance(age, (int, float)) and age >= 65:
            points.append((1, f"dirigeant de {int(age)} ans"))
    if math.isfinite(initie) and initie >= 0.10:
        points.append((2 if initie >= 0.30 else 1, f"initiés détenant {initie * 100:.0f} % du capital"))
    if math.isfinite(conseil) and conseil >= 8:
        points.append((1, f"conseil peu indépendant (risque ISS {int(conseil)}/10)"))
    if math.isfinite(effectif) and effectif < 3000:
        points.append((1, f"petite équipe ({int(effectif):,} salariés)".replace(",", " ")))
    if ajustement:
        signe = "+" if ajustement > 0 else ""
        points.append((ajustement, f"correction manuelle {signe}{ajustement:g}" + (f" : {motif}" if motif else "")))
    note = min(max(sum(p for p, _ in points), 0.0), 10.0)
    return {
        "homme_cle": note,
        "homme_cle_niveau": niveau(note),
        "homme_cle_facteurs": " ; ".join(t for _, t in points) if points else "aucun facteur de dépendance relevé",
        "homme_cle_dirigeant": (f"{dg['nom']} ({dg['fonction']}" + (f", {dg['age']} ans" if dg.get("age") else "") + ")")
        if dg else "",
    }


def relire(tickers: list[str], pause: float = 1.2, progress=None) -> dict[str, dict]:
    """Relit sur Yahoo les seuls dirigeants, part des initiés et risque du conseil des `tickers` déjà en cache, puis
    reporte la note dans les indicateurs calculés. Les comptes et la date de la fiche ne changent pas : le
    renouvellement par roulement des fondamentaux suit son cours. Renvoie la note de chaque valeur relue."""
    import time

    import yfinance as yf

    from .config import METRICS_PARQUET, ecrire_json, ecriture_atomique
    from .data import fundamentals_path, load_fundamentals

    corrections = load_ajustements()
    notes: dict[str, dict] = {}
    for i, t in enumerate(tickers, 1):
        fund = load_fundamentals(t)
        if not fund:
            continue
        try:
            brut = yf.Ticker(t).info or {}
        except Exception:  # Yahoo limite le débit : la valeur garde ses données, on passe à la suivante
            brut = {}
        if brut:
            info = fund.setdefault("info", {})
            info["dirigeants"] = dirigeants_yahoo(brut.get("companyOfficers"))
            for cle in ("heldPercentInsiders", "boardRisk", "fullTimeEmployees"):
                if brut.get(cle) is not None:
                    info[cle] = brut[cle]
            ecrire_json(fundamentals_path(t), fund)
            notes[t] = evaluer(info, *corrections.get(t, (0.0, "")))
        if progress:
            progress(i, len(tickers), t)
        time.sleep(pause)
    if notes and METRICS_PARQUET.exists():
        m = pd.read_parquet(METRICS_PARQUET)
        for col in ("homme_cle", "homme_cle_niveau", "homme_cle_facteurs", "homme_cle_dirigeant"):
            if col not in m.columns:
                m[col] = math.nan if col == "homme_cle" else pd.Series(pd.NA, index=m.index, dtype="string")
            for t, n in notes.items():
                if t in m.index:
                    m.loc[t, col] = n[col]
        ecriture_atomique(METRICS_PARQUET, m.to_parquet)
    return notes


def load_ajustements() -> dict[str, tuple[float, str]]:
    """Corrections manuelles : ticker -> (points ajoutés ou retirés, motif)."""
    if not AJUSTEMENTS_CSV.exists():
        return {}
    df = read_csv_fr(AJUSTEMENTS_CSV, numeric=("ajustement",))
    return {str(r["ticker"]): (float(r["ajustement"]) if pd.notna(r["ajustement"]) else 0.0, str(r.get("motif") or ""))
            for _, r in df.iterrows() if r.get("ticker")}
