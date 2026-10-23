"""Minimum volatility, ethical exclusions held fixed, whole-share USD allocation."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from pypfopt import DiscreteAllocation, EfficientFrontier, risk_models
from pypfopt.exceptions import OptimizationError
from scipy.optimize import Bounds, LinearConstraint, milp

from quant.backtest import as_dict, backtest
from quant.stats import validate_prices
from quant.contracts import shared_model

if TYPE_CHECKING:
    Portfolio = shared_model("Portfolio")

TOTAL_USD = 100_000
BOND_ETFS = {"AGG": "iShares Core U.S. Aggregate Bond ETF", "BND": "Vanguard Total Bond Market ETF",
             "IEF": "iShares 7-10 Year Treasury Bond ETF", "TLT": "iShares 20+ Year Treasury Bond ETF"}


def _whole_shares(weights, latest, caps, bonds, yields, min_bonds, min_yield):
    """Start with requested greedy allocation; repair rounding with integer constraints."""
    allocation, _ = DiscreteAllocation(dict(zip(latest.index, weights)), latest,
                                      total_portfolio_value=TOTAL_USD).greedy_portfolio()
    quantities = np.array([allocation.get(t, 0) for t in latest.index], dtype=float)
    p = latest.to_numpy()

    def valid(q):
        dollar = q * p
        return (dollar.sum() <= TOTAL_USD + 1e-6 and
                np.all(dollar <= caps * TOTAL_USD + 1e-6) and
                dollar @ bonds >= min_bonds * TOTAL_USD - 1e-6 and
                dollar @ yields >= min_yield * TOTAL_USD - 1e-6)

    if valid(quantities):
        return quantities.astype(int)
    # Shares and absolute dollar deviations from continuous targets. This repairs
    # cash/rounding feasibility; it does not introduce a return objective.
    n = len(p)
    diagonal = np.diag(p)
    matrix = np.vstack([
        np.r_[p, np.zeros(n)], np.r_[p * bonds, np.zeros(n)],
        np.r_[p * yields, np.zeros(n)],
        np.c_[diagonal, -np.eye(n)], np.c_[-diagonal, -np.eye(n)],
    ])
    lower = np.r_[-np.inf, min_bonds * TOTAL_USD, min_yield * TOTAL_USD, np.full(2*n, -np.inf)]
    upper = np.r_[TOTAL_USD, np.inf, np.inf, weights * TOTAL_USD, -weights * TOTAL_USD]
    result = milp(c=np.r_[np.zeros(n), np.ones(n)], integrality=np.r_[np.ones(n), np.zeros(n)],
                  bounds=Bounds(np.zeros(2*n), np.r_[np.floor(caps * TOTAL_USD / p), np.full(n, np.inf)]),
                  constraints=LinearConstraint(matrix, lower, upper), options={"time_limit": 15})
    if not result.success or result.x is None:
        return None
    quantities = np.rint(result.x[:n]).astype(int)
    return quantities if valid(quantities) else None


def optimise(decisions, rules, prices, *, gbpusd=None, companies=None, register_source=None) -> Portfolio:
    """prices: validated long daily frame, including distributions, SPY and AGG.

    Supply observed USD-per-GBP FX as gbpusd or prices.attrs['gbpusd']; never
    substitute a made-up rate. Optional companies maps ticker -> Company metadata.
    Shared models/registry are imported only at the integration boundary.
    """
    from schemas import Portfolio

    rules = as_dict(rules)
    decisions = [as_dict(d) for d in decisions]
    if len({d["ticker"] for d in decisions}) != len(decisions):
        raise ValueError("Duplicate decisions")
    if gbpusd is None:
        gbpusd = prices.attrs.get("gbpusd")
    if gbpusd is None or not math.isfinite(float(gbpusd)) or float(gbpusd) <= 0:
        raise ValueError("Observed gbpusd (USD per GBP) is required")
    companies = companies or prices.attrs.get("companies", {})
    prices = validate_prices(prices)
    companies = {t: as_dict(c) for t, c in companies.items()}
    constraints = rules["constraints"]
    for key in ("max_weight", "min_bonds", "min_yield"):
        if not 0 <= constraints[key] <= 1:
            raise ValueError(f"Invalid constraint {key}")
    if not -1 <= constraints["max_drawdown"] <= 0:
        raise ValueError("Invalid constraint max_drawdown")
    permitted = {d["ticker"]: d for d in decisions if d["decision"] in ("APPROVE", "APPROVE_CAPPED")}
    excluded = {d["ticker"] for d in decisions if d["decision"] not in ("APPROVE", "APPROVE_CAPPED")}
    available = set(prices.ticker)
    missing = set(permitted) - available
    if missing:
        raise ValueError(f"Approved companies missing prices: {sorted(missing)}")
    bonds = {t for t in available if t in BOND_ETFS or companies.get(t, {}).get("is_bond", False)} - excluded
    symbols = sorted(set(permitted) | bonds)
    relaxed = []
    frame = prices.pivot(index="date", columns="ticker", values="close").sort_index()
    as_of = pd.Timestamp(prices.date.max()).date().isoformat()
    base = dict(charity_id=rules["charity_id"], total_usd=TOTAL_USD, gbpusd=float(gbpusd), as_of=as_of,
                holdings=[], cash_usd=float(TOTAL_USD), risk={}, checks={}, relaxed=relaxed,
                rejected=[d for d in decisions if d["decision"] == "REJECT"],
                trustee_review=[d for d in decisions if d["decision"] == "TRUSTEE_REVIEW"],
                memo="", devils_advocate=[], run_stats={"seconds": 0.0, "llm_calls": 0, "tokens": 0, "by_agent": {}})
    if symbols:
        close = frame[symbols].dropna()
        if len(close) < 253:
            raise ValueError("Optimisation needs at least 253 common price observations")
        if close.index[-1] != frame.index[-1]:
            raise ValueError("Stale prices in optimisation universe")
        as_of = pd.Timestamp(close.index[-1])
        cutoff = as_of - pd.DateOffset(years=1)
        if close.index[0] > cutoff:
            raise ValueError("Optimisation needs a complete calendar year of dividends")
        distributions = prices[prices.date.gt(cutoff) & prices.date.le(as_of)].groupby("ticker").dividends.sum()
        latest = close.iloc[-1]
        yields = (distributions.reindex(symbols) / latest).to_numpy()
        if not np.isfinite(yields).all():
            raise ValueError("Missing trailing dividend observations")
        bond_mask = np.array([t in bonds for t in symbols], dtype=float)
        caps = np.array([permitted[t]["cap"] if t in permitted and t not in bonds else 1.0 for t in symbols])
        if not np.isfinite(caps).all() or np.any(caps < 0) or np.any(caps > 1):
            raise ValueError("Decision caps must lie between zero and one")
        covariance = risk_models.CovarianceShrinkage(close).ledoit_wolf()
        target = constraints["min_yield"]
        attempts = [(caps.copy(), target, None)]
        raised = caps.copy()
        for i, ticker in enumerate(symbols):
            if ticker in permitted and permitted[ticker]["decision"] == "APPROVE_CAPPED" and ticker not in bonds:
                raised[i] = max(caps[i], 0.10)
        if np.any(raised > caps):
            attempts.append((raised.copy(), target, "Raised APPROVE_CAPPED company caps to 0.10; ethics decisions unchanged."))
        while target > 1e-10:
            target = max(0.0, round(target - 0.005, 10))
            attempts.append((raised.copy(), target, f"Lowered minimum yield to {target:.1%}; ethics decisions unchanged."))
        allocation = None
        for active_caps, target, explanation in attempts:
            if explanation:
                relaxed.append(explanation)
            optimiser = EfficientFrontier(None, covariance, weight_bounds=list(zip(np.zeros(len(symbols)), active_caps)))
            optimiser.add_constraint(lambda w: w @ bond_mask >= constraints["min_bonds"])
            optimiser.add_constraint(lambda w: w @ yields >= target)
            try:
                optimiser.min_volatility()
                weights = np.asarray(optimiser.weights)
                allocation = _whole_shares(weights, latest, active_caps, bond_mask, yields, constraints["min_bonds"], target)
            except OptimizationError:
                continue
            if allocation is not None:
                break
        if allocation is not None:
            bond_source = f"Q-{rules['charity_id']}-min_bonds"
            if any(q > 0 and t in bonds for t, q in zip(symbols, allocation)):
                if register_source is None:
                    from sources import register as register_source
                register_source(source_id=bond_source, ticker="", kind="computed", origin="quant",
                                title=f"{rules['name']}: bond constraint", date=base["as_of"],
                                url=f"/api/sources/{bond_source}",
                                section=f"constraints.min_bonds: {constraints['min_bonds']:.1%}; origin: {rules['constraint_origin']['min_bonds']}")
            for i, (ticker, shares) in enumerate(zip(symbols, allocation)):
                if shares <= 0:
                    continue
                is_bond = ticker in bonds
                decision = permitted.get(ticker)
                usd = float(shares * latest[ticker])
                base["holdings"].append(dict(ticker=ticker, name=companies.get(ticker, {}).get("name", BOND_ETFS.get(ticker, ticker)),
                    is_bond=is_bond, usd=usd, shares=int(shares), price=float(latest[ticker]), weight=usd/TOTAL_USD,
                    cap=float(active_caps[i]), reason=(f"Bond constraint: at least {constraints['min_bonds']:.1%} in bonds (constraints.min_bonds)." if is_bond else decision["reason"]),
                    source_ids=([bond_source] if is_bond else decision["source_ids"])))
            base["cash_usd"] = float(TOTAL_USD - sum(h["usd"] for h in base["holdings"]))
        else:
            relaxed.append("No feasible whole-share portfolio after permitted relaxations. Held all funds as cash; bond and yield limits may fail. Ethics decisions unchanged.")
    else:
        relaxed.append("No approved companies or eligible bond ETFs with prices. Held all funds as cash; constraints may fail. Ethics decisions unchanged.")
    # Backtest validates even the all-cash result, and checks ORIGINAL limits.
    return backtest(base, rules, prices)
