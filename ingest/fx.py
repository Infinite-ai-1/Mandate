"""GBP/USD exchange rate, via Twelve Data.

The portfolio is denominated in USD (Portfolio.total_usd) but charities in this
project are UK-based, so the frontend/memo need a GBP/USD rate to show the
equivalent in the charity's own currency (Portfolio.gbpusd in the schema).

Needs TWELVE_DATA_API_KEY in .env (shared with prices.py's fallback path). Fails
soft without one.
"""
import datetime
import os

import requests

from ingest._cache import cached_fetch

URL = "https://api.twelvedata.com/exchange_rate"


def fetch_gbpusd():
    """-> the current GBP/USD rate (1 GBP = N USD), or None if unavailable.
    Cached per calendar day (the key includes today's date) so a full pipeline
    run doesn't refetch it per charity.
    """
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        print("[fx] no TWELVE_DATA_API_KEY set, skipping GBP/USD")
        return None

    today = datetime.date.today().isoformat()

    def _fetch():
        resp = requests.get(URL, params={"symbol": "GBP/USD", "apikey": key}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "rate" not in data:
            print(f"[fx] unexpected response: {data}")
            return None
        return data["rate"]

    return cached_fetch("fx_gbpusd", {"date": today}, _fetch)
