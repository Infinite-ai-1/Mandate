"""Generate clearly labelled synthetic output, without modifying shared data.

Run from the repository root: python -m quant.demo_stats
Only the demonstration injects a Metric double because schemas.py is absent.
"""
from pathlib import Path
import json
import types
from unittest.mock import patch

from quant.stats import compute_all
from quant.test_stats import StubMetric, stub_prices


def main():
    destination = Path(__file__).resolve().parent / "examples"
    destination.mkdir(exist_ok=True)
    prices = destination / "synthetic_prices.parquet"
    stub_prices().to_parquet(prices, index=False)
    sources = {}

    def register(**source):
        sources[source["source_id"]] = source

    with patch.dict("sys.modules", {"schemas": types.SimpleNamespace(Metric=StubMetric)}):
        compute_all(["TEST", "SPY", "AGG"], prices_path=prices,
                    output_dir=destination / "risk", register_source=register)
    (destination / "sources.json").write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    print("SYNTHETIC TEST DATA — past performance, not a forecast")
    print((destination / "risk/TEST.json").read_text())


if __name__ == "__main__":
    main()
