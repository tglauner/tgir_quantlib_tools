import unittest

from app import app
from portfolio import price_portfolio


class PortfolioSmokeTests(unittest.TestCase):
    def test_price_portfolio_returns_expected_rows(self):
        df = price_portfolio([5.0, 5.1, 5.2, 5.3, 5.4])

        self.assertListEqual(
            df["Type"].tolist(),
            ["Swap", "European Swaption", "Bermudan Swaption"],
        )
        self.assertTrue(df["NPV"].notna().all())

    def test_homepage_renders(self):
        client = app.test_client()

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Portfolio Blotter", response.data)


if __name__ == "__main__":
    unittest.main()
