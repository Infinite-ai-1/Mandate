# Quant integration

Latest integration check: main `627d556` introduces `mandate/schemas.py`, but
it has neither Metric nor Portfolio and uses a different decision/rules shape
from AGENTS.md. `contracts.py` supports both root `schemas` and `mandate.schemas`
when the required contract models exist; otherwise it raises an explanatory
error. No substitute production schemas are defined in quant. The team must
reconcile the shared contract before real integration.

`python -m quant.check_team_stubs` reads the fetched `origin/stubs` branch
without modifying it. Those prices are wide daily closes with no cash dividends.
The diagnostic computes the four price-risk metrics for PM, MMM, XYL, SPY and
AGG and writes `examples/team-stub-validation.json`. Dividend yield remains
explicitly unavailable. It is not a complete production Metric file and is
never substituted for one. A complete dividend history and agreed ingest
layout remain required for yield-constrained optimisation.

`stats.compute_all(tickers)` reads `data/processed/prices.parquet`, imports the
shared `schemas.Metric`, calls `sources.register(**source_fields)` once per metric,
and writes `data/processed/risk/{ticker}.json`. It returns ticker -> Metric list.
No network calls. Source IDs are stable and repeat runs require registry upserts.
The registry's actual signature must be checked when Person 1 adds `sources.py`.

Price input: long daily rows with `date`, `ticker`, `close`, `dividends`; include
SPY. Close must be split-adjusted, excluding dividend adjustments. Cash dividends
per share must use the same split basis. Missing values, duplicate dates,
non-positive prices, and insufficient history raise explicit errors.
If ingest uses a different parquet layout, agree its layout before adapting.

Metrics: `annualised_volatility` uses sample standard deviation of daily price
returns times sqrt(252); `max_drawdown` uses daily running peaks; `worst_12m` uses
252 trading observations; `beta` uses sample covariance over overlapping price
dates against SPY; `dividend_yield` sums distributions over (as_of minus one
calendar year, as_of], divided by latest close. Fraction metrics use unit
`fraction` (0.03 means 3%); beta uses `ratio`. These are historical price-risk
statistics, not a total-return backtest or a forecast. Require at least 253
observations covering a full calendar year, including 252 overlapping returns
for beta. Inputs should already be daily trading sessions.

The repository initially contains neither shared models, registry nor stubs.
Isolated tests use a strict Pydantic Metric double and synthetic parquet, never
production fallback models. `python -m unittest quant.test_stats` runs the tests;
`python -m quant.demo_stats` reproduces `examples/`, which is SYNTHETIC ONLY and
must not be served as real market data. Install `quant/requirements.txt` first.

Shared integration and real-data validation remain pending until those modules
arrive. Past performance, not a forecast.

## Optimiser and backtest

`optimiser.optimise(decisions, rules, prices, *, gbpusd=None, companies=None,
register_source=None)` accepts shared models or matching dictionaries; prices
is a validated long dataframe. Supply observed USD-per-GBP `gbpusd` explicitly
or as `prices.attrs['gbpusd']`. Company metadata may be passed as a ticker map
or in `prices.attrs['companies']`. Metadata is used for names and bond flags.
Without names the ticker is the label; a missing FX rate raises an error.

Only APPROVE/APPROVE_CAPPED names and available bond ETFs enter the universe.
REJECT/TRUSTEE_REVIEW always exclude an asset, including bond ETFs. Bond ETF
defaults are AGG, BND, IEF and TLT; metadata can identify other bond ETFs.
Equities use the Decision cap exactly; bonds have an upper bound of one.
Ledoit-Wolf covariance and minimum volatility use PyPortfolioOpt, without
expected return estimates. The constraints require full continuous investment,
the specified minimum bond weight, and cash-distribution yield.

On infeasibility, APPROVE_CAPPED caps below 0.10 rise to 0.10, followed by
minimum-yield reductions in 0.005 steps down to zero. Each attempted relaxation
is recorded. Ethics decisions and original rule inputs are never mutated.
DiscreteAllocation greedy provides whole shares; a SciPy integer repair is
used only when rounding breaks caps, yield or bond constraints. It minimises
absolute dollar deviation from continuous target weights. Feasible allocations
cannot overspend. If no permitted relaxation yields an allocation, all funds
remain cash and `relaxed` explains why; original checks expose unmet limits.
Missing/invalid market data is an explicit error, never a relaxation.

Bond holdings cite a registered computed source for `constraints.min_bonds`
and its policy/assumed origin. Other holding reasons/source IDs are copied from
the Decision. `backtest.backtest(portfolio, rules, prices)` also works separately;
it returns a validated shared Portfolio. `optimise` calls it automatically.
Final dollar weights are replayed as a daily rebalanced total-return scenario,
including cash dividends and cash at zero return. SPY/AGG use the same common
dates and a daily rebalanced 60/40 benchmark. `vs_6040_return` is the difference
in cumulative returns, not a ratio or annualised return. All risk/check outputs
are ordinary finite numbers. Drawdown checks use peak-to-trough total-return
drawdown; the displayed worst rolling twelve months is a separate statistic.
Original trustee constraints determine checks even after relaxation.

The Portfolio memo always labels the result "past performance, not a forecast"
and explains costs/taxes are excluded. `presentation.py` supplies API-side
display totals without extending the Portfolio/Selection JSON schemas.
