# Quant integration

The React/Flask pipeline reuses calculate_price_metrics for observed adjusted-price
risk statistics and _whole_shares for integer allocation repair. The source registry
accepts both the ingestion dictionary API and quant keyword/stable-ID API.
Production contract types are in schemas.py. Controlled test inputs live only in
tests/quant_fixtures.py; there are no bundled example portfolios or fake price files.

Run `python -m unittest quant.test_stats quant.test_portfolio`.

The standalone quant optimiser and dividend-inclusive replay require long-form
`date,ticker,close,dividends` data: split-adjusted close excluding dividend adjustments,
with observed distributions on the same split basis. Supply that DataFrame explicitly.
The committed wide prices.parquet contains dividend-adjusted closes and must not
be paired with cash dividends for a second dividend adjustment. The active mandate
pipeline uses adjusted-price returns and separately observed trailing yields.

Historical results are not forecasts. Missing data must remain unavailable rather
than being replaced with zero. The paper account is separate from the optimiser.
