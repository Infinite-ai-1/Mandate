"""Historical risk metrics. Past performance, not a forecast.

Input contract: long daily parquet, columns date, ticker, close, dividends.
`close` must be split-adjusted (but not dividend-adjusted); dividends must be
cash per share on the same split basis. Zero means an observed non-payment.
Missing dividends are not silently interpreted as zero. SPY is required for beta.
Returns are daily price returns; 12 months means 252 trading observations for
rolling returns, and a calendar year for trailing cash distributions.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable

import numpy as np
import pandas as pd
from quant.contracts import shared_model

if TYPE_CHECKING:
    from schemas import Metric

ROOT = Path(__file__).resolve().parents[1]
PRICES_PATH = ROOT / "data/processed/prices.parquet"
RISK_DIR = ROOT / "data/processed/risk"
TRADING_DAYS = 252
LABEL = "past performance, not a forecast"


def load_prices(path: str | Path = PRICES_PATH) -> pd.DataFrame:
    """Read and validate the local daily price contract, without filling gaps."""
    return validate_prices(pd.read_parquet(path))


def validate_prices(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalise a supplied long daily price frame."""
    required = {"date", "ticker", "close", "dividends"}
    if missing := required - set(frame.columns):
        raise ValueError(f"Prices missing required columns: {sorted(missing)}")
    frame = frame[list(sorted(required))].copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="raise").dt.tz_convert(None).dt.normalize()
    if frame[["ticker", "date"]].isna().any().any():
        raise ValueError("Prices contain missing ticker/date values")
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    if frame.duplicated(["ticker", "date"]).any():
        raise ValueError("Prices must have one row per ticker per day")
    for column in ("close", "dividends"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not np.isfinite(frame[column]).all():
            raise ValueError(f"Prices contain missing/non-finite {column}")
    if (frame["close"] <= 0).any() or (frame["dividends"] < 0).any():
        raise ValueError("Prices must be positive and dividends non-negative")
    return frame.sort_values(["ticker", "date"]).reset_index(drop=True)


def calculate_price_metrics(frame: pd.DataFrame, ticker: str) -> tuple[str, dict[str, float]]:
    """Calculate full-precision fractions; reject insufficient histories explicitly."""
    own = frame.loc[frame.ticker == ticker].set_index("date").sort_index()
    spy = frame.loc[frame.ticker == "SPY"].set_index("date").sort_index()
    if own.empty:
        raise ValueError(f"{ticker}: no price history")
    close = own["close"]
    end = close.index[-1]
    start_ttm = end - pd.DateOffset(years=1)
    if len(close) <= TRADING_DAYS or close.index[0] > start_ttm:
        raise ValueError(f"{ticker}: need at least 253 daily prices covering a calendar year")
    if spy.empty:
        raise ValueError("SPY price history is required for beta")
    returns = close.pct_change(fill_method=None).dropna()
    # Align prices first so both returns measure exactly the same intervals.
    paired = pd.concat([close.rename("asset"), spy.close.rename("spy")], axis=1).dropna()
    joint = paired.pct_change(fill_method=None).dropna()
    if len(joint) < TRADING_DAYS or joint.spy.var(ddof=1) <= 0:
        raise ValueError(f"{ticker}: beta needs 252 overlapping returns and non-zero SPY variance")
    values = {
        "annualised_volatility": float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS)),
        "max_drawdown": float((close / close.cummax() - 1).min()),
        "worst_12m": float(close.pct_change(TRADING_DAYS, fill_method=None).dropna().min()),
        "beta": float(joint.asset.cov(joint.spy) / joint.spy.var(ddof=1)),
    }
    if not all(np.isfinite(value) for value in values.values()):
        raise ValueError(f"{ticker}: non-finite computed metric")
    return end.date().isoformat(), values


def calculate_metrics(frame: pd.DataFrame, ticker: str) -> tuple[str, dict[str, float]]:
    """Add observed trailing cash distributions to the price-only statistics."""
    as_of, values = calculate_price_metrics(frame, ticker)
    own = frame.loc[frame.ticker == ticker].set_index("date").sort_index()
    if "dividends" not in own or not np.isfinite(own.dividends).all():
        raise ValueError("Cash dividend history is required; yield cannot be inferred from closes")
    cutoff = pd.Timestamp(as_of) - pd.DateOffset(years=1)
    values["dividend_yield"] = float(own.loc[own.index > cutoff,"dividends"].sum()/own.close.iloc[-1])
    return as_of, values


def compute_all(
    tickers: Iterable[str],
    *,
    prices_path: str | Path = PRICES_PATH,
    output_dir: str | Path = RISK_DIR,
    register_source: Callable | None = None,
) -> dict[str, list[Metric]]:
    """Register computed sources and write {ticker, metrics: [Metric]} files.

    Uses Person 2's shared Metric model and Person 1's registry. An optional
    register_source callback permits isolated offline contract tests. Registry
    receives Source fields as keyword arguments, including the stable source_id.
    All tickers are calculated before writing anything, so validation failures
    cannot leave a partially updated batch. Registry failures propagate.
    """
    Metric = shared_model("Metric")

    if register_source is None:
        from sources import register as register_source

    symbols = list(dict.fromkeys(str(t).upper() for t in tickers))
    for ticker in symbols:
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.^=-]{0,19}", ticker):
            raise ValueError(f"Invalid ticker: {ticker!r}")
    if not symbols:
        return {}
    frame = load_prices(prices_path)
    calculated = {ticker: calculate_metrics(frame, ticker) for ticker in symbols}
    result = {}
    for ticker, (as_of, values) in calculated.items():
        result[ticker] = [Metric(name=name, value=value,
                                 unit="ratio" if name == "beta" else "fraction",
                                 as_of=as_of, source_id=f"Q-{ticker}-{name}")
                          for name, value in values.items()]
    for ticker, metrics in result.items():
        for metric in metrics:
            register_source(
                source_id=metric.source_id, ticker=ticker, kind="computed", origin="quant",
                title=f"{ticker}: {metric.name} ({LABEL})", date=metric.as_of,
                url=f"/api/sources/{metric.source_id}",
                section=f"prices.parquet; daily split-adjusted close and cash dividends; {metric.name}",
            )
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for ticker, metrics in result.items():
        target = destination / f"{ticker}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"ticker": ticker, "metrics": [
            metric.model_dump(mode="json") for metric in metrics
        ]}, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(target)
    return result
