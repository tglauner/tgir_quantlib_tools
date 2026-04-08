import copy
import csv
import json
import math
import random
import statistics
from functools import lru_cache
from io import StringIO
from pathlib import Path

import QuantLib as ql
import pandas as pd

SOFR_CURVE_POINT_SPECS = (
    ("1D", ql.Period(1, ql.Days), "deposit"),
    ("1W", ql.Period(1, ql.Weeks), "ois"),
    ("2W", ql.Period(2, ql.Weeks), "ois"),
    ("3W", ql.Period(3, ql.Weeks), "ois"),
    ("1M", ql.Period(1, ql.Months), "ois"),
    ("2M", ql.Period(2, ql.Months), "ois"),
    ("3M", ql.Period(3, ql.Months), "ois"),
    ("6M", ql.Period(6, ql.Months), "ois"),
    ("9M", ql.Period(9, ql.Months), "ois"),
    ("1Y", ql.Period(1, ql.Years), "ois"),
    ("2Y", ql.Period(2, ql.Years), "ois"),
    ("3Y", ql.Period(3, ql.Years), "ois"),
    ("4Y", ql.Period(4, ql.Years), "ois"),
    ("5Y", ql.Period(5, ql.Years), "ois"),
    ("6Y", ql.Period(6, ql.Years), "ois"),
    ("7Y", ql.Period(7, ql.Years), "ois"),
    ("8Y", ql.Period(8, ql.Years), "ois"),
    ("10Y", ql.Period(10, ql.Years), "ois"),
    ("12Y", ql.Period(12, ql.Years), "ois"),
    ("15Y", ql.Period(15, ql.Years), "ois"),
    ("20Y", ql.Period(20, ql.Years), "ois"),
    ("30Y", ql.Period(30, ql.Years), "ois"),
)
SOFR_CURVE_TENOR_LABELS = tuple(label for label, _period, _kind in SOFR_CURVE_POINT_SPECS)
SOFR_LEGACY_CURVE_TENOR_LABELS = ("1D", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "12Y")

SWAPTION_MATRIX_EXPIRY_LABELS = (
    "1M",
    "3M",
    "6M",
    "9M",
    "1Y",
    "2Y",
    "4Y",
    "5Y",
    "6Y",
    "7Y",
    "8Y",
    "9Y",
    "10Y",
    "12Y",
    "15Y",
    "20Y",
    "25Y",
)
SWAPTION_MATRIX_TENOR_LABELS = (
    "1Y",
    "2Y",
    "3Y",
    "4Y",
    "5Y",
    "6Y",
    "7Y",
    "8Y",
    "9Y",
    "10Y",
    "12Y",
    "15Y",
    "20Y",
    "25Y",
    "30Y",
)
SOFR_FORWARD_HORIZON_YEARS = 10
BERMUDAN_INITIAL_SIGMA_BP = 65.0
BERMUDAN_GSR_INTEGRATION_POINTS = 5
BERMUDAN_GSR_STDDEVS = 5.0

BERMUDAN_GRID_MATURITIES_YEARS = (2, 3, 5, 7, 10)
BERMUDAN_GRID_NONCALL_YEARS = tuple(range(1, 10))

CLIQUET_MC_PATH_COUNT = 4096
CLIQUET_MC_SEED = 17
CLIQUET_SCENARIO_SPOT_SHOCKS_PCT = (-20.0, -10.0, -5.0, 0.0, 5.0, 10.0, 20.0)
CLIQUET_SCENARIO_VOL_SHOCKS_PCT = (-5.0, -2.5, 0.0, 2.5, 5.0)
CLIQUET_MARKET_BUMP_DEFINITIONS = (
    ("SPX spot", "equity_spot", 0.01, "pct-move"),
    ("Dividend yield", "equity_dividend_yield_pct", 0.10, "pct-pts"),
    ("Flat equity vol", "equity_volatility_pct", 1.00, "pct-pts"),
)

IR_FREQUENCY_MONTH_OPTIONS = (
    (12, "Annual"),
    (6, "Semiannual"),
    (3, "Quarterly"),
    (1, "Monthly"),
)
IR_FREQUENCY_LABELS = {months: label for months, label in IR_FREQUENCY_MONTH_OPTIONS}
IR_FREQUENCY_SHORT_LABELS = {
    12: "A",
    6: "S",
    3: "Q",
    1: "M",
}

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_MARKET_DATA_JSON_PATH = REPO_ROOT / "data" / "default_market_data.json"
DEFAULT_TRADE_DATA_JSON_PATH = REPO_ROOT / "data" / "default_trades.json"

BERMUDAN_TRADE_KEYS = ("bermudan_swaption", "bermudan_swaption_2")
TRADE_SEQUENCE = ("swap", "european_swaption", "bermudan_swaption", "bermudan_swaption_2", "equity_cliquet")
TRADE_TITLES = {
    "swap": "Swap",
    "european_swaption": "European Swaption",
    "bermudan_swaption": "Bermudan Swaption",
    "bermudan_swaption_2": "Bermudan Swaption 2",
    "equity_cliquet": "Equity Cliquet",
}

CURVE_POINT_BUMP_BP = 1.0
VOL_POINT_BUMP_BP = 1.0
SENSITIVITY_ZERO_TOLERANCE = 1e-9


def _read_json_file(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _default_market_data():
    payload = _read_json_file(DEFAULT_MARKET_DATA_JSON_PATH)
    curve_payload = payload["curve_quotes_pct"]
    curve_quote_map = curve_payload.get("quotes", curve_payload)
    model_payload = payload.get("hw_mean_reversion", {})
    default_hw_mean_reversion = model_payload.get("value")
    if default_hw_mean_reversion is None:
        legacy_hw_mean_reversion = payload.get("hw_mean_reversion", 0.03)
        if isinstance(legacy_hw_mean_reversion, dict):
            default_hw_mean_reversion = legacy_hw_mean_reversion.get("value", 0.03)
        else:
            default_hw_mean_reversion = legacy_hw_mean_reversion
    matrix_payload = payload["swaption_vol_matrix_bp"]
    row_map = matrix_payload["rows"]
    equity_payload = payload.get("equity", {})
    equity_volatility = equity_payload.get("volatility", {})
    return {
        "valuation_date_iso": str(payload["valuation_date_iso"]),
        "curve_quotes_pct": [float(curve_quote_map[label]) for label in SOFR_CURVE_TENOR_LABELS],
        "hw_mean_reversion": float(default_hw_mean_reversion),
        "swaption_vol_matrix_bp": [
            [float(value) for value in row_map[expiry_label]]
            for expiry_label in SWAPTION_MATRIX_EXPIRY_LABELS
        ],
        "equity_spot": float(equity_payload.get("spot", payload.get("equity_spot", 0.0))),
        "equity_dividend_yield_pct": float(
            equity_payload.get("dividend_yield_pct", payload.get("equity_dividend_yield_pct", 0.0))
        ),
        "equity_volatility_pct": float(
            equity_volatility.get("value_pct", equity_payload.get("flat_volatility_pct", payload.get("equity_volatility_pct", 0.0)))
        ),
    }


@lru_cache(maxsize=1)
def _default_trades_data():
    payload = _read_json_file(DEFAULT_TRADE_DATA_JSON_PATH)
    return copy.deepcopy(payload)


DEFAULT_VALUATION_DATE_ISO = _default_market_data()["valuation_date_iso"]
SOFR_DEFAULT_CURVE_QUOTES_PCT = tuple(_default_market_data()["curve_quotes_pct"])
SOFR_OVERNIGHT_DEFAULT_PCT = SOFR_DEFAULT_CURVE_QUOTES_PCT[0]
DEFAULT_HW_MEAN_REVERSION = _default_market_data()["hw_mean_reversion"]
EQUITY_INDEX_DEFAULT_SPOT = _default_market_data()["equity_spot"]
EQUITY_INDEX_DEFAULT_DIVIDEND_YIELD_PCT = _default_market_data()["equity_dividend_yield_pct"]
EQUITY_INDEX_DEFAULT_VOLATILITY_PCT = _default_market_data()["equity_volatility_pct"]


def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _direction_or_default(value, default="payer"):
    return value if value in {"payer", "receiver"} else default


def _option_type_or_default(value, default="call"):
    return value if value in {"call", "put"} else default


def _period_from_label(label):
    text = str(label).strip().upper()
    if len(text) < 2:
        raise ValueError(f"Unsupported period label: {label}")
    return ql.Period(int(text[:-1]), {"D": ql.Days, "W": ql.Weeks, "M": ql.Months, "Y": ql.Years}[text[-1]])


def _years_from_label(label):
    text = str(label).strip().upper()
    if len(text) < 2:
        raise ValueError(f"Unsupported period label: {label}")
    value = int(text[:-1])
    if text[-1] == "Y":
        return float(value)
    if text[-1] == "M":
        return float(value) / 12.0
    if text[-1] == "W":
        return float(value) / 52.0
    if text[-1] == "D":
        return float(value) / 365.0
    raise ValueError(f"Unsupported period label: {label}")


def _date_iso_or_default(value, default_iso=DEFAULT_VALUATION_DATE_ISO):
    text = str(value or default_iso).strip()
    try:
        return ql.DateParser.parseISO(text).ISO()
    except RuntimeError:
        return default_iso


def valuation_date(state=None):
    return ql.DateParser.parseISO(
        _date_iso_or_default((state or {}).get("valuation_date_iso", DEFAULT_VALUATION_DATE_ISO))
    )


def _matrix_label_from_value(value, allowed_labels, default_label):
    if isinstance(value, str):
        text = value.strip().upper()
        if text in allowed_labels:
            return text
        if text.isdigit():
            candidate = f"{text}Y"
            if candidate in allowed_labels:
                return candidate
        return default_label

    try:
        integer_value = int(value)
    except (TypeError, ValueError):
        return default_label

    candidate = f"{integer_value}Y"
    return candidate if candidate in allowed_labels else default_label


def _frequency_months_or_default(value, default=12):
    try:
        months = int(value)
    except (TypeError, ValueError):
        return default
    return months if months in IR_FREQUENCY_LABELS else default


def frequency_label(months):
    return IR_FREQUENCY_LABELS.get(int(months), f"{int(months)}M")


def frequency_short_label(months):
    return IR_FREQUENCY_SHORT_LABELS.get(int(months), frequency_label(months))


def _default_swaption_normal_vol_matrix_bp(_base_vol_bp=62.0):
    return copy.deepcopy(_default_market_data()["swaption_vol_matrix_bp"])


def _full_curve_index_map(labels):
    return [SOFR_CURVE_TENOR_LABELS.index(label) for label in labels]


def _normalize_curve_quotes(quotes):
    if not isinstance(quotes, list):
        return list(SOFR_DEFAULT_CURVE_QUOTES_PCT)

    if len(quotes) == len(SOFR_DEFAULT_CURVE_QUOTES_PCT):
        return [_safe_float(quote, default) for quote, default in zip(quotes, SOFR_DEFAULT_CURVE_QUOTES_PCT)]

    if len(quotes) == len(SOFR_DEFAULT_CURVE_QUOTES_PCT) - 1:
        return [SOFR_OVERNIGHT_DEFAULT_PCT] + [
            _safe_float(quote, default)
            for quote, default in zip(quotes, SOFR_DEFAULT_CURVE_QUOTES_PCT[1:])
        ]

    normalized = list(SOFR_DEFAULT_CURVE_QUOTES_PCT)
    label_sets = {
        len(SOFR_LEGACY_CURVE_TENOR_LABELS): SOFR_LEGACY_CURVE_TENOR_LABELS,
        6: ("1D", "1Y", "2Y", "3Y", "5Y", "10Y"),
        5: ("1Y", "2Y", "3Y", "5Y", "10Y"),
    }
    labels = label_sets.get(len(quotes))
    if labels is not None:
        for index, full_index in enumerate(_full_curve_index_map(labels)):
            normalized[full_index] = _safe_float(quotes[index], normalized[full_index])
        return normalized

    return list(SOFR_DEFAULT_CURVE_QUOTES_PCT)


def _normalize_swaption_vol_matrix(matrix_like, base_vol_bp):
    defaults = _default_swaption_normal_vol_matrix_bp(base_vol_bp)
    if not isinstance(matrix_like, list):
        return defaults

    matrix = []
    annual_expiry_labels = tuple(f"{year}Y" for year in range(1, 11))
    annual_tenor_labels = tuple(f"{year}Y" for year in range(1, 11))
    annual_tenor_indexes = [SWAPTION_MATRIX_TENOR_LABELS.index(label) for label in annual_tenor_labels]

    if len(matrix_like) == len(annual_expiry_labels) and all(
        isinstance(row, list) and len(row) == len(annual_tenor_labels)
        for row in matrix_like
    ):
        mapped = [list(row) for row in defaults]
        for row_index, expiry_label in enumerate(annual_expiry_labels):
            if expiry_label not in SWAPTION_MATRIX_EXPIRY_LABELS:
                continue
            expiry_index = SWAPTION_MATRIX_EXPIRY_LABELS.index(expiry_label)
            for col_index, tenor_index in enumerate(annual_tenor_indexes):
                try:
                    mapped[expiry_index][tenor_index] = float(matrix_like[row_index][col_index])
                except (TypeError, ValueError):
                    pass
        return mapped

    for expiry_idx in range(len(SWAPTION_MATRIX_EXPIRY_LABELS)):
        raw_row = matrix_like[expiry_idx] if expiry_idx < len(matrix_like) else []
        if not isinstance(raw_row, list):
            raw_row = []
        row = []
        for tenor_idx in range(len(SWAPTION_MATRIX_TENOR_LABELS)):
            default_value = defaults[expiry_idx][tenor_idx]
            try:
                row.append(float(raw_row[tenor_idx]))
            except (IndexError, TypeError, ValueError):
                row.append(default_value)
        matrix.append(row)
    return matrix


def _clamp_year(years, minimum, maximum):
    return max(minimum, min(int(years), maximum))


def _clamp_months(months, minimum, maximum):
    return max(minimum, min(int(months), maximum))


def _coerce_expiry_years(value, default_label="1Y"):
    if isinstance(value, str):
        text = value.strip().upper()
        if text in SWAPTION_MATRIX_EXPIRY_LABELS:
            return _years_from_label(text)
        if len(text) >= 2 and text[:-1].isdigit() and text[-1] in {"D", "W", "M", "Y"}:
            return _years_from_label(text)
        if text.isdigit():
            return float(int(text))
    try:
        return float(value)
    except (TypeError, ValueError):
        return _years_from_label(default_label)


def _matrix_market_point(expiry_label, tenor_label, state):
    expiry_index = SWAPTION_MATRIX_EXPIRY_LABELS.index(expiry_label)
    tenor_index = SWAPTION_MATRIX_TENOR_LABELS.index(tenor_label)
    return float(state["market"]["swaption_vol_matrix_bp"][expiry_index][tenor_index])


def swaption_matrix_market_sources(portfolio_state, expiry_value, swap_tenor_value):
    state = normalize_portfolio_state(portfolio_state)
    tenor_label = _matrix_label_from_value(swap_tenor_value, SWAPTION_MATRIX_TENOR_LABELS, "1Y")
    target_years = _coerce_expiry_years(expiry_value)

    exact_label = None
    if isinstance(expiry_value, str):
        candidate = expiry_value.strip().upper()
        if candidate in SWAPTION_MATRIX_EXPIRY_LABELS:
            exact_label = candidate
    else:
        integer_target = int(round(target_years))
        candidate = f"{integer_target}Y"
        if abs(target_years - float(integer_target)) <= 1e-9 and candidate in SWAPTION_MATRIX_EXPIRY_LABELS:
            exact_label = candidate

    if exact_label is not None:
        return {
            "vol_bp": _matrix_market_point(exact_label, tenor_label, state),
            "source_market_points": [(exact_label, tenor_label)],
            "effective_expiry_label": exact_label,
        }

    expiry_year_pairs = [(_years_from_label(label), label) for label in SWAPTION_MATRIX_EXPIRY_LABELS]
    if target_years <= expiry_year_pairs[0][0]:
        nearest_label = expiry_year_pairs[0][1]
        return {
            "vol_bp": _matrix_market_point(nearest_label, tenor_label, state),
            "source_market_points": [(nearest_label, tenor_label)],
            "effective_expiry_label": nearest_label,
        }
    if target_years >= expiry_year_pairs[-1][0]:
        nearest_label = expiry_year_pairs[-1][1]
        return {
            "vol_bp": _matrix_market_point(nearest_label, tenor_label, state),
            "source_market_points": [(nearest_label, tenor_label)],
            "effective_expiry_label": nearest_label,
        }

    for (lower_years, lower_label), (upper_years, upper_label) in zip(expiry_year_pairs, expiry_year_pairs[1:]):
        if lower_years <= target_years <= upper_years:
            if abs(target_years - lower_years) <= 1e-9:
                return {
                    "vol_bp": _matrix_market_point(lower_label, tenor_label, state),
                    "source_market_points": [(lower_label, tenor_label)],
                    "effective_expiry_label": lower_label,
                }
            if abs(target_years - upper_years) <= 1e-9:
                return {
                    "vol_bp": _matrix_market_point(upper_label, tenor_label, state),
                    "source_market_points": [(upper_label, tenor_label)],
                    "effective_expiry_label": upper_label,
                }
            lower_vol = _matrix_market_point(lower_label, tenor_label, state)
            upper_vol = _matrix_market_point(upper_label, tenor_label, state)
            weight = (target_years - lower_years) / (upper_years - lower_years)
            return {
                "vol_bp": lower_vol + weight * (upper_vol - lower_vol),
                "source_market_points": [(lower_label, tenor_label), (upper_label, tenor_label)],
                "effective_expiry_label": f"{target_years:g}Y",
            }

    fallback_label = SWAPTION_MATRIX_EXPIRY_LABELS[-1]
    return {
        "vol_bp": _matrix_market_point(fallback_label, tenor_label, state),
        "source_market_points": [(fallback_label, tenor_label)],
        "effective_expiry_label": fallback_label,
    }


def lookup_swaption_normal_vol_bp(portfolio_state, expiry_years, swap_tenor_years):
    return float(swaption_matrix_market_sources(portfolio_state, expiry_years, swap_tenor_years)["vol_bp"])


def default_portfolio_state():
    market_defaults = _default_market_data()
    trade_defaults = _default_trades_data()
    return copy.deepcopy(
        {
            "valuation_date_iso": market_defaults["valuation_date_iso"],
            "market": {
                "curve_quotes_pct": list(market_defaults["curve_quotes_pct"]),
                "hw_mean_reversion": market_defaults["hw_mean_reversion"],
                "swaption_vol_matrix_bp": copy.deepcopy(market_defaults["swaption_vol_matrix_bp"]),
                "equity_spot": market_defaults["equity_spot"],
                "equity_dividend_yield_pct": market_defaults["equity_dividend_yield_pct"],
                "equity_volatility_pct": market_defaults["equity_volatility_pct"],
            },
            "trades": trade_defaults,
        }
    )


def normalize_portfolio_state(portfolio_state=None):
    state = default_portfolio_state()
    if not portfolio_state:
        return state

    if isinstance(portfolio_state, list):
        state["market"]["curve_quotes_pct"] = _normalize_curve_quotes(portfolio_state)
        return state

    state["valuation_date_iso"] = _date_iso_or_default(
        portfolio_state.get(
            "valuation_date_iso",
            portfolio_state.get("market", {}).get("valuation_date_iso", state["valuation_date_iso"]),
        ),
        state["valuation_date_iso"],
    )

    market = portfolio_state.get("market", {})
    state["market"]["curve_quotes_pct"] = _normalize_curve_quotes(
        market.get("curve_quotes_pct", state["market"]["curve_quotes_pct"])
    )

    hw_mean_reversion = market.get("hw_mean_reversion", state["market"]["hw_mean_reversion"])
    if isinstance(hw_mean_reversion, dict):
        hw_mean_reversion = hw_mean_reversion.get("value", state["market"]["hw_mean_reversion"])
    try:
        state["market"]["hw_mean_reversion"] = max(float(hw_mean_reversion), 0.0)
    except (TypeError, ValueError):
        state["market"]["hw_mean_reversion"] = DEFAULT_HW_MEAN_REVERSION

    state["market"]["swaption_vol_matrix_bp"] = _normalize_swaption_vol_matrix(
        market.get("swaption_vol_matrix_bp"),
        62.0,
    )
    state["market"]["equity_spot"] = max(
        _safe_float(market.get("equity_spot", state["market"]["equity_spot"]), EQUITY_INDEX_DEFAULT_SPOT),
        1.0,
    )
    state["market"]["equity_dividend_yield_pct"] = _safe_float(
        market.get("equity_dividend_yield_pct", state["market"]["equity_dividend_yield_pct"]),
        EQUITY_INDEX_DEFAULT_DIVIDEND_YIELD_PCT,
    )
    state["market"]["equity_volatility_pct"] = max(
        _safe_float(
            market.get("equity_volatility_pct", state["market"]["equity_volatility_pct"]),
            EQUITY_INDEX_DEFAULT_VOLATILITY_PCT,
        ),
        0.0,
    )

    for trade_type in TRADE_SEQUENCE:
        overrides = portfolio_state.get("trades", {}).get(trade_type, {})
        state["trades"][trade_type].update(overrides)

    state["trades"]["swap"]["direction"] = _direction_or_default(
        state["trades"]["swap"]["direction"],
        "payer",
    )
    state["trades"]["swap"]["notional"] = max(
        _safe_float(state["trades"]["swap"]["notional"], 1_000_000),
        1.0,
    )
    state["trades"]["swap"]["fixed_rate_pct"] = _safe_float(
        state["trades"]["swap"]["fixed_rate_pct"],
        3.0,
    )
    state["trades"]["swap"]["tenor_years"] = _clamp_year(
        state["trades"]["swap"]["tenor_years"],
        1,
        30,
    )
    state["trades"]["swap"]["payment_frequency_months"] = _frequency_months_or_default(
        state["trades"]["swap"].get("payment_frequency_months", 12),
        12,
    )
    state["trades"]["swap"]["reset_frequency_months"] = _frequency_months_or_default(
        state["trades"]["swap"].get("reset_frequency_months", 12),
        12,
    )

    state["trades"]["european_swaption"]["direction"] = _direction_or_default(
        state["trades"]["european_swaption"]["direction"],
        "payer",
    )
    state["trades"]["european_swaption"]["notional"] = max(
        _safe_float(state["trades"]["european_swaption"]["notional"], 1_000_000),
        1.0,
    )
    state["trades"]["european_swaption"]["strike_pct"] = _safe_float(
        state["trades"]["european_swaption"]["strike_pct"],
        3.0,
    )
    state["trades"]["european_swaption"]["expiry_years"] = _clamp_year(
        state["trades"]["european_swaption"]["expiry_years"],
        1,
        10,
    )
    state["trades"]["european_swaption"]["swap_tenor_years"] = _clamp_year(
        state["trades"]["european_swaption"]["swap_tenor_years"],
        1,
        10,
    )
    state["trades"]["european_swaption"]["payment_frequency_months"] = _frequency_months_or_default(
        state["trades"]["european_swaption"].get("payment_frequency_months", 12),
        12,
    )
    state["trades"]["european_swaption"]["reset_frequency_months"] = _frequency_months_or_default(
        state["trades"]["european_swaption"].get("reset_frequency_months", 12),
        12,
    )

    for bermudan_trade_key in BERMUDAN_TRADE_KEYS:
        state["trades"][bermudan_trade_key]["direction"] = _direction_or_default(
            state["trades"][bermudan_trade_key]["direction"],
            "payer",
        )
        state["trades"][bermudan_trade_key]["notional"] = max(
            _safe_float(state["trades"][bermudan_trade_key]["notional"], 1_000_000),
            1.0,
        )
        state["trades"][bermudan_trade_key]["strike_pct"] = _safe_float(
            state["trades"][bermudan_trade_key]["strike_pct"],
            3.0,
        )
        state["trades"][bermudan_trade_key]["first_exercise_years"] = _clamp_year(
            state["trades"][bermudan_trade_key]["first_exercise_years"],
            1,
            9,
        )
        legacy_swap_tenor_years = _clamp_year(
            state["trades"][bermudan_trade_key].get("swap_tenor_years", 4),
            1,
            10,
        )
        default_final_maturity = (
            state["trades"][bermudan_trade_key]["first_exercise_years"] + legacy_swap_tenor_years
        )
        state["trades"][bermudan_trade_key]["final_maturity_years"] = _clamp_year(
            state["trades"][bermudan_trade_key].get("final_maturity_years", default_final_maturity),
            state["trades"][bermudan_trade_key]["first_exercise_years"] + 1,
            10,
        )
        state["trades"][bermudan_trade_key]["payment_frequency_months"] = _frequency_months_or_default(
            state["trades"][bermudan_trade_key].get("payment_frequency_months", 12),
            12,
        )
        state["trades"][bermudan_trade_key]["reset_frequency_months"] = _frequency_months_or_default(
            state["trades"][bermudan_trade_key].get("reset_frequency_months", 12),
            12,
        )

    state["trades"]["equity_cliquet"]["option_type"] = _option_type_or_default(
        state["trades"]["equity_cliquet"]["option_type"],
        "call",
    )
    state["trades"]["equity_cliquet"]["quantity"] = max(
        _safe_float(state["trades"]["equity_cliquet"]["quantity"], 50.0),
        0.01,
    )
    state["trades"]["equity_cliquet"]["moneyness_pct"] = max(
        _safe_float(state["trades"]["equity_cliquet"]["moneyness_pct"], 100.0),
        0.01,
    )
    state["trades"]["equity_cliquet"]["maturity_months"] = _clamp_months(
        state["trades"]["equity_cliquet"]["maturity_months"],
        1,
        36,
    )
    state["trades"]["equity_cliquet"]["reset_frequency_months"] = _clamp_months(
        state["trades"]["equity_cliquet"]["reset_frequency_months"],
        1,
        12,
    )
    if state["trades"]["equity_cliquet"]["reset_frequency_months"] > state["trades"]["equity_cliquet"]["maturity_months"]:
        state["trades"]["equity_cliquet"]["reset_frequency_months"] = state["trades"]["equity_cliquet"]["maturity_months"]

    return state


def build_sofr_curve(today, sofr_rates):
    normalized_quotes = _normalize_curve_quotes(list(sofr_rates))
    if len(normalized_quotes) != len(SOFR_CURVE_TENOR_LABELS):
        raise ValueError(
            "Expected "
            f"{len(SOFR_CURVE_TENOR_LABELS)} SOFR quotes for "
            f"{', '.join(SOFR_CURVE_TENOR_LABELS)}."
        )

    calendar = ql.UnitedStates(ql.UnitedStates.Settlement)
    helpers = []
    for (label, period, helper_kind), rate in zip(SOFR_CURVE_POINT_SPECS, normalized_quotes):
        quote_handle = ql.QuoteHandle(ql.SimpleQuote(rate / 100.0))
        if helper_kind == "deposit":
            helpers.append(
                ql.DepositRateHelper(
                    quote_handle,
                    period,
                    0,
                    calendar,
                    ql.Following,
                    False,
                    ql.Actual360(),
                )
            )
            continue
        helpers.append(
            ql.OISRateHelper(
                2,
                period,
                quote_handle,
                ql.Sofr(),
            )
        )
    return ql.PiecewiseLogCubicDiscount(today, helpers, ql.Actual360())


def curve_zero_rate_points(curve, tenor_labels=SOFR_CURVE_TENOR_LABELS):
    node_dates = list(curve.dates())[1:]
    day_counter = ql.Actual365Fixed()
    points = []

    for index, node_date in enumerate(node_dates):
        label = tenor_labels[index] if index < len(tenor_labels) else f"Node {index + 1}"
        zero_rate_pct = curve.zeroRate(node_date, day_counter, ql.Continuous).rate() * 100.0
        points.append(
            {
                "label": label,
                "date_iso": node_date.ISO(),
                "short_date": f"{node_date.month():02d}/{node_date.dayOfMonth():02d}/{node_date.year()}",
                "rate_pct": zero_rate_pct,
                "year_fraction": day_counter.yearFraction(curve.referenceDate(), node_date),
            }
        )

    return points


def daily_one_day_forward_points(curve, horizon_years=SOFR_FORWARD_HORIZON_YEARS):
    day_counter = ql.Actual360()
    reference_date = curve.referenceDate()
    horizon_end_date = reference_date + ql.Period(int(horizon_years), ql.Years)
    points = []
    start_date = reference_date
    offset_days = 0

    while start_date <= horizon_end_date:
        end_date = start_date + 1
        forward_rate_pct = (
            curve.forwardRate(start_date, end_date, day_counter, ql.Simple).rate() * 100.0
        )
        points.append(
            {
                "label": start_date.ISO(),
                "short_label": f"{start_date.month():02d}/{start_date.dayOfMonth():02d}",
                "axis_label": (
                    f"{start_date.month():02d}/{start_date.dayOfMonth():02d}/{start_date.year()}"
                ),
                "start_date_iso": start_date.ISO(),
                "end_date_iso": end_date.ISO(),
                "offset_days": offset_days,
                "rate_pct": forward_rate_pct,
            }
        )
        start_date = start_date + 1
        offset_days += 1

    return points


def curve_debug_rows(curve, sofr_rates):
    normalized_quotes = _normalize_curve_quotes(list(sofr_rates))
    node_dates = list(curve.dates())[1:]
    zero_points = curve_zero_rate_points(curve)

    sofr_by_date = {
        node_date.ISO(): normalized_quotes[index]
        for index, node_date in enumerate(node_dates)
        if index < len(normalized_quotes)
    }
    zero_by_date = {
        point["date_iso"]: point["rate_pct"]
        for point in zero_points
    }

    last_curve_date = node_dates[-1]
    forward_by_date = {}
    day_counter = ql.Actual360()
    current_date = curve.referenceDate()
    while current_date < last_curve_date:
        next_date = current_date + 1
        forward_by_date[current_date.ISO()] = (
            curve.forwardRate(current_date, next_date, day_counter, ql.Simple).rate() * 100.0
        )
        current_date = next_date

    rows = []
    current_date = curve.referenceDate()
    while current_date <= last_curve_date:
        date_iso = current_date.ISO()
        rows.append(
            {
                "date": date_iso,
                "sofr_rate_pct": sofr_by_date.get(date_iso),
                "zero_rate_pct": zero_by_date.get(date_iso),
                "forward_rate_pct": forward_by_date.get(date_iso),
            }
        )
        current_date = current_date + 1

    return rows


def curve_debug_csv(curve, sofr_rates):
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["date", "sofr_rate_pct", "zero_rate_pct", "forward_rate_pct"])

    for row in curve_debug_rows(curve, sofr_rates):
        writer.writerow(
            [
                row["date"],
                "" if row["sofr_rate_pct"] is None else f"{row['sofr_rate_pct']:.8f}",
                "" if row["zero_rate_pct"] is None else f"{row['zero_rate_pct']:.8f}",
                "" if row["forward_rate_pct"] is None else f"{row['forward_rate_pct']:.8f}",
            ]
        )

    return output.getvalue()


def write_curve_debug_csv(output_path, curve, sofr_rates):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(curve_debug_csv(curve, sofr_rates), encoding="utf-8")
    return path


def _fixed_leg_direction(direction):
    return ql.OvernightIndexedSwap.Payer if direction == "payer" else ql.OvernightIndexedSwap.Receiver


def _spot_start_date(today, calendar):
    return calendar.advance(today, 2, ql.Days)


def _build_schedule(start, maturity, frequency_months, calendar):
    return ql.Schedule(
        start,
        maturity,
        ql.Period(int(frequency_months), ql.Months),
        calendar,
        ql.ModifiedFollowing,
        ql.ModifiedFollowing,
        ql.DateGeneration.Forward,
        False,
    )


def _make_ois_swap(
    start,
    maturity,
    direction,
    notional,
    fixed_rate_pct,
    curve_handle,
    payment_frequency_months=12,
    reset_frequency_months=12,
):
    calendar = ql.UnitedStates(ql.UnitedStates.Settlement)
    fixed_schedule = _build_schedule(start, maturity, payment_frequency_months, calendar)
    float_schedule = _build_schedule(start, maturity, reset_frequency_months, calendar)
    fixed_nominals = [float(notional)] * max(len(fixed_schedule) - 1, 1)
    float_nominals = [float(notional)] * max(len(float_schedule) - 1, 1)
    swap = ql.OvernightIndexedSwap(
        _fixed_leg_direction(direction),
        fixed_nominals,
        fixed_schedule,
        fixed_rate_pct / 100.0,
        ql.Actual360(),
        float_nominals,
        float_schedule,
        ql.Sofr(curve_handle),
        0.0,
        0,
        ql.ModifiedFollowing,
        calendar,
        False,
        ql.RateAveraging.Compound,
    )
    swap.setPricingEngine(ql.DiscountingSwapEngine(curve_handle))
    return swap


def _market_context(portfolio_state):
    state = normalize_portfolio_state(portfolio_state)
    today = valuation_date(state)
    ql.Settings.instance().evaluationDate = today
    curve = build_sofr_curve(today, state["market"]["curve_quotes_pct"])
    curve_handle = ql.YieldTermStructureHandle(curve)
    calendar = ql.UnitedStates(ql.UnitedStates.Settlement)
    return state, today, calendar, curve, curve_handle


def _resolve_market_context(portfolio_state=None, market_context=None):
    if market_context is not None:
        return market_context
    return _market_context(portfolio_state)


def _format_notional(notional):
    if abs(notional) >= 1_000_000:
        return f"${notional / 1_000_000:.2f}mm"
    if abs(notional) >= 1_000:
        return f"${notional / 1_000:.0f}k"
    return f"${notional:,.0f}"


def _equity_calendar():
    return ql.UnitedStates(ql.UnitedStates.NYSE)


def _equity_day_count():
    return ql.Actual365Fixed()


def _cliquet_option_enum(option_type):
    return ql.Option.Call if option_type == "call" else ql.Option.Put


def _safe_greek(callable_metric):
    try:
        value = float(callable_metric())
    except RuntimeError:
        return 0.0
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return value


def _normal_cdf(value):
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _normal_pdf(value):
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _build_equity_market_context(portfolio_state=None, market_context=None):
    state, today, _calendar, curve, curve_handle = _resolve_market_context(
        portfolio_state,
        market_context,
    )
    equity_calendar = _equity_calendar()
    day_count = _equity_day_count()
    spot_quote = ql.SimpleQuote(float(state["market"]["equity_spot"]))
    dividend_curve = ql.FlatForward(
        today,
        float(state["market"]["equity_dividend_yield_pct"]) / 100.0,
        day_count,
    )
    volatility_surface = ql.BlackConstantVol(
        today,
        equity_calendar,
        float(state["market"]["equity_volatility_pct"]) / 100.0,
        day_count,
    )
    process = ql.BlackScholesMertonProcess(
        ql.QuoteHandle(spot_quote),
        ql.YieldTermStructureHandle(dividend_curve),
        curve_handle,
        ql.BlackVolTermStructureHandle(volatility_surface),
    )
    return {
        "state": state,
        "today": today,
        "curve": curve,
        "curve_handle": curve_handle,
        "equity_calendar": equity_calendar,
        "day_count": day_count,
        "spot_quote": spot_quote,
        "dividend_curve": dividend_curve,
        "volatility_surface": volatility_surface,
        "process": process,
    }


def cliquet_reset_schedule(trade, today, calendar=None):
    calendar = calendar or _equity_calendar()
    maturity_months = int(trade["maturity_months"])
    reset_frequency_months = int(trade["reset_frequency_months"])
    maturity = calendar.advance(today, maturity_months, ql.Months, ql.ModifiedFollowing)
    reset_dates = [today]
    reset_month = reset_frequency_months
    while reset_month < maturity_months:
        reset_dates.append(calendar.advance(today, reset_month, ql.Months, ql.ModifiedFollowing))
        reset_month += reset_frequency_months
    return reset_dates, maturity


def _cliquet_period_unit_price(
    option_type,
    spot,
    moneyness,
    start,
    end,
    today,
    risk_free_curve,
    dividend_curve,
    flat_volatility_pct,
    day_count=None,
):
    day_count = day_count or _equity_day_count()
    tau = day_count.yearFraction(start, end)
    if tau <= 0.0:
        return 0.0

    sigma = max(float(flat_volatility_pct) / 100.0, 0.0)
    discount_to_start = risk_free_curve.discount(start)
    discount_to_end = risk_free_curve.discount(end)
    dividend_to_start = dividend_curve.discount(start)
    dividend_to_end = dividend_curve.discount(end)
    discount_period = discount_to_end / discount_to_start
    dividend_period = dividend_to_end / dividend_to_start
    forward_ratio = dividend_period / discount_period

    if sigma <= 0.0:
        intrinsic = max(
            (forward_ratio - moneyness) if option_type == "call" else (moneyness - forward_ratio),
            0.0,
        )
        return float(spot) * dividend_to_start * discount_period * intrinsic

    std_dev = sigma * math.sqrt(tau)
    d1 = (math.log(forward_ratio / moneyness) + 0.5 * sigma * sigma * tau) / std_dev
    d2 = d1 - std_dev
    if option_type == "call":
        return float(spot) * dividend_to_start * (
            dividend_period * _normal_cdf(d1) - moneyness * discount_period * _normal_cdf(d2)
        )
    return float(spot) * dividend_to_start * (
        moneyness * discount_period * _normal_cdf(-d2) - dividend_period * _normal_cdf(-d1)
    )


def _cliquet_period_discounted_intrinsic(
    option_type,
    spot,
    moneyness,
    start,
    end,
    risk_free_curve,
    dividend_curve,
    day_count=None,
):
    day_count = day_count or _equity_day_count()
    tau = day_count.yearFraction(start, end)
    if tau <= 0.0:
        return 0.0
    discount_to_start = risk_free_curve.discount(start)
    discount_to_end = risk_free_curve.discount(end)
    dividend_to_start = dividend_curve.discount(start)
    dividend_to_end = dividend_curve.discount(end)
    discount_period = discount_to_end / discount_to_start
    dividend_period = dividend_to_end / dividend_to_start
    forward_ratio = dividend_period / discount_period
    intrinsic = max(
        (forward_ratio - moneyness) if option_type == "call" else (moneyness - forward_ratio),
        0.0,
    )
    return float(spot) * dividend_to_start * discount_period * intrinsic


def cliquet_forward_start_rows(portfolio_state=None, market_context=None):
    equity_context = _build_equity_market_context(portfolio_state, market_context)
    state = equity_context["state"]
    trade = state["trades"]["equity_cliquet"]
    reset_dates, maturity = cliquet_reset_schedule(
        trade,
        equity_context["today"],
        equity_context["equity_calendar"],
    )
    period_dates = list(reset_dates) + [maturity]
    rows = []
    for period_index, (start_date, end_date) in enumerate(
        zip(period_dates[:-1], period_dates[1:]),
        start=1,
    ):
        unit_npv = _cliquet_period_unit_price(
            trade["option_type"],
            state["market"]["equity_spot"],
            trade["moneyness_pct"] / 100.0,
            start_date,
            end_date,
            equity_context["today"],
            equity_context["curve_handle"],
            equity_context["dividend_curve"],
            state["market"]["equity_volatility_pct"],
            equity_context["day_count"],
        )
        discount_period = equity_context["curve_handle"].discount(end_date) / equity_context["curve_handle"].discount(
            start_date
        )
        dividend_period = equity_context["dividend_curve"].discount(end_date) / equity_context["dividend_curve"].discount(
            start_date
        )
        forward_ratio = dividend_period / discount_period
        tau = equity_context["day_count"].yearFraction(start_date, end_date)
        rows.append(
            {
                "period": period_index,
                "start_date_iso": start_date.ISO(),
                "end_date_iso": end_date.ISO(),
                "year_fraction": tau,
                "forward_ratio": forward_ratio,
                "unit_npv": unit_npv,
                "trade_npv": unit_npv * float(trade["quantity"]),
                "unit_delta": unit_npv / float(state["market"]["equity_spot"]),
                "trade_delta": unit_npv * float(trade["quantity"]) / float(state["market"]["equity_spot"]),
            }
        )
    return rows


def _create_equity_cliquet(portfolio_state=None, market_context=None):
    equity_context = _build_equity_market_context(portfolio_state, market_context)
    trade = equity_context["state"]["trades"]["equity_cliquet"]
    reset_dates, maturity = cliquet_reset_schedule(
        trade,
        equity_context["today"],
        equity_context["equity_calendar"],
    )
    option = ql.CliquetOption(
        ql.PercentageStrikePayoff(
            _cliquet_option_enum(trade["option_type"]),
            float(trade["moneyness_pct"]) / 100.0,
        ),
        ql.EuropeanExercise(maturity),
        reset_dates,
    )
    option.setPricingEngine(ql.AnalyticCliquetEngine(equity_context["process"]))
    return option, reset_dates, maturity, equity_context


def cliquet_analytics(portfolio_state=None, market_context=None):
    option, reset_dates, maturity, equity_context = _create_equity_cliquet(
        portfolio_state,
        market_context,
    )
    state = equity_context["state"]
    trade = state["trades"]["equity_cliquet"]
    quantity = float(trade["quantity"])
    unit_npv = option.NPV()
    base_npv = unit_npv * quantity
    period_rows = cliquet_forward_start_rows(
        state,
        market_context=(
            state,
            equity_context["today"],
            ql.UnitedStates(ql.UnitedStates.Settlement),
            equity_context["curve"],
            equity_context["curve_handle"],
        ),
    )
    scenario_rows = []
    for spot_shock in CLIQUET_SCENARIO_SPOT_SHOCKS_PCT:
        row = {"spot_shock_pct": spot_shock, "cells": []}
        for vol_shock in CLIQUET_SCENARIO_VOL_SHOCKS_PCT:
            shocked_state = copy.deepcopy(state)
            shocked_state["market"]["equity_spot"] = max(
                shocked_state["market"]["equity_spot"] * (1.0 + spot_shock / 100.0),
                1.0,
            )
            shocked_state["market"]["equity_volatility_pct"] = max(
                shocked_state["market"]["equity_volatility_pct"] + vol_shock,
                0.0,
            )
            shocked_option, _dates, _maturity, _context = _create_equity_cliquet(
                shocked_state,
                market_context=(
                    shocked_state,
                    equity_context["today"],
                    ql.UnitedStates(ql.UnitedStates.Settlement),
                    equity_context["curve"],
                    equity_context["curve_handle"],
                ),
            )
            row["cells"].append(
                {
                    "vol_shock_pct": vol_shock,
                    "npv": shocked_option.NPV() * quantity,
                }
            )
        scenario_rows.append(row)

    randomizer = random.Random(CLIQUET_MC_SEED)
    period_dates = list(reset_dates) + [maturity]
    pv_paths = []
    realized_payoff_paths = []
    positive_period_counts = []
    for _ in range(CLIQUET_MC_PATH_COUNT):
        start_spot = float(state["market"]["equity_spot"])
        pv_total = 0.0
        realized_total = 0.0
        positive_periods = 0
        for start_date, end_date in zip(period_dates[:-1], period_dates[1:]):
            tau = equity_context["day_count"].yearFraction(start_date, end_date)
            if tau <= 0.0:
                continue
            discount_period = equity_context["curve_handle"].discount(end_date) / equity_context["curve_handle"].discount(
                start_date
            )
            dividend_period = equity_context["dividend_curve"].discount(end_date) / equity_context["dividend_curve"].discount(
                start_date
            )
            sigma = float(state["market"]["equity_volatility_pct"]) / 100.0
            drift = math.log(dividend_period / discount_period) - 0.5 * sigma * sigma * tau
            end_spot = start_spot * math.exp(drift + sigma * math.sqrt(tau) * randomizer.gauss(0.0, 1.0))
            period_payoff = max(
                (end_spot - (trade["moneyness_pct"] / 100.0) * start_spot)
                if trade["option_type"] == "call"
                else ((trade["moneyness_pct"] / 100.0) * start_spot - end_spot),
                0.0,
            ) * quantity
            if period_payoff > 0.0:
                positive_periods += 1
            pv_total += period_payoff * equity_context["curve_handle"].discount(end_date)
            realized_total += period_payoff
            start_spot = end_spot
        pv_paths.append(pv_total)
        realized_payoff_paths.append(realized_total)
        positive_period_counts.append(positive_periods)

    sorted_pv_paths = sorted(pv_paths)
    tail_count = max(int(0.05 * len(sorted_pv_paths)), 1)
    distribution_summary = {
        "path_count": CLIQUET_MC_PATH_COUNT,
        "seed": CLIQUET_MC_SEED,
        "mean_pv": statistics.fmean(pv_paths),
        "stdev_pv": statistics.pstdev(pv_paths),
        "p05_pv": sorted_pv_paths[tail_count - 1],
        "expected_shortfall_pv": statistics.fmean(sorted_pv_paths[:tail_count]),
        "probability_of_zero_payoff_pct": 100.0
        * sum(1 for value in realized_payoff_paths if value == 0.0)
        / len(realized_payoff_paths),
        "average_positive_periods": statistics.fmean(positive_period_counts),
    }

    return {
        "base_npv": base_npv,
        "unit_npv": unit_npv,
        "quantity": quantity,
        "equivalent_notional": quantity * float(state["market"]["equity_spot"]),
        "maturity_date_iso": maturity.ISO(),
        "reset_count": len(period_rows),
        "reset_dates": [date.ISO() for date in reset_dates],
        "greeks": {
            "delta": _safe_greek(option.delta) * quantity,
            "gamma": _safe_greek(option.gamma) * quantity,
            "vega": _safe_greek(option.vega) * quantity,
            "theta": _safe_greek(option.theta) * quantity,
            "rho": _safe_greek(option.rho) * quantity,
            "dividend_rho": _safe_greek(option.dividendRho) * quantity,
            "elasticity": _safe_greek(option.elasticity),
        },
        "period_rows": period_rows,
        "scenario_rows": scenario_rows,
        "scenario_vol_headers": [f"{shock:+.1f} vol pts" for shock in CLIQUET_SCENARIO_VOL_SHOCKS_PCT],
        "distribution_summary": distribution_summary,
    }


def trade_structure_summary(trade_type, trade, market):
    if trade_type == "swap":
        fixed_side = "Pay fixed" if trade["direction"] == "payer" else "Receive fixed"
        return (
            f"{fixed_side} | {trade['tenor_years']}Y | "
            f"{trade['fixed_rate_pct']:.2f}% | {frequency_short_label(trade['payment_frequency_months'])}/"
            f"{frequency_short_label(trade['reset_frequency_months'])} | {_format_notional(trade['notional'])}"
        )

    if trade_type == "european_swaption":
        option_side = "Payer" if trade["direction"] == "payer" else "Receiver"
        matrix_vol_bp = lookup_swaption_normal_vol_bp(
            {"market": market},
            trade["expiry_years"],
            trade["swap_tenor_years"],
        )
        return (
            f"{option_side} | {trade['expiry_years']}Y x {trade['swap_tenor_years']}Y | "
            f"K {trade['strike_pct']:.2f}% | {frequency_short_label(trade['payment_frequency_months'])}/"
            f"{frequency_short_label(trade['reset_frequency_months'])} | ATM {matrix_vol_bp:.1f}bp"
        )

    if trade_type in BERMUDAN_TRADE_KEYS:
        option_side = "Payer" if trade["direction"] == "payer" else "Receiver"
        final_maturity_years = int(trade["final_maturity_years"])
        exercise_count = max(
            math.ceil(
                (final_maturity_years - int(trade["first_exercise_years"])) * 12
                / int(trade["payment_frequency_months"])
            ),
            1,
        )
        return (
            f"{option_side} | {final_maturity_years}Y NC {trade['first_exercise_years']}Y | "
            f"{exercise_count} dates | {frequency_short_label(trade['payment_frequency_months'])}/"
            f"{frequency_short_label(trade['reset_frequency_months'])} | Diagonal matrix calib"
        )

    option_side = "Call" if trade["option_type"] == "call" else "Put"
    reset_count = max(
        math.ceil(int(trade["maturity_months"]) / int(trade["reset_frequency_months"])),
        1,
    )
    return (
        f"{option_side} | SPX | {reset_count} resets | "
        f"M {trade['moneyness_pct']:.1f}% | Qty {trade['quantity']:.2f}"
    )


def trade_card_summary(trade_type, trade, market):
    if trade_type == "swap":
        headline = "Pay fixed" if trade["direction"] == "payer" else "Receive fixed"
        detail = (
            f"{trade['tenor_years']}Y maturity, {trade['fixed_rate_pct']:.2f}% fixed, "
            f"{frequency_label(trade['payment_frequency_months'])} pay, "
            f"{frequency_label(trade['reset_frequency_months'])} reset, "
            f"{_format_notional(trade['notional'])}"
        )
        return headline, detail

    if trade_type == "european_swaption":
        matrix_vol_bp = lookup_swaption_normal_vol_bp(
            {"market": market},
            trade["expiry_years"],
            trade["swap_tenor_years"],
        )
        headline = f"{trade['expiry_years']}Y x {trade['swap_tenor_years']}Y"
        detail = (
            f"{'Payer' if trade['direction'] == 'payer' else 'Receiver'} style, "
            f"K {trade['strike_pct']:.2f}%, {_format_notional(trade['notional'])}, "
            f"{frequency_label(trade['payment_frequency_months'])} pay / "
            f"{frequency_label(trade['reset_frequency_months'])} reset, ATM {matrix_vol_bp:.1f}bp matrix"
        )
        return headline, detail

    if trade_type in BERMUDAN_TRADE_KEYS:
        final_maturity_years = int(trade["final_maturity_years"])
        exercise_count = max(
            math.ceil(
                (final_maturity_years - int(trade["first_exercise_years"])) * 12
                / int(trade["payment_frequency_months"])
            ),
            1,
        )
        headline = f"{final_maturity_years}Y NC {trade['first_exercise_years']}Y with {exercise_count} dates"
        detail = (
            f"{'Payer' if trade['direction'] == 'payer' else 'Receiver'} style, "
            f"K {trade['strike_pct']:.2f}%, {_format_notional(trade['notional'])}, "
            f"{frequency_label(trade['payment_frequency_months'])} pay / "
            f"{frequency_label(trade['reset_frequency_months'])} reset, "
            f"HW mean reversion {market['hw_mean_reversion']:.4f}, diagonal calibration"
        )
        return headline, detail

    reset_count = max(
        math.ceil(int(trade["maturity_months"]) / int(trade["reset_frequency_months"])),
        1,
    )
    headline = f"SPX {trade['maturity_months']}M cliquet with {reset_count} reset periods"
    detail = (
        f"{'Call' if trade['option_type'] == 'call' else 'Put'} strip, "
        f"M {trade['moneyness_pct']:.1f}%, qty {trade['quantity']:.2f}, "
        f"spot {market['equity_spot']:.2f}, vol {market['equity_volatility_pct']:.2f}%"
    )
    return headline, detail


def _create_live_swap(trade, today, calendar, curve_handle):
    start = _spot_start_date(today, calendar)
    maturity = calendar.advance(start, int(trade["tenor_years"]), ql.Years)
    return _make_ois_swap(
        start,
        maturity,
        trade["direction"],
        trade["notional"],
        trade["fixed_rate_pct"],
        curve_handle,
        payment_frequency_months=trade["payment_frequency_months"],
        reset_frequency_months=trade["reset_frequency_months"],
    )


def _create_forward_swap(trade, start, maturity, curve_handle):
    return _make_ois_swap(
        start,
        maturity,
        trade["direction"],
        trade["notional"],
        trade["strike_pct"],
        curve_handle,
        payment_frequency_months=trade["payment_frequency_months"],
        reset_frequency_months=trade["reset_frequency_months"],
    )


def _normal_vol_from_bp(vol_bp):
    return max(float(vol_bp) / 10000.0, 1e-8)


def _create_european_swaption(trade, today, calendar, curve_handle, normal_vol_bp):
    spot = _spot_start_date(today, calendar)
    exercise_date = calendar.advance(spot, int(trade["expiry_years"]), ql.Years)
    maturity = calendar.advance(exercise_date, int(trade["swap_tenor_years"]), ql.Years)
    underlying = _create_forward_swap(trade, exercise_date, maturity, curve_handle)
    swaption = ql.Swaption(underlying, ql.EuropeanExercise(exercise_date))
    swaption.setPricingEngine(
        ql.BachelierSwaptionEngine(
            curve_handle,
            ql.QuoteHandle(ql.SimpleQuote(_normal_vol_from_bp(normal_vol_bp))),
        )
    )
    return swaption


def _bermudan_schedule_context(trade, today, calendar):
    spot = _spot_start_date(today, calendar)
    first_exercise = calendar.advance(spot, int(trade["first_exercise_years"]), ql.Years)
    final_maturity = calendar.advance(spot, int(trade["final_maturity_years"]), ql.Years)
    fixed_schedule = _build_schedule(
        first_exercise,
        final_maturity,
        trade["payment_frequency_months"],
        calendar,
    )
    exercise_dates = [calendar.advance(date, -1, ql.Days) for date in list(fixed_schedule)[:-1]]
    if not exercise_dates:
        exercise_dates.append(calendar.advance(first_exercise, -1, ql.Days))
    return {
        "spot": spot,
        "first_exercise": first_exercise,
        "final_maturity": final_maturity,
        "fixed_schedule": fixed_schedule,
        "exercise_dates": exercise_dates,
    }


def bermudan_diagonal_calibration_pillars(
    portfolio_state=None,
    market_context=None,
    calibration_horizon_years=None,
):
    state, today, calendar, curve, _curve_handle = _resolve_market_context(
        portfolio_state,
        market_context,
    )
    spot = _spot_start_date(today, calendar)
    max_curve_date = curve.maxDate()
    pillars = []
    if calibration_horizon_years is None:
        horizon_years = int(state["trades"]["bermudan_swaption"]["final_maturity_years"])
    else:
        horizon_years = max(int(calibration_horizon_years), 1)

    common_labels = [
        label
        for label in ("1Y", "2Y", "3Y", "4Y", "5Y", "6Y", "7Y", "8Y", "9Y", "10Y", "12Y", "15Y", "20Y", "25Y")
        if label in SWAPTION_MATRIX_TENOR_LABELS and _years_from_label(label) <= horizon_years
    ]
    for label in common_labels:
        period = _period_from_label(label)
        exercise_date = calendar.advance(spot, period)
        maturity_date = calendar.advance(exercise_date, period)
        if maturity_date > max_curve_date:
            continue
        market_source = swaption_matrix_market_sources(state, label, label)
        pillars.append(
            {
                "label": f"{label} x {label}",
                "expiry_label": label,
                "swap_tenor_label": label,
                "exercise_date": exercise_date,
                "exercise_date_iso": exercise_date.ISO(),
                "maturity_date": maturity_date,
                "maturity_date_iso": maturity_date.ISO(),
                "normal_vol_bp": market_source["vol_bp"],
                "source_market_points": market_source["source_market_points"],
            }
        )

    return pillars


def build_bermudan_gsr_model(
    portfolio_state=None,
    market_context=None,
    calibration_horizon_years=None,
):
    state, today, calendar, curve, curve_handle = _resolve_market_context(
        portfolio_state,
        market_context,
    )
    calibration_pillars = bermudan_diagonal_calibration_pillars(
        state,
        market_context=(state, today, calendar, curve, curve_handle),
        calibration_horizon_years=calibration_horizon_years,
    )
    initial_sigma = _normal_vol_from_bp(BERMUDAN_INITIAL_SIGMA_BP)
    step_dates = [pillar["exercise_date"] for pillar in calibration_pillars]
    volatility_quotes = [
        ql.QuoteHandle(ql.SimpleQuote(initial_sigma))
        for _ in range(len(step_dates) + 1)
    ]
    reversion_quotes = [
        ql.QuoteHandle(ql.SimpleQuote(state["market"]["hw_mean_reversion"]))
    ]

    model = ql.Gsr(
        curve_handle,
        step_dates,
        volatility_quotes,
        reversion_quotes,
        curve.timeFromReference(curve.maxDate()),
    )
    engine = ql.Gaussian1dSwaptionEngine(
        model,
        BERMUDAN_GSR_INTEGRATION_POINTS,
        BERMUDAN_GSR_STDDEVS,
        True,
        False,
        curve_handle,
    )

    helpers = ql.BlackCalibrationHelperVector()
    calibration_rows = []
    for pillar in calibration_pillars:
        helper = ql.SwaptionHelper(
            _period_from_label(pillar["expiry_label"]),
            _period_from_label(pillar["swap_tenor_label"]),
            ql.QuoteHandle(ql.SimpleQuote(pillar["normal_vol_bp"] / 10000.0)),
            ql.Sofr(curve_handle),
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
        helper.setPricingEngine(engine)
        helpers.push_back(helper)
        calibration_rows.append(
            {
                "label": pillar["label"],
                "expiry_label": pillar["expiry_label"],
                "swap_tenor_label": pillar["swap_tenor_label"],
                "exercise_date_iso": pillar["exercise_date_iso"],
                "maturity_date_iso": pillar["maturity_date_iso"],
                "market_normal_vol_bp": pillar["normal_vol_bp"],
            }
        )

    if helpers.size() > 0:
        model.calibrateVolatilitiesIterative(
            helpers,
            ql.LevenbergMarquardt(),
            ql.EndCriteria(200, 50, 1e-8, 1e-8, 1e-8),
        )

    calibrated_sigmas = list(model.volatility())
    for index, row in enumerate(calibration_rows):
        row["model_value"] = helpers[index].modelValue()
        row["market_value"] = helpers[index].marketValue()
        row["calibration_error"] = helpers[index].calibrationError()
        row["segment_sigma_bp"] = calibrated_sigmas[index] * 10000.0

    sigma_rows = []
    interval_start = curve.referenceDate()
    for index, sigma in enumerate(calibrated_sigmas):
        interval_end = step_dates[index] if index < len(step_dates) else curve.maxDate()
        sigma_rows.append(
            {
                "segment": index + 1,
                "start_date_iso": interval_start.ISO(),
                "end_date_iso": interval_end.ISO(),
                "sigma_bp": sigma * 10000.0,
            }
        )
        interval_start = interval_end

    return {
        "model": model,
        "engine": engine,
        "calibration_rows": calibration_rows,
        "sigma_rows": sigma_rows,
        "mean_reversion": list(model.reversion())[0],
        "curve_max_date_iso": curve.maxDate().ISO(),
    }


def _create_bermudan_swaption(trade, today, calendar, curve_handle, pricing_engine):
    schedule_context = _bermudan_schedule_context(trade, today, calendar)
    underlying = _create_forward_swap(
        trade,
        schedule_context["first_exercise"],
        schedule_context["final_maturity"],
        curve_handle,
    )
    exercise = ql.BermudanExercise(schedule_context["exercise_dates"])
    swaption = ql.Swaption(underlying, exercise)
    swaption.setPricingEngine(pricing_engine)
    return swaption


def reprice_sofr_calibration_swaps(curve, sofr_rates, tenor_labels=None):
    normalized_quotes = _normalize_curve_quotes(list(sofr_rates))
    curve_handle = ql.YieldTermStructureHandle(curve)
    engine = ql.DiscountingSwapEngine(curve_handle)
    overnight_index = ql.Sofr(curve_handle)
    market_quotes = dict(zip(SOFR_CURVE_TENOR_LABELS[1:], normalized_quotes[1:]))
    active_tenor_labels = tuple(tenor_labels or SOFR_CURVE_TENOR_LABELS[1:])
    repriced_swaps = []

    for tenor_label in active_tenor_labels:
        fixed_rate = market_quotes[tenor_label]
        swap = ql.MakeOIS(
            _period_from_label(tenor_label),
            overnight_index,
            fixed_rate / 100.0,
            ql.Period(0, ql.Days),
        )
        swap.setPricingEngine(engine)
        repriced_swaps.append(
            {
                "Tenor": tenor_label,
                "Market Quote (%)": fixed_rate,
                "Fair Rate (%)": swap.fairRate() * 100.0,
                "NPV": swap.NPV(),
            }
        )

    return pd.DataFrame(repriced_swaps)


def build_bermudan_pricing_grid(portfolio_state=None, market_context=None, bermudan_pricing_engine=None):
    state, today, calendar, curve, curve_handle = _resolve_market_context(
        portfolio_state,
        market_context,
    )
    template_trade = state["trades"]["bermudan_swaption"]
    if bermudan_pricing_engine is None:
        bermudan_pricing_engine = build_bermudan_gsr_model(
            state,
            market_context=(state, today, calendar, curve, curve_handle),
            calibration_horizon_years=max(BERMUDAN_GRID_MATURITIES_YEARS),
        )["engine"]
    rows = []

    for noncall_years in BERMUDAN_GRID_NONCALL_YEARS:
        row = {"Non-call": f"{noncall_years}Y"}
        for maturity_years in BERMUDAN_GRID_MATURITIES_YEARS:
            if noncall_years >= maturity_years:
                row[f"{maturity_years}Y"] = None
                continue
            trade = dict(template_trade)
            trade["first_exercise_years"] = noncall_years
            trade["final_maturity_years"] = maturity_years
            row[f"{maturity_years}Y"] = _create_bermudan_swaption(
                trade,
                today,
                calendar,
                curve_handle,
                bermudan_pricing_engine,
            ).NPV()
        rows.append(row)

    return pd.DataFrame(rows)


def _trade_npv(trade_type, portfolio_state=None, market_context=None, bermudan_pricing_engine=None):
    state, today, calendar, curve, curve_handle = _resolve_market_context(
        portfolio_state,
        market_context,
    )
    trades = state["trades"]

    if trade_type == "swap":
        return _create_live_swap(trades["swap"], today, calendar, curve_handle).NPV()

    if trade_type == "european_swaption":
        european_matrix_vol_bp = lookup_swaption_normal_vol_bp(
            state,
            trades["european_swaption"]["expiry_years"],
            trades["european_swaption"]["swap_tenor_years"],
        )
        return _create_european_swaption(
            trades["european_swaption"],
            today,
            calendar,
            curve_handle,
            european_matrix_vol_bp,
        ).NPV()

    if trade_type in BERMUDAN_TRADE_KEYS:
        if bermudan_pricing_engine is None:
            bermudan_pricing_engine = build_bermudan_gsr_model(
                state,
                market_context=(state, today, calendar, curve, curve_handle),
                calibration_horizon_years=trades[trade_type]["final_maturity_years"],
            )["engine"]
        return _create_bermudan_swaption(
            trades[trade_type],
            today,
            calendar,
            curve_handle,
            bermudan_pricing_engine,
        ).NPV()

    if trade_type == "equity_cliquet":
        option, _dates, _maturity, _context = _create_equity_cliquet(
            state,
            market_context=(state, today, calendar, curve, curve_handle),
        )
        return option.NPV() * float(trades["equity_cliquet"]["quantity"])

    raise ValueError(f"Unsupported trade type: {trade_type}")


def _priced_trade_row(trade_type, portfolio_state=None, market_context=None, bermudan_pricing_engine=None):
    state, *_unused = _resolve_market_context(portfolio_state, market_context)
    market = state["market"]
    trade = state["trades"][trade_type]
    npv = _trade_npv(
        trade_type,
        state,
        market_context=market_context,
        bermudan_pricing_engine=bermudan_pricing_engine,
    )
    return {
        "TradeKey": trade_type,
        "Type": TRADE_TITLES[trade_type],
        "Structure": trade_structure_summary(trade_type, trade, market),
        "MTM": npv,
        "NPV": npv,
    }


def price_portfolio(portfolio_state=None, market_context=None, bermudan_pricing_engine=None):
    state, today, calendar, curve, curve_handle = _resolve_market_context(
        portfolio_state,
        market_context,
    )
    bermudan_pricing_engines = {}
    if bermudan_pricing_engine is not None:
        bermudan_pricing_engines["bermudan_swaption"] = bermudan_pricing_engine
    for trade_key in BERMUDAN_TRADE_KEYS:
        if trade_key in bermudan_pricing_engines:
            continue
        bermudan_pricing_engines[trade_key] = build_bermudan_gsr_model(
            state,
            market_context=(state, today, calendar, curve, curve_handle),
            calibration_horizon_years=state["trades"][trade_key]["final_maturity_years"],
        )["engine"]

    securities = [
        _priced_trade_row(
            trade_type,
            state,
            market_context=(state, today, calendar, curve, curve_handle),
            bermudan_pricing_engine=bermudan_pricing_engines.get(trade_type),
        )
        for trade_type in TRADE_SEQUENCE
    ]
    return pd.DataFrame(securities)


def _clean_sensitivity(value):
    return 0.0 if abs(value) <= SENSITIVITY_ZERO_TOLERANCE else float(value)


def trade_point_sensitivities(
    trade_type,
    portfolio_state=None,
    curve_bump_bp=CURVE_POINT_BUMP_BP,
    vol_bump_bp=VOL_POINT_BUMP_BP,
    mean_reversion_bump=0.001,
):
    if trade_type not in TRADE_SEQUENCE:
        raise ValueError(f"Unsupported trade type: {trade_type}")

    state, today, calendar, curve, curve_handle = _market_context(portfolio_state)
    base_market_context = (state, today, calendar, curve, curve_handle)
    base_bermudan_engine = None
    if trade_type in BERMUDAN_TRADE_KEYS:
        base_bermudan_engine = build_bermudan_gsr_model(
            state,
            market_context=base_market_context,
            calibration_horizon_years=state["trades"][trade_type]["final_maturity_years"],
        )["engine"]

    base_npv = _trade_npv(
        trade_type,
        state,
        market_context=base_market_context,
        bermudan_pricing_engine=base_bermudan_engine,
    )

    curve_rows = []
    for index, label in enumerate(SOFR_CURVE_TENOR_LABELS):
        shocked_state = copy.deepcopy(state)
        shocked_state["market"]["curve_quotes_pct"][index] += float(curve_bump_bp) / 100.0
        shocked_state, shocked_today, shocked_calendar, shocked_curve, shocked_curve_handle = _market_context(
            shocked_state
        )
        shocked_market_context = (
            shocked_state,
            shocked_today,
            shocked_calendar,
            shocked_curve,
            shocked_curve_handle,
        )
        shocked_bermudan_engine = None
        if trade_type in BERMUDAN_TRADE_KEYS:
            shocked_bermudan_engine = build_bermudan_gsr_model(
                shocked_state,
                market_context=shocked_market_context,
                calibration_horizon_years=shocked_state["trades"][trade_type]["final_maturity_years"],
            )["engine"]
        shocked_npv = _trade_npv(
            trade_type,
            shocked_state,
            market_context=shocked_market_context,
            bermudan_pricing_engine=shocked_bermudan_engine,
        )
        curve_rows.append(
            {
                "label": label,
                "base_quote_pct": state["market"]["curve_quotes_pct"][index],
                "bumped_quote_pct": shocked_state["market"]["curve_quotes_pct"][index],
                "delta_npv": _clean_sensitivity(shocked_npv - base_npv),
            }
        )

    sensitive_matrix_points = set()
    if trade_type == "european_swaption":
        trade = state["trades"]["european_swaption"]
        sensitive_matrix_points = set(
            swaption_matrix_market_sources(
                state,
                trade["expiry_years"],
                trade["swap_tenor_years"],
            )["source_market_points"]
        )
    elif trade_type in BERMUDAN_TRADE_KEYS:
        sensitive_matrix_points = {
            point
            for pillar in bermudan_diagonal_calibration_pillars(
                state,
                market_context=base_market_context,
                calibration_horizon_years=state["trades"][trade_type]["final_maturity_years"],
            )
            for point in pillar["source_market_points"]
        }

    vega_matrix_rows = []
    for expiry_index, expiry_label in enumerate(SWAPTION_MATRIX_EXPIRY_LABELS):
        row = {"expiry_label": expiry_label, "cells": []}
        for tenor_index, tenor_label in enumerate(SWAPTION_MATRIX_TENOR_LABELS):
            delta_npv = 0.0
            if (expiry_label, tenor_label) in sensitive_matrix_points:
                shocked_state = copy.deepcopy(state)
                shocked_state["market"]["swaption_vol_matrix_bp"][expiry_index][tenor_index] += float(
                    vol_bump_bp
                )
                shocked_market_context = (shocked_state, today, calendar, curve, curve_handle)
                shocked_bermudan_engine = None
                if trade_type in BERMUDAN_TRADE_KEYS:
                    shocked_bermudan_engine = build_bermudan_gsr_model(
                        shocked_state,
                        market_context=shocked_market_context,
                        calibration_horizon_years=shocked_state["trades"][trade_type]["final_maturity_years"],
                    )["engine"]
                shocked_npv = _trade_npv(
                    trade_type,
                    shocked_state,
                    market_context=shocked_market_context,
                    bermudan_pricing_engine=shocked_bermudan_engine,
                )
                delta_npv = _clean_sensitivity(shocked_npv - base_npv)
            row["cells"].append(
                {
                    "label": f"{expiry_label} x {tenor_label}",
                    "delta_npv": delta_npv,
                }
            )
        vega_matrix_rows.append(row)

    market_rows = []
    if trade_type == "equity_cliquet":
        for label, field_name, bump_size, unit_label in CLIQUET_MARKET_BUMP_DEFINITIONS:
            shocked_state = copy.deepcopy(state)
            if field_name == "equity_spot":
                shocked_state["market"][field_name] = max(
                    shocked_state["market"][field_name] * (1.0 + bump_size),
                    1.0,
                )
            else:
                shocked_state["market"][field_name] = max(
                    shocked_state["market"][field_name] + bump_size,
                    0.0,
                )
            shocked_npv = _trade_npv(
                trade_type,
                shocked_state,
                market_context=_market_context(shocked_state),
            )
            market_rows.append(
                {
                    "label": label,
                    "unit": unit_label,
                    "base_value": state["market"][field_name],
                    "bumped_value": shocked_state["market"][field_name],
                    "delta_npv": _clean_sensitivity(shocked_npv - base_npv),
                }
            )

    model_parameter_delta_npv = 0.0
    if trade_type in BERMUDAN_TRADE_KEYS:
        shocked_state = copy.deepcopy(state)
        shocked_state["market"]["hw_mean_reversion"] += float(mean_reversion_bump)
        shocked_market_context = (shocked_state, today, calendar, curve, curve_handle)
        shocked_bermudan_engine = build_bermudan_gsr_model(
            shocked_state,
            market_context=shocked_market_context,
            calibration_horizon_years=shocked_state["trades"][trade_type]["final_maturity_years"],
        )["engine"]
        callable_seed_npv = _trade_npv(
            trade_type,
            shocked_state,
            market_context=shocked_market_context,
            bermudan_pricing_engine=shocked_bermudan_engine,
        )
        model_parameter_delta_npv = _clean_sensitivity(callable_seed_npv - base_npv)

    return {
        "base_npv": base_npv,
        "curve_bump_bp": float(curve_bump_bp),
        "vol_bump_bp": float(vol_bump_bp),
        "curve_rows": curve_rows,
        "vega_matrix_headers": list(SWAPTION_MATRIX_TENOR_LABELS),
        "vega_matrix_rows": vega_matrix_rows,
        "market_rows": market_rows,
        "model_parameter_row": {
            "label": "Hull-White mean reversion",
            "base_value": state["market"]["hw_mean_reversion"],
            "bumped_value": state["market"]["hw_mean_reversion"] + float(mean_reversion_bump),
            "delta_npv": model_parameter_delta_npv,
        },
    }
