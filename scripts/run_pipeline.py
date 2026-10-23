"""Run the full pipeline: python scripts/run_pipeline.py [charity_id] [--equities MO MMM XYL]"""
import argparse
import sys
import warnings
from collections import Counter
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mandate import config as C  # noqa: E402
from mandate.pipeline import DEFAULT_CHARITY, run_charity  # noqa: E402


def summarise(r: dict) -> None:
    opt, st = r["optimiser"], r["stats"]
    print(f"\n=== {r['policy']['charity']} ({r['charity_id']}) ===")
    if opt["ok"]:
        hs = opt["holdings"]
        bonds = sum(h["weight"] for h in hs if h["is_bond"])
        print(f"Invest ${C.BUDGET_USD:,} across {len(hs)} holdings: {1 - bonds:.0%} shares, {bonds:.0%} bonds, "
              f"${opt['cash_usd']:,.2f} cash left over.")
        for h in hs:
            print(f"  {h['ticker']:6s} ${h['dollars']:>10,.2f} {h['shares']:>5d} sh {h['weight']:>6.1%}{'  bond' if h['is_bond'] else ''}")
        bt = opt["backtest"]
        print(f"Worst 12m {bt['worst_12m_return']:+.1%} (limit {bt['worst_12m_limit']:+.0%}), yield {bt['trailing_yield']:.2%} "
              f"(target {bt['min_yield']:.1%}), vs 60/40 {bt['vs_6040']:+.1%}. Past performance, not a forecast.")
    else:
        print(f"OPTIMISER FAILED: {opt['error']}")
    for line in opt["relaxed"]:
        print(f"  constraint relaxed: {line}")
    print("Decisions:", dict(Counter(d["status"] for d in r["decisions"])))
    for d in r["decisions"]:
        if d["status"] == "REJECTED_ETHICS":
            v = d["veto"]
            print(f"  VETO {d['ticker']:6s} {v['rule_id']}: \"{(v['quote'] or '')[:70]}\" [{v['source_id']}]")
    for w in r["warnings"]:
        print("  warning:", w)
    print(f"Memo: {len(r['memo'].split())} words" if r["memo"] else "Memo: none")
    print(f"Run: {st['wall_seconds']}s, {st['llm_calls']} LLM calls, {st['cache_hits']} cache hits, {st['tokens']:,} tokens")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("charity_id", nargs="?", default=DEFAULT_CHARITY)
    ap.add_argument("--equities", nargs="*", help="subset of equities (default: all 32)")
    args = ap.parse_args()
    summarise(run_charity(args.charity_id, [t.upper() for t in args.equities] if args.equities else None))
    print(f"Wrote {C.RESULTS_DIR / 'run.json'}")


if __name__ == "__main__":
    main()
