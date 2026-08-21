from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import threading
from typing import Any, Mapping

from standalone_xccy_pricer import price, write_result_json


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_XCCY_DATA_FILES = {
    "market": REPO_ROOT / "data" / "xccy_market_eurusd.json",
    "deal": REPO_ROOT / "data" / "xccy_deal_10y_nc2.json",
    "result": REPO_ROOT / "result.json",
}
XCCY_PATH_CONFIG_KEYS = {
    "market": "XCCY_MARKET_JSON_PATH",
    "deal": "XCCY_DEAL_JSON_PATH",
    "result": "XCCY_RESULT_JSON_PATH",
}
_WEB_PRICING_LOCK = threading.Lock()


class XccyPageInputError(ValueError):
    """Raised when an editable web-page pricing input is invalid."""


def xccy_data_files(config: Mapping[str, Any] | None = None) -> dict[str, Path]:
    config = config or {}
    return {
        key: Path(config.get(config_key, DEFAULT_XCCY_DATA_FILES[key])).resolve()
        for key, config_key in XCCY_PATH_CONFIG_KEYS.items()
    }


def _load_object(path: Path, *, optional: bool = False) -> dict[str, Any] | None:
    if optional and not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required XCCY page data is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"XCCY page data must contain a JSON object: {path}")
    return value


def _find_leg(deal: dict[str, Any], currency: str) -> dict[str, Any]:
    for leg in deal.get("legs", []):
        if leg.get("currency") == currency:
            return leg
    return {}


def _valuation_cards(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result:
        return []
    definitions = (
        ("callable_npv", "Callable NPV", "Holder value after optimal cancellation"),
        ("non_callable_npv", "Non-callable NPV", "Identical cash-flow stream without exercise"),
        ("embedded_option_value", "Embedded option", "Callable minus non-callable value"),
        ("usd_fixed_leg_pv", "USD fixed leg", "Pathwise PV of the 4% fixed-pay leg"),
        ("eur_estr_leg_pv_in_usd", "EUR €STR leg", "EUR receive leg converted to USD"),
    )
    cards = []
    valuation = result.get("valuation", {})
    for key, label, detail in definitions:
        value = valuation.get(key, {})
        if not isinstance(value, dict) or "mean" not in value:
            continue
        cards.append(
            {
                "key": key,
                "label": label,
                "detail": detail,
                "mean": float(value["mean"]),
                "standard_error": float(value.get("standard_error", 0.0)),
                "confidence_95_low": float(value.get("confidence_95_low", value["mean"])),
                "confidence_95_high": float(value.get("confidence_95_high", value["mean"])),
            }
        )
    return cards


def _value_bars(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not cards:
        return []
    maximum = max(abs(card["mean"]) for card in cards) or 1.0
    return [
        {
            **card,
            "width_pct": 100.0 * abs(card["mean"]) / maximum,
            "direction": "positive" if card["mean"] >= 0.0 else "negative",
        }
        for card in cards
    ]


def _exercise_rows(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result:
        return []
    rows = []
    for item in result.get("exercise", []):
        probability = float(item.get("unconditional_probability", 0.0))
        is_no_exercise = item.get("call_index") is None
        rows.append(
            {
                **item,
                "label": item.get("label", item.get("exercise_date", "Exercise")),
                "probability": probability,
                "bar_width_pct": max(0.0, min(100.0, 100.0 * probability)),
                "is_no_exercise": is_no_exercise,
            }
        )
    return rows


def _martingale_rows(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result:
        return []
    labels = {
        "domestic_discount": "USD discount bond",
        "discounted_fx_zero_coupon": "FX-converted EUR zero coupon",
        "discounted_fx_bank_account": "FX-converted EUR bank account",
    }
    rows = []
    diagnostics = result.get("martingale_diagnostics", {})
    for key, label in labels.items():
        item = diagnostics.get(key, {})
        sample = item.get("sample", {})
        if "mean" not in sample or "target" not in item:
            continue
        standard_error = float(sample.get("standard_error", 0.0))
        difference = float(sample["mean"]) - float(item["target"])
        z_score = difference / standard_error if standard_error > 0.0 else math.inf
        rows.append(
            {
                "label": label,
                "mean": float(sample["mean"]),
                "target": float(item["target"]),
                "standard_error": standard_error,
                "z_score": z_score,
                "passes": abs(z_score) <= 3.0,
            }
        )
    return rows


def _calibration_checks(
    market: dict[str, Any], result: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if not result:
        return []
    metrics = result.get("calibration", {}).get("metrics", {})
    limits = market.get("calibration_limits", {})
    definitions = (
        (
            "max_ois_error_bp",
            "ois_error_bp",
            "Maximum OIS repricing error",
            "bp",
        ),
        (
            "usd_swaption_weighted_rms_relative_error",
            "swaption_weighted_rms_relative_error",
            "USD swaption equal-weight RMS error",
            "%",
        ),
        (
            "eur_swaption_weighted_rms_relative_error",
            "swaption_weighted_rms_relative_error",
            "EUR swaption equal-weight RMS error",
            "%",
        ),
        (
            "fx_max_abs_vol_error",
            "fx_abs_vol_error",
            "FX maximum absolute vol error",
            "%",
        ),
    )
    checks = []
    for metric_key, limit_key, label, unit in definitions:
        if metric_key not in metrics or limit_key not in limits:
            continue
        value = float(metrics[metric_key])
        limit = float(limits[limit_key])
        display_scale = 100.0 if unit == "%" else 1.0
        checks.append(
            {
                "label": label,
                "value": value,
                "limit": limit,
                "display_value": value * display_scale,
                "display_limit": limit * display_scale,
                "unit": unit,
                "passes": value <= limit,
            }
        )
    return checks


def _curve_groups(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result:
        return []
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in result.get("calibration", {}).get("curve_rows", []):
        groups.setdefault(row.get("curve", "Curve"), []).append(row)
    return [{"name": name, "rows": rows} for name, rows in groups.items()]


def _correlation_matrix_from_values(values: Mapping[str, float]) -> list[list[float]]:
    rho_ue = float(values["USD_EUR"])
    rho_us = float(values["USD_FX"])
    rho_es = float(values["EUR_FX"])
    return [
        [1.0, rho_ue, rho_us],
        [rho_ue, 1.0, rho_es],
        [rho_us, rho_es, 1.0],
    ]


def correlation_determinant(values: Mapping[str, float]) -> float:
    rho_ue = float(values["USD_EUR"])
    rho_us = float(values["USD_FX"])
    rho_es = float(values["EUR_FX"])
    return 1.0 + 2.0 * rho_ue * rho_us * rho_es - rho_ue**2 - rho_us**2 - rho_es**2


def _parse_correlation_form(form: Mapping[str, Any]) -> dict[str, float]:
    if form.get("market_source") != "local_json":
        raise XccyPageInputError("The supported market source is the repository's local JSON snapshot.")
    fields = {
        "USD_EUR": "rho_usd_eur",
        "USD_FX": "rho_usd_fx",
        "EUR_FX": "rho_eur_fx",
    }
    values: dict[str, float] = {}
    for key, field in fields.items():
        raw_value = form.get(field)
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise XccyPageInputError(f"{field} must be a number between -1 and 1.") from exc
        if not math.isfinite(value) or not -1.0 <= value <= 1.0:
            raise XccyPageInputError(f"{field} must be a finite number between -1 and 1.")
        values[key] = value
    determinant = correlation_determinant(values)
    if determinant < -1.0e-10:
        raise XccyPageInputError(
            "The correlation matrix is not positive semidefinite "
            f"(determinant {determinant:.6f}); reduce the combined correlation magnitudes."
        )
    return values


def reprice_xccy_from_page(
    form: Mapping[str, Any], data_files: Mapping[str, Path]
) -> dict[str, Any]:
    """Reprice local JSON inputs with validated web-form correlation overrides."""

    correlation_values = _parse_correlation_form(form)
    market = _load_object(data_files["market"])
    deal = _load_object(data_files["deal"])
    assert market is not None
    assert deal is not None
    market_for_run = copy.deepcopy(market)
    market_for_run["correlation"] = correlation_values
    with _WEB_PRICING_LOCK:
        result = price(market_for_run, deal)
        write_result_json(data_files["result"], result)
    return result


def build_xccy_callable_context(
    data_files: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    data_files = dict(data_files or xccy_data_files())
    market = _load_object(data_files["market"])
    deal = _load_object(data_files["deal"])
    result = _load_object(data_files["result"], optional=True)
    assert market is not None
    assert deal is not None

    usd_leg = _find_leg(deal, "USD")
    eur_leg = _find_leg(deal, "EUR")
    valuation_cards = _valuation_cards(result)
    schedule = result.get("schedule", {}) if result else {}
    exercise_rows = _exercise_rows(result)
    no_exercise_probability = next(
        (row["probability"] for row in exercise_rows if row["is_no_exercise"]),
        None,
    )
    market_correlation_values = {
        key: float(market.get("correlation", {}).get(key, 0.0))
        for key in ("USD_EUR", "USD_FX", "EUR_FX")
    }
    correlation = result.get("model", {}).get("correlation") if result else None
    if correlation:
        correlation_values = {
            "USD_EUR": float(correlation[0][1]),
            "USD_FX": float(correlation[0][2]),
            "EUR_FX": float(correlation[1][2]),
        }
    else:
        correlation_values = market_correlation_values
        correlation = _correlation_matrix_from_values(correlation_values)

    return {
        "market": market,
        "deal": deal,
        "result": result,
        "result_available": result is not None,
        "usd_leg": usd_leg,
        "eur_leg": eur_leg,
        "schedule": schedule,
        "valuation_cards": valuation_cards,
        "value_bars": _value_bars(valuation_cards),
        "exercise_rows": exercise_rows,
        "no_exercise_probability": no_exercise_probability,
        "martingale_rows": _martingale_rows(result),
        "calibration_checks": _calibration_checks(market, result),
        "curve_groups": _curve_groups(result),
        "usd_swaption_rows": (
            result.get("calibration", {}).get("usd_swaption_rows", []) if result else []
        ),
        "eur_swaption_rows": (
            result.get("calibration", {}).get("eur_swaption_rows", []) if result else []
        ),
        "fx_calibration_rows": (
            result.get("calibration", {}).get("fx_option_rows", []) if result else []
        ),
        "correlation": correlation,
        "correlation_values": correlation_values,
        "market_correlation_values": market_correlation_values,
        "correlation_determinant": correlation_determinant(correlation_values),
        "factor_labels": ("USD HW", "EUR HW", "EURUSD"),
        "data_paths": {
            key: (
                str(path.relative_to(REPO_ROOT))
                if path.is_relative_to(REPO_ROOT)
                else str(path)
            )
            for key, path in data_files.items()
        },
    }
