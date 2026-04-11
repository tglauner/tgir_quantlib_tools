import math
import unittest

import QuantLib as ql
import pandas as pd

from portfolio import (
    BERMUDAN_MODEL_G2PP,
    BERMUDAN_MODEL_HULL_WHITE_1F,
    BERMUDAN_GRID_MATURITIES_YEARS,
    BERMUDAN_GRID_NONCALL_YEARS,
    DEFAULT_VALUATION_DATE_ISO,
    SOFR_FORWARD_HORIZON_YEARS,
    SOFR_DEFAULT_CURVE_QUOTES_PCT,
    SOFR_CURVE_TENOR_LABELS,
    SWAPTION_MATRIX_EXPIRY_LABELS,
    SWAPTION_MATRIX_TENOR_LABELS,
    _bermudan_schedule_context,
    _create_bermudan_swaption,
    _default_swaption_normal_vol_matrix_bp,
    bermudan_diagonal_calibration_pillars,
    bermudan_exercise_schedule_rows,
    build_bermudan_pricing_grid,
    build_bermudan_short_rate_model,
    build_sofr_curve,
    curve_debug_rows,
    curve_zero_rate_points,
    daily_one_day_forward_points,
    default_portfolio_state,
    lookup_swaption_normal_vol_bp,
    normalize_portfolio_state,
    reprice_sofr_calibration_swaps,
    trade_point_sensitivities,
    valuation_date,
)


class SofrCurveTests(unittest.TestCase):
    def test_curve_reprices_all_quoted_ois_swaps(self):
        today = valuation_date(default_portfolio_state())
        ql.Settings.instance().evaluationDate = today
        sofr_quotes = list(SOFR_DEFAULT_CURVE_QUOTES_PCT)

        curve = build_sofr_curve(today, sofr_quotes)
        repriced = reprice_sofr_calibration_swaps(curve, sofr_quotes)

        self.assertListEqual(
            repriced["Tenor"].tolist(),
            list(SOFR_CURVE_TENOR_LABELS[1:]),
        )
        for npv in repriced["NPV"]:
            self.assertAlmostEqual(npv, 0.0, places=10)

        zero_points = curve_zero_rate_points(curve)
        forward_points = daily_one_day_forward_points(curve)

        self.assertEqual(len(zero_points), len(SOFR_CURVE_TENOR_LABELS))
        self.assertEqual(zero_points[0]["label"], "1D")
        self.assertEqual(zero_points[-1]["label"], "30Y")
        zero_by_label = {point["label"]: point for point in zero_points}
        day_counter = ql.Actual365Fixed()
        one_day_date = ql.DateParser.parseISO(zero_by_label["1D"]["date_iso"])
        one_day_time = day_counter.yearFraction(curve.referenceDate(), one_day_date)
        expected_one_day_zero_pct = -math.log(curve.discount(one_day_date)) / one_day_time * 100.0
        self.assertAlmostEqual(zero_by_label["1D"]["rate_pct"], expected_one_day_zero_pct, places=10)
        self.assertLessEqual(zero_by_label["3Y"]["rate_pct"], zero_by_label["4Y"]["rate_pct"])
        self.assertLessEqual(zero_by_label["4Y"]["rate_pct"], zero_by_label["6Y"]["rate_pct"])
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
        self.assertEqual(len(bermudan_pillars), 4)
        self.assertEqual(bermudan_pillars[-1]["label"], "4Y x 1Y")

        short_rate_model = build_bermudan_short_rate_model(state)
        self.assertEqual(short_rate_model["model_name"], BERMUDAN_MODEL_HULL_WHITE_1F)
        self.assertEqual(len(short_rate_model["calibration_rows"]), 4)
        self.assertEqual(short_rate_model["calibration_rows"][0]["label"], "1Y x 4Y")
        self.assertGreater(short_rate_model["parameter_rows"][-1]["value"], 0.0)
        for row in short_rate_model["calibration_rows"]:
            self.assertGreater(row["market_value"], 0.0)
            self.assertGreater(row["model_value"], 0.0)
            self.assertLess(abs(row["calibration_error"]), 0.10)

    def test_default_state_exposes_workbook_surface_and_bermudan_grid(self):
        state = default_portfolio_state()
        matrix = state["market"]["swaption_vol_matrix_bp"]
        grid = build_bermudan_pricing_grid(state)

        self.assertEqual(len(matrix), len(SWAPTION_MATRIX_EXPIRY_LABELS))
        self.assertTrue(all(len(row) == len(SWAPTION_MATRIX_TENOR_LABELS) for row in matrix))
        self.assertEqual(state["valuation_date_iso"], DEFAULT_VALUATION_DATE_ISO)
        self.assertNotIn("3Y", SWAPTION_MATRIX_EXPIRY_LABELS)
        self.assertAlmostEqual(lookup_swaption_normal_vol_bp(state, 3, 3), 77.355, places=3)
        self.assertEqual(state["trades"]["swap"]["notional"], 100_000_000)
        self.assertEqual(state["trades"]["european_swaption"]["notional"], 100_000_000)
        self.assertEqual(state["trades"]["bermudan_swaption"]["notional"], 100_000_000)
        self.assertEqual(state["trades"]["bermudan_swaption_2"]["notional"], 100_000_000)
        self.assertListEqual(
            grid.columns.tolist(),
            ["Non-call"] + [f"{year}Y" for year in BERMUDAN_GRID_MATURITIES_YEARS],
        )
        self.assertEqual(len(grid), len(BERMUDAN_GRID_NONCALL_YEARS))
        self.assertTrue(pd.isna(grid.iloc[-1]["2Y"]))
        self.assertIsNotNone(grid.iloc[0]["10Y"])

    def test_swap_point_sensitivities_show_all_curve_nodes_and_zero_vega_cells(self):
        sensitivities = trade_point_sensitivities("swap", default_portfolio_state())

        self.assertEqual(len(sensitivities["curve_rows"]), len(SOFR_CURVE_TENOR_LABELS))
        self.assertListEqual(
            [row["label"] for row in sensitivities["curve_rows"]],
            list(SOFR_CURVE_TENOR_LABELS),
        )
        self.assertTrue(any(row["delta_npv"] != 0.0 for row in sensitivities["curve_rows"]))
        self.assertEqual(len(sensitivities["vega_matrix_rows"]), len(SWAPTION_MATRIX_EXPIRY_LABELS))
        self.assertTrue(
            all(len(row["cells"]) == len(SWAPTION_MATRIX_TENOR_LABELS) for row in sensitivities["vega_matrix_rows"])
        )
        self.assertTrue(
            all(
                cell["delta_npv"] == 0.0
                for row in sensitivities["vega_matrix_rows"]
                for cell in row["cells"]
            )
        )
        self.assertEqual(sensitivities["model_parameter_row"]["delta_npv"], 0.0)

    def test_european_swaption_only_moves_selected_matrix_pillar(self):
        sensitivities = trade_point_sensitivities("european_swaption", default_portfolio_state())
        nonzero_labels = [
            cell["label"]
            for row in sensitivities["vega_matrix_rows"]
            for cell in row["cells"]
            if cell["delta_npv"] != 0.0
        ]

        self.assertListEqual(nonzero_labels, ["1Y x 4Y"])
        self.assertEqual(sensitivities["model_parameter_row"]["label"], "Hull-White mean reversion")
        self.assertNotEqual(sensitivities["model_parameter_row"]["delta_npv"], 0.0)

    def test_bermudan_swaption_uses_diagonal_calibration_strip_only(self):
        labels = [pillar["label"] for pillar in bermudan_diagonal_calibration_pillars(default_portfolio_state())]
        sensitivities = trade_point_sensitivities("bermudan_swaption", default_portfolio_state())
        nonzero_vega_labels = [
            cell["label"]
            for row in sensitivities["vega_matrix_rows"]
            for cell in row["cells"]
            if cell["delta_npv"] != 0.0
        ]

        self.assertListEqual(labels, ["1Y x 4Y", "2Y x 3Y", "3Y x 2Y", "4Y x 1Y"])
        self.assertListEqual(nonzero_vega_labels, ["1Y x 4Y", "2Y x 2Y", "2Y x 3Y", "4Y x 1Y", "4Y x 2Y"])

    def test_workbook_bermudan_calibration_strip_matches_call_schedule(self):
        rows = bermudan_exercise_schedule_rows(default_portfolio_state(), trade_key="bermudan_swaption_2")

        self.assertListEqual(
            [row["schedule_label"] for row in rows],
            ["2Y x 3Y", "3Y x 2Y", "4Y x 1Y"],
        )
        self.assertEqual(rows[1]["calibration_label"], "3Y x 2Y")
        self.assertEqual(rows[1]["source_market_points"], [("2Y", "2Y"), ("4Y", "2Y")])
        self.assertEqual(
            rows[1]["exercise_probability_label"],
            "Not exposed by QuantLib tree swaption engines",
        )

    def test_bermudan_schedule_keeps_fixed_final_maturity_and_shortens_underlying_tenor(self):
        today = ql.Date(10, 3, 2026)
        ql.Settings.instance().evaluationDate = today
        calendar = ql.UnitedStates(ql.UnitedStates.Settlement)
        trade = default_portfolio_state()["trades"]["bermudan_swaption"]
        trade["first_exercise_years"] = 2
        trade["final_maturity_years"] = 5
        trade["payment_frequency_months"] = 12
        trade["reset_frequency_months"] = 12

        schedule_context = _bermudan_schedule_context(trade, today, calendar)
        fixed_schedule_dates = list(schedule_context["fixed_schedule"])
        remaining_coupon_counts = [
            len(fixed_schedule_dates) - schedule_index - 1
            for schedule_index in range(len(fixed_schedule_dates) - 1)
        ]
        exercise_dates = [date.ISO() for date in schedule_context["exercise_dates"]]

        self.assertEqual(schedule_context["first_exercise"].ISO(), "2028-03-13")
        self.assertEqual(schedule_context["final_maturity"].ISO(), "2031-03-12")
        self.assertListEqual([date.ISO() for date in fixed_schedule_dates], ["2028-03-13", "2029-03-13", "2030-03-13", "2031-03-12"])
        self.assertListEqual(exercise_dates, ["2028-03-10", "2029-03-12", "2030-03-12"])
        self.assertListEqual(remaining_coupon_counts, [3, 2, 1])

    def test_workbook_reference_bermudan_tracks_excel_mark(self):
        state = normalize_portfolio_state(
            {
                "market": {
                    "curve_quotes_pct": list(SOFR_DEFAULT_CURVE_QUOTES_PCT),
                    "hw_mean_reversion": 0.03,
                    "swaption_vol_matrix_bp": _default_swaption_normal_vol_matrix_bp(),
                },
                "trades": {
                    "bermudan_swaption": {
                        "direction": "payer",
                        "notional": 100_000_000,
                        "strike_pct": 3.4,
                        "first_exercise_years": 2,
                        "final_maturity_years": 5,
                        "payment_frequency_months": 12,
                        "reset_frequency_months": 12,
                        "model_name": BERMUDAN_MODEL_HULL_WHITE_1F,
                    }
                },
            }
        )
        today = ql.Date(10, 3, 2026)
        ql.Settings.instance().evaluationDate = today
        calendar = ql.UnitedStates(ql.UnitedStates.Settlement)
        curve = build_sofr_curve(today, state["market"]["curve_quotes_pct"])
        curve_handle = ql.YieldTermStructureHandle(curve)
        market_context = (state, today, calendar, curve, curve_handle)
        bermudan_engine = build_bermudan_short_rate_model(state, market_context=market_context)["engine"]
        npv = _create_bermudan_swaption(
            state["trades"]["bermudan_swaption"],
            today,
            calendar,
            curve_handle,
            bermudan_engine,
        ).NPV()

        self.assertGreater(npv, 0.0)
        self.assertAlmostEqual(npv, 1_414_296.66, delta=20_000.0)

    def test_g2pp_bermudan_model_builds_with_two_factor_parameters(self):
        state = default_portfolio_state()
        state["trades"]["bermudan_swaption"]["model_name"] = BERMUDAN_MODEL_G2PP

        model = build_bermudan_short_rate_model(state, trade_key="bermudan_swaption")

        self.assertEqual(model["model_name"], BERMUDAN_MODEL_G2PP)
        parameter_names = [row["parameter"] for row in model["parameter_rows"]]
        self.assertListEqual(parameter_names, ["a", "sigma", "b", "eta", "rho"])


if __name__ == "__main__":
    unittest.main()
