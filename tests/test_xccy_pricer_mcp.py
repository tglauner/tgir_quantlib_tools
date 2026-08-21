import asyncio
import json
import unittest
from pathlib import Path

from mcp import Client

from standalone_xccy_pricer import price
from xccy_pricer_diagnostics import bump_revaluation_diagnostics, path_convergence_diagnostics
from xccy_pricer_mcp import mcp, validate_deal_inputs


ROOT = Path(__file__).resolve().parents[1]


def load_inputs():
    market = json.loads((ROOT / "data" / "xccy_market_eurusd.json").read_text(encoding="utf-8"))
    deal = json.loads((ROOT / "data" / "xccy_deal_10y_nc2.json").read_text(encoding="utf-8"))
    return market, deal


class XccyMcpValidationTests(unittest.TestCase):
    def test_incomplete_inputs_return_specific_questions(self):
        _, deal = load_inputs()
        response = validate_deal_inputs(None, deal)

        self.assertEqual(response.status, "NEEDS_INPUT")
        self.assertFalse(response.ready_to_price)
        self.assertIn("Please provide the complete market-data object.", response.questions)

    def test_semantically_invalid_deal_is_not_ready(self):
        market, deal = load_inputs()
        deal["legs"][0]["currency"] = "USD"
        response = validate_deal_inputs(market, deal)

        self.assertEqual(response.status, "INVALID")
        self.assertFalse(response.ready_to_price)
        self.assertTrue(response.questions)

    def test_in_process_mcp_contract_and_single_valuation(self):
        market, deal = load_inputs()

        async def exercise_tools():
            async with Client(mcp) as client:
                listed = await client.list_tools()
                tools = {tool.name: tool for tool in listed.tools}
                self.assertEqual(set(tools), {"xccy_validate_deal", "xccy_price_deal"})
                self.assertTrue(tools["xccy_price_deal"].annotations.read_only_hint)
                self.assertIsNotNone(tools["xccy_price_deal"].output_schema)

                missing = await client.call_tool(
                    "xccy_validate_deal",
                    {"request": {"market_data": None, "deal_data": deal}},
                )
                self.assertFalse(missing.is_error)
                self.assertEqual(missing.structured_content["status"], "NEEDS_INPUT")
                self.assertTrue(missing.structured_content["questions"])

                valued = await client.call_tool(
                    "xccy_price_deal",
                    {
                        "request": {
                            "market_data": market,
                            "deal_data": deal,
                            "training_paths": 256,
                            "pricing_paths": 512,
                            "include_convergence": True,
                        }
                    },
                )
                self.assertFalse(valued.is_error)
                self.assertEqual(valued.structured_content["status"], "OK")
                self.assertEqual(valued.structured_content["trade_id"], deal["trade_id"])
                self.assertTrue(valued.structured_content["convergence"]["passed"])
                self.assertIn("callable_npv", valued.structured_content["valuation"]["valuation"])

        asyncio.run(exercise_tools())


class XccyRiskControlTests(unittest.TestCase):
    def test_common_random_number_greeks_are_half_bump_stable(self):
        market, deal = load_inputs()
        diagnostics = bump_revaluation_diagnostics(market, deal, 1024, 2048, 1729)

        self.assertTrue(diagnostics["all_stability_checks_passed"])
        self.assertEqual(
            set(diagnostics["greeks"]),
            {"fx_delta_usd_per_1pct", "usd_parallel_dv01", "eur_parallel_dv01"},
        )
        for row in diagnostics["greeks"].values():
            self.assertLessEqual(row["stability"]["relative_difference"], 0.20)

    def test_independent_path_count_convergence_is_within_four_standard_errors(self):
        market, deal = load_inputs()
        base = price(
            market,
            deal,
            {"training_paths": 512, "pricing_paths": 1024, "chunk_size": 1024, "seed": 1729},
        )
        diagnostics = path_convergence_diagnostics(market, deal, base, 512, 1024, 1729)

        self.assertTrue(diagnostics["passed"])
        self.assertLessEqual(abs(diagnostics["z_score"]), 4.0)
        self.assertLess(diagnostics["low"]["pricing_paths"], diagnostics["high"]["pricing_paths"])


if __name__ == "__main__":
    unittest.main()
