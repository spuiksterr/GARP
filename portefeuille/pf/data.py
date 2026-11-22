"""Récupération et mise en cache des données de marché.

Sources : Yahoo Finance (via yfinance) pour les cours, les fondamentaux et le consensus ; Banque centrale
européenne pour les taux de change, Yahoo servant alors de secours et de point de comparaison.

Cache local :
- data/cache/prix.parquet           cours ajustés (dividendes réinvestis) en devise de cotation
- data/cache/fx.parquet             taux EURxxx (unités de devise pour 1 EUR)
- data/cache/fondamentaux/*.json    profil, états financiers annuels + 12 mois glissants, bilan trimestriel, consensus
- data/cache/controles.json         résultat des recoupements entre sources
"""
from __future__ import annotations

import io
import re
import time
import urllib.request
import warnings
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import numpy as np
import pandas as pd

# yfinance déclenche des avertissements de dépréciation de pandas en rafale : on ne fait taire que les
# siens, pour que ceux de notre propre code restent visibles.
warnings.filterwarnings("ignore", module=r"yfinance")
import yfinance as yf  # noqa: E402

from . import esef, sec  # noqa: E402

ESEF_PAR_MAJ = 60  # nouvelles sociétés européennes lues par mise à jour (une vingtaine de secondes chacune)
from .config import (  # noqa: E402
    BENCHMARKS,
    CONTROLES_JSON,
    FUND_DIR,
    FX_PARQUET,
    PRICES_PARQUET,
    SUBUNITS,
    ecrire_json,
    ecriture_atomique,
    fund_tickers,
    lire_json,
    load_model_portfolio,
)

INFO_KEYS = [
    "longName", "shortName", "country", "sector", "industry", "currency", "financialCurrency",
    "exchange", "quoteType", "marketCap", "currentPrice", "regularMarketPrice", "previousClose",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "trailingPE", "forwardPE", "priceToBook", "beta",
    "returnOnEquity", "grossMargins", "operatingMargins", "profitMargins", "revenueGrowth",
    "earningsGrowth", "dividendRate", "trailingAnnualDividendYield", "payoutRatio",
    "recommendationMean", "recommendationKey", "numberOfAnalystOpinions", "targetMeanPrice",
    "targetLowPrice", "targetHighPrice", "sharesOutstanding", "fullTimeEmployees",
    "longBusinessSummary", "website",
]

# Sections d'une fiche de fondamentaux ; sans les trois premières, aucun indicateur n'est fiable.
SECTIONS_ESSENTIELLES = ("income", "balance", "cashflow")
SECTIONS = (*SECTIONS_ESSENTIELLES, "ttm_income", "ttm_cashflow", "balance_q", "eps_estimate", "revenue_estimate")

SUFFIX_CURRENCY = {
    "PA": "EUR", "AS": "EUR", "DE": "EUR", "MI": "EUR", "MC": "EUR", "BR": "EUR", "IR": "EUR",
    "HE": "EUR", "LS": "EUR", "VI": "EUR", "L": "GBp", "SW": "CHF", "CO": "DKK", "ST": "SEK",
    "OL": "NOK", "TO": "CAD", "V": "CAD", "T": "JPY", "HK": "HKD", "WA": "PLN", "AT": "EUR",
}


# --------------------------------------------------------------------------- devises

def guess_currency(ticker: str) -> str:
    if ticker.endswith("=X"):
        return ticker[3:6]
    suffix = ticker.rsplit(".", 1)[1] if "." in ticker else ""
    return SUFFIX_CURRENCY.get(suffix, "USD")


def split_currency(code: str | None) -> tuple[str, float]:
    """« GBp » -> (« GBP », 0.01) : devise de référence + facteur de conversion du cours."""
    if not code:
        return "EUR", 1.0
    if code in SUBUNITS:
        return SUBUNITS[code]
    return code.upper(), 1.0


def currency_of(ticker: str, fundamentals: dict | None = None) -> str:
    if fundamentals and fundamentals.get("info", {}).get("currency"):
        return fundamentals["info"]["currency"]
    return guess_currency(ticker)


# --------------------------------------------------------------------------- utilitaires

def _safe_name(ticker: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", ticker)


def _clean(v):
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


def _frame_to_dict(df: pd.DataFrame | None) -> dict:
    """États financiers yfinance (lignes = postes, colonnes = dates) -> {poste: {date: valeur}}."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    out: dict[str, dict[str, float]] = {}
    for row in df.index:
        values = {}
        for col in df.columns:
            v = _clean(df.at[row, col])
            if v is not None:
                values[pd.Timestamp(col).strftime("%Y-%m-%d")] = v
        if values:
            out[str(row)] = values
    return out


def _with_retry(fn: Callable, tries: int = 3, pause: float = 2.0):
    last = None
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:  # yfinance lève des exceptions variées (réseau, quota, parsing)
            last = exc
            time.sleep(pause * (attempt + 1))
    raise last  # type: ignore[misc]


# --------------------------------------------------------------------------- fondamentaux

def fetch_fundamentals(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = _with_retry(lambda: t.info) or {}
    if not info.get("marketCap") and not (info.get("currentPrice") or info.get("regularMarketPrice")):
        raise ValueError(f"{ticker} : aucune donnée renvoyée par Yahoo (ticker invalide ou renommé ?)")
    data: dict = {
        "ticker": ticker,
        "fetched": datetime.now().isoformat(timespec="seconds"),
        "info": {k: _clean(info.get(k)) for k in INFO_KEYS},
    }
    for key, attr in [
        ("income", "financials"), ("balance", "balance_sheet"), ("cashflow", "cashflow"),
        ("ttm_income", "ttm_income_stmt"), ("ttm_cashflow", "ttm_cashflow"),
        ("balance_q", "quarterly_balance_sheet"),  # dette et trésorerie au dernier trimestre
    ]:
        try:
            data[key] = _frame_to_dict(_with_retry(lambda a=attr: getattr(t, a), tries=2))
        except Exception:  # refus ponctuel de Yahoo : section notée manquante plus bas
            data[key] = {}
    for key, attr in [("eps_estimate", "earnings_estimate"), ("revenue_estimate", "revenue_estimate")]:
        try:
            df = getattr(t, attr)
            data[key] = {
                str(p): {c: _clean(df.at[p, c]) for c in df.columns if c != "currency"}
                for p in df.index
            } if isinstance(df, pd.DataFrame) and not df.empty else {}
        except Exception:
            data[key] = {}
    data["manquantes"] = [k for k in SECTIONS if not data.get(k)]
    return data


def fundamentals_path(ticker: str):
    return FUND_DIR / f"{_safe_name(ticker)}.json"


def load_fundamentals(ticker: str) -> dict | None:
    """Fiche en cache ; None si absente ou illisible (elle sera alors retéléchargée)."""
    fund = lire_json(fundamentals_path(ticker))
    return fund if isinstance(fund, dict) and fund.get("fetched") else None


def incomplete(fund: dict | None) -> bool:
    """Compte de résultat, bilan ou flux absent : sans eux, les indicateurs seraient faux ou vides."""
    return bool(fund) and any(not fund.get(k) for k in SECTIONS_ESSENTIELLES)


def save_fundamentals(ticker: str, data: dict) -> None:
    """Enregistre une fiche ; une section que Yahoo n'a pas renvoyée cette fois garde sa version précédente.

    Yahoo refuse parfois une requête sur une rafale : sans cette reprise, une fiche complète serait
    remplacée par une fiche à trous, et les indicateurs calculés comme si la société n'avait pas de bilan.
    """
    ancien = load_fundamentals(ticker) or {}
    reprises = [k for k in data.get("manquantes", []) if ancien.get(k)]
    for k in reprises:
        data[k] = ancien[k]
    data["sections_reprises"] = reprises
    ecrire_json(fundamentals_path(ticker), data)


def fundamentals_age_days(ticker: str) -> float | None:
    fund = load_fundamentals(ticker)
    if not fund:
        return None
    return (datetime.now() - datetime.fromisoformat(fund["fetched"])).total_seconds() / 86400


def update_fundamentals(
    tickers: list[str],
    max_age_days: float = 7,
    workers: int = 6,
    progress: Callable[[int, int, str], None] | None = None,
    max_refresh: int | None = None,
    priority: set[str] | None = None,
) -> dict:
    """Rafraîchit les fondamentaux plus vieux que `max_age_days`. Renvoie {"ok": [...], "erreurs": {...}}.

    `max_refresh` limite le nombre de fiches par passage : `priority` d'abord, puis les plus anciennes.
    """
    FUND_DIR.mkdir(parents=True, exist_ok=True)
    age = {t: fundamentals_age_days(t) or 1e9 for t in tickers}
    # Une fiche à trous est retentée dès le lendemain, avant les fiches simplement anciennes.
    a_trous = {t for t in tickers if 1 < age[t] < 1e9 and incomplete(load_fundamentals(t))}
    todo = [t for t in tickers if age[t] > max_age_days or t in a_trous]
    if max_refresh:
        todo = sorted(todo, key=lambda t: (t not in (priority or ()), t not in a_trous, -age[t]))[:max_refresh]
    result = {"ok": [], "erreurs": {}, "a_jour": len(tickers) - len(todo)}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_fundamentals, t): t for t in todo}
        for fut in as_completed(futures):
            tk = futures[fut]
            done += 1
            try:
                save_fundamentals(tk, fut.result())
                result["ok"].append(tk)
            except Exception as exc:
                result["erreurs"][tk] = str(exc)[:200]
            if progress:
                progress(done, len(todo), tk)
    # Seconde chance, en séquentiel : la plupart des échecs viennent du quota de requêtes Yahoo.
    for tk in list(result["erreurs"]):
        time.sleep(2)
        try:
            save_fundamentals(tk, fetch_fundamentals(tk))
            result["ok"].append(tk)
            del result["erreurs"][tk]
        except Exception as exc:
            result["erreurs"][tk] = str(exc)[:200]
    return result


# --------------------------------------------------------------------------- cours & devises

def _download_close(tickers: list[str], start: str) -> pd.DataFrame:
    try:
        with warnings.catch_warnings():  # dépréciations pandas en rafale, émises depuis les fils de yfinance
            warnings.simplefilter("ignore")
            raw = yf.download(
                tickers, start=start, auto_adjust=True, progress=False, threads=True, group_by="column"
            )
    except Exception:
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
    else:
        close = raw[["Close"]].rename(columns={"Close": tickers[0]})
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    close = close[~close.index.duplicated(keep="last")].sort_index()
    return close[[c for c in close.columns if close[c].notna().any()]]


LOT_COURS = 100  # valeurs par requête : 120 cours récents arrivent en 5 secondes quand Yahoo répond bien
RELANCES_MAX_S = 90  # au-delà, les valeurs encore manquantes gardent leurs anciens cours


def _download_batch(tickers: list[str], start: str, chunk: int = LOT_COURS) -> pd.DataFrame:
    """Téléchargement par lots, puis relance des valeurs manquantes : d'abord par lots, une à une ensuite
    seulement s'il en reste peu, et jamais plus de RELANCES_MAX_S secondes.

    Yahoo rejette parfois un lot entier quand il est surchargé : relancer chacune de ses valeurs une à une, trois
    fois, a déjà fait durer une mise à jour douze minutes.
    """
    frames, missing = [], []
    for i in range(0, len(tickers), chunk):
        part = tickers[i : i + chunk]
        close = _download_close(part, start)
        frames.append(close)
        missing += [t for t in part if t not in close.columns]
        time.sleep(1)
    fin_relances = time.time() + RELANCES_MAX_S
    for tour in range(3):
        if not missing or time.time() > fin_relances:
            break
        time.sleep(3 * (tour + 1))
        taille = chunk if len(missing) > 10 else 1  # par lots tant qu'il en manque beaucoup
        still = []
        for i in range(0, len(missing), taille):
            part = missing[i : i + taille]
            if time.time() > fin_relances:
                still += part
                continue
            close = _download_close(part, start)
            frames.append(close)
            still += [t for t in part if t not in close.columns]
            time.sleep(0.5)
        missing = still
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    close = pd.concat(frames, axis=1)
    close = close.loc[:, ~close.columns.duplicated(keep="last")]
    return close[~close.index.duplicated(keep="last")].sort_index()


def _splice(old: pd.Series, fresh: pd.Series) -> pd.Series:
    """Raccorde un historique ancien à des cours récents.

    Les cours « ajustés » de Yahoo sont recalculés à chaque détachement de dividende : on remet
    l'ancien historique à l'échelle du nouveau sur la première date commune.
    """
    o, f = old.dropna(), fresh.dropna()
    if f.empty:
        return o
    common = o.index.intersection(f.index)
    if common.empty or o[common[0]] <= 0:
        return pd.concat([o[o.index < f.index[0]], f])
    anchor = common[0]
    return pd.concat([o[o.index < anchor] * (f[anchor] / o[anchor]), f[f.index >= anchor]])


def update_prices(
    tickers: list[str], start: str = "2010-01-01", chunk: int = LOT_COURS, full: bool = False
) -> pd.DataFrame:
    """Met à jour le cache des cours de clôture ajustés (dividendes réinvestis, divisions).

    Par défaut, seules les ~6 dernières semaines sont téléchargées pour les valeurs déjà en cache ;
    l'historique complet n'est récupéré que pour les nouvelles valeurs (ou si `full=True`).
    """
    tickers = sorted(set(tickers) | set(BENCHMARKS))
    old = pd.DataFrame() if full else load_prices()
    known = [t for t in tickers if t in old.columns and old[t].notna().any()]
    new = [t for t in tickers if t not in known]
    series: dict[str, pd.Series] = {c: old[c].dropna() for c in old.columns}
    if new:
        hist = _download_batch(new, start, chunk)
        series.update({c: hist[c].dropna() for c in hist.columns})
    if known:
        since = (old.index.max() - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
        fresh = _download_batch(known, since, chunk)
        for c in fresh.columns:
            series[c] = _splice(series[c], fresh[c])
    close = pd.DataFrame(series).sort_index()
    close = close[~close.index.duplicated(keep="last")].dropna(how="all")
    close = close.astype("float64")
    ecriture_atomique(PRICES_PARQUET, close.to_parquet)
    return close


def _lire_parquet(path) -> pd.DataFrame:
    """Parquet en cache ; vide s'il est absent ou illisible (il sera alors retéléchargé)."""
    try:
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()
    except (OSError, ValueError):
        return pd.DataFrame()


def load_prices() -> pd.DataFrame:
    return _lire_parquet(PRICES_PARQUET)


ECB_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.{}.EUR.SP00.A?startPeriod={}&format=csvdata&detail=dataonly"
SEUIL_ECART_FX = 0.01


def fetch_ecb_fx(currencies: set[str], start: str = "2010-01-01") -> pd.DataFrame:
    """Cours de référence quotidiens de la BCE (unités de devise pour 1 EUR). Vide si le service ne répond pas."""
    try:
        with urllib.request.urlopen(ECB_URL.format("+".join(sorted(currencies)), start), timeout=60) as resp:
            raw = pd.read_csv(io.BytesIO(resp.read()))
    except Exception:
        return pd.DataFrame()
    raw = raw.dropna(subset=["OBS_VALUE"])
    if raw.empty:
        return pd.DataFrame()
    out = raw.pivot_table(index="TIME_PERIOD", columns="CURRENCY", values="OBS_VALUE")
    out.index = pd.to_datetime(out.index)
    out.columns.name = None
    # Une devise que la BCE ne publie plus (dollar de Taïwan…) est laissée à Yahoo.
    recent = out.index.max() - pd.Timedelta(days=30)
    return out.sort_index()[[c for c in out.columns if out[c].last_valid_index() >= recent]]


def fx_crosscheck(ref: pd.DataFrame, other: pd.DataFrame, days: int = 90) -> dict[str, float]:
    """Écart relatif médian entre deux sources de change sur les `days` derniers jours communs, par devise.

    Médian et non maximal : la BCE fixe ses cours à 14 h 15, Yahoo retient la clôture de Londres ;
    quelques dixièmes de point d'écart sur une journée agitée sont normaux.
    """
    out = {}
    for c in ref.columns.intersection(other.columns):
        both = pd.concat([ref[c], other[c]], axis=1, keys=["a", "b"]).dropna()
        both = both[both.index >= ref.index.max() - pd.Timedelta(days=days)]
        if len(both) >= 10:
            out[c] = float((both["b"] / both["a"] - 1).abs().median())
    return out


def save_controle(key: str, value) -> None:
    ctl = load_controles()
    ctl[key] = {"date": datetime.now().isoformat(timespec="seconds"), "resultat": value}
    ecrire_json(CONTROLES_JSON, ctl, indent=1)


def load_controles() -> dict:
    return lire_json(CONTROLES_JSON, {}) or {}


def update_fx(currencies: set[str], start: str = "2010-01-01") -> pd.DataFrame:
    """Taux EURxxx quotidiens. Colonne = devise, valeur = unités de devise pour 1 EUR.

    Source principale : cours de référence de la BCE. Yahoo comble les devises ou les jours absents
    (jours fériés du calendrier TARGET, cours du jour pas encore publié) et sert de contrôle.
    """
    currencies = {split_currency(c)[0] for c in currencies} | {"USD", "GBP", "CHF"}
    currencies.discard("EUR")
    symbols = {f"EUR{c}=X": c for c in sorted(currencies)}
    # Incrémental : les 100 derniers jours pour les devises déjà en cache (assez pour le contrôle BCE / Yahoo
    # sur 90 jours), tout l'historique pour une nouvelle devise. Tout retélécharger prenait près d'une minute.
    ancien = load_fx()
    nouvelles = {c for c in currencies if c not in ancien.columns or ancien[c].notna().sum() == 0}
    recent = (ancien.index.max() - pd.Timedelta(days=100)).strftime("%Y-%m-%d") if not ancien.empty else start
    lots = [(sorted(currencies - nouvelles), recent), (sorted(nouvelles), start)]
    ecb_parts, yahoo_parts = [], []
    for devises, debut in lots:
        if not devises:
            continue
        ecb_parts.append(fetch_ecb_fx(set(devises), debut))
        yahoo_parts.append(_download_close([f"EUR{c}=X" for c in devises], debut).rename(columns=symbols))
    def reunir(parts: list[pd.DataFrame]) -> pd.DataFrame:
        """Fusionne les lots ; une devise présente dans deux lots n'est gardée qu'une fois."""
        out = pd.DataFrame()
        for x in parts:
            if not x.empty:
                x = x.loc[:, ~x.columns.duplicated()]
                out = x if out.empty else out.combine_first(x)
        return out

    ecb, close = reunir(ecb_parts), reunir(yahoo_parts)
    for _ in range(3):  # Yahoo refuse parfois une paire isolée : on la redemande seule, si la BCE ne l'a pas
        missing = [sym for sym, c in symbols.items() if (c not in close.columns or close[c].notna().sum() == 0)
                   and c not in ecb.columns]
        if not missing:
            break
        time.sleep(2)
        for sym in missing:
            one = _download_close([sym], recent if symbols[sym] not in nouvelles else start).rename(columns=symbols)
            if not one.empty:
                close = one.combine_first(close)
    if not ecb.empty:
        save_controle("change", {"source": "BCE", "ecart_median_yahoo": fx_crosscheck(ecb, close),
                                 "absentes_bce": sorted(currencies - set(ecb.columns))})
        close = ecb.combine_first(close)
    else:
        save_controle("change", {"source": "Yahoo (BCE injoignable)"})
    # Une paire non reçue ne doit jamais effacer un historique déjà acquis.
    close = close.combine_first(load_fx().drop(columns="EUR", errors="ignore"))
    # Les séries FX Yahoo contiennent parfois des points aberrants : on filtre les sauts > 15 % isolés.
    for col in close.columns:
        s = close[col]
        jump = (s / s.rolling(5, min_periods=1, center=True).median() - 1).abs()
        close.loc[jump > 0.15, col] = np.nan
    close = close.ffill()
    close["EUR"] = 1.0
    close = close.astype("float64")
    ecriture_atomique(FX_PARQUET, close.to_parquet)
    return close


def load_fx() -> pd.DataFrame:
    return _lire_parquet(FX_PARQUET)


def fx_rate(fx: pd.DataFrame, from_cur: str, to_cur: str, date=None) -> float:
    """Combien d'unités de `to_cur` vaut 1 unité de `from_cur` (au dernier cours, ou à `date`)."""
    a, fa = split_currency(from_cur)
    b, fb = split_currency(to_cur)
    if a == b:
        return fa / fb
    if fx.empty or a not in fx.columns or b not in fx.columns:
        return float("nan")
    rows = fx if date is None else fx.loc[: pd.Timestamp(date)]
    if rows.empty:
        rows = fx
    eur_a, eur_b = rows[a].dropna(), rows[b].dropna()
    if eur_a.empty or eur_b.empty:
        return float("nan")
    return (eur_b.iloc[-1] / eur_a.iloc[-1]) * fa / fb


def prices_in_eur(prices: pd.DataFrame, currencies: dict[str, str], fx: pd.DataFrame) -> pd.DataFrame:
    """Convertit chaque série de cours dans l'euro du jour (taux du jour reporté sur les jours fériés)."""
    if prices.empty:
        return prices
    idx = prices.index.union(fx.index) if not fx.empty else prices.index
    fx_aligned = fx.reindex(idx).ffill().bfill().reindex(prices.index) if not fx.empty else None
    out = {}
    for col in prices.columns:
        cur, factor = split_currency(currencies.get(col) or guess_currency(col))
        s = prices[col] * factor
        if cur != "EUR":
            if fx_aligned is None or cur not in fx_aligned.columns:
                continue
            s = s / fx_aligned[cur]
        out[col] = s
    return pd.DataFrame(out, index=prices.index)


def currency_map(tickers: list[str]) -> dict[str, str]:
    cmap = {}
    for t in tickers:
        cmap[t] = currency_of(t, load_fundamentals(t))
    for b in BENCHMARKS:
        cmap.setdefault(b, "EUR")
    return cmap


# --------------------------------------------------------------------------- tout-en-un

def update_all(
    tickers: list[str],
    max_age_days: float = 7,
    progress: Callable[[str], None] | None = None,
    max_refresh: int | None = None,
    rapide: bool = False,
) -> dict:
    """Téléchargements de la mise à jour. `rapide` : cours, changes et sources annexes seulement (pas de
    fondamentaux ni de comptes SEC ou ESEF), pour un passage quotidien en quelques minutes.

    La durée de chaque étape est rendue dans `durees` (secondes).
    """
    say = progress or (lambda msg: None)
    durees: dict[str, float] = {}
    funds = fund_tickers()
    stocks = [t for t in tickers if t not in funds]  # un ETF n'a pas d'états financiers
    fres = {"ok": [], "erreurs": {}, "a_jour": len(stocks)}
    sres: dict = {"ok": [], "erreurs": {}}
    eres: dict = {"ok": [], "erreurs": {}, "reste": 0}
    if not rapide:
        t0 = time.time()
        say(f"Fondamentaux : {len(stocks)} valeurs (rafraîchis si > {max_age_days:g} jours)…")
        fres = update_fundamentals(
            stocks, max_age_days=max_age_days, progress=lambda i, n, t: say(f"  {i}/{n} {t}"), max_refresh=max_refresh,
            priority=set(load_model_portfolio().index),
        )
        durees["Fondamentaux"] = time.time() - t0
        t0 = time.time()
        say("Comptes déposés à la SEC (valeurs américaines)…")
        sres = sec.update(stocks, progress=lambda i, n, t: say(f"  SEC {i}/{n} {t}") if i % 50 == 0 or i == n else None)
        if sres.get("saute"):
            say(f"  étape sautée : {sres['saute']}")
        durees["Comptes SEC"] = time.time() - t0
        t0 = time.time()
        say("Rapports annuels européens (ESEF, 60 nouvelles sociétés au plus par mise à jour)…")
        eres = esef.update(stocks, load_fundamentals, maximum=ESEF_PAR_MAJ,
                           progress=lambda i, n, t: say(f"  ESEF {i}/{n} {t}") if i % 10 == 0 or i == n else None)
        durees["Rapports européens"] = time.time() - t0
    t0 = time.time()
    say("Portefeuilles de grands investisseurs (13F) et transactions d'élus…")
    try:  # sources annexes : un échec ne doit pas bloquer la mise à jour
        from . import congres, investisseurs
        ires, cres = investisseurs.mettre_a_jour(), congres.mettre_a_jour()
        say(f"  {ires.get('nouvelles', 0)} trimestres de gérants, {cres['nouveaux']} rapports d'élus lus")
    except Exception as exc:
        say(f"  étape sautée : {str(exc)[:120]}")
    durees["Grands investisseurs et élus"] = time.time() - t0
    t0 = time.time()
    say("Actualités de vos valeurs…")
    try:
        from . import actualites
        from .config import load_universe
        ares = actualites.mettre_a_jour(load_universe()["nom"].to_dict())
        say(f"  {ares['lues']} valeurs lues")
    except Exception as exc:
        say(f"  étape sautée : {str(exc)[:120]}")
    durees["Actualités"] = time.time() - t0
    t0 = time.time()
    say("Cours historiques…")
    prices = update_prices(tickers)
    durees["Cours"] = time.time() - t0
    t0 = time.time()
    # Devises : celles des cotations, celles déjà suivies, et celles des comptes des fiches rafraîchies (une
    # nouvelle valeur en fait partie). Relire les 1 100 fiches pour cela prenait plusieurs secondes.
    currencies = set(currency_map(tickers).values()) | set(load_fx().columns)
    for t in fres["ok"]:
        fund = load_fundamentals(t)
        if fund and fund["info"].get("financialCurrency"):
            currencies.add(fund["info"]["financialCurrency"])
    say("Taux de change…")
    update_fx(currencies)
    durees["Changes"] = time.time() - t0
    stale = [t for t in tickers if t not in prices.columns or prices[t].dropna().empty]
    return {
        "rapide": rapide,
        "fondamentaux_ok": len(fres["ok"]),
        "fondamentaux_deja_a_jour": fres["a_jour"],
        "sec_ok": len(sres["ok"]),
        "sec_saute": sres.get("saute"),
        "esef_ok": len(eres["ok"]), "esef_reste": eres["reste"],
        "erreurs": {**fres["erreurs"], **{f"SEC {t}": e for t, e in sres["erreurs"].items()},
                    **{f"ESEF {t}": e for t, e in eres["erreurs"].items()}},
        "sans_cours": stale,
        "derniere_date": str(prices.index.max().date()) if not prices.empty else None,
        "durees": durees,
    }
