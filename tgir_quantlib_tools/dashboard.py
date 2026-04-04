from __future__ import annotations

from datetime import datetime
import random

import QuantLib as ql
from flask import current_app, session, url_for

from portfolio import (
    BERMUDAN_GRID_MATURITIES_YEARS,
    BERMUDAN_GRID_NONCALL_YEARS,
    SOFR_CURVE_TENOR_LABELS,
    SWAPTION_MATRIX_EXPIRY_YEARS,
    SWAPTION_MATRIX_TENOR_YEARS,
    TRADE_TITLES,
    build_bermudan_pricing_grid,
    build_sofr_curve,
    default_portfolio_state,
    lookup_swaption_normal_vol_bp,
    normalize_portfolio_state,
    price_portfolio,
    reprice_sofr_calibration_swaps,
    trade_card_summary,
)


REALTIME_MOVE_MIN_BP = 1.0
REALTIME_MOVE_MAX_BP = 2.0

MATRIX_SOURCE_NOTE = (
    "ATM normal-vol pillars are editable demo values on a 1Y to 10Y by 1Y to 10Y grid. "
    "The layout follows the expiry-by-underlying swap structure described by ICE SDX "
    "Swaption Forward Rates and Swaption Volatility Surface pages. The repo does not "
    "download live vendor data."
)

TRADE_FORM_DEFINITIONS = {
    "swap": {
        "title": "Interest Rate Swap",
        "description": (
            "Spot-starting fixed versus SOFR swap. Keep the surface clean on the dashboard "
            "and edit the actual terms here."
        ),
        "fields": [
            {
                "name": "direction",
                "label": "Fixed side",
                "type": "select",
                "options": [("payer", "Pay fixed"), ("receiver", "Receive fixed")],
            },
            {"name": "notional", "label": "Notional", "type": "number", "step": "100000"},
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
        ],
    },
    "european_swaption": {
        "title": "European Swaption",
        "description": (
            "Single exercise into a forward-starting swap. Priced off the editable ATM "
            "normal-vol matrix at the selected expiry and swap tenor."
        ),
        "fields": [
            {
                "name": "direction",
                "label": "Option style",
                "type": "select",
                "options": [("payer", "Payer"), ("receiver", "Receiver")],
            },
            {"name": "notional", "label": "Notional", "type": "number", "step": "100000"},
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
        ],
    },
    "bermudan_swaption": {
        "title": "Bermudan Swaption",
        "description": (
            "Multi-exercise callable structure into a fixed versus SOFR swap. Priced with "
            "a Hull-White tree using the flat callable normal-vol input as a simple sigma proxy."
        ),
        "fields": [
            {
                "name": "direction",
                "label": "Option style",
                "type": "select",
                "options": [("payer", "Payer"), ("receiver", "Receiver")],
            },
            {"name": "notional", "label": "Notional", "type": "number", "step": "100000"},
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
                "name": "swap_tenor_years",
                "label": "Underlying tenor (years)",
                "type": "number",
                "step": "1",
                "min": "1",
                "max": "10",
            },
            {
                "name": "exercise_count",
                "label": "Exercise dates",
                "type": "number",
                "step": "1",
                "min": "1",
                "max": "9",
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


def parse_float(form, name, default):
    try:
        return float(form.get(name, default))
    except (TypeError, ValueError):
        return default


def parse_int(form, name, default):
    try:
        return int(float(form.get(name, default)))
    except (TypeError, ValueError):
        return default


def clamp_int(value, minimum, maximum):
    return max(minimum, min(int(value), maximum))


def curve_inputs(state):
    return [
        {"label": label, "name": f"rate{index}", "value": state["market"]["curve_quotes_pct"][index]}
        for index, label in enumerate(SOFR_CURVE_TENOR_LABELS)
    ]


def swaption_matrix_headers():
    return [f"{tenor}Y" for tenor in SWAPTION_MATRIX_TENOR_YEARS]


def swaption_matrix_rows(state):
    matrix = state["market"]["swaption_vol_matrix_bp"]
    rows = []
    for expiry_index, expiry_years in enumerate(SWAPTION_MATRIX_EXPIRY_YEARS):
        rows.append(
            {
                "expiry_label": f"{expiry_years}Y",
                "cells": [
                    {
                        "name": f"vol_{expiry_years}_{tenor_years}",
                        "value": matrix[expiry_index][tenor_index],
                    }
                    for tenor_index, tenor_years in enumerate(SWAPTION_MATRIX_TENOR_YEARS)
                ],
            }
        )
    return rows


def curve_chart(curve_quotes):
    width = 500
    height = 220
    padding_left = 32
    padding_right = 18
    padding_top = 24
    padding_bottom = 34
    plot_width = width - padding_left - padding_right
    plot_height = height - padding_top - padding_bottom

    min_quote = min(curve_quotes)
    max_quote = max(curve_quotes)
    buffer = max((max_quote - min_quote) * 0.30, 0.20)
    y_min = min_quote - buffer
    y_max = max_quote + buffer

    markers = []
    for index, (label, quote) in enumerate(zip(SOFR_CURVE_TENOR_LABELS, curve_quotes)):
        x_position = padding_left + index * plot_width / (len(curve_quotes) - 1)
        ratio = 0.5 if y_max == y_min else (quote - y_min) / (y_max - y_min)
        y_position = padding_top + (1 - ratio) * plot_height
        markers.append(
            {"label": label, "quote": quote, "x": round(x_position, 2), "y": round(y_position, 2)}
        )

    polyline = " ".join(f"{marker['x']},{marker['y']}" for marker in markers)
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

    return {
        "width": width,
        "height": height,
        "markers": markers,
        "polyline": polyline,
        "area": area,
        "y_ticks": y_ticks,
    }


def market_snapshot(state):
    curve_quotes = state["market"]["curve_quotes_pct"]
    return {
        "curve_rows": [
            {"label": label, "quote": curve_quotes[index]}
            for index, label in enumerate(SOFR_CURVE_TENOR_LABELS)
        ],
        "callable_normal_vol_bp": float(state["market"]["callable_normal_vol_bp"]),
        "curve_steepness_bp": (curve_quotes[-1] - curve_quotes[0]) * 100.0,
        "curve_average_pct": sum(curve_quotes) / len(curve_quotes),
        "atm_5y5y_bp": lookup_swaption_normal_vol_bp(state, 5, 5),
    }


def prepare_trade_form(definition, trade):
    fields = []
    for field in definition["fields"]:
        field_context = dict(field)
        field_context["value"] = trade[field["name"]]
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


def update_market_state(state, form) -> None:
    state["market"]["curve_quotes_pct"] = [
        parse_float(form, f"rate{index}", state["market"]["curve_quotes_pct"][index])
        for index in range(len(SOFR_CURVE_TENOR_LABELS))
    ]
    state["market"]["callable_normal_vol_bp"] = max(
        parse_float(form, "callable_normal_vol_bp", state["market"]["callable_normal_vol_bp"]),
        0.0,
    )

    current_matrix = state["market"]["swaption_vol_matrix_bp"]
    updated_matrix = []
    for expiry_index, expiry_years in enumerate(SWAPTION_MATRIX_EXPIRY_YEARS):
        row = []
        for tenor_index, tenor_years in enumerate(SWAPTION_MATRIX_TENOR_YEARS):
            row.append(
                max(
                    parse_float(
                        form,
                        f"vol_{expiry_years}_{tenor_years}",
                        current_matrix[expiry_index][tenor_index],
                    ),
                    0.0,
                )
            )
        updated_matrix.append(row)
    state["market"]["swaption_vol_matrix_bp"] = updated_matrix


def update_trade_state(state, trade_type, form) -> None:
    trade = state["trades"][trade_type]
    direction = form.get("direction", trade["direction"])
    trade["direction"] = direction if direction in {"payer", "receiver"} else trade["direction"]
    trade["notional"] = max(parse_float(form, "notional", trade["notional"]), 1.0)

    if trade_type == "swap":
        trade["fixed_rate_pct"] = parse_float(form, "fixed_rate_pct", trade["fixed_rate_pct"])
        trade["tenor_years"] = clamp_int(parse_int(form, "tenor_years", trade["tenor_years"]), 1, 30)
        return

    trade["strike_pct"] = parse_float(form, "strike_pct", trade["strike_pct"])
    trade["swap_tenor_years"] = clamp_int(
        parse_int(form, "swap_tenor_years", trade["swap_tenor_years"]),
        1,
        10,
    )

    if trade_type == "european_swaption":
        trade["expiry_years"] = clamp_int(parse_int(form, "expiry_years", trade["expiry_years"]), 1, 10)
        return

    trade["first_exercise_years"] = clamp_int(
        parse_int(form, "first_exercise_years", trade["first_exercise_years"]),
        1,
        9,
    )
    trade["exercise_count"] = clamp_int(
        parse_int(form, "exercise_count", trade["exercise_count"]),
        1,
        9,
    )


def pricing_tables(state):
    portfolio_rows = []
    calibration_rows = []
    bermudan_grid_rows = []
    pricing_error = None

    try:
        portfolio_rows = price_portfolio(state).to_dict("records")
        today = ql.Date.todaysDate()
        ql.Settings.instance().evaluationDate = today
        curve = build_sofr_curve(today, state["market"]["curve_quotes_pct"])
        calibration_rows = reprice_sofr_calibration_swaps(
            curve,
            state["market"]["curve_quotes_pct"],
        ).to_dict("records")
        bermudan_grid_rows = build_bermudan_pricing_grid(state).to_dict("records")
    except Exception as exc:
        pricing_error = str(exc)

    return portfolio_rows, calibration_rows, bermudan_grid_rows, pricing_error


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
    return {
        "portfolio_rows": portfolio_rows,
        "blotter_rows": enrich_portfolio_rows(portfolio_rows),
        "calibration_rows": calibration_rows,
        "bermudan_grid_rows": bermudan_grid_rows,
        "curve_inputs": curve_inputs(state),
        "curve_chart": curve_chart(state["market"]["curve_quotes_pct"]),
        "market_snapshot": market_snapshot(state),
        "portfolio_marks": portfolio_marks(portfolio_rows),
        "pricing_error": pricing_error,
        "last_update_label": datetime.now().strftime("%H:%M:%S"),
    }


def build_dashboard_context(state):
    payload = dynamic_dashboard_payload(state)
    payload.update(
        {
            "swaption_matrix_headers": swaption_matrix_headers(),
            "swaption_matrix_rows": swaption_matrix_rows(state),
            "bermudan_grid_headers": [f"{year}Y" for year in BERMUDAN_GRID_MATURITIES_YEARS],
            "normal_vol_note": (
                "European swaptions read ATM normal vols from the editable matrix. "
                "Bermudans use the flat callable normal vol below as a simple Hull-White sigma proxy."
            ),
            "matrix_source_note": MATRIX_SOURCE_NOTE,
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
    if trade_type == "european_swaption":
        selected_matrix_vol_bp = lookup_swaption_normal_vol_bp(
            state,
            trade["expiry_years"],
            trade["swap_tenor_years"],
        )
    return {
        "trade_type": trade_type,
        "trade_title": definition["title"],
        "trade_description": definition["description"],
        "trade_fields": prepare_trade_form(definition, trade),
        "trade_headline": headline,
        "trade_detail": detail,
        "market_snapshot": market_snapshot(state),
        "selected_matrix_vol_bp": selected_matrix_vol_bp,
    }


def apply_realtime_tick(state):
    updated_quotes = []
    for quote in state["market"]["curve_quotes_pct"]:
        move_bp = random.uniform(REALTIME_MOVE_MIN_BP, REALTIME_MOVE_MAX_BP)
        direction = random.choice((-1.0, 1.0))
        updated_quotes.append(max(0.01, quote + direction * move_bp / 100.0))
    state["market"]["curve_quotes_pct"] = updated_quotes
    return state
