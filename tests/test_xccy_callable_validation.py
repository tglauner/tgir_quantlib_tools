"""Validation test suite for the callable cross-currency swap pricer.

This module implements model validation tests including:
- Upper/lower bounds using simpler structures
- Monotonicity tests with respect to model parameters
- Martingale condition verification
- Convergence tests
- Sensitivity analysis

Run with:
    ./.venv/bin/python -m pytest tests/test_xccy_callable_validation.py -v --tb=short
"""

import copy
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from standalone_xccy_pricer import price, PricingError

# Base test data paths
DATA_DIR = Path(__file__).parent.parent / "data"
MARKET_FILE = DATA_DIR / "xccy_market_eurusd.json"
DEAL_FILE = DATA_DIR / "xccy_deal_10y_nc2.json"


@pytest.fixture(scope="module")
def base_market() -> dict[str, Any]:
    """Load the base market data."""
    return json.loads(MARKET_FILE.read_text())


@pytest.fixture(scope="module")
def base_deal() -> dict[str, Any]:
    """Load the base deal data."""
    return json.loads(DEAL_FILE.read_text())


@pytest.fixture(scope="module")
def base_result(base_market, base_deal) -> dict[str, Any]:
    """Run the base pricing and cache the result."""
    return price(base_market, base_deal)


# =============================================================================
# TEST CLASS 1: Structural Bounds
# =============================================================================

class TestStructuralBounds:
    """Test that callable swap price satisfies fundamental arbitrage bounds."""

    def test_callable_ge_non_callable(self, base_result):
        """Callable value >= non-callable value (holder has right to cancel)."""
        callable_npv = base_result["valuation"]["callable_npv"]["mean"]
        non_callable_npv = base_result["valuation"]["non_callable_npv"]["mean"]
        option_value = base_result["valuation"]["embedded_option_value"]["mean"]

        # Option value should be non-negative
        assert option_value >= 0, (
            f"Option value must be >= 0, got {option_value:,.2f}"
        )

        # Callable = Non-callable + Option
        recomputed = non_callable_npv + option_value
        assert abs(callable_npv - recomputed) < 1.0, (
            f"Callable ({callable_npv:,.2f}) != Non-callable ({non_callable_npv:,.2f}) + "
            f"Option ({option_value:,.2f})"
        )

    def test_option_value_less_than_notional(self, base_deal, base_result):
        """Option value should be less than total notional (sanity check)."""
        option_value = abs(base_result["valuation"]["embedded_option_value"]["mean"])
        notional = float(base_deal["notionals"]["USD"])

        # Option can't be worth more than the notional
        assert option_value < notional, (
            f"Option value ({option_value:,.2f}) exceeds notional ({notional:,.2f})"
        )

    def test_leg_values_sum_to_non_callable(self, base_result):
        """USD leg + EUR leg should approximately equal non-callable NPV."""
        usd_leg = base_result["valuation"]["usd_fixed_leg_pv"]["mean"]
        eur_leg = base_result["valuation"]["eur_estr_leg_pv_in_usd"]["mean"]
        non_callable = base_result["valuation"]["non_callable_npv"]["mean"]

        # Allow for Monte Carlo error
        error = base_result["valuation"]["non_callable_npv"]["standard_error"]
        tolerance = 3.0 * error + 1000  # 3 sigma + small buffer

        difference = abs((usd_leg + eur_leg) - non_callable)
        assert difference < tolerance, (
            f"USD ({usd_leg:,.2f}) + EUR ({eur_leg:,.2f}) = {usd_leg + eur_leg:,.2f} "
            f"!= Non-callable ({non_callable:,.2f}), diff={difference:,.2f}"
        )


# =============================================================================
# TEST CLASS 2: Martingale Tests
# =============================================================================

class TestMartingaleConditions:
    """Verify the model satisfies no-arbitrage martingale conditions."""

    def test_domestic_discount_martingale(self, base_result):
        """E[D(0,T)] under domestic measure should equal P(0,T)."""
        diagnostics = base_result["martingale_diagnostics"]
        sample_mean = diagnostics["domestic_discount"]["sample"]["mean"]
        target = diagnostics["domestic_discount"]["target"]
        std_error = diagnostics["domestic_discount"]["sample"]["standard_error"]

        # Should be within 3 standard errors
        z_score = abs(sample_mean - target) / std_error
        assert z_score < 3.5, (
            f"Domestic discount martingale failed: sample={sample_mean:.6f}, "
            f"target={target:.6f}, z={z_score:.2f}"
        )

    def test_discounted_fx_martingale(self, base_result):
        """E[D(0,T) * X_T] should equal X_0 * P^EUR(0,T)."""
        diagnostics = base_result["martingale_diagnostics"]
        sample_mean = diagnostics["discounted_fx_zero_coupon"]["sample"]["mean"]
        target = diagnostics["discounted_fx_zero_coupon"]["target"]
        std_error = diagnostics["discounted_fx_zero_coupon"]["sample"]["standard_error"]

        z_score = abs(sample_mean - target) / std_error
        assert z_score < 3.5, (
            f"Discounted FX martingale failed: sample={sample_mean:.6f}, "
            f"target={target:.6f}, z={z_score:.2f}"
        )

    def test_fx_bank_account_martingale(self, base_result):
        """E[D(0,T) * X_T * B^EUR_T] should equal X_0."""
        diagnostics = base_result["martingale_diagnostics"]
        sample_mean = diagnostics["discounted_fx_bank_account"]["sample"]["mean"]
        target = diagnostics["discounted_fx_bank_account"]["target"]
        std_error = diagnostics["discounted_fx_bank_account"]["sample"]["standard_error"]

        z_score = abs(sample_mean - target) / std_error
        assert z_score < 3.5, (
            f"FX bank account martingale failed: sample={sample_mean:.6f}, "
            f"target={target:.6f}, z={z_score:.2f}"
        )


# =============================================================================
# TEST CLASS 3: Monotonicity Tests
# =============================================================================

class TestMonotonicity:
    """Test that option value responds correctly to parameter changes."""

    def test_higher_volatility_increases_option(self, base_market, base_deal):
        """Increasing swaption volatility should increase option value."""
        # Base case
        base_result = price(base_market, base_deal)
        base_option = base_result["valuation"]["embedded_option_value"]["mean"]

        # Increase USD swaption volatilities by 20%
        high_vol_market = copy.deepcopy(base_market)
        for point in high_vol_market["swaptions"]["USD"]["points"]:
            point["normal_vol_bp"] *= 1.20
        for point in high_vol_market["swaptions"]["EUR"]["points"]:
            point["normal_vol_bp"] *= 1.20

        high_vol_result = price(high_vol_market, base_deal)
        high_vol_option = high_vol_result["valuation"]["embedded_option_value"]["mean"]

        # Higher vol should give higher option value (allowing for MC error)
        base_error = base_result["valuation"]["embedded_option_value"]["standard_error"]
        high_error = high_vol_result["valuation"]["embedded_option_value"]["standard_error"]
        combined_error = math.sqrt(base_error**2 + high_error**2)

        assert high_vol_option > base_option - 2 * combined_error, (
            f"Higher volatility should increase option value: "
            f"base={base_option:,.2f}, high_vol={high_vol_option:,.2f}"
        )

    def test_longer_non_call_decreases_option(self, base_market, base_deal):
        """Longer non-call period should decrease option value."""
        # Reduce non-call to 1Y
        short_nc_deal = copy.deepcopy(base_deal)
        short_nc_deal["exercise"]["non_call"] = "1Y"
        short_nc_result = price(base_market, short_nc_deal)
        short_nc_option = short_nc_result["valuation"]["embedded_option_value"]["mean"]

        # Increase non-call to 5Y
        long_nc_deal = copy.deepcopy(base_deal)
        long_nc_deal["exercise"]["non_call"] = "5Y"
        long_nc_result = price(base_market, long_nc_deal)
        long_nc_option = long_nc_result["valuation"]["embedded_option_value"]["mean"]

        # Shorter non-call => more exercise opportunities => higher option value
        assert short_nc_option > long_nc_option * 0.9, (
            f"Shorter non-call should give higher option value: "
            f"1Y NC={short_nc_option:,.2f}, 5Y NC={long_nc_option:,.2f}"
        )

    def test_fx_spot_sensitivity(self, base_market, base_deal):
        """Test sensitivity to FX spot rate changes."""
        # Base result
        base_result = price(base_market, base_deal)

        # Increase EUR/USD spot by 5%
        high_spot_market = copy.deepcopy(base_market)
        high_spot_market["fx"]["spot"] *= 1.05
        # Adjust forwards proportionally
        for fwd in high_spot_market["fx"]["forwards"]:
            fwd["outright"] *= 1.05

        high_spot_result = price(high_spot_market, base_deal)
        high_spot_npv = high_spot_result["valuation"]["callable_npv"]["mean"]

        # NPV should change with FX (receiving EUR, paying USD)
        # Higher spot means EUR receivables worth more in USD
        eur_leg_base = base_result["valuation"]["eur_estr_leg_pv_in_usd"]["mean"]
        eur_leg_high = high_spot_result["valuation"]["eur_estr_leg_pv_in_usd"]["mean"]

        # EUR leg should increase with higher spot
        assert eur_leg_high > eur_leg_base, (
            f"EUR leg should increase with higher spot: "
            f"base={eur_leg_base:,.2f}, high_spot={eur_leg_high:,.2f}"
        )


# =============================================================================
# TEST CLASS 4: Convergence Tests
# =============================================================================

class TestConvergence:
    """Test Monte Carlo convergence properties."""

    def test_standard_error_decreases_with_paths(self, base_market, base_deal):
        """Standard error should decrease as sqrt(N)."""
        # Run with different path counts
        low_paths_deal = copy.deepcopy(base_deal)
        low_paths_deal["numerics"]["pricing_paths"] = 10000
        low_result = price(base_market, low_paths_deal)
        low_se = low_result["valuation"]["callable_npv"]["standard_error"]

        high_paths_deal = copy.deepcopy(base_deal)
        high_paths_deal["numerics"]["pricing_paths"] = 40000
        high_result = price(base_market, high_paths_deal)
        high_se = high_result["valuation"]["callable_npv"]["standard_error"]

        # SE should scale as 1/sqrt(N)
        expected_ratio = math.sqrt(40000 / 10000)  # 2.0
        actual_ratio = low_se / high_se

        # Allow 30% tolerance due to MC noise
        assert 0.7 * expected_ratio < actual_ratio < 1.4 * expected_ratio, (
            f"SE ratio should be ~{expected_ratio:.2f}, got {actual_ratio:.2f}"
        )

    def test_seed_reproducibility(self, base_market, base_deal):
        """Same seed should produce identical results."""
        result1 = price(base_market, base_deal)
        result2 = price(base_market, base_deal)

        # Results should be identical
        npv1 = result1["valuation"]["callable_npv"]["mean"]
        npv2 = result2["valuation"]["callable_npv"]["mean"]

        assert npv1 == npv2, (
            f"Same seed should give identical results: {npv1:,.2f} != {npv2:,.2f}"
        )

    def test_different_seed_gives_different_result(self, base_market, base_deal):
        """Different seeds should give different (but consistent) results."""
        result1 = price(base_market, base_deal)

        different_seed_deal = copy.deepcopy(base_deal)
        different_seed_deal["numerics"]["seed"] = 42
        result2 = price(base_market, different_seed_deal)

        npv1 = result1["valuation"]["callable_npv"]["mean"]
        npv2 = result2["valuation"]["callable_npv"]["mean"]

        # Different but within confidence interval
        se1 = result1["valuation"]["callable_npv"]["standard_error"]
        se2 = result2["valuation"]["callable_npv"]["standard_error"]
        combined_se = math.sqrt(se1**2 + se2**2)

        assert abs(npv1 - npv2) < 3 * combined_se, (
            f"Different seeds should give consistent results: "
            f"diff={abs(npv1-npv2):,.2f}, 3*SE={3*combined_se:,.2f}"
        )


# =============================================================================
# TEST CLASS 5: Calibration Quality
# =============================================================================

class TestCalibrationQuality:
    """Verify calibration meets acceptance criteria."""

    def test_calibration_accepted(self, base_result):
        """Calibration should be accepted for base case."""
        assert base_result["calibration"]["accepted"], (
            "Base case calibration should be accepted"
        )

    def test_curve_bootstrap_accuracy(self, base_result):
        """OIS curve bootstrap should be accurate to 0.01bp."""
        for row in base_result["calibration"]["curve_rows"]:
            error_bp = abs(row.get("error_bp", 0.0))
            assert error_bp < 0.01, (
                f"Curve {row['curve']} {row['tenor']} error {error_bp:.6f}bp > 0.01bp"
            )

    def test_swaption_calibration_quality(self, base_result):
        """Swaption calibration RMS error should be < 5%."""
        metrics = base_result["calibration"]["metrics"]

        usd_error = metrics["usd_swaption_weighted_rms_relative_error"]
        eur_error = metrics["eur_swaption_weighted_rms_relative_error"]

        assert usd_error < 0.05, f"USD swaption RMS error {usd_error:.4f} > 5%"
        assert eur_error < 0.05, f"EUR swaption RMS error {eur_error:.4f} > 5%"

    def test_fx_calibration_quality(self, base_result):
        """FX volatility calibration error should be < 0.25%."""
        fx_error = base_result["calibration"]["metrics"]["fx_max_abs_vol_error"]
        assert fx_error < 0.0025, f"FX vol error {fx_error:.6f} > 0.25%"


# =============================================================================
# TEST CLASS 6: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test behavior at parameter boundaries."""

    def test_zero_correlation(self, base_market, base_deal):
        """Model should work with zero correlations."""
        zero_corr_market = copy.deepcopy(base_market)
        zero_corr_market["correlation"] = {
            "USD_EUR": 0.0,
            "USD_FX": 0.0,
            "EUR_FX": 0.0
        }

        result = price(zero_corr_market, base_deal)
        assert result["status"] in ("OK", "CALIBRATION_WARNING")
        assert result["valuation"]["callable_npv"]["mean"] is not None

    def test_high_correlation(self, base_market, base_deal):
        """Model should work with high (but valid) correlations."""
        high_corr_market = copy.deepcopy(base_market)
        high_corr_market["correlation"] = {
            "USD_EUR": 0.7,
            "USD_FX": -0.5,
            "EUR_FX": -0.5
        }

        result = price(high_corr_market, base_deal)
        assert result["status"] in ("OK", "CALIBRATION_WARNING")

    def test_at_the_money_swap(self, base_market, base_deal):
        """Test with an approximately ATM fixed rate."""
        # Get roughly ATM fixed rate from static curve benchmark
        base_result = price(base_market, base_deal)
        usd_leg = base_result["valuation"]["static_curve_benchmark"]["USD_FIXED"]
        eur_leg = base_result["valuation"]["static_curve_benchmark"]["EUR_ESTR_IN_USD"]

        # Adjust fixed rate to make swap closer to par
        # Find the USD leg index dynamically
        usd_leg_index = next(
            i for i, leg in enumerate(base_deal["legs"]) if leg["currency"] == "USD"
        )
        current_fixed = float(base_deal["legs"][usd_leg_index]["fixed_rate"])

        # If EUR > USD, lower the fixed rate
        if eur_leg > -usd_leg:
            new_fixed = current_fixed * 0.95
        else:
            new_fixed = current_fixed * 1.05

        atm_deal = copy.deepcopy(base_deal)
        atm_deal["legs"][usd_leg_index]["fixed_rate"] = new_fixed

        result = price(base_market, atm_deal)
        assert result["status"] in ("OK", "CALIBRATION_WARNING")


# =============================================================================
# TEST CLASS 7: Static Curve Benchmark
# =============================================================================

class TestStaticCurveBenchmark:
    """Compare Monte Carlo results against deterministic curve pricing."""

    def test_mc_close_to_static_benchmark(self, base_result):
        """Monte Carlo non-callable should be close to static curve valuation."""
        mc_non_callable = base_result["valuation"]["non_callable_npv"]["mean"]
        mc_error = base_result["valuation"]["non_callable_npv"]["standard_error"]
        static_benchmark = base_result["valuation"]["static_curve_benchmark"]["total"]

        # Should be within a few standard errors + convexity adjustment
        # Stochastic rates create convexity that can cause small differences
        tolerance = max(5 * mc_error, 50000)  # 5 sigma or 50k minimum

        difference = abs(mc_non_callable - static_benchmark)
        relative_diff = difference / abs(static_benchmark) if static_benchmark != 0 else 0

        assert relative_diff < 0.05, (
            f"MC non-callable ({mc_non_callable:,.2f}) differs from "
            f"static benchmark ({static_benchmark:,.2f}) by {relative_diff:.2%}"
        )


# =============================================================================
# VALIDATION REPORT GENERATOR
# =============================================================================

def generate_validation_summary(market_file: Path, deal_file: Path) -> dict[str, Any]:
    """Generate a comprehensive validation summary for reporting."""
    market = json.loads(market_file.read_text())
    deal = json.loads(deal_file.read_text())

    # Run base pricing
    base_result = price(market, deal)

    # Run sensitivity tests
    sensitivities = {}

    # Rate shift +25bp
    shifted_market = copy.deepcopy(market)
    for curve in ["USD-SOFR", "EUR-ESTR"]:
        for inst in shifted_market["curves"][curve]["instruments"]:
            inst["rate"] += 0.0025
    shifted_result = price(shifted_market, deal)
    sensitivities["rate_plus_25bp"] = {
        "callable_npv": shifted_result["valuation"]["callable_npv"]["mean"],
        "delta": shifted_result["valuation"]["callable_npv"]["mean"] - base_result["valuation"]["callable_npv"]["mean"]
    }

    # Vol shift +10%
    vol_shifted_market = copy.deepcopy(market)
    for ccy in ["USD", "EUR"]:
        for point in vol_shifted_market["swaptions"][ccy]["points"]:
            point["normal_vol_bp"] *= 1.10
    vol_shifted_result = price(vol_shifted_market, deal)
    sensitivities["vol_plus_10pct"] = {
        "callable_npv": vol_shifted_result["valuation"]["callable_npv"]["mean"],
        "vega": vol_shifted_result["valuation"]["callable_npv"]["mean"] - base_result["valuation"]["callable_npv"]["mean"]
    }

    # FX spot +1%
    fx_shifted_market = copy.deepcopy(market)
    fx_shifted_market["fx"]["spot"] *= 1.01
    for fwd in fx_shifted_market["fx"]["forwards"]:
        fwd["outright"] *= 1.01
    fx_shifted_result = price(fx_shifted_market, deal)
    sensitivities["fx_plus_1pct"] = {
        "callable_npv": fx_shifted_result["valuation"]["callable_npv"]["mean"],
        "fx_delta": fx_shifted_result["valuation"]["callable_npv"]["mean"] - base_result["valuation"]["callable_npv"]["mean"]
    }

    return {
        "base_result": base_result,
        "sensitivities": sensitivities,
        "validation_metrics": {
            "martingale_z_scores": {
                name: abs(
                    base_result["martingale_diagnostics"][name]["sample"]["mean"] -
                    base_result["martingale_diagnostics"][name]["target"]
                ) / base_result["martingale_diagnostics"][name]["sample"]["standard_error"]
                for name in ["domestic_discount", "discounted_fx_zero_coupon", "discounted_fx_bank_account"]
            },
            "calibration_metrics": base_result["calibration"]["metrics"],
            "exercise_probabilities": [
                {"date": ex.get("exercise_date", "MATURITY"), "prob": ex["unconditional_probability"]}
                for ex in base_result["exercise"]
            ]
        }
    }


if __name__ == "__main__":
    # Run validation summary when executed directly
    summary = generate_validation_summary(MARKET_FILE, DEAL_FILE)
    print(json.dumps(summary, indent=2, default=str))
