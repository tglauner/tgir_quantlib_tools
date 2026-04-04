import unittest

import QuantLib as ql
import pandas as pd

from portfolio import (
    BERMUDAN_GRID_MATURITIES_YEARS,
    BERMUDAN_GRID_NONCALL_YEARS,
    build_bermudan_pricing_grid,
    build_sofr_curve,
    default_portfolio_state,
    reprice_sofr_calibration_swaps,
)


class SofrCurveTests(unittest.TestCase):
    def test_curve_reprices_all_quoted_ois_swaps(self):
        today = ql.Date.todaysDate()
        ql.Settings.instance().evaluationDate = today
        sofr_quotes = [4.85, 4.98, 5.04, 5.09, 5.17, 5.22, 5.28, 5.31]

        curve = build_sofr_curve(today, sofr_quotes)
        repriced = reprice_sofr_calibration_swaps(curve, sofr_quotes)

        self.assertListEqual(
            repriced["Tenor"].tolist(),
            ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "12Y"],
        )
        for npv in repriced["NPV"]:
            self.assertAlmostEqual(npv, 0.0, places=10)

    def test_default_state_exposes_10x10_vol_matrix_and_bermudan_grid(self):
        state = default_portfolio_state()
        matrix = state["market"]["swaption_vol_matrix_bp"]
        grid = build_bermudan_pricing_grid(state)

        self.assertEqual(len(matrix), 10)
        self.assertTrue(all(len(row) == 10 for row in matrix))
        self.assertListEqual(
            grid.columns.tolist(),
            ["Non-call"] + [f"{year}Y" for year in BERMUDAN_GRID_MATURITIES_YEARS],
        )
        self.assertEqual(len(grid), len(BERMUDAN_GRID_NONCALL_YEARS))
        self.assertTrue(pd.isna(grid.iloc[-1]["2Y"]))
        self.assertIsNotNone(grid.iloc[0]["10Y"])


if __name__ == "__main__":
    unittest.main()
