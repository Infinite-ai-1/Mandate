"""Synthetic 5y daily adjusted closes for the stub tickers -> stubs/prices.csv.

Seeded random walk with per-ticker drift/vol roughly matching stubs/risk/*.json.
Same shape as the real data/processed/prices.parquet: date index, one column per ticker.
"""
import csv, datetime as dt, math, os, random, sys

OUT = os.path.join(sys.argv[1], "stubs", "prices.csv")
TICKERS = {  # start price, annual drift, annual vol
    "PM":  (92.50, 0.09, 0.213),
    "MMM": (118.00, 0.02, 0.274),
    "XYL": (104.00, 0.11, 0.246),
    "SPY": (430.00, 0.08, 0.165),
    "AGG": (97.00, 0.015, 0.054),
}
END = dt.date(2026, 10, 22)
days = []
d = END
while len(days) < 1260:                      # ~5 years of weekdays
    if d.weekday() < 5:
        days.append(d)
    d -= dt.timedelta(days=1)
days.reverse()

rng = random.Random(20261022)
series = {}
n = len(days)
dt_step = 1 / 252
for t, (p0, mu, vol) in TICKERS.items():
    # demean the shocks so the realised drift is the target drift, not whatever
    # the draw happened to give: keeps stub prices consistent with stubs/risk/*.json
    shocks = [rng.gauss(0, 1) * vol * math.sqrt(dt_step) for _ in range(n)]
    mean = sum(shocks) / n
    shocks = [s - mean for s in shocks]
    logp, col = math.log(p0), []
    for s in shocks:
        logp += (mu - 0.5 * vol ** 2) * dt_step + s
        col.append(round(math.exp(logp), 4))
    series[t] = col

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date"] + list(TICKERS))
    for i, day in enumerate(days):
        w.writerow([day.isoformat()] + [series[t][i] for t in TICKERS])

print(f"wrote stubs/prices.csv  {len(days)} rows x {len(TICKERS)} tickers "
      f"({days[0]} .. {days[-1]})")
for t in TICKERS:
    print(f"  {t:4} {series[t][0]:>9.2f} -> {series[t][-1]:>9.2f}")
