"""Archive des données pour la version autonome de l'outil (pf/autonome.py) : `pf export-outil --vers <dossier>`.

Préparée chaque nuit par le flux « Données de l'application », publiée dans la release « donnees ». Elle contient
la configuration (univers, stratégie…), le cache calculé (cours, fondamentaux, indicateurs, comptes SEC et ESEF,
grands investisseurs) et l'historique des scores. Rien du profil ni du journal des transactions : sur les serveurs
de GitHub, le profil est celui d'exemple, et ces fichiers ne sont de toute façon pas repris.
"""
from __future__ import annotations

import time
import zipfile
from pathlib import Path

import pandas as pd

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


def prechauffer(sc: pd.DataFrame, minutes: float = 10, progress=print) -> dict:
    """Lit, dans un temps limité, les sources SEC des fiches (dirigeants, ventilation du chiffre d'affaires) pour les
    valeurs américaines éligibles, les mieux classées d'abord, avant l'archive de la nuit. Ce qui est en cache n'est
    pas relu : nuit après nuit, toutes les fiches se remplissent. Sans adresse de contact SEC, rien n'est lu."""
    from . import dirigeants, sec, ventilation

    if not sec.contact():
        return {"saute": "adresse de contact SEC absente"}
    fin = time.monotonic() + minutes * 60
    us = sc[(sc["statut"] == "Éligible") & ~sc.index.str.contains(r"\.")].sort_values("rang")
    res = {"dirigeants": 0, "ventilations": 0}
    limite = (pd.Timestamp.today() - pd.Timedelta(days=7)).date().isoformat()
    for t in us.index:
        if time.monotonic() > fin:
            break
        try:
            deja = dirigeants.en_cache(t)
            if deja is None or (deja.attrs.get("lu_le") or "") < limite:
                dirigeants.transactions(t)
                res["dirigeants"] += 1
            if not (ventilation.CACHE / f"{t}.json").exists():
                ventilation.ventilation(t, max_age_days=300)
                res["ventilations"] += 1
        except Exception as exc:  # une valeur illisible ne bloque pas les autres
            progress(f"  {t} : {str(exc)[:120]}")
    return res
