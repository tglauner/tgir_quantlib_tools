from __future__ import annotations

from datetime import datetime
import math
import random

import QuantLib as ql
from flask import current_app, session, url_for

from portfolio import (
    BERMUDAN_GRID_MATURITIES_YEARS,
    DEFAULT_MARKET_DATA_JSON_PATH,
    DEFAULT_TRADE_DATA_JSON_PATH,
    CLIQUET_SCENARIO_VOL_SHOCKS_PCT,
    IR_FREQUENCY_MONTH_OPTIONS,
    SOFR_CURVE_TENOR_LABELS,
    SOFR_FORWARD_HORIZON_YEARS,
    SWAPTION_MATRIX_EXPIRY_LABELS,
    SWAPTION_MATRIX_TENOR_LABELS,
    TRADE_TITLES,
    bermudan_diagonal_calibration_pillars,
    build_bermudan_pricing_grid,
    build_bermudan_gsr_model,
    build_sofr_curve,
    cliquet_analytics,
    curve_zero_rate_points,
    daily_one_day_forward_points,
    default_portfolio_state,
    frequency_label,
    lookup_swaption_normal_vol_bp,
    normalize_portfolio_state,
    price_portfolio,
    reprice_sofr_calibration_swaps,
    trade_card_summary,
    valuation_date,
)


REALTIME_MOVE_MIN_BP = 1.0
REALTIME_MOVE_MAX_BP = 2.0

MATRIX_SOURCE_NOTE = (
    "ATM normal-vol pillars are loaded from the workbook surface used for the QL comparison: "
    "short expiries from 1M onward, annual expiries through 10Y, then 12Y, 15Y, 20Y, and 25Y, "
    "against underlying swap tenors from 1Y to 30Y. The on-screen matrix matches the workbook axes "
    "exactly. When the Bermudan calibration needs a 3Y expiry, the model linearly interpolates it "
    "between the 2Y and 4Y workbook rows."
)

ZERO_RATE_NOTE = (
    "This graph uses continuous-compounded spot zero rates on an Actual/365 basis, derived from "
    "the QuantLib discount curve at the actual helper node dates: df(x) = exp(-z * x / 365)."
)

FORWARD_RATE_NOTE = (
    "The strip below shows daily one-day simple forward rates over the next ten years from the "
    "same QuantLib SOFR term structure using forwardRate(start, start + 1D, Actual360, Simple)."
)

EQUITY_MARKET_NOTE = (
    "The SPX cliquet uses the same SOFR curve for discounting, plus editable SPX spot, flat "
    "dividend yield, and flat Black volatility inputs. QuantLib prices the strip as a "
    "CliquetOption with an AnalyticCliquetEngine."
)

IR_FREQUENCY_OPTIONS = list(IR_FREQUENCY_MONTH_OPTIONS)

BERMUDAN_FORM_FIELDS = [
    {
        "name": "direction",
        "label": "Option style",
        "type": "select",
        "options": [("payer", "Payer"), ("receiver", "Receiver")],
    },
    {"name": "notional", "label": "Notional", "type": "number", "step": "100000", "format": "grouped_decimal"},
    {"name": "strike_pct", "label": "Strike (%)", "type": "number", "step": "0.01"},
    {
        "name": "first_exercise_years",
        "label": "First exercise (years)",
        "type": "number",
        "step": "1",
        "min": "1",
        "max": "9",
    },
    {
        "name": "final_maturity_years",
        "label": "Final maturity (years)",
        "type": "number",
        "step": "1",
        "min": "2",
        "max": "10",
    },
    {
        "name": "payment_frequency_months",
        "label": "Payment frequency",
        "type": "select",
        "options": IR_FREQUENCY_OPTIONS,
    },
    {
        "name": "reset_frequency_months",
        "label": "Reset frequency",
        "type": "select",
        "options": IR_FREQUENCY_OPTIONS,
    },
]

TRADE_FORM_DEFINITIONS = {
    "swap": {
        "title": "Interest Rate Swap",
        "description": (
            "Spot-starting fixed versus daily compounded SOFR OIS. Keep the market surface clean "
            "on the dashboard and edit the actual deal conventions here."
        ),
        "fields": [
            {
                "name": "direction",
                "label": "Fixed side",
                "type": "select",
                "options": [("payer", "Pay fixed"), ("receiver", "Receive fixed")],
            },
            {"name": "notional", "label": "Notional", "type": "number", "step": "100000", "format": "grouped_decimal"},
            {
                "name": "fixed_rate_pct",
                "label": "Fixed rate (%)",
                "type": "number",
                "step": "0.01",
            },
            {
                "name": "tenor_years",
                "label": "Maturity (years)",
                "type": "number",
                "step": "1",
                "min": "1",
                "max": "30",
            },
            {
                "name": "payment_frequency_months",
                "label": "Payment frequency",
                "type": "select",
                "options": IR_FREQUENCY_OPTIONS,
            },
            {
                "name": "reset_frequency_months",
                "label": "Reset frequency",
                "type": "select",
                "options": IR_FREQUENCY_OPTIONS,
            },
        ],
    },
    "european_swaption": {
        "title": "European Swaption",
        "description": (
            "Single exercise into a forward-starting SOFR OIS. Priced off the editable ATM "
            "normal-vol matrix at the selected expiry and swap tenor."
        ),
        "fields": [
            {
                "name": "direction",
                "label": "Option style",
                "type": "select",
                "options": [("payer", "Payer"), ("receiver", "Receiver")],
            },
            {"name": "notional", "label": "Notional", "type": "number", "step": "100000", "format": "grouped_decimal"},
            {"name": "strike_pct", "label": "Strike (%)", "type": "number", "step": "0.01"},
            {
                "name": "expiry_years",
                "label": "Expiry (years)",
                "type": "number",
                "step": "1",
                "min": "1",
                "max": "10",
            },
            {
                "name": "swap_tenor_years",
                "label": "Underlying tenor (years)",
                "type": "number",
                "step": "1",
                "min": "1",
                "max": "10",
            },
            {
                "name": "payment_frequency_months",
                "label": "Payment frequency",
                "type": "select",
                "options": IR_FREQUENCY_OPTIONS,
            },
            {
                "name": "reset_frequency_months",
                "label": "Reset frequency",
                "type": "select",
                "options": IR_FREQUENCY_OPTIONS,
            },
        ],
    },
    "bermudan_swaption": {
        "title": "Bermudan Swaption",
        "description": (
            "Multi-exercise callable structure into a fixed versus daily compounded SOFR OIS. "
            "The trade is booked off a fixed final maturity, with exercise opportunities on each "
            "payment date from first exercise up to the period before maturity. Pricing uses a "
            "time-dependent Gaussian short-rate model calibrated to the feasible diagonal of the "
            "ATM normal-vol matrix with user-controlled Hull-White mean reversion."
        ),
        "fields": BERMUDAN_FORM_FIELDS,
    },
    "bermudan_swaption_2": {
        "title": "Bermudan Swaption 2",
        "description": (
            "Workbook benchmark trade matching the QL.xlsx comparison setup. Use this deal to "
            "compare model marks and risk against the spreadsheet reference while keeping the "
            "same market data and valuation date as the rest of the workstation."
        ),
        "fields": BERMUDAN_FORM_FIELDS,
    },
    "equity_cliquet": {
        "title": "Equity Cliquet",
        "description": (
            "SPX forward-start cliquet strip priced with QuantLib's analytic cliquet engine. "
            "Each reset starts a new percentage-strike option on the S&P 500 index."
        ),
        "fields": [
            {
                "name": "option_type",
                "label": "Option style",
                "type": "select",
                "options": [("call", "Call"), ("put", "Put")],
            },
            {"name": "quantity", "label": "Index units", "type": "number", "step": "1"},
            {
                "name": "moneyness_pct",
                "label": "Moneyness (%)",
                "type": "number",
                "step": "0.1",
                "min": "1",
                "max": "200",
            },
            {
                "name": "maturity_months",
                "label": "Maturity (months)",
                "type": "number",
                "step": "1",
                "min": "1",
                "max": "36",
            },
            {
                "name": "reset_frequency_months",
                "label": "Reset frequency (months)",
                "type": "number",
                "step": "1",
                "min": "1",
                "max": "12",
            },
        ],
    },
}


def money_filter(value):
    return f"${value:,.2f}"


def signed_money_filter(value):
    return f"${value:,.2f}" if value >= 0 else f"-${abs(value):,.2f}"


def pct_filter(value):
    return f"{value:.2f}%"


def sign_class_filter(value):
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "flat"


def register_template_filters(app) -> None:
    app.add_template_filter(money_filter, "money")
    app.add_template_filter(signed_money_filter, "signed_money")
    app.add_template_filter(pct_filter, "pct")
    app.add_template_filter(sign_class_filter, "sign_class")


def get_portfolio_state():
    stored = session.get(current_app.config["SESSION_STATE_KEY"])
    if stored is None:
        state = default_portfolio_state()
        session[current_app.config["SESSION_STATE_KEY"]] = state
        return state
    return normalize_portfolio_state(stored)


def save_portfolio_state(state) -> None:
    session[current_app.config["SESSION_STATE_KEY"]] = normalize_portfolio_state(state)
    session.modified = True


def _clean_numeric_text(value):
    if value is None:
        return value
    return str(value).replace(",", "").strip()


def parse_float(form, name, default):
    try:
        return float(_clean_numeric_text(form.get(name, default)))
    except (TypeError, ValueError):
        return default


def parse_int(form, name, default):
    try:
        return int(float(_clean_numeric_text(form.get(name, default))))
    except (TypeError, ValueError):
        return default


def clamp_int(value, minimum, maximum):
    return max(minimum, min(int(value), maximum))


def curve_inputs(state):
    return [
        {"label": label, "name": f"rate{index}", "value": state["market"]["curve_quotes_pct"][index]}
        for index, label in enumerate(SOFR_CURVE_TENOR_LABELS)
    ]


def valuation_date_input(state):
    return {"label": "Valuation date", "name": "valuation_date_iso", "value": state["valuation_date_iso"]}


def equity_market_inputs(state):
    return [
        {"label": "SPX spot", "name": "equity_spot", "value": state["market"]["equity_spot"], "step": "0.1"},
        {
            "label": "Dividend yield (%)",
            "name": "equity_dividend_yield_pct",
            "value": state["market"]["equity_dividend_yield_pct"],
            "step": "0.01",
        },
        {
            "label": "Flat vol (%)",
            "name": "equity_volatility_pct",
            "value": state["market"]["equity_volatility_pct"],
            "step": "0.01",
        },
    ]


def swaption_matrix_headers():
    return list(SWAPTION_MATRIX_TENOR_LABELS)


def swaption_matrix_rows(state):
    matrix = state["market"]["swaption_vol_matrix_bp"]
    rows = []
    for expiry_index, expiry_label in enumerate(SWAPTION_MATRIX_EXPIRY_LABELS):
        rows.append(
            {
                "expiry_label": expiry_label,
                "cells": [
                    {
                        "name": f"vol_{expiry_label}_{tenor_label}",
                        "value": matrix[expiry_index][tenor_index],
                    }
                    for tenor_index, tenor_label in enumerate(SWAPTION_MATRIX_TENOR_LABELS)
                ],
            }
        )
    return rows


def _empty_line_chart():
    return {
        "width": 500,
        "height": 220,
        "x_ticks": [],
        "y_ticks": [],
        "markers": [],
        "polyline": "",
        "area": "",
    }


def _sample_indexes(item_count, target_count):
    if item_count <= 0:
        return []
    if item_count <= target_count:
        return list(range(item_count))

    last_index = item_count - 1
    indexes = {
        round(last_index * step / (target_count - 1))
        for step in range(target_count)
    }
    indexes.add(last_index)
    return sorted(indexes)


def _line_chart(
    points,
    *,
    label_key="label",
    value_key="rate_pct",
    marker_indexes=None,
    x_tick_indexes=None,
    width=500,
):
    if not points:
        return _empty_line_chart()

    height = 220
    padding_left = 36
    padding_right = 18
    padding_top = 24
    padding_bottom = 34
    plot_width = width - padding_left - padding_right
    plot_height = height - padding_top - padding_bottom

    values = [point[value_key] for point in points]
    min_value = min(values)
    max_value = max(values)
    buffer = max((max_value - min_value) * 0.25, 0.12)
    y_min = min_value - buffer
    y_max = max_value + buffer

    denominator = max(len(points) - 1, 1)
    chart_points = []
    for index, point in enumerate(points):
        x_position = padding_left + index * plot_width / denominator
        ratio = 0.5 if y_max == y_min else (point[value_key] - y_min) / (y_max - y_min)
        y_position = padding_top + (1 - ratio) * plot_height
        chart_points.append(
            {
                "label": point[label_key],
                "value": point[value_key],
                "x": round(x_position, 2),
                "y": round(y_position, 2),
            }
        )

    polyline = " ".join(f"{point['x']},{point['y']}" for point in chart_points)
    area = (
        f"{padding_left},{height - padding_bottom} "
        + polyline
        + f" {padding_left + plot_width},{height - padding_bottom}"
    )

    y_ticks = []
    for step in range(4):
        tick_value = y_min + (y_max - y_min) * step / 3
        tick_ratio = 0.0 if y_max == y_min else (tick_value - y_min) / (y_max - y_min)
        tick_y = padding_top + (1 - tick_ratio) * plot_height
        y_ticks.append({"value": tick_value, "y": round(tick_y, 2)})

    if marker_indexes is None:
        marker_indexes = _sample_indexes(len(chart_points), min(len(chart_points), 8))
    if x_tick_indexes is None:
        x_tick_indexes = marker_indexes

    return {
        "width": width,
        "height": height,
        "markers": [chart_points[index] for index in marker_indexes],
        "x_ticks": [{"label": chart_points[index]["label"], "x": chart_points[index]["x"]} for index in x_tick_indexes],
        "y_ticks": y_ticks,
        "polyline": polyline,
        "area": area,
    }


def _curve_analytics(state):
    today = valuation_date(state)
    ql.Settings.instance().evaluationDate = today
    calendar = ql.UnitedStates(ql.UnitedStates.Settlement)
    curve = build_sofr_curve(today, state["market"]["curve_quotes_pct"])
    zero_points = curve_zero_rate_points(curve)
    forward_points = daily_one_day_forward_points(curve)
    bermudan_pillars = bermudan_diagonal_calibration_pillars(
        state,
        market_context=(state, today, calendar, curve, ql.YieldTermStructureHandle(curve)),
    )
    return zero_points, forward_points, bermudan_pillars


def _forward_summary(forward_points):
    if not forward_points:
        return {
            "start_pct": 0.0,
            "three_month_pct": 0.0,
            "six_month_pct": 0.0,
            "one_year_pct": 0.0,
        }

    reference_date = ql.DateParser.parseISO(forward_points[0]["start_date_iso"])
    point_by_iso = {point["start_date_iso"]: point for point in forward_points}

    def point_rate(target_date, fallback_index):
        point = point_by_iso.get(target_date.ISO())
        if point is None:
            point = forward_points[min(fallback_index, len(forward_points) - 1)]
        return point["rate_pct"]

    return {
        "start_pct": forward_points[0]["rate_pct"],
        "three_month_pct": point_rate(reference_date + ql.Period(3, ql.Months), 91),
        "six_month_pct": point_rate(reference_date + ql.Period(6, ql.Months), 183),
        "one_year_pct": point_rate(reference_date + ql.Period(1, ql.Years), 365),
    }


def _zero_rate_chart(zero_points):
    return _line_chart(
        zero_points,
        label_key="label",
        value_key="rate_pct",
        marker_indexes=list(range(len(zero_points))),
        x_tick_indexes=_sample_indexes(len(zero_points), min(len(zero_points), 8)),
    )


def _forward_rate_chart(forward_points):
    tick_indexes = []
    if forward_points:
        reference_date = ql.DateParser.parseISO(forward_points[0]["start_date_iso"])
        point_index_by_iso = {
            point["start_date_iso"]: index for index, point in enumerate(forward_points)
        }
        for year in range(SOFR_FORWARD_HORIZON_YEARS + 1):
            tick_date = reference_date + ql.Period(year, ql.Years)
            point_index = point_index_by_iso.get(tick_date.ISO())
            if point_index is not None:
                tick_indexes.append(point_index)

    return _line_chart(
        forward_points,
        label_key="axis_label",
        value_key="rate_pct",
        marker_indexes=tick_indexes,
        x_tick_indexes=tick_indexes,
        width=620,
    )


def market_snapshot(state, zero_points, forward_points, bermudan_pillars):
    zero_rates = [point["rate_pct"] for point in zero_points]
    zero_steepness_bp = (zero_rates[-1] - zero_rates[0]) * 100.0 if len(zero_rates) >= 2 else 0.0
    last_pillar = bermudan_pillars[-1]["label"] if bermudan_pillars else "-"

    return {
        "zero_rate_rows": [
            {
                "label": point["label"],
                "date_iso": point["date_iso"],
                "short_date": point["short_date"],
                "rate_pct": point["rate_pct"],
            }
            for point in zero_points
        ],
        "valuation_date_iso": state["valuation_date_iso"],
        "zero_rate_steepness_bp": zero_steepness_bp,
        "atm_5y5y_bp": lookup_swaption_normal_vol_bp(state, 5, 5),
        "hw_mean_reversion": float(state["market"]["hw_mean_reversion"]),
        "bermudan_calibration_helper_count": len(bermudan_pillars),
        "bermudan_last_diagonal_label": last_pillar,
        "forward_rate_summary": _forward_summary(forward_points),
        "equity_spot": float(state["market"]["equity_spot"]),
        "equity_dividend_yield_pct": float(state["market"]["equity_dividend_yield_pct"]),
        "equity_volatility_pct": float(state["market"]["equity_volatility_pct"]),
    }


def prepare_trade_form(definition, trade):
    fields = []
    for field in definition["fields"]:
        field_context = dict(field)
        raw_value = trade[field["name"]]
        field_context["value"] = raw_value
        field_context["input_type"] = field["type"]
        field_context["inputmode"] = None
        if field.get("format") == "grouped_decimal":
            field_context["input_type"] = "text"
            field_context["inputmode"] = "decimal"
            field_context["value"] = f"{float(raw_value):,.2f}"
        if field["type"] == "select":
            field_context["options"] = [
                {
                    "value": option_value,
                    "label": option_label,
                    "selected": trade[field["name"]] == option_value,
                }
                for option_value, option_label in field["options"]
            ]
        fields.append(field_context)
    return fields


def trade_detail_rows(trade_type, trade):
    if trade_type == "swap":
        return [
            {"label": "Payment frequency", "value": frequency_label(trade["payment_frequency_months"])},
            {"label": "Reset frequency", "value": frequency_label(trade["reset_frequency_months"])},
        ]

    if trade_type == "european_swaption":
        return [
            {"label": "Expiry", "value": f"{trade['expiry_years']}Y"},
            {"label": "Underlying tenor", "value": f"{trade['swap_tenor_years']}Y"},
            {"label": "Payment frequency", "value": frequency_label(trade["payment_frequency_months"])},
            {"label": "Reset frequency", "value": frequency_label(trade["reset_frequency_months"])},
        ]

    if trade_type in {"bermudan_swaption", "bermudan_swaption_2"}:
        return [
            {"label": "First exercise", "value": f"{trade['first_exercise_years']}Y"},
            {"label": "Final maturity", "value": f"{trade['final_maturity_years']}Y"},
            {"label": "Payment frequency", "value": frequency_label(trade["payment_frequency_months"])},
            {"label": "Reset frequency", "value": frequency_label(trade["reset_frequency_months"])},
        ]

    return [
        {"label": "Reset frequency", "value": f"{trade['reset_frequency_months']}M"},
    ]


def update_market_state(state, form) -> None:
    state["valuation_date_iso"] = form.get("valuation_date_iso", state["valuation_date_iso"]) or state["valuation_date_iso"]
    state["market"]["curve_quotes_pct"] = [
        parse_float(form, f"rate{index}", state["market"]["curve_quotes_pct"][index])
        for index in range(len(SOFR_CURVE_TENOR_LABELS))
    ]
    state["market"]["hw_mean_reversion"] = max(
        parse_float(form, "hw_mean_reversion", state["market"]["hw_mean_reversion"]),
        0.0,
    )

    current_matrix = state["market"]["swaption_vol_matrix_bp"]
    updated_matrix = []
    for expiry_index, expiry_label in enumerate(SWAPTION_MATRIX_EXPIRY_LABELS):
        row = []
        for tenor_index, tenor_label in enumerate(SWAPTION_MATRIX_TENOR_LABELS):
            row.append(
                max(
                    parse_float(
                        form,
                        f"vol_{expiry_label}_{tenor_label}",
                        current_matrix[expiry_index][tenor_index],
                    ),
                    0.0,
                )
            )
        updated_matrix.append(row)
    state["market"]["swaption_vol_matrix_bp"] = updated_matrix
    state["market"]["equity_spot"] = max(
        parse_float(form, "equity_spot", state["market"]["equity_spot"]),
        1.0,
    )
    state["market"]["equity_dividend_yield_pct"] = parse_float(
        form,
        "equity_dividend_yield_pct",
        state["market"]["equity_dividend_yield_pct"],
    )
    state["market"]["equity_volatility_pct"] = max(
        parse_float(form, "equity_volatility_pct", state["market"]["equity_volatility_pct"]),
        0.0,
    )


def update_trade_state(state, trade_type, form) -> None:
    trade = state["trades"][trade_type]
    if trade_type == "equity_cliquet":
        option_type = form.get("option_type", trade["option_type"])
        trade["option_type"] = option_type if option_type in {"call", "put"} else trade["option_type"]
        trade["quantity"] = max(parse_float(form, "quantity", trade["quantity"]), 0.01)
        trade["moneyness_pct"] = max(parse_float(form, "moneyness_pct", trade["moneyness_pct"]), 0.01)
        trade["maturity_months"] = clamp_int(
            parse_int(form, "maturity_months", trade["maturity_months"]),
            1,
            36,
        )
        trade["reset_frequency_months"] = clamp_int(
            parse_int(form, "reset_frequency_months", trade["reset_frequency_months"]),
            1,
            12,
        )
        if trade["reset_frequency_months"] > trade["maturity_months"]:
            trade["reset_frequency_months"] = trade["maturity_months"]
        return

    direction = form.get("direction", trade["direction"])
    trade["direction"] = direction if direction in {"payer", "receiver"} else trade["direction"]
    trade["notional"] = max(parse_float(form, "notional", trade["notional"]), 1.0)
    trade["payment_frequency_months"] = parse_int(
        form,
        "payment_frequency_months",
        trade.get("payment_frequency_months", 12),
    )
    trade["reset_frequency_months"] = parse_int(
        form,
        "reset_frequency_months",
        trade.get("reset_frequency_months", 12),
    )

    if trade_type == "swap":
        trade["fixed_rate_pct"] = parse_float(form, "fixed_rate_pct", trade["fixed_rate_pct"])
        trade["tenor_years"] = clamp_int(parse_int(form, "tenor_years", trade["tenor_years"]), 1, 30)
        return

    trade["strike_pct"] = parse_float(form, "strike_pct", trade["strike_pct"])

    if trade_type == "european_swaption":
        trade["swap_tenor_years"] = clamp_int(
            parse_int(form, "swap_tenor_years", trade["swap_tenor_years"]),
            1,
            10,
        )
        trade["expiry_years"] = clamp_int(parse_int(form, "expiry_years", trade["expiry_years"]), 1, 10)
        return

    trade["first_exercise_years"] = clamp_int(
        parse_int(form, "first_exercise_years", trade["first_exercise_years"]),
        1,
        9,
    )
    trade["final_maturity_years"] = clamp_int(
        parse_int(form, "final_maturity_years", trade["final_maturity_years"]),
        trade["first_exercise_years"] + 1,
        10,
    )


def pricing_tables(state):
    portfolio_rows = []
    calibration_rows = []
    bermudan_grid_rows = []
    pricing_error = None

    try:
        state, today, calendar, curve, curve_handle = (
            normalize_portfolio_state(state),
            valuation_date(state),
            ql.UnitedStates(ql.UnitedStates.Settlement),
            None,
            None,
        )
        ql.Settings.instance().evaluationDate = today
        curve = build_sofr_curve(today, state["market"]["curve_quotes_pct"])
        curve_handle = ql.YieldTermStructureHandle(curve)
        market_context = (state, today, calendar, curve, curve_handle)
        bermudan_engine = build_bermudan_gsr_model(
            state,
            market_context=market_context,
        )["engine"]
        portfolio_rows = price_portfolio(
            state,
            market_context=market_context,
            bermudan_pricing_engine=bermudan_engine,
        ).to_dict("records")
        calibration_rows = reprice_sofr_calibration_swaps(
            curve,
            state["market"]["curve_quotes_pct"],
        ).to_dict("records")
        bermudan_grid_rows = build_bermudan_pricing_grid(
            state,
            market_context=market_context,
        ).to_dict("records")
    except Exception as exc:
        pricing_error = str(exc)

    return portfolio_rows, calibration_rows, bermudan_grid_rows, pricing_error


def _json_safe(value):
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def enrich_portfolio_rows(portfolio_rows):
    enriched_rows = []
    for row in portfolio_rows:
        trade_key = row["TradeKey"]
        enriched_rows.append(
            {
                **row,
                "EditURL": url_for("workbench.edit_trade", trade_type=trade_key),
                "EditLabel": f"Edit {TRADE_TITLES[trade_key]}",
            }
        )
    return enriched_rows


def portfolio_marks(portfolio_rows):
    if not portfolio_rows:
        return {
            "total_npv": 0.0,
            "total_mtm": 0.0,
            "gross_mtm": 0.0,
            "best_trade": {"type": "-", "mtm": 0.0},
            "worst_trade": {"type": "-", "mtm": 0.0},
        }

    total_mtm = sum(row["MTM"] for row in portfolio_rows)
    best_trade = max(portfolio_rows, key=lambda row: row["MTM"])
    worst_trade = min(portfolio_rows, key=lambda row: row["MTM"])
    return {
        "total_npv": sum(row["NPV"] for row in portfolio_rows),
        "total_mtm": total_mtm,
        "gross_mtm": sum(abs(row["MTM"]) for row in portfolio_rows),
        "best_trade": {"type": best_trade["Type"], "mtm": best_trade["MTM"]},
        "worst_trade": {"type": worst_trade["Type"], "mtm": worst_trade["MTM"]},
    }


def dynamic_dashboard_payload(state):
    portfolio_rows, calibration_rows, bermudan_grid_rows, pricing_error = pricing_tables(state)

    analytics_error = None
    zero_points = []
    forward_points = []
    bermudan_pillars = []
    try:
        zero_points, forward_points, bermudan_pillars = _curve_analytics(state)
    except Exception as exc:
        analytics_error = str(exc)

    return _json_safe(
        {
        "portfolio_rows": portfolio_rows,
        "blotter_rows": enrich_portfolio_rows(portfolio_rows),
        "calibration_rows": calibration_rows,
        "bermudan_grid_rows": bermudan_grid_rows,
        "curve_inputs": curve_inputs(state),
        "zero_rate_chart": _zero_rate_chart(zero_points),
        "forward_rate_chart": _forward_rate_chart(forward_points),
        "market_snapshot": market_snapshot(state, zero_points, forward_points, bermudan_pillars),
        "portfolio_marks": portfolio_marks(portfolio_rows),
        "pricing_error": pricing_error or analytics_error,
        "last_update_label": datetime.now().strftime("%H:%M:%S"),
        }
    )


def build_dashboard_context(state):
    payload = dynamic_dashboard_payload(state)
    payload.update(
        {
            "swaption_matrix_headers": swaption_matrix_headers(),
            "swaption_matrix_rows": swaption_matrix_rows(state),
            "valuation_date_input": valuation_date_input(state),
            "equity_market_inputs": equity_market_inputs(state),
            "bermudan_grid_headers": [f"{year}Y" for year in BERMUDAN_GRID_MATURITIES_YEARS],
            "normal_vol_note": (
                "European swaptions read ATM normal vols from the editable matrix. "
                "Bermudans calibrate the time-dependent sigma term structure to the feasible diagonal "
                "of that same matrix while holding the user-specified Hull-White mean reversion fixed."
            ),
            "matrix_source_note": MATRIX_SOURCE_NOTE,
            "zero_rate_note": ZERO_RATE_NOTE,
            "forward_rate_note": FORWARD_RATE_NOTE,
            "equity_market_note": EQUITY_MARKET_NOTE,
            "quantlib_data_model_url": url_for("workbench.quantlib_data_model"),
            "curve_debug_csv_url": url_for("workbench.curve_debug_download"),
            "curve_debug_csv_repo_path": current_app.config["CURVE_DEBUG_CSV_PATH"],
            "default_market_data_json_path": str(DEFAULT_MARKET_DATA_JSON_PATH.relative_to(DEFAULT_MARKET_DATA_JSON_PATH.parent.parent)),
            "default_trade_data_json_path": str(DEFAULT_TRADE_DATA_JSON_PATH.relative_to(DEFAULT_TRADE_DATA_JSON_PATH.parent.parent)),
            "defaults_note": "Panels show the current session market state. Reset demo reloads the JSON defaults.",
        }
    )
    return payload


def build_realtime_payload(state):
    payload = dynamic_dashboard_payload(state)
    payload["bermudan_grid_headers"] = [f"{year}Y" for year in BERMUDAN_GRID_MATURITIES_YEARS]
    return payload


def build_trade_editor_context(state, trade_type):
    definition = TRADE_FORM_DEFINITIONS[trade_type]
    trade = state["trades"][trade_type]
    headline, detail = trade_card_summary(trade_type, trade, state["market"])
    selected_matrix_vol_bp = None
    trade_page_error = None
    cliquet_context = None
    if trade_type == "european_swaption":
        selected_matrix_vol_bp = lookup_swaption_normal_vol_bp(
            state,
            trade["expiry_years"],
            trade["swap_tenor_years"],
        )
    elif trade_type == "equity_cliquet":
        try:
            cliquet_context = cliquet_analytics(state)
        except Exception as exc:
            trade_page_error = str(exc)

    zero_points = []
    forward_points = []
    bermudan_pillars = []
    try:
        zero_points, forward_points, bermudan_pillars = _curve_analytics(state)
    except Exception as exc:
        trade_page_error = str(exc)

    return {
        "trade_type": trade_type,
        "trade_title": definition["title"],
        "trade_description": definition["description"],
        "trade_fields": prepare_trade_form(definition, trade),
        "trade_headline": headline,
        "trade_detail": detail,
        "trade_detail_rows": trade_detail_rows(trade_type, trade),
        "market_snapshot": market_snapshot(state, zero_points, forward_points, bermudan_pillars),
        "selected_matrix_vol_bp": selected_matrix_vol_bp,
        "cliquet_context": cliquet_context,
        "trade_page_error": trade_page_error,
        "trade_risk_api_url": "" if trade_type == "equity_cliquet" else url_for("workbench.trade_risk", trade_type=trade_type),
        "trade_risk_matrix_headers": swaption_matrix_headers(),
    }


def apply_realtime_tick(state):
    updated_quotes = []
    for quote in state["market"]["curve_quotes_pct"]:
        move_bp = random.uniform(REALTIME_MOVE_MIN_BP, REALTIME_MOVE_MAX_BP)
        direction = random.choice((-1.0, 1.0))
        updated_quotes.append(max(0.01, quote + direction * move_bp / 100.0))
    state["market"]["curve_quotes_pct"] = updated_quotes
    return state
