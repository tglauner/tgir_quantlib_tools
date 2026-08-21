from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tgir_quantlib_tools import create_app


class CallableXccyPageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1]
        self.market_path = Path(self.temp_dir.name) / "market.json"
        self.deal_path = Path(self.temp_dir.name) / "deal.json"
        self.result_path = Path(self.temp_dir.name) / "result.json"
        shutil.copyfile(root / "data" / "xccy_market_eurusd.json", self.market_path)
        shutil.copyfile(root / "data" / "xccy_deal_10y_nc2.json", self.deal_path)
        shutil.copyfile(root / "result.json", self.result_path)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "AUTH_USERNAME": "tester",
                "AUTH_PASSWORD": "secret-pass",
                "AUTH_PASSWORD_HASH": None,
                "SESSION_COOKIE_SECURE": False,
                "CURVE_DEBUG_CSV_PATH": str(Path(self.temp_dir.name) / "curve_debug.csv"),
                "XCCY_MARKET_JSON_PATH": str(self.market_path),
                "XCCY_DEAL_JSON_PATH": str(self.deal_path),
                "XCCY_RESULT_JSON_PATH": str(self.result_path),
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def login(self):
        return self.client.post(
            "/login",
            data={"username": "tester", "password": "secret-pass"},
        )

    def test_page_requires_login(self):
        response = self.client.get("/xccy-callable")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login?next=/xccy-callable", response.location)

    def test_dashboard_links_to_callable_xccy_page(self):
        self.login()

        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="open-xccy-callable"', response.data)
        self.assertIn(b'href="/xccy-callable"', response.data)
        self.assertIn(b"Open XCCY callable lab", response.data)

    def test_callable_xccy_page_renders_quantitative_content(self):
        self.login()

        response = self.client.get("/xccy-callable")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Callable cross-currency", html)
        self.assertIn("EURUSD-10Y-NC2-ESTR-VS-USD4", html)
        self.assertIn("Two Hull–White factors and lognormal FX", html)
        self.assertIn('<math display="block"', html)
        self.assertIn("Domestic-measure dynamics", html)
        self.assertIn("negative EUR quanto term", html)
        self.assertIn('id="rho_usd_eur"', html)
        self.assertIn('id="xccy-reprice-button"', html)
        self.assertIn("Recalibrate &amp; reprice", html)
        self.assertIn("Exact implementation definition", html)
        self.assertIn("equal weight", html)
        self.assertIn("Backward regression, forward stopping", html)
        self.assertIn("Domestic-numeraire martingales", html)
        self.assertIn("QuantLib responsibilities", html)
        self.assertIn("STORED · NOT LIVE", html)
        stored_result = json.loads(self.result_path.read_text(encoding="utf-8"))
        expected_npv = stored_result["valuation"]["callable_npv"]["mean"]
        self.assertIn(f"${expected_npv:,.2f}", html)
        self.assertNotIn("NaN", html)

    def test_authenticated_json_views_return_exact_inputs(self):
        self.login()

        for dataset, expected_schema in (
            ("market", "xccy-market/1.0"),
            ("deal", "callable-xccy-deal/1.0"),
            ("result", "callable-xccy-result/1.0"),
        ):
            with self.subTest(dataset=dataset):
                response = self.client.get(f"/xccy-callable/json/{dataset}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "application/json")
                self.assertEqual(json.loads(response.data)["schema"], expected_schema)
                self.assertIn("inline; filename=", response.headers["Content-Disposition"])

    def test_unknown_json_dataset_is_not_exposed(self):
        self.login()

        response = self.client.get("/xccy-callable/json/unknown")

        self.assertEqual(response.status_code, 404)

    def test_invalid_non_psd_correlation_is_rejected_without_pricing(self):
        self.login()
        original_result = self.result_path.read_text(encoding="utf-8")

        with patch("tgir_quantlib_tools.xccy_page.price") as price_mock:
            response = self.client.post(
                "/xccy-callable/price",
                data={
                    "market_source": "local_json",
                    "rho_usd_eur": "0.90",
                    "rho_usd_fx": "0.90",
                    "rho_eur_fx": "-0.90",
                },
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"not positive semidefinite", response.data)
        price_mock.assert_not_called()
        self.assertEqual(self.result_path.read_text(encoding="utf-8"), original_result)

    def test_valid_web_correlations_reprice_local_json_and_refresh_result(self):
        self.login()
        stored_result = json.loads(self.result_path.read_text(encoding="utf-8"))
        repriced_result = copy.deepcopy(stored_result)
        repriced_result["run_id"] = "web-reprice-test"
        repriced_result["model"]["correlation"] = [
            [1.0, 0.10, -0.20],
            [0.10, 1.0, -0.25],
            [-0.20, -0.25, 1.0],
        ]
        repriced_result["valuation"]["callable_npv"]["mean"] = 8_500_000.0

        with patch("tgir_quantlib_tools.xccy_page.price", return_value=repriced_result) as price_mock:
            response = self.client.post(
                "/xccy-callable/price",
                data={
                    "market_source": "local_json",
                    "rho_usd_eur": "0.10",
                    "rho_usd_fx": "-0.20",
                    "rho_eur_fx": "-0.25",
                },
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"recalibration and repricing completed", response.data)
        self.assertIn(b"$8,500,000.00", response.data)
        priced_market, priced_deal = price_mock.call_args.args
        self.assertEqual(
            priced_market["correlation"],
            {"USD_EUR": 0.10, "USD_FX": -0.20, "EUR_FX": -0.25},
        )
        self.assertEqual(priced_deal["trade_id"], "EURUSD-10Y-NC2-ESTR-VS-USD4")
        self.assertEqual(
            json.loads(self.result_path.read_text(encoding="utf-8"))["run_id"],
            "web-reprice-test",
        )


if __name__ == "__main__":
    unittest.main()
