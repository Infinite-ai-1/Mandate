"""Tickers and groups (CLAUDE+.md 8.1). Groups are for the demo story only."""

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
