"""Rudimentary bump-and-revalue diagnostics for the callable XCCY pricer.

These controls are deliberately small and transparent.  They use common random
numbers, full recalibration after every market bump, and central differences.
They are useful regression controls, not a replacement for independent model
validation or a production risk engine.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Callable

from standalone_xccy_pricer import PricingError, price


def _callable_mean(result: dict[str, Any]) -> float:
    return float(result["valuation"]["callable_npv"]["mean"])


def _callable_standard_error(result: dict[str, Any]) -> float:
    return float(result["valuation"]["callable_npv"]["standard_error"])


def _valuation(
    market: dict[str, Any],
    deal: dict[str, Any],
    training_paths: int,
    pricing_paths: int,
    seed: int,
) -> dict[str, Any]:
    return price(
        market,
        deal,
        {
            "training_paths": int(training_paths),
            "pricing_paths": int(pricing_paths),
            "chunk_size": min(int(pricing_paths), 10_000),
            "seed": int(seed),
        },
    )


def _bump_fx_spot(market: dict[str, Any], relative_bump: float) -> dict[str, Any]:
    bumped = copy.deepcopy(market)
    multiplier = 1.0 + float(relative_bump)
    if multiplier <= 0.0:
        raise PricingError("FX spot bump would create a non-positive spot.")
    bumped["fx"]["spot"] = float(bumped["fx"]["spot"]) * multiplier
    # Scale outright forwards with spot so F/S, and therefore the effective
    # foreign discount curve, is held fixed for a pure spot sensitivity.
    for point in bumped["fx"]["forwards"]:
        point["outright"] = float(point["outright"]) * multiplier
    return bumped


def _bump_ois_curve(market: dict[str, Any], curve_name: str, bump_bp: float) -> dict[str, Any]:
    bumped = copy.deepcopy(market)
    shift = float(bump_bp) * 1.0e-4
    try:
        instruments = bumped["curves"][curve_name]["instruments"]
    except KeyError as exc:
        raise PricingError(f"Cannot bump missing curve {curve_name}.") from exc
    for instrument in instruments:
        instrument["rate"] = float(instrument["rate"]) + shift
    return bumped


def _central_measure(
    market: dict[str, Any],
    deal: dict[str, Any],
    bump: float,
    unit: float,
    bump_market: Callable[[dict[str, Any], float], dict[str, Any]],
    training_paths: int,
    pricing_paths: int,
    seed: int,
) -> dict[str, float]:
    up = _valuation(bump_market(market, bump), deal, training_paths, pricing_paths, seed)
    down = _valuation(bump_market(market, -bump), deal, training_paths, pricing_paths, seed)
    up_npv = _callable_mean(up)
    down_npv = _callable_mean(down)
    normalized = (up_npv - down_npv) * unit / (2.0 * bump)
    return {"up_npv": up_npv, "down_npv": down_npv, "value": normalized}


def _stability(full: float, half: float, tolerance: float = 0.20) -> dict[str, Any]:
    denominator = max(abs(full), abs(half), 1.0)
    relative_difference = abs(full - half) / denominator
    return {
        "full_bump_value": full,
        "half_bump_value": half,
        "relative_difference": relative_difference,
        "tolerance": tolerance,
        "passed": relative_difference <= tolerance,
    }


def bump_revaluation_diagnostics(
    market: dict[str, Any],
    deal: dict[str, Any],
    training_paths: int,
    pricing_paths: int,
    seed: int,
) -> dict[str, Any]:
    """Calculate three central-difference Greeks and half-bump stability.

    FX delta is reported as USD value change for a 1% proportional spot move.
    Curve PV01s are USD value changes for a parallel one-basis-point move.  All
    repricings recalibrate the model and reuse identical random seeds.
    """

    if min(training_paths, pricing_paths) < 128:
        raise PricingError("Greek diagnostics require at least 128 training and pricing paths.")

    definitions: tuple[
        tuple[str, float, float, float, Callable[[dict[str, Any], float], dict[str, Any]], str], ...
    ] = (
        ("fx_delta_usd_per_1pct", 0.01, 0.005, 0.01, _bump_fx_spot, "USD per 1% EURUSD spot move"),
        (
            "usd_parallel_dv01",
            1.0,
            0.5,
            1.0,
            lambda value, bump: _bump_ois_curve(value, "USD-SOFR", bump),
            "USD per 1 bp parallel USD-SOFR move",
        ),
        (
            "eur_parallel_dv01",
            1.0,
            0.5,
            1.0,
            lambda value, bump: _bump_ois_curve(value, "EUR-ESTR", bump),
            "USD per 1 bp parallel EUR-ESTR forecast-curve move",
        ),
    )
    rows: dict[str, Any] = {}
    for name, full_bump, half_bump, unit, bump_function, units in definitions:
        full = _central_measure(
            market,
            deal,
            full_bump,
            unit,
            bump_function,
            training_paths,
            pricing_paths,
            seed,
        )
        half = _central_measure(
            market,
            deal,
            half_bump,
            unit,
            bump_function,
            training_paths,
            pricing_paths,
            seed,
        )
        rows[name] = {
            "value": full["value"],
            "units": units,
            "full_bump": full_bump,
            "half_bump": half_bump,
            "full_bump_up_npv": full["up_npv"],
            "full_bump_down_npv": full["down_npv"],
            "stability": _stability(full["value"], half["value"]),
        }
    return {
        "method": "CENTRAL_BUMP_REVALUE_FULL_RECALIBRATION_COMMON_RANDOM_NUMBERS",
        "training_paths": int(training_paths),
        "pricing_paths": int(pricing_paths),
        "seed": int(seed),
        "all_stability_checks_passed": all(row["stability"]["passed"] for row in rows.values()),
        "greeks": rows,
        "limitations": [
            "Only parallel USD/EUR OIS shifts and proportional EURUSD spot delta are covered.",
            "The EUR PV01 is a forecast-curve sensitivity; cross-currency-basis PV01 is not included.",
            "No gamma, vega, correlation risk, bucketed risk, or adjoint differentiation is provided.",
        ],
    }


def path_convergence_diagnostics(
    market: dict[str, Any],
    deal: dict[str, Any],
    base_result: dict[str, Any],
    training_paths: int,
    pricing_paths: int,
    seed: int,
) -> dict[str, Any]:
    """Compare the requested valuation with a half-sized independent sample."""

    if training_paths < 256 or pricing_paths < 512:
        raise PricingError(
            "Convergence diagnostics require at least 256 training and 512 pricing paths "
            "so the half-sized comparison is meaningful."
        )
    low_training = max(128, training_paths // 2)
    low_pricing = max(256, pricing_paths // 2)
    low_seed = seed + 7_919
    low_result = _valuation(market, deal, low_training, low_pricing, low_seed)
    high_mean = _callable_mean(base_result)
    low_mean = _callable_mean(low_result)
    high_se = _callable_standard_error(base_result)
    low_se = _callable_standard_error(low_result)
    combined_se = math.sqrt(high_se * high_se + low_se * low_se)
    difference = high_mean - low_mean
    z_score: float | None = 0.0 if combined_se == 0.0 and difference == 0.0 else (
        None if combined_se == 0.0 else difference / combined_se
    )
    tolerance_z = 4.0
    return {
        "method": "INDEPENDENT_HALF_VERSUS_REQUESTED_PATH_COUNT",
        "low": {
            "training_paths": low_training,
            "pricing_paths": low_pricing,
            "seed": low_seed,
            "callable_npv": low_mean,
            "standard_error": low_se,
        },
        "high": {
            "training_paths": int(training_paths),
            "pricing_paths": int(pricing_paths),
            "seed": int(seed),
            "callable_npv": high_mean,
            "standard_error": high_se,
        },
        "difference_usd": difference,
        "combined_standard_error": combined_se,
        "z_score": z_score,
        "absolute_z_tolerance": tolerance_z,
        "passed": z_score is not None and math.isfinite(z_score) and abs(z_score) <= tolerance_z,
        "limitation": "This is a rudimentary path-count check, not a grid, basis, seed-ensemble, or dual-bound study.",
    }
