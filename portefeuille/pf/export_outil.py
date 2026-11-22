"""Archive des données pour la version autonome de l'outil (pf/autonome.py) : `pf export-outil --vers <dossier>`.

Préparée chaque nuit par le flux « Données de l'application », publiée dans la release « donnees ». Elle contient
la configuration (univers, stratégie…), le cache calculé (cours, fondamentaux, indicateurs, comptes SEC et ESEF,
grands investisseurs) et l'historique des scores. Rien du profil ni du journal des transactions : sur les serveurs
de GitHub, le profil est celui d'exemple, et ces fichiers ne sont de toute façon pas repris.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from .config import CACHE_DIR, CONFIG_DIR, DATA_DIR, DOSSIER

NOM = "garp-outil.zip"
# Formats déjà compressés : stockés tels quels, plus rapide sans perte de place.
DEJA_COMPRESSES = {".parquet", ".gz", ".zip"}
EXCLUS = {".tmp", ".lock"}


def fichiers() -> list[Path]:
    out = [f for f in sorted(CONFIG_DIR.glob("*")) if f.is_file()]
    for dossier in (CACHE_DIR, DATA_DIR / "historique"):
        if dossier.is_dir():
            out += [f for f in sorted(dossier.rglob("*")) if f.is_file() and f.suffix not in EXCLUS]
    return out


def exporter(vers: Path) -> Path:
    from .scoring import enregistrer_screener

    # Screener tout prêt (data/cache/screener.parquet et son empreinte) : la version installée s'ouvre sans le calculer.
    enregistrer_screener()
    vers.mkdir(parents=True, exist_ok=True)
    chemin = vers / NOM
    temp = chemin.with_suffix(".tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in fichiers():
            nom = f.relative_to(DOSSIER).as_posix()
            mode = zipfile.ZIP_STORED if f.suffix in DEJA_COMPRESSES else zipfile.ZIP_DEFLATED
            z.write(f, nom, compress_type=mode)
    temp.replace(chemin)
    return chemin
