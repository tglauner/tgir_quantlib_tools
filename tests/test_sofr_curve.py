import unittest

import QuantLib as ql
import pandas as pd

from portfolio import (
    BERMUDAN_GRID_MATURITIES_YEARS,
    BERMUDAN_GRID_NONCALL_YEARS,
    SOFR_FORWARD_HORIZON_YEARS,
    bermudan_diagonal_calibration_pillars,
    build_bermudan_pricing_grid,
    build_bermudan_gsr_model,
    build_sofr_curve,
    curve_debug_rows,
    curve_zero_rate_points,
    daily_one_day_forward_points,
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

        zero_points = curve_zero_rate_points(curve)
        forward_points = daily_one_day_forward_points(curve)

        self.assertEqual(len(zero_points), 8)
        self.assertEqual(zero_points[0]["label"], "ON")
        self.assertEqual(zero_points[-1]["label"], "12Y")
        self.assertEqual(
            len(forward_points),
            (curve.referenceDate() + ql.Period(SOFR_FORWARD_HORIZON_YEARS, ql.Years))
            - curve.referenceDate()
            + 1,
        )
        self.assertEqual(forward_points[0]["offset_days"], 0)
        self.assertEqual(
            forward_points[-1]["start_date_iso"],
            (curve.referenceDate() + ql.Period(SOFR_FORWARD_HORIZON_YEARS, ql.Years)).ISO(),
        )
        self.assertGreater(forward_points[0]["rate_pct"], 0.0)

        debug_rows = curve_debug_rows(curve, sofr_quotes)
        self.assertEqual(debug_rows[0]["date"], curve.referenceDate().ISO())
        self.assertEqual(
            len(debug_rows),
            curve.dates()[-1] - curve.referenceDate() + 1,
        )
        self.assertEqual(
            sum(row["sofr_rate_pct"] is not None for row in debug_rows),
            len(sofr_quotes),
        )
        self.assertEqual(
            sum(row["zero_rate_pct"] is not None for row in debug_rows),
            len(zero_points),
        )
        self.assertIsNone(debug_rows[-1]["forward_rate_pct"])
        self.assertGreater(debug_rows[0]["forward_rate_pct"], 0.0)

        state = default_portfolio_state()
        state["market"]["curve_quotes_pct"] = sofr_quotes
        bermudan_pillars = bermudan_diagonal_calibration_pillars(state)
        self.assertEqual(len(bermudan_pillars), 6)
        self.assertEqual(bermudan_pillars[-1]["label"], "6Y x 6Y")

        gsr_model = build_bermudan_gsr_model(state)
        self.assertEqual(len(gsr_model["calibration_rows"]), 6)
        self.assertEqual(gsr_model["calibration_rows"][0]["label"], "1Y x 1Y")
        self.assertGreater(gsr_model["sigma_rows"][0]["sigma_bp"], 0.0)

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
