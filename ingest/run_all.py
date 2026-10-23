"""Orchestrates every fetcher for a set of tickers, then prints a coverage table.

Usage:
    python -m ingest.run_all --tickers PM,MMM,XYL
    python -m ingest.run_all --charity cancer_research_wales
        (reads data/processed/selection/<id>.json's "selected" tickers)

Runs tickers sequentially (sources.py's registry isn't safe for concurrent
writers) and fails soft per-ticker-per-source: one company's EPA lookup erroring
out doesn't stop its Finnhub fetch, let alone the next company.
"""
import argparse
import json
import os
import re
import sys
import time

import ingest.edgar as edgar
import ingest.epa as epa
import ingest.fda as fda
import ingest.finnhub as finnhub
import ingest.gdelt as gdelt
import ingest.guardian as guardian
import ingest.prices as prices

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_LEGAL_SUFFIXES = re.compile(
    r"\s*[,.]?\s*\b(Inc|Incorporated|Corp|Corporation|Co|Company|Ltd|Limited|"
    r"plc|p\.l\.c|International|Holdings?|Group)\b\.?\s*$",
    re.IGNORECASE,
)


def _core_name(name):
    """Strips a trailing corporate suffix ("Philip Morris International Inc." ->
    "Philip Morris"), applied repeatedly since names stack more than one ("Xylem
    Inc." has one, "3M International Holdings Inc." could have several).

    EPA ECHO and openFDA search by (near-)literal substring match against actual
    facility names, which skew informal ("3M CORDOVA", "PHILIP MORRIS USA") --
    the full SEC legal name often matches nothing even when the company plainly
    has a presence in the data. Guardian/GDELT are free-text search over prose,
    so they're given the fuller name instead; only EPA/FDA get the stripped one.
    """
    prev = name
    while True:
        stripped = _LEGAL_SUFFIXES.sub("", prev).strip()
        if stripped == prev or not stripped:
            return prev
        prev = stripped


def _load_universe_names():
    import universe
    return {c["ticker"]: c["name"] for c in universe.load_universe()}


def _tickers_for_charity(charity_id):
    path = os.path.join(HERE, "data", "processed", "selection", f"{charity_id}.json")
    with open(path) as f:
        selection = json.load(f)
    return [row["ticker"] for row in selection["selected"]]


def _run_one(ticker, company_name):
    """Runs every per-company fetcher for one ticker. -> {source: count} for the
    coverage table. Each fetcher is isolated: one raising doesn't block the rest.
    """
    row = {}

    def _try(label, fn):
        try:
            row[label] = fn()
        except Exception as exc:
            print(f"[run_all] {ticker} {label}: unhandled error ({exc})")
            row[label] = "ERROR"

    _try("edgar_filings", lambda: edgar.fetch_filing_items(ticker))
    _try("edgar_events", lambda: edgar.fetch_recent_events(ticker))
    _try("edgar_xbrl", lambda: len(edgar.fetch_fundamentals(ticker)))
    _try("finnhub_news", lambda: finnhub.fetch_news(ticker))
    _try("finnhub_other", lambda: sum([
        bool(finnhub.fetch_profile(ticker)),
        bool(finnhub.fetch_basic_financials(ticker)),
        len(finnhub.fetch_recommendation_trends(ticker)),
    ]))
    _try("guardian_news", lambda: guardian.fetch_news(ticker, company_name=company_name))
    _try("gdelt_news", lambda: gdelt.fetch_news(ticker, company_name=company_name))
    core_name = _core_name(company_name)
    _try("epa", lambda: epa.fetch_violations(ticker, core_name))
    _try("fda", lambda: fda.fetch_recalls(ticker, core_name))
    return row


def _print_coverage(coverage, tickers, columns):
    widths = {col: max(len(col), 6) for col in columns}
    header = "TICKER".ljust(8) + "  " + "  ".join(col.ljust(widths[col]) for col in columns)
    print(header)
    print("-" * len(header))
    for ticker in tickers:
        row = coverage.get(ticker, {})
        cells = [str(row.get(col, "-")).ljust(widths[col]) for col in columns]
        print(ticker.ljust(8) + "  " + "  ".join(cells))


def run_all(tickers):
    names = _load_universe_names()
    coverage = {}
    start = time.monotonic()

    for i, ticker in enumerate(tickers, 1):
        company_name = names.get(ticker, ticker)
        print(f"\n=== [{i}/{len(tickers)}] {ticker} ({company_name}) ===")
        coverage[ticker] = _run_one(ticker, company_name)

    print(f"\nFetching prices for {len(tickers)} tickers + benchmarks...")
    price_ok = prices.fetch_prices(tickers)

    columns = ["edgar_filings", "edgar_events", "edgar_xbrl", "finnhub_news",
               "finnhub_other", "guardian_news", "gdelt_news", "epa", "fda"]
    print(f"\n=== Coverage (new chunks/metrics added this run) -- {len(tickers)} tickers, "
          f"{time.monotonic() - start:.0f}s ===")
    _print_coverage(coverage, tickers, columns)
    print(f"\nPrices: {sum(price_ok.values())}/{len(price_ok)} tickers resolved "
          f"({', '.join(t for t, ok in price_ok.items() if not ok) or 'none missing'})")
    return coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", help="comma-separated tickers, e.g. PM,MMM,XYL")
    parser.add_argument("--charity", help="charity_id; reads its selection/<id>.json")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.charity:
        tickers = _tickers_for_charity(args.charity)
    else:
        parser.error("pass --tickers A,B,C or --charity <id>")
        return

    if not tickers:
        print("No tickers to fetch.")
        return
    run_all(tickers)


if __name__ == "__main__":
    main()
