"""Per-company refresh and the live judge-added-rule search.

refresh(ticker): re-fetches only Finnhub + Guardian news for one company
(filings/XBRL/EPA/FDA don't change minute to minute, so a "refresh" button only
needs to touch the two fast-moving news sources), bypassing their raw-response
cache, then clears that ticker's embedding cache so rank_evidence() computes
fresh vectors for the new chunks on its next call rather than serving stale ones.

search_new_topic(tickers, keywords): when a judge adds a rule live, pulls fresh
Guardian + Finnhub coverage of that specific topic for the affected companies,
added as new chunks -- Finnhub has no server-side keyword search, so its
company-news pull is filtered client-side to articles that mention a keyword.
"""
import os

import evidence
import ingest.finnhub as finnhub
import ingest.guardian as guardian


def _company_name(ticker):
    import universe
    for c in universe.load_universe():
        if c["ticker"] == ticker:
            return c["name"]
    return ticker


def _clear_embedding_cache(ticker):
    path = evidence._embed_cache_path(ticker)
    if os.path.exists(path):
        os.remove(path)


def refresh(ticker, company_name=None):
    """-> {"finnhub_chunks": int, "guardian_chunks": int}, the new chunks added
    by the live re-fetch."""
    name = company_name or _company_name(ticker)
    new_finnhub = finnhub.fetch_news(ticker, bypass_cache=True)
    new_guardian = guardian.fetch_news(ticker, company_name=name, bypass_cache=True)
    _clear_embedding_cache(ticker)
    return {"finnhub_chunks": new_finnhub, "guardian_chunks": new_guardian}


def search_new_topic(tickers, keywords):
    """-> {ticker: new_chunk_count} across Guardian + Finnhub + GDELT for every
    ticker in `tickers`, searching for `keywords` (a judge's newly-added rule)."""
    import ingest.gdelt as gdelt

    results = {}
    for ticker in tickers:
        name = _company_name(ticker)
        guardian_query = f"{name} " + " ".join(keywords)
        new_guardian = guardian.fetch_news(ticker, company_name=guardian_query, bypass_cache=True)
        new_finnhub = finnhub.fetch_news(ticker, bypass_cache=True, keywords=keywords)
        new_gdelt = gdelt.search_new_topic(ticker, name, keywords)
        _clear_embedding_cache(ticker)
        results[ticker] = {"guardian_chunks": new_guardian, "finnhub_chunks": new_finnhub,
                            "gdelt_chunks": new_gdelt}
    return results
