"""5 years of daily adjusted close + dividends for selected tickers + SPY + AGG.

Primary source is yfinance (free, no key). Twelve Data is the documented fallback
for a ticker yfinance can't resolve -- in practice this is rare for US-listed
equities/ETFs, so it's wired in but not expected to fire often; openFDA-style
"log and skip" if a ticker fails on both.

Writes data/processed/prices.parquet: one column per ticker, 5y of daily adjusted
close. Dividends are written alongside to prices_dividends.parquet (same shape,
0.0 on non-ex-dividend days) -- CLAUDE.md's schema only names prices.parquet, but
quant/'s yield calculations need dividend history, and splitting it out keeps the
main price file exactly the shape the contract describes.
"""
import os
import warnings

import pandas as pd
import requests

from ingest._cache import RateLimiter, cached_fetch

warnings.filterwarnings("ignore", category=FutureWarning, module="yfinance")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES_PATH = os.path.join(HERE, "data", "processed", "prices.parquet")
DIVIDENDS_PATH = os.path.join(HERE, "data", "processed", "prices_dividends.parquet")

BENCHMARK_TICKERS = ["SPY", "AGG"]
PERIOD = "5y"

_td_limiter = RateLimiter(7.5)  # Twelve Data free tier: 8 req/min


def _yfinance_history(ticker):
    import yfinance as yf
    hist = yf.Ticker(ticker).history(period=PERIOD, auto_adjust=False)
    if hist is None or hist.empty:
        return None
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in hist.index],
        "adj_close": hist["Adj Close"].tolist(),
        "dividends": hist["Dividends"].tolist(),
    }


def _twelvedata_history(ticker):
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        return None
    _td_limiter.wait()
    resp = requests.get("https://api.twelvedata.com/time_series", params={
        "symbol": ticker, "interval": "1day", "outputsize": 5000, "apikey": key,
    }, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    values = data.get("values")
    if not values:
        print(f"[prices] Twelve Data has no series for {ticker}: {data.get('message', data)}")
        return None
    values = sorted(values, key=lambda v: v["datetime"])
    return {
        "dates": [v["datetime"] for v in values],
        "adj_close": [float(v["close"]) for v in values],
        "dividends": [None] * len(values),  # Missing distributions are unknown, not zero.
    }


def fetch_history(ticker):
    """-> {"dates": [...], "adj_close": [...], "dividends": [...]} for one ticker,
    trying yfinance first then Twelve Data, or None if both fail."""
    data = cached_fetch("prices_yfinance", {"ticker": ticker}, lambda: _yfinance_history(ticker))
    if data:
        return data
    print(f"[prices] yfinance had nothing for {ticker}, trying Twelve Data")
    data = cached_fetch("prices_twelvedata", {"ticker": ticker}, lambda: _twelvedata_history(ticker))
    if not data:
        print(f"[prices] {ticker}: no price history from yfinance or Twelve Data")
    return data


def fetch_prices(tickers):
    """Fetches 5y history for every ticker in `tickers` plus the benchmarks, and
    (re)writes data/processed/prices.parquet and prices_dividends.parquet.
    -> {ticker: bool} for which tickers actually got data, for run_all.py's
    coverage table.
    """
    wanted = list(dict.fromkeys(list(tickers) + BENCHMARK_TICKERS))
    price_series, div_series, ok = {}, {}, {}

    for ticker in wanted:
        data = fetch_history(ticker)
        if not data:
            ok[ticker] = False
            continue
        s = pd.Series(data["adj_close"], index=pd.to_datetime(data["dates"]), name=ticker)
        d = pd.Series(data["dividends"], index=pd.to_datetime(data["dates"]), name=ticker)
        price_series[ticker] = s[~s.index.duplicated()]
        div_series[ticker] = d[~d.index.duplicated()]
        ok[ticker] = True

    if not price_series:
        print("[prices] nothing fetched for any ticker")
        return ok

    prices_df = pd.DataFrame(price_series).sort_index()
    div_df = pd.DataFrame(div_series).sort_index().fillna(0.0)

    os.makedirs(os.path.dirname(PRICES_PATH), exist_ok=True)
    prices_df.to_parquet(PRICES_PATH)
    div_df.to_parquet(DIVIDENDS_PATH)
    print(f"[prices] wrote {PRICES_PATH}: {prices_df.shape[0]} rows x {prices_df.shape[1]} tickers")
    return ok


def load_prices():
    """-> DataFrame, date index, one column per ticker (adjusted close)."""
    return pd.read_parquet(PRICES_PATH)


def load_dividends():
    """-> DataFrame, date index, one column per ticker (dividend paid that day, 0.0 otherwise)."""
    return pd.read_parquet(DIVIDENDS_PATH)
