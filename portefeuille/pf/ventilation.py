"""Ventilation du chiffre d'affaires d'une société américaine : par activité et par géographie.

Source : le dernier rapport annuel (10-K, ou 20-F) déposé à la SEC, au format XBRL intégré au document. Les
montants y portent des étiquettes (« dimension ») : produit ou service, segment d'activité, zone géographique.
Yahoo n'a pas ces données, et la base « companyfacts » de la SEC ne garde que les montants sans étiquette.

Une répartition n'est retenue que si ses parts somment au chiffre d'affaires total (à 2 % près, le reste éventuel
devenant « Autres ») : on lit les montants tableau par tableau du rapport, on écarte les sous-totaux (une ligne
égale à la somme d'autres lignes du même tableau), puis on garde la répartition la plus détaillée.
Téléchargé à l'ouverture de la fiche (2 à 5 Mo), gardé en cache 30 jours.
"""
from __future__ import annotations

import html
import itertools
import re
import time

from . import sec
from .config import SEC_DIR, ecrire_json, lire_json

CACHE = SEC_DIR / "ventilation"
CONCEPTS = ["us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax", "us-gaap:SalesRevenueNet", "ifrs-full:Revenue"]
# Axes d'activité, du plus parlant au moins parlant.
AXES_ACTIVITE = ["us-gaap:StatementBusinessSegmentsAxis", "srt:ProductOrServiceAxis", "us-gaap:SubsegmentsAxis",
                 "srt:ConsolidationItemsAxis", "us-gaap:ContractWithCustomerSalesChannelAxis"]
AXE_GEO = "srt:StatementGeographicalAxis"
GEO = re.compile(r"^country:|NonUs|Domestic|Foreign|International|UnitedStates|Americas|Europe|EMEA|Asia|Pacific|Region",
                 re.I)
LIBELLES = {"ProductMember": "Produits", "ServiceMember": "Services", "ServiceOtherMember": "Services et autres",
            "SalesChannelDirectlyToConsumerMember": "Vente directe", "SalesChannelThroughIntermediaryMember": "Revendeurs",
            "SubscriptionAndCirculationMember": "Abonnements", "LicenseMember": "Licences",
            "TechnologyServiceMember": "Services technologiques", "FinancialServiceMember": "Services financiers"}
TOLERANCE = 0.02
MAX_PARTS = 12
VERSION = 4  # version de l'analyse : un cache plus ancien est recalculé


def _attributs(balise: str) -> dict[str, str]:
    return dict(re.findall(r'([\w:.-]+)="([^"]*)"', balise))


def _nombre(attr: dict, texte: str) -> float | None:
    t = re.sub(r"<[^>]+>", "", texte).strip()
    if attr.get("format", "").endswith(("fixed-zero", "zerodash")) or t in ("-", "—", "–"):
        return 0.0
    t = t.replace(",", "").replace(" ", "").replace(" ", "")
    try:
        v = float(t)
    except ValueError:
        return None
    v *= 10 ** int(attr.get("scale", "0") or 0)
    return -v if attr.get("sign") == "-" else v


def libelle(membre: str) -> str:
    """« zts:DogsAndCatsMember » -> « Dogs and Cats » ; « aapl:IPhoneMember » -> « IPhone »."""
    local = membre.split(":")[-1]
    if local in LIBELLES:
        return LIBELLES[local]
    nom = re.sub(r"Member$|Segment$", "", local)
    nom = re.sub(r"(?<=[a-z])(and|of|or)(?=[A-Z])", lambda m: f" {m.group(1)} ", nom)  # « Homeand » -> « Home and »
    nom = re.sub(r"(?<=[a-z0-9])(?=[A-Z][a-z])", " ", nom)
    mots = [m.lower() if m.lower() in ("and", "of", "or", "the") else m for m in nom.split()]
    return " ".join(mots) or local


def _regrouper(parts: dict[str, float], total: float) -> dict[str, float]:
    """Parts de moins de 1 % regroupées dans « Autres », plus grosses parts d'abord."""
    tri = [(k, v) for k, v in sorted(parts.items(), key=lambda kv: -kv[1]) if k != "Autres"]
    garde = {k: v for k, v in tri[:7] if v >= 0.01 * total}  # sept parts au plus : un camembert reste lisible
    reste = sum(v for k, v in parts.items() if k not in garde)
    if reste >= 0.005 * total:
        garde["Autres"] = reste
    return garde


def _sans_sous_totaux(parts: dict[str, float]) -> dict[str, float]:
    """Retire les lignes égales à la somme d'autres lignes (sous-totaux), en partant des plus grosses."""
    garde = dict(parts)
    for m, v in sorted(parts.items(), key=lambda kv: -kv[1]):
        autres = [x for k, x in garde.items() if k != m and x < v]
        if v <= 0 or len(autres) < 2 or len(autres) > 16:
            continue
        if any(abs(sum(c) - v) <= 0.005 * v for n in range(2, len(autres) + 1) for c in itertools.combinations(autres, n)):
            del garde[m]
    return garde


def analyser(document: str, fin_exercice: str) -> dict:
    """Ventilations du chiffre d'affaires de l'exercice clos à `fin_exercice` dans un document XBRL intégré."""
    contextes = {}
    for m in re.finditer(r'<(?:xbrli:)?context id="([^"]+)"[^>]*>(.*?)</(?:xbrli:)?context>', document, re.S):
        dims = re.findall(r'dimension="([^"]+)"[^>]*>\s*([^<\s]+)\s*<', m.group(2))
        debut = re.search(r"<(?:xbrli:)?startDate>([^<]+)<", m.group(2))
        fin = re.search(r"<(?:xbrli:)?endDate>([^<]+)<", m.group(2))
        if debut and fin:
            contextes[m.group(1)] = (dims, debut.group(1), fin.group(1))
    tables = [(m.start(), m.end()) for m in re.finditer(r"<table\b.*?</table>", document, re.S | re.I)]

    def table_de(pos: int) -> int:
        return next((i for i, (a, b) in enumerate(tables) if a <= pos < b), -1)

    faits: dict[str, list] = {}
    for m in re.finditer(r"<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>", document, re.S):
        attr = _attributs(m.group(1))
        if attr.get("name") not in CONCEPTS:
            continue
        ctx = contextes.get(attr.get("contextRef", ""))
        if not ctx or ctx[2] != fin_exercice:
            continue
        v = _nombre(attr, m.group(2))
        if v is None:
            continue
        faits.setdefault(attr["name"], []).append((ctx[0], v, table_de(m.start())))

    # Chaque poste de chiffre d'affaires est jugé avec son propre total : une société peut publier son total
    # sous un poste et sa ventilation sous un autre (Alphabet).
    meilleure, rang, geographie = None, None, None
    totaux_tous = [max(v for dims, v, _ in faits.get(c, []) if not dims) for c in CONCEPTS
                   if any(not dims for dims, _, _ in faits.get(c, []))]
    if not totaux_tous:
        return {}
    total_general = max(totaux_tous)
    for concept in CONCEPTS:
        liste = faits.get(concept, [])
        totaux = [v for dims, v, _ in liste if not dims]
        if not liste:
            continue
        # Poste sans total propre (Alphabet ventile sous un poste, totalise sous un autre) : le total général.
        total = max(totaux) if totaux else total_general
        groupes: dict[tuple, dict[str, float]] = {}
        for dims, v, tab in liste:
            if len(dims) == 1:
                groupes.setdefault((dims[0][0], tab), {}).setdefault(dims[0][1], v)
        for (axe, _), parts in groupes.items():
            if axe == AXE_GEO and geographie is None:
                if 0 < parts.get("country:US", 0) < total:
                    geographie = {"États-Unis": parts["country:US"], "International": total - parts["country:US"]}
                elif 0 < parts.get("us-gaap:NonUsMember", 0) < total:
                    geographie = {"États-Unis": total - parts["us-gaap:NonUsMember"], "International": parts["us-gaap:NonUsMember"]}
            if axe not in AXES_ACTIVITE or any(GEO.search(m.split(":")[-1]) for m in parts):
                continue
            parts = _sans_sous_totaux({m: v for m, v in parts.items() if v > 0})
            somme = sum(parts.values())
            if not 2 <= len(parts) <= MAX_PARTS or not (1 - 0.10) * total <= somme <= (1 + TOLERANCE) * total:
                continue
            score = (AXES_ACTIVITE.index(axe), -len(parts), abs(somme - total) / total)
            if rang is None or score < rang:
                rang = score
                meilleure = {libelle(m): v for m, v in parts.items()}
                # Reste non ventilé : écart au total du poste, et au total général si le poste en exclut une partie
                # (Berkshire Hathaway ventile ses ventes, pas ses primes d'assurance).
                if somme < (1 - TOLERANCE) * total_general:
                    meilleure["Autres"] = total_general - somme
                meilleure = _regrouper(meilleure, total_general)
    return {"total": total_general, "activites": meilleure, "geographie": geographie}


def ventilation(ticker: str, max_age_days: float = 30) -> dict | None:
    """Ventilation du dernier rapport annuel (cache de 30 jours). None hors des États-Unis ou sans contact SEC."""
    if "." in ticker:
        return None
    chemin = CACHE / f"{ticker}.json"
    cache = lire_json(chemin)
    if cache and (time.time() - chemin.stat().st_mtime) / 86400 < max_age_days:
        return cache
    agent = sec.contact()
    cik = sec.ticker_map(agent).get(ticker.upper()) if agent else None
    if not cik:
        return cache
    try:
        recents = sec._get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", agent)["filings"]["recent"]
        i = next(k for k, f in enumerate(recents["form"]) if f in ("10-K", "20-F", "40-F"))
        numero = recents["accessionNumber"][i].replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{numero}/{recents['primaryDocument'][i]}"
        if cache and cache.get("url") == url and cache.get("version") == VERSION:  # rapport inchangé : rien à refaire
            ecrire_json(chemin, cache)
            return cache
        document = html.unescape(sec._brut(url, agent).decode("utf-8", errors="ignore"))
        res = {"url": url, "version": VERSION, "formulaire": recents["form"][i], "exercice": recents["reportDate"][i],
               **analyser(document, recents["reportDate"][i])}
    except Exception:  # réseau, rapport sans XBRL intégré : on garde l'ancienne ventilation s'il y en a une
        return cache
    ecrire_json(chemin, res)
    return res
