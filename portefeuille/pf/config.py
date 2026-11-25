"""Chemins, fichiers de configuration et constantes partagées."""
from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent  # le code
# Les données (config/, data/, theses/, rapports/, profil/) sont à côté du code, ou dans le dossier que désigne
# la variable d'environnement PF_DOSSIER (par exemple le jeu d'essai des tests).
DOSSIER = Path(os.environ["PF_DOSSIER"]).resolve() if os.environ.get("PF_DOSSIER") else ROOT
CONFIG_DIR = DOSSIER / "config"
DATA_DIR = DOSSIER / "data"
CACHE_DIR = DATA_DIR / "cache"
FUND_DIR = CACHE_DIR / "fondamentaux"
THESES_DIR = DOSSIER / "theses"
RAPPORTS_DIR = DOSSIER / "rapports"

# Fichiers personnels (portefeuille, listes de suivi, règles de vente…) : dossier `profil/`, exclu du dépôt,
# ou celui que désigne la variable d'environnement PF_PROFIL. Sur une installation neuve, il est créé à partir
# de `profil.exemple/` (données fictives, versionnées).
PROFIL_EXEMPLE_DIR = ROOT / "profil.exemple"
PROFIL_DIR = Path(os.environ["PF_PROFIL"]) if os.environ.get("PF_PROFIL") else DOSSIER / "profil"


def preparer_profil(dossier: Path = PROFIL_DIR, exemple: Path = PROFIL_EXEMPLE_DIR) -> bool:
    """Crée le profil à partir de l'exemple s'il n'existe pas encore. Ne touche jamais à un profil existant."""
    if dossier.exists() or not exemple.exists():
        return False
    shutil.copytree(exemple, dossier)
    return True


preparer_profil()

UNIVERS_CSV = CONFIG_DIR / "univers.csv"
STRATEGIE_JSON = CONFIG_DIR / "strategie.json"
# Réglages personnels (adresse de contact SEC…), à ne pas partager avec le reste du dossier.
PRIVE_JSON = PROFIL_DIR / "prive.json"
# Holdings, financières non reconnues par Yahoo, sociétés dont la trésorerie appartient à leurs clients.
CAS_PARTICULIERS_CSV = CONFIG_DIR / "cas_particuliers.csv"
MODELE_CSV = PROFIL_DIR / "portefeuille_modele.csv"
# Sélection de 25 valeurs proposée par Claude le 29/10/2026, remplacée par le portefeuille réel.
SELECTION_CLAUDE_CSV = PROFIL_DIR / "selection_claude_2026-10.csv"
# Valeurs écartées pour l'instant, avec leur condition d'entrée (remplie lors des analyses).
SURVEILLANCE_CSV = PROFIL_DIR / "surveillance.csv"
TRANSACTIONS_CSV = DATA_DIR / "transactions.csv"
SAUVEGARDES_DIR = DATA_DIR / "sauvegardes"
PRICES_PARQUET = CACHE_DIR / "prix.parquet"
FX_PARQUET = CACHE_DIR / "fx.parquet"
CONTROLES_JSON = CACHE_DIR / "controles.json"
SEC_DIR = CACHE_DIR / "sec"
METRICS_PARQUET = CACHE_DIR / "indicateurs.parquet"
# Paramètres de valorisation utilisés pour le dernier calcul : s'ils changent, il faut recalculer.
METRICS_META = CACHE_DIR / "indicateurs.meta.json"

# ETF capitalisants cotés en EUR : performance dividendes réinvestis, directement comparable.
BENCHMARKS = {
    "IWDA.AS": "MSCI World (iShares, EUR)",
    "CW8.PA": "MSCI World éligible PEA (Amundi)",
    "EXSA.DE": "STOXX Europe 600",
    "SXR8.DE": "S&P 500 (en EUR)",
    "SXRV.DE": "Nasdaq 100 (en EUR)",
}
BENCHMARK_DEFAUT = "IWDA.AS"
# Fondamentaux renouvelés par mise à jour normale : par roulement, vos lignes d'abord (Yahoo limite le débit).
# Au moins 100, et assez pour relire tout l'univers en 4 mises à jour normales (une par semaine en automatique) :
# une fiche a ainsi au plus un mois environ, et aucune publication trimestrielle n'est manquée.
RENOUVELLEMENT_FONDAMENTAUX = 100
CYCLE_FONDAMENTAUX = 4


def renouvellement(nb_valeurs: int) -> int:
    return max(RENOUVELLEMENT_FONDAMENTAUX, -(-nb_valeurs // CYCLE_FONDAMENTAUX))


def etalement(cle: str) -> float:
    """Nombre stable entre 0 et 1 propre à une valeur. Multiplier un délai de renouvellement par (0,5 + ce
    nombre) répartit les rafraîchissements sur les jours, au lieu de tout relire le même jour."""
    import zlib

    return (zlib.crc32(cle.encode("utf-8")) % 10_000) / 10_000

# Codes de cotation exprimés en centièmes de la devise de référence.
SUBUNITS = {"GBp": ("GBP", 0.01), "GBX": ("GBP", 0.01), "ZAc": ("ZAR", 0.01), "ILA": ("ILS", 0.01)}

SECTEURS = [
    "Logiciels & IT",
    "Semi-conducteurs",
    "Internet & Médias",
    "Santé",
    "Industrie & Électrification",
    "Aéronautique & Défense",
    "Luxe & Consommation",
    "Consommation de base",
    "Distribution",
    "Services financiers",
    "Assurance",
    "Matériaux & Chimie",
    "Services aux entreprises & Données",
    "Infrastructures & Énergie",
    "Fonds & matières premières",
    "Banques",
    "Immobilier",
    "Télécoms",
]
# ETF et ETC : suivis sur leurs cours, sans filtres ni score fondamentaux.
SECTEUR_FONDS = "Fonds & matières premières"


def ecriture_atomique(path: Path, ecrire: Callable[[Path], None]) -> None:
    """Écrit dans un fichier temporaire du même dossier, puis le renomme.

    Une interruption (fenêtre fermée pendant une mise à jour, coupure) laisse l'ancien fichier intact
    au lieu d'un fichier tronqué que plus rien ne saurait relire. Sous Windows, le renommage échoue tant
    qu'un autre programme lit le fichier (application ouverte, antivirus) : on réessaie quelques secondes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        ecrire(tmp)
        for essai in range(20):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if essai == 19:
                    raise
                time.sleep(0.25)
    finally:
        if tmp.exists():
            tmp.unlink()


def ecrire_texte(path: Path, texte: str) -> None:
    ecriture_atomique(path, lambda p: p.write_text(texte, encoding="utf-8"))


def ecrire_json(path: Path, obj, **kw) -> None:
    ecrire_texte(path, json.dumps(obj, ensure_ascii=False, **kw))


def lire_json(path: Path, defaut=None):
    """Contenu d'un fichier JSON, ou `defaut` s'il est absent ou illisible."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defaut


def read_csv_fr(path: Path, numeric: tuple[str, ...] = ()) -> pd.DataFrame:
    """Lit un CSV au format « Excel français » (séparateur ;, UTF-8) en tolérant la virgule décimale."""
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    for col in df.columns:
        df[col] = df[col].str.strip()
    for col in numeric:
        if col in df.columns:
            cleaned = df[col].str.replace(" ", "", regex=False).str.replace(" ", "", regex=False)
            df[col] = pd.to_numeric(cleaned.str.replace(",", ".", regex=False), errors="coerce")
    return df


def write_csv_fr(df: pd.DataFrame, path: Path) -> None:
    ecriture_atomique(path, lambda p: df.to_csv(p, sep=";", encoding="utf-8-sig", index=False))


def load_universe() -> pd.DataFrame:
    df = read_csv_fr(UNIVERS_CSV)
    return df.drop_duplicates("ticker").set_index("ticker")


def load_strategy() -> dict:
    with open(STRATEGIE_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_strategy(strategy: dict) -> None:
    ecrire_json(STRATEGIE_JSON, strategy, indent=2)


def load_prive() -> dict:
    return lire_json(PRIVE_JSON, {}) or {}


def load_cas_particuliers() -> dict[str, set[str]]:
    """{catégorie: tickers} : « holding », « financiere », « tresorerie_clients »."""
    out: dict[str, set[str]] = {"holding": set(), "financiere": set(), "tresorerie_clients": set()}
    if CAS_PARTICULIERS_CSV.exists():
        for _, r in read_csv_fr(CAS_PARTICULIERS_CSV).iterrows():
            out.setdefault(r["categorie"], set()).add(r["ticker"])
    return out


def load_model_portfolio(path: Path = MODELE_CSV) -> pd.DataFrame:
    """Poids cibles du portefeuille (par défaut le portefeuille réel ; `path` pour une autre sélection)."""
    if not path.exists():
        return pd.DataFrame(columns=["ticker", "poids_cible"]).set_index("ticker")
    df = read_csv_fr(path, numeric=("poids_cible", "conviction"))
    return df.set_index("ticker")


def fund_tickers() -> set[str]:
    u = load_universe()
    return set(u.index[u["secteur"] == SECTEUR_FONDS])


def all_tracked_tickers() -> list[str]:
    """Univers + portefeuille modèle + lignes détenues : tout ce dont l'outil a besoin."""
    tickers = list(load_universe().index)
    tickers += [t for t in load_model_portfolio().index if t not in tickers]
    if TRANSACTIONS_CSV.exists():
        tx = read_csv_fr(TRANSACTIONS_CSV)
        if "ticker" in tx.columns:
            tickers += [t for t in tx["ticker"].unique() if t and t not in tickers]
    return tickers
