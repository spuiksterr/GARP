"""Non-régression : indicateurs et score de cinq valeurs du jeu d'essai, comparés à des valeurs de référence (Q-05).

Un écart signale un changement de calcul. S'il est voulu (méthode modifiée, indicateur corrigé), régénérer
la référence et expliquer l'écart dans le commit :
    PF_REGENERER_ATTENDUS=1 .venv/Scripts/python.exe -m pytest tests/test_non_regression.py -q
Une colonne nouvelle n'est pas comparée tant que la référence n'est pas régénérée.
"""
import json
import math
import os
from pathlib import Path

import pytest

ATTENDUS = Path(__file__).resolve().parent / "attendus_indicateurs.json"
# Américaine, européenne, banque, historique court (4 exercices), fonds.
VALEURS = ["ADBE", "MC.PA", "JPM", "SAP.DE", "NUKL.DE"]
COLONNES_SCREENER = ["score", "statut", "qualite", "croissance", "valorisation", "momentum", "criteres"]


def _valeur(v):
    if isinstance(v, bool | str) or v is None:
        return v
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    return None if not math.isfinite(x) else float(f"{x:.10g}")


@pytest.fixture(scope="module")
def calcules():
    from pf.metrics import compute_all
    from pf.scoring import build_screener
    m = compute_all(save=False)
    sc = build_screener(m)
    out = {}
    for t in VALEURS:
        ligne = {k: _valeur(v) for k, v in m.loc[t].items()}
        ligne.update({f"screener.{k}": _valeur(sc.loc[t, k]) for k in COLONNES_SCREENER if k in sc.columns})
        out[t] = ligne
    return out


def test_indicateurs_de_reference(calcules):
    if os.environ.get("PF_REGENERER_ATTENDUS") == "1":
        ATTENDUS.write_text(json.dumps(calcules, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")
        pytest.skip("référence régénérée")
    attendus = json.loads(ATTENDUS.read_text(encoding="utf-8"))
    ecarts = []
    for t, ref in attendus.items():
        for k, v in ref.items():
            obtenu = calcules[t].get(k, "absent")
            if isinstance(v, float) and isinstance(obtenu, float):
                if not math.isclose(v, obtenu, rel_tol=1e-6, abs_tol=1e-9):
                    ecarts.append(f"{t}.{k} : {v} -> {obtenu}")
            elif v != obtenu:
                ecarts.append(f"{t}.{k} : {v!r} -> {obtenu!r}")
    assert not ecarts, f"{len(ecarts)} écarts :\n" + "\n".join(ecarts[:40])
