import copy
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from tgir_quantlib_tools.xccy_portfolio import XccyPortfolioManager, build_validation_portfolio


ROOT = Path(__file__).resolve().parents[1]


def _fake_price(market, deal):
    usd_rate = sum(item["rate"] for item in market["curves"]["USD-SOFR"]["instruments"])
    eur_rate = sum(item["rate"] for item in market["curves"]["EUR-ESTR"]["instruments"])
    usd_vol = sum(item["normal_vol_bp"] for item in market["swaptions"]["USD"]["points"])
    eur_vol = sum(item["normal_vol_bp"] for item in market["swaptions"]["EUR"]["points"])
    fx_vol = sum(item["black_vol"] for item in market["fx_options"]["points"])
    fixed_rate = next(item["fixed_rate"] for item in deal["legs"] if item["currency"] == "USD")
    npv = (deal["notionals"]["USD"] * fixed_rate + 1_000_000 * (usd_rate - eur_rate)
           + 100 * (usd_vol + eur_vol) + 1_000 * fx_vol + 10_000 * market["fx"]["spot"])
    return {"status": "OK", "valuation": {"callable_npv": {"mean": npv, "standard_error": 12.5}}}


class XccyPortfolioTests(unittest.TestCase):
    def setUp(self):
        self.market = json.loads((ROOT / "data/xccy_market_eurusd.json").read_text(encoding="utf-8"))
        self.deal = json.loads((ROOT / "data/xccy_deal_10y_nc2.json").read_text(encoding="utf-8"))

    @staticmethod
    def _wait(manager, job_id):
        for _ in range(200):
            snapshot = manager.snapshot(job_id)
            if snapshot["status"] in {"COMPLETED", "FAILED"}:
                return snapshot
            time.sleep(0.01)
        raise AssertionError("Background job did not finish in time")

    def test_builds_twenty_distinct_validating_trade_rows(self):
        rows = build_validation_portfolio(self.deal, self.market["fx"]["spot"])
        self.assertEqual(len(rows), 20)
        self.assertEqual(len({row["trade_id"] for row in rows}), 20)
        self.assertTrue(all(row["numerics"]["training_paths"] == 512 for row in rows))
        self.assertTrue(all(row["notionals"]["EUR"] > 0 for row in rows))

    def test_background_valuation_then_factor_risk(self):
        manager = XccyPortfolioManager()
        with patch("tgir_quantlib_tools.xccy_portfolio._price", side_effect=_fake_price):
            valuation = manager.start_valuation(copy.deepcopy(self.market), copy.deepcopy(self.deal))
            completed_valuation = self._wait(manager, valuation["job_id"])
            self.assertEqual(completed_valuation["status"], "COMPLETED")
            self.assertEqual(len(completed_valuation["rows"]), 20)
            self.assertEqual(completed_valuation["summary"]["trade_count"], 20)

            risk = manager.start_risk(copy.deepcopy(self.market))
            completed_risk = self._wait(manager, risk["job_id"])
            self.assertEqual(completed_risk["status"], "COMPLETED")
            self.assertEqual(len(completed_risk["rows"]), 20)
            self.assertIn("usd_hw_dv01", completed_risk["rows"][0])
            self.assertIn("eurusd_vega", completed_risk["summary"])
        manager._executor.shutdown(wait=True)

    def test_risk_requires_completed_valuation(self):
        manager = XccyPortfolioManager()
        with self.assertRaisesRegex(ValueError, "Run the 20-trade valuation"):
            manager.start_risk(self.market)
        manager._executor.shutdown(wait=True)
