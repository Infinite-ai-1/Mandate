"""GDELT DOC API: article titles + URLs, for discovery (not full article text --
the DOC API only returns metadata, never body text, so each Chunk here is just a
headline; it exists to surface topics/leads a Guardian or Finnhub search might
miss, not as a primary evidence source).

Keyless public API, no .env entry needed. Rate limit is informal ("be reasonable");
a conservative 1 req/sec is used here.
"""
import datetime
import os

import requests

import evidence
from ingest._cache import RateLimiter, cached_fetch

BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
RECENT_DAYS = 365
MAX_RECORDS = 50
TIMEOUT = 20  # GDELT can be slow/unreachable from some networks; fails soft either way

_limiter = RateLimiter(1.0)


def _search(query, max_records=MAX_RECORDS):
    _limiter.wait()
    resp = requests.get(BASE_URL, params={
        "query": query, "mode": "artlist", "maxrecords": max_records,
        "format": "json", "sort": "datedesc",
    }, headers={"User-Agent": "Mozilla/5.0 (Mandate Hackathon research tool)"}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_news(ticker, company_name=None, days=RECENT_DAYS):
    """Searches GDELT for `company_name` (falls back to `ticker`), ingesting each
    hit's headline as a short Chunk. -> number of new chunks added.
    """
    query = f'"{company_name or ticker}"'
    params = {"ticker": ticker, "query": query, "days": days}
    data = cached_fetch("gdelt_search", params, lambda: _search(query))
    if not data:
        return 0

    articles = data.get("articles") or []
    total_new = 0
    for article in articles:
        title = (article.get("title") or "").strip()
        if not title:
            continue
        seen = article.get("seendate", "")  # "20261022T134500Z"
        date = f"{seen[0:4]}-{seen[4:6]}-{seen[6:8]}" if len(seen) >= 8 else None
        total_new += len(evidence.ingest_document(
            ticker,
            {"kind": "news", "origin": "gdelt", "title": title, "date": date,
             "url": article.get("url"), "section": article.get("domain")},
            title,
        ))
    return total_new


def search_new_topic(ticker, company_name, keywords):
    """For the live judge-added-rule flow: a fresh GDELT search for `keywords`
    about this company, bypassing nothing (GDELT has no per-ticker cache key
    collision risk here since the query itself is the cache key) -- called
    alongside ingest.refresh.search_new_topic(), which handles the Guardian/
    Finnhub side and the cache-bypass semantics.
    """
    query = f'"{company_name or ticker}" ' + " ".join(keywords)
    data = _search(query)  # always live: a judge's new rule needs current coverage
    articles = (data or {}).get("articles") or []
    total_new = 0
    for article in articles:
        title = (article.get("title") or "").strip()
        if not title:
            continue
        seen = article.get("seendate", "")
        date = f"{seen[0:4]}-{seen[4:6]}-{seen[6:8]}" if len(seen) >= 8 else None
        total_new += len(evidence.ingest_document(
            ticker,
            {"kind": "news", "origin": "gdelt", "title": title, "date": date,
             "url": article.get("url"), "section": article.get("domain")},
            title,
        ))
    return total_new
