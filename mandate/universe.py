"""Tickers and groups (CLAUDE+.md 8.1). Groups are for the demo story only."""
import json
from functools import lru_cache

from . import config as C

GROUPS = {
    "likely_fails": ["XOM", "CVX", "BP", "SHEL", "MO", "PM", "BTI", "LMT", "RTX"],
    "alcohol": ["BUD", "DEO", "STZ"],
    "grey_zone": ["MMM", "DD", "CC", "DOW", "KO", "PEP", "DUK", "JNJ"],
    "likely_passes": ["XYL", "ECL", "AWK", "ABT", "TMO", "DHR", "MSFT", "AAPL", "COST", "PG", "ISRG", "V"],
}
EQUITIES = [t for g in GROUPS.values() for t in g]      # 32
BONDS = ["SHY", "IEF", "BND", "TIP"]
BENCHMARKS = ["SPY", "BND"]
FILES_20F = {"BP", "SHEL", "BTI", "BUD", "DEO"}         # everyone else files a 10-K


def form_for(ticker: str) -> str:
    return "20-F" if ticker in FILES_20F else "10-K"


def price_tickers(equities: list[str] | None = None) -> list[str]:
    """Everything we need prices for: equities, bonds and the SPY benchmark (deduplicated, ordered)."""
    return list(dict.fromkeys((equities or EQUITIES) + BONDS + BENCHMARKS))


# A ticker on its own ("XOM", "DD") means nothing to a trustee -- every list the API returns
# needs the real company name alongside it. SEC's own registrant name for a fund ("iSHARES
# TRUST") doesn't distinguish SHY from IEF from TIP, so those four get the fund's actual name;
# CC (Chemours) isn't in universe.json (outside the S&P 500 and not a foreign filer we added),
# so it's listed here too. Everything else resolves from data/processed/universe.json, built
# live from SEC's company_tickers.json + submissions API.
_NAME_OVERRIDES = {
    "CC": "Chemours Co",
    "SHY": "iShares 1-3 Year Treasury Bond ETF",
    "IEF": "iShares 7-10 Year Treasury Bond ETF",
    "BND": "Vanguard Total Bond Market ETF",
    "TIP": "iShares TIPS Bond ETF",
}


@lru_cache(maxsize=1)
def _universe_names() -> dict[str, str]:
    path = C.ROOT / "data" / "processed" / "universe.json"
    if not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {row["ticker"]: row["name"] for row in rows if row.get("ticker") and row.get("name")}


def name_for(ticker: str) -> str:
    """-> the real company/fund name for `ticker`, falling back to the ticker itself if truly
    unknown (never raises, never blank -- every caller displays this directly)."""
    ticker = ticker.upper()
    return _NAME_OVERRIDES.get(ticker) or _universe_names().get(ticker) or ticker
