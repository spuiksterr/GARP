"""Fiches de thèse (theses/TICKER.md) : pourquoi on détient, ce qui ferait vendre, journal de suivi."""
from __future__ import annotations

import re
from datetime import date

import pandas as pd

from .config import THESES_DIR, ecrire_texte, load_model_portfolio
from .formats import nombre, pct

REGLE_DE_VENTE = (
    "On ne vend que pour l'une de ces trois raisons : on s'est trompé sur l'entreprise, les faits "
    "invalident la thèse, ou une opportunité nettement meilleure apparaît (rendement attendu supérieur "
    "d'au moins 5 points à risque comparable). La baisse du cours et le prix de revient n'en font pas partie."
)

INDICATEURS_FICHE = [
    ("rentabilite", "Rentabilité moyenne (ROIC ou ROE)", "pct"),
    ("marge_operationnelle", "Marge opérationnelle moyenne", "pct"),
    ("croiss_ca", "Croissance du CA (historique)", "pct"),
    ("croissance_attendue", "Croissance attendue (médiane des signaux)", "pct"),
    ("per_prospectif", "PER prospectif", "x"),
    ("rendement_fcf", "Rendement du flux de trésorerie disponible", "pct"),
    ("croissance_implicite", "Croissance implicite dans le cours", "pct"),
    ("tri_implicite", "TRI implicite", "pct"),
    ("mom_12_1", "Momentum 12-1 mois", "pct"),
    ("score", "Score composite (0-100)", "n"),
]


def _safe(ticker: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", ticker)


def thesis_path(ticker: str):
    return THESES_DIR / f"{_safe(ticker)}.md"


def _fmt(v, kind: str) -> str:
    return pct(v) if kind == "pct" else nombre(v, 1, "x") if kind == "x" else nombre(v, 0)


def _text(row: pd.Series, col: str, placeholder: str) -> str:
    v = row.get(col)
    return str(v).strip() if isinstance(v, str) and v.strip() else f"_{placeholder}_"


def render(ticker: str, row: pd.Series, metrics: pd.Series | None) -> str:
    today = date.today().isoformat()
    conviction = _fmt(row.get("conviction"), "n")
    entete = [f"poche « {row.get('poche', '')} »"]
    if conviction != "n.d.":
        entete.append(f"conviction {conviction}/3")
    entete += [f"poids cible {_fmt(float(row.get('poids_cible', 0)) / 100, 'pct')}", f"enveloppe {row.get('enveloppe', '')}"]
    lines = [
        f"# {row.get('nom', ticker)} ({ticker})",
        "",
        f"> Fiche créée le {today} : " + ", ".join(entete) + ".",
        "",
        "## Thèse",
        "",
        _text(row, "these", "À rédiger : pourquoi je détiens cette valeur et ce que j'en attends à 5 ans "
                            "(ou lancer /analyse-valeur " + ticker + ")."),
        "",
        "## Ce qui pourrait la casser",
        "",
        _text(row, "risque_principal", "À rédiger : le fait précis qui prouverait que j'ai tort."),
        "",
        "## Conditions de vente (décidées avant d'acheter)",
        "",
        f"- {_text(row, 'condition_vente', 'À rédiger : seuil chiffré ou événement.')}",
        f"- {REGLE_DE_VENTE}",
        "",
    ]
    if row.get("alternative"):
        lines += [f"Alternative si la valeur n'est pas accessible ou en cas de remplacement : {row['alternative']}.", ""]
    if metrics is not None:
        lines += [f"## Indicateurs au {today}", "", "| Indicateur | Valeur |", "|---|---|"]
        for col, label, kind in INDICATEURS_FICHE:
            lines.append(f"| {label} | {_fmt(metrics.get(col), kind)} |")
        lines.append("")
    lines += [
        "## Journal de suivi",
        "",
        f"- {today} : création de la fiche.",
        "",
    ]
    return "\n".join(lines)


def ensure_thesis_files(screener: pd.DataFrame | None = None, overwrite: bool = False) -> list[str]:
    """Crée la fiche de chaque ligne du portefeuille modèle si elle n'existe pas encore."""
    THESES_DIR.mkdir(parents=True, exist_ok=True)
    created = []
    for ticker, row in load_model_portfolio().iterrows():
        path = thesis_path(ticker)
        if path.exists() and not overwrite:
            continue
        metrics = screener.loc[ticker] if screener is not None and ticker in screener.index else None
        ecrire_texte(path, render(ticker, row, metrics))
        created.append(ticker)
    return created


def read_thesis(ticker: str) -> str | None:
    path = thesis_path(ticker)
    return path.read_text(encoding="utf-8") if path.exists() else None


def append_journal(ticker: str, text: str) -> None:
    path = thesis_path(ticker)
    content = path.read_text(encoding="utf-8") if path.exists() else f"# {ticker}\n\n## Journal de suivi\n\n"
    if "## Journal de suivi" not in content:
        content += "\n## Journal de suivi\n\n"
    content = content.rstrip("\n") + f"\n- {date.today().isoformat()} : {text.strip()}\n"
    ecrire_texte(path, content)
