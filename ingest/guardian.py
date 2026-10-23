"""Guardian Open Platform: news search by company name, last 3 years.

Needs GUARDIAN_API_KEY in .env (free developer key at open-platform.theguardian.com).
Fails soft without one -- logs once and returns 0, same as a network failure.

Guardian results are far noisier for ethics screening than a search by ticker
(the API only supports free-text search, so "Philip Morris" also returns stories
that merely mention the brand in passing). We don't try to filter that here --
ranked relevance to a charity's rules is evidence.rank_evidence()'s job, not ours.
"""
import datetime
import os

import requests

import evidence
from ingest._cache import RateLimiter, cached_fetch

BASE_URL = "https://content.guardianapis.com/search"
RECENT_YEARS = 3
MAX_PAGES = 3    # 50 results/page; caps a single company's search at 150 articles
PAGE_SIZE = 50

_limiter = RateLimiter(0.6)  # Guardian's free tier: 500 calls/day, 1 call/sec burst


def _api_key():
    return os.environ.get("GUARDIAN_API_KEY") or None


def _search_page(query, from_date, page):
    key = _api_key()
    if not key:
        return None
    _limiter.wait()
    resp = requests.get(BASE_URL, params={
        "q": query, "from-date": from_date, "show-fields": "bodyText",
        "page-size": PAGE_SIZE, "page": page, "order-by": "newest", "api-key": key,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_news(ticker, company_name=None, years=RECENT_YEARS, bypass_cache=False):
    """Searches the Guardian for `company_name` (falls back to `ticker` if no
    name given) over the last `years` years, ingesting each hit's body text as a
    Chunk. bypass_cache=True re-fetches live even if a cached response exists,
    for ingest.refresh.refresh() and search_new_topic() (pass a query that
    already includes the new topic's keywords as part of `company_name`).
    -> number of new chunks added.
    """
    if not _api_key():
        print(f"[guardian] no GUARDIAN_API_KEY set, skipping news for {ticker}")
        return 0

    query = company_name or ticker
    from_date = (datetime.date.today() - datetime.timedelta(days=365 * years)).isoformat()

    total_new = 0
    for page in range(1, MAX_PAGES + 1):
        params = {"ticker": ticker, "query": query, "from_date": from_date, "page": page}
        data = cached_fetch("guardian_search", params, lambda p=page: _search_page(query, from_date, p),
                             bypass_cache=bypass_cache)
        if not data:
            break
        response = data.get("response", {})
        results = response.get("results", [])
        if not results:
            break

        for article in results:
            fields = article.get("fields", {})
            body = fields.get("bodyText") or ""
            title = article.get("webTitle") or ""
            text = f"{title}. {body}".strip() if body else title
            if not text.strip():
                continue
            date = (article.get("webPublicationDate") or "")[:10] or None
            total_new += len(evidence.ingest_document(
                ticker,
                {"kind": "news", "origin": "guardian", "title": title, "date": date,
                 "url": article.get("webUrl"), "section": article.get("sectionName")},
                text,
            ))

        if page >= response.get("pages", 1):
            break

    return total_new
