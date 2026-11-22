"""Construit le jeu d'essai versionné (tests/jeu_essai/) à partir des données réelles du poste.

Seize valeurs aux données figées (cours, fondamentaux, comptes SEC et ESEF, indicateurs) : de quoi afficher
toutes les pages sans réseau ni données personnelles. Le profil vient de profil.exemple/ (fictif) ; le
journal d'opérations et la thèse sont fictifs.

À relancer seulement si le format des données change, depuis portefeuille/ :
    .venv/Scripts/python.exe tests/construire_jeu_essai.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from pf.config import BENCHMARKS  # noqa: E402

SOURCE = RACINE
CIBLE = RACINE / "tests" / "jeu_essai"
# Américaines, européennes, banque, assureur, holding, fonds, historique court (SAP.DE, CS.PA : 4 exercices).
VALEURS = ["ADBE", "MSFT", "GOOGL", "COST", "JPM", "BRK-B", "ONON", "MC.PA", "ASML.AS", "AI.PA", "TTE.PA",
           "CS.PA", "SAP.DE", "NOVO-B.CO", "RACE.MI", "NUKL.DE"]
CONFIG_COMMUNE = ["strategie.json", "cas_particuliers.csv", "investisseurs.csv", "elus.csv",
                  "regards_ajustements.csv"]

THESE = """# Microsoft (MSFT)

> Fiche fictive du jeu d'essai. Verdict : **Conserver**.

## Thèse

1. Exemple : logiciels et cloud à revenus récurrents.

## Conditions de vente (décidées avant d'acheter)

- Exemple : croissance d'Azure sous 10 % deux trimestres de suite.

## Journal de suivi

- 2026-11-01 : fiche d'exemple.
"""
TRANSACTIONS = """date;compte;type;ticker;quantite;prix_unitaire;devise;frais_eur;montant_eur;taux_change;note
2026-01-02;PEA;VERSEMENT;;;;EUR;;4000;;Exemple fictif
2026-01-02;CTO;VERSEMENT;;;;EUR;;3000;;Exemple fictif
2026-01-05;PEA;ACHAT;ASML.AS;3;650;EUR;2;1952;;Exemple fictif
2026-01-05;PEA;ACHAT;AI.PA;10;170;EUR;2;1702;;Exemple fictif
2026-01-06;CTO;ACHAT;MSFT;4;420;USD;1;1610;1.045;Exemple fictif
2026-03-02;CTO;ACHAT;COST;1;900;USD;1;829;1.087;Exemple fictif
2026-06-15;PEA;DIVIDENDE;AI.PA;;;EUR;;33;;Exemple fictif
"""


def copier(rel: str) -> None:
    src, dst = SOURCE / rel, CIBLE / rel
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def photos_fictives() -> None:
    """Deux photos du screener (data/historique) : rangs décalés et MSFT « Exclu » la semaine précédente.

    Lancé dans un processus où PF_DOSSIER désigne le jeu d'essai, pour calculer le screener sur ses données.
    """
    from pf import photos
    from pf.scoring import build_screener
    sc = build_screener()
    avant = sc.copy()
    avant["rang"] = avant["rang"] + 2
    avant.loc["MSFT", "statut"] = "Exclu"
    photos.enregistrer(avant, "2026-11-01")
    photos.enregistrer(sc, "2026-11-08")


def main() -> None:
    if CIBLE.exists():
        shutil.rmtree(CIBLE)
    (CIBLE / "config").mkdir(parents=True)
    cache = Path("data/cache")

    univers = pd.read_csv(SOURCE / "config/univers.csv", sep=";", dtype=str, keep_default_na=False,
                          encoding="utf-8-sig")
    manquantes = set(VALEURS) - set(univers["ticker"])
    assert not manquantes, manquantes
    univers[univers["ticker"].isin(VALEURS)].to_csv(CIBLE / "config/univers.csv", sep=";", index=False,
                                                    encoding="utf-8")
    for nom in CONFIG_COMMUNE:
        copier(f"config/{nom}")

    prix = pd.read_parquet(SOURCE / cache / "prix.parquet")
    colonnes = [c for c in VALEURS + list(BENCHMARKS) if c in prix.columns]
    (CIBLE / cache).mkdir(parents=True)
    prix[colonnes].dropna(how="all").to_parquet(CIBLE / cache / "prix.parquet")
    indic = pd.read_parquet(SOURCE / cache / "indicateurs.parquet")
    indic[indic.index.isin(VALEURS)].to_parquet(CIBLE / cache / "indicateurs.parquet")
    for rel in ("fx.parquet", "indicateurs.meta.json", "mises_a_jour.json", "controles.json"):
        copier(str(cache / rel))
    for t in VALEURS:
        for sous in ("fondamentaux", "sec", "esef", "actualites"):
            copier(str(cache / sous / f"{t}.json"))
    for f in (SOURCE / cache / "sec" / "13f").glob("*.json"):
        copier(str(f.relative_to(SOURCE)))

    shutil.copytree(RACINE / "profil.exemple", CIBLE / "profil")
    (CIBLE / "theses").mkdir()
    (CIBLE / "theses" / "MSFT.md").write_text(THESE, encoding="utf-8")
    (CIBLE / "data" / "transactions.csv").write_text(TRANSACTIONS, encoding="utf-8")
    subprocess.run([sys.executable, __file__, "--photos"], check=True, env={**os.environ, "PF_DOSSIER": str(CIBLE)})

    taille = sum(f.stat().st_size for f in CIBLE.rglob("*") if f.is_file())
    print(f"Jeu d'essai : {len(VALEURS)} valeurs, {sum(1 for f in CIBLE.rglob('*') if f.is_file())} fichiers, "
          f"{taille / 1e6:.1f} Mo")


if __name__ == "__main__":
    photos_fictives() if "--photos" in sys.argv else main()
