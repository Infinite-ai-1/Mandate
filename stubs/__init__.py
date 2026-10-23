"""Synthetic data in the CLAUDE.md schemas, so agents/, quant/ and frontend/ can be
built before the real ingest lands.

Everything here is hand-written and fake. Numbers are plausible, not true; the filing
and news text is written for this repo and is not a real filing or article. Nothing in
stubs/ is ever read by the real pipeline — swap `stubs` for the real loaders when they
land and the shapes will match:

    from stubs import load_chunks            ->  from evidence import load_chunks
    from stubs import load_universe          ->  from universe import load_universe
    from stubs import get_source, load_all   ->  from sources import get, load_all

Stdlib only, so importing this never depends on the venv being ready.
"""
import json
import os
import re

DIR = os.path.dirname(os.path.abspath(__file__))

TICKERS = ["PM", "MMM", "XYL"]          # full stub coverage
BOND_TICKERS = ["AGG"]                  # risk metrics + prices only


def _read(*parts):
    with open(os.path.join(DIR, *parts)) as f:
        return json.load(f)


# ----------------------------------------------------------------- universe
def load_universe():
    """-> list[Company]"""
    return _read("universe.json")


# ------------------------------------------------------------------ sources
def load_all():
    """-> {source_id: Source}"""
    return _read("sources.json")


def get_source(source_id):
    """-> Source, or None if the id is unknown (same as sources.get())."""
    return load_all().get(source_id)


get = get_source                        # alias matching sources.py's function name


# ------------------------------------------------------------------- chunks
def load_chunks(ticker):
    """-> list[Chunk] for one ticker, [] if the ticker has no stub."""
    path = os.path.join(DIR, "chunks", f"{ticker.upper()}.json")
    return _read("chunks", f"{ticker.upper()}.json") if os.path.exists(path) else []


# ------------------------------------------------------------------ metrics
def load_fundamentals(ticker):
    """-> {"ticker": ..., "metrics": [Metric]}"""
    return _read("fundamentals", f"{ticker.upper()}.json")


def load_risk(ticker):
    """-> {"ticker": ..., "metrics": [Metric]}"""
    return _read("risk", f"{ticker.upper()}.json")


def metric(ticker, name, kind="fundamentals"):
    """One Metric by name, or None. kind is "fundamentals" or "risk"."""
    blob = load_fundamentals(ticker) if kind == "fundamentals" else load_risk(ticker)
    return next((m for m in blob["metrics"] if m["name"] == name), None)


# ------------------------------------------------------------------- prices
def load_prices():
    """5y of daily adjusted closes.

    Returns a pandas DataFrame (date index, one column per ticker) when pandas is
    installed, matching data/processed/prices.parquet. Falls back to
    {"dates": [...], "PM": [...], ...} so it still works with stdlib only.
    """
    path = os.path.join(DIR, "prices.csv")
    try:
        import pandas as pd
        return pd.read_csv(path, index_col="date", parse_dates=True)
    except ImportError:
        import csv
        with open(path) as f:
            rows = list(csv.DictReader(f))
        cols = [c for c in rows[0] if c != "date"]
        out = {"dates": [r["date"] for r in rows]}
        out.update({c: [float(r[c]) for r in rows] for c in cols})
        return out


# ---------------------------------------------------------------- evidence
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "any", "no",
    "not", "is", "are", "be", "by", "that", "this", "it", "its", "we", "our", "from",
    "as", "at", "all", "than", "more", "may", "must", "shall", "should", "will",
    "company", "companies", "invest", "investment", "investments", "holding",
    "holdings", "do", "does", "have", "has",
}


def rank_evidence(rules, ticker, k=8):
    """Keyword-overlap stand-in for evidence.rank_evidence().

    Same signature and return shape ({rule_id: [Chunk]}), so agent prompts can be
    built and tested now; the real one ranks by embedding cosine similarity.
    Filings break ties ahead of news, as in the real ranker.
    """
    chunks = load_chunks(ticker)
    sources = load_all()
    out = {}
    for rule in rules:
        terms = set()
        for word in re.findall(r"[a-z]+", (rule.get("text") or "").lower()):
            if word not in _STOP and len(word) > 2:
                terms.add(word)
        for kw in rule.get("keywords") or []:
            terms.update(w for w in re.findall(r"[a-z]+", kw.lower()) if len(w) > 2)

        scored = []
        for chunk in chunks:
            words = set(re.findall(r"[a-z]+", chunk["text"].lower()))
            hits = len(terms & words)
            if not hits:
                continue
            is_filing = sources.get(chunk["source_id"], {}).get("kind") == "filing"
            scored.append((hits, is_filing, chunk["date"], chunk))
        scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
        out[rule["id"]] = [row[3] for row in scored[:k]]
    return out
