"""Backtest « à date » des méthodes de notation : sans regarder l'avenir.

Le backtest du portefeuille note les actions avec les comptes d'aujourd'hui : il sait déjà qui a réussi. Ici, à
chaque date de rééquilibrage (le 1er avril de chaque année), les indicateurs sont recalculés avec les seuls
comptes publiés à cette date :
- comptes annuels déposés à la SEC (sociétés américaines de l'univers), réputés connus 90 jours après la clôture ;
- capitalisation de l'époque : capitalisation actuelle × cours d'alors / cours d'aujourd'hui × actions d'alors /
  actions d'aujourd'hui, avec les divisions d'actions repérées et neutralisées (la SEC publie les nombres d'actions
  d'origine : Apple passe de 0,9 à 6,6 milliards d'actions en 2012, division par 7) ;
- momentum : cours d'il y a 12 mois à 1 mois.
Les valeurs retenues sont gardées un an à poids égaux ; rendements en euros (cours ajustés des dividendes).

Indicateurs reconstitués (une version simplifiée des piliers de l'outil) :
- qualité : rentabilité des fonds propres, marge opérationnelle, marge de FCF, dilution (moins = mieux) ;
- croissance : croissance annuelle du chiffre d'affaires sur 3 ans ;
- valeur : rendement du FCF et des bénéfices (flux / capitalisation) ;
- momentum.
Les quatre regards, les critères, Piotroski, Altman et Beneish ne sont pas reconstitués.

Limites :
- biais du survivant : l'univers est celui d'aujourd'hui (les sociétés disparues ou sorties de l'indice manquent).
  Il gonfle toutes les courbes ; la comparaison avec toutes les valeurs éligibles à poids égaux, soumises au même
  biais, est la plus juste ;
- banques, assureurs et sociétés financières exclus (flux de trésorerie sans signification) ;
- sociétés américaines seulement (les comptes européens n'ont pas d'historique daté assez long).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import sec
from .data import currency_map, load_fundamentals, load_fx, load_prices, prices_in_eur

PUBLICATION = pd.Timedelta(days=90)
FRAICHEUR_MAX = pd.Timedelta(days=550)  # comptes de plus de 18 mois à la date : valeur écartée
PILIERS = {
    "qualite": ["roe", "marge_op", "marge_fcf", "sobriete"],
    "croissance": ["croissance_ca_3a"],
    "valeur": ["rendement_fcf", "rendement_benefices"],
    "momentum": ["mom_12_1"],
}
METHODES = {
    "Piliers (qualité, croissance, valeur, momentum)": {"qualite": 1, "croissance": 1, "valeur": 1, "momentum": 1},
    "Qualité": {"qualite": 1},
    "Qualité + valeur": {"qualite": 1, "valeur": 1},
    "Valeur": {"valeur": 1},
    "Croissance": {"croissance": 1},
    "Momentum": {"momentum": 1},
    # Le style GARP de pf/styles.py : la croissance d'abord, sans la surpayer.
    "GARP (croissance, valeur, qualité)": {"croissance": 0.4, "valeur": 0.35, "qualite": 0.25},
}
RAPPORTS_DIVISION = [1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 30, 40, 50]


# --------------------------------------------------------------------------- comptes historiques

def comptes(sec_data: dict) -> pd.DataFrame:
    """Comptes annuels SEC (un poste = le premier concept XBRL disponible, complété par les suivants)."""
    series = (sec_data or {}).get("series") or {}
    cols = {}
    for cle, concepts in sec.CONCEPTS.items():
        s = pd.Series(dtype="float64")
        for c in concepts:
            v = (series.get(cle) or {}).get(c)
            if v:
                x = pd.Series(v, dtype="float64")
                x.index = pd.to_datetime(x.index, format="%Y-%m-%d")
                s = x if s.empty else s.combine_first(x)
        cols[cle] = s
    df = pd.DataFrame(cols).sort_index()
    if "capex" in df.columns:
        df["capex"] = df["capex"].abs()
    return df


def actions_corrigees(actions: pd.Series) -> pd.Series:
    """Nombres d'actions ramenés à la base la plus récente : un saut d'un exercice à l'autre proche d'un rapport de
    division (2, 3, 4, 7, 10…, à 8 % près) ou de regroupement est neutralisé."""
    s = actions.dropna().sort_index()
    s = s[s > 0]
    if s.empty:
        return pd.Series(dtype="float64", index=pd.DatetimeIndex([]))
    if len(s) < 2:
        return s
    facteur, out = 1.0, {s.index[-1]: float(s.iloc[-1])}
    for i in range(len(s) - 2, -1, -1):
        rapport = s.iloc[i + 1] / s.iloc[i]
        for k in RAPPORTS_DIVISION:
            if abs(rapport / k - 1) < 0.08:  # division d'actions
                facteur *= k
                break
            if abs(rapport * k - 1) < 0.08:  # regroupement
                facteur /= k
                break
        out[s.index[i]] = float(s.iloc[i]) * facteur
    return pd.Series(out).sort_index()


def indicateurs_a_date(d: pd.Timestamp, comptes_t: pd.DataFrame, actions_adj: pd.Series, prix: pd.Series,
                       capi_aujourdhui: float) -> dict | None:
    """Indicateurs d'une valeur à la date `d`, avec les seuls comptes publiés (clôture + 90 jours)."""
    connus = comptes_t[comptes_t.index + PUBLICATION <= d]
    if connus.empty or d - (connus.index[-1] + PUBLICATION) > FRAICHEUR_MAX:
        return None
    dernier = connus.iloc[-1]
    p = prix.dropna()
    p_d = p[p.index <= d]
    if len(p_d) < 200 or not math.isfinite(capi_aujourdhui) or capi_aujourdhui <= 0:
        return None
    if actions_adj.empty:
        return None
    a_connues = actions_adj[actions_adj.index + PUBLICATION <= d]
    if a_connues.empty:
        return None
    capi = capi_aujourdhui * float(p_d.iloc[-1]) / float(p.iloc[-1]) * float(a_connues.iloc[-1]) / float(actions_adj.iloc[-1])
    ca, rn = dernier.get("revenue", math.nan), dernier.get("net_income", math.nan)
    fcf = dernier.get("ocf", math.nan) - (dernier.get("capex", 0.0) if pd.notna(dernier.get("capex")) else 0.0)
    fp = dernier.get("equity", math.nan)
    ancien_ca = connus["revenue"].dropna()
    ancien_ca = ancien_ca[ancien_ca.index <= connus.index[-1] - pd.Timedelta(days=3 * 365 - 30)]
    croissance = (ca / ancien_ca.iloc[-1]) ** (1 / 3) - 1 if len(ancien_ca) and ancien_ca.iloc[-1] > 0 and ca > 0 \
        else math.nan
    actions_3a = a_connues[a_connues.index <= a_connues.index[-1] - pd.Timedelta(days=3 * 365 - 30)]
    dilution = a_connues.iloc[-1] / actions_3a.iloc[-1] - 1 if len(actions_3a) else math.nan
    il_y_a_1m = p_d[p_d.index <= d - pd.Timedelta(days=30)]
    il_y_a_12m = p_d[p_d.index <= d - pd.Timedelta(days=365)]
    mom = float(il_y_a_1m.iloc[-1] / il_y_a_12m.iloc[-1] - 1) if len(il_y_a_1m) and len(il_y_a_12m) else math.nan
    if not (isinstance(ca, float) and ca > 0):
        return None
    return {
        "roe": rn / fp if pd.notna(fp) and fp > 0 else math.nan,
        "marge_op": dernier.get("op_income", math.nan) / ca,
        "marge_fcf": fcf / ca,
        "sobriete": -dilution if math.isfinite(dilution) else math.nan,
        "croissance_ca_3a": croissance,
        "rendement_fcf": fcf / capi,
        "rendement_benefices": rn / capi,
        "mom_12_1": mom,
    }


def note(indic: pd.DataFrame, poids: dict[str, float]) -> pd.Series:
    """Note de 0 à 100 : moyenne pondérée des piliers, eux-mêmes moyennes des rangs centiles de leurs indicateurs."""
    piliers = {}
    for p, cols in PILIERS.items():
        rangs = [indic[c].rank(pct=True) for c in cols if c in indic.columns]
        piliers[p] = pd.concat(rangs, axis=1).mean(axis=1) * 100 if rangs else pd.Series(np.nan, index=indic.index)
    total = sum(piliers[p].fillna(50) * w for p, w in poids.items())
    return total / sum(poids.values())


# --------------------------------------------------------------------------- simulation

def preparer(tickers: list[str], exclure: set[str]) -> dict:
    """Comptes, actions corrigées, cours en euros et capitalisation actuelle des valeurs testables."""
    prix = load_prices()
    ok = [t for t in tickers if t not in exclure and "." not in t and t in prix.columns]
    donnees = {}
    for t in ok:
        d = sec.load(t)
        if not d:
            continue
        c = comptes(d)
        if c.empty or "revenue" not in c.columns or c["revenue"].notna().sum() < 4:
            continue
        info = (load_fundamentals(t) or {}).get("info", {})
        capi = info.get("marketCap")
        if not capi:
            continue
        donnees[t] = {"comptes": c, "actions": actions_corrigees(c.get("shares", pd.Series(dtype=float))),
                      "capi": float(capi)}
    cols = list(donnees)
    eur = prices_in_eur(prix[cols], currency_map(cols), load_fx()) if cols else pd.DataFrame()
    return {"valeurs": donnees, "prix_local": prix[cols], "prix_eur": eur}


def dates_reequilibrage(debut: int, fin: pd.Timestamp, jours: pd.DatetimeIndex) -> list[pd.Timestamp]:
    out = []
    for an in range(debut, fin.year + 1):
        apres = jours[jours >= pd.Timestamp(f"{an}-04-01")]
        if len(apres) and apres[0] < fin:
            out.append(apres[0])
    return out


def simuler(prep: dict, methodes: dict[str, dict[str, float]], n: int = 20, debut: int = 2012,
            reference: pd.Series | None = None) -> dict:
    """Courbes (base 100) de chaque méthode, de l'univers testable à poids égaux, et de la référence ; sélections."""
    eur = prep["prix_eur"]
    if eur.empty:
        return {}
    jours = eur.index
    dates = dates_reequilibrage(debut, jours[-1], jours)
    courbes = {nom: [] for nom in list(methodes) + ["Toutes les valeurs testables (poids égaux)"]}
    selections: dict[str, dict[pd.Timestamp, list[str]]] = {nom: {} for nom in methodes}
    niveaux = {nom: 100.0 for nom in courbes}
    for i, d in enumerate(dates):
        fin = dates[i + 1] if i + 1 < len(dates) else jours[-1]
        lignes = {}
        for t, v in prep["valeurs"].items():
            x = indicateurs_a_date(d, v["comptes"], v["actions"], prep["prix_local"][t], v["capi"])
            if x is not None:
                lignes[t] = x
        indic = pd.DataFrame(lignes).T
        periode = eur.loc[(eur.index >= d) & (eur.index <= fin)]
        if indic.empty or len(periode) < 2:
            continue
        depart = periode.iloc[0]
        valides = [t for t in indic.index if pd.notna(depart.get(t)) and depart[t] > 0]
        indic = indic.loc[valides]
        paniers = {"Toutes les valeurs testables (poids égaux)": valides}
        for nom, poids in methodes.items():
            choix = note(indic, poids).sort_values(ascending=False).head(n).index.tolist()
            paniers[nom] = choix
            selections[nom][d] = choix
        for nom, panier in paniers.items():
            rel = periode[panier].ffill() / depart[panier]  # poids égaux au départ, puis dérive
            valeur = rel.mean(axis=1) * niveaux[nom]
            courbes[nom].append(valeur if not courbes[nom] else valeur.iloc[1:])
            niveaux[nom] = float(valeur.iloc[-1])
    df = pd.DataFrame({nom: pd.concat(s) for nom, s in courbes.items() if s})
    if reference is not None and not df.empty:
        ref = reference.dropna()
        ref = ref[ref.index >= df.index[0]]
        if len(ref):
            df["S&P 500 (en euros)"] = ref / ref.iloc[0] * 100
    return {"courbes": df.ffill(), "selections": selections, "dates": dates,
            "nb_valeurs": len(prep["valeurs"])}


def statistiques(courbe: pd.Series, univers: pd.Series | None = None) -> dict:
    c = courbe.dropna()
    if len(c) < 2:
        return {}
    annees = (c.index[-1] - c.index[0]).days / 365.25
    r = c.pct_change().dropna()
    out = {"rendement_annualise": (c.iloc[-1] / c.iloc[0]) ** (1 / annees) - 1,
           "volatilite": float(r.std() * np.sqrt(252)),
           "perte_maximale": float((c / c.cummax() - 1).min())}
    if univers is not None:
        u = univers.reindex(c.index).ffill()
        ua = (u.iloc[-1] / u.iloc[0]) ** (1 / annees) - 1
        out["ecart_annuel"] = out["rendement_annualise"] - ua
        a = c.resample("YE").last().pct_change().dropna()
        b = u.resample("YE").last().pct_change().dropna()
        commun = a.index.intersection(b.index)
        out["annees_gagnantes"] = float((a[commun] > b[commun]).mean()) if len(commun) else math.nan
    return out
