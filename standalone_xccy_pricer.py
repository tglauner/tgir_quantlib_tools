"""Standalone callable EUR/USD cross-currency swap reference pricer.

The model has one Hull-White factor for USD, one Hull-White factor for EUR,
and a lognormal EURUSD FX factor under the USD money-market measure.  The
joint Gaussian state is evolved with exact Ornstein-Uhlenbeck kernels and
Gauss-Legendre covariance integration.  Bermudan cancellation is valued by
two-sample Longstaff-Schwartz regression.

This module is intentionally independent from the Flask application.  Run:

    ./.venv/bin/python standalone_xccy_pricer.py \
        --market data/xccy_market_eurusd.json \
        --deal data/xccy_deal_10y_nc2.json \
        --output result.json
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import QuantLib as ql


MARKET_SCHEMA = "xccy-market/1.0"
DEAL_SCHEMA = "callable-xccy-deal/1.0"
RESULT_SCHEMA = "callable-xccy-result/1.0"
MODEL_ID = "HW1F_USD_HW1F_EUR_BSFX_LSM_V1"
DAY_COUNTER = ql.Actual365Fixed()
GAUSS_NODES, GAUSS_WEIGHTS = np.polynomial.legendre.leggauss(16)


class PricingError(ValueError):
    """Raised for an invalid input or a failed numerical prerequisite."""


@dataclass(frozen=True)
class RateModel:
    currency: str
    mean_reversion: float
    volatility: float
    calibration_rows: tuple[dict[str, Any], ...]
    weighted_rms_relative_error: float

    def sigma(self, _time: float) -> float:
        return self.volatility


@dataclass(frozen=True)
class FxModel:
    bucket_ends: np.ndarray
    volatilities: np.ndarray
    calibration_rows: tuple[dict[str, Any], ...]
    max_abs_vol_error: float

    def sigma(self, time_value: float) -> float:
        index = int(np.searchsorted(self.bucket_ends, time_value, side="right"))
        return float(self.volatilities[min(index, len(self.volatilities) - 1)])


@dataclass(frozen=True)
class CurveBundle:
    usd_discount: Any
    eur_forecast: Any
    eur_effective: Any
    curve_rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CashflowPlan:
    as_of: Any
    effective_date: Any
    maturity_date: Any
    call_dates: tuple[Any, ...]
    call_times: np.ndarray
    cashflows: tuple[dict[str, Any], ...]
    schedule_summary: dict[str, Any]


@dataclass(frozen=True)
class StepTransition:
    matrix: np.ndarray
    offset: np.ndarray
    covariance_root: np.ndarray


@dataclass(frozen=True)
class SimulationContext:
    curves: CurveBundle
    usd_model: RateModel
    eur_model: RateModel
    fx_model: FxModel
    correlation: np.ndarray
    spot: float
    plan: CashflowPlan
    grid: np.ndarray
    transitions: tuple[StepTransition, ...]
    capture_times: tuple[float, ...]
    exercise_tolerance: float


@dataclass
class SimulationBatch:
    pre_call_pv: np.ndarray
    interval_pv: np.ndarray
    call_states: np.ndarray
    call_discounts: np.ndarray
    usd_leg_pv: np.ndarray
    eur_leg_pv: np.ndarray
    domestic_discount: np.ndarray
    discounted_fx: np.ndarray
    discounted_fx_bank_account: np.ndarray

    @property
    def non_callable_pv(self) -> np.ndarray:
        if self.interval_pv.size == 0:
            return self.pre_call_pv.copy()
        return self.pre_call_pv + np.sum(self.interval_pv, axis=0)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PricingError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PricingError(f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise PricingError(f"Top-level JSON value in {path} must be an object.")
    return value


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PricingError(f"{field} must be an object.")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise PricingError(f"{field} must be a non-empty array.")
    return value


def _reject_unknown(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value).difference(allowed))
    if unknown:
        raise PricingError(f"{field} contains unsupported field(s): {', '.join(unknown)}.")


def _positive_number(value: Any, field: str, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise PricingError(f"{field} must be a finite number.")
    result = float(value)
    if result < 0.0 or (result == 0.0 and not allow_zero):
        comparator = "non-negative" if allow_zero else "positive"
        raise PricingError(f"{field} must be {comparator}.")
    return result


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise PricingError(f"{field} must be a finite number.")
    return float(value)


def _parse_date(value: Any, field: str) -> Any:
    if not isinstance(value, str):
        raise PricingError(f"{field} must be an ISO-8601 date string.")
    try:
        result = ql.DateParser.parseISO(value)
    except RuntimeError as exc:
        raise PricingError(f"{field} is not a valid ISO-8601 date: {value}") from exc
    if result == ql.Date():
        raise PricingError(f"{field} is not a valid date: {value}")
    return result


def _period(value: Any, field: str) -> Any:
    if not isinstance(value, str):
        raise PricingError(f"{field} must be a QuantLib period string such as 3M or 10Y.")
    try:
        result = ql.Period(value)
    except RuntimeError as exc:
        raise PricingError(f"{field} is not a valid period: {value}") from exc
    if result.length() <= 0:
        raise PricingError(f"{field} must be positive.")
    return result


def _time(as_of: Any, date_value: Any) -> float:
    return max(0.0, float(DAY_COUNTER.yearFraction(as_of, date_value)))


def _time_key(value: float) -> float:
    return round(float(value), 12)


def _correlation_matrix(market: dict[str, Any]) -> np.ndarray:
    corr = _require_object(market.get("correlation"), "market.correlation")
    _reject_unknown(corr, {"USD_EUR", "USD_FX", "EUR_FX"}, "market.correlation")
    values = []
    for field in ("USD_EUR", "USD_FX", "EUR_FX"):
        value = corr.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PricingError(f"market.correlation.{field} must be numeric.")
        value = float(value)
        if not -1.0 <= value <= 1.0:
            raise PricingError(f"market.correlation.{field} must be in [-1, 1].")
        values.append(value)
    rho_df, rho_ds, rho_fs = values
    matrix = np.array(
        [[1.0, rho_df, rho_ds], [rho_df, 1.0, rho_fs], [rho_ds, rho_fs, 1.0]],
        dtype=float,
    )
    minimum_eigenvalue = float(np.linalg.eigvalsh(matrix)[0])
    if minimum_eigenvalue < -1.0e-10:
        raise PricingError(
            "market.correlation is not positive semidefinite; "
            f"minimum eigenvalue is {minimum_eigenvalue:.6g}."
        )
    return matrix


def validate_inputs(market: dict[str, Any], deal: dict[str, Any]) -> None:
    _reject_unknown(
        market,
        {
            "schema",
            "as_of",
            "source",
            "fx",
            "curves",
            "rate_models",
            "swaptions",
            "fx_options",
            "correlation",
            "calibration_limits",
        },
        "market",
    )
    _reject_unknown(
        deal,
        {
            "schema",
            "trade_id",
            "effective_date",
            "maturity",
            "reporting_currency",
            "collateral_currency",
            "notionals",
            "legs",
            "notional_exchanges",
            "exercise",
            "numerics",
        },
        "deal",
    )
    if market.get("schema") != MARKET_SCHEMA:
        raise PricingError(f"market.schema must equal {MARKET_SCHEMA!r}.")
    if deal.get("schema") != DEAL_SCHEMA:
        raise PricingError(f"deal.schema must equal {DEAL_SCHEMA!r}.")
    _parse_date(market.get("as_of"), "market.as_of")

    fx = _require_object(market.get("fx"), "market.fx")
    _reject_unknown(fx, {"pair", "quote", "spot", "forwards"}, "market.fx")
    if fx.get("pair") != "EURUSD" or fx.get("quote") != "USD_PER_EUR":
        raise PricingError("Version 1 requires fx.pair=EURUSD and fx.quote=USD_PER_EUR.")
    _positive_number(fx.get("spot"), "market.fx.spot")
    forwards = _require_list(fx.get("forwards"), "market.fx.forwards")
    for index, point in enumerate(forwards):
        point = _require_object(point, f"market.fx.forwards[{index}]")
        _reject_unknown(point, {"tenor", "outright"}, f"market.fx.forwards[{index}]")
        _period(point.get("tenor"), f"market.fx.forwards[{index}].tenor")
        _positive_number(point.get("outright"), f"market.fx.forwards[{index}].outright")

    curves = _require_object(market.get("curves"), "market.curves")
    for name in ("USD-SOFR", "EUR-ESTR"):
        spec = _require_object(curves.get(name), f"market.curves.{name}")
        _reject_unknown(spec, {"settlement_days", "instruments"}, f"market.curves.{name}")
        instruments = _require_list(spec.get("instruments"), f"market.curves.{name}.instruments")
        for index, point in enumerate(instruments):
            point = _require_object(point, f"market.curves.{name}.instruments[{index}]")
            _reject_unknown(point, {"type", "tenor", "rate"}, f"market.curves.{name}.instruments[{index}]")
            if point.get("type") != "OIS":
                raise PricingError(f"market.curves.{name}.instruments[{index}].type must be OIS.")
            _period(point.get("tenor"), f"market.curves.{name}.instruments[{index}].tenor")
            _finite_number(point.get("rate"), f"market.curves.{name}.instruments[{index}].rate")

    swaptions = _require_object(market.get("swaptions"), "market.swaptions")
    rate_models = _require_object(market.get("rate_models"), "market.rate_models")
    for currency in ("USD", "EUR"):
        model = _require_object(rate_models.get(currency), f"market.rate_models.{currency}")
        _reject_unknown(model, {"mean_reversion", "initial_sigma"}, f"market.rate_models.{currency}")
        _positive_number(model.get("mean_reversion"), f"market.rate_models.{currency}.mean_reversion")
        _positive_number(model.get("initial_sigma", 0.01), f"market.rate_models.{currency}.initial_sigma")
        surface = _require_object(swaptions.get(currency), f"market.swaptions.{currency}")
        _reject_unknown(surface, {"type", "points"}, f"market.swaptions.{currency}")
        if surface.get("type") != "NORMAL":
            raise PricingError(f"market.swaptions.{currency}.type must be NORMAL.")
        for index, point in enumerate(_require_list(surface.get("points"), f"market.swaptions.{currency}.points")):
            point = _require_object(point, f"market.swaptions.{currency}.points[{index}]")
            _reject_unknown(
                point,
                {"expiry", "tenor", "normal_vol_bp"},
                f"market.swaptions.{currency}.points[{index}]",
            )
            _period(point.get("expiry"), f"market.swaptions.{currency}.points[{index}].expiry")
            _period(point.get("tenor"), f"market.swaptions.{currency}.points[{index}].tenor")
            _positive_number(point.get("normal_vol_bp"), f"market.swaptions.{currency}.points[{index}].normal_vol_bp")

    fx_options = _require_object(market.get("fx_options"), "market.fx_options")
    _reject_unknown(fx_options, {"type", "points"}, "market.fx_options")
    if fx_options.get("type") != "BLACK_ATM":
        raise PricingError("market.fx_options.type must be BLACK_ATM.")
    for index, point in enumerate(_require_list(fx_options.get("points"), "market.fx_options.points")):
        point = _require_object(point, f"market.fx_options.points[{index}]")
        _reject_unknown(point, {"tenor", "black_vol"}, f"market.fx_options.points[{index}]")
        _period(point.get("tenor"), f"market.fx_options.points[{index}].tenor")
        vol = _positive_number(point.get("black_vol"), f"market.fx_options.points[{index}].black_vol")
        if vol >= 3.0:
            raise PricingError("FX Black volatilities are decimals and must be less than 3.0.")
    _correlation_matrix(market)

    if deal.get("reporting_currency") != "USD" or deal.get("collateral_currency") != "USD":
        raise PricingError("Version 1 requires USD reporting and collateral currency.")
    if not isinstance(deal.get("trade_id"), str) or not deal["trade_id"].strip():
        raise PricingError("deal.trade_id must be a non-empty string.")
    as_of = _parse_date(market.get("as_of"), "market.as_of")
    effective = _parse_date(deal.get("effective_date"), "deal.effective_date")
    if effective < as_of:
        raise PricingError("deal.effective_date before market.as_of is not supported in version 1.")
    _period(deal.get("maturity"), "deal.maturity")
    notionals = _require_object(deal.get("notionals"), "deal.notionals")
    _reject_unknown(notionals, {"USD", "EUR"}, "deal.notionals")
    _positive_number(notionals.get("USD"), "deal.notionals.USD")
    _positive_number(notionals.get("EUR"), "deal.notionals.EUR")
    legs = _require_list(deal.get("legs"), "deal.legs")
    if len(legs) != 2:
        raise PricingError("deal.legs must contain exactly one EUR floating leg and one USD fixed leg.")
    by_currency = {str(item.get("currency")): item for item in legs if isinstance(item, dict)}
    if set(by_currency) != {"USD", "EUR"}:
        raise PricingError("deal.legs must contain currencies USD and EUR exactly once.")
    if by_currency["EUR"].get("index") != "ESTR":
        raise PricingError("The EUR leg index must be ESTR.")
    _finite_number(by_currency["USD"].get("fixed_rate"), "USD fixed_rate")
    _finite_number(by_currency["EUR"].get("spread", 0.0), "EUR spread")
    for currency, leg in by_currency.items():
        allowed_leg_fields = {
            "currency",
            "side",
            "frequency",
            "day_count",
            "payment_lag_days",
            "index",
            "spread",
            "fixed_rate",
        }
        _reject_unknown(leg, allowed_leg_fields, f"{currency} leg")
        if leg.get("side") not in {"PAY", "RECEIVE"}:
            raise PricingError(f"{currency} leg side must be PAY or RECEIVE.")
        _period(leg.get("frequency"), f"{currency} leg frequency")
        if leg.get("day_count") not in {"ACT/360", "ACT/365F", "30/360"}:
            raise PricingError(f"Unsupported {currency} leg day_count.")
        lag = leg.get("payment_lag_days", 0)
        if not isinstance(lag, int) or isinstance(lag, bool) or lag < 0:
            raise PricingError(f"{currency} leg payment_lag_days must be a non-negative integer.")
    exercise = _require_object(deal.get("exercise"), "deal.exercise")
    _reject_unknown(
        exercise,
        {"style", "holder", "non_call", "frequency", "settlement_amount", "event_order"},
        "deal.exercise",
    )
    if exercise.get("style") != "CANCEL_REMAINING_SWAP":
        raise PricingError("Version 1 supports CANCEL_REMAINING_SWAP only.")
    if exercise.get("event_order") != "PAY_DUE_THEN_CANCEL":
        raise PricingError("Version 1 requires exercise.event_order=PAY_DUE_THEN_CANCEL.")
    _period(exercise.get("non_call"), "deal.exercise.non_call")
    _period(exercise.get("frequency"), "deal.exercise.frequency")
    _positive_number(exercise.get("settlement_amount", 0.0), "exercise.settlement_amount", True)
    if float(exercise.get("settlement_amount", 0.0)) != 0.0:
        raise PricingError("Version 1 supports zero-fee cancellation only.")
    if not isinstance(exercise.get("holder"), str) or not exercise["holder"].strip():
        raise PricingError("deal.exercise.holder must be a non-empty string.")
    exchanges = _require_object(deal.get("notional_exchanges"), "deal.notional_exchanges")
    _reject_unknown(exchanges, {"initial", "final"}, "deal.notional_exchanges")
    if not all(isinstance(exchanges.get(field), bool) for field in ("initial", "final")):
        raise PricingError("deal.notional_exchanges.initial and final must be booleans.")
    numerics = _require_object(deal.get("numerics", {}), "deal.numerics")
    _reject_unknown(
        numerics,
        {"training_paths", "pricing_paths", "chunk_size", "seed", "max_step_years", "exercise_tolerance"},
        "deal.numerics",
    )
    for field in ("training_paths", "pricing_paths", "chunk_size"):
        value = numerics.get(field)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value <= 0):
            raise PricingError(f"deal.numerics.{field} must be a positive integer.")
    seed = numerics.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool) or seed < 0):
        raise PricingError("deal.numerics.seed must be a non-negative integer.")
    if "max_step_years" in numerics:
        _positive_number(numerics["max_step_years"], "deal.numerics.max_step_years")
    tolerance = numerics.get("exercise_tolerance", 0.0)
    _positive_number(tolerance, "deal.numerics.exercise_tolerance", True)
    limits = _require_object(market.get("calibration_limits", {}), "market.calibration_limits")
    _reject_unknown(
        limits,
        {"ois_error_bp", "swaption_weighted_rms_relative_error", "fx_abs_vol_error"},
        "market.calibration_limits",
    )
    for field, default in (
        ("ois_error_bp", 0.01),
        ("swaption_weighted_rms_relative_error", 0.10),
        ("fx_abs_vol_error", 0.0025),
    ):
        _positive_number(limits.get(field, default), f"market.calibration_limits.{field}", True)


def _day_count(name: str) -> Any:
    if name == "ACT/360":
        return ql.Actual360()
    if name == "ACT/365F":
        return ql.Actual365Fixed()
    if name == "30/360":
        return ql.Thirty360(ql.Thirty360.BondBasis)
    raise PricingError(f"Unsupported day count: {name}")


def _build_ois_curve(as_of: Any, specification: dict[str, Any], currency: str) -> tuple[Any, list[dict[str, Any]]]:
    if currency == "USD":
        index = ql.Sofr()
        settlement_days = int(specification.get("settlement_days", 2))
    else:
        index = ql.Estr()
        settlement_days = int(specification.get("settlement_days", 2))
    helpers: list[Any] = []
    source_quotes: list[tuple[str, float]] = []
    for point in specification["instruments"]:
        rate = float(point["rate"])
        helper = ql.OISRateHelper(
            settlement_days,
            ql.Period(point["tenor"]),
            ql.QuoteHandle(ql.SimpleQuote(rate)),
            index,
        )
        helpers.append(helper)
        source_quotes.append((point["tenor"], rate))
    try:
        curve = ql.PiecewiseLogLinearDiscount(as_of, helpers, DAY_COUNTER)
        curve.enableExtrapolation()
        _ = curve.discount(curve.maxDate())
    except RuntimeError as exc:
        raise PricingError(f"Failed to bootstrap {currency} OIS curve: {exc}") from exc
    rows = []
    for helper, (tenor, quote) in zip(helpers, source_quotes):
        implied = float(helper.impliedQuote())
        rows.append(
            {
                "curve": f"{currency}-OIS",
                "tenor": tenor,
                "market_rate": quote,
                "model_rate": implied,
                "error_bp": (implied - quote) * 10_000.0,
            }
        )
    return curve, rows


def build_curves(market: dict[str, Any]) -> CurveBundle:
    as_of = _parse_date(market["as_of"], "market.as_of")
    ql.Settings.instance().evaluationDate = as_of
    usd_curve, usd_rows = _build_ois_curve(as_of, market["curves"]["USD-SOFR"], "USD")
    eur_curve, eur_rows = _build_ois_curve(as_of, market["curves"]["EUR-ESTR"], "EUR")
    usd_curve.enableExtrapolation()
    eur_curve.enableExtrapolation()

    spot = float(market["fx"]["spot"])
    calendar = ql.JointCalendar(ql.TARGET(), ql.UnitedStates(ql.UnitedStates.Settlement), ql.JoinHolidays)
    dates = [as_of]
    discounts = [1.0]
    previous_date = as_of
    for point in market["fx"]["forwards"]:
        date_value = calendar.advance(as_of, ql.Period(point["tenor"]), ql.ModifiedFollowing)
        if date_value <= previous_date:
            raise PricingError("market.fx.forwards tenors must be strictly increasing.")
        effective_discount = usd_curve.discount(date_value) * float(point["outright"]) / spot
        if not math.isfinite(effective_discount) or effective_discount <= 0.0:
            raise PricingError(f"Derived EUR effective discount factor is invalid at {point['tenor']}.")
        dates.append(date_value)
        discounts.append(effective_discount)
        previous_date = date_value
    try:
        eur_effective = ql.DiscountCurve(dates, discounts, DAY_COUNTER, calendar)
        eur_effective.enableExtrapolation()
    except RuntimeError as exc:
        raise PricingError(f"Failed to construct USD-collateralized EUR effective curve: {exc}") from exc

    forward_rows = []
    for point, date_value, discount in zip(market["fx"]["forwards"], dates[1:], discounts[1:]):
        model_forward = spot * discount / usd_curve.discount(date_value)
        forward_rows.append(
            {
                "curve": "EUR-EFFECTIVE-USD-COLLATERAL",
                "tenor": point["tenor"],
                "market_forward": float(point["outright"]),
                "model_forward": model_forward,
                "relative_error": model_forward / float(point["outright"]) - 1.0,
            }
        )
    return CurveBundle(usd_curve, eur_curve, eur_effective, tuple(usd_rows + eur_rows + forward_rows))


def _helper_vector(helpers: Iterable[Any]) -> Any:
    result = ql.CalibrationHelperVector()
    for helper in helpers:
        result.push_back(helper)
    return result


def calibrate_rate_model(
    currency: str,
    curve: Any,
    surface: dict[str, Any],
    configuration: dict[str, Any],
) -> RateModel:
    curve_handle = ql.YieldTermStructureHandle(curve)
    index = ql.Sofr(curve_handle) if currency == "USD" else ql.Estr(curve_handle)
    helpers = []
    labels = []
    for point in surface["points"]:
        helper = ql.SwaptionHelper(
            ql.Period(point["expiry"]),
            ql.Period(point["tenor"]),
            ql.QuoteHandle(ql.SimpleQuote(float(point["normal_vol_bp"]) * 1.0e-4)),
            index,
            ql.Period("1Y"),
            ql.Actual360(),
            ql.Actual360(),
            curve_handle,
            ql.BlackCalibrationHelper.RelativePriceError,
            ql.nullDouble(),
            1.0,
            ql.Normal,
            0.0,
            2,
            ql.RateAveraging.Compound,
        )
        helpers.append(helper)
        labels.append(f"{point['expiry']}x{point['tenor']}")
    mean_reversion = _positive_number(
        configuration.get("mean_reversion"), f"market.rate_models.{currency}.mean_reversion"
    )
    initial_sigma = _positive_number(
        configuration.get("initial_sigma", 0.01), f"market.rate_models.{currency}.initial_sigma"
    )
    model = ql.HullWhite(curve_handle, mean_reversion, initial_sigma)
    engine = ql.JamshidianSwaptionEngine(model)
    for helper in helpers:
        helper.setPricingEngine(engine)
    try:
        model.calibrate(
            _helper_vector(helpers),
            ql.LevenbergMarquardt(),
            ql.EndCriteria(500, 100, 1.0e-10, 1.0e-10, 1.0e-10),
            ql.PositiveConstraint(),
            ql.DoubleVector(),
            ql.BoolVector([True, False]),
        )
    except RuntimeError as exc:
        raise PricingError(f"{currency} Hull-White calibration failed: {exc}") from exc
    sigma = float(model.params()[1])
    rows = []
    squared_errors = []
    for label, helper in zip(labels, helpers):
        market_value = float(helper.marketValue())
        model_value = float(helper.modelValue())
        relative_error = 0.0 if abs(market_value) < 1.0e-14 else model_value / market_value - 1.0
        squared_errors.append(relative_error * relative_error)
        rows.append(
            {
                "currency": currency,
                "instrument": label,
                "market_value": market_value,
                "model_value": model_value,
                "relative_price_error": relative_error,
            }
        )
    rms = math.sqrt(sum(squared_errors) / len(squared_errors))
    return RateModel(currency, mean_reversion, sigma, tuple(rows), rms)


def _b_value(mean_reversion: float, time_value: np.ndarray | float) -> np.ndarray | float:
    if abs(mean_reversion) < 1.0e-10:
        return time_value
    return -np.expm1(-mean_reversion * np.asarray(time_value)) / mean_reversion


def _state_transition_matrix(h: float, usd_model: RateModel, eur_model: RateModel) -> np.ndarray:
    ad = usd_model.mean_reversion
    af = eur_model.mean_reversion
    ed = math.exp(-ad * h)
    ef = math.exp(-af * h)
    bd = float(_b_value(ad, h))
    bf = float(_b_value(af, h))
    matrix = np.eye(5)
    matrix[0, :] = [ed, 0.0, 0.0, 0.0, 0.0]
    matrix[1, :] = [0.0, ef, 0.0, 0.0, 0.0]
    matrix[2, :] = [bd, 0.0, 1.0, 0.0, 0.0]
    matrix[3, :] = [0.0, bf, 0.0, 1.0, 0.0]
    matrix[4, :] = [bd, -bf, 0.0, 0.0, 1.0]
    return matrix


def _step_covariance(
    h: float,
    usd_model: RateModel,
    eur_model: RateModel,
    fx_sigma: float,
    correlation: np.ndarray,
) -> np.ndarray:
    ad = usd_model.mean_reversion
    af = eur_model.mean_reversion
    sd = usd_model.volatility
    sf = eur_model.volatility
    covariance = np.zeros((5, 5), dtype=float)
    for node, weight in zip(GAUSS_NODES, GAUSS_WEIGHTS):
        v = 0.5 * h * (float(node) + 1.0)
        kernel = np.zeros((5, 3), dtype=float)
        kernel[0, 0] = sd * math.exp(-ad * v)
        kernel[1, 1] = sf * math.exp(-af * v)
        kernel[2, 0] = sd * float(_b_value(ad, v))
        kernel[3, 1] = sf * float(_b_value(af, v))
        kernel[4, 0] = kernel[2, 0]
        kernel[4, 1] = -kernel[3, 1]
        kernel[4, 2] = fx_sigma
        covariance += 0.5 * h * float(weight) * (kernel @ correlation @ kernel.T)
    return 0.5 * (covariance + covariance.T)


def _covariance_root(covariance: np.ndarray) -> np.ndarray:
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    scale = max(float(np.max(np.abs(eigenvalues))), 1.0)
    if float(eigenvalues[0]) < -1.0e-11 * scale:
        raise PricingError(f"Transition covariance is not positive semidefinite: {eigenvalues[0]:.6g}")
    eigenvalues = np.maximum(eigenvalues, 0.0)
    return eigenvectors @ np.diag(np.sqrt(eigenvalues))


def _variance_log_fx(
    maturity: float,
    usd_model: RateModel,
    eur_model: RateModel,
    bucket_ends: np.ndarray,
    volatilities: np.ndarray,
    correlation: np.ndarray,
) -> float:
    boundaries = [0.0]
    boundaries.extend(float(x) for x in bucket_ends if 0.0 < x < maturity)
    boundaries.append(float(maturity))
    covariance = np.zeros((5, 5), dtype=float)
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        h = end - start
        mid = 0.5 * (start + end)
        index = int(np.searchsorted(bucket_ends, mid, side="right"))
        fx_sigma = float(volatilities[min(index, len(volatilities) - 1)])
        matrix = _state_transition_matrix(h, usd_model, eur_model)
        step_covariance = _step_covariance(h, usd_model, eur_model, fx_sigma, correlation)
        covariance = matrix @ covariance @ matrix.T + step_covariance
    return max(float(covariance[4, 4]), 0.0)


def _bounded_minimize(function: Any, lower: float, upper: float, iterations: int = 80) -> tuple[float, float]:
    ratio = 0.5 * (math.sqrt(5.0) - 1.0)
    left, right = float(lower), float(upper)
    x1 = right - ratio * (right - left)
    x2 = left + ratio * (right - left)
    f1, f2 = float(function(x1)), float(function(x2))
    for _ in range(iterations):
        if f1 <= f2:
            right, x2, f2 = x2, x1, f1
            x1 = right - ratio * (right - left)
            f1 = float(function(x1))
        else:
            left, x1, f1 = x1, x2, f2
            x2 = left + ratio * (right - left)
            f2 = float(function(x2))
    return (x1, f1) if f1 <= f2 else (x2, f2)


def calibrate_fx_model(
    market: dict[str, Any],
    usd_model: RateModel,
    eur_model: RateModel,
    correlation: np.ndarray,
) -> FxModel:
    as_of = _parse_date(market["as_of"], "market.as_of")
    calendar = ql.JointCalendar(ql.TARGET(), ql.UnitedStates(ql.UnitedStates.Settlement), ql.JoinHolidays)
    points = []
    for point in market["fx_options"]["points"]:
        expiry_date = calendar.advance(as_of, ql.Period(point["tenor"]), ql.ModifiedFollowing)
        points.append((_time(as_of, expiry_date), point))
    points.sort(key=lambda item: item[0])
    if any(points[index][0] <= points[index - 1][0] for index in range(1, len(points))):
        raise PricingError("FX option tenors must be strictly increasing.")
    bucket_ends = np.array([item[0] for item in points], dtype=float)
    calibrated: list[float] = []
    rows: list[dict[str, Any]] = []
    for index, (maturity, point) in enumerate(points):
        target_vol = float(point["black_vol"])
        target_variance = target_vol * target_vol * maturity

        def objective(candidate: float) -> float:
            values = np.array(calibrated + [candidate], dtype=float)
            ends = bucket_ends[: index + 1]
            variance = _variance_log_fx(maturity, usd_model, eur_model, ends, values, correlation)
            scale = max(target_variance, 1.0e-10)
            return ((variance - target_variance) / scale) ** 2

        sigma, _ = _bounded_minimize(objective, 1.0e-5, 2.0)
        calibrated.append(sigma)
        model_variance = _variance_log_fx(
            maturity,
            usd_model,
            eur_model,
            bucket_ends[: index + 1],
            np.array(calibrated),
            correlation,
        )
        model_vol = math.sqrt(model_variance / maturity)
        rows.append(
            {
                "instrument": f"EURUSD-ATM-{point['tenor']}",
                "market_black_vol": target_vol,
                "model_black_vol": model_vol,
                "vol_error": model_vol - target_vol,
                "diffusion_sigma": sigma,
            }
        )
    max_error = max(abs(row["vol_error"]) for row in rows)
    return FxModel(bucket_ends, np.array(calibrated, dtype=float), tuple(rows), max_error)


def _calendar() -> Any:
    return ql.JointCalendar(ql.TARGET(), ql.UnitedStates(ql.UnitedStates.Settlement), ql.JoinHolidays)


def _side_sign(value: str) -> float:
    return 1.0 if value == "RECEIVE" else -1.0


def _schedule(start: Any, end: Any, frequency: str) -> list[Any]:
    return list(
        ql.Schedule(
            start,
            end,
            ql.Period(frequency),
            _calendar(),
            ql.ModifiedFollowing,
            ql.ModifiedFollowing,
            ql.DateGeneration.Backward,
            False,
        )
    )


def build_cashflow_plan(market: dict[str, Any], deal: dict[str, Any]) -> CashflowPlan:
    as_of = _parse_date(market["as_of"], "market.as_of")
    effective = _parse_date(deal["effective_date"], "deal.effective_date")
    maturity_unadjusted = effective + ql.Period(deal["maturity"])
    maturity = _calendar().adjust(maturity_unadjusted, ql.ModifiedFollowing)
    legs = {leg["currency"]: leg for leg in deal["legs"]}
    usd_schedule = _schedule(effective, maturity, legs["USD"]["frequency"])
    eur_schedule = _schedule(effective, maturity, legs["EUR"]["frequency"])

    exercise = deal["exercise"]
    call_dates = []
    unadjusted_candidate = effective + ql.Period(exercise["non_call"])
    while unadjusted_candidate < maturity_unadjusted:
        candidate = _calendar().adjust(unadjusted_candidate, ql.ModifiedFollowing)
        if candidate < maturity and (not call_dates or candidate > call_dates[-1]):
            call_dates.append(candidate)
        unadjusted_candidate = unadjusted_candidate + ql.Period(exercise["frequency"])
    if not call_dates:
        raise PricingError("The exercise schedule contains no dates before maturity.")
    call_times = np.array([_time(as_of, value) for value in call_dates], dtype=float)

    cashflows: list[dict[str, Any]] = []
    usd_sign = _side_sign(legs["USD"]["side"])
    eur_sign = _side_sign(legs["EUR"]["side"])
    usd_notional = float(deal["notionals"]["USD"])
    eur_notional = float(deal["notionals"]["EUR"])
    usd_day_count = _day_count(legs["USD"]["day_count"])
    eur_day_count = _day_count(legs["EUR"]["day_count"])

    for start, end in zip(usd_schedule[:-1], usd_schedule[1:]):
        pay_date = _calendar().advance(end, int(legs["USD"].get("payment_lag_days", 0)), ql.Days)
        amount = usd_sign * usd_notional * float(legs["USD"]["fixed_rate"]) * usd_day_count.yearFraction(start, end)
        cashflows.append(
            {
                "kind": "FIXED",
                "leg": "USD_FIXED",
                "currency": "USD",
                "amount": amount,
                "pay_time": _time(as_of, pay_date),
                "entitlement_time": _time(as_of, end),
            }
        )
    for start, end in zip(eur_schedule[:-1], eur_schedule[1:]):
        pay_date = _calendar().advance(end, int(legs["EUR"].get("payment_lag_days", 0)), ql.Days)
        cashflows.append(
            {
                "kind": "FLOATING",
                "leg": "EUR_ESTR",
                "currency": "EUR",
                "sign": eur_sign,
                "notional": eur_notional,
                "spread": float(legs["EUR"].get("spread", 0.0)),
                "accrual": eur_day_count.yearFraction(start, end),
                "start_time": _time(as_of, start),
                "end_time": _time(as_of, end),
                "pay_time": _time(as_of, pay_date),
                "entitlement_time": _time(as_of, end),
            }
        )

    exchanges = _require_object(deal.get("notional_exchanges", {}), "deal.notional_exchanges")
    for leg, sign, notional, currency in (
        ("USD_FIXED", usd_sign, usd_notional, "USD"),
        ("EUR_ESTR", eur_sign, eur_notional, "EUR"),
    ):
        if bool(exchanges.get("initial", False)):
            cashflows.append(
                {
                    "kind": "EXCHANGE",
                    "leg": leg,
                    "currency": currency,
                    "amount": -sign * notional,
                    "pay_time": _time(as_of, effective),
                    "entitlement_time": _time(as_of, effective),
                }
            )
        if bool(exchanges.get("final", False)):
            cashflows.append(
                {
                    "kind": "EXCHANGE",
                    "leg": leg,
                    "currency": currency,
                    "amount": sign * notional,
                    "pay_time": _time(as_of, maturity),
                    "entitlement_time": _time(as_of, maturity),
                }
            )
    cashflows.sort(key=lambda item: (item["pay_time"], item["currency"], item["kind"]))
    return CashflowPlan(
        as_of=as_of,
        effective_date=effective,
        maturity_date=maturity,
        call_dates=tuple(call_dates),
        call_times=call_times,
        cashflows=tuple(cashflows),
        schedule_summary={
            "effective_date": effective.ISO(),
            "maturity_date": maturity.ISO(),
            "usd_fixed_payment_dates": [date_value.ISO() for date_value in usd_schedule[1:]],
            "eur_estr_payment_dates": [date_value.ISO() for date_value in eur_schedule[1:]],
            "exercise_dates": [date_value.ISO() for date_value in call_dates],
        },
    )


def _rate_integral_variance(time_value: float, model: RateModel) -> float:
    if time_value <= 0.0:
        return 0.0
    a = model.mean_reversion
    sigma = model.volatility
    if abs(a) < 1.0e-8:
        return sigma * sigma * time_value**3 / 3.0
    return (sigma * sigma / (a * a)) * (
        time_value
        - 2.0 * (1.0 - math.exp(-a * time_value)) / a
        + (1.0 - math.exp(-2.0 * a * time_value)) / (2.0 * a)
    )


def _phi_integral(curve: Any, model: RateModel, start: float, end: float) -> float:
    if end <= start:
        return 0.0
    discount_ratio = float(curve.discount(end)) / float(curve.discount(start))
    return -math.log(discount_ratio) + 0.5 * (
        _rate_integral_variance(end, model) - _rate_integral_variance(start, model)
    )


def _build_grid(plan: CashflowPlan, fx_model: FxModel, max_step: float) -> tuple[np.ndarray, tuple[float, ...]]:
    capture = {0.0, _time(plan.as_of, plan.maturity_date)}
    capture.update(float(value) for value in plan.call_times)
    for cashflow in plan.cashflows:
        capture.add(float(cashflow["pay_time"]))
        capture.add(float(cashflow["entitlement_time"]))
        if cashflow["kind"] == "FLOATING":
            capture.add(float(cashflow["start_time"]))
            capture.add(float(cashflow["end_time"]))
    boundaries = set(capture)
    boundaries.update(float(value) for value in fx_model.bucket_ends)
    ordered = sorted(boundaries)
    grid = [ordered[0]]
    for start, end in zip(ordered[:-1], ordered[1:]):
        steps = max(1, int(math.ceil((end - start) / max_step)))
        grid.extend(float(value) for value in np.linspace(start, end, steps + 1)[1:])
    return np.array(sorted(set(_time_key(value) for value in grid)), dtype=float), tuple(
        sorted(_time_key(value) for value in capture)
    )


def build_simulation_context(
    market: dict[str, Any],
    deal: dict[str, Any],
    curves: CurveBundle,
    usd_model: RateModel,
    eur_model: RateModel,
    fx_model: FxModel,
    correlation: np.ndarray,
    plan: CashflowPlan,
) -> SimulationContext:
    numerics = _require_object(deal.get("numerics", {}), "deal.numerics")
    max_step = _positive_number(numerics.get("max_step_years", 1.0 / 12.0), "numerics.max_step_years")
    grid, capture_times = _build_grid(plan, fx_model, max_step)
    rho_fs = float(correlation[1, 2])
    transitions: list[StepTransition] = []
    for start, end in zip(grid[:-1], grid[1:]):
        h = float(end - start)
        mid = 0.5 * float(start + end)
        sigma_fx = fx_model.sigma(mid)
        matrix = _state_transition_matrix(h, usd_model, eur_model)
        covariance = _step_covariance(h, usd_model, eur_model, sigma_fx, correlation)
        root = _covariance_root(covariance)
        af = eur_model.mean_reversion
        bf = float(_b_value(af, h))
        quanto = rho_fs * eur_model.volatility * sigma_fx
        foreign_forcing_integral = -quanto * (h - bf) / af if abs(af) > 1.0e-10 else -0.5 * quanto * h * h
        phi_d = _phi_integral(curves.usd_discount, usd_model, float(start), float(end))
        phi_f = _phi_integral(curves.eur_effective, eur_model, float(start), float(end))
        offset = np.zeros(5, dtype=float)
        offset[1] = -quanto * bf
        offset[2] = phi_d
        offset[3] = phi_f + foreign_forcing_integral
        offset[4] = phi_d - phi_f - foreign_forcing_integral - 0.5 * sigma_fx * sigma_fx * h
        transitions.append(StepTransition(matrix, offset, root))
    return SimulationContext(
        curves=curves,
        usd_model=usd_model,
        eur_model=eur_model,
        fx_model=fx_model,
        correlation=correlation,
        spot=float(market["fx"]["spot"]),
        plan=plan,
        grid=grid,
        transitions=tuple(transitions),
        capture_times=capture_times,
        exercise_tolerance=float(numerics.get("exercise_tolerance", 0.0)),
    )


def _antithetic_normals(generator: np.random.Generator, paths: int, dimensions: int) -> np.ndarray:
    half = (paths + 1) // 2
    draws = generator.standard_normal((half, dimensions))
    return np.concatenate((draws, -draws), axis=0)[:paths]


def _curve_basis_integral(curves: CurveBundle, start: float, end: float) -> float:
    forecast_log_factor = math.log(curves.eur_forecast.discount(start) / curves.eur_forecast.discount(end))
    effective_log_factor = math.log(curves.eur_effective.discount(start) / curves.eur_effective.discount(end))
    return forecast_log_factor - effective_log_factor


def simulate_batch(context: SimulationContext, paths: int, seed: int) -> SimulationBatch:
    if paths <= 0:
        raise PricingError("Path count must be positive.")
    generator = np.random.Generator(np.random.PCG64(seed))
    state = np.zeros((paths, 5), dtype=float)
    state[:, 4] = math.log(context.spot)
    capture_set = set(context.capture_times)
    captured: dict[float, np.ndarray] = {}
    if 0.0 in capture_set:
        captured[0.0] = state.copy()
    for index, transition in enumerate(context.transitions):
        normals = _antithetic_normals(generator, paths, 5)
        state = state @ transition.matrix.T + transition.offset + normals @ transition.covariance_root.T
        time_value = _time_key(context.grid[index + 1])
        if time_value in capture_set:
            captured[time_value] = state.copy()
    missing = capture_set.difference(captured)
    if missing:
        raise PricingError(f"Simulation failed to capture event times: {sorted(missing)[:5]}")

    call_count = len(context.plan.call_times)
    pre_call = np.zeros(paths, dtype=float)
    interval = np.zeros((call_count, paths), dtype=float)
    usd_leg = np.zeros(paths, dtype=float)
    eur_leg = np.zeros(paths, dtype=float)
    call_states = np.empty((call_count, paths, 3), dtype=float)
    call_discounts = np.empty((call_count, paths), dtype=float)
    for index, call_time in enumerate(context.plan.call_times):
        values = captured[_time_key(call_time)]
        call_states[index, :, 0] = values[:, 0]
        call_states[index, :, 1] = values[:, 1]
        call_states[index, :, 2] = values[:, 4] - math.log(context.spot)
        call_discounts[index] = np.exp(-values[:, 2])

    for cashflow in context.plan.cashflows:
        pay_state = captured[_time_key(cashflow["pay_time"])]
        discount = np.exp(-pay_state[:, 2])
        if cashflow["kind"] == "FLOATING":
            start_state = captured[_time_key(cashflow["start_time"])]
            end_state = captured[_time_key(cashflow["end_time"])]
            basis = _curve_basis_integral(
                context.curves, float(cashflow["start_time"]), float(cashflow["end_time"])
            )
            accumulated = end_state[:, 3] - start_state[:, 3] + basis
            if not np.all(np.isfinite(accumulated)) or float(np.max(np.abs(accumulated))) > 50.0:
                raise PricingError("EUR overnight accumulation became numerically unstable.")
            amount = float(cashflow["sign"]) * float(cashflow["notional"]) * (
                np.exp(accumulated) - 1.0 + float(cashflow["spread"]) * float(cashflow["accrual"])
            )
        else:
            amount = float(cashflow["amount"])
        if cashflow["currency"] == "EUR":
            path_pv = discount * np.exp(pay_state[:, 4]) * amount
            eur_leg += path_pv
        else:
            path_pv = discount * amount
            usd_leg += path_pv
        bucket = bisect.bisect_left(context.plan.call_times.tolist(), float(cashflow["entitlement_time"])) - 1
        if bucket < 0:
            pre_call += path_pv
        else:
            interval[min(bucket, call_count - 1)] += path_pv

    maturity_time = _time_key(_time(context.plan.as_of, context.plan.maturity_date))
    terminal = captured[maturity_time]
    domestic_discount = np.exp(-terminal[:, 2])
    discounted_fx = np.exp(-terminal[:, 2] + terminal[:, 4])
    discounted_fx_bank_account = np.exp(-terminal[:, 2] + terminal[:, 4] + terminal[:, 3])
    return SimulationBatch(
        pre_call,
        interval,
        call_states,
        call_discounts,
        usd_leg,
        eur_leg,
        domestic_discount,
        discounted_fx,
        discounted_fx_bank_account,
    )


def _combine_batches(batches: list[SimulationBatch]) -> SimulationBatch:
    if not batches:
        raise PricingError("No simulation batches were supplied.")
    return SimulationBatch(
        pre_call_pv=np.concatenate([batch.pre_call_pv for batch in batches]),
        interval_pv=np.concatenate([batch.interval_pv for batch in batches], axis=1),
        call_states=np.concatenate([batch.call_states for batch in batches], axis=1),
        call_discounts=np.concatenate([batch.call_discounts for batch in batches], axis=1),
        usd_leg_pv=np.concatenate([batch.usd_leg_pv for batch in batches]),
        eur_leg_pv=np.concatenate([batch.eur_leg_pv for batch in batches]),
        domestic_discount=np.concatenate([batch.domestic_discount for batch in batches]),
        discounted_fx=np.concatenate([batch.discounted_fx for batch in batches]),
        discounted_fx_bank_account=np.concatenate([batch.discounted_fx_bank_account for batch in batches]),
    )


def _simulate_in_chunks(context: SimulationContext, paths: int, seed: int, chunk_size: int) -> SimulationBatch:
    sequence = np.random.SeedSequence(seed)
    chunk_counts = []
    remaining = paths
    while remaining > 0:
        current = min(chunk_size, remaining)
        chunk_counts.append(current)
        remaining -= current
    child_sequences = sequence.spawn(len(chunk_counts))
    batches = []
    for count, child in zip(chunk_counts, child_sequences):
        child_seed = int(child.generate_state(1, dtype=np.uint64)[0])
        batches.append(simulate_batch(context, count, child_seed))
    return _combine_batches(batches)


def _basis(states: np.ndarray, mean: np.ndarray, scale: np.ndarray) -> np.ndarray:
    values = (states - mean) / scale
    x, y, z = values[:, 0], values[:, 1], values[:, 2]
    return np.column_stack((np.ones(len(states)), x, y, z, x * x, y * y, z * z, x * y, x * z, y * z))


def train_lsm(batch: SimulationBatch, exercise_tolerance: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    call_count = batch.interval_pv.shape[0]
    later_value = np.zeros_like(batch.pre_call_pv)
    policies: list[dict[str, Any] | None] = [None] * call_count
    diagnostics: list[dict[str, Any] | None] = [None] * call_count
    for index in range(call_count - 1, -1, -1):
        continuation_zero = batch.interval_pv[index] + later_value
        continuation_at_call = continuation_zero / batch.call_discounts[index]
        states = batch.call_states[index]
        mean = np.mean(states, axis=0)
        scale = np.std(states, axis=0, ddof=1)
        scale = np.where(scale < 1.0e-12, 1.0, scale)
        design = _basis(states, mean, scale)
        condition_number = float(np.linalg.cond(design))
        ridge = 0.0
        if condition_number <= 1.0e10:
            coefficients, _, rank, _ = np.linalg.lstsq(design, continuation_at_call, rcond=1.0e-12)
            rank_value = int(rank)
        else:
            ridge = 1.0e-8
            gram = design.T @ design
            penalty = np.eye(gram.shape[0]) * ridge
            penalty[0, 0] = 0.0
            coefficients = np.linalg.solve(gram + penalty, design.T @ continuation_at_call)
            rank_value = int(np.linalg.matrix_rank(design))
        fitted = design @ coefficients
        residuals = continuation_at_call - fitted
        exercise = fitted < -exercise_tolerance
        later_value = np.where(exercise, 0.0, continuation_zero)
        policies[index] = {
            "mean": mean,
            "scale": scale,
            "coefficients": coefficients,
        }
        diagnostics[index] = {
            "call_index": index,
            "training_paths": int(len(states)),
            "rank": rank_value,
            "basis_size": int(design.shape[1]),
            "condition_number": condition_number,
            "ridge": ridge,
            "residual_rms": float(math.sqrt(np.mean(residuals * residuals))),
            "backward_exercise_fraction": float(np.mean(exercise)),
        }
    return [item for item in policies if item is not None], [item for item in diagnostics if item is not None]


def apply_lsm_policy(
    batch: SimulationBatch,
    policies: list[dict[str, Any]],
    exercise_tolerance: float,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    value = batch.pre_call_pv.copy()
    alive = np.ones(len(value), dtype=bool)
    exercise_rows = []
    for index, policy in enumerate(policies):
        design = _basis(batch.call_states[index], policy["mean"], policy["scale"])
        continuation = design @ policy["coefficients"]
        exercised = alive & (continuation < -exercise_tolerance)
        alive_before = int(np.sum(alive))
        exercise_count = int(np.sum(exercised))
        exercise_rows.append(
            {
                "call_index": index,
                "alive_paths": alive_before,
                "exercise_paths": exercise_count,
                "unconditional_probability": exercise_count / len(value),
                "conditional_probability": 0.0 if alive_before == 0 else exercise_count / alive_before,
            }
        )
        continuing = alive & ~exercised
        value[continuing] += batch.interval_pv[index, continuing]
        alive = continuing
    exercise_rows.append(
        {
            "call_index": None,
            "alive_paths": int(np.sum(alive)),
            "exercise_paths": 0,
            "unconditional_probability": float(np.mean(alive)),
            "conditional_probability": None,
            "label": "NO_EXERCISE",
        }
    )
    return value, exercise_rows


def _summary(values: np.ndarray) -> dict[str, float]:
    count = len(values)
    mean = float(np.mean(values))
    standard_deviation = float(np.std(values, ddof=1)) if count > 1 else 0.0
    standard_error = standard_deviation / math.sqrt(count) if count > 0 else float("nan")
    return {
        "mean": mean,
        "standard_deviation": standard_deviation,
        "standard_error": standard_error,
        "confidence_95_low": mean - 1.959963984540054 * standard_error,
        "confidence_95_high": mean + 1.959963984540054 * standard_error,
    }


def _static_curve_pv(context: SimulationContext) -> dict[str, float]:
    usd = 0.0
    eur = 0.0
    for cashflow in context.plan.cashflows:
        if cashflow["kind"] == "FLOATING":
            factor = (
                context.curves.eur_forecast.discount(cashflow["start_time"])
                / context.curves.eur_forecast.discount(cashflow["end_time"])
                - 1.0
                + float(cashflow["spread"]) * float(cashflow["accrual"])
            )
            amount = float(cashflow["sign"]) * float(cashflow["notional"]) * factor
        else:
            amount = float(cashflow["amount"])
        if cashflow["currency"] == "EUR":
            eur += context.spot * context.curves.eur_effective.discount(cashflow["pay_time"]) * amount
        else:
            usd += context.curves.usd_discount.discount(cashflow["pay_time"]) * amount
    return {"USD_FIXED": usd, "EUR_ESTR_IN_USD": eur, "total": usd + eur}


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_ready(item) for item in value.tolist()]
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _normalized_hash(market: dict[str, Any], deal: dict[str, Any]) -> str:
    payload = json.dumps({"market": market, "deal": deal}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def price(market: dict[str, Any], deal: dict[str, Any], overrides: dict[str, int] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    validate_inputs(market, deal)
    as_of = _parse_date(market["as_of"], "market.as_of")
    ql.Settings.instance().evaluationDate = as_of
    curves = build_curves(market)
    configurations = _require_object(market.get("rate_models"), "market.rate_models")
    usd_model = calibrate_rate_model("USD", curves.usd_discount, market["swaptions"]["USD"], configurations["USD"])
    eur_model = calibrate_rate_model("EUR", curves.eur_forecast, market["swaptions"]["EUR"], configurations["EUR"])
    correlation = _correlation_matrix(market)
    fx_model = calibrate_fx_model(market, usd_model, eur_model, correlation)
    plan = build_cashflow_plan(market, deal)
    context = build_simulation_context(market, deal, curves, usd_model, eur_model, fx_model, correlation, plan)

    numerics = dict(deal.get("numerics", {}))
    if overrides:
        numerics.update({key: value for key, value in overrides.items() if value is not None})
    training_paths = int(numerics.get("training_paths", 10_000))
    pricing_paths = int(numerics.get("pricing_paths", 30_000))
    chunk_size = int(numerics.get("chunk_size", 20_000))
    seed = int(numerics.get("seed", 1729))
    if min(training_paths, pricing_paths, chunk_size) <= 0:
        raise PricingError("training_paths, pricing_paths, and chunk_size must be positive integers.")

    training = _simulate_in_chunks(context, training_paths, seed, chunk_size)
    policies, regression_rows = train_lsm(training, context.exercise_tolerance)
    pricing = _simulate_in_chunks(context, pricing_paths, seed + 1_000_003, chunk_size)
    callable_paths, exercise_rows = apply_lsm_policy(pricing, policies, context.exercise_tolerance)
    for index, row in enumerate(exercise_rows[:-1]):
        row["exercise_date"] = plan.call_dates[index].ISO()
    non_callable_paths = pricing.non_callable_pv
    option_paths = callable_paths - non_callable_paths
    maturity_time = _time(plan.as_of, plan.maturity_date)
    expected_domestic_discount = curves.usd_discount.discount(maturity_time)
    expected_discounted_fx = context.spot * curves.eur_effective.discount(maturity_time)

    max_curve_error = max(abs(float(row.get("error_bp", 0.0))) for row in curves.curve_rows)
    calibration_limits = market.get("calibration_limits", {})
    rate_limit = float(calibration_limits.get("swaption_weighted_rms_relative_error", 0.05))
    fx_limit = float(calibration_limits.get("fx_abs_vol_error", 0.0025))
    calibration_ok = (
        max_curve_error <= float(calibration_limits.get("ois_error_bp", 0.01))
        and usd_model.weighted_rms_relative_error <= rate_limit
        and eur_model.weighted_rms_relative_error <= rate_limit
        and fx_model.max_abs_vol_error <= fx_limit
    )
    result = {
        "schema": RESULT_SCHEMA,
        "status": "OK" if calibration_ok else "CALIBRATION_WARNING",
        "run_id": str(uuid.uuid4()),
        "trade_id": deal.get("trade_id"),
        "as_of": market["as_of"],
        "currency": "USD",
        "model": {
            "id": MODEL_ID,
            "measure": "USD_MONEY_MARKET",
            "fx_quote": "USD_PER_EUR",
            "rate_volatility_parameterization": "ONE_PIECE_CONSTANT",
            "usd_hull_white": {"a": usd_model.mean_reversion, "sigma": usd_model.volatility},
            "eur_hull_white": {"a": eur_model.mean_reversion, "sigma": eur_model.volatility},
            "fx_bucket_ends_years": fx_model.bucket_ends,
            "fx_sigmas": fx_model.volatilities,
            "correlation": correlation,
            "foreign_quanto_drift_sign": "NEGATIVE",
            "basis": "DETERMINISTIC_FORECAST_DISCOUNT",
        },
        "valuation": {
            "callable_npv": _summary(callable_paths),
            "non_callable_npv": _summary(non_callable_paths),
            "embedded_option_value": _summary(option_paths),
            "usd_fixed_leg_pv": _summary(pricing.usd_leg_pv),
            "eur_estr_leg_pv_in_usd": _summary(pricing.eur_leg_pv),
            "static_curve_benchmark": _static_curve_pv(context),
        },
        "exercise": exercise_rows,
        "calibration": {
            "accepted": calibration_ok,
            "curve_rows": curves.curve_rows,
            "usd_swaption_rows": usd_model.calibration_rows,
            "eur_swaption_rows": eur_model.calibration_rows,
            "fx_option_rows": fx_model.calibration_rows,
            "metrics": {
                "max_ois_error_bp": max_curve_error,
                "usd_swaption_weighted_rms_relative_error": usd_model.weighted_rms_relative_error,
                "eur_swaption_weighted_rms_relative_error": eur_model.weighted_rms_relative_error,
                "fx_max_abs_vol_error": fx_model.max_abs_vol_error,
            },
        },
        "martingale_diagnostics": {
            "maturity_years": maturity_time,
            "domestic_discount": {
                "sample": _summary(pricing.domestic_discount),
                "target": expected_domestic_discount,
            },
            "discounted_fx_zero_coupon": {
                "sample": _summary(pricing.discounted_fx),
                "target": expected_discounted_fx,
            },
            "discounted_fx_bank_account": {
                "sample": _summary(pricing.discounted_fx_bank_account),
                "target": context.spot,
            },
        },
        "regression": regression_rows,
        "schedule": plan.schedule_summary,
        "numerics": {
            "training_paths": training_paths,
            "pricing_paths": pricing_paths,
            "chunk_size": chunk_size,
            "seed": seed,
            "rng": "NUMPY_PCG64_ANTITHETIC",
            "time_grid_size": int(len(context.grid)),
            "max_step_years": float(numerics.get("max_step_years", 1.0 / 12.0)),
            "independent_training_and_pricing": True,
        },
        "provenance": {
            "normalized_input_sha256": _normalized_hash(market, deal),
            "quantlib_version": ql.__version__,
            "numpy_version": np.__version__,
            "python_version": sys.version.split()[0],
            "runtime_seconds": time.perf_counter() - started,
        },
        "limitations": [
            "Reference implementation; independent model validation is required before production use.",
            "Rate volatility is one-piece constant per currency in model version 1.",
            "Forecast/discount and cross-currency basis are deterministic.",
            "FX uses ATM lognormal volatility and does not fit a strike smile.",
            "EUR overnight compounding uses the continuous-time bank-account equivalent with zero lookback and lockout.",
            "The LSM estimate is a lower bound and must be convergence-tested against a dual or nested-MC benchmark.",
        ],
    }
    return _json_ready(result)


def write_result_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically persist one JSON-ready pricing result."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=False, allow_nan=False)
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", required=True, type=Path, help="Market-data JSON file")
    parser.add_argument("--deal", required=True, type=Path, help="Deal JSON file")
    parser.add_argument("--output", required=True, type=Path, help="Result JSON file")
    parser.add_argument("--training-paths", type=int, help="Override training path count")
    parser.add_argument("--pricing-paths", type=int, help="Override pricing path count")
    parser.add_argument("--chunk-size", type=int, help="Override simulation chunk size")
    parser.add_argument("--seed", type=int, help="Override base random seed")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        market = _read_json(arguments.market)
        deal = _read_json(arguments.deal)
        result = price(
            market,
            deal,
            {
                "training_paths": arguments.training_paths,
                "pricing_paths": arguments.pricing_paths,
                "chunk_size": arguments.chunk_size,
                "seed": arguments.seed,
            },
        )
        write_result_json(arguments.output, result)
    except PricingError as exc:
        print(f"Pricing failed: {exc}", file=sys.stderr)
        return 2
    print(
        f"[{result['run_id']}] {result['status']} callable NPV "
        f"{result['valuation']['callable_npv']['mean']:.2f} USD; wrote {arguments.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
