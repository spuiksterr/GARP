"""Lecture des états financiers : une seule table de correspondance avec les postes Yahoo, et un seul
historique annuel, prolongé dans le passé par les comptes déposés à la SEC.

Tous les calculs (indicateurs, signaux de santé, critères, recoupement SEC) passent par ici : un poste
renommé chez Yahoo se corrige à un seul endroit, et une même notion a la même valeur partout.

Yahoo fournit quatre exercices, soit trois ans de croissance. Pour une société américaine, les comptes
déposés à la SEC prolongent chaque série vers le passé, à condition de reproduire à 3 % près les chiffres
Yahoo sur les exercices communs : on atteint alors cinq ans.
"""
from __future__ import annotations

import collections
import math

import numpy as np
import pandas as pd

# Poste : (état financier Yahoo, libellés acceptés par ordre de préférence).
POSTES = {
    # compte de résultat
    "revenue": ("income", ["Total Revenue", "Operating Revenue"]),
    "gross_profit": ("income", ["Gross Profit"]),
    "op_income": ("income", ["Operating Income", "Total Operating Income As Reported", "EBIT"]),
    "ebit": ("income", ["EBIT", "Operating Income"]),
    "ebitda": ("income", ["EBITDA", "Normalized EBITDA"]),
    "net_income": ("income", ["Net Income Common Stockholders", "Net Income"]),
    "interest": ("income", ["Interest Expense", "Interest Expense Non Operating"]),
    "tax_rate": ("income", ["Tax Rate For Calcs"]),
    "sga": ("income", ["Selling General And Administration"]),
    "shares": ("income", ["Diluted Average Shares", "Basic Average Shares"]),  # moyenne diluée de l'exercice
    # bilan
    "assets": ("balance", ["Total Assets"]),
    "current_assets": ("balance", ["Current Assets"]),
    "current_liabilities": ("balance", ["Current Liabilities"]),
    "liabilities": ("balance", ["Total Liabilities Net Minority Interest"]),
    "long_term_debt": ("balance", ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"]),
    "retained": ("balance", ["Retained Earnings"]),
    "receivables": ("balance", ["Accounts Receivable", "Receivables"]),
    "ppe": ("balance", ["Net PPE"]),
    "equity": ("balance", ["Stockholders Equity", "Common Stock Equity"]),
    "debt": ("balance", ["Total Debt"]),
    "cash": ("balance", ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"]),
    "shares_outstanding": ("balance", ["Ordinary Shares Number", "Share Issued"]),  # nombre en fin d'exercice
    # flux de trésorerie
    "ocf": ("cashflow", ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]),
    "capex": ("cashflow", ["Capital Expenditure"]),
    "fcf": ("cashflow", ["Free Cash Flow"]),
    "sbc": ("cashflow", ["Stock Based Compensation"]),
    "depreciation": ("cashflow", ["Depreciation And Amortization", "Depreciation Amortization Depletion"]),
    "dividends": ("cashflow", ["Cash Dividends Paid", "Common Stock Dividend Paid"]),
    "buybacks": ("cashflow", ["Repurchase Of Capital Stock", "Common Stock Payments"]),
}
ANNEES = 5
TOLERANCE_RACCORD = 0.03
# Variation maximale d'un exercice à l'autre dans la partie prolongée : au-delà, la série SEC est
# coupée. Une division d'action (Deckers, 6 pour 1 en 2024) n'est retraitée que dans les rapports
# postérieurs ; les exercices plus anciens restent en actions d'avant la division.
SAUT_MAX = {"shares": 1.33, "revenue": 2.0, "assets": 2.0, "current_liabilities": 2.0}


# --------------------------------------------------------------------------- lecture

def _dates(index) -> pd.DatetimeIndex:
    """Dates « AAAA-MM-JJ » des comptes. Le format donné évite sa détection automatique, de loin l'étape la plus
    lente du calcul des indicateurs (des dizaines de milliers d'appels) ; tout autre format reste accepté."""
    try:
        return pd.to_datetime(index, format="%Y-%m-%d")
    except (ValueError, TypeError):
        return pd.to_datetime(index)


def serie(fund: dict, cle: str, section: str | None = None) -> pd.Series:
    """Valeurs datées d'un poste (la première étiquette disponible), du plus ancien au plus récent.

    `section` remplace l'état annuel par un autre : « balance_q », « ttm_income », « ttm_cashflow ».
    """
    defaut, labels = POSTES[cle]
    rows = fund.get(section or defaut) or {}
    for lab in labels:
        if rows.get(lab):
            return _lue(rows[lab]).copy()
    return pd.Series(dtype="float64")


# Postes déjà convertis en séries : un même poste est relu des dizaines de fois par valeur (indicateurs, critères,
# santé financière). La clé garde l'objet lu (qui ne peut donc pas être remplacé par un autre à la même adresse)
# et sa taille ; une fiche rechargée est un nouvel objet, donc relue.
_MEMOIRE: collections.OrderedDict = collections.OrderedDict()
_MEMOIRE_MAX = 2000


def _lue(valeurs: dict) -> pd.Series:
    cle = (id(valeurs), len(valeurs))
    entree = _MEMOIRE.get(cle)
    if entree is not None and entree[0] is valeurs:
        _MEMOIRE.move_to_end(cle)
        return entree[1]
    s = pd.Series(valeurs, dtype="float64")
    s.index = _dates(s.index)
    s = s.sort_index().dropna()
    _MEMOIRE[cle] = (valeurs, s)
    if len(_MEMOIRE) > _MEMOIRE_MAX:
        _MEMOIRE.popitem(last=False)
    return s


def dernier(fund: dict, cle: str, section: str | None = None) -> float:
    s = serie(fund, cle, section)
    return float(s.iloc[-1]) if len(s) else math.nan


def valeurs(fund: dict, cle: str, date: str) -> list[float]:
    """Toutes les valeurs publiées à une date sous les différentes étiquettes du poste."""
    section, labels = POSTES[cle]
    rows = fund.get(section) or {}
    return [rows[lab][date] for lab in labels if date in (rows.get(lab) or {})]


def table(fund: dict, cles) -> pd.DataFrame:
    """Postes Yahoo seuls, alignés par date de clôture."""
    df = pd.DataFrame({c: serie(fund, c) for c in cles}, columns=list(cles))
    return df.sort_index()


# --------------------------------------------------------------------------- historique prolongé

def _signe_concordant(y: pd.Series, s: pd.Series, tol: float) -> float | None:
    """+1 ou -1 si `s` reproduit `y` (au signe près) sur au moins deux exercices communs, sinon None.

    Pour chaque exercice Yahoo, la référence est la première valeur de `s` (triée) à 10 jours au plus. Calcul
    matriciel : la boucle valeur par valeur coûtait une minute sur l'univers entier.
    """
    if y.empty or s.empty:
        return None
    ecarts = np.abs((y.index.values[:, None] - s.index.values[None, :]) / np.timedelta64(1, "D"))
    proches = ecarts <= 10
    communs = proches.any(axis=1)
    if communs.sum() < 2:
        return None
    refs = s.values[proches.argmax(axis=1)][communs]
    v = y.values[communs]
    for signe in (1.0, -1.0):
        ref = signe * refs
        # Même règle qu'auparavant : un écart (ou une référence nulle) sur un seul exercice commun suffit à rejeter.
        if not ((ref == 0) | (np.abs(v - ref) > tol * np.abs(ref))).any():
            return signe
    return None


def prolonger(yahoo: pd.Series, candidats: dict[str, dict[str, float]], tol: float = TOLERANCE_RACCORD,
              saut_max: float | None = None) -> pd.Series:
    """Ajoute, avant le premier exercice Yahoo, les exercices SEC des postes qui reproduisent Yahoo.

    Un poste n'est retenu que s'il concorde sur au moins deux exercices communs et ne s'écarte sur aucun :
    un poste de périmètre différent ne doit pas allonger la série. Le signe suit la convention Yahoo
    (investissements négatifs). Avec `saut_max`, on remonte le temps exercice par exercice et on s'arrête
    au premier écart supérieur à ce facteur.
    """
    y = yahoo.dropna()
    if y.empty or not candidats:
        return yahoo
    debut = y.index.min() - pd.Timedelta(days=10)
    anciens = pd.Series(dtype="float64")
    for vals in candidats.values():
        s = pd.Series(vals, dtype="float64")
        s.index = _dates(s.index)
        signe = _signe_concordant(y, s.sort_index(), tol)
        if signe is None:
            continue
        plus_anciens = s[s.index < debut] * signe
        anciens = plus_anciens if anciens.empty else anciens.combine_first(plus_anciens)
    if saut_max and not anciens.empty:
        garde, suivant = [], y.iloc[0]
        for d in anciens.index.sort_values(ascending=False):
            v = anciens[d]
            if v <= 0 or suivant <= 0 or not 1 / saut_max <= suivant / v <= saut_max:
                break
            garde.append(d)
            suivant = v
        anciens = anciens[garde]
    if anciens.empty:
        return yahoo
    return pd.concat([anciens, y]).sort_index()


def historique(fund: dict, sec_data: dict | None = None) -> tuple[pd.DataFrame, bool]:
    """Exercices annuels de tous les postes, prolongés par la SEC quand c'est possible.

    Renvoie aussi vrai si la SEC a prolongé le chiffre d'affaires, qui borne l'historique : les exercices
    sans chiffre d'affaires ni résultat sont écartés.
    """
    sec_series = (sec_data or {}).get("series") or {}
    cols = {}
    for cle in POSTES:
        y = serie(fund, cle)
        if sec_series.get(cle):  # la SEC ne fournit pas de FCF ; les rapports européens, si (ESEF)
            y = prolonger(y, sec_series[cle], saut_max=SAUT_MAX.get(cle))
        cols[cle] = y
    df = pd.DataFrame(cols, columns=list(POSTES)).sort_index()
    if df.empty:
        return df, False
    # FCF publié par Yahoo, sinon flux d'exploitation + investissements (négatifs chez Yahoo).
    df["fcf"] = df["fcf"].fillna(df["ocf"] + df["capex"])
    df = df[df[["revenue", "net_income"]].notna().any(axis=1)]
    return df, int(df["revenue"].notna().sum()) > len(serie(fund, "revenue"))


def fenetre(s: pd.Series, annees: int = ANNEES) -> tuple[float, float, float] | None:
    """(valeur de départ, valeur finale, durée en années) sur au plus `annees` ans jusqu'au dernier exercice."""
    s = s.dropna()
    if len(s) < 2:
        return None
    fin = s.index[-1]
    s = s[s.index >= fin - pd.DateOffset(years=annees) - pd.Timedelta(days=120)]
    duree = (fin - s.index[0]).days / 365.25
    return (float(s.iloc[0]), float(s.iloc[-1]), duree) if duree >= 0.9 else None


def taux_annuel(s: pd.Series, annees: int = ANNEES) -> float:
    """Croissance annuelle moyenne sur la fenêtre ; NaN si une borne est négative ou nulle."""
    w = fenetre(s, annees)
    if w is None or not (w[0] > 0 and w[1] > 0):
        return math.nan
    return (w[1] / w[0]) ** (1 / w[2]) - 1


def derniers(s: pd.Series, annees: int = ANNEES) -> pd.Series:
    """Les exercices des `annees` dernières années (au plus `annees` valeurs)."""
    s = s.dropna()
    if s.empty:
        return s
    return s[s.index > s.index[-1] - pd.DateOffset(years=annees) + pd.Timedelta(days=120)]


def dernier_bilan(fund: dict, tresorerie_clients: bool = False) -> tuple[float, float, str] | None:
    """(dette, trésorerie, période) au dernier bilan connu : trimestriel s'il existe, sinon annuel.

    La date de référence est la dernière où la dette est connue (à défaut, la trésorerie) : une ligne
    de dette absente du dernier trimestre ne doit pas faire croire à une société sans dette. Sans bilan,
    renvoie None : une dette inconnue n'est pas une dette nulle.
    """
    for section, periode in (("balance_q", "au dernier trimestre"), ("balance", "au dernier exercice")):
        dette, cash = serie(fund, "debt", section), serie(fund, "cash", section)
        if dette.empty and cash.empty:
            continue
        date = dette.index[-1] if len(dette) else cash.index[-1]
        d = float(dette.get(date, 0.0)) if len(dette) else 0.0
        c = 0.0 if tresorerie_clients else float(cash.get(date, 0.0)) if len(cash) else 0.0
        return d, c, periode
    return None
