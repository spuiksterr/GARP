"""Contrôle de l'état du projet : univers, fichiers de configuration, cours et fiches (commande `pf verifier`).

Chaque constat a une gravité : « erreur » (à corriger : un calcul serait faux ou un fichier illisible) ou
« avertissement » (à examiner). Rien n'est modifié.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import (
    CONFIG_DIR,
    MODELE_CSV,
    PROFIL_DIR,
    SECTEUR_FONDS,
    SECTEURS,
    STRATEGIE_JSON,
    UNIVERS_CSV,
    read_csv_fr,
)

# Colonnes indispensables des fichiers connus.
COLONNES = {
    "univers.csv": ["ticker", "nom", "pays", "enveloppe", "secteur"],
    "portefeuille_modele.csv": ["ticker", "poids_cible"],
    "selection_claude_2026-10.csv": ["ticker", "poids_cible"],
    "watchlist.csv": ["ticker", "ajoute_le", "cours_ajout"],
    "surveillance.csv": ["ticker", "condition_entree"],
    "regles_vente.csv": ["ticker", "indicateur", "operateur", "seuil"],
    "scenarios.csv": ["ticker"],
    "actualites.csv": ["ticker", "recherche"],
}
ENVELOPPES = {"PEA", "CTO"}
COURS_FIGE_JOURS = 10  # dernier cours plus ancien que la dernière séance de l'univers


@dataclass
class Constat:
    gravite: str  # "erreur" ou "avertissement"
    categorie: str
    message: str


def verifier_csv(chemin: Path) -> list[Constat]:
    """Fichier lisible, même nombre de champs sur chaque ligne, colonnes indispensables présentes."""
    nom = chemin.name
    try:
        texte = chemin.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return [Constat("erreur", "configuration", f"{nom} : encodage autre que UTF-8")]
    lignes = list(csv.reader(texte.splitlines(), delimiter=";"))
    if not lignes:
        return [Constat("erreur", "configuration", f"{nom} : fichier vide")]
    entete = [c.strip() for c in lignes[0]]
    out = []
    for i, ligne in enumerate(lignes[1:], start=2):
        if ligne and len(ligne) != len(entete):
            out.append(Constat("erreur", "configuration",
                               f"{nom}, ligne {i} : {len(ligne)} champs au lieu de {len(entete)} "
                               "(un « ; » dans un texte ?)"))
    manquantes = [c for c in COLONNES.get(nom, []) if c not in entete]
    if manquantes:
        out.append(Constat("erreur", "configuration", f"{nom} : colonnes absentes {', '.join(manquantes)}"))
    return out


def verifier_univers(univers: pd.DataFrame) -> list[Constat]:
    out = []
    for t in sorted(set(univers["ticker"][univers["ticker"].duplicated()])):
        out.append(Constat("erreur", "univers", f"{t} figure plusieurs fois (seule la première ligne compte)"))
    for _, r in univers.iterrows():
        if r["enveloppe"] not in ENVELOPPES:
            out.append(Constat("erreur", "univers", f"{r['ticker']} : enveloppe « {r['enveloppe']} » (PEA ou CTO)"))
        if r["secteur"] not in SECTEURS:
            out.append(Constat("erreur", "univers", f"{r['ticker']} : secteur inconnu « {r['secteur']} »"))
    # Une même société cotée deux fois (ASML et ASML.AS) : voir indices.meme_societe.
    from .indices import meme_societe
    noms = dict(zip(univers["ticker"], univers["nom"]))
    for t in sorted(noms):
        racine = t.split(".")[0]
        if "." in t and racine in noms and meme_societe(t, noms[t], racine, noms[racine]):
            out.append(Constat("avertissement", "univers",
                               f"{racine} ({noms[racine]}) et {t} ({noms[t]}) : probablement la même société, "
                               "comptée deux fois dans le screener"))
    return out


def verifier_profil(univers: pd.DataFrame) -> list[Constat]:
    out = []
    connus = set(univers["ticker"])
    if MODELE_CSV.exists():
        modele = read_csv_fr(MODELE_CSV, numeric=("poids_cible",))
        total = modele["poids_cible"].sum()
        if abs(total - 100) > 0.5:
            out.append(Constat("avertissement", "profil",
                               f"poids cibles du portefeuille : {total:.1f} % au lieu de 100 %"))
    for nom in ("watchlist.csv", "surveillance.csv", "regles_vente.csv"):
        chemin = PROFIL_DIR / nom
        if chemin.exists():
            for t in sorted(set(read_csv_fr(chemin)["ticker"]) - connus):
                out.append(Constat("avertissement", "profil",
                                   f"{nom} : {t} absent de l'univers (pas de cours ni de score)"))
    return out


def verifier_cours(univers: pd.DataFrame, prix: pd.DataFrame) -> list[Constat]:
    out = []
    if prix.empty:
        return [Constat("erreur", "cours", "aucun cours en cache : lancer pf maj")]
    derniere = prix.index.max()
    for t in univers["ticker"]:
        if t not in prix.columns or prix[t].dropna().empty:
            out.append(Constat("erreur", "cours", f"{t} : aucun cours"))
            continue
        date = prix[t].last_valid_index()
        if (derniere - date).days > COURS_FIGE_JOURS:
            out.append(Constat("avertissement", "cours",
                               f"{t} : dernier cours au {date:%d/%m/%Y} (radiée, rachetée ou ticker changé ?)"))
    return out


def verifier_fiches(univers: pd.DataFrame) -> list[Constat]:
    from .data import incomplete, load_fundamentals
    out = []
    for t in univers["ticker"][univers["secteur"] != SECTEUR_FONDS]:
        fiche = load_fundamentals(t)
        if not fiche:
            out.append(Constat("avertissement", "fiches", f"{t} : pas de fiche de fondamentaux"))
        elif incomplete(fiche):
            out.append(Constat("avertissement", "fiches", f"{t} : fiche incomplète (comptes absents)"))
    return out


def verifier() -> list[Constat]:
    """Tous les contrôles. Les suivants sont sautés si un fichier indispensable est illisible."""
    from .data import load_prices
    out = []
    for chemin in sorted([*CONFIG_DIR.glob("*.csv"), *PROFIL_DIR.glob("*.csv")]):
        out += verifier_csv(chemin)
    try:
        json.loads(STRATEGIE_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        out.append(Constat("erreur", "configuration", f"strategie.json illisible : {exc}"))
    if any(c.gravite == "erreur" and c.message.startswith("univers.csv") for c in out):
        return out
    univers = read_csv_fr(UNIVERS_CSV)
    out += verifier_univers(univers)
    out += verifier_profil(univers)
    out += verifier_cours(univers, load_prices())
    out += verifier_fiches(univers)
    return out
