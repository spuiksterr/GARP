"""Prix d'achat juste : le cours auquel l'action se paierait au multiple que l'on juge raisonnable.

À résultat inchangé (12 derniers mois), le cours est proportionnel au multiple :
    prix cible = cours actuel × multiple cible / multiple actuel.
Pas de conversion de devise ni de nombre d'actions : le cours et le multiple viennent des mêmes chiffres.

Les historiques jour par jour du multiple (metrics.serie_multiple) donnent les repères pour choisir sa cible :
médianes sur 5 et 10 ans et sur tout l'historique, minimum. Une médiane sur 5 ou 10 ans n'est donnée que
si l'historique couvre la durée (à 5 % près) : tirée de 6 ans de données, une « médiane sur 10 ans » tromperait.
"""
from __future__ import annotations

import math

import pandas as pd

from . import postes
from .metrics import serie_multiple

# Ratio : (poste du dénominateur, état des 12 derniers mois, rémunérations en actions retirées)
RATIOS = {
    "P/FCF": ("fcf", "ttm_cashflow", False),
    "P/FCF hors SBC": ("fcf", "ttm_cashflow", True),
    "PER": ("net_income", "ttm_income", False),
    "P/CA": ("revenue", "ttm_income", False),
}
DEFINITIONS = {
    "P/FCF": "Capitalisation / flux de trésorerie disponible",
    "P/FCF hors SBC": "Capitalisation / (flux de trésorerie disponible − rémunérations en actions)",
    "PER": "Capitalisation / résultat net",
    "P/CA": "Capitalisation / chiffre d'affaires (en anglais : P/S)",
}


def ratios_pour(financiere: bool, holding: bool) -> list[str]:
    """Ratios qui ont un sens pour la société : le PER seul pour une banque ou un assureur (leurs « flux »
    mêlent dépôts et crédits), aucun pour une holding (elle se juge sur sa décote à l'actif net)."""
    if holding:
        return []
    return ["PER"] if financiere else list(RATIOS)


def serie(ratio: str, fund: dict, h: pd.DataFrame, prix: pd.Series, mcap_now: float, fx: pd.DataFrame,
          devise: str, devise_comptes: str) -> pd.Series:
    """Multiple jour par jour (dernier point : 12 derniers mois), à partir de l'historique commun `h`."""
    cle, section, net = RATIOS[ratio]
    annuel = h[cle] if cle in h.columns else pd.Series(dtype="float64")
    if net and h["sbc"].notna().any():
        annuel = annuel - h["sbc"]
    ttm = None
    douze_mois = postes.serie(fund, cle, section)
    if len(douze_mois):
        valeur = float(douze_mois.iloc[-1])
        if net:
            sbc = postes.dernier(fund, "sbc", "ttm_cashflow")
            valeur -= sbc if math.isfinite(sbc) else 0.0
        ttm = (douze_mois.index[-1], valeur)
    return serie_multiple(prix, mcap_now, fx, devise, devise_comptes, h["shares"], annuel, ttm)


def actuel(s: pd.Series) -> float:
    """Multiple du jour ; NaN si le dénominateur des 12 derniers mois est négatif ou nul."""
    return float(s.iloc[-1]) if len(s) and pd.notna(s.iloc[-1]) else math.nan


def mediane(s: pd.Series, annees: int | None = None) -> float:
    """Médiane du multiple sur les `annees` dernières années (tout l'historique si None).

    NaN si l'historique ne couvre pas la durée à 5 % près. Les trous (exercices à résultat négatif) sont
    ignorés, mais une période qui commence par un trou n'est pas couverte.
    """
    s = s.dropna()
    if s.empty:
        return math.nan
    if annees is None:
        return float(s.median())
    debut = s.index.max() - pd.DateOffset(years=annees)
    if s.index.min() > debut + pd.Timedelta(days=max(30, round(0.05 * 365.25 * annees))):
        return math.nan
    return float(s[s.index >= debut].median())


def reperes(s: pd.Series) -> list[tuple[str, float]]:
    """Lignes du tableau des médianes : sur 5 ans, sur 10 ans, et depuis le début de l'historique."""
    valides = s.dropna()
    lignes = [("Sur 5 ans", mediane(s, 5)), ("Sur 10 ans", mediane(s, 10))]
    if len(valides):
        lignes.append((f"Depuis {valides.index.min().year}", mediane(s)))
    return lignes


def cible_par_defaut(s: pd.Series) -> float:
    """Point de départ de la saisie : la médiane sur 5 ans, à défaut sur 10 ans, sur tout l'historique,
    ou le multiple actuel. C'est un repère neutre, pas une recommandation."""
    return next((x for x in (mediane(s, 5), mediane(s, 10), mediane(s), actuel(s)) if math.isfinite(x)), math.nan)


def prix_cible(cours: float, multiple_actuel: float, cible: float) -> float:
    """Cours auquel l'action se paierait `cible` fois les résultats des 12 derniers mois."""
    if all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in (cours, multiple_actuel, cible)):
        return cours * cible / multiple_actuel
    return math.nan


def ecart(valeur: float, reference: float) -> float:
    """valeur / reference − 1 : négatif quand la valeur est sous la référence."""
    if all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in (valeur, reference)):
        return valeur / reference - 1
    return math.nan
