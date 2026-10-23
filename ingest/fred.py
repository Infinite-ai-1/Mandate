"""FRED: 3-month Treasury rate (DGS3MO) and CPI (CPIAUCSL).

Used for the "vs 60/40" and real-return context in the portfolio memo. Needs
FRED_API_KEY in .env (free at fred.stlouisfed.org/docs/api/api_key.html). Fails
soft without one.
"""
import os

import requests

from ingest._cache import cached_fetch

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
SERIES = {"dgs3mo": "DGS3MO", "cpi": "CPIAUCSL"}


def _fetch_series(series_id, limit=60):
    key = os.environ.get("FRED_API_KEY")
    if not key:
        return None
    resp = requests.get(BASE_URL, params={
        "series_id": series_id, "api_key": key, "file_type": "json",
        "sort_order": "desc", "limit": limit,
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if "observations" not in data:
        print(f"[fred] {series_id}: unexpected response: {data}")
        return None
    return data["observations"]


def fetch_series(name, limit=60):
    """`name` is "dgs3mo" or "cpi". -> list of {"date": "...", "value": "..."}
    observations, most recent first, or None if unavailable."""
    series_id = SERIES.get(name)
    if not series_id:
        raise ValueError(f"unknown FRED series {name!r}, expected one of {list(SERIES)}")
    if not os.environ.get("FRED_API_KEY"):
        print(f"[fred] no FRED_API_KEY set, skipping {name}")
        return None
    return cached_fetch(f"fred_{name}", {"limit": limit}, lambda: _fetch_series(series_id, limit))


def latest_value(name):
    """-> the most recent observation's float value for `name`, or None."""
    obs = fetch_series(name, limit=5)
    if not obs:
        return None
    for o in obs:
        if o.get("value") not in (None, "."):  # FRED uses "." for missing
            return float(o["value"])
    return None
