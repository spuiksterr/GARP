"""Version autonome : l'outil installé par GARP-Setup, sans Python ni projet sur le poste, alimenté par GitHub.

La construction (.github/workflows/app.yml) pose `autonome.json` à côté du code, avec le numéro de version.
GARP.pyw appelle alors `preparer()` avant tout le reste :
- les données vont dans %LOCALAPPDATA%\\Climax\\donnees (PF_DOSSIER), hors du dossier d'installation ;
- la configuration livrée (univers, stratégie…) y est copiée au premier lancement ;
- PF_AUTONOME=1 : la barre latérale remplace les mises à jour Yahoo et SEC par « Données de la nuit ».

Les données viennent de la release « donnees » du dépôt public (archive `garp-outil.zip`, préparée chaque nuit par
`pf export-outil`) : aucun jeton n'est nécessaire. Un jeton GitHub facultatif (lecture seule) lève la limite de
GitHub sur les requêtes anonymes ; il est chiffré par Windows pour l'utilisateur courant (DPAPI) et n'est envoyé
qu'à api.github.com : les téléchargements sont redirigés vers un stockage de GitHub, suivi sans jeton.
Les fichiers personnels (profil, journal des transactions, sauvegardes) ne sont jamais remplacés.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

DEPOT = "spuiksterr/GARP"
RELEASE_DONNEES = "donnees"
ARCHIVE = "garp-outil.zip"
MARQUEUR = "autonome.json"
API = "https://api.github.com"
# Contenu admis dans l'archive : rien d'autre n'est écrit sur le poste.
PREFIXES = ("config/", "data/cache/", "data/historique/")
# Réglages que l'utilisateur peut changer dans l'outil : livrés une fois, jamais écrasés ensuite.
CONFIG_PERSONNELLE = {"config/strategie.json"}

URL_CREATION_JETON = "https://github.com/settings/personal-access-tokens/new?" + urllib.parse.urlencode({
    "name": "G.A.R.P", "description": "Lecture des données de G.A.R.P", "target_name": DEPOT.split("/")[0],
    "expires_in": "365", "contents": "read"})


class ErreurGitHub(Exception):
    pass


# ---------------------------------------------------------------------------------------------- environnement

def actif() -> bool:
    return os.environ.get("PF_AUTONOME") == "1"


def dossier_local() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Climax"  # nom d'origine du projet : ne pas changer, les données déjà installées y sont


def lire_marqueur(racine: Path) -> dict | None:
    try:
        return json.loads((racine / MARQUEUR).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def preparer(racine: Path) -> bool:
    """Prépare l'environnement de la version installée ; sans effet (False) dans le projet de développement."""
    if lire_marqueur(racine) is None:
        return False
    os.environ["PF_AUTONOME"] = "1"
    os.environ.setdefault("PF_DOSSIER", str(dossier_local() / "donnees"))
    dossier = Path(os.environ["PF_DOSSIER"])
    for nom in ("data", "theses", "rapports"):
        (dossier / nom).mkdir(parents=True, exist_ok=True)
    livree = racine / "config"
    if livree.is_dir():
        for f in livree.iterdir():
            cible = dossier / "config" / f.name
            if f.is_file() and not cible.exists():
                cible.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, cible)
    return True


def version_installee() -> int | None:
    from .config import ROOT

    m = lire_marqueur(ROOT)
    try:
        return int(m["version"]) if m else None
    except (KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------- jeton (DPAPI)

def _fichier_jeton() -> Path:
    return dossier_local() / "jeton.dat"


def _dpapi(octets: bytes, chiffrer: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    tampon = ctypes.create_string_buffer(octets, len(octets))
    entree, sortie = Blob(len(octets), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char))), Blob()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    fonction = crypt32.CryptProtectData if chiffrer else crypt32.CryptUnprotectData
    if chiffrer:
        ok = fonction(ctypes.byref(entree), "G.A.R.P", None, None, None, 0, ctypes.byref(sortie))
    else:
        ok = fonction(ctypes.byref(entree), None, None, None, None, 0, ctypes.byref(sortie))
    if not ok:
        raise OSError("chiffrement Windows indisponible")
    try:
        return ctypes.string_at(sortie.pbData, sortie.cbData)
    finally:
        kernel32.LocalFree(sortie.pbData)


def jeton() -> str | None:
    try:
        return _dpapi(_fichier_jeton().read_bytes(), chiffrer=False).decode("utf-8") or None
    except (OSError, ValueError):
        return None


def enregistrer_jeton(valeur: str) -> None:
    chemin = _fichier_jeton()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(_dpapi(valeur.strip().encode("utf-8"), chiffrer=True))


def oublier_jeton() -> None:
    _fichier_jeton().unlink(missing_ok=True)


# ---------------------------------------------------------------------------------------------- GitHub

def _ouvrir(chemin: str, jeton_: str | None, accept: str = "application/vnd.github+json", timeout: float = 30):
    req = urllib.request.Request(f"{API}/repos/{DEPOT}{chemin}", headers={
        "Accept": accept, "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "GARP"})
    # Dépôt public : sans jeton, requête anonyme. En-tête « non redirigé » : le jeton ne suit pas la redirection
    # vers le stockage des fichiers.
    if jeton_:
        req.add_unredirected_header("Authorization", f"Bearer {jeton_}")
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ErreurGitHub("Jeton refusé par GitHub : il a peut-être expiré. Saisissez-en un nouveau.") from e
        if e.code == 404:
            raise ErreurGitHub("Introuvable sur GitHub : dépôt GARP ou données de la nuit absents.") from e
        if e.code in (403, 429) and not jeton_:
            raise ErreurGitHub("GitHub limite les requêtes sans jeton (60 par heure) : réessayez plus tard, ou "
                               "ajoutez un jeton (bas de la barre latérale).") from e
        raise ErreurGitHub(f"GitHub a répondu {e.code}.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErreurGitHub("GitHub injoignable : vérifiez la connexion à Internet.") from e


def _json(chemin: str, jeton_: str | None):
    with _ouvrir(chemin, jeton_, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def verifier_jeton(jeton_: str) -> None:
    """Lève ErreurGitHub si le jeton n'ouvre pas le dépôt."""
    _json("", jeton_)


def archive_distante(jeton_: str | None) -> dict:
    """Archive de la nuit dans la release « donnees » : identifiant, taille, date de publication."""
    rel = _json(f"/releases/tags/{RELEASE_DONNEES}", jeton_)
    for a in rel.get("assets", []):
        if a.get("name") == ARCHIVE:
            return {"id": a["id"], "taille": a.get("size", 0), "date": a.get("updated_at", "")}
    raise ErreurGitHub("Les données de la nuit ne sont pas encore publiées sur GitHub.")


def _etat_local_fichier() -> Path:
    from .config import DATA_DIR

    return DATA_DIR / "telechargement.json"


def etat_local() -> dict:
    try:
        return json.loads(_etat_local_fichier().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _telecharger(chemin: str, jeton_: str | None, vers: Path, taille: int,
                 progression: Callable[[float], None] | None = None) -> None:
    with _ouvrir(chemin, jeton_, accept="application/octet-stream", timeout=60) as r, open(vers, "wb") as f:
        total = int(r.headers.get("Content-Length") or taille or 0)
        lu = 0
        while morceau := r.read(1 << 20):
            f.write(morceau)
            lu += len(morceau)
            if progression and total:
                progression(min(lu / total, 1.0))


def installer_archive(zip_path: Path, dossier: Path) -> int:
    """Copie le contenu admis de l'archive dans `dossier` (fichier par fichier, remplacement atomique).
    Renvoie le nombre de fichiers écrits. Lève ValueError si l'archive n'a pas la forme attendue."""
    base = dossier.resolve()
    with zipfile.ZipFile(zip_path) as z:
        noms = [n for n in z.namelist() if not n.endswith("/")]
        if "data/cache/indicateurs.parquet" not in noms:
            raise ValueError("archive incomplète : indicateurs absents")
        for n in noms:
            if ".." in Path(n).parts or n.startswith(("/", "\\")) or "\\" in n or not n.startswith(PREFIXES):
                raise ValueError(f"archive refusée : {n}")
            if not (base / n).resolve().is_relative_to(base):
                raise ValueError(f"archive refusée : {n}")
        temp = Path(tempfile.mkdtemp(prefix=".maj-", dir=dossier))
        try:
            z.extractall(temp, noms)
            ecrits = 0
            for n in noms:
                cible = dossier / n
                if n in CONFIG_PERSONNELLE and cible.exists():
                    continue
                cible.parent.mkdir(parents=True, exist_ok=True)
                for essai in range(5):  # Windows verrouille parfois un fichier un instant
                    try:
                        os.replace(temp / n, cible)
                        break
                    except PermissionError:
                        if essai == 4:
                            raise
                        time.sleep(0.5)
                ecrits += 1
            return ecrits
        finally:
            shutil.rmtree(temp, ignore_errors=True)


def telecharger_donnees(jeton_: str | None, progression: Callable[[float], None] | None = None) -> dict:
    """Télécharge et installe les données de la nuit. Renvoie l'état enregistré (date de l'archive…)."""
    from .config import DATA_DIR

    a = archive_distante(jeton_)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, nom = tempfile.mkstemp(suffix=".zip", dir=DATA_DIR)
    os.close(fd)
    zip_path = Path(nom)
    try:
        _telecharger(f"/releases/assets/{a['id']}", jeton_, zip_path, a["taille"], progression)
        return _installer_et_noter(zip_path, a)
    finally:
        zip_path.unlink(missing_ok=True)


def _installer_et_noter(zip_path: Path, archive: dict) -> dict:
    from .config import DOSSIER, ecrire_json

    fichiers = installer_archive(zip_path, DOSSIER)
    etat = {"archive": archive["date"], "telecharge_le": time.strftime("%Y-%m-%dT%H:%M:%S"), "fichiers": fichiers}
    ecrire_json(_etat_local_fichier(), etat, indent=1)
    return etat


def donnees_a_jour(jeton_: str | None) -> tuple[bool, dict]:
    """(vrai si l'archive locale est la dernière publiée, archive distante)."""
    a = archive_distante(jeton_)
    return etat_local().get("archive") == a["date"], a


# ---------------------------------------------------------------------------------------------- en arrière-plan

@dataclass
class TacheNuit:
    """Recherche et téléchargement des données de la nuit dans un fil à part : l'interface s'ouvre tout de suite
    avec les données déjà installées, puis propose de charger les nouvelles une fois téléchargées. Une seule tâche
    par processus (ui la garde avec st.cache_resource) ; le fil ne touche jamais à l'interface."""
    statut: str = "inactif"  # inactif, verification, telechargement, pret, a_jour, erreur
    progression: float = 0.0
    message: str = ""
    archive: dict | None = None
    fichier: Path | None = None
    version: dict | None = None
    verrou: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def en_cours(self) -> bool:
        return self.statut in ("verification", "telechargement")


def _fichier_attente() -> Path:
    """Archive téléchargée, en attente d'installation (gardée si l'on ferme l'outil avant de la charger)."""
    from .config import DATA_DIR

    return DATA_DIR / "nuit_en_attente.zip"


def chercher_en_arriere_plan(tache: TacheNuit, jeton_: str | None) -> threading.Thread | None:
    """Lance la recherche (nouvelle version du logiciel, nouvelles données) et le téléchargement ; sans effet si
    une recherche est déjà en cours. Renvoie le fil lancé."""
    from .config import ecrire_json, lire_json

    with tache.verrou:
        if tache.en_cours():
            return None
        tache.statut, tache.progression, tache.message = "verification", 0.0, ""

    def travail() -> None:
        try:
            try:
                tache.version = derniere_version(jeton_)
            except ErreurGitHub:
                pass
            a = archive_distante(jeton_)
            if etat_local().get("archive") == a["date"]:
                tache.statut = "a_jour"
                return
            tache.archive = a
            vers = _fichier_attente()
            if not (vers.exists() and lire_json(vers.with_suffix(".json")) == a):
                tache.statut = "telechargement"
                vers.parent.mkdir(parents=True, exist_ok=True)
                partiel = vers.with_suffix(".part")
                _telecharger(f"/releases/assets/{a['id']}", jeton_, partiel, a["taille"],
                             lambda x: setattr(tache, "progression", x))
                os.replace(partiel, vers)
                ecrire_json(vers.with_suffix(".json"), a)
            tache.fichier, tache.progression, tache.statut = vers, 1.0, "pret"
        except (ErreurGitHub, OSError) as e:
            tache.statut, tache.message = "erreur", str(e)

    fil = threading.Thread(target=travail, name="donnees-de-la-nuit", daemon=True)
    fil.start()
    return fil


def installer_en_attente(tache: TacheNuit) -> dict:
    """Installe l'archive téléchargée en arrière-plan (quelques secondes) et la supprime."""
    if tache.statut != "pret" or tache.fichier is None or tache.archive is None:
        raise ValueError("aucune archive en attente")
    etat = _installer_et_noter(tache.fichier, tache.archive)
    tache.fichier.unlink(missing_ok=True)
    tache.fichier.with_suffix(".json").unlink(missing_ok=True)
    tache.statut, tache.fichier = "a_jour", None
    return etat


# ---------------------------------------------------------------------------------------------- nouvelles versions

def _nom_installateur_valide(nom: str) -> bool:
    return bool(nom) and Path(nom).name == nom and nom.startswith("GARP-Setup") and nom.endswith(".exe")


def _sha256_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        while morceau := f.read(1 << 20):
            h.update(morceau)
    return h.hexdigest().lower()


def _lire_sha256sums(contenu: str, nom: str) -> str | None:
    for ligne in contenu.splitlines():
        parts = ligne.strip().split()
        if len(parts) >= 2 and parts[1].lstrip("*") == nom and len(parts[0]) == 64:
            try:
                int(parts[0], 16)
                return parts[0].lower()
            except ValueError:
                continue
    return None


def _sha256_attendu(jeton_: str | None, version: dict, nom: str) -> str | None:
    direct = str(version.get("sha256") or "").strip().lower()
    if direct.startswith("sha256:"):
        direct = direct[7:]
    if len(direct) == 64:
        return direct
    if version.get("sha256_id") is not None:
        with _ouvrir(f"/releases/assets/{version['sha256_id']}", jeton_,
                     accept="application/octet-stream", timeout=30) as r:
            texte = r.read().decode("utf-8", errors="replace")
        attendu = _lire_sha256sums(texte, nom)
        if not attendu:
            raise ErreurGitHub(f"Empreinte SHA-256 absente de SHA256SUMS.txt pour {nom}.")
        return attendu
    return None


def derniere_version(jeton_: str | None) -> dict | None:
    """Release app-b<n> la plus récente qui contient un installateur Windows : {numero, id, nom, taille, …}."""
    meilleure = None
    for rel in _json("/releases?per_page=30", jeton_):
        tag = str(rel.get("tag_name", ""))
        if not tag.startswith("app-b") or not tag[5:].isdigit():
            continue
        numero = int(tag[5:])
        assets = rel.get("assets", [])
        setup = next((a for a in assets if _nom_installateur_valide(str(a.get("name", "")))), None)
        if setup and (meilleure is None or numero > meilleure["numero"]):
            sums = next((a for a in assets if a.get("name") == "SHA256SUMS.txt"), None)
            digest = str(setup.get("digest") or "")
            meilleure = {
                "numero": numero, "id": setup["id"], "nom": setup["name"], "taille": setup.get("size", 0),
                "sha256": digest[7:].lower() if digest.lower().startswith("sha256:") else None,
                "sha256_id": sums["id"] if sums else None,
            }
    return meilleure


def installer_version(jeton_: str | None, version: dict, progression: Callable[[float], None] | None = None) -> None:
    """Télécharge l'installateur, vérifie son empreinte SHA-256 si publiée, puis le lance."""
    nom = str(version.get("nom", ""))
    if not _nom_installateur_valide(nom):
        raise ErreurGitHub(f"Nom d'installateur refusé : {nom!r}.")
    attendu = _sha256_attendu(jeton_, version, nom)
    vers = Path(tempfile.gettempdir()) / nom
    partiel = vers.with_suffix(".exe.part")
    try:
        _telecharger(f"/releases/assets/{version['id']}", jeton_, partiel, version["taille"], progression)
        if attendu is not None and _sha256_fichier(partiel) != attendu:
            raise ErreurGitHub("Empreinte SHA-256 invalide : l'installateur téléchargé a été rejeté.")
        os.replace(partiel, vers)
    finally:
        partiel.unlink(missing_ok=True)
    options = {"creationflags": subprocess.DETACHED_PROCESS} if sys.platform == "win32" else {}
    subprocess.Popen([str(vers)], close_fds=True, **options)
