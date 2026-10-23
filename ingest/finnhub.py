"""Finnhub: company news, profile, basic financials, recommendation trends.

Company news is ingested as Chunks (kind="news"); profile, basic financials and
recommendation trends are summarised into one short text chunk each (kind="market"
-- they're Finnhub's market-derived numbers, not news stories, and not the 5
contract Metric names that belong to XBRL via edgar.py), so agents can still cite
them through rank_evidence() the same way they'd cite a news story.

Needs FINNHUB_API_KEY in .env. Missing key -> fails soft (logs once, returns 0/[]
rather than raising), same as a network failure.
"""
import datetime
import os

import requests

import evidence
from ingest._cache import RateLimiter, cached_fetch, demo_mode

BASE_URL = "https://finnhub.io/api/v1"
RECENT_MONTHS = 12

# Free tier allows 60 calls/min; stay comfortably under it.
_limiter = RateLimiter(1.1)


def _api_key():
    return os.environ.get("FINNHUB_API_KEY") or None


def _get(path, params):
    key = _api_key()
    if not key:
        return None
    _limiter.wait()
    resp = requests.get(f"{BASE_URL}/{path}", params={**params, "token": key}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_news(ticker, months=RECENT_MONTHS):
    """Ingests Finnhub company news from the last `months` months as Chunks.
    -> number of new chunks added."""
    if not _api_key():
        print(f"[finnhub] no FINNHUB_API_KEY set, skipping news for {ticker}")
        return 0

    today = datetime.date.today()
    start = today - datetime.timedelta(days=months * 31)
    params = {"symbol": ticker, "from": start.isoformat(), "to": today.isoformat()}
    items = cached_fetch("finnhub_news", params, lambda: _get("company-news", params))
    if not items:
        return 0

    total_new = 0
    for item in items:
        text = (item.get("headline") or "").strip()
        if item.get("summary"):
            text = f"{text}. {item['summary']}".strip(". ").strip()
        if not text:
            continue
        try:
            date = datetime.datetime.utcfromtimestamp(item["datetime"]).date().isoformat()
        except Exception:
            date = None
        total_new += len(evidence.ingest_document(
            ticker,
            {"kind": "news", "origin": "finnhub", "title": item.get("headline"),
             "date": date, "url": item.get("url"), "section": None},
            text,
        ))
    return total_new


def fetch_profile(ticker):
    """Ingests a one-line Finnhub profile summary as a single chunk.
    -> the raw profile dict, or {} if unavailable."""
    if not _api_key():
        return {}
    profile = cached_fetch("finnhub_profile", {"ticker": ticker},
                            lambda: _get("stock/profile2", {"symbol": ticker}))
    if not profile:
        return {}

    parts = [profile.get("name", ticker)]
    if profile.get("finnhubIndustry"):
        parts.append(f"operates in the {profile['finnhubIndustry']} industry")
    if profile.get("exchange"):
        parts.append(f"listed on {profile['exchange']}")
    if profile.get("marketCapitalization"):
        parts.append(f"market capitalization approximately ${profile['marketCapitalization']:,.0f}M")
    if profile.get("ipo"):
        parts.append(f"IPO date {profile['ipo']}")
    text = ", ".join(parts) + "."

    evidence.ingest_document(
        ticker,
        {"kind": "market", "origin": "finnhub", "title": f"{profile.get('name', ticker)} company profile",
         "date": datetime.date.today().isoformat(), "url": profile.get("weburl"), "section": None},
        text,
    )
    return profile


def fetch_basic_financials(ticker):
    """Ingests a one-chunk summary of Finnhub's basic-financials ratios (dividend
    yield, beta, margins, P/E). -> the raw metric dict, or {} if unavailable."""
    if not _api_key():
        return {}
    data = cached_fetch("finnhub_basic_financials", {"ticker": ticker},
                         lambda: _get("stock/metric", {"symbol": ticker, "metric": "all"}))
    metric = (data or {}).get("metric") or {}
    if not metric:
        return {}

    fields = [
        ("currentDividendYieldTTM", "trailing-twelve-month dividend yield", "%"),
        ("beta", "beta vs. the market", ""),
        ("peTTM", "trailing P/E ratio", ""),
        ("netProfitMarginTTM", "trailing net profit margin", "%"),
        ("totalDebt/totalEquityAnnual", "annual total debt to equity", "%"),
        ("52WeekHigh", "52-week high price", "$"),
        ("52WeekLow", "52-week low price", "$"),
    ]
    parts = []
    for key, label, unit in fields:
        if key in metric and metric[key] is not None:
            parts.append(f"{label} is {metric[key]}{unit}")
    if not parts:
        return metric
    text = f"Finnhub basic financials for {ticker} as of today: " + "; ".join(parts) + "."

    evidence.ingest_document(
        ticker,
        {"kind": "market", "origin": "finnhub", "title": f"{ticker} Finnhub basic financials",
         "date": datetime.date.today().isoformat(), "url": None, "section": None},
        text,
    )
    return metric


def fetch_recommendation_trends(ticker):
    """Ingests the latest analyst recommendation trend as a one-chunk summary.
    -> the raw trend list, or [] if unavailable."""
    if not _api_key():
        return []
    trends = cached_fetch("finnhub_recommendation", {"ticker": ticker},
                           lambda: _get("stock/recommendation", {"symbol": ticker}))
    if not trends:
        return []

    latest = trends[0]
    text = (
        f"Analyst recommendation trend for {ticker} as of {latest.get('period')}: "
        f"{latest.get('strongBuy', 0)} strong buy, {latest.get('buy', 0)} buy, "
        f"{latest.get('hold', 0)} hold, {latest.get('sell', 0)} sell, "
        f"{latest.get('strongSell', 0)} strong sell."
    )
    evidence.ingest_document(
        ticker,
        {"kind": "market", "origin": "finnhub", "title": f"{ticker} analyst recommendation trend",
         "date": latest.get("period"), "url": None, "section": None},
        text,
    )
    return trends


def fetch_company(ticker):
    """Runs all four Finnhub fetches for one ticker. -> dict for run_all.py's
    coverage table."""
    news_chunks = fetch_news(ticker)
    profile = fetch_profile(ticker)
    financials = fetch_basic_financials(ticker)
    trends = fetch_recommendation_trends(ticker)
    return {
        "news_chunks": news_chunks,
        "profile": bool(profile),
        "basic_financials": bool(financials),
        "recommendation_trends": len(trends),
    }
