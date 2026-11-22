"""Mise en forme des nombres à la française, commune à l'interface, à la ligne de commande et aux fiches."""
from __future__ import annotations

import math


def _fini(v) -> float | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def nombre(v, d: int = 1, suffixe: str = "") -> str:
    v = _fini(v)
    if v is None:
        return "n.d."
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",") + suffixe


def pct(v, d: int = 1, signe: bool = False) -> str:
    v = _fini(v)
    if v is None:
        return "n.d."
    x = round(v * 100, d) + 0.0  # + 0.0 : « 0,0 % » plutôt que « -0,0 % » après l'arrondi
    s = f"{x:+.{d}f}" if signe else f"{x:.{d}f}"
    return s.replace(".", ",") + " %"


def eur(v, d: int = 0) -> str:
    return "n.d." if _fini(v) is None else nombre(v, d) + " €"
