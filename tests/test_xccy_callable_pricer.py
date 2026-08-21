import json
import unittest
from pathlib import Path

import numpy as np

from standalone_xccy_pricer import (
    FxModel,
    PricingError,
    RateModel,
    _correlation_matrix,
    _summary,
    _static_curve_pv,
    _time,
    _variance_log_fx,
    apply_lsm_policy,
    build_cashflow_plan,
    build_curves,
    build_simulation_context,
    calibrate_fx_model,
    calibrate_rate_model,
    simulate_batch,
    train_lsm,
    validate_inputs,
)


ROOT = Path(__file__).resolve().parents[1]


def load_inputs():
    market = json.loads((ROOT / "data" / "xccy_market_eurusd.json").read_text(encoding="utf-8"))
    deal = json.loads((ROOT / "data" / "xccy_deal_10y_nc2.json").read_text(encoding="utf-8"))
    return market, deal


class XccyInputTests(unittest.TestCase):
    def test_example_inputs_and_nc2_schedule_are_valid(self):
        market, deal = load_inputs()
        validate_inputs(market, deal)
        plan = build_cashflow_plan(market, deal)

        self.assertEqual(len(plan.call_dates), 8)
        self.assertEqual(plan.call_dates[0].ISO(), "2028-08-18")
        self.assertEqual(plan.call_dates[-1].ISO(), "2035-08-20")
        self.assertEqual(len(plan.schedule_summary["usd_fixed_payment_dates"]), 20)
        self.assertEqual(len(plan.schedule_summary["eur_estr_payment_dates"]), 40)

    def test_invalid_correlation_and_unknown_fields_are_rejected(self):
        market, deal = load_inputs()
        market["correlation"] = {"USD_EUR": 0.9, "USD_FX": 0.9, "EUR_FX": -0.9}
        with self.assertRaisesRegex(PricingError, "positive semidefinite"):
            validate_inputs(market, deal)

        market, deal = load_inputs()
        deal["silent_approximation"] = True
        with self.assertRaisesRegex(PricingError, "unsupported field"):
            validate_inputs(market, deal)

    def test_log_fx_variance_reduces_to_black_scholes_without_rate_volatility(self):
        zero_usd = RateModel("USD", 0.03, 0.0, (), 0.0)
        zero_eur = RateModel("EUR", 0.04, 0.0, (), 0.0)
        correlation = np.eye(3)
        maturity = 7.0
        sigma = 0.18

        variance = _variance_log_fx(
            maturity,
            zero_usd,
            zero_eur,
            np.array([maturity]),
            np.array([sigma]),
            correlation,
        )

        self.assertAlmostEqual(variance, sigma * sigma * maturity, places=12)


class XccyQuantitativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.market, cls.deal = load_inputs()
        validate_inputs(cls.market, cls.deal)
        cls.curves = build_curves(cls.market)
        cls.correlation = _correlation_matrix(cls.market)
        cls.usd_model = calibrate_rate_model(
            "USD",
            cls.curves.usd_discount,
            cls.market["swaptions"]["USD"],
            cls.market["rate_models"]["USD"],
        )
        cls.eur_model = calibrate_rate_model(
            "EUR",
            cls.curves.eur_forecast,
            cls.market["swaptions"]["EUR"],
            cls.market["rate_models"]["EUR"],
        )
        cls.fx_model = calibrate_fx_model(
            cls.market,
            cls.usd_model,
            cls.eur_model,
            cls.correlation,
        )
        cls.plan = build_cashflow_plan(cls.market, cls.deal)
        cls.context = build_simulation_context(
            cls.market,
            cls.deal,
            cls.curves,
            cls.usd_model,
            cls.eur_model,
            cls.fx_model,
            cls.correlation,
            cls.plan,
        )

    def test_calibration_reprices_curve_and_volatility_targets(self):
        curve_errors = [abs(row.get("error_bp", 0.0)) for row in self.curves.curve_rows]
        self.assertLess(max(curve_errors), 0.01)
        self.assertLess(self.usd_model.weighted_rms_relative_error, 0.05)
        self.assertLess(self.eur_model.weighted_rms_relative_error, 0.05)
        self.assertLess(self.fx_model.max_abs_vol_error, 0.0025)

    def test_zero_volatility_limit_matches_static_curve_cashflows(self):
        zero_usd = RateModel("USD", self.usd_model.mean_reversion, 0.0, (), 0.0)
        zero_eur = RateModel("EUR", self.eur_model.mean_reversion, 0.0, (), 0.0)
        zero_fx = FxModel(np.array([12.0]), np.array([0.0]), (), 0.0)
        context = build_simulation_context(
            self.market,
            self.deal,
            self.curves,
            zero_usd,
            zero_eur,
            zero_fx,
            self.correlation,
            self.plan,
        )
        batch = simulate_batch(context, 8, 7)
        benchmark = _static_curve_pv(context)["total"]

        self.assertTrue(np.all(batch.non_callable_pv == batch.non_callable_pv[0]))
        self.assertAlmostEqual(float(batch.non_callable_pv[0]), benchmark, delta=0.01)

    def test_joint_simulation_is_reproducible_and_passes_martingales(self):
        first = simulate_batch(self.context, 4096, 918273)
        second = simulate_batch(self.context, 4096, 918273)
        np.testing.assert_array_equal(first.non_callable_pv, second.non_callable_pv)

        final_time = _time(self.plan.as_of, self.plan.maturity_date)
        targets = (
            self.curves.usd_discount.discount(final_time),
            self.context.spot * self.curves.eur_effective.discount(final_time),
            self.context.spot,
        )
        samples = (
            first.domestic_discount,
            first.discounted_fx,
            first.discounted_fx_bank_account,
        )
        for values, target in zip(samples, targets):
            statistics = _summary(values)
            tolerance = 4.0 * statistics["standard_error"] + 2.0e-4 * abs(target)
            self.assertLess(abs(statistics["mean"] - target), tolerance)

    def test_two_pass_lsm_preserves_value_identity_and_probability_mass(self):
        training = simulate_batch(self.context, 2048, 20260814)
        policies, diagnostics = train_lsm(training, 0.0)
        pricing = simulate_batch(self.context, 4096, 20260815)
        callable_paths, exercise = apply_lsm_policy(pricing, policies, 0.0)
        non_callable_paths = pricing.non_callable_pv
        option_paths = callable_paths - non_callable_paths

        self.assertEqual(len(policies), len(self.plan.call_dates))
        self.assertEqual(len(diagnostics), len(self.plan.call_dates))
        self.assertTrue(all(row["rank"] == row["basis_size"] for row in diagnostics))
        probability_mass = sum(row["unconditional_probability"] for row in exercise)
        self.assertAlmostEqual(probability_mass, 1.0, places=12)
        self.assertAlmostEqual(
            float(np.mean(callable_paths)) - float(np.mean(non_callable_paths)),
            float(np.mean(option_paths)),
            places=8,
        )
        option_stats = _summary(option_paths)
        self.assertGreater(option_stats["mean"] + 4.0 * option_stats["standard_error"], 0.0)


if __name__ == "__main__":
    unittest.main()
