"""Transactions boursières des élus de la Chambre des représentants américaine (STOCK Act).

Depuis 2012, chaque représentant déclare au greffe de la Chambre les achats et ventes de titres réalisés par
lui, son conjoint ou ses enfants à charge, au plus tard 45 jours après l'opération (« Periodic Transaction
Report »). Le greffe publie :
- un index annuel de toutes les déclarations (fichier XML dans une archive ZIP) ;
- chaque rapport en PDF. Les rapports remplis en ligne contiennent du texte, lu ici avec pypdf ; ceux déposés
  sur papier sont des images scannées, non lisibles sans reconnaissance de caractères : seul leur lien est donné.

Limites : montants déclarés par tranches (« 1 000 001 – 5 000 000 $ ») et non au dollar près, délai légal de
45 jours (souvent dépassé), Sénat non couvert (son site impose une acceptation de conditions à chaque visite).

Élus suivis : config/elus.csv (nom, prénom, parti, circonscription), modifiable depuis la page « Grands
investisseurs ». Les rapports lus sont gardés en cache : une mise à jour ne lit que les nouveaux.
"""
from __future__ import annotations

import io
import re
import time
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import date, datetime

import pandas as pd

from .config import CACHE_DIR, CONFIG_DIR, ecrire_json, lire_json, read_csv_fr, write_csv_fr

LISTE_CSV = CONFIG_DIR / "elus.csv"
COLONNES = ["nom", "prenom", "parti", "circonscription"]
CACHE = CACHE_DIR / "congres"
BASE = "https://disclosures-clerk.house.gov/public_disc"
AGENT = "portefeuille-perso/1.0 (outil personnel de recherche)"
PAUSE = 1.0
ANNEES = 2  # année en cours et précédente
FRAICHEUR_INDEX = 1  # jours avant de relire l'index de l'année en cours
FORMAT = 1

DETENTEURS = {"SP": "Conjoint", "JT": "Commun", "DC": "Enfant à charge", "": "Élu"}
OPERATIONS = {"P": "Achat", "S": "Vente", "S (partial)": "Vente partielle", "E": "Échange"}
TYPES = {"ST": "Action", "OP": "Options", "EF": "ETF", "MF": "Fonds", "GS": "Obligation d'État", "CS": "Obligation",
         "AB": "Placement non coté", "OT": "Autre", "PS": "Action de préférence", "CT": "Cryptomonnaie",
         "RS": "Actions de performance", "OI": "Participation", "HN": "Fonds spéculatif", "PE": "Capital-investissement"}

TYPE = re.compile(r"\[([A-Z]{2,3})\]")
COEUR = re.compile(r"(?:^|\s)(?P<op>P|S \(partial\)|S|E)\s+(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<notif>\d{2}/\d{2}/\d{4})(?=\s|$)")
TICKER = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,6})\)")
STATUT = re.compile(r"^F ?S ?:")
RATTACHEMENT = re.compile(r"^S ?O ?:")
DESCRIPTION = re.compile(r"^D ?:")
COMMENTAIRE = re.compile(r"^C ?:")
MONTANT = re.compile(r"\$[\d,]+(?:\.\d+)?")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    for essai in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                donnees = resp.read()
            time.sleep(PAUSE)
            return donnees
        except Exception:
            if essai == 2:
                raise
            time.sleep(5 * (essai + 1))  # le site coupe parfois les requêtes trop rapprochées
    raise RuntimeError("inaccessible")


# --------------------------------------------------------------------------- liste suivie et index

def load_liste() -> pd.DataFrame:
    if not LISTE_CSV.exists():
        return pd.DataFrame(columns=COLONNES)
    return read_csv_fr(LISTE_CSV).drop_duplicates(["nom", "circonscription"]).reset_index(drop=True)


def cle(nom: str, circonscription: str) -> str:
    return f"{nom}|{circonscription}"


def index(annee: int, force: bool = False) -> list[dict]:
    """Déclarations de l'année : une ligne par dépôt (nom, prénom, type, circonscription, date, numéro)."""
    chemin = CACHE / f"index_{annee}.json"
    d = lire_json(chemin)
    courante = annee == date.today().year
    if d and not force and not (courante and (time.time() - chemin.stat().st_mtime) / 86400 > FRAICHEUR_INDEX):
        return d["depots"]
    try:
        archive = zipfile.ZipFile(io.BytesIO(_get(f"{BASE}/financial-pdfs/{annee}FD.zip")))
        xml = archive.read(f"{annee}FD.xml").decode("utf-8-sig", errors="ignore")
    except Exception:
        return d["depots"] if d else []
    champ = lambda m, t: (re.search(f"<{t}>(.*?)</{t}>", m, re.S) or [None, ""])[1].strip()  # noqa: E731
    depots = []
    for m in re.findall(r"<Member>(.*?)</Member>", xml, re.S):
        jour = champ(m, "FilingDate")
        try:
            jour = datetime.strptime(jour, "%m/%d/%Y").date().isoformat()
        except ValueError:
            pass
        depots.append({"nom": champ(m, "Last"), "prenom": champ(m, "First"), "type": champ(m, "FilingType"),
                       "circonscription": champ(m, "StateDst"), "depose_le": jour, "numero": champ(m, "DocID"),
                       "annee": annee})
    CACHE.mkdir(parents=True, exist_ok=True)
    ecrire_json(chemin, {"depots": depots, "lu": datetime.now().isoformat(timespec="seconds")})
    return depots


def rapports_de_transactions(force: bool = False) -> list[dict]:
    annee = date.today().year
    return [x for a in range(annee - ANNEES + 1, annee + 1) for x in index(a, force) if x["type"] == "P"]


def elus_declarants() -> pd.DataFrame:
    """Tous les représentants ayant déclaré des transactions sur la période (pour en ajouter à la liste)."""
    df = pd.DataFrame(rapports_de_transactions())
    if df.empty:
        return df
    return (df.groupby(["nom", "circonscription"]).agg(prenom=("prenom", "last"), rapports=("numero", "count"))
            .reset_index().sort_values("rapports", ascending=False))


def ajouter(nom: str, prenom: str, circonscription: str, parti: str = "") -> None:
    liste = load_liste()
    nettoie = lambda t: str(t or "").replace(";", ",").strip()  # noqa: E731  (séparateur du CSV)
    ligne = {"nom": nettoie(nom), "prenom": nettoie(prenom), "parti": nettoie(parti), "circonscription": nettoie(circonscription)}
    liste = pd.concat([liste, pd.DataFrame([ligne])]).drop_duplicates(["nom", "circonscription"], keep="last")
    write_csv_fr(liste[COLONNES], LISTE_CSV)


def retirer(nom: str, circonscription: str) -> None:
    liste = load_liste()
    write_csv_fr(liste[~((liste["nom"] == nom) & (liste["circonscription"] == circonscription))][COLONNES], LISTE_CSV)


# --------------------------------------------------------------------------- lecture d'un rapport

def _bornes(montants: list[str]) -> tuple[float, float]:
    nombres = [float(x.replace("$", "").replace(",", "")) for x in montants]
    if not nombres:
        return float("nan"), float("nan")
    return nombres[0], (nombres[1] if len(nombres) > 1 else float("nan"))


def _lignes_du_tableau(texte: str) -> list[str]:
    """Lignes du tableau des opérations, sans les en-têtes de page ni les mentions finales."""
    # Les intitulés du formulaire (« Filing Status », « Description ») sortent du PDF avec des caractères nuls.
    brutes = [re.sub(r"\s+", " ", x.replace("\x00", " ")).strip() for x in texte.replace("\r", "").split("\n")]
    debut = next((i for i, x in enumerate(brutes) if x == "$200?"), -1)
    lignes, dans_entete = [], False
    for s in brutes[debut + 1:]:
        if s.startswith("* For the complete list"):
            break
        if s.startswith("Filing ID #") or s == "ID Owner Asset Transaction":
            dans_entete = True  # en-tête répété en haut de page, jusqu'à « $200? »
            continue
        if dans_entete:
            dans_entete = s != "$200?"
            continue
        if s:
            lignes.append(s)
    return lignes


def _operation(bloc: str) -> dict | None:
    """Une opération à partir de ses lignes réunies, quel que soit leur ordre (un saut de page peut les mêler)."""
    c = COEUR.search(bloc)
    t = TYPE.search(bloc)
    if not c or not t:
        return None
    reste = (bloc[:c.start()] + " " + bloc[c.end():]).replace(t.group(0), " ")
    montants = MONTANT.findall(reste)
    plus_de = "Over" in reste
    reste = re.sub(r"(Spouse/DC )?Over", " ", re.sub(MONTANT.pattern + r"(\s*-)?", " ", reste))  # avec le tiret de la tranche
    actif = re.sub(r"\s+-\s*$", "", re.sub(r"\s+", " ", reste)).strip(" -")
    detenteur = ""
    code = re.match(r"(SP|JT|DC)\s", actif + " ")
    if code:
        detenteur, actif = code.group(1), actif[code.end():].strip()
    tickers = TICKER.findall(actif)
    bas, haut = _bornes(montants)
    texte_montant = (f"Plus de {montants[0]}" if plus_de and montants else " – ".join(montants)) or "n.d."
    return {"detenteur": detenteur, "actif": actif, "type": t.group(1), "ticker": tickers[-1] if tickers else None,
            "operation": c.group("op"),
            "date": datetime.strptime(c.group("date"), "%m/%d/%Y").date().isoformat(),
            "notification": datetime.strptime(c.group("notif"), "%m/%d/%Y").date().isoformat(),
            "montant_min": bas, "montant_max": haut if not plus_de else float("nan"), "montant": texte_montant,
            "description": ""}


def analyser(texte: str) -> list[dict]:
    """Texte d'un rapport de transactions -> une ligne par opération.

    Chaque opération occupe un bloc : l'actif (terminé par son type entre crochets), l'opération, la date, la date
    de notification et la tranche de montant, puis la ligne de statut (« Filing Status : New »). Viennent ensuite,
    facultatifs, le compte de rattachement (« Subholding Of »), une description et un commentaire.
    """
    lignes = _lignes_du_tableau(texte)
    operations: list[dict] = []
    bloc: list[str] = []
    description_ouverte = False
    for s in lignes:
        if STATUT.match(s):  # fin du bloc de l'opération
            op = _operation(" ".join(bloc))
            if op:
                operations.append(op)
            bloc, description_ouverte = [], False
            continue
        if RATTACHEMENT.match(s) or COMMENTAIRE.match(s):
            description_ouverte = False
            continue
        if DESCRIPTION.match(s):
            if operations:
                operations[-1]["description"] = s.split(":", 1)[1].strip()
            description_ouverte = True
            continue
        if description_ouverte and operations:
            # Suite d'une description coupée, sauf si la ligne ouvre visiblement l'opération suivante.
            precedente = operations[-1]["description"]
            nouvelle = re.match(r"(SP|JT|DC)\s", s) or TYPE.search(s) or COEUR.search(s)
            if not nouvelle and not precedente.endswith("."):
                operations[-1]["description"] = f"{precedente} {s}"
                continue
            description_ouverte = False
        bloc.append(s)
    if bloc:  # dernière opération sans ligne de statut
        op = _operation(" ".join(bloc))
        if op:
            operations.append(op)
    return operations


def lire_rapport(annee: int, numero: str) -> dict:
    """Télécharge et lit un rapport : {"scanne": bool, "operations": [...]}."""
    from pypdf import PdfReader  # import local : pypdf ne sert qu'ici

    pdf = PdfReader(io.BytesIO(_get(f"{BASE}/ptr-pdfs/{annee}/{numero}.pdf")))
    texte = "\n".join((p.extract_text() or "") for p in pdf.pages)
    if len(texte.strip()) < 50:
        return {"scanne": True, "operations": []}
    return {"scanne": False, "operations": analyser(texte)}


def url_rapport(annee: int, numero: str) -> str:
    return f"{BASE}/ptr-pdfs/{annee}/{numero}.pdf"


# --------------------------------------------------------------------------- mise à jour

def path_rapports():
    return CACHE / "rapports.json"


def mettre_a_jour(force: bool = False, progress: Callable[[str], None] | None = None) -> dict:
    """Index des deux dernières années, puis les rapports des élus suivis qui ne sont pas encore en cache."""
    cache = lire_json(path_rapports()) or {}
    if cache.get("format") != FORMAT:
        cache = {"format": FORMAT, "rapports": {}}
    suivis = {cle(r["nom"], r["circonscription"]) for _, r in load_liste().iterrows()}
    a_lire = [x for x in rapports_de_transactions(force) if cle(x["nom"], x["circonscription"]) in suivis
              and x["numero"] not in cache["rapports"]]
    res = {"nouveaux": 0, "scannes": 0, "erreurs": {}}
    for k, x in enumerate(a_lire, 1):
        try:
            lu = lire_rapport(x["annee"], x["numero"])
        except Exception as exc:
            res["erreurs"][x["numero"]] = str(exc)[:200]
            continue
        cache["rapports"][x["numero"]] = {**{c: x[c] for c in ("nom", "prenom", "circonscription", "depose_le", "annee")}, **lu}
        res["nouveaux"] += 1
        res["scannes"] += lu["scanne"]
        if progress and (k % 10 == 0 or k == len(a_lire)):
            progress(f"  rapports {k}/{len(a_lire)}")
            ecrire_json(path_rapports(), cache)  # on garde le travail fait en cas d'interruption
    cache["lu"] = datetime.now().isoformat(timespec="seconds")
    CACHE.mkdir(parents=True, exist_ok=True)
    ecrire_json(path_rapports(), cache)
    return res


# --------------------------------------------------------------------------- lecture pour l'interface

def transactions() -> pd.DataFrame:
    """Toutes les opérations lues des élus suivis, la plus récente d'abord."""
    cache = lire_json(path_rapports()) or {}
    liste = load_liste()
    suivis = {cle(r["nom"], r["circonscription"]): r for _, r in liste.iterrows()}
    lignes = []
    for numero, r in (cache.get("rapports") or {}).items():
        elu = suivis.get(cle(r["nom"], r["circonscription"]))
        if elu is None:
            continue
        base = {"elu": f"{elu['prenom']} {elu['nom']}".strip(), "parti": elu.get("parti", ""),
                "circonscription": r["circonscription"], "depose_le": r["depose_le"], "numero": numero,
                "lien": url_rapport(r["annee"], numero)}
        for op in r["operations"]:
            lignes.append({**base, **op})
    df = pd.DataFrame(lignes)
    if df.empty:
        return df
    df["retard_jours"] = (pd.to_datetime(df["depose_le"]) - pd.to_datetime(df["date"])).dt.days
    return df.sort_values(["date", "depose_le"], ascending=False).reset_index(drop=True)


def rapports_scannes() -> pd.DataFrame:
    """Rapports déposés sur papier (images) des élus suivis : seul leur lien est disponible."""
    cache = lire_json(path_rapports()) or {}
    suivis = {cle(r["nom"], r["circonscription"]) for _, r in load_liste().iterrows()}
    lignes = [{"elu": f"{r['prenom']} {r['nom']}", "depose_le": r["depose_le"], "lien": url_rapport(r["annee"], n)}
              for n, r in (cache.get("rapports") or {}).items()
              if r.get("scanne") and cle(r["nom"], r["circonscription"]) in suivis]
    return pd.DataFrame(lignes, columns=["elu", "depose_le", "lien"])


def derniere_mise_a_jour() -> str | None:
    return (lire_json(path_rapports()) or {}).get("lu")
