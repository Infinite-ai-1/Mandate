"""Pull and cache all data: python scripts/fetch_data.py [--tickers MO MMM XYL] [--force] [--no-embed]"""
import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")     # yfinance/pandas deprecation noise
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mandate import config as C  # noqa: E402
from mandate import evidence, universe  # noqa: E402
from mandate.sources import edgar, market, news  # noqa: E402


def step(label: str, fn, *a):
    """Run one collector; a failure is reported and the run continues."""
    try:
        return fn(*a)
    except Exception as e:
        print(f"  ! {label}: {type(e).__name__}: {str(e)[:160]}")
        return None


def _count(path) -> str:
    return str(len(json.loads(path.read_text(encoding="utf-8")))) if path.exists() else "-"


def coverage(equities: list[str]) -> None:
    fund = market._load_json(market.FUNDAMENTALS)
    risk = market._load_json(market.RISK_STATS)
    prices = market.load_prices() if market.PRICES.exists() else None
    yn = lambda b: "yes" if b else "-"  # noqa: E731
    print(f"\n{'ticker':7s}{'price':>6s}{'fund':>6s}{'risk':>6s}{'form':>6s}{'sections':>34s}{'news':>6s}{'chunks':>7s}{'emb':>5s}")
    for t in equities + universe.BONDS:
        f = edgar.EDGAR_DIR / f"{t}.json"
        filing = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        secs = ",".join(s.split()[0] for s in filing["sections"]) if filing else "-"
        has_price = prices is not None and t in prices.columns
        has_fund = bool(fund.get(t)) and any(v is not None for v in fund[t].values())
        print(f"{t:7s}{yn(has_price):>6s}{yn(has_fund):>6s}{yn(t in risk):>6s}{(filing['form'] if filing else '-'):>6s}"
              f"{secs:>34s}{_count(news.NEWS_DIR / f'{t}.json'):>6s}{_count(evidence.EMB_DIR / f'{t}.json'):>7s}"
              f"{yn((evidence.EMB_DIR / f'{t}.npy').exists()):>5s}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", help="equities to fetch (default: all 32)")
    ap.add_argument("--force", action="store_true", help="ignore the cache")
    ap.add_argument("--no-embed", action="store_true", help="chunk only, skip embeddings")
    args = ap.parse_args()
    equities = [t.upper() for t in args.tickers] if args.tickers else universe.EQUITIES
    print(f"DEMO_MODE={int(C.DEMO_MODE)}  equities={len(equities)}  cache={C.CACHE_DIR}")

    print("prices ...")
    prices = step("prices", market.fetch_prices, universe.price_tickers(equities), args.force)
    if prices is not None:
        print(f"  {prices.shape[1]} tickers x {prices.shape[0]} days")
        step("yields", market.fetch_yields, equities + universe.BONDS, prices, args.force)
        step("risk stats", market.compute_risk_stats, prices)
    print("fundamentals ...")
    step("fundamentals", market.fetch_fundamentals, equities, args.force)

    for t in equities:
        print(f"{t} ...")
        step(f"{t} edgar", edgar.fetch_filing, t, universe.form_for(t), args.force)
        step(f"{t} news", news.fetch_news, t, args.force)
        if args.no_embed:
            step(f"{t} chunks", evidence.save_chunks, t)
        else:
            step(f"{t} embeddings", evidence.build_index, t, args.force)
    coverage(equities)


if __name__ == "__main__":
    main()
