"""Historical constant-weight total-return replay. Past performance, not a forecast."""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.stats import LABEL, TRADING_DAYS, validate_prices
from quant.contracts import shared_model


def as_dict(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)


def replay(holdings, cash_usd, total_usd, rules, prices):
    """Replay final weights daily, cash at zero return; compare on identical dates.

    Includes cash dividends in daily total returns. This is a retrospective
    constant-weight scenario, without trading costs, taxes or return forecasts.
    No forward filling, no partial-window comparisons, no invented cash yield.
    """
    rules = as_dict(rules)
    prices = validate_prices(prices)
    holdings = [as_dict(h) for h in holdings]
    symbols = list(dict.fromkeys([h["ticker"] for h in holdings] + ["SPY", "AGG"]))
    close = prices.pivot(index="date", columns="ticker", values="close").sort_index()
    dividends = prices.pivot(index="date", columns="ticker", values="dividends").sort_index()
    missing = set(symbols) - set(close.columns)
    if missing:
        raise ValueError(f"Backtest missing prices: {sorted(missing)}")
    close = close[symbols]
    dividends = dividends[symbols]
    # Require actual observations and distributions on every retained date.
    valid = close.notna().all(axis=1) & dividends.notna().all(axis=1)
    close, dividends = close.loc[valid], dividends.loc[valid]
    if len(close) <= TRADING_DAYS:
        raise ValueError("Backtest needs at least 253 common daily observations")
    if close.index[0] > close.index[-1] - pd.DateOffset(years=1):
        raise ValueError("Backtest needs a complete calendar year for dividend yield")
    returns = ((close + dividends) / close.shift(1) - 1).iloc[1:]
    weights = pd.Series({h["ticker"]: h["weight"] for h in holdings}, dtype=float)
    if total_usd <= 0 or abs(sum(weights) + cash_usd / total_usd - 1) > 1e-6:
        raise ValueError("Holdings plus cash must reconcile with total_usd")
    portfolio_returns = returns.reindex(columns=weights.index).dot(weights)
    wealth = pd.concat([pd.Series([1.0], index=close.index[:1]), (1 + portfolio_returns).cumprod()])
    benchmark = (1 + 0.6 * returns["SPY"] + 0.4 * returns["AGG"]).cumprod()
    cutoff = close.index[-1] - pd.DateOffset(years=1)
    yields = dividends.loc[dividends.index > cutoff].sum() / close.iloc[-1]
    trailing_yield = float(yields.reindex(weights.index).dot(weights))
    drawdown = float((wealth / wealth.cummax() - 1).min())
    constraints = rules["constraints"]
    bond_weight = sum(h["weight"] for h in holdings if h["is_bond"])
    risk = {
        "worst_12m": float((wealth / wealth.shift(TRADING_DAYS) - 1).dropna().min()),
        "yield": trailing_yield,
        "volatility": float(portfolio_returns.std(ddof=1) * np.sqrt(TRADING_DAYS)),
        "vs_6040_return": float(wealth.iloc[-1] - benchmark.iloc[-1]),
    }
    if not all(np.isfinite(v) for v in risk.values()):
        raise ValueError("Non-finite backtest results")
    checks = {
        "max_drawdown_ok": bool(drawdown >= constraints["max_drawdown"] - 1e-9),
        "yield_ok": bool(trailing_yield >= constraints["min_yield"] - 1e-9),
        "bonds_ok": bool(bond_weight >= constraints["min_bonds"] - 1e-9),
    }
    return risk, checks


def backtest(portfolio, rules, prices):
    """Return a revalidated shared Portfolio with risk/checks populated."""
    Portfolio = shared_model("Portfolio")

    data = as_dict(portfolio)
    data["risk"], data["checks"] = replay(data["holdings"], data["cash_usd"], data["total_usd"], rules, prices)
    explanation = f"{LABEL}; final weights replayed daily with cash dividends, zero cash return, no costs or taxes."
    data["memo"] = (data.get("memo", "") + "\n\n" + explanation).strip()
    return Portfolio.model_validate(data)
