"""Phase 3 acceptance check: optimiser on 10 dummy approved equities + 4 bond ETFs, using cached yfinance data.

Run: python scripts/test_phase3.py   (downloads any missing prices once, then uses cache/)
"""
import math
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mandate import config as C  # noqa: E402
from mandate import universe  # noqa: E402
from mandate.agents.compiler import merge_limits  # noqa: E402
from mandate.optimise import optimise  # noqa: E402
from mandate.schemas import StatedLimits  # noqa: E402
from mandate.sources import market  # noqa: E402

EQUITIES = ["XYL", "ECL", "AWK", "ABT", "TMO", "DHR", "MSFT", "AAPL", "COST", "PG"]
CAPS = {t: (C.CAP_BY_DECISION["full"] if i < 6 else C.CAP_BY_DECISION["reduced"]) for i, t in enumerate(EQUITIES)}
failed = 0


def check(label: str, ok: bool) -> None:
    global failed
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    failed += not ok


prices = market.fetch_prices(universe.price_tickers(EQUITIES))
yields = market.fetch_yields(EQUITIES + universe.BONDS, prices)
limits = merge_limits(StatedLimits())      # all defaults: min_bonds 30%, min_yield 2.5%, worst year -15%

print(f"Data: {prices.shape[1]} tickers x {prices.shape[0]} days; caps: 6 full (10%) + 4 reduced (5%) equities, bonds 25% each")
r = optimise(CAPS, universe.BONDS, prices, yields, limits)
print("\n1. Dummy portfolio, default limits")
if not r.ok:
    raise SystemExit(f"optimiser failed: {r.error}")
print(f"{'ticker':7s}{'$':>11s}{'shares':>8s}{'price':>9s}{'weight':>8s}{'cap':>6s}")
for h in r.holdings:
    print(f"{h.ticker:7s}{h.dollars:>11,.2f}{h.shares:>8d}{h.price:>9.2f}{h.weight:>8.1%}{h.cap:>6.0%}{'  bond' if h.is_bond else ''}")
bond_w = sum(h.weight for h in r.holdings if h.is_bond)
print(f"invested ${r.invested_usd:,.2f}, cash ${r.cash_usd:,.2f}, bonds {bond_w:.1%}, relaxed: {r.relaxed or 'nothing'}")
bt = r.backtest
print(f"backtest {bt.window_start} to {bt.window_end} (past performance, not a forecast)")
print(f"  worst 12m {bt.worst_12m_return:+.1%} (limit {bt.worst_12m_limit:+.0%})  max drawdown {bt.max_drawdown:.1%}  "
      f"vol {bt.annual_vol:.1%}  yield {bt.trailing_yield:.2%} (target {bt.min_yield:.1%})")
print(f"  total return {bt.total_return:+.1%} vs 60/40 SPY/BND {bt.benchmark_6040_return:+.1%} (diff {bt.vs_6040:+.1%})")
check("shares are whole numbers and total dollars < $100,000", all(isinstance(h.shares, int) for h in r.holdings)
      and sum(h.shares * h.price for h in r.holdings) < C.BUDGET_USD)
check("invested + cash == budget", abs(r.invested_usd + r.cash_usd - C.BUDGET_USD) < 0.01)
check(f"bonds {bond_w:.1%} >= min_bonds 30%", r.checks["bonds_ok"])
check("every position within its cap", r.checks["caps_ok"])
check("each bond ETF <= 25%", all(h.weight <= 0.25 + 0.005 for h in r.holdings if h.is_bond))
check("yield >= 2.5% target, nothing relaxed", r.checks["yield_ok"] and not r.relaxed)
check("backtest numbers are finite", all(math.isfinite(v) for v in
      (bt.worst_12m_return, bt.max_drawdown, bt.annual_vol, bt.trailing_yield, bt.total_return, bt.vs_6040)))

print("\n2. Income target unreachable (min_yield 8%) -> step 1: income constraint dropped")
r2 = optimise(CAPS, universe.BONDS, prices, yields, merge_limits(StatedLimits(min_yield=0.08)))
print(f"  ok={r2.ok} relaxed={r2.relaxed} yield_ok={r2.checks.get('yield_ok')}")
check("relaxed by dropping income only, still shows yield_ok False", r2.ok and len(r2.relaxed) == 1
      and "income" in r2.relaxed[0] and r2.checks["yield_ok"] is False and r2.checks["bonds_ok"])

print("3. min_bonds 80% with only 3 bond ETFs at 25% (max 75%) -> step 2: bond cap raised to 35%")
r3 = optimise(CAPS, ["SHY", "IEF", "TIP"], prices, yields, merge_limits(StatedLimits(min_bonds=0.80)))
print(f"  ok={r3.ok} bond_cap_used={r3.bond_cap_used} relaxed={r3.relaxed}")
check("bond cap raised and recorded, min_bonds still held", r3.ok and r3.bond_cap_used == 0.35
      and len(r3.relaxed) == 2 and r3.checks["bonds_ok"])

print("4. Impossible min_bonds -> step 3: clear failure, nothing silently dropped")
r4 = optimise(CAPS, universe.BONDS, prices, yields, merge_limits(StatedLimits(min_bonds=1.5)))
print(f"  ok={r4.ok}\n  error: {r4.error}")
check("fails with a clear message", not r4.ok and "min_bonds=150%" in r4.error and not r4.holdings)

print("5. Too few approved holdings (caps sum < 100%)")
r5 = optimise({"XYL": 0.10}, ["SHY"], prices, yields, limits)
print(f"  ok={r5.ok}\n  error: {r5.error[:110]}")
check("reports not enough approved holdings", not r5.ok and "Not enough approved holdings" in r5.error)

print(f"\n{'ALL CHECKS PASSED' if not failed else str(failed) + ' CHECK(S) FAILED'}")
sys.exit(1 if failed else 0)
