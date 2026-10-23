"""Generic disk cache for raw API responses, keyed by (source, params).

CLAUDE.md: "Cache every raw API response in data/cache/ keyed by source + params.
Never refetch cached items except in refresh() and search_new_topic()." and
"DEMO_MODE=1: no network, cache only."

Usage, from any ingest/*.py fetcher:

    from ingest._cache import cached_fetch

    def get_quote(ticker):
        return cached_fetch("finnhub_quote", {"ticker": ticker}, lambda: _http_get(...))

cached_fetch() never raises: on a cache miss in DEMO_MODE it returns None, and on a
genuine fetch failure it logs and returns None, so callers just need to handle None.
"""
import hashlib
import json
import os
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(HERE, "data", "cache")


def demo_mode():
    return os.environ.get("DEMO_MODE", "0") == "1"


def _cache_path(source, params):
    blob = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]
    safe_source = "".join(c if c.isalnum() or c in "-_." else "_" for c in source)
    return os.path.join(CACHE_DIR, f"{safe_source}__{digest}.json")


def cache_read(source, params):
    """-> the cached value for (source, params), or None if not cached."""
    path = _cache_path(source, params)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)["data"]
    except Exception as exc:
        print(f"[cache] corrupt entry {path}, ignoring ({exc})")
        return None


def cache_write(source, params, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(source, params)
    with open(path, "w") as f:
        json.dump({"source": source, "params": params, "fetched_at": time.time(), "data": data}, f)
    return data


def cached_fetch(source, params, fetch_fn, bypass_cache=False):
    """Returns cached data for (source, params) if present (unless bypass_cache),
    else calls fetch_fn() -- unless DEMO_MODE is set, in which case it fails soft
    and returns None instead of hitting the network.

    fetch_fn takes no arguments and should return JSON-serialisable data, or raise
    on failure (the exception is caught, logged, and turned into a None return).
    bypass_cache=True is for refresh()/search_new_topic(), which must re-fetch even
    when a cached entry exists; the fresh result still overwrites the cache entry.
    """
    if not bypass_cache:
        cached = cache_read(source, params)
        if cached is not None:
            return cached

    if demo_mode():
        print(f"[cache] DEMO_MODE=1, no cached entry for {source} {params}, skipping")
        return None

    try:
        data = fetch_fn()
    except Exception as exc:
        print(f"[fetch] {source} {params} failed: {exc}")
        return None

    if data is not None:
        cache_write(source, params, data)
    return data


class RateLimiter:
    """Simple sleep-based limiter: min_interval seconds between calls, shared across
    all callers that hold the same RateLimiter instance."""

    def __init__(self, min_interval):
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self):
        elapsed = time.monotonic() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()
