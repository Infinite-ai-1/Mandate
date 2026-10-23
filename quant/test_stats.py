"""Offline mathematical and contract tests; shared modules are isolated doubles."""
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from quant.stats import calculate_metrics, compute_all, load_prices


class StubMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    value: float
    unit: str
    as_of: str
    source_id: str


def stub_prices():
    dates = pd.bdate_range("2023-01-02", periods=800)
    # Deterministic changing returns, with a sustained drawdown and recovery.
    changes = 0.0004 + 0.009 * np.sin(np.arange(800) * 0.3)
    changes[320:390] -= 0.006
    rows = []
    for ticker, scale, base in [("SPY", 1.0, 400), ("TEST", 1.5, 100), ("AGG", 0.15, 95)]:
        close = base * np.cumprod(1 + scale * changes)
        dividend = np.zeros(800)
        dividend[60::63] = 0.5
        rows.append(pd.DataFrame(dict(date=dates, ticker=ticker, close=close, dividends=dividend)))
    return pd.concat(rows, ignore_index=True)


class StatsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "prices.parquet"
        stub_prices().to_parquet(self.path, index=False)

    def test_known_beta_and_cash_yield(self):
        frame = load_prices(self.path)
        as_of, values = calculate_metrics(frame, "TEST")
        self.assertAlmostEqual(values["beta"], 1.5, places=11)
        own = frame[frame.ticker == "TEST"]
        cutoff = pd.Timestamp(as_of) - pd.DateOffset(years=1)
        expected = own.loc[own.date > cutoff, "dividends"].sum() / own.close.iloc[-1]
        self.assertAlmostEqual(values["dividend_yield"], expected)
        self.assertLess(values["max_drawdown"], 0)
        self.assertLess(values["worst_12m"], 0)

    def test_spy_self_beta(self):
        self.assertAlmostEqual(calculate_metrics(load_prices(self.path), "SPY")[1]["beta"], 1)

    def test_formula_against_independent_numpy(self):
        frame = load_prices(self.path)
        close = frame.loc[frame.ticker == "TEST", "close"].to_numpy()
        _, values = calculate_metrics(frame, "TEST")
        self.assertAlmostEqual(values["annualised_volatility"], np.std(close[1:] / close[:-1] - 1, ddof=1) * np.sqrt(252))
        self.assertAlmostEqual(values["max_drawdown"], np.min(close / np.maximum.accumulate(close) - 1))
        self.assertAlmostEqual(values["worst_12m"], np.min(close[252:] / close[:-252] - 1))

    def test_registry_and_output_contract(self):
        registered = []
        with patch.dict("sys.modules", {"schemas": types.SimpleNamespace(Metric=StubMetric)}):
            result = compute_all(["test", "TEST", "SPY"], prices_path=self.path,
                                 output_dir=Path(self.temp.name) / "risk",
                                 register_source=lambda **source: registered.append(source))
        self.assertEqual(len(registered), 10)
        self.assertEqual(len(result["TEST"]), 5)
        for source in registered:
            self.assertEqual((source["kind"], source["origin"]), ("computed", "quant"))
            self.assertEqual(source["url"], f'/api/sources/{source["source_id"]}')
        output = json.loads((Path(self.temp.name) / "risk/TEST.json").read_text())
        self.assertEqual(set(output), {"ticker", "metrics"})
        self.assertEqual(output["metrics"][0]["source_id"], "Q-TEST-annualised_volatility")

    def test_bad_data_and_short_history_fail(self):
        frame = stub_prices()
        for invalid in [frame.drop(columns="dividends"), pd.concat([frame, frame.iloc[:1]]),
                        frame.assign(dividends=np.nan), frame.assign(close=0)]:
            invalid.to_parquet(self.path, index=False)
            with self.assertRaises(ValueError):
                load_prices(self.path)
        with self.assertRaisesRegex(ValueError, "253"):
            calculate_metrics(frame.groupby("ticker").head(100), "TEST")
        with self.assertRaisesRegex(ValueError, "SPY"):
            calculate_metrics(frame[frame.ticker != "SPY"], "TEST")


if __name__ == "__main__":
    unittest.main()
