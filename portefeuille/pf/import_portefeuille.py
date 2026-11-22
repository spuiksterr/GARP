"""Import d'un portefeuille depuis ce que l'utilisateur a sous la main : export CSV du courtier, tableau copié
d'Excel ou du site du courtier, ou simple liste « ticker ; poids ».

Repris de l'application (app/lib/import_portefeuille.dart), avec les mêmes règles. Trois étapes, sans réseau :
lire le tableau (séparateur et ligne d'en-tête devinés), reconnaître chaque ligne parmi les valeurs de l'univers
(ISIN déjà vu, ticker, puis nom), calculer les poids (poids donnés, sinon montants, sinon quantités × cours en
euros). L'utilisateur vérifie ensuite le résultat (page « Importer mon portefeuille ») avant de l'enregistrer.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd


class Confiance(str, Enum):
    SURE = "Reconnue"
    PROBABLE = "À vérifier"
    AUCUNE = "Hors des données"


@dataclass
class LigneImportee:
    libelle: str  # nom de la ligne tel qu'écrit dans le fichier (ou son ticker, ou son ISIN)
    isin: str | None = None
    ticker_fichier: str | None = None
    taille: float | None = None  # poids ou montant (proportionnels au poids), s'ils figurent dans le fichier
    quantite: float | None = None
    prix: float | None = None  # cours donné par le fichier (en pratique l'euro)
    ticker: str | None = None  # valeur de l'univers retenue
    confiance: Confiance = Confiance.AUCUNE
    ignoree: bool = False
    poids: float = 0.0  # en % du portefeuille importé, calculé par calculer_poids

    @property
    def cle(self) -> str:
        """Clé sous laquelle la correspondance choisie est retenue (ISIN, sinon nom normalisé)."""
        return self.isin or normaliser(self.libelle)


@dataclass
class ResultatImport:
    lignes: list[LigneImportee]
    methode: str  # comment les poids ont été obtenus, pour l'expliquer
    retenues: list[LigneImportee] = field(init=False)

    def __post_init__(self):
        self.retenues = [ligne for ligne in self.lignes if not ligne.ignoree]


# ---------------------------------------------------------------------------------------------- lecture du tableau

_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_AVEC = "àâäáãåçéèêëíìîïñóòôöõúùûüýÿœæ"
_SANS = "aaaaaaceeeeiiiinooooouuuuyyoa"
_ACCENTS = str.maketrans(_AVEC, _SANS)


def normaliser(s: str) -> str:
    """Minuscules sans accents ni ponctuation, espaces simples."""
    s = s.lower().translate(_ACCENTS)
    return re.sub(r"[^a-z0-9%]+", " ", s).strip()


def lire_nombre(brut: str | None) -> float | None:
    """Nombre écrit à la française ou à l'anglaise : « 1 234,56 € », « 1,234.56 », « 34,5 % », « 1’234.5 »."""
    if brut is None:
        return None
    # \s couvre aussi les espaces insécables qui séparent les milliers.
    s = re.sub(r"[\s’'€$£%]|EUR|USD|GBP|CHF", "", str(brut).strip(), flags=re.IGNORECASE)
    if not s or not re.fullmatch(r"[-+(]?[0-9.,]+\)?", s):
        return None
    negatif = s.startswith(("-", "("))
    s = re.sub(r"[-+()]", "", s)
    virgule, point = s.rfind(","), s.rfind(".")
    if virgule >= 0 and point >= 0:  # le dernier des deux sépare les décimales
        s = s.replace(".", "").replace(",", ".") if virgule > point else s.replace(",", "")
    elif virgule >= 0:
        s = s.replace(",", "") if s.count(",") > 1 else s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if negatif else v


def _decouper(ligne: str, sep: str) -> list[str]:
    out, cellule, guillemets, i = [], [], False, 0
    while i < len(ligne):
        c = ligne[i]
        if c == '"':
            if guillemets and i + 1 < len(ligne) and ligne[i + 1] == '"':
                cellule.append('"')
                i += 1
            else:
                guillemets = not guillemets
        elif c == sep and not guillemets:
            out.append("".join(cellule).strip())
            cellule = []
        else:
            cellule.append(c)
        i += 1
    out.append("".join(cellule).strip())
    return out


def lire_tableau(texte: str) -> list[list[str]]:
    """Découpe le texte en lignes et cellules. Séparateur deviné parmi tabulation, point-virgule, barre et virgule ;
    à défaut (liste tapée à la main), chaque ligne devient « libellé, nombre »."""
    lignes = [ligne for ligne in re.split(r"\r\n|\r|\n", texte.replace("﻿", "")) if ligne.strip()]
    if not lignes:
        return []
    echantillon = lignes[:30]
    meilleur, meilleur_score = None, 0.0
    for sep in ["\t", ";", "|", ","]:
        avec = sum(1 for ligne in echantillon if len(_decouper(ligne, sep)) > 1)
        # Part des lignes découpées ; la virgule, qui sert aussi aux décimales, ne gagne qu'à défaut d'autre.
        score = avec / len(echantillon) - (0.3 if sep == "," else 0)
        if avec > 0 and score > meilleur_score:
            meilleur, meilleur_score = sep, score
    if meilleur is not None and meilleur_score >= 0.5:
        return [_decouper(ligne, meilleur) for ligne in lignes]
    libre = re.compile(r"^(.*?)[\s:=]+([-+]?[0-9][0-9   .,’]*\s*%?)$")
    out = []
    for ligne in lignes:
        m = libre.match(ligne.strip())
        out.append([m.group(1).strip(), m.group(2).strip()] if m else [ligne.strip()])
    return out


# ---------------------------------------------------------------------------------------------- colonnes

ISIN, TICKER, NOM, POIDS, MONTANT, QUANTITE, PRIX = "isin", "ticker", "nom", "poids", "montant", "quantite", "prix"


def _contient(entete: str, mots: list[str]) -> bool:
    return any(entete == m or m in entete for m in mots)


def role_colonne(entete: str) -> str | None:
    """Rôle d'une colonne d'après son en-tête (None si inutile pour l'import)."""
    e = normaliser(entete)
    if not e:
        return None
    if "isin" in e:
        return ISIN
    # Performances, plus-values et prix de revient ne disent rien du poids actuel.
    if re.search(r"\+\s*/?\s*[-−]", entete) or _contient(e, [
            "plus value", "plus ou moins", "perf", "variation", "var ", "gain", "latent", "revient", "pru",
            "prix moyen", "achat", "investi", "frais", "date", "devise"]):
        return None
    if _contient(e, ["ticker", "symbole", "symbol", "mnemo", "code valeur", "code"]):
        return TICKER
    if _contient(e, ["poids", "weight", "repartition", "allocation", "part du portefeuille", "% du",
                     "pourcentage"]) or e in ("%", "part"):
        return POIDS
    if _contient(e, ["quantite", "qte", "qty", "quantity", "nombre de", "nombre", "nb titres", "shares", "parts"]):
        return QUANTITE
    if _contient(e, ["montant", "valorisation", "valeur en", "valeur eur", "valeur totale", "valeur actuelle",
                     "valeur de marche", "market value", "evaluation", "encours", "total", "solde", "value"]):
        return MONTANT
    if _contient(e, ["cours", "prix", "price", "dernier", "cloture", "close"]):
        return PRIX
    if _contient(e, ["nom", "libelle", "produit", "instrument", "designation", "name", "titre", "actif", "support",
                     "societe", "entreprise", "description"]) or e in ("valeur", "valeurs"):
        return NOM
    return None


def en_tete(tableau: list[list[str]]) -> tuple[int, dict[str, int]] | None:
    """Ligne d'en-tête : la première (parmi les 15 premières) dont au moins deux colonnes ont un rôle."""
    for i, ligne in enumerate(tableau[:15]):
        roles: dict[str, int] = {}
        for j, cellule in enumerate(ligne):
            r = role_colonne(cellule)
            if r is None or lire_nombre(cellule) is not None:
                continue
            # Montant : préférer la colonne en euros quand il y en a plusieurs.
            if r == MONTANT and r in roles and "eur" not in normaliser(cellule):
                continue
            if r in roles and r != MONTANT:
                continue
            roles[r] = j
        if len(roles) >= 2 and (NOM in roles or TICKER in roles or ISIN in roles):
            return i, roles
    return None


def _total(s: str) -> bool:
    return re.match(r"^(sous )?total|^totaux|^ensemble", normaliser(s)) is not None


def _liquidites(s: str) -> bool:
    return re.search(r"liquidit|especes|^cash|solde|compte espece|fonds disponibles", normaliser(s)) is not None


def lignes_du_tableau(tableau: list[list[str]]) -> list[LigneImportee]:
    """Lignes du fichier, avant reconnaissance."""
    out: list[LigneImportee] = []
    entete = en_tete(tableau)
    if entete is not None:
        debut, roles = entete

        def cellule(ligne: list[str], role: str) -> str | None:
            j = roles.get(role)
            return None if j is None or j >= len(ligne) or not ligne[j] else ligne[j]

        for ligne in tableau[debut + 1:]:
            # Un ISIN peut aussi être dans la colonne « Symbole/ISIN » ou ailleurs.
            candidats = [c for c in [cellule(ligne, ISIN), *ligne] if c]
            isin = next((c.strip().upper() for c in candidats if _ISIN.match(c.strip().upper())), None)
            brut = cellule(ligne, TICKER)
            brut = brut.upper() if brut else None
            ticker = brut if brut and not _ISIN.match(brut) else None
            libelle = cellule(ligne, NOM) or ticker or isin
            if libelle is None or _total(libelle):
                continue
            taille = lire_nombre(cellule(ligne, POIDS))
            li = LigneImportee(
                libelle=libelle, isin=isin, ticker_fichier=ticker,
                taille=taille if taille is not None else lire_nombre(cellule(ligne, MONTANT)),
                quantite=lire_nombre(cellule(ligne, QUANTITE)), prix=lire_nombre(cellule(ligne, PRIX)))
            # Notes de bas de tableau : ni identifiant ni chiffre.
            if isin is None and ticker is None and li.taille is None and li.quantite is None:
                continue
            if _liquidites(libelle) and isin is None:
                li.ignoree = True
            out.append(li)
        return out
    # Sans en-tête : le premier texte est le libellé, le dernier nombre le poids (ou le montant).
    for ligne in tableau:
        textes, nombre, isin = [], None, None
        for c in ligne:
            if not c:
                continue
            n = lire_nombre(c)
            if n is not None:
                nombre = n
            elif _ISIN.match(c.upper()):
                isin = c.upper()
            else:
                textes.append(c)
        libelle = textes[0] if textes else isin
        if libelle is None or _total(libelle):
            continue
        ticker = libelle.upper() if re.fullmatch(r"[A-Za-z0-9]{1,6}([.-][A-Za-z]{1,3})?", libelle) else None
        li = LigneImportee(libelle=libelle, isin=isin, ticker_fichier=ticker, taille=nombre)
        if _liquidites(libelle) and isin is None:
            li.ignoree = True
        out.append(li)
    return out


# ---------------------------------------------------------------------------------------------- reconnaissance

# Pays d'immatriculation d'après les deux lettres de l'ISIN, dans les noms de l'univers.
PAYS_ISIN = {
    "US": "États-Unis", "FR": "France", "DE": "Allemagne", "GB": "Royaume-Uni", "CH": "Suisse", "NL": "Pays-Bas",
    "IT": "Italie", "ES": "Espagne", "SE": "Suède", "DK": "Danemark", "NO": "Norvège", "FI": "Finlande",
    "BE": "Belgique", "IE": "Irlande", "AT": "Autriche", "PT": "Portugal", "PL": "Pologne", "GR": "Grèce",
    "LU": "Luxembourg", "JE": "Jersey", "GG": "Guernesey", "BM": "Bermudes", "KY": "Îles Caïmans", "CA": "Canada",
    "IL": "Israël", "CN": "Chine", "HK": "Hong Kong", "TW": "Taïwan", "SG": "Singapour", "JP": "Japon",
    "KR": "Corée du Sud", "IN": "Inde", "AU": "Australie", "BR": "Brésil", "AR": "Argentine", "UY": "Uruguay",
    "MX": "Mexique", "CY": "Chypre",
}

# Mots qui ne distinguent pas une société d'une autre.
_VIDES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "cie", "sa", "se", "plc", "ag", "nv", "spa",
    "ltd", "limited", "holding", "holdings", "group", "groupe", "the", "de", "du", "des", "la", "le", "les", "et",
    "and", "of", "cl", "class", "classe", "ord", "shs", "reg", "registered", "act", "action", "actions", "adr",
    "sca", "asa", "ab", "as", "oyj", "bv", "kgaa", "llc", "lp", "publ", "a", "b", "c", "com", "new", "eo", "ns",
}

# Fonds et matières premières : à ne pas confondre avec une société (« Amundi MSCI World » n'est pas Amundi).
_MOTS_FONDS = re.compile(
    r"\b(etf|etc|etn|ucits|sicav|fcp|opcvm|ishares|xtrackers|lyxor|vanguard|spdr|wisdomtree|invesco|vaneck|"
    r"global x|amundi (msci|index|stoxx|s ?p|nasdaq|etf)|msci|s ?p 500|stoxx|nasdaq 100|physical|tracker)\b")


def _mots(nom: str) -> set[str]:
    return {m for m in normaliser(nom).split(" ") if m and m not in _VIDES}


def _meme_mot(a: str, b: str) -> bool:
    return a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)))


def ressemblance(a: str, b: str) -> float:
    """Ressemblance de deux noms entre 0 et 1 : part des mots significatifs communs."""
    ma, mb = _mots(a), _mots(b)
    if not ma or not mb:
        return 0.0
    communs = sum(1 for x in ma if any(_meme_mot(x, y) for y in mb))
    return communs / max(len(ma), len(mb))


class Reconnaissance:
    """`valeurs` : index ticker, colonnes nom, pays et fonds (booléen). `correspondances` : choix déjà faits
    (clé de ligne -> ticker, '' pour une ligne gardée hors des données)."""

    def __init__(self, valeurs: pd.DataFrame, correspondances: dict[str, str] | None = None):
        self.valeurs = valeurs
        self.correspondances = correspondances or {}
        self._par_base: dict[str, list[str]] = {}
        for t in valeurs.index:
            base = t.split(".")[0]
            for cle in {base.replace("-", "."), base}:
                self._par_base.setdefault(cle, []).append(t)

    def _par_pays(self, candidats: list[str], pays: str | None) -> str | None:
        if len(candidats) == 1:
            return candidats[0]
        meme = [t for t in candidats if pays is not None and self.valeurs.at[t, "pays"] == pays]
        return meme[0] if len(meme) == 1 else None

    def reconnaitre(self, li: LigneImportee) -> None:
        deja = self.correspondances.get(li.cle)
        if deja is not None:
            li.ticker = deja if deja and deja in self.valeurs.index else None
            li.confiance = Confiance.SURE if li.ticker else Confiance.AUCUNE
            return
        pays = PAYS_ISIN.get(li.isin[:2]) if li.isin else None
        for t in [li.ticker_fichier, li.libelle.upper()]:
            if t and t in self.valeurs.index:
                li.ticker, li.confiance = t, Confiance.SURE
                return
        # Ticker sans la place de cotation (« AI » pour « AI.PA ») : départagé par le pays de l'ISIN.
        base = re.split(r"[.:\s]", li.ticker_fichier)[0] if li.ticker_fichier else None
        if base:
            t = self._par_pays(list(dict.fromkeys(self._par_base.get(base, []))), pays)
            if t is not None:
                li.ticker = t
                li.confiance = Confiance.SURE if pays and self.valeurs.at[t, "pays"] == pays else Confiance.PROBABLE
                return
        fonds = _MOTS_FONDS.search(normaliser(li.libelle)) is not None
        meilleure, score, second = None, 0.0, 0.0
        for t, v in self.valeurs.iterrows():
            if fonds != bool(v["fonds"]):
                continue
            s = ressemblance(li.libelle, str(v["nom"]))
            if s == 0:
                continue
            if pays is not None:
                s += 0.15 if v["pays"] == pays else -0.15
            if s > score:
                second, score, meilleure = score, s, t
            elif s > second:
                second = s
        if meilleure is not None and score >= 0.5:
            li.ticker = meilleure
            li.confiance = Confiance.SURE if score >= 0.99 and score - second >= 0.3 else Confiance.PROBABLE


# ---------------------------------------------------------------------------------------------- poids

def calculer_poids(lignes: list[LigneImportee], cours_eur: dict[str, float] | None = None) -> str:
    """Poids en % des lignes retenues : poids ou montants du fichier, sinon quantités × cours (du fichier, sinon
    cours en euros des données), sinon parts égales. Renvoie la méthode employée."""
    cours_eur = cours_eur or {}
    retenues = [li for li in lignes if not li.ignoree]
    tailles: dict[int, float] = {}
    if any(li.taille is not None and li.taille > 0 for li in retenues):
        methode = "poids ou montants du fichier"
        for li in retenues:
            tailles[id(li)] = li.taille or 0.0
    elif any(li.quantite is not None for li in retenues):
        methode = "quantités × derniers cours"
        for li in retenues:
            cours = li.prix if li.prix is not None else (cours_eur.get(li.ticker) if li.ticker else None)
            tailles[id(li)] = li.quantite * cours if li.quantite is not None and cours is not None else 0.0
    else:
        methode = "parts égales (le fichier ne donne ni poids ni montant)"
        for li in retenues:
            tailles[id(li)] = 1.0
    total = sum(x for x in tailles.values() if x > 0)
    for li in lignes:
        t = tailles.get(id(li), 0.0)
        li.poids = t / total * 100 if total > 0 and t > 0 else 0.0
    return methode


def importer(textes: list[str] | str, valeurs: pd.DataFrame | None = None,
             cours_eur: dict[str, float] | None = None,
             correspondances: dict[str, str] | None = None) -> ResultatImport:
    """Tout le trajet : texte(s) -> lignes reconnues et pondérées. Plusieurs textes (un par compte) s'ajoutent."""
    lignes: list[LigneImportee] = []
    for texte in [textes] if isinstance(textes, str) else textes:
        lignes += lignes_du_tableau(lire_tableau(texte))
    if valeurs is not None and not valeurs.empty:
        r = Reconnaissance(valeurs, correspondances)
        for li in lignes:
            r.reconnaitre(li)
    return ResultatImport(lignes, calculer_poids(lignes, cours_eur))


def decoder_texte(octets: bytes) -> str:
    """Texte d'un fichier : UTF-8, sinon l'encodage Windows des exports de courtiers français."""
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        return octets.decode("cp1252", errors="replace")


def est_classeur(octets: bytes) -> bool:
    """Classeur Excel récent (.xlsx, .xlsm) : une archive zip, qui commence par « PK »."""
    return octets[:2] == b"PK"


def _cellule(v) -> str:
    """Valeur d'une cellule Excel en texte lisible par lire_nombre et lire_tableau."""
    if v is None or isinstance(v, bool):
        return ""
    if isinstance(v, float):
        if not math.isfinite(v):
            return ""
        # Sans notation scientifique (1e-05), que lire_nombre ne lit pas.
        return f"{v:.10f}".rstrip("0").rstrip(".")
    if isinstance(v, int):
        return str(v)
    if not isinstance(v, str):  # dates et heures : rien à voir avec une position
        return ""
    s = " ".join(v.split())  # ni tabulation ni retour à la ligne dans une cellule
    if s.startswith("#"):  # erreurs de formule : #N/A, #REF!…
        return ""
    return s.replace('"', "”")  # un guillemet droit ouvrirait un champ entre guillemets


def textes_classeur(octets: bytes) -> list[str]:
    """Les feuilles d'un classeur Excel en texte tabulé, prêt pour lire_tableau.

    Seules les feuilles où une ligne d'en-tête est reconnue sont gardées (une feuille de synthèse ou de graphiques
    ne donnerait que des lignes parasites) ; à défaut, toutes les feuilles non vides. Les formules donnent leur
    dernière valeur calculée par Excel. Lève ValueError si le fichier n'est pas un classeur lisible."""
    import io
    import zipfile

    from openpyxl import load_workbook

    try:
        classeur = load_workbook(io.BytesIO(octets), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError) as e:
        raise ValueError("classeur Excel illisible (protégé par un mot de passe, ou abîmé)") from e
    feuilles: list[tuple[bool, str]] = []
    try:
        for feuille in classeur.worksheets:
            lignes = []
            for rang in feuille.iter_rows(values_only=True):
                cellules = [_cellule(v) for v in rang]
                while cellules and not cellules[-1]:
                    cellules.pop()
                if any(cellules):
                    lignes.append("\t".join(cellules))
            if lignes:
                texte = "\n".join(lignes)
                feuilles.append((en_tete(lire_tableau(texte)) is not None, texte))
    finally:
        classeur.close()
    avec_en_tete = [t for ok, t in feuilles if ok]
    return avec_en_tete or [t for _, t in feuilles]


def textes_fichier(octets: bytes) -> list[str]:
    """Texte(s) d'un fichier déposé : classeur Excel (une entrée par feuille utile), sinon CSV ou texte."""
    if est_classeur(octets):
        return textes_classeur(octets)
    if octets[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ValueError("ancien format Excel (.xls) : ouvrez-le dans Excel et enregistrez-le au format .xlsx ou CSV")
    return [decoder_texte(octets)]


def lignes_modele(resultat: ResultatImport, existant: pd.DataFrame, enveloppe: str,
                  noms: dict[str, str] | None = None) -> pd.DataFrame:
    """Nouveau portefeuille_modele.csv : une ligne par valeur reconnue (doublons de deux comptes additionnés).
    Les colonnes déjà remplies pour une valeur (poche, thèse, condition de vente…) sont conservées."""
    poids: dict[str, float] = {}
    for li in resultat.retenues:
        if li.ticker and li.poids > 0:
            poids[li.ticker] = poids.get(li.ticker, 0.0) + li.poids
    colonnes = ["ticker", "nom", "enveloppe", "poche", "conviction", "poids_cible", "these", "risque_principal",
                "condition_vente", "alternative"]
    anciennes = existant.reset_index() if existant.index.name == "ticker" else existant
    colonnes += [c for c in anciennes.columns if c not in colonnes]
    deja = anciennes.set_index("ticker") if "ticker" in anciennes.columns else pd.DataFrame()
    rangs = []
    for t, p in sorted(poids.items(), key=lambda x: -x[1]):
        r = {c: "" for c in colonnes}
        if t in deja.index:
            r.update({c: ("" if pd.isna(v) else v) for c, v in deja.loc[t].items() if c in r})
        r["ticker"], r["poids_cible"] = t, round(p, 2)
        r["nom"] = r["nom"] or (noms or {}).get(t, t)
        r["enveloppe"] = r["enveloppe"] or enveloppe
        r["poche"] = r["poche"] or "Cœur"
        rangs.append(r)
    return pd.DataFrame(rangs, columns=colonnes)
