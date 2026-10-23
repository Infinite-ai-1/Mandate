"""Live data fetchers, one module per public API, plus run_all/refresh orchestration.

Every fetcher here is called with a list of tickers (we only deep-fetch the ~40
companies a charity's selector actually picked). Raw API responses are cached in
data/cache/ keyed by (source, params); DEMO_MODE=1 means cache-only, zero network.
Everything fails soft: a fetcher that errors logs and returns what it has, it never
raises out of a run_all() pass.
"""
