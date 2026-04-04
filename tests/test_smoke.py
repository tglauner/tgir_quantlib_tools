import unittest

from tgir_quantlib_tools import create_app
from portfolio import default_portfolio_state, price_portfolio


class PortfolioSmokeTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "AUTH_USERNAME": "tester",
                "AUTH_PASSWORD": "secret-pass",
                "AUTH_PASSWORD_HASH": None,
                "SESSION_COOKIE_SECURE": False,
            }
        )
        self.client = self.app.test_client()

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
        self.assertIn(b"SOFR curve, ATM vol surface, callable grid.", response.data)
        self.assertIn(b"ATM swaption normal-vol matrix", response.data)

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
        self.assertEqual(len(payload["market_snapshot"]["curve_rows"]), 8)
        self.assertEqual(len(payload["blotter_rows"]), 3)
        self.assertEqual(len(payload["bermudan_grid_rows"]), 9)
        self.assertEqual(payload["blotter_rows"][0]["Type"], "Swap")

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

    def test_health_is_public(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "app": "tgir_quantlib_tools"})


if __name__ == "__main__":
    unittest.main()
