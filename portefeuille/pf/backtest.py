"""Backtest d'une allocation cible en euros, dividendes réinvestis, avec rééquilibrages périodiques.

Biais à garder en tête : un portefeuille choisi aujourd'hui avec ce que l'on sait aujourd'hui a
forcément « bien marché » dans le passé (biais rétrospectif et de survie). Le backtest sert à
comprendre le profil de risque (volatilité, pertes maximales, corrélation au marché), pas à prouver
une surperformance future.
"""
from __future__ import annotations

import math

import pandas as pd

from .config import BENCHMARKS
from .data import currency_map, load_fx, load_prices, prices_in_eur

FREQUENCES = {"Aucun (achat-conservation)": None, "Annuel": "YS", "Semestriel": "6MS", "Trimestriel": "QS"}


def eur_prices(tickers: list[str]) -> pd.DataFrame:
    prices = load_prices()
    cols = [t for t in tickers if t in prices.columns]
    eur = prices_in_eur(prices[cols], currency_map(cols), load_fx())
    # Jours fériés propres à chaque place : on reporte le dernier cours (au plus une semaine).
    return eur.ffill(limit=5)


def run_backtest(
    weights: pd.Series,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp | None = None,
    rebalance: str | None = "YS",
    cost_bps: float = 10.0,
    prices: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Valeur quotidienne d'un portefeuille de base 100.

    Une valeur sans historique à une date de rééquilibrage est ignorée et son poids redistribué
    aux autres ; elle entre au premier rééquilibrage où elle a un cours.
    """
    weights = weights[weights > 0]
    px = prices if prices is not None else eur_prices(list(weights.index))
    px = px.reindex(columns=[t for t in weights.index if t in px.columns])
    px = px[(px.index >= pd.Timestamp(start)) & (px.index <= pd.Timestamp(end or px.index.max()))]
    px = px.dropna(how="all").ffill()
    if px.empty:
        return pd.DataFrame(columns=["valeur", "rotation"])
    dates = [px.index[0]]
    if rebalance:
        for mark in pd.date_range(px.index[0], px.index[-1], freq=rebalance):
            i = px.index.searchsorted(mark)
            if i < len(px.index) and px.index[i] > dates[-1]:
                dates.append(px.index[i])
    value = 100.0
    units = None
    out = []
    # Rééquilibrage à la clôture de chaque date ; le segment suivant part de cette même clôture.
    for k, d in enumerate(dates):
        end = dates[k + 1] if k + 1 < len(dates) else px.index[-1]
        prices_d = px.loc[d]
        avail = prices_d.notna() & (prices_d > 0)
        w = weights.reindex(px.columns).where(avail, 0.0).fillna(0.0)
        if w.sum() <= 0:
            continue
        w = w / w.sum()
        if units is None:
            turnover = 1.0  # constitution initiale du portefeuille
        else:
            current = (units * prices_d).fillna(0.0) / value
            turnover = float((w - current).abs().sum() / 2)
        value *= 1 - turnover * cost_bps / 10_000
        units = (w * value / prices_d.where(avail)).fillna(0.0)
        seg = px.loc[d:end]
        seg_val = (seg * units).sum(axis=1, min_count=1)
        frame = pd.DataFrame({"valeur": seg_val, "rotation": 0.0})
        frame.iloc[0, 1] = turnover
        out.append(frame if k == 0 else frame.iloc[1:])
        if k > 0 and len(out) > 1 and not out[-2].empty:
            # La date de rééquilibrage figure déjà en fin de segment précédent : on y reporte la rotation.
            out[-2].iloc[-1, 1] = turnover
        value = float(seg_val.iloc[-1])
    return pd.concat(out) if out else pd.DataFrame(columns=["valeur", "rotation"])


def benchmark_curve(ticker: str, start, end=None) -> pd.Series:
    px = eur_prices([ticker])
    if ticker not in px.columns:
        return pd.Series(dtype=float)
    s = px[ticker].dropna()
    s = s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end or s.index.max()))]
    return s / s.iloc[0] * 100 if not s.empty else s


def drawdown(series: pd.Series) -> pd.Series:
    return series / series.cummax() - 1


def annual_returns(series: pd.Series) -> pd.Series:
    yearly = series.resample("YE").last()
    first = series.iloc[0]
    rets = yearly.pct_change()
    rets.iloc[0] = yearly.iloc[0] / first - 1
    rets.index = rets.index.year
    return rets


def perf_stats(series: pd.Series, bench: pd.Series | None = None, rf: float = 0.02) -> dict:
    s = series.dropna()
    if len(s) < 30:
        return {}
    years = (s.index[-1] - s.index[0]).days / 365.25
    daily = s.pct_change().dropna()
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1 if years > 0 else math.nan
    vol = daily.std() * math.sqrt(252)
    downside = daily[daily < 0].std() * math.sqrt(252)
    mdd = drawdown(s).min()
    monthly = s.resample("ME").last().pct_change().dropna()
    stats = {
        "Rendement annualisé": cagr,
        "Performance totale": s.iloc[-1] / s.iloc[0] - 1,
        "Volatilité": vol,
        "Ratio de Sharpe": (cagr - rf) / vol if vol > 0 else math.nan,
        "Ratio de Sortino": (cagr - rf) / downside if downside > 0 else math.nan,
        "Perte maximale": mdd,
        "Ratio de Calmar": cagr / abs(mdd) if mdd < 0 else math.nan,
        "Mois positifs": (monthly > 0).mean() if len(monthly) else math.nan,
    }
    if bench is not None and len(bench.dropna()) > 30:
        b = bench.reindex(s.index).ffill().dropna()
        # Rendements hebdomadaires : les clôtures européennes et américaines sont décalées de plusieurs
        # heures, ce qui écrase artificiellement corrélation et bêta en données quotidiennes.
        weekly = pd.concat([s, b], axis=1, join="inner").resample("W-FRI").last()
        joined = weekly.pct_change().dropna()
        if len(joined) > 20:
            rp, rb = joined.iloc[:, 0], joined.iloc[:, 1]
            beta = rp.cov(rb) / rb.var() if rb.var() > 0 else math.nan
            b_years = (b.index[-1] - b.index[0]).days / 365.25
            b_cagr = (b.iloc[-1] / b.iloc[0]) ** (1 / b_years) - 1 if b_years > 0 else math.nan
            te = (rp - rb).std() * math.sqrt(52)
            stats.update({
                "Rendement annualisé de l'indice": b_cagr,
                "Surperformance annualisée": cagr - b_cagr,
                "Bêta": beta,
                "Écart de suivi": te,
                "Ratio d'information": (cagr - b_cagr) / te if te > 0 else math.nan,
                "Corrélation": rp.corr(rb),
            })
    return stats


def rolling_excess(series: pd.Series, bench: pd.Series, years: int = 3) -> pd.Series:
    """Surperformance annualisée glissante sur `years` ans (en points de pourcentage)."""
    b = bench.reindex(series.index).ffill()
    window = int(252 * years)
    rp = (series / series.shift(window)) ** (1 / years) - 1
    rb = (b / b.shift(window)) ** (1 / years) - 1
    return (rp - rb).dropna()


def default_benchmarks() -> dict:
    return dict(BENCHMARKS)
