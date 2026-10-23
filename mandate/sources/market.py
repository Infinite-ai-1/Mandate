"""yfinance: prices, trailing yield, fundamentals and risk stats, all cached under cache/."""
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import yfinance as yf

from .. import config as C

PRICES = C.CACHE_DIR / "prices.csv"
FUNDAMENTALS = C.CACHE_DIR / "fundamentals.json"
RISK_STATS = C.CACHE_DIR / "risk_stats.json"
YIELDS = C.CACHE_DIR / "yields.json"
FUND_KEYS = ["profitMargins", "operatingMargins", "returnOnEquity", "debtToEquity", "currentRatio",
             "revenueGrowth", "freeCashflow", "marketCap", "sector", "longBusinessSummary"]


def _load_json(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_json(path, data: dict) -> None:
    C.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def load_prices() -> pd.DataFrame:
    processed = C.ROOT / "data" / "processed" / "prices.parquet"
    if PRICES.exists():
        return pd.read_csv(PRICES, index_col=0, parse_dates=True)
    if processed.exists():
        return pd.read_parquet(processed)
    return pd.DataFrame()


def fetch_prices(tickers: list[str], force: bool = False) -> pd.DataFrame:
    """3 years of daily auto-adjusted closes. Only downloads tickers missing from the cache."""
    have = load_prices()
    missing = [t for t in tickers if force or t not in have.columns]
    if missing and not C.DEMO_MODE:
        raw = yf.download(missing, period=f"{C.PRICE_YEARS}y", auto_adjust=True, progress=False)["Close"]
        if isinstance(raw, pd.Series):
            raw = raw.to_frame(missing[0])
        raw = raw.dropna(axis=1, how="all")
        for t in [m for m in missing if m not in raw.columns]:     # batch downloads sometimes drop a ticker
            one = yf.download(t, period=f"{C.PRICE_YEARS}y", auto_adjust=True, progress=False)["Close"]
            raw[t] = one.iloc[:, 0] if hasattr(one, "columns") else one
        have = raw.combine_first(have[[c for c in have.columns if c not in raw.columns]]) if len(have) else raw
        C.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        have.sort_index().to_csv(PRICES)
    return have[[t for t in tickers if t in have.columns]]


def trailing_yield(ticker: str, last_price: float) -> float:
    """Dividends paid in the last 365 days / last price. Not info['dividendYield'] (units changed)."""
    div = yf.Ticker(ticker).dividends
    if div is None or len(div) == 0 or not last_price:
        return 0.0
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    idx = div.index.tz_convert("UTC") if div.index.tz else div.index.tz_localize("UTC")
    return float(div[idx >= cutoff].sum() / last_price)


def fetch_yields(tickers: list[str], prices: pd.DataFrame, force: bool = False) -> dict:
    out = _load_json(YIELDS)
    for t in tickers:
        if (force or t not in out) and not C.DEMO_MODE and t in prices.columns:
            out[t] = trailing_yield(t, float(prices[t].dropna().iloc[-1]))
    _save_json(YIELDS, out)
    return out


def fundamentals(ticker: str) -> dict:
    info = yf.Ticker(ticker).info or {}
    return {k: info.get(k) for k in FUND_KEYS}


def fetch_fundamentals(tickers: list[str], force: bool = False) -> dict:
    out = _load_json(FUNDAMENTALS)
    for t in tickers:
        if (force or t not in out) and not C.DEMO_MODE:
            try:
                out[t] = fundamentals(t)
            except Exception as e:      # yfinance is flaky; one bad ticker must not stop the run
                print(f"  fundamentals {t}: {type(e).__name__}: {e}")
    _save_json(FUNDAMENTALS, out)
    return out


def risk_stats(prices: pd.DataFrame, benchmark: str = "SPY") -> dict:
    """annual_vol, max_drawdown, worst_12m_return, beta_vs_spy per ticker, all computed here."""
    rets = prices.pct_change()
    out = {}
    for t in prices.columns:
        p = prices[t].dropna()
        if len(p) < 253:
            continue
        r = p.pct_change().dropna()
        joined = pd.concat([r, rets[benchmark]], axis=1, join="inner").dropna() if benchmark in prices else None
        beta = None
        if joined is not None and joined.iloc[:, 1].var() > 0:
            beta = float(joined.iloc[:, 0].cov(joined.iloc[:, 1]) / joined.iloc[:, 1].var())
        out[t] = {
            "annual_vol": float(r.std() * np.sqrt(252)),
            "max_drawdown": float((p / p.cummax() - 1).min()),
            "worst_12m_return": float(p.pct_change(252).min()),
            "beta_vs_spy": beta,
        }
    return out


def compute_risk_stats(prices: pd.DataFrame) -> dict:
    stats = _load_json(RISK_STATS)
    stats.update(risk_stats(prices))
    _save_json(RISK_STATS, stats)
    return stats
