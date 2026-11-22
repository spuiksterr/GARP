"""Élargissement de l'univers : S&P 500, STOXX Europe 600 et grandes valeurs du Nasdaq.

Sources : composition quotidienne publiée par les ETF iShares qui répliquent les deux indices, et
annuaire officiel des titres cotés au Nasdaq (segment Global Select, capitalisation d'au moins
1 milliard de dollars d'après Yahoo).
L'import ne fait qu'ajouter des lignes à config/univers.csv : une ligne existante n'est jamais
modifiée. Les lignes importées se reconnaissent à leur colonne `profil` vide ; `refine_universe`
les complète ensuite (nom et secteur fins) à partir des fondamentaux Yahoo.
"""
from __future__ import annotations

import io
import re
import time
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd

from .config import CACHE_DIR, UNIVERS_CSV, ecrire_json, lire_json, read_csv_fr, write_csv_fr
from .data import load_fundamentals

_ISHARES = "https://www.ishares.com/ch/individual/en/products/{id}/{slug}/1495092304805.ajax?fileType=csv&fileName={name}_holdings&dataType=fund"
SOURCES = {
    "STOXX Europe 600": _ISHARES.format(id=251931, slug="ishares-stoxx-europe-600-ucits-etf-de-fund", name="EXSA"),
    "S&P 500": _ISHARES.format(id=253743, slug="ishares-sp-500-b-ucits-etf-acc-fund", name="CSPX"),
}

SUFFIXES = {
    "New York Stock Exchange Inc.": "", "NASDAQ": "", "Cboe BZX": "",
    "London Stock Exchange": ".L", "Xetra": ".DE", "Deutsche Boerse Xetra": ".DE",
    "Nyse Euronext - Euronext Paris": ".PA", "SIX Swiss Exchange": ".SW", "Nasdaq Omx Nordic": ".ST",
    "Borsa Italiana": ".MI", "Euronext Amsterdam": ".AS", "Bolsa De Madrid": ".MC",
    "Omx Nordic Exchange Copenhagen A/S": ".CO", "Oslo Bors Asa": ".OL", "Nasdaq Omx Helsinki Ltd.": ".HE",
    "Warsaw Stock Exchange/Equities/Main Market": ".WA", "Nyse Euronext - Euronext Brussels": ".BR",
    "Athens Exchange S.A. Cash Market": ".AT", "Wiener Boerse Ag": ".VI",
    "Irish Stock Exchange - All Market": ".IR", "Nyse Euronext - Euronext Lisbon": ".LS",
}

PAYS = {
    "United States": "États-Unis", "United Kingdom": "Royaume-Uni", "France": "France", "Germany": "Allemagne",
    "Switzerland": "Suisse", "Sweden": "Suède", "Italy": "Italie", "Netherlands": "Pays-Bas", "Spain": "Espagne",
    "Denmark": "Danemark", "Norway": "Norvège", "Finland": "Finlande", "Poland": "Pologne", "Belgium": "Belgique",
    "Greece": "Grèce", "Austria": "Autriche", "Ireland": "Irlande", "Portugal": "Portugal",
    # Sociétés étrangères cotées au Nasdaq.
    "Canada": "Canada", "Israel": "Israël", "China": "Chine", "Hong Kong": "Hong Kong", "Taiwan": "Taïwan",
    "Singapore": "Singapour", "Japan": "Japon", "South Korea": "Corée du Sud", "India": "Inde",
    "Australia": "Australie", "Brazil": "Brésil", "Argentina": "Argentine", "Uruguay": "Uruguay",
    "Mexico": "Mexique", "Luxembourg": "Luxembourg", "Bermuda": "Bermudes", "Cayman Islands": "Îles Caïmans",
    "Jersey": "Jersey", "Guernsey": "Guernesey", "Cyprus": "Chypre",
}
HORS_PEA = {"États-Unis", "Royaume-Uni", "Suisse"}

SECTEURS_GICS = {
    "Information Technology": "Logiciels & IT", "Communication": "Internet & Médias",
    "Consumer Discretionary": "Luxe & Consommation", "Consumer Staples": "Consommation de base",
    "Health Care": "Santé", "Industrials": "Industrie & Électrification", "Financials": "Services financiers",
    "Materials": "Matériaux & Chimie", "Energy": "Infrastructures & Énergie", "Utilities": "Infrastructures & Énergie",
    "Real Estate": "Immobilier",
}
# Secteur Yahoo (valeurs du Nasdaq, que l'annuaire ne classe pas).
SECTEURS_YAHOO = {
    "Technology": "Logiciels & IT", "Communication Services": "Internet & Médias",
    "Consumer Cyclical": "Luxe & Consommation", "Consumer Defensive": "Consommation de base",
    "Healthcare": "Santé", "Industrials": "Industrie & Électrification", "Financial Services": "Services financiers",
    "Basic Materials": "Matériaux & Chimie", "Energy": "Infrastructures & Énergie",
    "Utilities": "Infrastructures & Énergie", "Real Estate": "Immobilier",
}
# Secteur plus fin d'après l'industrie Yahoo (première correspondance retenue).
SECTEURS_INDUSTRIE = [
    (r"Semiconductor", "Semi-conducteurs"), (r"Aerospace", "Aéronautique & Défense"), (r"^Banks", "Banques"),
    (r"Insurance", "Assurance"), (r"Telecom", "Télécoms"), (r"REIT|Real Estate", "Immobilier"),
    (r"Discount Stores|Department Stores|Grocery|Specialty Retail|Home Improvement Retail|Apparel Retail|Internet Retail", "Distribution"),
    (r"Consulting Services|Staffing|Specialty Business Services|Information Technology Services", "Services aux entreprises & Données"),
]

# Tickers iShares qui ne se déduisent pas par la règle générale.
CORRECTIONS = {"-.HE": "UPM.HE"}
# Cotations sans intérêt : seconde classe ou seconde place d'une société déjà présente.
IGNORER = {"GOOG", "FOX", "NWS", "ROP.SW", "HEIO.AS", "STMMI.MI"}


def to_yahoo(ticker: str, exchange: str) -> str | None:
    suffix = SUFFIXES.get(exchange)
    if suffix is None:
        return None
    t = ticker.strip().rstrip(".").replace("/", "-").replace(" ", "-").replace(".", "-")
    if suffix == "" and len(t) > 2 and t[-1] in "AB" and t[:-1] in ("BRK", "BF"):
        t = f"{t[:-1]}-{t[-1]}"
    return CORRECTIONS.get(f"{t}{suffix}", f"{t}{suffix}")


def parse_holdings(text: str) -> pd.DataFrame:
    lines = text.lstrip("﻿").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Ticker,"))
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    df = df[(df["Asset Class"] == "Equity") & df["Ticker"].notna()].copy()
    df["yahoo"] = [to_yahoo(str(t), e) for t, e in zip(df["Ticker"], df["Exchange"])]
    return df[df["yahoo"].notna() & ~df["yahoo"].isin(IGNORER)]


def fetch_holdings(index: str) -> pd.DataFrame:
    req = urllib.request.Request(SOURCES[index], headers={"User-Agent": "Mozilla/5.0", "Cookie": "blkUserType-ch=individual"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return parse_holdings(resp.read().decode("utf-8-sig"))


def _base_name(name: str) -> str:
    """Nom sans la classe d'action, pour ne garder qu'une cotation par société."""
    return re.sub(r"\s+(CLASS\s+\w+|SERIES\s+\w+|PREF.*|NON[- ]VOTING.*|VOTING.*|[AB]|PS PAR AG|PS)$", "", str(name).upper()).strip()


def candidates(holdings: pd.DataFrame, known: set[str]) -> pd.DataFrame:
    """Lignes à ajouter à l'univers : une cotation par société (la plus lourde), hors valeurs connues."""
    h = holdings.sort_values("Weight (%)", ascending=False).assign(base=lambda d: d["Name"].map(_base_name))
    h = h.drop_duplicates(["base", "Location"])
    h = h[~h["yahoo"].isin(known)]
    rows = pd.DataFrame({
        "ticker": h["yahoo"], "nom": h["Name"].str.title(), "pays": h["Location"].map(PAYS).fillna(h["Location"]),
        "secteur": h["Sector"].map(SECTEURS_GICS).fillna("Services financiers"), "profil": "",
    })
    rows.insert(3, "enveloppe", rows["pays"].map(lambda p: "CTO" if p in HORS_PEA else "PEA"))
    return rows.drop_duplicates("ticker")


def extend_universe() -> int:
    """Ajoute à config/univers.csv les valeurs des indices absentes. Renvoie le nombre d'ajouts."""
    u = read_csv_fr(UNIVERS_CSV)
    holdings = pd.concat([fetch_holdings(index) for index in SOURCES])
    new = candidates(holdings, set(u["ticker"]))
    write_csv_fr(pd.concat([u, new[u.columns]], ignore_index=True), UNIVERS_CSV)
    return len(new)


def _clean_name(name: str) -> str:
    name = re.sub(r"[,\s]+(Aktiengesellschaft|Société anonyme|S\.?A\.?|N\.?V\.?|AG|SE|plc|PLC|Inc\.?|Corporation|Corp\.?|"
                  r"Oyj|ASA|AB \(publ\)|AB|A/S|S\.p\.A\.?|SpA|Ltd\.?|Limited|& Co\. KGaA)$", "", name.replace(";", ",").strip())
    return name.rstrip(",. ")


def refine_universe() -> int:
    """Complète nom et secteur des lignes importées d'après Yahoo. Renvoie le nombre de lignes changées."""
    u = read_csv_fr(UNIVERS_CSV)
    u = u[~u["ticker"].isin(IGNORER)].reset_index(drop=True)
    changed = 0
    for i in u.index[u["profil"] == ""]:
        info = (load_fundamentals(u.at[i, "ticker"]) or {}).get("info", {})
        name = _clean_name(info.get("longName") or info.get("shortName") or "")
        industry = info.get("industry") or ""
        sector = next((s for pattern, s in SECTEURS_INDUSTRIE if re.search(pattern, industry)), None)
        if name and name != u.at[i, "nom"]:
            u.at[i, "nom"] = name
            changed += 1
        if sector and sector != u.at[i, "secteur"]:
            u.at[i, "secteur"] = sector
            changed += 1
    write_csv_fr(u, UNIVERS_CSV)
    return changed


# --------------------------------------------------------------------------- Nasdaq
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_CAPI_MIN = 1e9  # en dollars
NASDAQ_REJETS = CACHE_DIR / "nasdaq_rejets.json"  # écartées (taille, type) : réexaminées après 90 jours
NASDAQ_REVUE_JOURS = 90
# Titres qui ne sont pas des actions ordinaires (ni des certificats d'actions ordinaires).
_PAS_UNE_ACTION = re.compile(r"warrant|\bright|\bunits?\b|preferred|\bnotes?\b|debenture|subordinat|%", re.I)
_SPAC = re.compile(r"acquisition corp", re.I)


def parse_nasdaq(text: str) -> pd.DataFrame:
    """Annuaire Nasdaq -> actions du segment Global Select en situation normale, une cotation par société."""
    df = pd.read_csv(io.StringIO(text), sep="|", dtype=str, keep_default_na=False)
    df = df[df["Symbol"].str.fullmatch(r"[A-Z]{1,5}")]  # écarte aussi la ligne de date en fin de fichier
    df = df[(df["Market Category"] == "Q") & (df["Test Issue"] == "N") & (df["Financial Status"] == "N")
            & (df["ETF"] == "N")]
    nom = df["Security Name"]
    df = df[~nom.str.contains(_PAS_UNE_ACTION) & ~nom.str.contains(_SPAC)].copy()
    df["base"] = df["Security Name"].str.split(" - ").str[0].str.strip()
    # Plusieurs classes d'une même société : le ticker le plus court, puis l'ordre alphabétique.
    df = df.assign(_l=df["Symbol"].str.len()).sort_values(["_l", "Symbol"]).drop_duplicates("base")
    return df.rename(columns={"Symbol": "ticker", "base": "nom"})[["ticker", "nom"]].reset_index(drop=True)


def fetch_nasdaq() -> pd.DataFrame:
    req = urllib.request.Request(NASDAQ_URL, headers={"User-Agent": "portefeuille-pf/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return parse_nasdaq(resp.read().decode("utf-8", "replace"))


def _norme(nom: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _clean_name(str(nom)).lower())


# Même racine de ticker et même premier mot du nom, mais sociétés différentes (vérifié).
PAIRES_DISTINCTES = {
    frozenset({"EQT", "EQT.ST"}),  # EQT Corp (gaz, États-Unis) / EQT AB (capital-investissement, Suède)
    frozenset({"PRU", "PRU.L"}),  # Prudential Financial (États-Unis) / Prudential plc (Asie)
    frozenset({"MRK", "MRK.DE"}),  # Merck & Co (États-Unis) / Merck KGaA (Allemagne)
}


def premier_mot(nom: str) -> str:
    mots = [m for m in re.findall(r"[a-z0-9]+", str(nom).lower()) if m != "the"]
    return mots[0] if mots else ""


def meme_societe(ticker: str, nom: str, autre: str, nom_autre: str) -> bool:
    """Deux cotations d'une même société : ASML (Nasdaq) et ASML.AS (Amsterdam), par exemple.

    Même racine de ticker, l'un sans suffixe de place, et même premier mot du nom. La racine seule ne suffit pas
    (DG est Dollar General, DG.PA Vinci) ; les exceptions vérifiées sont dans PAIRES_DISTINCTES.
    """
    if ticker == autre or frozenset({ticker, autre}) in PAIRES_DISTINCTES:
        return False
    if ticker.split(".")[0] != autre.split(".")[0] or ("." in ticker) == ("." in autre):
        return False
    return premier_mot(nom) == premier_mot(nom_autre)


def _sonde(ticker: str) -> dict:
    """Profil Yahoo : type, capitalisation, nom, pays, secteur."""
    import yfinance as yf
    for essai in range(3):
        try:
            info = yf.Ticker(ticker).info or {}
            if info:
                return info
        except Exception:
            pass
        time.sleep(2 * (essai + 1))
    return {}


def ligne_nasdaq(ticker: str, info: dict, cap_min: float = NASDAQ_CAPI_MIN) -> tuple[dict | None, str]:
    """Ligne d'univers pour une valeur du Nasdaq, ou None et le motif du rejet."""
    if not info:
        return None, "pas de données Yahoo"
    if info.get("quoteType") != "EQUITY":
        return None, f"type {info.get('quoteType')}"
    if (info.get("industry") or "") == "Shell Companies":
        return None, "société coquille (SPAC)"
    cap = info.get("marketCap") or 0
    if cap < cap_min:
        return None, f"capitalisation {cap / 1e9:.2f} Md$"
    industrie = info.get("industry") or ""
    secteur = next((s for motif, s in SECTEURS_INDUSTRIE if re.search(motif, industrie)), None) \
        or SECTEURS_YAHOO.get(info.get("sector") or "", "Industrie & Électrification")
    pays = info.get("country") or "United States"
    return {"ticker": ticker, "nom": _clean_name(info.get("longName") or info.get("shortName") or ticker),
            "pays": PAYS.get(pays, pays), "enveloppe": "CTO", "secteur": secteur, "profil": ""}, ""


def extend_nasdaq(cap_min: float = NASDAQ_CAPI_MIN, progress: Callable[[int, int, str], None] | None = None,
                  workers: int = 4) -> dict:
    """Ajoute à l'univers les actions du Nasdaq Global Select d'au moins `cap_min` dollars.

    Une société déjà présente (même ticker, ou même nom pour le certificat d'une société européenne)
    n'est pas reprise. Les rejets sont mémorisés pour ne pas réinterroger Yahoo avant 90 jours.
    """
    u = read_csv_fr(UNIVERS_CSV)
    connus, noms = set(u["ticker"]), {_norme(n) for n in u["nom"]}
    places = {}  # racine -> cotations européennes (ASML -> ASML.AS)
    for t, n in zip(u["ticker"], u["nom"]):
        if "." in t:
            places.setdefault(t.split(".")[0], []).append((t, n))
    rejets = lire_json(NASDAQ_REJETS) or {}
    maintenant = datetime.now()
    recents = {t for t, r in rejets.items()
               if (maintenant - datetime.fromisoformat(r["date"])).days < NASDAQ_REVUE_JOURS}
    cands = fetch_nasdaq()
    cands = cands[~cands["ticker"].isin(connus | IGNORER | recents)]
    lignes, n = [], len(cands)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (t, info) in enumerate(zip(cands["ticker"], pool.map(_sonde, cands["ticker"])), 1):
            ligne, motif = ligne_nasdaq(t, info, cap_min)
            if ligne and (_norme(ligne["nom"]) in noms
                          or any(meme_societe(t, ligne["nom"], a, n) for a, n in places.get(t, []))):
                ligne, motif = None, "société déjà présente sous un autre ticker"
            if ligne:
                lignes.append(ligne)
                noms.add(_norme(ligne["nom"]))
                rejets.pop(t, None)
            elif motif != "pas de données Yahoo":  # échec ponctuel : retenté au prochain passage
                rejets[t] = {"date": maintenant.isoformat(timespec="seconds"), "motif": motif}
            if progress:
                progress(i, n, t)
    ecrire_json(NASDAQ_REJETS, rejets)
    if lignes:
        write_csv_fr(pd.concat([u, pd.DataFrame(lignes)[u.columns]], ignore_index=True), UNIVERS_CSV)
    return {"ajouts": [x["ticker"] for x in lignes], "examinees": n}
