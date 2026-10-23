"""Full investable universe: S&P 500 constituents + listed foreign filers + bond ETFs.

Produces data/processed/universe.json, a list of Company dicts in the schema from
CLAUDE.md:

    {"ticker": "...", "name": "...", "cik": "...", "sic": "2111",
     "sic_description": "...", "form": "10-K|20-F", "is_bond": false}

Everything here is public, keyless SEC + Wikipedia data (SEC only requires a
descriptive User-Agent, set via SEC_USER_AGENT in .env). ingest/ deep-fetches only
the ~40 tickers selected per charity; this module just builds the ~550-row catalog
every selector draws from.

Run directly to rebuild the universe:
    python3 universe.py
"""
import json
import os
import sys
import time

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(HERE, "data", "processed")
UNIVERSE_PATH = os.path.join(PROCESSED_DIR, "universe.json")

SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT") or "Mandate Hackathon (no contact set in .env)"
DEMO_MODE = os.environ.get("DEMO_MODE", "0") == "1"

# US-listed foreign private issuers (ADRs), added to the S&P 500 constituents.
FOREIGN_FILERS = [
    "BTI", "DEO", "GSK", "NVO", "TEVA", "BP", "SHEL", "UL", "AZN", "SNY", "NVS", "BUD",
]

# Bond ETFs, flagged is_bond=True. These file N-CEN/N-1A, not 10-K/20-F, so
# ingest/edgar.py skips 10-K item extraction for them; we still resolve a CIK and
# SIC so the Company row has one, and record form as "10-K" as a schema filler.
BOND_ETFS = ["SHY", "IEF", "AGG", "TIP", "BND"]

# Demo grey-zone stars, kept in the universe even if the SIC pre-filter or selector
# would otherwise drop them (agents/selector.py reads this to decide what to force in).
ALWAYS_INCLUDE = [
    "PM", "MO", "BTI", "XOM", "CVX", "LMT", "RTX", "BA", "MMM", "KO", "PEP", "DUK",
    "MCK", "CAH", "DEO", "XYL", "AWK", "ECL",
]

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
# ETFs/mutual funds aren't exchange-act registrants, so they're absent from
# company_tickers.json; they're listed here instead, keyed by fund series.
SEC_TICKERS_MF_URL = "https://www.sec.gov/files/company_tickers_mf.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

_MIN_SEC_INTERVAL = 1.0 / 9  # ~9 req/s, under SEC's 10 req/s limit
_last_sec_call = [0.0]


def _sec_get(url, timeout=15):
    """GET against SEC with the required User-Agent and a self-imposed rate limit."""
    elapsed = time.monotonic() - _last_sec_call[0]
    if elapsed < _MIN_SEC_INTERVAL:
        time.sleep(_MIN_SEC_INTERVAL - elapsed)
    _last_sec_call[0] = time.monotonic()
    resp = requests.get(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp


def fetch_sp500_tickers():
    """-> list[str], read live from Wikipedia's S&P 500 constituents table.

    Dots in dual-class tickers (BRK.B) are normalised to dashes (BRK-B) to match
    SEC's ticker format.
    """
    tables = pd.read_html(WIKI_SP500_URL, storage_options={"User-Agent": "Mozilla/5.0"})
    df = tables[0]
    return (
        df["Symbol"].astype(str).str.strip().str.replace(".", "-", regex=False).tolist()
    )


def fetch_sec_ticker_map():
    """-> {ticker: cik(int)}, from SEC's company_tickers.json (all exchange-act
    registrants: operating companies, ADRs). Does not include ETFs/mutual funds;
    see fetch_sec_mf_ticker_map() for those.
    """
    data = _sec_get(SEC_TICKERS_URL).json()
    return {row["ticker"].upper(): row["cik_str"] for row in data.values()}


def fetch_sec_mf_ticker_map():
    """-> {ticker: cik(int)}, from SEC's company_tickers_mf.json (ETFs and mutual
    funds, keyed by fund series/class rather than by registrant).
    """
    data = _sec_get(SEC_TICKERS_MF_URL).json()
    return {row[3].upper(): row[0] for row in data["data"]}


def fetch_company_detail(cik, ticker, is_fund=False):
    """-> (sic, sic_description, name, form) for one CIK, or None on any failure.

    form is "20-F" if a 20-F appears anywhere in the recent filings list (foreign
    private issuer filing an annual report on 20-F), else "10-K". Funds don't file
    either, so is_fund=True always reports "10-K" as a schema filler -- callers
    with is_bond=True should not attempt 10-K/20-F item extraction on it.
    """
    try:
        data = _sec_get(SEC_SUBMISSIONS_URL.format(cik=cik)).json()
    except Exception as exc:
        print(f"  [drop] {ticker}: SEC submissions lookup failed ({exc})")
        return None

    sic = data.get("sic") or None
    sic_description = data.get("sicDescription") or None
    name = data.get("name") or ticker
    if is_fund:
        return sic, sic_description, name, "10-K"
    forms = (data.get("filings", {}) or {}).get("recent", {}).get("form", [])
    form = "20-F" if "20-F" in forms else "10-K"
    return sic, sic_description, name, form


def build_universe():
    """Fetches the full universe live and writes data/processed/universe.json.

    Fail-soft: a company whose SEC lookup fails is dropped and printed, never
    crashes the run.
    """
    if DEMO_MODE:
        print("DEMO_MODE=1: build_universe() needs the network, refusing to run. "
              "Use the committed data/processed/universe.json instead.")
        return load_universe()

    print("Fetching S&P 500 constituents from Wikipedia...")
    sp500 = fetch_sp500_tickers()
    print(f"  {len(sp500)} constituents")

    wanted = list(dict.fromkeys(sp500 + FOREIGN_FILERS))  # de-dup, keep order
    print(f"Fetching SEC ticker -> CIK map for {len(wanted)} target tickers...")
    ticker_to_cik = fetch_sec_ticker_map()

    print(f"Fetching SEC fund ticker -> CIK map for {len(BOND_ETFS)} bond ETFs...")
    mf_ticker_to_cik = fetch_sec_mf_ticker_map()

    companies = []
    dropped = []

    def resolve(ticker, is_bond, is_fund=False):
        cik_map = mf_ticker_to_cik if is_fund else ticker_to_cik
        source_file = "company_tickers_mf.json" if is_fund else "company_tickers.json"
        cik = cik_map.get(ticker.upper())
        if cik is None:
            dropped.append(ticker)
            print(f"  [drop] {ticker}: not found in SEC {source_file}")
            return
        detail = fetch_company_detail(cik, ticker, is_fund=is_fund)
        if detail is None:
            dropped.append(ticker)
            return
        sic, sic_description, name, form = detail
        companies.append({
            "ticker": ticker,
            "name": name,
            "cik": str(cik),
            "sic": sic,
            "sic_description": sic_description,
            "form": form,
            "is_bond": is_bond,
        })

    print(f"Looking up CIK/SIC/form for {len(wanted)} companies (this takes a few minutes)...")
    for i, ticker in enumerate(wanted, 1):
        resolve(ticker, is_bond=False)
        if i % 50 == 0:
            print(f"  ...{i}/{len(wanted)}")

    print(f"Looking up {len(BOND_ETFS)} bond ETFs...")
    for ticker in BOND_ETFS:
        resolve(ticker, is_bond=True, is_fund=True)

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    with open(UNIVERSE_PATH, "w") as f:
        json.dump(companies, f, indent=2)
        f.write("\n")

    print(f"\nWrote {len(companies)} companies to {UNIVERSE_PATH}")
    if dropped:
        print(f"Dropped {len(dropped)} tickers (not found / lookup failed): {', '.join(dropped)}")
    always_missing = sorted(set(ALWAYS_INCLUDE) - {c['ticker'] for c in companies})
    if always_missing:
        print(f"WARNING: always_include tickers missing from universe: {always_missing}")
    return companies


def load_universe():
    """-> list[Company], read from the committed data/processed/universe.json."""
    with open(UNIVERSE_PATH) as f:
        return json.load(f)


if __name__ == "__main__":
    build_universe()
