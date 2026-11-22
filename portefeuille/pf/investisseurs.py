"""Portefeuilles d'investisseurs reconnus, d'après leurs déclarations trimestrielles 13F à la SEC.

Tout gérant qui détient plus de 100 millions de dollars d'actions cotées aux États-Unis déclare ses positions
dans les 45 jours qui suivent la fin de chaque trimestre (formulaire 13F-HR). On y lit, titre par titre, le
nombre d'actions et leur valeur au dernier jour du trimestre. En comparant deux trimestres, on voit les
entrées, renforcements, allègements et sorties.

Limites : positions longues en actions américaines seulement (ni ventes à découvert, ni valeurs cotées hors
des États-Unis, ni liquidités), photo prise un jour donné et publiée avec six semaines de retard, sans le
prix payé ni la raison de l'achat. Les options (put, call) sont écartées.

Liste des investisseurs suivis : config/investisseurs.csv (CIK SEC, nom, société, style), modifiable depuis la
page « Grands investisseurs ». Les déclarations lues sont gardées en cache : une mise à jour ne lit que les
nouvelles. Les tickers viennent d'OpenFIGI (Bloomberg), à partir du code CUSIP de chaque titre.
"""
from __future__ import annotations

import collections
import difflib
import json
import math
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import date, datetime

import pandas as pd

from . import sec
from .config import CONFIG_DIR, SEC_DIR, ecrire_json, lire_json, read_csv_fr, write_csv_fr

LISTE_CSV = CONFIG_DIR / "investisseurs.csv"
COLONNES = ["cik", "investisseur", "societe", "style"]
CACHE = SEC_DIR / "13f"
TICKERS_JSON = CACHE / "cusip_tickers.json"
TRIMESTRES = 8  # deux ans de déclarations par investisseur
FRAICHEUR = 7  # jours entre deux consultations de la liste des dépôts d'un investisseur
FORMAT = 1
FIGI_URL = "https://api.openfigi.com/v3/mapping"
FIGI_LOT = 10  # codes par requête sans clé d'accès
FIGI_PAUSE = 2.6  # 25 requêtes par minute sans clé d'accès
SEUIL_INCHANGEE = 0.02  # variation du nombre d'actions en deçà de laquelle une ligne est « inchangée »


# --------------------------------------------------------------------------- liste suivie

def load_liste() -> pd.DataFrame:
    if not LISTE_CSV.exists():
        return pd.DataFrame(columns=COLONNES[1:], index=pd.Index([], name="cik", dtype="int64"))
    df = read_csv_fr(LISTE_CSV)
    df["cik"] = pd.to_numeric(df["cik"], errors="coerce")
    return df.dropna(subset=["cik"]).astype({"cik": "int64"}).drop_duplicates("cik").set_index("cik")


def identifier(cik: int) -> dict:
    """Nom SEC et dernière déclaration 13F d'un déposant ; lève ValueError s'il n'en dépose pas."""
    agent = sec.contact()
    if not agent:
        raise ValueError("contact_sec absent de profil/prive.json")
    d = sec._get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", agent)
    r = d["filings"]["recent"]
    periodes = [r["reportDate"][i] for i, f in enumerate(r["form"]) if f == "13F-HR"]
    if not periodes:
        raise ValueError(f"{d.get('name', cik)} ne dépose pas de déclaration 13F")
    return {"nom": d.get("name", ""), "derniere": max(periodes)}


def ajouter(cik: int, investisseur: str = "", style: str = "") -> dict:
    """Ajoute un déposant à la liste, après avoir vérifié qu'il dépose des 13F. Renvoie son identité SEC."""
    ident = identifier(cik)
    liste = load_liste()
    nettoie = lambda t: str(t or "").replace(";", ",").strip()  # noqa: E731  (séparateur du CSV)
    liste.loc[int(cik)] = {"investisseur": nettoie(investisseur) or ident["nom"].title(),
                           "societe": ident["nom"].title(), "style": nettoie(style)}
    write_csv_fr(liste.reset_index(), LISTE_CSV)
    return ident


def retirer(cik: int) -> None:
    liste = load_liste()
    if int(cik) in liste.index:
        write_csv_fr(liste.drop(index=int(cik)).reset_index(), LISTE_CSV)


# --------------------------------------------------------------------------- lecture d'une déclaration

def _local(balise: str) -> str:
    return balise.rsplit("}", 1)[-1]


def _texte(e: ET.Element, nom: str) -> str:
    for x in e.iter():
        if _local(x.tag) == nom:
            return (x.text or "").strip()
    return ""


def analyser_table(xml: str, en_milliers: bool = False) -> list[dict]:
    """Table d'information d'une 13F -> une ligne par titre détenu (options écartées, lignes d'un même titre additionnées).

    Avant 2023, les valeurs étaient déclarées en milliers de dollars (`en_milliers`).
    """
    racine = ET.fromstring(xml.strip().encode("utf-8"))
    lignes: dict[str, dict] = {}
    for e in racine.iter():
        if _local(e.tag) != "infoTable":
            continue
        if _texte(e, "putCall") or _texte(e, "sshPrnamtType") not in ("SH", ""):
            continue  # options et obligations (montant nominal)
        cusip = _texte(e, "cusip").upper()
        try:
            valeur = float(_texte(e, "value")) * (1000 if en_milliers else 1)
            actions = float(_texte(e, "sshPrnamt"))
        except ValueError:
            continue
        x = lignes.setdefault(cusip, {"cusip": cusip, "nom": _texte(e, "nameOfIssuer"), "classe": _texte(e, "titleOfClass"),
                                      "valeur": 0.0, "actions": 0.0})
        x["valeur"] += valeur
        x["actions"] += actions
    return list(lignes.values())


def _type_rectificatif(cik: int, numero: str, agent: str) -> str:
    """« RESTATEMENT » (remplace la déclaration) ou « NEW HOLDINGS » (ajoute des positions jusque-là confidentielles)."""
    xml = sec._brut(f"https://www.sec.gov/Archives/edgar/data/{cik}/{numero.replace('-', '')}/primary_doc.xml", agent)
    racine = ET.fromstring(xml)
    return _texte(racine, "amendmentType").upper() or "RESTATEMENT"


def _lire_depot(cik: int, numero: str, depot: str, agent: str) -> list[dict]:
    dossier = f"https://www.sec.gov/Archives/edgar/data/{cik}/{numero.replace('-', '')}"
    fichiers = sec._get(f"{dossier}/index.json", agent)["directory"]["item"]
    tables = [f["name"] for f in fichiers if f["name"].lower().endswith(".xml") and f["name"] != "primary_doc.xml"]
    if not tables:
        return []
    time.sleep(sec.PAUSE)
    return analyser_table(sec._brut(f"{dossier}/{tables[0]}", agent).decode("utf-8", errors="ignore"),
                          en_milliers=depot < "2023-01-03")


# --------------------------------------------------------------------------- mise à jour

def path_of(cik: int):
    return CACHE / f"{int(cik)}.json"


def _a_consulter(cik: int, force: bool) -> bool:
    d = lire_json(path_of(cik))
    if force or not d or d.get("format") != FORMAT:
        return True
    return (pd.Timestamp.today() - pd.Timestamp(d.get("consulte_le", "2000-01-01"))).days >= FRAICHEUR


def mettre_a_jour_un(cik: int, agent: str) -> dict:
    """Lit les déclarations des TRIMESTRES derniers trimestres qui ne sont pas encore en cache (ou qui ont été rectifiées)."""
    d = lire_json(path_of(cik)) or {}
    if d.get("format") != FORMAT:
        d = {"format": FORMAT, "periodes": {}}
    sub = sec._get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", agent)
    r = sub["filings"]["recent"]
    depots = sorted(((r["reportDate"][i], r["filingDate"][i], r["accessionNumber"][i], f)
                     for i, f in enumerate(r["form"]) if f in ("13F-HR", "13F-HR/A")), key=lambda x: (x[0], x[1]))
    periodes = sorted({p for p, *_ in depots if p})[-TRIMESTRES:]
    nouvelles = 0
    for periode in periodes:
        du_trimestre = [(dep, num, f) for p, dep, num, f in depots if p == periode]
        numeros = [num for _, num, _ in du_trimestre]
        if d["periodes"].get(periode, {}).get("depots") == numeros:
            continue  # déjà lu, sans rectificatif depuis
        lignes: dict[str, dict] = {}
        for dep, num, forme in du_trimestre:  # dans l'ordre des dépôts
            nouvelles_lignes = _lire_depot(cik, num, dep, agent)
            time.sleep(sec.PAUSE)
            if forme == "13F-HR/A" and _type_rectificatif(cik, num, agent) == "NEW HOLDINGS":
                for x in nouvelles_lignes:  # positions révélées après coup : elles s'ajoutent
                    y = lignes.setdefault(x["cusip"], {**x, "valeur": 0.0, "actions": 0.0})
                    y["valeur"] += x["valeur"]
                    y["actions"] += x["actions"]
            else:  # déclaration d'origine, ou rectificatif qui la remplace
                lignes = {x["cusip"]: x for x in nouvelles_lignes} if nouvelles_lignes else lignes
        d["periodes"][periode] = {"depots": numeros, "depose_le": du_trimestre[-1][0], "lignes": list(lignes.values())}
        nouvelles += 1
    d["periodes"] = {p: v for p, v in d["periodes"].items() if p in periodes}
    d.update(cik=int(cik), nom_sec=sub.get("name", ""), consulte_le=date.today().isoformat(),
             lu=datetime.now().isoformat(timespec="seconds"))
    CACHE.mkdir(parents=True, exist_ok=True)
    ecrire_json(path_of(cik), d)
    return {"nouvelles": nouvelles}


def _figi(lot: list[str], place_us: bool = True) -> list[dict | None]:
    """Ticker de chaque CUSIP. Sans `place_us`, toutes les places sont interrogées et le ticker américain
    (places « U… ») le plus fréquent est retenu : certains titres ne répondent pas à la place composite « US »."""
    corps = json.dumps([{"idType": "ID_CUSIP", "idValue": c, **({"exchCode": "US"} if place_us else {})}
                        for c in lot]).encode()
    req = urllib.request.Request(FIGI_URL, data=corps, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "portefeuille-perso/1.0"})
    for essai in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                reponse = json.loads(resp.read())
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or essai == 3:
                raise
            time.sleep(61)  # fenêtre d'une minute écoulée
    out = []
    for x in reponse:
        donnees = (x or {}).get("data") or []
        actions = [y for y in donnees if y.get("marketSector") == "Equity"] or donnees
        if not place_us:
            actions = [y for y in actions if str(y.get("exchCode", "")).startswith("U") and len(str(y.get("exchCode"))) == 2]
            if actions:
                frequent = collections.Counter(y["ticker"] for y in actions).most_common(1)[0][0]
                actions = [y for y in actions if y["ticker"] == frequent]
        out.append({"ticker": actions[0]["ticker"].replace("/", "-"), "nom": actions[0].get("name", "")} if actions else None)
    return out


FORMES = {"INCORPORATED": "INC", "CORPORATION": "CORP", "LIMITED": "LTD", "COMPANY": "CO", "HOLDINGS": "HLDGS",
          "GROUP": "GRP", "THE": "", "PLC": "", "NV": "", "SA": "", "AG": "", "SE": "", "CL": "", "CLASS": "", "COM": ""}


def _nom_normalise(nom: str) -> str:
    mots = re.findall(r"[A-Z0-9]+", nom.upper().replace("&", " AND "))
    return " ".join(m for m in (FORMES.get(x, x) for x in mots) if m)


def _par_nom(noms: dict[str, str]) -> dict[str, dict]:
    """Dernier recours : nom déclaré -> ticker SEC, si un seul titre de la SEC porte un nom très proche."""
    agent = sec.contact()
    if not agent or not noms:
        return {}
    brut = lire_json(SEC_DIR / "company_tickers.json") or {}
    if not brut:
        sec.ticker_map(agent)
        brut = lire_json(SEC_DIR / "company_tickers.json") or {}
    par_nom: dict[str, set[str]] = {}
    for v in brut.values():
        par_nom.setdefault(_nom_normalise(v["title"]), set()).add(v["ticker"].upper())
    trouves = {}
    for cusip, nom in noms.items():
        cle = _nom_normalise(nom)
        proches = difflib.get_close_matches(cle, list(par_nom), n=2, cutoff=0.92)
        if len(proches) == 1 and len(par_nom[proches[0]]) == 1:  # plusieurs classes d'actions : on s'abstient
            trouves[cusip] = {"ticker": next(iter(par_nom[proches[0]])).replace(".", "-"), "nom": nom, "par_nom": True}
    return trouves


def completer_tickers(progress: Callable[[str], None] | None = None) -> int:
    """Associe un ticker aux codes CUSIP pas encore connus (cache permanent). Renvoie le nombre de codes traités.

    OpenFIGI d'abord (place composite « US », puis toutes places), puis le nom déclaré. Un code resté sans
    ticker est retenté après 90 jours.
    """
    connus = lire_json(TICKERS_JSON) or {}
    noms = {x["cusip"]: x["nom"] for cik in load_liste().index
            for p in (lire_json(path_of(cik)) or {}).get("periodes", {}).values() for x in p["lignes"]}
    limite = (pd.Timestamp.today() - pd.Timedelta(days=90)).date().isoformat()
    a_faire = sorted(c for c in noms if c not in connus or (connus[c] is None)
                     or (not connus[c].get("ticker") and connus[c].get("essai", "") < limite))
    for place_us in (True, False):
        lot_total = [c for c in a_faire if not (connus.get(c) or {}).get("ticker")]
        for i in range(0, len(lot_total), FIGI_LOT):
            lot = lot_total[i:i + FIGI_LOT]
            try:
                for c, res in zip(lot, _figi(lot, place_us)):
                    if res:
                        connus[c] = res
            except Exception:
                break  # service injoignable : les codes restants attendront la prochaine mise à jour
            if progress:
                progress(f"  tickers {min(i + FIGI_LOT, len(lot_total))}/{len(lot_total)}")
            time.sleep(FIGI_PAUSE)
    restants = {c: noms[c] for c in a_faire if not (connus.get(c) or {}).get("ticker")}
    connus.update(_par_nom(restants))
    for c in a_faire:
        if not (connus.get(c) or {}).get("ticker"):
            connus[c] = {"ticker": None, "nom": noms[c], "essai": date.today().isoformat()}
    CACHE.mkdir(parents=True, exist_ok=True)
    ecrire_json(TICKERS_JSON, connus)
    return len(a_faire)


def mettre_a_jour(force: bool = False, progress: Callable[[str], None] | None = None) -> dict:
    """Met à jour les investisseurs dont la dernière consultation a plus d'une semaine (tous si `force`)."""
    agent = sec.contact()
    if not agent:
        return {"ok": [], "erreurs": {}, "saute": "contact_sec absent de profil/prive.json"}
    res: dict = {"ok": [], "erreurs": {}, "nouvelles": 0}
    liste = load_liste()
    for k, (cik, ligne) in enumerate(liste.iterrows(), 1):
        if not _a_consulter(cik, force):
            continue
        try:
            res["nouvelles"] += mettre_a_jour_un(cik, agent)["nouvelles"]
            res["ok"].append(ligne["investisseur"])
        except Exception as exc:
            res["erreurs"][ligne["investisseur"]] = str(exc)[:200]
        if progress:
            progress(f"  {k}/{len(liste)} {ligne['investisseur']}")
        time.sleep(sec.PAUSE)
    res["tickers"] = completer_tickers(progress)
    return res


# --------------------------------------------------------------------------- lecture pour l'interface

def _tickers() -> dict:
    return lire_json(TICKERS_JSON) or {}


def periodes(cik: int) -> list[str]:
    return sorted((lire_json(path_of(cik)) or {}).get("periodes", {}))


def derniere_mise_a_jour() -> str | None:
    dates = [(lire_json(path_of(c)) or {}).get("lu") for c in load_liste().index]
    dates = [x for x in dates if x]
    return max(dates) if dates else None


def _table(d: dict, periode: str, tickers: dict) -> pd.DataFrame:
    p = d.get("periodes", {}).get(periode)
    df = pd.DataFrame(p["lignes"] if p else [], columns=["cusip", "nom", "classe", "valeur", "actions"])
    df["ticker"] = df["cusip"].map(lambda c: (tickers.get(c) or {}).get("ticker"))
    return df.set_index("cusip")


def mouvement(actions: float, avant: float) -> tuple[str, float]:
    """(« Nouvelle », « Renforcée », « Allégée », « Soldée » ou « Inchangée », variation du nombre d'actions)."""
    a = actions if isinstance(actions, (int, float)) and math.isfinite(actions) else 0.0
    b = avant if isinstance(avant, (int, float)) and math.isfinite(avant) else 0.0
    if b <= 0 and a > 0:
        return "Nouvelle", math.nan
    if a <= 0 and b > 0:
        return "Soldée", -1.0
    if b <= 0:
        return "", math.nan
    v = a / b - 1
    return ("Renforcée" if v > SEUIL_INCHANGEE else "Allégée" if v < -SEUIL_INCHANGEE else "Inchangée"), v


def positions(cik: int, periode: str | None = None) -> pd.DataFrame:
    """Lignes du trimestre (par défaut le dernier) : poids, mouvement depuis le trimestre précédent, ancienneté.

    Les lignes soldées pendant le trimestre figurent aussi, avec une valeur nulle.
    """
    d = lire_json(path_of(cik)) or {}
    liste = sorted(d.get("periodes", {}))
    if not liste:
        return pd.DataFrame()
    periode = periode if periode in liste else liste[-1]
    i = liste.index(periode)
    tickers = _tickers()
    cur = _table(d, periode, tickers)
    avant = _table(d, liste[i - 1], tickers) if i > 0 else None
    total = cur["valeur"].sum()
    out = cur.copy()
    out["poids"] = out["valeur"] / total if total else math.nan
    if avant is not None:
        soldees = avant.loc[avant.index.difference(out.index)].assign(valeur=0.0, actions=0.0, poids=0.0)
        out = pd.concat([out, soldees])
        out["actions_avant"] = avant["actions"].reindex(out.index).fillna(0.0)
        mv = [mouvement(a, b) for a, b in zip(out["actions"], out["actions_avant"])]
        out["mouvement"] = [m for m, _ in mv]
        out["variation"] = [v for _, v in mv]
        # Ancienneté : premier trimestre d'une détention continue jusqu'à celui-ci (dans la fenêtre lue).
        presents = {p: {x["cusip"] for x in d["periodes"][p]["lignes"]} for p in liste[:i]}
        depuis = {}
        for c in out.index:
            debut = periode
            for p in reversed(liste[:i]):
                if c not in presents[p]:
                    break
                debut = p
            depuis[c] = debut
        out["depuis"] = pd.Series(depuis)
        out["depuis_debut_fenetre"] = out["depuis"] == liste[0]
    else:
        out["actions_avant"], out["mouvement"], out["variation"] = math.nan, "", math.nan
        out["depuis"], out["depuis_debut_fenetre"] = periode, True
    out.attrs.update(periode=periode, precedente=liste[i - 1] if i > 0 else None, total=total,
                     depose_le=d["periodes"][periode].get("depose_le"), premiere=liste[0])
    return out.sort_values(["valeur", "nom"], ascending=[False, True])


def mouvements(liste: pd.DataFrame | None = None) -> pd.DataFrame:
    """Mouvements du dernier trimestre déclaré par chaque investisseur (lignes inchangées exclues)."""
    liste = load_liste() if liste is None else liste
    lignes = []
    for cik, inv in liste.iterrows():
        p = positions(cik)
        if p.empty or "mouvement" not in p.columns:
            continue
        m = p[p["mouvement"].isin(["Nouvelle", "Renforcée", "Allégée", "Soldée"])]
        for cusip, x in m.iterrows():
            lignes.append({"investisseur": inv["investisseur"], "cik": cik, "periode": p.attrs["periode"], "cusip": cusip,
                           "nom": x["nom"], "ticker": x["ticker"], "mouvement": x["mouvement"], "variation": x["variation"],
                           "poids": x["poids"], "valeur": x["valeur"]})
    return pd.DataFrame(lignes)


def consensus(liste: pd.DataFrame | None = None) -> pd.DataFrame:
    """Titres les plus partagés : nombre d'investisseurs qui les détiennent (dernier trimestre de chacun) et poids moyen."""
    liste = load_liste() if liste is None else liste
    lignes = []
    for cik, inv in liste.iterrows():
        p = positions(cik)
        if p.empty:
            continue
        for cusip, x in p[p["valeur"] > 0].iterrows():
            lignes.append({"cusip": cusip, "nom": x["nom"], "ticker": x["ticker"], "investisseur": inv["investisseur"],
                           "poids": x["poids"]})
    if not lignes:
        return pd.DataFrame()
    df = pd.DataFrame(lignes)
    # Un émetteur = les six premiers caractères du CUSIP : les classes d'actions (GOOGL, GOOG) sont réunies.
    df["emetteur"] = df["cusip"].str[:6]
    par_inv = df.groupby(["emetteur", "investisseur"]).agg(
        nom=("nom", "first"), poids=("poids", "sum"),
        ticker=("ticker", lambda s: ", ".join(dict.fromkeys(x for x in s if isinstance(x, str))) or None)).reset_index()
    g = par_inv.groupby("emetteur").agg(
        nom=("nom", "first"), ticker=("ticker", lambda s: ", ".join(dict.fromkeys(
            y for x in s if isinstance(x, str) for y in x.split(", "))) or None),
        detenteurs=("investisseur", "nunique"), poids_moyen=("poids", "mean"), poids_max=("poids", "max"),
        qui=("investisseur", lambda s: ", ".join(sorted(set(s)))), liste=("investisseur", lambda s: sorted(set(s))))
    return g.sort_values(["detenteurs", "poids_moyen"], ascending=False)


def detenteurs_par_ticker() -> dict[str, list[str]]:
    """Ticker -> investisseurs suivis qui détiennent le titre à leur dernier trimestre déclaré (toutes classes d'actions)."""
    cons = consensus()
    out: dict[str, list[str]] = {}
    if cons.empty:
        return out
    for _, x in cons.iterrows():
        for t in str(x["ticker"] or "").split(", "):
            if t and t != "None":
                out[t] = list(x["liste"])
    return out
