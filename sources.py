"""Source registry: every chunk and metric gets a unique source_id, resolvable here.

Schema (data/processed/sources.json, keyed by source_id), from CLAUDE.md:
    {"source_id": "S-XOM-0012", "ticker": "XOM", "kind": "filing|news|regulator|market|computed",
     "origin": "edgar_10k|edgar_8k|edgar_20f|edgar_6k|edgar_xbrl|finnhub|guardian|gdelt|epa|fda|
                yfinance|twelvedata|fred|quant",
     "title": "...", "date": "YYYY-MM-DD", "url": "...", "section": "Item 3 Legal Proceedings"}

This is the one place that mints source_ids and is the only writer of
data/processed/sources.json. ingest/* calls register() for every chunk or metric it
produces; nothing else should touch the file directly. verify.py (Person 2) reads it
via get()/load_all() to resolve a quote's claimed source_id back to real text.

The registry is loaded into memory once per process and flushed to disk on every
register() call, so concurrent ingest runs for different tickers are safe as long as
they don't run in parallel processes (ingest/run_all.py runs tickers sequentially).
"""
import json
import os
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(HERE, "data", "processed")
SOURCES_PATH = os.path.join(PROCESSED_DIR, "sources.json")

KINDS = {"filing", "news", "regulator", "market", "computed"}
ORIGINS = {
    "edgar_10k", "edgar_8k", "edgar_20f", "edgar_6k", "edgar_xbrl",
    "finnhub", "guardian", "gdelt", "epa", "fda", "yfinance", "twelvedata", "fred", "quant",
}

_lock = threading.Lock()
_cache = None  # {source_id: Source}, lazily loaded


def _load():
    global _cache
    if _cache is not None:
        return _cache
    if os.path.exists(SOURCES_PATH):
        with open(SOURCES_PATH) as f:
            _cache = json.load(f)
    else:
        _cache = {}
    return _cache


def _flush():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    temporary = SOURCES_PATH + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(_cache, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(temporary, SOURCES_PATH)


def _next_seq(ticker):
    """Smallest unused 4-digit sequence number for this ticker's source_id."""
    prefix = f"S-{ticker}-"
    used = {
        int(sid[len(prefix):])
        for sid in _load()
        if sid.startswith(prefix) and sid[len(prefix):].isdigit()
    }
    seq = 1
    while seq in used:
        seq += 1
    return seq


def register(source=None, **fields):
    """Mints a source_id for `source` (a dict with every key except source_id:
    ticker, kind, origin, title, date, url, section) and persists it to
    data/processed/sources.json. Returns the new source_id.

    If an identical source (same ticker/kind/origin/title/date/url/section) is
    already registered, returns the existing source_id instead of minting a
    duplicate -- callers can register the same chunk's source on every run without
    the registry growing.
    """
    source = {**(source or {}), **fields}
    if source.get("kind") not in KINDS:
        raise ValueError(f"unknown kind {source.get('kind')!r}, expected one of {KINDS}")
    if source.get("origin") not in ORIGINS:
        raise ValueError(f"unknown origin {source.get('origin')!r}, expected one of {ORIGINS}")
    ticker = source["ticker"]

    with _lock:
        registry = _load()
        dedupe_keys = ("ticker", "kind", "origin", "title", "date", "url", "section")
        explicit_id = source.get("source_id")
        for sid, existing in registry.items():
            if all(existing.get(k) == source.get(k) for k in dedupe_keys):
                if not explicit_id or sid == explicit_id:
                    return sid

        seq = _next_seq(ticker)
        source_id = explicit_id or f"S-{ticker}-{seq:04d}"
        if source_id in registry and registry[source_id]["ticker"] != ticker:
            raise ValueError("Source ID already belongs to another company")
        registry[source_id] = {
            "source_id": source_id,
            "ticker": ticker,
            "kind": source["kind"],
            "origin": source["origin"],
            "title": source.get("title"),
            "date": source.get("date"),
            "url": source.get("url"),
            "section": source.get("section"),
        }
        _flush()
        return source_id


def get(source_id):
    """-> Source dict, or None if source_id is unknown."""
    return _load().get(source_id)


def load_all():
    """-> {source_id: Source}, the full registry."""
    return dict(_load())


def reset_cache():
    """Forces the next load to re-read from disk. Mainly for tests."""
    global _cache
    with _lock:
        _cache = None
