"""Min-volatility optimiser with exact dollars and share counts, a relaxation chain and a code-only backtest."""
import numpy as np
import pandas as pd
from pypfopt import DiscreteAllocation, EfficientFrontier, risk_models
from pypfopt.discrete_allocation import get_latest_prices

from . import config as C
from .schemas import Backtest, Holding, Limits, OptimiserResult

BOND_CAP_RELAXED = 0.35
BOND_BUFFER = 0.005         # solve slightly above min_bonds so share rounding cannot push the real mix below it
CAP_TOL = 0.005             # whole shares can overshoot a cap by a little; anything above this fails the check


def _solve(S: pd.DataFrame, caps: dict[str, float], bonds: set[str], yields: dict,
           min_bonds: float, min_yield: float | None) -> dict[str, float]:
    tickers = list(S.columns)
    is_bond = np.array([t in bonds for t in tickers], dtype=float)
    y = np.array([yields.get(t, 0.0) for t in tickers])
    ef = EfficientFrontier(None, S, weight_bounds=[(0, caps[t]) for t in tickers])
    ef.add_constraint(lambda w: w @ is_bond >= min_bonds + min(BOND_BUFFER, max(0.0, 1.0 - min_bonds)))
    if min_yield is not None:
        ef.add_constraint(lambda w: w @ y >= min_yield)
    ef.min_volatility()
    return {t: w for t, w in ef.clean_weights().items() if w > 0}


def backtest(weights: dict[str, float], prices: pd.DataFrame, yields: dict, limits: Limits) -> Backtest:
    """Daily-rebalanced portfolio on the final weights vs a 60/40 SPY/BND mix over the same window."""
    cols = list(weights) + [b for b in ("SPY", "BND") if b not in weights]
    px = prices[cols].dropna()
    rets = px.pct_change().dropna()
    w = pd.Series(weights)
    w = w / w.sum()
    port = (rets[w.index] * w).sum(axis=1)
    bench = rets["SPY"] * 0.6 + rets["BND"] * 0.4
    value = (1 + port).cumprod()
    roll = value.pct_change(252).dropna()
    total, total_b = float(value.iloc[-1] - 1), float((1 + bench).prod() - 1)
    y = float(sum(wt * yields.get(t, 0.0) for t, wt in w.items()))
    worst = float(roll.min()) if len(roll) else None
    return Backtest(
        window_start=str(px.index[0].date()), window_end=str(px.index[-1].date()),
        worst_12m_return=worst, worst_12m_limit=limits.worst_year_limit.value,
        max_drawdown=float((value / value.cummax() - 1).min()), annual_vol=float(port.std() * np.sqrt(252)),
        trailing_yield=y, min_yield=limits.min_yield.value, total_return=total,
        benchmark_6040_return=total_b, vs_6040=total - total_b,
        worst_12m_ok=None if worst is None else worst >= limits.worst_year_limit.value,
        yield_ok=y >= limits.min_yield.value)


def optimise(caps: dict[str, float], bonds: list[str], prices: pd.DataFrame, yields: dict, limits: Limits,
             budget: float = C.BUDGET_USD) -> OptimiserResult:
    """caps: max weight per approved equity (cap > 0 only). Bonds get BOND_MAX_WEIGHT each.

    Relaxation chain: 1) drop the income constraint, 2) raise the bond cap to 0.35, 3) fail loudly.
    min_bonds and the equity caps are never dropped.
    """
    msh = limits.max_single_holding.value if limits.max_single_holding else 1.0
    have = set(prices.columns)
    equities = {t: min(c, msh) for t, c in caps.items() if c > 0 and t in have}
    skipped = [t for t in caps if caps[t] > 0 and t not in have]
    bonds = [b for b in bonds if b in have]
    tickers = list(equities) + bonds
    notes = [f"No price data for {t}, left out." for t in skipped]
    min_bonds = limits.min_bonds.value

    def fail(msg: str, relaxed: list[str]) -> OptimiserResult:
        return OptimiserResult(ok=False, error=msg, relaxed=notes + relaxed)

    # attempts in order: (bond cap, enforce income, what was relaxed)
    attempts = [(C.BOND_MAX_WEIGHT, True, []),
                (C.BOND_MAX_WEIGHT, False, ["Relaxation 1: income target (min_yield) dropped."]),
                (BOND_CAP_RELAXED, False, ["Relaxation 1: income target (min_yield) dropped.",
                                           f"Relaxation 2: bond cap raised from {C.BOND_MAX_WEIGHT:.0%} to {BOND_CAP_RELAXED:.0%} per ETF."])]
    px = prices[tickers].dropna()
    if not bonds or len(px) < 253:
        return fail("Not enough price history or bond ETFs to optimise.", [])
    S = risk_models.CovarianceShrinkage(px).ledoit_wolf()
    last_error = ""
    for bond_cap, income, relaxed in attempts:
        cap = {**equities, **{b: min(bond_cap, msh) for b in bonds}}
        if sum(cap.values()) < 1.0:
            last_error = f"Not enough approved holdings: caps sum to {sum(cap.values()):.0%}, need at least 100%."
            continue
        try:
            weights = _solve(S, cap, set(bonds), yields, min_bonds, limits.min_yield.value if income else None)
        except Exception as e:      # cvxpy / PyPortfolioOpt raise several types for an infeasible problem
            last_error = f"{type(e).__name__}: {str(e)[:120]}"
            continue
        return _finish(weights, cap, set(bonds), px, prices, yields, limits, budget, notes + relaxed, bond_cap)
    if last_error.startswith("Not enough approved holdings"):
        return fail(last_error + " Approve more holdings; the caps were not relaxed.", attempts[-1][2])
    return fail(f"No feasible portfolio even after relaxing the income target and raising the bond cap to "
                f"{BOND_CAP_RELAXED:.0%}. min_bonds={min_bonds:.0%} and the position caps were not relaxed. "
                f"Last solver message: {last_error}", attempts[-1][2])


def _finish(weights, cap, bonds, px, prices, yields, limits, budget, relaxed, bond_cap) -> OptimiserResult:
    latest = get_latest_prices(px)
    alloc, leftover = DiscreteAllocation(weights, latest[list(weights)], total_portfolio_value=budget).greedy_portfolio()
    holdings = []
    for t, n in sorted(alloc.items(), key=lambda kv: -kv[1] * latest[kv[0]]):
        dollars = float(n * latest[t])
        holdings.append(Holding(ticker=t, is_bond=t in bonds, cap=cap[t], target_weight=weights[t], shares=int(n),
                                price=float(latest[t]), dollars=round(dollars, 2), weight=dollars / budget))
    invested = sum(h.dollars for h in holdings)
    bond_share = sum(h.weight for h in holdings if h.is_bond)
    bt = backtest(weights, prices, yields, limits)
    checks = {"bonds_ok": bond_share >= limits.min_bonds.value,
              "caps_ok": all(h.weight <= h.cap + CAP_TOL for h in holdings),
              "budget_ok": invested <= budget,
              "yield_ok": bt.yield_ok}
    return OptimiserResult(ok=True, relaxed=relaxed, bond_cap_used=bond_cap, holdings=holdings,
                           invested_usd=round(invested, 2), cash_usd=round(budget - invested, 2),
                           checks=checks, backtest=bt)
