import unittest

from app import app
from portfolio import default_portfolio_state, price_portfolio


class PortfolioSmokeTests(unittest.TestCase):
    def test_price_portfolio_returns_expected_rows(self):
        df = price_portfolio(default_portfolio_state())

        self.assertListEqual(
            df["Type"].tolist(),
            ["Swap", "European Swaption", "Bermudan Swaption"],
        )
        self.assertTrue(df["NPV"].notna().all())

    def test_dashboard_renders(self):
        client = app.test_client()

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"SOFR curve, ATM vol surface, callable grid.", response.data)
        self.assertIn(b"ATM swaption normal-vol matrix", response.data)

    def test_market_update_round_trips(self):
        client = app.test_client()

        response = client.post(
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
        client = app.test_client()
        client.post(
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

        response = client.post("/api/realtime/tick")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["market_snapshot"]["callable_normal_vol_bp"], 60.0)
        self.assertEqual(len(payload["market_snapshot"]["curve_rows"]), 8)
        self.assertEqual(len(payload["blotter_rows"]), 3)
        self.assertEqual(len(payload["bermudan_grid_rows"]), 9)
        self.assertEqual(payload["blotter_rows"][0]["Type"], "Swap")

    def test_trade_editor_updates_swap_terms(self):
        client = app.test_client()

        response = client.post(
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


if __name__ == "__main__":
    unittest.main()
