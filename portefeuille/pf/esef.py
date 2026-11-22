"""Comptes officiels des sociétés européennes : rapports annuels au format ESEF, pour allonger l'historique Yahoo.

Depuis l'exercice 2020, les sociétés cotées dans l'Union européenne (et au Royaume-Uni, sous un régime
proche) publient leur rapport annuel avec des étiquettes XBRL. La base publique filings.xbrl.org les
rassemble et les convertit en JSON. Chaque rapport donne l'exercice et son comparatif : avec quatre ou cinq
rapports, on remonte jusqu'à 2019 ou 2020, là où Yahoo s'arrête à quatre exercices. La Suisse n'est pas
couverte.

La base n'indique pas les tickers : la société est cherchée par son nom, puis retenue seulement si son
chiffre d'affaires ou son résultat d'un exercice commun reproduit Yahoo à 3 % près. Ensuite, comme pour la
SEC, un poste ne prolonge l'historique que s'il concorde avec Yahoo sur deux exercices (postes.prolonger).

Le résultat a la forme des comptes SEC (`series` : {grandeur: {poste IFRS: {date de clôture: valeur}}}),
ce qui permet de le passer tel quel à postes.historique.
"""
from __future__ import annotations

import difflib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date, datetime

import pandas as pd

from .config import CACHE_DIR, ecrire_json, etalement, lire_json

ESEF_DIR = CACHE_DIR / "esef"
BASE = "https://filings.xbrl.org"
AGENT = "portefeuille-perso/1.0 (outil personnel de recherche)"
PAUSE = 1.0  # la base limite le débit : une requête par seconde
FORMAT = 3  # 3 : rapports annuels seuls, investissements corporels + incorporels, FCF candidat
AGE_MAX = 30  # jours avant de regarder si un nouveau rapport est paru
AGE_ECHEC = 90  # jours avant de rechercher à nouveau une société introuvable
TOLERANCE = 0.03

# Postes IFRS (taxonomie ifrs-full) pour chaque grandeur, par ordre de préférence.
CONCEPTS = {
    "revenue": ["Revenue", "RevenueFromContractsWithCustomers"],
    "net_income": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
    "ocf": ["CashFlowsFromUsedInOperatingActivities"],
    "equity": ["EquityAttributableToOwnersOfParent"],
    "assets": ["Assets"],
    "op_income": ["ProfitLossFromOperatingActivities"],
    "current_liabilities": ["CurrentLiabilities"],
    "shares": ["AdjustedWeightedAverageShares", "WeightedAverageShares"],
    "sbc": ["AdjustmentsForSharebasedPayments", "ExpenseFromSharebasedPaymentTransactionsWithEmployees"],
    "gross_profit": ["GrossProfit"],
    "dividends": ["DividendsPaidClassifiedAsFinancingActivities", "DividendsPaid"],
    "cash": ["CashAndCashEquivalents"],
}
BILAN = {"equity", "assets", "current_liabilities", "cash"}
# Investissements : postes IFRS ou propres à la société (« LVM:OperatingInvestments… »), corporels,
# incorporels ou les deux. Chacun, et chaque somme corporels + incorporels (le chiffre de Yahoo, souvent), est
# un candidat que le raccord avec Yahoo départage. Les postes nets de cessions (« …Proceeds… ») sont écartés.
CAPEX = re.compile(r"^(Purchases?|Payments?|Acquisitions?|Capital|OperatingInvestment|Investments?In).*"
                   r"(PropertyPlant|Tangible|FixedAsset|Intangible|Expenditure|OperatingInvestment)")
CORPOREL = re.compile(r"PropertyPlant|Tangible|FixedAsset")  # « Tangible » avec sa majuscule : pas « Intangible »
DIMENSIONS_DE_BASE = {"concept", "entity", "period", "unit", "language"}

# Mots des noms de société qui ne permettent pas de la retrouver (formes juridiques, mots génériques).
MOTS_VIDES = {
    "se", "sa", "ag", "nv", "plc", "spa", "asa", "ab", "publ", "oyj", "as", "kgaa", "co", "cie", "and", "et", "the",
    "group", "groupe", "gruppe", "holding", "holdings", "company", "compagnie", "societe", "europeenne", "european",
    "aktiengesellschaft", "ltd", "limited", "inc", "corporation", "corp", "sca", "bv", "sab", "de", "cv", "des", "du",
    "la", "le", "les", "of", "und", "ord", "class", "series", "akt", "aktiebolag", "aktieselskab", "oy", "nyrt",
    "ad", "s", "a", "p", "n", "v", "international", "industries", "sgps", "sad", "pjsc",
}


def _get(chemin: str, pause: float = PAUSE, **params) -> dict:
    """GET JSON, au rythme demandé par la base (nouvel essai après un refus « trop de requêtes »)."""
    url = chemin if chemin.startswith("http") else BASE + chemin
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
    for essai in range(6):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                donnees = json.loads(resp.read())
            time.sleep(pause)
            return donnees
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or essai == 5:
                raise
            attente = exc.headers.get("Retry-After")
            time.sleep(float(attente) if attente and attente.isdigit() else 15 * (essai + 1))
    raise RuntimeError("inaccessible")


def path_of(ticker: str):
    return ESEF_DIR / f"{ticker}.json"


def load(ticker: str) -> dict | None:
    """Comptes ESEF en cache (sans `series` si la société n'a pas été trouvée)."""
    d = lire_json(path_of(ticker)) if "." in ticker else None
    return d if d and d.get("series") else None


# --------------------------------------------------------------------------- lecture d'un rapport

def _date_fin(texte: str) -> str:
    """Fin d'une période xBRL-JSON : « 2022-01-01T00:00:00 » désigne la fin de la journée du 31/12/2021."""
    t = pd.Timestamp(texte)
    if "T" in texte and t == t.normalize():
        t -= pd.Timedelta(days=1)
    return t.date().isoformat()


def extraire(rapport: dict, devise: str | None = None) -> tuple[dict, str | None]:
    """Rapport xBRL-JSON -> ({grandeur: {poste: {date de clôture: valeur}}}, devise des comptes).

    Seuls les faits sans dimension (les totaux du groupe) sont gardés, en montants annuels (340 à 380 jours)
    pour les flux, à une date pour le bilan, dans une seule devise (celle de Yahoo si elle est fournie).
    """
    voulus = {f"ifrs-full:{c}": (cle, c) for cle, liste in CONCEPTS.items() for c in liste}
    faits = []
    for f in (rapport.get("facts") or {}).values():
        dims = f.get("dimensions") or {}
        concept = dims.get("concept") or ""
        if concept not in voulus:
            local = concept.split(":")[-1]
            if not CAPEX.search(local) or "Proceeds" in local or "Sale" in local:
                continue
            incorporel = "Intangible" in local and not CORPOREL.search(local)
            voulus[concept] = ("capex_incorporels" if incorporel else "capex", concept)
        if set(dims) - DIMENSIONS_DE_BASE or "period" not in dims:
            continue
        try:
            valeur = float(f.get("value"))
        except (TypeError, ValueError):
            continue
        faits.append((voulus[dims["concept"]], dims["period"], str(dims.get("unit", "")), valeur))
    if devise is None:  # devise la plus fréquente parmi les montants
        unites = [u.split(":")[-1] for _, _, u, _ in faits if u.startswith("iso4217:")]
        devise = max(set(unites), key=unites.count) if unites else None
    series: dict = {}
    for (cle, concept), periode, unite, valeur in faits:
        if cle == "shares":
            if "shares" not in unite:
                continue
        elif unite != f"iso4217:{devise}":
            continue
        if "/" in periode:
            debut, fin = periode.split("/")
            if cle in BILAN or not 340 <= (pd.Timestamp(_date_fin(fin)) - pd.Timestamp(debut)).days + 1 <= 380:
                continue
        elif cle not in BILAN:
            continue
        else:
            fin = periode
        series.setdefault(cle, {}).setdefault(concept, {})[_date_fin(fin)] = valeur
    # Investissements corporels + incorporels, que Yahoo additionne souvent.
    incorporels = series.pop("capex_incorporels", {})
    for nom_c, c in list((series.get("capex") or {}).items()):
        if CORPOREL.search(nom_c) and "Intangible" not in nom_c:
            for nom_i, i in incorporels.items():
                somme = {d: abs(c[d]) + abs(i[d]) for d in c if d in i}
                if somme:
                    series["capex"][f"{nom_c}+{nom_i}"] = somme
    # Flux de trésorerie disponible, candidat lui aussi au raccord avec celui de Yahoo.
    ocf = (series.get("ocf") or {}).get("CashFlowsFromUsedInOperatingActivities") or {}
    for nom, cap in (series.get("capex") or {}).items():
        fcf = {d: ocf[d] - abs(cap[d]) for d in ocf if d in cap}
        if fcf:
            series.setdefault("fcf", {})[f"ocf-{nom}"] = fcf
    return series, devise


def _fusionner(series: dict, nouvelles: dict) -> None:
    """Ajoute les valeurs d'un rapport plus récent : un comparatif retraité remplace la valeur d'origine."""
    for cle, postes in nouvelles.items():
        for concept, valeurs in postes.items():
            series.setdefault(cle, {}).setdefault(concept, {}).update(valeurs)


# --------------------------------------------------------------------------- recherche de la société

def _ascii(texte: str) -> str:
    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()


def mots_du_nom(nom: str) -> list[str]:
    """« LVMH Moët Hennessy - Louis Vuitton, Société Européenne » -> ['lvmh', 'moet', 'hennessy', 'louis', 'vuitton']."""
    mots = re.findall(r"[a-z0-9]+", _ascii(nom).replace("&", " "))
    utiles = [m for m in mots if m not in MOTS_VIDES and len(m) >= 2]
    return utiles or mots[:1]


def _motifs(nom: str) -> list[str]:
    mots = mots_du_nom(nom)
    if not mots:
        return []
    motifs = []
    if len(mots) >= 2:
        motifs.append(f"%{mots[0]}%{mots[1]}%")
    motifs.append(f"%{mots[0]}%")
    # Accents de la base (« SOCIÉTÉ ») : chaque voyelle devient un joker d'un caractère.
    joker = re.sub(r"[aeiouyc]", "_", mots[0])
    if joker != mots[0] and len(mots[0]) >= 4:
        motifs.append(f"%{joker}%")
    return motifs


def candidats(nom: str, maximum: int = 4) -> list[tuple[str, str]]:
    """(LEI, nom) des sociétés de la base dont le nom ressemble à `nom`, les plus proches d'abord."""
    vus: dict[str, str] = {}
    complet = re.findall(r"[a-z0-9]+", _ascii(nom))
    for motif in ([f"%{'%'.join(complet)}%"] if len(complet) >= 2 else []) + _motifs(nom):
        filtre = json.dumps([{"name": "name", "op": "ilike", "val": motif}])
        for e in _get("/api/entities", filter=filtre, **{"page[size]": 20}).get("data", []):
            vus.setdefault(e["attributes"]["identifier"], e["attributes"]["name"])
        if vus:
            break
    # Le nom le plus ressemblant d'abord : « Novo Nordisk A/S » avant « Novo Nordisk Fonden ».
    reference = " ".join(complet)
    proches = sorted(vus.items(), key=lambda kv: -difflib.SequenceMatcher(
        None, reference, " ".join(re.findall(r"[a-z0-9]+", _ascii(kv[1])))).ratio())
    return proches[:maximum]


def _rapports(lei: str, clotures: set[str] | None = None) -> list[dict]:
    """Un rapport annuel par exercice (le moins d'erreurs de validation), du plus ancien au plus récent.

    `clotures` (« 12-31 »…) écarte les rapports trimestriels ou semestriels que certaines sociétés déposent aussi.
    """
    par_exercice: dict[str, dict] = {}
    for f in _get(f"/api/entities/{lei}/filings", **{"page[size]": 100}).get("data", []):
        a = f["attributes"]
        if not a.get("json_url") or not a.get("period_end"):
            continue
        fin_de_mois = (pd.Timestamp(a["period_end"]) + pd.Timedelta(days=1)).day == 1
        if clotures and fin_de_mois and a["period_end"][5:] not in clotures:
            continue  # rapport trimestriel ou semestriel
        actuel = par_exercice.get(a["period_end"])
        if actuel is None or (a.get("error_count") or 0) < (actuel.get("error_count") or 0):
            par_exercice[a["period_end"]] = a
    return [par_exercice[k] for k in sorted(par_exercice)]


def _yahoo(fund: dict, cle: str) -> list[tuple[pd.Timestamp, float]]:
    """Toutes les valeurs annuelles Yahoo d'une grandeur, sous chacune de ses étiquettes."""
    from . import postes  # import local : postes n'a pas besoin de ce module

    section, libelles = postes.POSTES[cle]
    lignes = fund.get(section) or {}
    return [(pd.Timestamp(d), float(v)) for lab in libelles for d, v in (lignes.get(lab) or {}).items()
            if v is not None and v == v]


def _concorde(series: dict, fund: dict) -> bool:
    """Vrai si le chiffre d'affaires, le résultat net ou le total du bilan d'un exercice reproduit Yahoo à 3 % près.

    Toutes les étiquettes Yahoo comptent : pour une banque, le « résultat net » retenu d'abord est diminué
    des coupons des dettes hybrides, pas celui du rapport.
    """
    for cle in ("revenue", "net_income", "assets"):
        yahoo = _yahoo(fund, cle)
        for valeurs in (series.get(cle) or {}).values():
            for d, v in valeurs.items():
                if v and any(abs((dy - pd.Timestamp(d)).days) <= 10 and abs(vy - v) <= TOLERANCE * abs(v)
                             for dy, vy in yahoo):
                    return True
    return False


def _clotures(fund: dict) -> set[str]:
    """Jours de clôture des exercices annuels Yahoo (« 12-31 »), à quelques jours près (exercices de 52 semaines)."""
    jours = set()
    for d, _ in _yahoo(fund, "revenue") + _yahoo(fund, "net_income"):
        for decalage in range(-7, 8):
            jours.add((d + pd.Timedelta(days=decalage)).strftime("%m-%d"))
    return jours


# --------------------------------------------------------------------------- mise à jour

PAUSE_FICHIER = 0.3  # les rapports sont des fichiers statiques, moins limités que l'API


def charger(ticker: str, fund: dict, cache: dict | None = None) -> dict:
    """Cherche la société (si besoin), lit ses nouveaux rapports et renvoie les comptes à mettre en cache.

    Tous les rapports sont lus : Yahoo reprend les comparatifs retraités des plus récents (Unilever après la
    scission de ses glaces), indispensables au raccord.
    """
    info = fund.get("info", {})
    devise = info.get("financialCurrency")
    cache = dict(cache or {}) if (cache or {}).get("format") == FORMAT else {}
    lei = cache.get("lei")
    lus: dict[str, dict] = {}  # rapports lus pendant ce passage
    if not lei:
        nom = info.get("longName") or info.get("shortName") or ""
        for lei_candidat, nom_candidat in candidats(nom) if nom else []:
            liste = _rapports(lei_candidat, _clotures(fund))
            if not liste:
                continue
            series, dev = extraire(_get(liste[-1]["json_url"], PAUSE_FICHIER), devise)
            if _concorde(series, fund):
                lei, rapports = lei_candidat, liste
                lus[liste[-1]["fxo_id"]] = series
                cache.update(lei=lei, nom=nom_candidat, devise=dev, series={}, rapports=[])
                break
        if not lei:
            return {"ticker": ticker, "lei": None, "essai": date.today().isoformat(), "format": FORMAT}
    else:
        rapports = _rapports(lei, _clotures(fund))
    deja = set(cache.get("rapports") or [])
    for a in rapports:
        if a["fxo_id"] not in deja and a["fxo_id"] not in lus:
            try:
                lus[a["fxo_id"]] = extraire(_get(a["json_url"], PAUSE_FICHIER), devise or cache.get("devise"))[0]
            except Exception:
                continue  # rapport illisible : on le retentera au prochain passage
    # Du plus ancien au plus récent : un comparatif retraité remplace la valeur d'origine.
    series = cache.get("series") or {}
    for a in rapports:
        if a["fxo_id"] in lus:
            _fusionner(series, lus[a["fxo_id"]])
            deja.add(a["fxo_id"])
    # Bilan : seulement aux dates de clôture d'un exercice (pas d'arrêté intermédiaire).
    clotures = {d for cle, postes_ in series.items() if cle not in BILAN for v in postes_.values() for d in v}
    for cle in BILAN & set(series):
        for concept in series[cle]:
            series[cle][concept] = {d: v for d, v in series[cle][concept].items() if d in clotures}
    cache.update(ticker=ticker, series=series, rapports=sorted(deja), exercices=[a["period_end"] for a in rapports],
                 fetched=datetime.now().isoformat(timespec="seconds"), format=FORMAT)
    return cache


def a_rafraichir(ticker: str) -> bool:
    d = lire_json(path_of(ticker))
    if not d or d.get("format") != FORMAT:
        return True
    facteur = 0.5 + etalement(ticker)  # délais répartis : pas toutes les sociétés le même jour
    if d.get("lei") is None:
        essai = pd.Timestamp(d.get("essai") or "2000-01-01")
        return (pd.Timestamp.today() - essai).days > AGE_ECHEC * facteur
    return (time.time() - path_of(ticker).stat().st_mtime) / 86400 > AGE_MAX * facteur


# Places couvertes : Union européenne, Norvège et Royaume-Uni (pas la Suisse).
PLACES = {"L", "PA", "DE", "ST", "MI", "AS", "MC", "CO", "OL", "HE", "WA", "BR", "AT", "VI", "IR", "LS", "F", "IC"}


def couvert(ticker: str) -> bool:
    return "." in ticker and ticker.rsplit(".", 1)[1] in PLACES


def update(tickers: list[str], charger_fund: Callable[[str], dict | None],
           progress: Callable[[int, int, str], None] | None = None, maximum: int | None = None) -> dict:
    """Comptes ESEF des valeurs européennes dont le cache est absent ou ancien (un mois ; trois si introuvable).

    `maximum` borne le nombre de sociétés traitées (une vingtaine de secondes chacune la première fois, au
    rythme d'une requête par seconde) : les suivantes attendent la prochaine mise à jour.
    """
    todo = [t for t in tickers if couvert(t) and a_rafraichir(t)]
    reste = max(0, len(todo) - maximum) if maximum is not None else 0
    todo = todo[:maximum] if maximum is not None else todo
    result: dict = {"ok": [], "introuvables": [], "erreurs": {}, "reste": reste}
    ESEF_DIR.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(todo, 1):
        fund = charger_fund(t)
        if fund:
            try:
                d = charger(t, fund, lire_json(path_of(t)))
                ecrire_json(path_of(t), d)
                (result["ok"] if d.get("lei") else result["introuvables"]).append(t)
            except Exception as exc:  # base injoignable : on garde l'ancien cache
                result["erreurs"][t] = str(exc)[:200]
        if progress:
            progress(i, len(todo), t)
    return result
