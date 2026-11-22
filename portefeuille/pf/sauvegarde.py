"""Sauvegarde des données personnelles, exclues de Git (ticket D-09).

Une archive zip datée de profil/, theses/, data/transactions.csv et data/historique/, déposée dans un dossier
choisi par le propriétaire : de préférence hors de ce disque, ou synchronisé (OneDrive…). Le dossier se règle par
`pf sauvegarde --vers DOSSIER` (une fois) ou par la clé `dossier_sauvegarde` de profil/prive.json ; il sert ensuite
à chaque mise à jour. Seules les GARDER dernières archives sont conservées.

Restaurer : décompresser l'archive dans le dossier portefeuille/ (elle reprend les chemins profil/, theses/, data/).
"""
from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, DOSSIER, PRIVE_JSON, PROFIL_DIR, THESES_DIR, ecrire_json, load_prive

PREFIXE = "climax-donnees-"
GARDER = 30


def elements() -> list[Path]:
    """Fichiers à sauvegarder, s'ils existent."""
    fichiers = []
    for dossier in (PROFIL_DIR, THESES_DIR, DATA_DIR / "historique"):
        if dossier.exists():
            fichiers += sorted(p for p in dossier.rglob("*") if p.is_file() and not p.name.endswith(".tmp"))
    tx = DATA_DIR / "transactions.csv"
    return fichiers + ([tx] if tx.exists() else [])


def dossier_configure() -> Path | None:
    d = load_prive().get("dossier_sauvegarde")
    return Path(d) if d else None


def memoriser_dossier(dossier: Path) -> None:
    """Enregistre le dossier dans profil/prive.json (sans toucher aux autres réglages)."""
    prive = load_prive()
    prive["dossier_sauvegarde"] = str(dossier)
    ecrire_json(PRIVE_JSON, prive)


def _arcname(p: Path) -> str:
    """Chemin dans l'archive, relatif au dossier de données (profil/…, theses/…, data/…)."""
    for base in (DOSSIER, PROFIL_DIR.parent, THESES_DIR.parent, DATA_DIR.parent):
        try:
            return p.relative_to(base).as_posix()
        except ValueError:
            continue
    return p.name


def creer(dossier: Path | None = None, maintenant: datetime | None = None) -> Path:
    """Crée l'archive du jour (remplace celle du même jour) et supprime les plus anciennes au-delà de GARDER."""
    dossier = Path(dossier or dossier_configure() or "")
    if not str(dossier) or str(dossier) == ".":
        raise ValueError("aucun dossier de sauvegarde : pf sauvegarde --vers DOSSIER")
    dossier.mkdir(parents=True, exist_ok=True)
    jour = (maintenant or datetime.now()).strftime("%Y-%m-%d")
    cible = dossier / f"{PREFIXE}{jour}.zip"
    tmp = cible.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in elements():
            z.write(p, _arcname(p))
    tmp.replace(cible)
    for ancienne in sorted(dossier.glob(f"{PREFIXE}*.zip"))[:-GARDER]:
        ancienne.unlink()
    return cible
