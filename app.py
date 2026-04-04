import os
import random
from datetime import datetime

import QuantLib as ql
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

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

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "tgir-quantlib-tools-local")

SESSION_STATE_KEY = "portfolio_state"
REALTIME_MOVE_MIN_BP = 1.0
REALTIME_MOVE_MAX_BP = 2.0
LOCAL_DEV_HOST = "127.0.0.1"
LOCAL_DEV_PORT = 5050

MATRIX_SOURCE_NOTE = (
    "ATM normal-vol pillars are editable demo values on a 1Y to 10Y by 1Y to 10Y grid. "
    "The layout follows the expiry-by-underlying swap structure described by ICE SDX "
    "Swaption Forward Rates and Swaption Volatility Surface pages. The repo does not "
    "download live vendor data."
)

TRADE_FORM_DEFINITIONS = {
    "swap": {
        "title": "Interest Rate Swap",
        "description": "Spot-starting fixed versus SOFR swap. Keep the surface clean on the dashboard and edit the actual terms here.",
        "fields": [
            {
                "name": "direction",
                "label": "Fixed side",
                "type": "select",
                "options": [
                    ("payer", "Pay fixed"),
                    ("receiver", "Receive fixed"),
                ],
            },
            {
                "name": "notional",
                "label": "Notional",
                "type": "number",
                "step": "100000",
            },
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
        "description": "Single exercise into a forward-starting swap. Priced off the editable ATM normal-vol matrix at the selected expiry and swap tenor.",
        "fields": [
            {
                "name": "direction",
                "label": "Option style",
                "type": "select",
                "options": [
                    ("payer", "Payer"),
                    ("receiver", "Receiver"),
                ],
            },
            {
                "name": "notional",
                "label": "Notional",
                "type": "number",
                "step": "100000",
            },
            {
                "name": "strike_pct",
                "label": "Strike (%)",
                "type": "number",
                "step": "0.01",
            },
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
        "description": "Multi-exercise callable structure into a fixed versus SOFR swap. Priced with a Hull-White tree using the flat callable normal-vol input as a simple sigma proxy.",
        "fields": [
            {
                "name": "direction",
                "label": "Option style",
                "type": "select",
                "options": [
                    ("payer", "Payer"),
                    ("receiver", "Receiver"),
                ],
            },
            {
                "name": "notional",
                "label": "Notional",
                "type": "number",
                "step": "100000",
            },
            {
                "name": "strike_pct",
                "label": "Strike (%)",
                "type": "number",
                "step": "0.01",
            },
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


@app.template_filter("money")
def money_filter(value):
    return f"${value:,.2f}"


@app.template_filter("signed_money")
def signed_money_filter(value):
    return f"${value:,.2f}" if value >= 0 else f"-${abs(value):,.2f}"


@app.template_filter("pct")
def pct_filter(value):
    return f"{value:.2f}%"


@app.template_filter("sign_class")
def sign_class_filter(value):
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "flat"


def _get_portfolio_state():
    stored = session.get(SESSION_STATE_KEY)
    if stored is None:
        state = default_portfolio_state()
        session[SESSION_STATE_KEY] = state
        return state
    return normalize_portfolio_state(stored)


def _save_portfolio_state(state):
    session[SESSION_STATE_KEY] = normalize_portfolio_state(state)
    session.modified = True


def _parse_float(form, name, default):
    try:
        return float(form.get(name, default))
    except (TypeError, ValueError):
        return default


def _parse_int(form, name, default):
    try:
        return int(float(form.get(name, default)))
    except (TypeError, ValueError):
        return default


def _clamp_int(value, minimum, maximum):
    return max(minimum, min(int(value), maximum))


def _env_flag(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _curve_inputs(state):
    return [
        {"label": label, "name": f"rate{i}", "value": state["market"]["curve_quotes_pct"][i]}
        for i, label in enumerate(SOFR_CURVE_TENOR_LABELS)
    ]


def _swaption_matrix_headers():
    return [f"{tenor}Y" for tenor in SWAPTION_MATRIX_TENOR_YEARS]


def _swaption_matrix_rows(state):
    matrix = state["market"]["swaption_vol_matrix_bp"]
    rows = []
    for expiry_index, expiry_years in enumerate(SWAPTION_MATRIX_EXPIRY_YEARS):
        cells = []
        for tenor_index, tenor_years in enumerate(SWAPTION_MATRIX_TENOR_YEARS):
            cells.append(
                {
                    "name": f"vol_{expiry_years}_{tenor_years}",
                    "value": matrix[expiry_index][tenor_index],
                }
            )
        rows.append({"expiry_label": f"{expiry_years}Y", "cells": cells})
    return rows


def _curve_chart(curve_quotes):
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
    for idx, (label, quote) in enumerate(zip(SOFR_CURVE_TENOR_LABELS, curve_quotes)):
        x = padding_left + idx * plot_width / (len(curve_quotes) - 1)
        ratio = 0.5 if y_max == y_min else (quote - y_min) / (y_max - y_min)
        y = padding_top + (1 - ratio) * plot_height
        markers.append({"label": label, "quote": quote, "x": round(x, 2), "y": round(y, 2)})

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


def _market_snapshot(state):
    curve_quotes = state["market"]["curve_quotes_pct"]
    return {
        "curve_rows": [
            {"label": label, "quote": curve_quotes[idx]}
            for idx, label in enumerate(SOFR_CURVE_TENOR_LABELS)
        ],
        "callable_normal_vol_bp": float(state["market"]["callable_normal_vol_bp"]),
        "curve_steepness_bp": (curve_quotes[-1] - curve_quotes[0]) * 100.0,
        "curve_average_pct": sum(curve_quotes) / len(curve_quotes),
        "atm_5y5y_bp": lookup_swaption_normal_vol_bp(state, 5, 5),
    }


def _prepare_trade_form(definition, trade):
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


def _update_market_state(state, form):
    curve_quotes = [
        _parse_float(form, f"rate{i}", state["market"]["curve_quotes_pct"][i])
        for i in range(len(SOFR_CURVE_TENOR_LABELS))
    ]
    state["market"]["curve_quotes_pct"] = curve_quotes
    state["market"]["callable_normal_vol_bp"] = max(
        _parse_float(
            form,
            "callable_normal_vol_bp",
            state["market"]["callable_normal_vol_bp"],
        ),
        0.0,
    )

    matrix = []
    current_matrix = state["market"]["swaption_vol_matrix_bp"]
    for expiry_index, expiry_years in enumerate(SWAPTION_MATRIX_EXPIRY_YEARS):
        row = []
        for tenor_index, tenor_years in enumerate(SWAPTION_MATRIX_TENOR_YEARS):
            row.append(
                max(
                    _parse_float(
                        form,
                        f"vol_{expiry_years}_{tenor_years}",
                        current_matrix[expiry_index][tenor_index],
                    ),
                    0.0,
                )
            )
        matrix.append(row)
    state["market"]["swaption_vol_matrix_bp"] = matrix


def _update_trade_state(state, trade_type, form):
    trade = state["trades"][trade_type]

    if trade_type == "swap":
        direction = form.get("direction", trade["direction"])
        trade["direction"] = direction if direction in {"payer", "receiver"} else trade["direction"]
        trade["notional"] = max(_parse_float(form, "notional", trade["notional"]), 1.0)
        trade["fixed_rate_pct"] = _parse_float(form, "fixed_rate_pct", trade["fixed_rate_pct"])
        trade["tenor_years"] = _clamp_int(
            _parse_int(form, "tenor_years", trade["tenor_years"]),
            1,
            30,
        )
        return

    direction = form.get("direction", trade["direction"])
    trade["direction"] = direction if direction in {"payer", "receiver"} else trade["direction"]
    trade["notional"] = max(_parse_float(form, "notional", trade["notional"]), 1.0)
    trade["strike_pct"] = _parse_float(form, "strike_pct", trade["strike_pct"])
    trade["swap_tenor_years"] = _clamp_int(
        _parse_int(form, "swap_tenor_years", trade["swap_tenor_years"]),
        1,
        10,
    )

    if trade_type == "european_swaption":
        trade["expiry_years"] = _clamp_int(
            _parse_int(form, "expiry_years", trade["expiry_years"]),
            1,
            10,
        )
        return

    trade["first_exercise_years"] = _clamp_int(
        _parse_int(form, "first_exercise_years", trade["first_exercise_years"]),
        1,
        9,
    )
    trade["exercise_count"] = _clamp_int(
        _parse_int(form, "exercise_count", trade["exercise_count"]),
        1,
        9,
    )


def _pricing_tables(state):
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


def _enrich_portfolio_rows(portfolio_rows):
    enriched_rows = []
    for row in portfolio_rows:
        trade_key = row["TradeKey"]
        enriched_rows.append(
            {
                **row,
                "EditURL": url_for("edit_trade", trade_type=trade_key),
                "EditLabel": f"Edit {TRADE_TITLES[trade_key]}",
            }
        )
    return enriched_rows


def _portfolio_marks(portfolio_rows):
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


def _dynamic_dashboard_payload(state):
    portfolio_rows, calibration_rows, bermudan_grid_rows, pricing_error = _pricing_tables(state)
    return {
        "portfolio_rows": portfolio_rows,
        "blotter_rows": _enrich_portfolio_rows(portfolio_rows),
        "calibration_rows": calibration_rows,
        "bermudan_grid_rows": bermudan_grid_rows,
        "curve_inputs": _curve_inputs(state),
        "curve_chart": _curve_chart(state["market"]["curve_quotes_pct"]),
        "market_snapshot": _market_snapshot(state),
        "portfolio_marks": _portfolio_marks(portfolio_rows),
        "pricing_error": pricing_error,
        "last_update_label": datetime.now().strftime("%H:%M:%S"),
    }


def _render_dashboard():
    state = _get_portfolio_state()
    payload = _dynamic_dashboard_payload(state)
    payload.update(
        {
            "swaption_matrix_headers": _swaption_matrix_headers(),
            "swaption_matrix_rows": _swaption_matrix_rows(state),
            "bermudan_grid_headers": [f"{year}Y" for year in BERMUDAN_GRID_MATURITIES_YEARS],
            "normal_vol_note": (
                "European swaptions read ATM normal vols from the editable matrix. "
                "Bermudans use the flat callable normal vol below as a simple Hull-White sigma proxy."
            ),
            "matrix_source_note": MATRIX_SOURCE_NOTE,
        }
    )
    return render_template("dashboard.html", **payload)


def _apply_realtime_tick(state):
    updated_quotes = []
    for quote in state["market"]["curve_quotes_pct"]:
        move_bp = random.uniform(REALTIME_MOVE_MIN_BP, REALTIME_MOVE_MAX_BP)
        direction = random.choice((-1.0, 1.0))
        updated_quotes.append(max(0.01, quote + direction * move_bp / 100.0))
    state["market"]["curve_quotes_pct"] = updated_quotes
    return state


@app.route("/", methods=["GET"])
def dashboard():
    return _render_dashboard()


@app.post("/market")
def update_market():
    state = _get_portfolio_state()
    _update_market_state(state, request.form)
    _save_portfolio_state(state)
    flash("Market settings updated.")
    return redirect(url_for("dashboard"))


@app.post("/reset")
def reset_portfolio():
    _save_portfolio_state(default_portfolio_state())
    flash("Portfolio reset to the demo defaults.")
    return redirect(url_for("dashboard"))


@app.post("/api/realtime/tick")
def realtime_tick():
    state = _get_portfolio_state()
    _apply_realtime_tick(state)
    _save_portfolio_state(state)
    payload = _dynamic_dashboard_payload(state)
    payload["bermudan_grid_headers"] = [f"{year}Y" for year in BERMUDAN_GRID_MATURITIES_YEARS]
    return jsonify(payload)


@app.route("/trade/<trade_type>", methods=["GET", "POST"])
def edit_trade(trade_type):
    if trade_type not in TRADE_FORM_DEFINITIONS:
        abort(404)

    state = _get_portfolio_state()
    if request.method == "POST":
        _update_trade_state(state, trade_type, request.form)
        _save_portfolio_state(state)
        flash(f"{TRADE_TITLES[trade_type]} updated.")
        return redirect(url_for("dashboard"))

    definition = TRADE_FORM_DEFINITIONS[trade_type]
    trade = state["trades"][trade_type]
    headline, detail = trade_card_summary(
        trade_type,
        trade,
        state["market"],
    )
    selected_matrix_vol_bp = None
    if trade_type == "european_swaption":
        selected_matrix_vol_bp = lookup_swaption_normal_vol_bp(
            state,
            trade["expiry_years"],
            trade["swap_tenor_years"],
        )
    return render_template(
        "trade_form.html",
        trade_type=trade_type,
        trade_title=definition["title"],
        trade_description=definition["description"],
        trade_fields=_prepare_trade_form(definition, trade),
        trade_headline=headline,
        trade_detail=detail,
        market_snapshot=_market_snapshot(state),
        selected_matrix_vol_bp=selected_matrix_vol_bp,
    )


if __name__ == "__main__":
    host = os.environ.get("FLASK_RUN_HOST", LOCAL_DEV_HOST)
    port = int(os.environ.get("PORT", os.environ.get("FLASK_RUN_PORT", LOCAL_DEV_PORT)))
    debug_enabled = _env_flag("FLASK_DEBUG", True)
    print(f"Open http://{host}:{port}", flush=True)
    app.run(host=host, port=port, debug=debug_enabled, use_reloader=False)
