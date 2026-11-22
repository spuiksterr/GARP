"""Mise à jour complète, la même depuis la ligne de commande et depuis l'interface.

Téléchargements (fondamentaux, comptes SEC, cours, changes), calcul des indicateurs et des scores,
création des fiches de thèse manquantes, puis bilan lisible de ce qui s'est passé.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

import pandas as pd

from . import photos
from .config import CACHE_DIR, all_tracked_tickers, ecrire_json, lire_json, renouvellement
from .data import update_all
from .metrics import compute_all
from .scoring import build_screener
from .theses import ensure_thesis_files

JOURNAL_JSON = CACHE_DIR / "mises_a_jour.json"


def journal() -> dict:
    """Date des derniers passages : {"rapide": iso, "complete": iso}."""
    return lire_json(JOURNAL_JSON) or {}


def jours_depuis_complete() -> float | None:
    d = journal().get("complete")
    return (datetime.now() - datetime.fromisoformat(d)).total_seconds() / 86400 if d else None


def tout_mettre_a_jour(complet: bool = False, age: float = 7, progress: Callable[[str], None] = print,
                       rapide: bool = False) -> tuple[dict, pd.DataFrame]:
    """Renvoie le compte rendu de la mise à jour et le screener recalculé.

    Trois niveaux : `rapide` (cours, changes, sources annexes, puis calculs : chaque jour), normal (en plus,
    un quart des fiches de fondamentaux par roulement et les comptes SEC et ESEF à renouveler : chaque semaine) et
    `complet` (toutes les fiches retéléchargées).
    """
    debut = time.time()
    tickers = all_tracked_tickers()
    res = update_all(tickers, max_age_days=0 if complet else age, progress=progress,
                     max_refresh=None if complet else renouvellement(len(tickers)), rapide=rapide and not complet)
    if not res.get("rapide"):
        # Portefeuilles 13F des grands investisseurs : chaque gérant relu au plus une fois par semaine.
        from . import investisseurs
        progress("Portefeuilles 13F des grands investisseurs…")
        try:
            res["investisseurs"] = investisseurs.mettre_a_jour(progress=progress)
        except Exception as exc:  # SEC injoignable : le reste de la mise à jour reste valable
            res["investisseurs"] = {"erreur": str(exc)[:200]}
    t0 = time.time()
    progress("Calcul des indicateurs et des scores…")
    sc = build_screener(compute_all())
    res["theses_creees"] = ensure_thesis_files(sc)
    if not res.get("rapide"):  # une photo par semaine suffit à suivre les rangs
        res["photo"] = photos.enregistrer(sc)
    from . import sauvegarde
    if sauvegarde.dossier_configure():  # données personnelles, hors Git : copie datée dans le dossier choisi
        try:
            res["sauvegarde"] = str(sauvegarde.creer())
        except OSError as exc:  # dossier absent (disque débranché…) : la mise à jour reste valable
            res["sauvegarde_erreur"] = str(exc)
    res["durees"]["Indicateurs et scores"] = time.time() - t0
    res["duree_totale"] = time.time() - debut
    j = journal()
    j["rapide" if res.get("rapide") else "complete"] = datetime.now().isoformat(timespec="seconds")
    ecrire_json(JOURNAL_JSON, j)
    return res, sc


def _duree(secondes: float) -> str:
    s = int(round(secondes))
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def bilan(res: dict, sc: pd.DataFrame) -> list[str]:
    """Compte rendu en quelques lignes : fraîcheur, recoupement SEC, erreurs, valeurs sans cours."""
    if res.get("rapide"):
        lignes = [f"Mise à jour rapide : cours au {res['derniere_date']}, indicateurs recalculés "
                  "(fondamentaux et comptes inchangés)."]
    else:
        lignes = [f"Données à jour au {res['derniere_date']} : {res['fondamentaux_ok']} fiches rafraîchies, "
                  f"{res['fondamentaux_deja_a_jour']} déjà récentes."]
    if res.get("durees"):
        etapes = sorted(((k, v) for k, v in res["durees"].items() if v >= 1), key=lambda kv: -kv[1])
        lignes.append(f"Durée : {_duree(res.get('duree_totale', sum(res['durees'].values())))}"
                      + (" (" + ", ".join(f"{k.lower()} {_duree(v)}" for k, v in etapes) + ")" if etapes else "") + ".")
    if not res.get("rapide") and res.get("sec_saute"):
        lignes.append(f"Recoupement SEC sauté : {res['sec_saute']}.")
    elif not res.get("rapide") and "verif_sec" in sc.columns:
        v = sc["verif_sec"].value_counts()
        retard = int(sc["sec_retard"].fillna(False).astype(bool).sum()) if "sec_retard" in sc.columns else 0
        lignes.append(f"Recoupement SEC : {res.get('sec_ok', 0)} comptes téléchargés ; {v.get('Confirmé', 0)} valeurs "
                      f"confirmées, {v.get('Écart', 0)} avec un écart, {retard} où Yahoo est en retard.")
    if res.get("esef_ok") or res.get("esef_reste"):
        lignes.append(f"Rapports européens (ESEF) : {res.get('esef_ok', 0)} sociétés lues"
                      + (f", {res['esef_reste']} à traiter aux prochaines mises à jour (ou : python -m pf esef)."
                         if res.get("esef_reste") else "."))
    inv = res.get("investisseurs") or {}
    if inv.get("saute") or inv.get("erreur"):
        lignes.append(f"Portefeuilles 13F non lus : {inv.get('saute') or inv.get('erreur')}.")
    elif inv.get("nouvelles"):
        lignes.append(f"Portefeuilles 13F : {inv['nouvelles']} nouveaux trimestres lus.")
    if res["erreurs"]:
        lignes.append("Non mises à jour : " + ", ".join(sorted(res["erreurs"])))
    if res["sans_cours"]:
        lignes.append("Sans cours : " + ", ".join(res["sans_cours"]))
    if res.get("sauvegarde"):
        lignes.append(f"Données personnelles sauvegardées : {res['sauvegarde']}.")
    elif res.get("sauvegarde_erreur"):
        lignes.append(f"Sauvegarde impossible : {res['sauvegarde_erreur']}.")
    if res.get("theses_creees"):
        lignes.append("Fiches de thèse créées : " + ", ".join(res["theses_creees"]))
    return lignes
