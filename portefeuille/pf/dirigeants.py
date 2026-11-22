"""Achats et ventes d'actions par les dirigeants des sociétés américaines (formulaires 4 déposés à la SEC).

Un dirigeant, un administrateur ou un actionnaire de plus de 10 % doit déclarer chaque transaction sur les
actions de sa société sous deux jours ouvrés. Seules comptent ici les opérations en bourse :
- code P : achat avec son propre argent, le signal le plus parlant (on vend pour mille raisons, on n'achète
  que pour une) ;
- code S : vente ; souvent programmée à l'avance (plan 10b5-1), pour payer des impôts ou diversifier.
Les attributions gratuites, levées d'options et retenues fiscales (codes A, M, F…) sont ignorées.

Source : liste des dépôts de la société (data.sec.gov/submissions), puis chaque formulaire XML. Un formulaire
ne change plus une fois déposé : il est gardé en cache par numéro de dépôt, et seuls les nouveaux sont lus.
"""
from __future__ import annotations

import math
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import pandas as pd

from . import sec
from .config import SEC_DIR, ecrire_json, lire_json

CACHE = SEC_DIR / "dirigeants"
CODES = {"P": "Achat", "S": "Vente"}
JOURS = 365
FRAICHEUR = 1  # jours avant de relire la liste des dépôts
MAX_FORMULAIRES = 250  # garde-fou pour les sociétés aux déclarations très nombreuses
FORMAT = 1
LECTEURS = 4  # formulaires lus en parallèle ; avec la pause de chacun, moins de 8 requêtes par seconde (limite SEC : 10)
PAUSE_LECTEUR = 0.5
GROUPES_MIN = 3  # dirigeants distincts achetant en bourse sur 12 mois : « achats groupés »


def _nombre(texte: str | None) -> float:
    try:
        return float(texte)
    except (TypeError, ValueError):
        return math.nan


def _vrai(texte: str | None) -> bool:
    return (texte or "").strip().lower() in ("1", "true")


def fonction(relation: ET.Element | None) -> str:
    """Qualité du déclarant : son titre s'il est dirigeant, sinon administrateur ou actionnaire de plus de 10 %."""
    if relation is None:
        return ""
    titres = []
    if _vrai(relation.findtext("isOfficer")):
        titres.append((relation.findtext("officerTitle") or "Dirigeant").strip())
    if _vrai(relation.findtext("isDirector")):
        titres.append("Administrateur")
    if _vrai(relation.findtext("isTenPercentOwner")):
        titres.append("Actionnaire > 10 %")
    if not titres and _vrai(relation.findtext("isOther")):
        titres.append((relation.findtext("otherText") or "Autre").strip())
    return ", ".join(titres)


def analyser(xml: str) -> list[dict]:
    """Transactions en bourse (achats P, ventes S) d'un formulaire 4."""
    racine = ET.fromstring(xml.strip())
    proprietaire = racine.find("reportingOwner")
    nom = (proprietaire.findtext("reportingOwnerId/rptOwnerName") or "").strip() if proprietaire is not None else ""
    qualite = fonction(proprietaire.find("reportingOwnerRelationship") if proprietaire is not None else None)
    plan = _vrai(racine.findtext("aff10b5One"))
    lignes = []
    for tr in racine.iter("nonDerivativeTransaction"):
        code = (tr.findtext("transactionCoding/transactionCode") or "").strip()
        if code not in CODES:
            continue
        actions = _nombre(tr.findtext("transactionAmounts/transactionShares/value"))
        prix = _nombre(tr.findtext("transactionAmounts/transactionPricePerShare/value"))
        lignes.append({
            "date": (tr.findtext("transactionDate/value") or "")[:10],
            "nom": nom.title(), "fonction": qualite, "code": code, "actions": actions, "prix": prix,
            "montant": actions * prix if math.isfinite(actions) and math.isfinite(prix) else math.nan,
            "detenues_apres": _nombre(tr.findtext("postTransactionAmounts/sharesOwnedFollowingTransaction/value")),
            "indirect": (tr.findtext("ownershipNature/directOrIndirectOwnership/value") or "").strip() == "I",
            "plan_10b5_1": plan,
        })
    return lignes


def path_of(ticker: str):
    return CACHE / f"{ticker}.json"


def en_cache(ticker: str, jours: int = JOURS) -> pd.DataFrame | None:
    """Transactions déjà lues (sans accès réseau) ; None si la valeur n'a jamais été lue."""
    d = lire_json(path_of(ticker))
    if not d or d.get("format") != FORMAT:
        return None
    return _tableau(d, jours)


def _tableau(d: dict, jours: int) -> pd.DataFrame:
    debut = (pd.Timestamp.today().normalize() - pd.Timedelta(days=jours)).date().isoformat()
    lignes = [{**x, "depot": numero} for numero, f in d.get("formulaires", {}).items() if f["date_depot"] >= debut
              for x in f["transactions"]]
    df = pd.DataFrame(lignes, columns=["date", "nom", "fonction", "code", "actions", "prix", "montant",
                                       "detenues_apres", "indirect", "plan_10b5_1", "depot"])
    df.attrs["lu_le"] = d.get("liste_le")
    return df.sort_values("date", ascending=False, kind="stable").reset_index(drop=True)


def a_jour(ticker: str) -> bool:
    d = lire_json(path_of(ticker))
    return bool(d and d.get("format") == FORMAT and d.get("liste_le") == date.today().isoformat())


def transactions(ticker: str, jours: int = JOURS, progress: Callable[[int, int], None] | None = None) -> pd.DataFrame | None:
    """Achats et ventes en bourse des dirigeants sur `jours` jours ; None hors des États-Unis ou sans contact SEC.

    Lit la liste des dépôts (une fois par jour) puis les seuls formulaires 4 pas encore en cache.
    """
    st_ticker = sec.sec_ticker(ticker)
    agent = sec.contact()
    if st_ticker is None or not agent:
        return None
    d = lire_json(path_of(ticker)) or {}
    if d.get("format") != FORMAT:
        d = {"format": FORMAT, "formulaires": {}}
    if d.get("liste_le") == date.today().isoformat():
        return _tableau(d, jours)
    cik = sec.ticker_map(agent).get(st_ticker)
    if not cik:
        return None
    try:
        recents = sec._get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", agent)["filings"]["recent"]
    except Exception:  # SEC injoignable : ce qui est déjà en cache
        return _tableau(d, jours) if d.get("formulaires") else None
    debut = (pd.Timestamp.today().normalize() - pd.Timedelta(days=jours)).date().isoformat()
    a_lire = [(recents["accessionNumber"][i], recents["filingDate"][i], recents["primaryDocument"][i])
              for i, forme in enumerate(recents["form"])
              if forme == "4" and recents["filingDate"][i] >= debut and recents["accessionNumber"][i] not in d["formulaires"]]
    a_lire = a_lire[:MAX_FORMULAIRES]

    def lire(item: tuple[str, str, str]) -> tuple[str, str, list[dict] | None]:
        numero, depot, document = item
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{numero.replace('-', '')}/{document.split('/')[-1]}"
        try:
            return numero, depot, analyser(sec._brut(url, agent).decode("utf-8", errors="ignore"))
        except Exception:
            return numero, depot, None  # formulaire illisible : il sera retenté au prochain passage
        finally:
            time.sleep(PAUSE_LECTEUR)

    with ThreadPoolExecutor(LECTEURS) as lecteurs:
        for k, (numero, depot, lignes) in enumerate(lecteurs.map(lire, a_lire), 1):
            if lignes is not None:
                d["formulaires"][numero] = {"date_depot": depot, "transactions": lignes}
            if progress:
                progress(k, len(a_lire))
    # On oublie ce qui a plus de deux ans.
    limite = (pd.Timestamp.today() - pd.Timedelta(days=730)).date().isoformat()
    d["formulaires"] = {n: f for n, f in d["formulaires"].items() if f["date_depot"] >= limite}
    d.update(ticker=ticker, liste_le=date.today().isoformat(), lu=datetime.now().isoformat(timespec="seconds"))
    CACHE.mkdir(parents=True, exist_ok=True)
    ecrire_json(path_of(ticker), d)
    return _tableau(d, jours)


def synthese(df: pd.DataFrame | None) -> dict:
    """Chiffres clés : achats (nombre, acheteurs distincts, montant), ventes (montant, part programmée), signal."""
    if df is None or df.empty:
        return {"achats": 0, "acheteurs": 0, "montant_achats": 0.0, "ventes": 0, "vendeurs": 0, "montant_ventes": 0.0,
                "part_ventes_programmees": math.nan, "signal": "Aucune transaction en bourse"}
    a, v = df[df["code"] == "P"], df[df["code"] == "S"]
    acheteurs = a["nom"].nunique()
    montant_v = float(v["montant"].sum())
    signal = ("Achats groupés" if acheteurs >= GROUPES_MIN else "Achats de deux dirigeants" if acheteurs == 2
              else "Achat d'un dirigeant" if acheteurs == 1 else "Ventes seulement" if len(v) else "Aucune transaction en bourse")
    return {"achats": len(a), "acheteurs": acheteurs, "montant_achats": float(a["montant"].sum()), "ventes": len(v),
            "vendeurs": v["nom"].nunique(), "montant_ventes": montant_v,
            "part_ventes_programmees": float(v.loc[v["plan_10b5_1"].astype(bool), "montant"].sum() / montant_v)
            if montant_v > 0 else math.nan, "signal": signal}
