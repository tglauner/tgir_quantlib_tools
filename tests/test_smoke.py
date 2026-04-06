import csv
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import QuantLib as ql
from flask import render_template

from tgir_quantlib_tools import create_app
from portfolio import SOFR_FORWARD_HORIZON_YEARS, build_sofr_curve, default_portfolio_state, price_portfolio


class PortfolioSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.curve_debug_csv_path = str(Path(self.temp_dir.name) / "curve_debug.csv")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "AUTH_USERNAME": "tester",
                "AUTH_PASSWORD": "secret-pass",
                "AUTH_PASSWORD_HASH": None,
                "SESSION_COOKIE_SECURE": False,
                "CURVE_DEBUG_CSV_PATH": self.curve_debug_csv_path,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def login(self):
        return self.client.post(
            "/login",
            data={"username": "tester", "password": "secret-pass"},
            follow_redirects=True,
        )

    def test_price_portfolio_returns_expected_rows(self):
        df = price_portfolio(default_portfolio_state())

        self.assertListEqual(
            df["Type"].tolist(),
            ["Swap", "European Swaption", "Bermudan Swaption"],
        )
        self.assertTrue(df["NPV"].notna().all())

    def test_login_page_renders(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sign in to the rates workstation.", response.data)
        self.assertIn(b"Open workstation", response.data)

    def test_dashboard_requires_login(self):
        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login?next=/dashboard", response.location)

    def test_login_redirects_to_dashboard(self):
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"SOFR zero rates, one-day forwards, ATM vol surface, callable grid.", response.data)
        self.assertIn(b"Zero rates", response.data)
        self.assertIn(b"Daily one-day forward SOFR", response.data)
        self.assertIn(b"ATM swaption normal-vol matrix", response.data)
        self.assertIn(b"Bermudan GSR seed", response.data)
        self.assertIn(self.curve_debug_csv_path.encode("utf-8"), response.data)

    def test_market_update_round_trips(self):
        self.login()

        response = self.client.post(
            "/market",
            data={
                "rate0": "4.75",
                "rate1": "4.90",
                "rate2": "5.05",
                "rate3": "5.20",
                "rate4": "5.35",
                "rate5": "5.42",
                "rate6": "5.48",
                "rate7": "5.52",
                "callable_normal_vol_bp": "72.5",
                "vol_1_1": "61.5",
                "vol_10_10": "89.5",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"72.5 bp", response.data)
        self.assertIn(b"4.75%", response.data)
        self.assertIn(b'value="61.5"', response.data)

    def test_realtime_tick_perturbs_curve_but_not_vol(self):
        self.login()
        self.client.post(
            "/market",
            data={
                "rate0": "4.85",
                "rate1": "4.98",
                "rate2": "5.04",
                "rate3": "5.09",
                "rate4": "5.17",
                "rate5": "5.22",
                "rate6": "5.28",
                "rate7": "5.31",
                "callable_normal_vol_bp": "60",
            },
        )

        response = self.client.post("/api/realtime/tick")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["market_snapshot"]["callable_normal_vol_bp"], 60.0)
        self.assertEqual(len(payload["market_snapshot"]["zero_rate_rows"]), 8)
        self.assertEqual(len(payload["forward_rate_chart"]["x_ticks"]), SOFR_FORWARD_HORIZON_YEARS + 1)
        self.assertEqual(len(payload["blotter_rows"]), 3)
        self.assertEqual(len(payload["bermudan_grid_rows"]), 9)
        self.assertEqual(payload["blotter_rows"][0]["Type"], "Swap")
        self.assertNotIn("NaN", response.get_data(as_text=True))

    def test_trade_editor_updates_swap_terms(self):
        self.login()

        response = self.client.post(
            "/trade/swap",
            data={
                "direction": "receiver",
                "notional": "2500000",
                "fixed_rate_pct": "3.85",
                "tenor_years": "6",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Receive fixed", response.data)
        self.assertIn(b"Receive fixed | 6Y | 3.85%", response.data)

    def test_trade_editor_renders_point_sensitivities(self):
        self.login()

        response = self.client.get("/trade/european_swaption")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Point sensitivities", response.data)
        self.assertIn(b"Analytics not run yet", response.data)
        self.assertIn(b"Run analytics", response.data)
        self.assertIn(b"$0.00", response.data)

    def test_trade_risk_api_returns_sensitivity_payload(self):
        self.login()

        response = self.client.get("/api/trade/swap/risk", headers={"X-Requested-With": "XMLHttpRequest"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("base_npv", payload)
        self.assertEqual(len(payload["curve_rows"]), 8)
        self.assertEqual(len(payload["vega_matrix_rows"]), 10)
        self.assertEqual(len(payload["vega_matrix_rows"][0]["cells"]), 10)

    def test_trade_template_falls_back_when_trade_risk_missing(self):
        with self.app.test_request_context("/trade/european_swaption"):
            html = render_template(
                "trade_form.html",
                trade_title="European Swaption",
                trade_description="desc",
                trade_fields=[],
                trade_headline="head",
                trade_detail="detail",
                market_snapshot={"zero_rate_rows": [], "callable_normal_vol_bp": 55.0},
                selected_matrix_vol_bp=62.0,
            )

        self.assertIn("Point sensitivities", html)
        self.assertIn("$0.00", html)

    def test_health_is_public(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "app": "tgir_quantlib_tools"})

    def test_quantlib_data_model_page_renders(self):
        self.login()

        response = self.client.get("/quantlib-data-model")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Actual object graph used by this workstation.", response.data)
        self.assertIn(b"ql.PiecewiseLogCubicDiscount", response.data)
        self.assertIn(b"ql.VanillaSwap", response.data)
        self.assertIn(b"ql.Gsr", response.data)
        self.assertIn(b"ql.Gaussian1dSwaptionEngine", response.data)

    def test_curve_debug_csv_downloads(self):
        self.login()

        response = self.client.get("/curve-debug.csv")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")
        self.assertIn("attachment; filename=", response.headers["Content-Disposition"])

        rows = list(csv.DictReader(StringIO(response.get_data(as_text=True))))
        today = ql.Date.todaysDate()
        ql.Settings.instance().evaluationDate = today
        curve = build_sofr_curve(today, default_portfolio_state()["market"]["curve_quotes_pct"])
        self.assertEqual(
            rows[0].keys(),
            {"date", "sofr_rate_pct", "zero_rate_pct", "forward_rate_pct"},
        )
        self.assertEqual(len(rows), curve.dates()[-1] - curve.referenceDate() + 1)
        self.assertEqual(rows[0]["date"], curve.referenceDate().ISO())
        self.assertEqual(rows[-1]["date"], curve.dates()[-1].ISO())
        self.assertEqual(rows[-1]["forward_rate_pct"], "")
        self.assertEqual(sum(bool(row["sofr_rate_pct"]) for row in rows), 8)
        self.assertEqual(Path(self.curve_debug_csv_path).read_text(encoding="utf-8"), response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
