"""Finnhub company news, last 180 days, max 40 articles per ticker."""
import json
import time
from datetime import date, timedelta

import requests

from .. import config as C

NEWS_DIR = C.CACHE_DIR / "news"
MAX_ARTICLES = 40


def fetch_news(ticker: str, force: bool = False) -> list[dict] | None:
    """Return cached or fresh news. None if there is no cache and no way to fetch."""
    path = NEWS_DIR / f"{ticker}.json"
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8"))
    if C.DEMO_MODE or not C.FINNHUB_API_KEY:
        return None
    today = date.today()
    r = requests.get("https://finnhub.io/api/v1/company-news", timeout=30, params={
        "symbol": ticker, "from": (today - timedelta(days=C.NEWS_DAYS)).isoformat(),
        "to": today.isoformat(), "token": C.FINNHUB_API_KEY})
    r.raise_for_status()
    items = sorted(r.json(), key=lambda a: a.get("datetime", 0), reverse=True)[:MAX_ARTICLES]
    keep = [{k: a.get(k) for k in ("headline", "summary", "url", "datetime", "source")} for a in items]
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keep, indent=1), encoding="utf-8")
    time.sleep(1.1)     # free tier: 60 calls/minute
    return keep
