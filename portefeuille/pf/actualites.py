"""Fil d'actualité des valeurs suivies : vos lignes et votre watchlist.

Quatre sources, réunies en un seul fil daté :
- Presse : Google Actualités en français (flux RSS public, pour un usage personnel), recherché sur le nom de la
  société ; seuls les titres qui citent ce nom sont gardés. Titre, journal, date et lien : pas le texte.
- Déclarations officielles : formulaires 8-K déposés à la SEC (sociétés américaines), avec leur objet
  (résultats, changement de dirigeant, acquisition…).
- Résultats à venir : date annoncée de la prochaine publication (Yahoo, quand il répond).
- Signaux de l'outil. Datés, dans le fil : achats de dirigeants, mouvements des grands investisseurs. Sans date,
  « À surveiller » : prix visé atteint, forte variation du cours, sortie des filtres de qualité, résultats à venir.

Les requêtes de presse se règlent dans profil/actualites.csv (ticker ; recherche), par exemple pour Alphabet,
que la presse appelle souvent Google.
"""
from __future__ import annotations

import email.utils
import html
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta

import pandas as pd

from .config import CACHE_DIR, PROFIL_DIR, ecrire_json, lire_json, read_csv_fr

CACHE = CACHE_DIR / "actualites"
REQUETES_CSV = PROFIL_DIR / "actualites.csv"
VU_JSON = CACHE / "vu.json"
AGENT = "Mozilla/5.0 (compatible; portefeuille-perso/1.0)"
FRAICHEUR_H = 6  # heures entre deux lectures d'une même valeur
JOURS = 60  # ancienneté maximale gardée
FORMAT = 1

# Objet des formulaires 8-K (rubriques de la SEC).
RUBRIQUES_8K = {
    "1.01": "Accord important", "1.02": "Fin d'un accord important", "1.03": "Faillite",
    "2.01": "Acquisition ou cession", "2.02": "Résultats publiés", "2.03": "Nouvelle dette",
    "2.05": "Restructuration", "2.06": "Dépréciation d'actifs", "3.01": "Menace de radiation de la cote",
    "3.02": "Émission d'actions", "4.01": "Changement de commissaire aux comptes",
    "4.02": "Comptes antérieurs non fiables", "5.01": "Changement de contrôle",
    "5.02": "Départ ou nomination de dirigeants", "5.03": "Modification des statuts",
    "5.07": "Vote des actionnaires", "7.01": "Communication aux investisseurs", "8.01": "Autre événement",
}
SANS_INTERET = {"9.01"}  # pièces jointes seules


def _get(url: str, agent: str = AGENT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": agent})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def requetes() -> dict[str, str]:
    """Recherches de presse propres à certaines valeurs (profil/actualites.csv)."""
    if not REQUETES_CSV.exists():
        return {}
    df = read_csv_fr(REQUETES_CSV)
    return {r["ticker"]: r["recherche"] for _, r in df.iterrows() if r.get("recherche")}


# --------------------------------------------------------------------------- presse

def termes(recherche: str) -> list[str]:
    """Noms à retrouver dans un titre : les expressions entre guillemets de la recherche (sauf les exclusions
    « -"…" »), sinon le premier mot."""
    entre_guillemets = re.findall(r'(?<!-)"([^"]+)"', recherche)
    return [t.lower() for t in (entre_guillemets or recherche.split()[:1])]


# Pages de cotation (« ADOBE Cours Action ADBE, Cotation Bourse NASDAQ ») : ce ne sont pas des articles.
PAGE_DE_COURS = re.compile(r"cours (de l'|de l’)?action|cotation|\| cours|stock price|share price", re.I)


def analyser_rss(xml: str, mots: list[str]) -> list[dict]:
    """Articles d'un flux RSS Google Actualités dont le titre cite l'un des `mots`."""
    articles = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        champ = lambda t: html.unescape((re.search(f"<{t}[^>]*>(.*?)</{t}>", item, re.S) or [None, ""])[1]).strip()  # noqa: E731, B023 (appelée dans ce tour)
        titre, source = champ("title"), champ("source")
        # Google ajoute « - Journal » à la fin du titre.
        if source and titre.endswith(f" - {source}"):
            titre = titre[: -len(source) - 3]
        if not any(m in titre.lower() for m in mots) or PAGE_DE_COURS.search(titre):
            continue
        try:
            date = email.utils.parsedate_to_datetime(champ("pubDate")).replace(tzinfo=None)
        except (TypeError, ValueError):
            continue
        articles.append({"date": date.isoformat(timespec="minutes"), "type": "Presse", "source": source or "Presse",
                         "titre": titre, "lien": champ("link"), "detail": ""})
    return articles


# Mots ajoutés à la recherche : sans eux, « Ferrari » ramène surtout la Formule 1, et « Jumbo » un club de football.
CONTEXTE = {"fr": "(action OR bourse OR résultats OR actionnaires OR \"chiffre d'affaires\" OR cours OR analystes)",
            "en": "(stock OR shares OR results OR earnings OR revenue OR analysts)"}
EDITIONS = {"fr": "hl=fr&gl=FR&ceid=FR:fr", "en": "hl=en-US&gl=US&ceid=US:en"}


def presse(nom: str, recherche: str | None = None, jours: int = 30) -> list[dict]:
    """Articles récents. Une recherche qui commence par « en: » interroge l'édition anglaise (société peu suivie
    par la presse française)."""
    recherche = recherche or f'"{nom}"'
    langue = "fr"
    if recherche.startswith("en:"):
        langue, recherche = "en", recherche[3:].strip()
    q = urllib.parse.quote(f"{recherche} {CONTEXTE[langue]} when:{jours}d")
    xml = _get(f"https://news.google.com/rss/search?q={q}&{EDITIONS[langue]}").decode("utf-8", errors="ignore")
    return analyser_rss(xml, termes(recherche))


# --------------------------------------------------------------------------- déclarations officielles (SEC)

def declarations_8k(ticker: str, jours: int = JOURS) -> list[dict]:
    from . import sec  # import local : sec n'est utile que pour les valeurs américaines

    agent = sec.contact()
    st_ticker = sec.sec_ticker(ticker)
    if not agent or st_ticker is None:
        return []
    cik = sec.ticker_map(agent).get(st_ticker)
    if not cik:
        return []
    r = sec._get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", agent)["filings"]["recent"]
    debut = (datetime.now() - timedelta(days=jours)).date().isoformat()
    out = []
    for i, forme in enumerate(r["form"]):
        if forme != "8-K" or r["filingDate"][i] < debut:
            continue
        codes = [c.strip() for c in str(r.get("items", [""] * len(r["form"]))[i]).split(",") if c.strip()]
        objets = [RUBRIQUES_8K.get(c, f"rubrique {c}") for c in codes if c not in SANS_INTERET]
        numero = r["accessionNumber"][i].replace("-", "")
        out.append({"date": r["filingDate"][i] + "T00:00", "type": "Déclaration officielle", "source": "SEC (8-K)",
                    "titre": " · ".join(objets) or "Déclaration 8-K",
                    "lien": f"https://www.sec.gov/Archives/edgar/data/{cik}/{numero}/{r['primaryDocument'][i]}",
                    "detail": ""})
    return out


# --------------------------------------------------------------------------- résultats à venir

def prochains_resultats(ticker: str) -> list[dict]:
    """Date annoncée de la prochaine publication de résultats (Yahoo) ; rien si Yahoo ne répond pas."""
    import warnings

    try:
        import yfinance as yf

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cal = yf.Ticker(ticker).calendar or {}
    except Exception:
        return []
    dates = cal.get("Earnings Date") or []
    dates = dates if isinstance(dates, list) else [dates]
    futures = sorted(d for d in dates if hasattr(d, "isoformat") and d >= datetime.now().date())
    if not futures:
        return []
    d = futures[0]
    return [{"date": datetime.now().isoformat(timespec="minutes"), "type": "À surveiller", "source": "Agenda (Yahoo)",
             "titre": f"Résultats attendus le {d:%d/%m/%Y}", "lien": "", "detail": "", "evenement": d.isoformat()}]


# --------------------------------------------------------------------------- mise à jour

def path_of(ticker: str):
    return CACHE / f"{ticker}.json"


def suivis() -> list[str]:
    """Vos lignes (hors fonds) puis votre watchlist."""
    from .config import load_model_portfolio
    from .data import fund_tickers
    from .watchlist import load_watchlist

    fonds = fund_tickers()
    tickers = list(load_model_portfolio().index) + list(load_watchlist().index)
    return [t for t in dict.fromkeys(tickers) if t not in fonds]


def mettre_a_jour(noms: dict[str, str], force: bool = False, progress: Callable[[str], None] | None = None) -> dict:
    """Relit presse, déclarations et agenda des valeurs suivies dont la dernière lecture a plus de 6 heures."""
    CACHE.mkdir(parents=True, exist_ok=True)
    req = requetes()
    res = {"lues": 0, "erreurs": {}}
    for t in suivis():
        ancien = lire_json(path_of(t)) or {}
        lu = ancien.get("lu")
        if not force and lu and datetime.now() - datetime.fromisoformat(lu) < timedelta(hours=FRAICHEUR_H):
            continue
        items: list[dict] = []
        # Recherche de presse employée : si elle a changé (nom, réglage, mots de contexte), les anciens articles,
        # trouvés par une autre recherche, ne sont pas repris.
        recherche = f"{req.get(t) or noms.get(t, t)} | {CONTEXTE}"
        if ancien.get("recherche") != recherche:
            ancien = {**ancien, "items": [x for x in ancien.get("items", []) if x["type"] != "Presse"]}
        # Les fonctions sont appelées dans ce tour de boucle : la capture de `t` est voulue.
        for nom_source, fonction in (("presse", lambda: presse(noms.get(t, t), req.get(t))),  # noqa: B023
                                     ("SEC", lambda: declarations_8k(t)), ("agenda", lambda: prochains_resultats(t))):  # noqa: B023
            try:
                items += fonction()
            except Exception as exc:  # une source injoignable n'empêche pas les autres
                res["erreurs"][f"{t} ({nom_source})"] = str(exc)[:120]
            time.sleep(0.5)
        # On garde les articles déjà lus que la nouvelle lecture ne renvoie plus (dans la limite de JOURS).
        limite = (datetime.now() - timedelta(days=JOURS)).isoformat()
        cles = {(x["titre"], x["date"][:10]) for x in items}
        items += [x for x in ancien.get("items", []) if (x["titre"], x["date"][:10]) not in cles
                  and x["type"] not in ("Agenda", "À surveiller")]
        items = [x for x in items if x["date"] >= limite or x["type"] == "À surveiller"]
        ecrire_json(path_of(t), {"format": FORMAT, "ticker": t, "lu": datetime.now().isoformat(timespec="seconds"),
                                 "recherche": recherche, "items": items})
        res["lues"] += 1
        if progress:
            progress(f"  actualités {t}")
    return res


# --------------------------------------------------------------------------- signaux de l'outil

def signaux(sc: pd.DataFrame) -> list[dict]:
    """Événements tirés des données de l'outil pour les valeurs suivies (aucun accès réseau)."""
    from . import dirigeants
    from . import investisseurs as inv
    from .watchlist import load_watchlist, prix_vises_atteints

    out = []
    maintenant = datetime.now().isoformat(timespec="minutes")
    tickers = suivis()
    for t, a in prix_vises_atteints(sc["cours"], load_watchlist()).iterrows():
        out.append({"ticker": t, "date": maintenant, "type": "À surveiller", "source": "Watchlist",
                    "titre": f"Prix visé atteint : cours {a['cours']:.2f} pour {a['prix_cible']:.2f} visé".replace(".", ","),
                    "lien": "", "detail": str(a.get("objectif") or "")})
    for t in tickers:
        if t not in sc.index:
            continue
        r = sc.loc[t]
        p1 = r.get("perf_1m")
        if pd.notna(p1) and abs(p1) >= 0.15:
            out.append({"ticker": t, "date": maintenant, "type": "À surveiller", "source": "Cours",
                        "titre": f"{'Forte hausse' if p1 > 0 else 'Forte baisse'} : {p1:+.0%} sur un mois".replace("%", " %"),
                        "lien": "", "detail": ""})
        if r.get("statut") == "Exclu":
            out.append({"ticker": t, "date": maintenant, "type": "À surveiller", "source": "Filtres",
                        "titre": "Hors des filtres de qualité", "lien": "", "detail": str(r.get("motifs_exclusion") or "")})
        tx = dirigeants.en_cache(t)
        if tx is not None:
            achats = tx[tx["code"] == "P"]
            for _, x in achats.iterrows():
                out.append({"ticker": t, "date": f"{x['date']}T00:00", "type": "Signal", "source": "Dirigeants (SEC)",
                            "titre": f"Achat en bourse par {x['nom']} ({x['fonction'] or 'dirigeant'})",
                            "lien": "", "detail": ""})
    # Mouvements des grands investisseurs sur vos valeurs, à leur dernier trimestre déclaré.
    try:
        mvt = inv.mouvements()
    except Exception:
        mvt = pd.DataFrame()
    if not mvt.empty:
        mvt = mvt[mvt["ticker"].isin(tickers)]
        libelles = {"Nouvelle": "entre sur", "Renforcée": "renforce", "Allégée": "allège", "Soldée": "sort de"}
        for _, x in mvt.iterrows():
            out.append({"ticker": x["ticker"], "date": f"{x['periode']}T00:00", "type": "Signal",
                        "source": "Grands investisseurs (13F)",
                        "titre": f"{x['investisseur']} {libelles.get(x['mouvement'], x['mouvement'].lower())} la valeur",
                        "lien": "", "detail": f"trimestre clos le {pd.Timestamp(x['periode']):%d/%m/%Y}"})
    return out


def fil(sc: pd.DataFrame) -> pd.DataFrame:
    """Toutes les actualités des valeurs suivies, la plus récente d'abord."""
    lignes = []
    for t in suivis():
        for x in (lire_json(path_of(t)) or {}).get("items", []):
            lignes.append({**x, "ticker": t})
    lignes += signaux(sc)
    df = pd.DataFrame(lignes, columns=["date", "ticker", "type", "source", "titre", "lien", "detail", "evenement"])
    if df.empty:
        return df
    df["nom"] = df["ticker"].map(sc["nom"]).fillna(df["ticker"])
    df = df.drop_duplicates(["ticker", "titre"]).sort_values("date", ascending=False, kind="stable")
    return df.reset_index(drop=True)


def derniere_visite() -> str | None:
    return (lire_json(VU_JSON) or {}).get("vu")


def marquer_vu() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    ecrire_json(VU_JSON, {"vu": datetime.now().isoformat(timespec="minutes")})
