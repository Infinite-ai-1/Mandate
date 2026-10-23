import types
import unittest
from unittest.mock import patch
import numpy as np

from quant.contract_fixtures import CHARITIES, Portfolio, fixture_inputs
from quant.optimiser import optimise, _whole_shares
from quant.backtest import replay

class PortfolioTests(unittest.TestCase):
    def run_optimiser(self, rules, decisions, prices):
        with patch.dict("sys.modules", {"schemas": types.SimpleNamespace(Portfolio=Portfolio)}):
            return optimise(decisions, rules, prices, gbpusd=1.30, register_source=lambda **s: None)

    def test_all_charities_validate_and_keep_ethics(self):
        for cid, name, _ in CHARITIES:
            with self.subTest(charity=cid):
                prices, rules, decisions = fixture_inputs(cid, name)
                p = self.run_optimiser(rules, decisions, prices)
                self.assertTrue(p.checks.bonds_ok)
                self.assertTrue(p.checks.yield_ok)
                self.assertIn("past performance, not a forecast", p.memo)
                self.assertAlmostEqual(sum(h.usd for h in p.holdings) + p.cash_usd, 100000)
                self.assertGreaterEqual(p.cash_usd, -1e-6)
                for h in p.holdings:
                    self.assertNotIn(h.ticker, ["VETO", "REVIEW", "SPY"])
                    self.assertLessEqual(h.weight, h.cap + 1e-8)
                    self.assertEqual(h.shares, int(h.shares))
                    if not h.is_bond:
                        self.assertEqual(h.reason, next(d["reason"] for d in decisions if d["ticker"]==h.ticker))

    def test_cap_then_yield_relaxation_and_original_checks(self):
        prices, rules, decisions = fixture_inputs(*CHARITIES[0][:2])
        rules["constraints"]["min_yield"] = .15
        p = self.run_optimiser(rules, decisions, prices)
        self.assertIn("Raised", p.relaxed[0])
        self.assertIn("Lowered", p.relaxed[1])
        self.assertFalse(p.checks.yield_ok)
        self.assertEqual(decisions[1]["cap"], .03)

    def test_infeasible_all_cash_and_no_rejected_bond(self):
        prices, rules, decisions = fixture_inputs(*CHARITIES[0][:2])
        decisions.extend([dict(ticker=t, decision="REJECT", cap=0, decided_by="code_veto", reason="Excluded", source_ids=[], weighted_score=None) for t in ("AGG", "BND")])
        p = self.run_optimiser(rules, decisions, prices)
        self.assertEqual(p.cash_usd, 100000)
        self.assertFalse(p.checks.bonds_ok)
        self.assertTrue(any("No feasible" in r for r in p.relaxed))

    def test_integer_repair_keeps_cap_and_bond_floor(self):
        import pandas as pd
        latest = pd.Series([213.0, 137.0], index=["TEST", "AGG"])
        q = _whole_shares(np.array([.1, .9]), latest, np.array([.1, 1]), np.array([0, 1]), np.array([.02, .04]), .9, .035)
        self.assertIsNotNone(q)
        self.assertLessEqual(q[0]*213, 10000)
        self.assertGreaterEqual(q[1]*137, 90000)
        self.assertLessEqual(q @ latest.to_numpy(), 100000)

    def test_cash_backtest_and_missing_benchmark(self):
        prices, rules, _ = fixture_inputs(*CHARITIES[0][:2])
        risk, checks = replay([], 100000, 100000, rules, prices)
        self.assertEqual(risk["volatility"], 0)
        self.assertEqual(risk["worst_12m"], 0)
        self.assertFalse(checks["yield_ok"])
        with self.assertRaisesRegex(ValueError, "AGG"):
            replay([], 100000, 100000, rules, prices[prices.ticker != "AGG"])

    def test_fx_must_be_observed(self):
        prices, rules, decisions = fixture_inputs(*CHARITIES[0][:2])
        with patch.dict("sys.modules", {"schemas": types.SimpleNamespace(Portfolio=Portfolio)}):
            with self.assertRaisesRegex(ValueError, "gbpusd"):
                optimise(decisions, rules, prices)

if __name__ == "__main__":
    unittest.main()
