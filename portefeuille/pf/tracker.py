"""Suivi du portefeuille réel à partir du journal des opérations (data/transactions.csv).

Conventions :
- montants en euros ; si `montant_eur` est renseigné (montant réellement débité/crédité, frais
  inclus), il fait foi ; sinon il est recalculé avec le cours du jour et le taux de change ;
- prix de revient unitaire (PRU) au prix moyen pondéré, frais d'achat inclus (règle fiscale française) ;
- si aucun versement n'est saisi, chaque achat non couvert par les espèces est traité comme un apport :
  la performance reste juste même si l'on ne note que les ordres ;
- REPRISE : ligne déjà détenue au début du suivi (import depuis un courtier). Son PRU vient du
  courtier (`montant_eur` = coût total), mais elle entre dans la performance à sa valeur de marché du
  jour : les plus-values passées comptent dans les plus-values latentes, pas dans la performance suivie ;
- une vente ne peut pas dépasser la quantité détenue sur le compte : elle est ramenée à cette quantité
  (montant et frais au prorata) et signalée par `controle_ventes`, plutôt que de créer une position négative ;
- chaque écriture du journal est précédée d'une copie dans data/sauvegardes (30 dernières conservées).
"""
from __future__ import annotations

import math
import shutil
from datetime import date, datetime

import numpy as np
import pandas as pd

from .config import SAUVEGARDES_DIR, TRANSACTIONS_CSV, read_csv_fr, write_csv_fr
from .data import currency_map, fx_rate, load_fx, load_prices, prices_in_eur

TYPES = ["ACHAT", "VENTE", "DIVIDENDE", "VERSEMENT", "RETRAIT", "FRAIS", "REPRISE"]
TITRES = ("ACHAT", "VENTE", "REPRISE")
COMPTES = ["PEA", "CTO"]
COLONNES = ["date", "compte", "type", "ticker", "quantite", "prix_unitaire", "devise", "frais_eur",
            "montant_eur", "taux_change", "note"]
_ORDRE = {"REPRISE": -1, "VERSEMENT": 0, "VENTE": 1, "DIVIDENDE": 2, "ACHAT": 3, "FRAIS": 4, "RETRAIT": 5}
_NUM = ("quantite", "prix_unitaire", "frais_eur", "montant_eur", "taux_change")


# --------------------------------------------------------------------------- journal

def load_transactions() -> pd.DataFrame:
    if not TRANSACTIONS_CSV.exists():
        return pd.DataFrame(columns=COLONNES)
    df = read_csv_fr(TRANSACTIONS_CSV, numeric=_NUM)
    for col in COLONNES:
        if col not in df.columns:
            df[col] = np.nan if col in _NUM else ""
    iso = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
    # Saisie sous Excel à la française (jj/mm/aaaa) : seules les dates non ISO sont relues ainsi.
    df["date"] = iso.fillna(pd.to_datetime(df["date"].where(iso.isna()), format="%d/%m/%Y", errors="coerce"))
    df = df.dropna(subset=["date"])
    df["type"] = df["type"].str.upper().str.strip()
    df["compte"] = df["compte"].str.upper().str.strip().replace("", "CTO")
    df["ordre"] = df["type"].map(_ORDRE).fillna(9)
    df = df.sort_values(["date", "ordre"], kind="stable").drop(columns="ordre").reset_index(drop=True)
    return df[COLONNES]


GARDER_SAUVEGARDES = 30


def sauvegarder_journal() -> None:
    """Copie datée du journal avant toute écriture : une ligne supprimée par erreur se retrouve."""
    if not TRANSACTIONS_CSV.exists():
        return
    SAUVEGARDES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TRANSACTIONS_CSV, SAUVEGARDES_DIR / f"transactions-{datetime.now():%Y%m%d-%H%M%S-%f}.csv")
    for ancienne in sorted(SAUVEGARDES_DIR.glob("transactions-*.csv"))[:-GARDER_SAUVEGARDES]:
        ancienne.unlink()


def append_transaction(row: dict) -> None:
    append_transactions([row])


def append_transactions(rows: list[dict]) -> None:
    df = load_transactions()
    new = pd.DataFrame([{c: row.get(c, "") for c in COLONNES} for row in rows])
    out = pd.concat([df, new], ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    sauvegarder_journal()
    write_csv_fr(out, TRANSACTIONS_CSV)


def save_transactions(df: pd.DataFrame) -> None:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    sauvegarder_journal()
    write_csv_fr(out[COLONNES], TRANSACTIONS_CSV)


def _num(v) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return math.nan
    return v if np.isfinite(v) else math.nan


def amount_eur(row: pd.Series, fx: pd.DataFrame) -> float:
    """Montant de l'opération en euros, toujours positif (le sens dépend du type)."""
    m = _num(row.get("montant_eur"))
    if np.isfinite(m):
        return abs(m)
    kind = row["type"]
    if kind in TITRES:
        gross = _num(row.get("quantite")) * _num(row.get("prix_unitaire"))
        devise = row.get("devise") or "EUR"
        rate = _num(row.get("taux_change"))  # unités de devise pour 1 EUR, tel qu'indiqué par le courtier
        gross_eur = gross / rate if np.isfinite(rate) and rate > 0 else gross * fx_rate(fx, devise, "EUR", row["date"])
        fees = _num(row.get("frais_eur"))
        fees = fees if np.isfinite(fees) else 0.0
        return gross_eur - fees if kind == "VENTE" else gross_eur + fees
    p = _num(row.get("prix_unitaire"))
    return abs(p) if np.isfinite(p) else 0.0


# --------------------------------------------------------------------------- contrôle des ventes

def quantite_detenue(tx: pd.DataFrame, compte: str, ticker: str, jusqua=None) -> float:
    """Quantité détenue sur un compte, à une date incluse (par défaut : aujourd'hui)."""
    if tx.empty:
        return 0.0
    t = controle_ventes(tx)[0]
    t = t[(t["compte"] == compte) & (t["ticker"] == ticker) & t["type"].isin(TITRES)]
    if jusqua is not None:
        t = t[t["date"] <= pd.Timestamp(jusqua)]
    q = pd.to_numeric(t["quantite"], errors="coerce").fillna(0.0)
    return float((q * np.where(t["type"] == "VENTE", -1, 1)).sum())


def controle_ventes(tx: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Ramène chaque vente à la quantité détenue sur son compte, dans l'ordre chronologique.

    Renvoie le journal corrigé (montant et frais réduits au prorata) et la liste des corrections : une
    saisie erronée ne doit ni créer une position négative ni inventer une plus-value.
    """
    out = tx.copy()
    held: dict[tuple, float] = {}
    anomalies = []
    for i, r in out.iterrows():
        if r["type"] not in TITRES or not r["ticker"]:
            continue
        key, q = (r["compte"], r["ticker"]), _num(r["quantite"])
        if not np.isfinite(q):
            continue
        dispo = held.get(key, 0.0)
        if r["type"] != "VENTE":
            held[key] = dispo + q
            continue
        if q > dispo + 1e-9:
            jour = pd.Timestamp(r["date"]).strftime("%d/%m/%Y")
            ratio = max(dispo, 0.0) / q
            for col in ("quantite", "montant_eur", "frais_eur"):
                v = _num(r[col])
                if np.isfinite(v):
                    out.at[i, col] = v * ratio
            if dispo <= 1e-9:
                anomalies.append(f"{jour} : vente de {q:g} {r['ticker']} ({r['compte']}) sans position détenue, ignorée")
            else:
                anomalies.append(f"{jour} : vente de {q:g} {r['ticker']} ({r['compte']}) ramenée aux {dispo:g} détenues")
            q = dispo
        held[key] = dispo - q
    return out, anomalies


# --------------------------------------------------------------------------- positions

def positions(tx: pd.DataFrame | None = None) -> pd.DataFrame:
    """Lignes détenues par compte : quantité, PRU, coût, valeur actuelle, plus-values, dividendes."""
    tx = load_transactions() if tx is None else tx
    if tx.empty:
        return pd.DataFrame()
    tx = controle_ventes(tx)[0]
    fx = load_fx()
    state: dict[tuple[str, str], dict] = {}
    for _, r in tx.iterrows():
        if r["type"] not in (*TITRES, "DIVIDENDE") or not r["ticker"]:
            continue
        key = (r["compte"], r["ticker"])
        s = state.setdefault(key, {"quantite": 0.0, "cout": 0.0, "pv_realisee": 0.0, "dividendes": 0.0,
                                   "premier_achat": r["date"]})
        amt = amount_eur(r, fx)
        q = _num(r["quantite"])
        if r["type"] in ("ACHAT", "REPRISE"):
            s["quantite"] += q
            s["cout"] += amt
        elif r["type"] == "VENTE" and s["quantite"] > 0:
            pru = s["cout"] / s["quantite"]
            s["pv_realisee"] += amt - q * pru
            s["cout"] -= q * pru
            s["quantite"] -= q
        elif r["type"] == "DIVIDENDE":
            s["dividendes"] += amt
    rows = []
    prices = load_prices()
    tickers = sorted({t for _, t in state})
    eur = prices_in_eur(prices[[t for t in tickers if t in prices.columns]], currency_map(tickers), fx)
    last = eur.ffill().iloc[-1] if not eur.empty else pd.Series(dtype=float)
    for (compte, ticker), s in state.items():
        qty = round(s["quantite"], 8)
        price = float(last.get(ticker, math.nan))
        value = qty * price if qty else 0.0
        rows.append({
            "compte": compte, "ticker": ticker, "quantite": qty,
            "pru_eur": s["cout"] / qty if qty else math.nan,
            "cout_eur": s["cout"] if qty else 0.0,
            "cours_eur": price, "valeur_eur": value,
            "pv_latente_eur": value - s["cout"] if qty else 0.0,
            "pv_latente_pct": value / s["cout"] - 1 if qty and s["cout"] else math.nan,
            "pv_realisee_eur": s["pv_realisee"], "dividendes_eur": s["dividendes"],
            "premier_achat": s["premier_achat"],
        })
    df = pd.DataFrame(rows)
    total = df["valeur_eur"].sum()
    df["poids"] = df["valeur_eur"] / total if total else 0.0
    return df.sort_values("valeur_eur", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------- historique & performance

def history(tx: pd.DataFrame | None = None, compte: str | None = None) -> pd.DataFrame:
    """Valeur quotidienne (titres + espèces) et flux externes, en euros."""
    tx = load_transactions() if tx is None else tx
    if compte:
        tx = tx[tx["compte"] == compte]
    if tx.empty:
        return pd.DataFrame()
    tx = controle_ventes(tx)[0]
    fx = load_fx()
    prices = load_prices()
    tickers = sorted(t for t in tx["ticker"].unique() if t)
    eur = prices_in_eur(prices[[t for t in tickers if t in prices.columns]], currency_map(tickers), fx)
    start = tx["date"].min()
    idx = eur.index[eur.index >= start] if not eur.empty else pd.DatetimeIndex([])
    idx = idx.union(pd.DatetimeIndex(tx["date"].unique()))
    eur = eur.reindex(idx).ffill()

    units = pd.DataFrame(0.0, index=idx, columns=tickers)
    cash_delta = pd.Series(0.0, index=idx)
    flows = pd.Series(0.0, index=idx)
    cash: dict[str, float] = {}
    for _, r in tx.iterrows():
        acct, kind, d = r["compte"], r["type"], r["date"]
        amt = amount_eur(r, fx)
        sign = {"ACHAT": -1, "VENTE": 1, "DIVIDENDE": 1, "VERSEMENT": 1, "RETRAIT": -1, "FRAIS": -1}.get(kind, 0)
        if kind in TITRES and r["ticker"]:
            units.loc[d, r["ticker"]] += _num(r["quantite"]) * (-1 if kind == "VENTE" else 1)
        if kind == "REPRISE":
            # Titres apportés : flux externe à leur valeur de marché du jour, sans mouvement d'espèces.
            px = eur.at[d, r["ticker"]] if r["ticker"] in eur.columns else math.nan
            flows[d] += _num(r["quantite"]) * px if np.isfinite(px) else amt
            continue
        c = cash.get(acct, 0.0) + sign * amt
        if kind in ("VERSEMENT", "RETRAIT"):
            flows[d] += sign * amt
        if c < -0.005:  # achat non couvert : apport implicite
            flows[d] += -c
            cash_delta[d] += -c
            c = 0.0
        cash_delta[d] += sign * amt
        cash[acct] = c
    held = units.cumsum()
    securities = (held * eur.reindex(columns=tickers)).sum(axis=1, min_count=1).fillna(0.0)
    especes = cash_delta.cumsum()
    out = pd.DataFrame({
        "valeur_titres": securities, "especes": especes, "valeur_totale": securities + especes,
        "flux_externes": flows, "apports_cumules": flows.cumsum(),
    })
    return out


def twr(hist: pd.DataFrame) -> pd.Series:
    """Performance pondérée par le temps (indépendante du calendrier des versements), base 100."""
    v, f = hist["valeur_totale"], hist["flux_externes"]
    prev = v.shift(1).fillna(0.0) + f
    r = (v / prev.where(prev > 0) - 1).fillna(0.0)
    return 100 * (1 + r).cumprod()


def xirr(dates: list, amounts: list[float]) -> float:
    """TRI annualisé de flux datés (convention investisseur : apports négatifs, valeur finale positive)."""
    if not dates or all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
        return math.nan
    t0 = min(dates)
    years = np.array([(d - t0).days / 365.25 for d in dates])
    amt = np.array(amounts, dtype=float)

    def npv(rate):
        return float((amt / (1 + rate) ** years).sum())

    try:
        from scipy.optimize import brentq  # import différé (démarrage)

        return brentq(npv, -0.99, 10.0)
    except ValueError:
        return math.nan


def money_weighted(hist: pd.DataFrame) -> float:
    f = hist["flux_externes"]
    f = f[f != 0]
    dates = list(f.index) + [hist.index[-1]]
    amounts = list(-f.values) + [float(hist["valeur_totale"].iloc[-1])]
    return xirr(dates, amounts)


def rendement_argent(hist: pd.DataFrame) -> tuple[float, bool]:
    """Rendement de votre argent (versements compris) et vrai s'il est annualisé.

    Il n'est annualisé qu'au-delà d'un an : sur quelques jours, +0,8 % deviendrait +64 % « par an ».
    En deçà, c'est le rendement de la période.
    """
    irr = money_weighted(hist)
    f = hist["flux_externes"]
    debut = f[f != 0].index.min() if (f != 0).any() else hist.index[0]
    annees = (hist.index[-1] - debut).days / 365.25
    if annees >= 1 or not np.isfinite(irr):
        return irr, True
    return (1 + irr) ** annees - 1, False


def benchmark_shadow(hist: pd.DataFrame, ticker: str) -> pd.Series:
    """Valeur qu'aurait atteinte le même argent, versé aux mêmes dates, dans l'ETF de référence."""
    prices = load_prices()
    if ticker not in prices.columns:
        return pd.Series(dtype=float)
    b = prices_in_eur(prices[[ticker]], currency_map([ticker]), load_fx())[ticker]
    b = b.reindex(hist.index.union(b.index)).ffill().reindex(hist.index)
    units = (hist["flux_externes"] / b).fillna(0.0).cumsum()
    return units * b


def realized_by_year(tx: pd.DataFrame | None = None) -> pd.DataFrame:
    """Plus-values réalisées (PMP) et dividendes par année et par compte : utile pour la déclaration."""
    tx = load_transactions() if tx is None else tx
    if tx.empty:
        return pd.DataFrame()
    tx = controle_ventes(tx)[0]
    fx = load_fx()
    state: dict[tuple, list[float]] = {}
    rows = []
    for _, r in tx.iterrows():
        key = (r["compte"], r["ticker"])
        qty_cost = state.setdefault(key, [0.0, 0.0])
        amt = amount_eur(r, fx)
        q = _num(r["quantite"])
        if r["type"] in ("ACHAT", "REPRISE"):
            qty_cost[0] += q
            qty_cost[1] += amt
        elif r["type"] == "VENTE" and qty_cost[0] > 0:
            pru = qty_cost[1] / qty_cost[0]
            rows.append({"annee": r["date"].year, "compte": r["compte"], "pv_realisee": amt - q * pru, "dividendes": 0.0,
                         "cessions": amt})
            qty_cost[1] -= q * pru
            qty_cost[0] -= q
        elif r["type"] == "DIVIDENDE":
            rows.append({"annee": r["date"].year, "compte": r["compte"], "pv_realisee": 0.0, "dividendes": amt,
                         "cessions": 0.0})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).groupby(["annee", "compte"]).sum().reset_index()


# --------------------------------------------------------------------------- apport mensuel

def contribution_plan(
    amount: float,
    compte: str,
    targets: pd.Series,
    envelopes: pd.Series,
    pos: pd.DataFrame | None = None,
    min_order: float = 300.0,
    fractional: bool = False,
    max_orders: int | None = None,
    prices_eur: pd.Series | None = None,
) -> pd.DataFrame:
    """Répartit un apport sur les lignes les plus sous-pondérées du compte, sans rien vendre.

    Algorithme glouton : on achète toujours la ligne la plus en retard sur sa cible, pour au moins
    `min_order` euros (frais de courtage). Une action plus chère que le besoin n'est achetée que si
    elle ne dépasse pas ce besoin de plus de 50 % : une valeur chère (ASML…) attend que le compte
    soit assez gros pour ne pas déséquilibrer le portefeuille.

    `targets` : poids cibles du portefeuille modèle (somme 1, tous comptes confondus) ;
    `envelopes` : enveloppe (PEA/CTO) de chaque valeur cible.
    """
    pos = positions() if pos is None else pos
    in_acct = targets[envelopes.reindex(targets.index) == compte]
    if in_acct.empty or amount <= 0:
        return pd.DataFrame()
    w = in_acct / in_acct.sum()
    held = pd.Series(0.0, index=w.index)
    if pos is not None and not pos.empty:
        p = pos[pos["compte"] == compte].groupby("ticker")["valeur_eur"].sum()
        held = p.reindex(w.index).fillna(0.0)
    if prices_eur is None:
        prices = load_prices()
        cols = [t for t in w.index if t in prices.columns]
        eur = prices_in_eur(prices[cols], currency_map(cols), load_fx()).ffill()
        prices_eur = eur.iloc[-1] if not eur.empty else pd.Series(dtype=float)
    prices_eur = prices_eur.reindex(w.index)
    target_value = w * (held.sum() + amount)
    if max_orders:
        # Nombre d'ordres limité : on retient les lignes les plus en retard (et achetables), puis on leur
        # répartit tout l'apport au prorata de leurs poids cibles, quitte à dépasser un peu leur cible.
        gap0 = (target_value - held).sort_values(ascending=False)
        chosen = [t for t in gap0.index if gap0[t] > 0 and prices_eur.get(t, math.inf) <= amount][:max_orders]
        if chosen:
            wc = w[chosen] / w[chosen].sum()
            target_value = held.copy()
            target_value[chosen] += wc * amount
    planned = held.copy()
    qty = pd.Series(0.0, index=w.index)
    budget = amount
    while True:
        gap = (target_value - planned).sort_values(ascending=False)
        bought = False
        for t in gap.index:
            price = float(prices_eur.get(t, math.nan))
            if gap[t] <= 0 or not np.isfinite(price) or price <= 0 or price > budget:
                continue
            want = max(gap[t], min_order if qty[t] == 0 else 0.0)
            q = want / price if fractional else math.floor(want / price)
            if q == 0:
                # Une seule action dépasse déjà le besoin : on ne l'achète que si le dépassement reste
                # limité, sinon elle attendra que le compte ait grossi.
                if price > 1.5 * want:
                    continue
                q = 1
            q = min(q, budget / price if fractional else math.floor(budget / price))
            cost = q * price
            if q <= 0 or (qty[t] == 0 and cost < 0.5 * min_order):
                continue
            qty[t] += q
            planned[t] += cost
            budget -= cost
            bought = True
            break
        if not bought or budget <= 0.01:
            break
    bought_mask = qty > 0
    if not bought_mask.any():
        return pd.DataFrame()
    df = pd.DataFrame({
        "ticker": qty[bought_mask].index,
        "quantite": qty[bought_mask].round(6).values,
        "cours_eur": prices_eur[bought_mask].values,
        "montant_eur": (qty * prices_eur)[bought_mask].values,
        "poids_cible_compte": w[bought_mask].values,
        "valeur_avant": held[bought_mask].values,
    }).sort_values("montant_eur", ascending=False).reset_index(drop=True)
    df["poids_apres"] = df["ticker"].map(planned / planned.sum())
    df.attrs["reste"] = budget
    return df


NOTE_APPORT = "Apport du mois"


def ordres_deja_saisis(tx: pd.DataFrame, plan: pd.DataFrame, compte: str, jour) -> set[str]:
    """Ordres du plan déjà présents dans le journal ce jour-là (même compte, valeur et quantité)."""
    if tx.empty or plan.empty:
        return set()
    j = tx[(tx["date"] == pd.Timestamp(jour)) & (tx["type"] == "ACHAT") & (tx["compte"] == compte)
           & tx["note"].astype(str).str.startswith(NOTE_APPORT)]
    deja = set()
    for _, o in plan.iterrows():
        q = pd.to_numeric(j.loc[j["ticker"] == o["ticker"], "quantite"], errors="coerce")
        if (abs(q - o["quantite"]) < 1e-6).any():
            deja.add(o["ticker"])
    return deja


def drift_alerts(pos: pd.DataFrame, targets: pd.Series, threshold: float = 0.03) -> pd.DataFrame:
    """Écarts entre poids réels et cibles (tous comptes confondus)."""
    if pos is None or pos.empty:
        return pd.DataFrame()
    actual = pos.groupby("ticker")["valeur_eur"].sum()
    actual = actual / actual.sum()
    df = pd.DataFrame({"poids_reel": actual, "poids_cible": targets}).fillna(0.0)
    df["ecart"] = df["poids_reel"] - df["poids_cible"]
    df["action"] = np.select(
        [df["ecart"] > threshold, df["ecart"] < -threshold],
        ["Alléger ou ne plus renforcer", "Renforcer en priorité"], default="Dans la cible",
    )
    return df.sort_values("ecart")


def today() -> date:
    return date.today()
