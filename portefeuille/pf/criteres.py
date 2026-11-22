"""Six critères de qualité, remplis ou non : croissance, rentabilité du capital, dette, dilution, marge.

Grille de type « réussi / échoué », sans pondération : chaque critère compare une mesure à un seuil
réglable (`criteres` dans config/strategie.json). Elle n'entre dans le score composite que si on lui
donne un poids (`poids_score.criteres`), car elle recoupe en partie les piliers qualité et croissance.

Les mesures viennent de l'historique commun (postes.py) : Yahoo, prolongé par la SEC (ou les rapports ESEF en Europe) pour les sociétés
américaines. Elles valent donc exactement les indicateurs de même nom du screener (croissance du CA,
marge de FCF, évolution du nombre d'actions). La fenêtre réellement utilisée est affichée avec chaque critère.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import postes
from .formats import nombre

SEUILS = {"croissance_ca_min": 0.10, "croissance_fcf_min": 0.10, "roce_min": 0.15,
          "dette_nette_fcf_max": 3.0, "evolution_actions_max": 0.0, "marge_fcf_min": 0.10}
# Critère : (seuil, comparaison). Une seule définition, pour le calcul et pour la réapplication des seuils.
REGLES = {"ca": ("croissance_ca_min", ">"), "fcf": ("croissance_fcf_min", ">"), "roce": ("roce_min", ">"),
          "dette": ("dette_nette_fcf_max", "<"), "actions": ("evolution_actions_max", "<="), "marge": ("marge_fcf_min", ">")}
SANS_OBJET = "Sans objet pour une banque, un assureur ou une holding"
FLUX_CLIENTS = "Sans objet : flux de trésorerie mêlés aux fonds des clients"


@dataclass
class Critere:
    cle: str
    titre: str
    valeur: float = math.nan
    rempli: bool | None = None  # None : non évalué (données absentes ou critère sans objet)
    periode: str = ""
    note: str = ""


def verdict(cle: str, valeur: float, seuils: dict | None = None) -> bool:
    s = {**SEUILS, **(seuils or {})}
    seuil, sens = REGLES[cle]
    return bool({">": valeur > s[seuil], "<": valeur < s[seuil], "<=": valeur <= s[seuil]}[sens])


def _sur(duree: float) -> str:
    n = max(int(round(duree)), 1)
    return "la dernière année" if n == 1 else f"les {n} dernières années"


def evaluer(fund: dict, sec_data: dict | None = None, financiere: bool = False, seuils: dict | None = None,
            tresorerie_clients: bool = False, h: pd.DataFrame | None = None) -> list[Critere]:
    """Les six critères, dans l'ordre d'affichage.

    `tresorerie_clients` : société dont la trésorerie et les flux incluent l'argent de ses clients
    (paiement, bourse, avances) ; les trois critères fondés sur le free cash flow n'ont alors pas de sens.
    `h` : historique déjà calculé (postes.historique), pour ne pas le refaire.
    """
    sans_fcf = SANS_OBJET if financiere else FLUX_CLIENTS if tresorerie_clients else ""
    h = postes.historique(fund, sec_data)[0] if h is None else h
    col = (lambda k: h[k]) if not h.empty else (lambda k: pd.Series(dtype="float64"))

    def croissance(cle: str, titre: str, s: pd.Series, libelle: str) -> Critere:
        c = Critere(cle, titre)
        w = postes.fenetre(s)
        if w is None:
            c.note = "Historique insuffisant"
            return c
        c.periode = f"par an sur {_sur(w[2])}"
        c.valeur = postes.taux_annuel(s)
        if np.isfinite(c.valeur):
            c.rempli = verdict(cle, c.valeur, seuils)
        else:
            c.rempli = False
            c.note = f"{libelle} négatif ou nul en début ou en fin de période"
        return c

    def moyenne(cle: str, titre: str, ratios: pd.Series) -> Critere:
        c = Critere(cle, titre)
        annuel = postes.derniers(ratios.replace([np.inf, -np.inf], np.nan))
        if len(annuel) >= 2:
            c.valeur = float(annuel.mean())
            c.rempli = verdict(cle, c.valeur, seuils)
            c.periode = f"en moyenne sur {len(annuel)} ans"
        else:
            c.note = "Historique insuffisant"
        return c

    out = [croissance("ca", "Croissance du chiffre d'affaires", col("revenue"), "Chiffre d'affaires")]
    out.append(Critere("fcf", "Croissance du free cash flow", note=sans_fcf) if sans_fcf
               else croissance("fcf", "Croissance du free cash flow", col("fcf"), "Flux"))

    if financiere:
        out.append(Critere("roce", "ROCE", note=SANS_OBJET))
    else:
        capital = col("assets") - col("current_liabilities")
        out.append(moyenne("roce", "ROCE", col("op_income") / capital.where(capital > 0)))

    dette = Critere("dette", "Dette nette / Free cash flow")
    bilan = postes.dernier_bilan(fund, tresorerie_clients)
    fcf = postes.dernier(fund, "fcf", "ttm_cashflow")
    if not np.isfinite(fcf) and col("fcf").notna().any():
        fcf = float(col("fcf").dropna().iloc[-1])
    if sans_fcf:
        dette.note = sans_fcf
    elif bilan is None or not np.isfinite(fcf):
        dette.note = "Données absentes"
    else:
        net = bilan[0] - bilan[1]
        dette.periode = bilan[2]
        if fcf > 0:
            dette.valeur = net / fcf
            dette.rempli = verdict("dette", dette.valeur, seuils)
            if net < 0:
                dette.note = "Trésorerie supérieure à la dette"
        else:
            dette.rempli = bool(net <= 0)
            dette.note = "Flux de trésorerie négatif" + (", mais pas de dette nette" if net <= 0 else "")
    out.append(dette)

    actions = Critere("actions", "Nombre d'actions en circulation")
    w = postes.fenetre(col("shares"))
    if w is None or w[0] <= 0:
        actions.note = "Historique insuffisant"
    else:
        actions.valeur = w[1] / w[0] - 1
        actions.rempli = verdict("actions", actions.valeur, seuils)
        actions.periode = f"sur {_sur(w[2])}"
    out.append(actions)

    out.append(Critere("marge", "Marge du free cash flow", note=sans_fcf) if sans_fcf
               else moyenne("marge", "Marge du free cash flow", col("fcf") / col("revenue").where(col("revenue") > 0)))
    return out


def resume(criteres: list[Critere]) -> dict:
    """Colonnes des indicateurs : valeur et verdict de chaque critère, puis le décompte."""
    m: dict = {}
    for c in criteres:
        m[f"crit_{c.cle}"] = c.valeur
        m[f"crit_{c.cle}_ok"] = c.rempli
    ok = sum(c.rempli is True for c in criteres)
    evalues = sum(c.rempli is not None for c in criteres)
    m["criteres_ok"] = ok
    m["criteres_evalues"] = evalues
    m["criteres"] = f"{ok}/{evalues}" if evalues else None
    return m


def reappliquer(df: pd.DataFrame, seuils: dict | None = None) -> pd.DataFrame:
    """Recalcule verdicts et décompte avec les seuils du moment, sans relire les comptes.

    Les seuils de strategie.json peuvent changer après le calcul des indicateurs : le screener doit
    alors juger comme la fiche, qui recalcule en direct. Seules les mesures chiffrées sont rejugées ;
    les cas sans valeur (flux négatif, critère sans objet) gardent leur verdict, qui ne dépend d'aucun seuil.
    """
    if "crit_ca" not in df.columns:
        return df
    out = df.copy()
    oks = []
    for cle in REGLES:
        v = pd.to_numeric(out[f"crit_{cle}"], errors="coerce")
        ok = out[f"crit_{cle}_ok"].astype("boolean") if f"crit_{cle}_ok" in out.columns else \
            pd.Series(pd.NA, index=out.index, dtype="boolean")
        fini = v.notna()
        ok[fini] = [verdict(cle, x, seuils) for x in v[fini]]
        out[f"crit_{cle}_ok"] = ok
        oks.append(ok)
    oks = pd.concat(oks, axis=1)
    out["criteres_ok"] = oks.fillna(False).astype(int).sum(axis=1)
    out["criteres_evalues"] = oks.notna().sum(axis=1)
    out["criteres"] = [f"{a}/{b}" if b else None for a, b in zip(out["criteres_ok"], out["criteres_evalues"])]
    return out


# --------------------------------------------------------------------------- textes

def texte_valeur(c: Critere) -> str:
    if not np.isfinite(c.valeur):
        return "n.d."
    if c.cle == "dette":
        return nombre(c.valeur, 2)
    signe = "+" if c.cle == "actions" and c.valeur > 0 else ""
    return f"{signe}{nombre(c.valeur * 100, 2)} %"


def texte_seuil(c: Critere, seuils: dict | None = None) -> str:
    s = {**SEUILS, **(seuils or {})}
    pct = lambda v: f"{nombre(v * 100, 0)} %"  # noqa: E731
    return {
        "ca": f"Doit être supérieure à {pct(s['croissance_ca_min'])}",
        "fcf": f"Doit être supérieure à {pct(s['croissance_fcf_min'])}",
        "roce": f"Doit être supérieur à {pct(s['roce_min'])}",
        "dette": f"Doit être inférieur à {nombre(s['dette_nette_fcf_max'], 0)}",
        "actions": f"Doit être inférieur ou égal à {pct(s['evolution_actions_max'])}",
        "marge": f"Doit être supérieure à {pct(s['marge_fcf_min'])}",
    }[c.cle]
