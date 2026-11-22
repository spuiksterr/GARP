"""Comptes officiels déposés à la SEC, pour recouper les fondamentaux Yahoo des sociétés américaines.

Source : API publique data.sec.gov (« companyfacts » : toutes les valeurs XBRL des rapports 10-K, 10-Q,
20-F…). La SEC demande que tout programme s'annonce avec un nom et une adresse de contact : renseigner
`contact_sec` dans profil/prive.json (par exemple « Portefeuille perso prenom@exemple.fr »),
sans quoi l'étape est sautée. Seuls les postes annuels utiles sont gardés en cache.

Le recoupement porte sur le dernier exercice que Yahoo et la SEC ont en commun : chiffre d'affaires,
résultat net, flux d'exploitation, investissements, fonds propres et total du bilan. Une société change
parfois de poste XBRL (« Revenues » puis « RevenueFromContract… ») et Yahoo retient parfois le chiffre
retraité l'année suivante : un écart n'est compté que si aucune des valeurs déposées ne concorde.

Les séries par poste XBRL (`series`) servent aussi à prolonger dans le passé les quatre exercices
fournis par Yahoo, pour les critères calculés sur cinq ans (voir criteres.py).
"""
from __future__ import annotations

import gzip
import json
import math
import time
import urllib.request
from collections.abc import Callable
from datetime import datetime

import pandas as pd

from . import esef, postes
from .config import SEC_DIR, ecrire_json, etalement, lire_json, load_prive, load_strategy

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{:010d}.json"
PAUSE = 0.15  # la SEC tolère 10 requêtes par seconde

# Postes XBRL acceptés pour chaque grandeur (us-gaap, puis ifrs-full pour les déposants étrangers).
CONCEPTS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "Revenue",
                "RevenueFromContractsWithCustomers"],
    "net_income": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic",
                   "ProfitLossAttributableToOwnersOfParent"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "CashFlowsFromUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
    "equity": ["StockholdersEquity", "EquityAttributableToOwnersOfParent", "Equity"],
    "assets": ["Assets"],
    # Postes servant seulement à prolonger l'historique (critères sur cinq ans).
    "op_income": ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"],
    "current_liabilities": ["LiabilitiesCurrent", "CurrentLiabilities"],
    "shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense", "AdjustmentsForSharebasedPayments"],
    # Graphiques de la fiche : un poste n'est repris que s'il reproduit les chiffres Yahoo (postes.prolonger).
    "gross_profit": ["GrossProfit"],
    "dividends": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsAndShortTermInvestments", "CashAndCashEquivalents"],
    "debt": ["LongTermDebt", "DebtLongtermAndShorttermCombinedAmount"],
}
BILAN = {"equity", "assets", "current_liabilities", "cash", "debt"}  # valeur à une date, et non sur une période
# Postes recoupés (voir postes.py pour les libellés Yahoo).
RECOUPES = ["revenue", "net_income", "ocf", "capex", "equity", "assets"]
LIBELLES = {"revenue": "CA", "net_income": "résultat net", "ocf": "flux d'exploitation", "capex": "investissements",
            "equity": "fonds propres", "assets": "total du bilan"}
# Les investissements ne déclenchent pas d'écart : Yahoo y ajoute souvent les logiciels et
# incorporels immobilisés, que la SEC isole dans d'autres postes.
CONTROLES = ["revenue", "net_income", "ocf", "equity", "assets"]
FORMULAIRES = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "10-KT")
TOLERANCE = 0.03
FORMAT = 4  # version du cache : un fichier d'un format antérieur est retéléchargé (4 : postes des graphiques de la fiche)


def contact() -> str:
    """Adresse de contact exigée par la SEC : profil/prive.json (ancien emplacement : strategie.json)."""
    return (load_prive().get("contact_sec") or load_strategy().get("sources", {}).get("contact_sec") or "").strip()


def _brut(url: str, agent: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": agent, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return raw


def _get(url: str, agent: str) -> dict:
    return json.loads(_brut(url, agent))


def sec_ticker(ticker: str) -> str | None:
    """Ticker Yahoo -> ticker SEC. None pour une valeur cotée hors des États-Unis."""
    return None if "." in ticker else ticker.upper()


def ticker_map(agent: str, max_age_days: float = 30) -> dict[str, int]:
    path = SEC_DIR / "company_tickers.json"
    raw = None
    if path.exists() and (time.time() - path.stat().st_mtime) / 86400 < max_age_days:
        raw = lire_json(path)
    if not raw:
        raw = _get(TICKERS_URL, agent)
        ecrire_json(path, raw)
    return {v["ticker"].upper(): int(v["cik_str"]) for v in raw.values()}


def extract(facts: dict) -> dict:
    """companyfacts -> valeurs des exercices annuels, sous deux formes.

    - `postes` : {grandeur: {date de clôture: [toutes les valeurs déposées]}}, pour le recoupement ;
    - `series` : {grandeur: {poste XBRL: {date de clôture: dernière valeur déposée}}}, pour l'historique.
    """
    postes: dict[str, dict[str, list[float]]] = {}
    series: dict[str, dict[str, dict[str, float]]] = {}
    devise = None
    for key, concepts in CONCEPTS.items():
        vals: dict[str, set[float]] = {}
        for taxo in ("us-gaap", "ifrs-full"):
            for c in concepts:
                units = facts.get("facts", {}).get(taxo, {}).get(c, {}).get("units", {})
                if key == "shares":
                    unit = "shares" if "shares" in units else None
                else:
                    unit = "USD" if "USD" in units else next((u for u in units if len(u) == 3), None)
                    if unit is None:
                        continue
                    devise = devise or unit
                    if unit != devise:
                        continue
                if unit is None:
                    continue
                latest: dict[str, tuple[str, float]] = {}
                for x in units[unit]:
                    if x.get("form") not in FORMULAIRES or x.get("val") is None:
                        continue
                    if key not in BILAN:
                        if not x.get("start"):
                            continue
                        days = (pd.Timestamp(x["end"]) - pd.Timestamp(x["start"])).days
                        if not 340 <= days <= 380:  # un 10-K publie aussi des trimestres
                            continue
                    vals.setdefault(x["end"], set()).add(float(x["val"]))
                    # Un exercice repris en comparatif l'année suivante : la valeur retraitée l'emporte.
                    if x["end"] not in latest or x.get("filed", "") >= latest[x["end"]][0]:
                        latest[x["end"]] = (x.get("filed", ""), float(x["val"]))
                if latest:
                    series.setdefault(key, {})[c] = {d: v for d, (_, v) in sorted(latest.items())}
        if vals:
            postes[key] = {d: sorted(v) for d, v in sorted(vals.items())}
    return {"nom": facts.get("entityName"), "devise": devise, "postes": postes, "series": series, "format": FORMAT}


def path_of(ticker: str):
    return SEC_DIR / f"{ticker}.json"


def load(ticker: str) -> dict | None:
    """Comptes SEC en cache ; None si absents ou illisibles (ils seront retéléchargés)."""
    return lire_json(path_of(ticker))


def comptes_officiels(ticker: str) -> dict | None:
    """Comptes déposés qui prolongent l'historique Yahoo : SEC (États-Unis) ou rapports ESEF (Europe)."""
    return load(ticker) or esef.load(ticker)


def update(tickers: list[str], max_age_days: float = 14, progress: Callable[[int, int, str], None] | None = None) -> dict:
    """Télécharge les comptes SEC des valeurs américaines dont le cache a dépassé son délai de renouvellement.

    Ce délai vaut `max_age_days` en moyenne, entre la moitié et une fois et demie selon la valeur (`etalement`) :
    les quelque 500 comptes ne sont pas tous relus le même jour.
    """
    agent = contact()
    if not agent:
        return {"ok": [], "erreurs": {}, "saute": "contact_sec absent de profil/prive.json"}
    cik = ticker_map(agent)
    todo = []
    for t in tickers:
        st = sec_ticker(t)
        if st is None or st not in cik:
            continue
        p = path_of(t)
        delai = max_age_days * (0.5 + etalement(t))
        perime = not p.exists() or (time.time() - p.stat().st_mtime) / 86400 > delai
        if perime or (load(t) or {}).get("format") != FORMAT:
            todo.append(t)
    result: dict = {"ok": [], "erreurs": {}}
    SEC_DIR.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(todo, 1):
        try:
            data = extract(_get(FACTS_URL.format(cik[sec_ticker(t)]), agent))
            data.update(ticker=t, cik=cik[sec_ticker(t)], fetched=datetime.now().isoformat(timespec="seconds"))
            ecrire_json(path_of(t), data)
            result["ok"].append(t)
        except Exception as exc:
            result["erreurs"][t] = str(exc)[:200]
        if progress:
            progress(i, len(todo), t)
        time.sleep(PAUSE)
    return result


def _match(sec_postes: dict[str, list[float]], date: str, days: int = 10) -> list[float]:
    d = pd.Timestamp(date)
    return [v for k, vals in sec_postes.items() if abs((pd.Timestamp(k) - d).days) <= days for v in vals]


def exercice_commun(fund: dict | None, sec: dict | None) -> str | None:
    """Dernier exercice annuel présent chez Yahoo et à la SEC (à défaut, le dernier de Yahoo)."""
    if not fund or not sec:
        return None
    rev = fund.get("income", {}).get("Total Revenue") or fund.get("income", {}).get("Net Income") or {}
    if not rev:
        return None
    sec_rev = {**sec.get("postes", {}).get("revenue", {}), **sec.get("postes", {}).get("net_income", {})}
    return next((d for d in sorted(rev, reverse=True) if _match(sec_rev, d)), max(rev))


def recoupement(fund: dict | None, sec: dict | None, sans_ca: bool = False) -> dict:
    """Compare Yahoo et la SEC sur leur dernier exercice annuel commun.

    Renvoie le nombre de postes comparés, l'écart le plus fort (en valeur relative), le détail des écarts
    au-delà de la tolérance et un indicateur « Yahoo en retard » quand la SEC a un exercice plus récent.
    `sans_ca` retire le chiffre d'affaires du verdict : banques, assureurs et foncières n'ont pas de poste
    XBRL normalisé pour leurs revenus, et Yahoo les recompose à sa façon.
    """
    out = {"sec_postes": 0, "sec_ecart_max": math.nan, "sec_ecarts": "", "sec_retard": False, "verif_sec": None}
    if not fund or not sec or not sec.get("postes"):
        return out
    date = exercice_commun(fund, sec)
    if date is None:
        return out
    rev = fund.get("income", {}).get("Total Revenue") or fund.get("income", {}).get("Net Income")
    last_sec = max((max(v) for k, v in sec["postes"].items() if k in ("revenue", "net_income")), default=None)
    out["sec_retard"] = bool(last_sec and (pd.Timestamp(last_sec) - pd.Timestamp(max(rev))).days > 30)
    fin_cur = fund.get("info", {}).get("financialCurrency") or "USD"
    if sec.get("devise") and sec["devise"] != fin_cur:
        out["verif_sec"] = "Non comparable"
        return out
    ecarts, notes = {}, []
    for key in RECOUPES:
        y, s = postes.valeurs(fund, key, date), _match(sec["postes"].get(key, {}), date)
        if not y or not s:
            continue
        # Signe ignoré : Yahoo compte les investissements en négatif, la SEC en positif.
        best = min(((abs(a) - abs(b)) / abs(b) for a in y for b in s if b), key=abs, default=math.nan)
        if math.isfinite(best):
            ecarts[key] = best
    controles = {k: v for k, v in ecarts.items() if k in CONTROLES and not (sans_ca and k == "revenue")}
    out["sec_postes"] = len(controles)
    if not controles:
        out["verif_sec"] = "Non comparable"
        return out
    out["sec_ecart_max"] = max(abs(v) for v in controles.values())
    for k, v in ecarts.items():
        if abs(v) > TOLERANCE and k in controles:
            notes.append(f"{LIBELLES[k]} {v:+.0%}".replace("%", " %"))
    out["sec_ecarts"] = ", ".join(notes)
    out["verif_sec"] = ("Écart" if out["sec_ecart_max"] > TOLERANCE
                        else "Confirmé" if len(controles) >= 3 else "Non comparable")
    return out


def detail(fund: dict | None, sec: dict | None) -> pd.DataFrame:
    """Tableau Yahoo / SEC poste par poste pour la fiche valeur (dernier exercice commun, dans `attrs`)."""
    date = exercice_commun(fund, sec)
    if date is None:
        return pd.DataFrame()
    rows = []
    for key in RECOUPES:
        y, s = postes.valeurs(fund, key, date), _match(sec["postes"].get(key, {}), date)
        if not y and not s:
            continue
        pairs = [(a, b) for a in y for b in s if b]
        a, b = min(pairs, key=lambda p: abs(abs(p[0]) - abs(p[1])) / abs(p[1])) if pairs else (
            y[0] if y else math.nan, s[-1] if s else math.nan)
        rows.append({"poste": LIBELLES[key], "yahoo": abs(a), "sec": abs(b),
                     "ecart": (abs(a) - abs(b)) / abs(b) if pairs else math.nan})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("poste")
    df.attrs["exercice"] = date
    return df
