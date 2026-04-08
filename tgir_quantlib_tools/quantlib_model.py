from __future__ import annotations

import QuantLib as ql
from flask import current_app, url_for

from portfolio import (
    BERMUDAN_GSR_INTEGRATION_POINTS,
    BERMUDAN_GSR_STDDEVS,
    SOFR_CURVE_POINT_SPECS,
    SOFR_CURVE_TENOR_LABELS,
    SWAPTION_MATRIX_EXPIRY_LABELS,
    SWAPTION_MATRIX_TENOR_LABELS,
    build_bermudan_gsr_model,
    cliquet_analytics,
    cliquet_reset_schedule,
    build_sofr_curve,
    curve_zero_rate_points,
    daily_one_day_forward_points,
    frequency_label,
    lookup_swaption_normal_vol_bp,
    normalize_portfolio_state,
    valuation_date,
)
from .research import CLIQUET_RESEARCH_SECTION, SWAPTION_RESEARCH_SECTIONS


def _enum_member(label, enum_value, notes):
    try:
        numeric_value = int(enum_value)
    except (TypeError, ValueError):
        numeric_value = "-"
    return {"label": label, "value": numeric_value, "notes": notes}


def _swap_type_label(direction):
    return "ql.OvernightIndexedSwap.Payer" if direction == "payer" else "ql.OvernightIndexedSwap.Receiver"


def _schedule_summary(name, start, maturity, payment_frequency_months, reset_frequency_months):
    return {
        "name": name,
        "start": start.ISO(),
        "maturity": maturity.ISO(),
        "fixed_tenor": f"ql.Period({int(payment_frequency_months)}, ql.Months)",
        "floating_tenor": f"ql.Period({int(reset_frequency_months)}, ql.Months)",
        "calendar": "ql.UnitedStates(ql.UnitedStates.Settlement)",
        "convention": "ql.ModifiedFollowing",
        "termination_convention": "ql.ModifiedFollowing",
        "rule": "ql.DateGeneration.Forward",
        "end_of_month": "False",
    }


def _component_card(title, family, factory, signature, purpose, dependencies, fields, table=None, enums=None):
    return {
        "title": title,
        "family": family,
        "factory": factory,
        "signature": signature,
        "purpose": purpose,
        "dependencies": dependencies,
        "fields": fields,
        "table": table,
        "enums": enums or [],
    }


def build_quantlib_model_context(portfolio_state=None):
    state = normalize_portfolio_state(portfolio_state)
    market = state["market"]
    trades = state["trades"]

    today = valuation_date(state)
    ql.Settings.instance().evaluationDate = today
    calendar = ql.UnitedStates(ql.UnitedStates.Settlement)
    curve = build_sofr_curve(today, market["curve_quotes_pct"])
    curve_handle = ql.YieldTermStructureHandle(curve)
    zero_points = curve_zero_rate_points(curve)
    forward_points = daily_one_day_forward_points(curve)
    bermudan_model = build_bermudan_gsr_model(
        state,
        market_context=(state, today, calendar, curve, curve_handle),
    )
    cliquet_model = cliquet_analytics(
        state,
        market_context=(state, today, calendar, curve, curve_handle),
    )
    bermudan_calibration_rows = bermudan_model["calibration_rows"]
    gsr_sigma_rows = bermudan_model["sigma_rows"]
    cliquet_reset_dates, cliquet_maturity = cliquet_reset_schedule(
        trades["equity_cliquet"],
        today,
    )

    spot = calendar.advance(today, 2, ql.Days)
    live_swap_maturity = calendar.advance(spot, int(trades["swap"]["tenor_years"]), ql.Years)

    european_exercise = calendar.advance(spot, int(trades["european_swaption"]["expiry_years"]), ql.Years)
    european_maturity = calendar.advance(
        european_exercise,
        int(trades["european_swaption"]["swap_tenor_years"]),
        ql.Years,
    )

    bermudan_first_exercise = calendar.advance(
        spot,
        int(trades["bermudan_swaption"]["first_exercise_years"]),
        ql.Years,
    )
    bermudan_maturity = calendar.advance(
        spot,
        int(trades["bermudan_swaption"]["final_maturity_years"]),
        ql.Years,
    )
    bermudan_schedule = ql.Schedule(
        bermudan_first_exercise,
        bermudan_maturity,
        ql.Period(int(trades["bermudan_swaption"]["payment_frequency_months"]), ql.Months),
        ql.UnitedStates(ql.UnitedStates.Settlement),
        ql.ModifiedFollowing,
        ql.ModifiedFollowing,
        ql.DateGeneration.Forward,
        False,
    )
    bermudan_exercise_dates = [
        calendar.advance(date, -1, ql.Days).ISO()
        for date in list(bermudan_schedule)[:-1]
    ]
    if not bermudan_exercise_dates:
        bermudan_exercise_dates.append(calendar.advance(bermudan_first_exercise, -1, ql.Days).ISO())

    cliquet_period_dates = list(cliquet_reset_dates) + [cliquet_maturity]
    cliquet_period_labels = [
        {
            "start": start.ISO(),
            "end": end.ISO(),
            "year_fraction": row["year_fraction"],
        }
        for row, start, end in zip(
            cliquet_model["period_rows"],
            cliquet_period_dates[:-1],
            cliquet_period_dates[1:],
        )
    ]

    curve_rows = [
        {
            "tenor": label,
            "quote_pct": market["curve_quotes_pct"][index],
        }
        for index, label in enumerate(SOFR_CURVE_TENOR_LABELS)
    ]
    curve_node_rows = []
    for node_index, ((node_date, discount_factor), zero_point) in enumerate(
        zip(curve.nodes()[1:], zero_points),
        start=1,
    ):
        curve_node_rows.append(
            {
                "node": node_index,
                "tenor": zero_point["label"],
                "date_iso": node_date.ISO(),
                "discount_factor": discount_factor,
                "zero_rate_pct": zero_point["rate_pct"],
            }
        )

    point_by_iso = {point["start_date_iso"]: point for point in forward_points}

    def _forward_checkpoint(label, target_date):
        point = point_by_iso.get(target_date.ISO(), forward_points[-1])
        return {
            "label": label,
            "date": point["start_date_iso"],
            "rate_pct": point["rate_pct"],
        }

    forward_summary_rows = [
        _forward_checkpoint("Start", today),
        _forward_checkpoint("3M", today + ql.Period(3, ql.Months)),
        _forward_checkpoint("1Y", today + ql.Period(1, ql.Years)),
        _forward_checkpoint("10Y", today + ql.Period(10, ql.Years)),
    ]

    swaption_matrix_rows = []
    for expiry_index, expiry_label in enumerate(SWAPTION_MATRIX_EXPIRY_LABELS):
        swaption_matrix_rows.append(
            {
                "expiry_label": expiry_label,
                "values": market["swaption_vol_matrix_bp"][expiry_index],
            }
        )

    object_flow = [
        {
            "step": "1",
            "title": "Evaluation context",
            "function": "_market_context / build_sofr_curve",
            "depends_on": "configured valuation date",
            "produces": "ql.Settings.instance().evaluationDate and ql.UnitedStates(Settlement)",
            "description": "Sets the pricing date once per request from the configured valuation date and uses a settlement calendar for curve and schedule dates.",
        },
        {
            "step": "2",
            "title": "Curve helpers",
            "function": "build_sofr_curve",
            "depends_on": "market.curve_quotes_pct",
            "produces": "1 ql.DepositRateHelper + 7 ql.OISRateHelper",
            "description": "Builds the helper strip from the overnight input and the OIS tenors that anchor the SOFR curve.",
        },
        {
            "step": "3",
            "title": "Discount curve",
            "function": "build_sofr_curve",
            "depends_on": "helper strip, day count",
            "produces": "ql.PiecewiseLogCubicDiscount and ql.YieldTermStructureHandle",
            "description": "Bootstraps the term structure used for discounting, forward extraction, swap pricing, and the Bermudan calibration stack.",
        },
        {
            "step": "4",
            "title": "Underlying instruments",
            "function": "_make_ois_swap",
            "depends_on": "curve handle, schedules, trade terms",
            "produces": "ql.OvernightIndexedSwap for the live swap and the swaption underlyings",
            "description": "Uses one canonical overnight-indexed swap constructor for the live trade and for both forward-starting swaption underlyings.",
        },
        {
            "step": "5",
            "title": "European swaption stack",
            "function": "_create_european_swaption",
            "depends_on": "forward swap, exercise date, ATM matrix vol",
            "produces": "ql.EuropeanExercise, ql.Swaption, ql.BachelierSwaptionEngine",
            "description": "Prices the European swaption directly from the selected normal-vol pillar in the editable matrix.",
        },
        {
            "step": "6",
            "title": "Bermudan swaption stack",
            "function": "_create_bermudan_swaption",
            "depends_on": "forward swap, exercise dates, diagonal swaption strip, curve handle",
            "produces": "ql.SwaptionHelper strip, ql.Gsr, ql.Gaussian1dSwaptionEngine, ql.Swaption",
            "description": "Calibrates a time-dependent Gaussian short-rate model to the feasible diagonal ATM swaption strip and prices the Bermudan with that calibrated engine.",
        },
        {
            "step": "7",
            "title": "Calibration instruments",
            "function": "reprice_sofr_calibration_swaps",
            "depends_on": "curve and quoted OIS rates",
            "produces": "ql.MakeOIS repricing strip",
            "description": "Rebuilds quoted OIS instruments against the bootstrapped curve to confirm the helper calibration is near-par.",
        },
        {
            "step": "8",
            "title": "Equity cliquet stack",
            "function": "_create_equity_cliquet / cliquet_analytics",
            "depends_on": "curve handle, SPX spot, dividend yield, flat vol, reset schedule",
            "produces": "ql.BlackScholesMertonProcess, ql.CliquetOption, ql.AnalyticCliquetEngine",
            "description": "Builds a forward-start SPX cliquet strip on top of the SOFR discount curve and decomposes it into reset-by-reset forward-start option analytics.",
        },
    ]

    state_sections = [
        {
            "title": "Session State: market",
            "rows": [
                {
                    "field": "curve_quotes_pct",
                    "type": f"list[float] length {len(SOFR_CURVE_TENOR_LABELS)}",
                    "value": ", ".join(f"{row['tenor']}={row['quote_pct']:.2f}%" for row in curve_rows),
                    "used_by": "build_sofr_curve",
                },
                {
                    "field": "hw_mean_reversion",
                    "type": "float",
                    "value": f"{market['hw_mean_reversion']:.4f}",
                    "used_by": "build_bermudan_gsr_model -> fixed mean-reversion input during calibration",
                },
                {
                    "field": "swaption_vol_matrix_bp",
                    "type": f"{len(SWAPTION_MATRIX_EXPIRY_LABELS)}x{len(SWAPTION_MATRIX_TENOR_LABELS)} list[list[float]]",
                    "value": f"matrix[5Y][5Y]={lookup_swaption_normal_vol_bp(state, 5, 5):.1f} bp",
                    "used_by": "_create_european_swaption -> ql.BachelierSwaptionEngine",
                },
                {
                    "field": "equity_spot / equity_dividend_yield_pct / equity_volatility_pct",
                    "type": "float triplet",
                    "value": (
                        f"spot={market['equity_spot']:.2f}, q={market['equity_dividend_yield_pct']:.2f}%, "
                        f"vol={market['equity_volatility_pct']:.2f}%"
                    ),
                    "used_by": "_create_equity_cliquet -> ql.BlackScholesMertonProcess",
                },
            ],
        },
        {
            "title": "Session State: trades",
            "rows": [
                {
                    "field": "trades.swap",
                    "type": "dict",
                    "value": (
                        f"direction={trades['swap']['direction']}, notional={trades['swap']['notional']:.0f}, "
                        f"fixed_rate_pct={trades['swap']['fixed_rate_pct']:.2f}, tenor_years={trades['swap']['tenor_years']}, "
                        f"payment_frequency_months={trades['swap']['payment_frequency_months']}, "
                        f"reset_frequency_months={trades['swap']['reset_frequency_months']}"
                    ),
                    "used_by": "_create_live_swap -> ql.OvernightIndexedSwap",
                },
                {
                    "field": "trades.european_swaption",
                    "type": "dict",
                    "value": (
                        f"direction={trades['european_swaption']['direction']}, notional={trades['european_swaption']['notional']:.0f}, "
                        f"strike_pct={trades['european_swaption']['strike_pct']:.2f}, expiry_years={trades['european_swaption']['expiry_years']}, "
                        f"swap_tenor_years={trades['european_swaption']['swap_tenor_years']}, "
                        f"payment_frequency_months={trades['european_swaption']['payment_frequency_months']}, "
                        f"reset_frequency_months={trades['european_swaption']['reset_frequency_months']}"
                    ),
                    "used_by": "_create_european_swaption",
                },
                {
                    "field": "trades.bermudan_swaption",
                    "type": "dict",
                    "value": (
                        f"direction={trades['bermudan_swaption']['direction']}, notional={trades['bermudan_swaption']['notional']:.0f}, "
                        f"strike_pct={trades['bermudan_swaption']['strike_pct']:.2f}, first_exercise_years={trades['bermudan_swaption']['first_exercise_years']}, "
                        f"final_maturity_years={trades['bermudan_swaption']['final_maturity_years']}, "
                        f"payment_frequency_months={trades['bermudan_swaption']['payment_frequency_months']}, "
                        f"reset_frequency_months={trades['bermudan_swaption']['reset_frequency_months']}"
                    ),
                    "used_by": "_create_bermudan_swaption",
                },
                {
                    "field": "trades.equity_cliquet",
                    "type": "dict",
                    "value": (
                        f"option_type={trades['equity_cliquet']['option_type']}, quantity={trades['equity_cliquet']['quantity']:.2f}, "
                        f"moneyness_pct={trades['equity_cliquet']['moneyness_pct']:.1f}, maturity_months={trades['equity_cliquet']['maturity_months']}, "
                        f"reset_frequency_months={trades['equity_cliquet']['reset_frequency_months']}"
                    ),
                    "used_by": "_create_equity_cliquet",
                },
            ],
        },
    ]

    component_cards = [
        _component_card(
            title="ql.Settings.instance().evaluationDate",
            family="Global pricing context",
            factory="_market_context",
            signature="ql.Settings.instance().evaluationDate = today",
            purpose="Pins every curve build and pricing engine to the same valuation date.",
            dependencies=["state.valuation_date_iso"],
            fields=[
                {"name": "today", "value": today.ISO(), "notes": "Configured QuantLib evaluation date"},
            ],
            enums=[],
        ),
        _component_card(
            title="ql.DepositRateHelper",
            family="Curve helper",
            factory="build_sofr_curve",
            signature="ql.DepositRateHelper(rate, tenor, fixingDays, calendar, convention, endOfMonth, dayCounter)",
            purpose="Anchors the overnight end of the SOFR curve.",
            dependencies=["market.curve_quotes_pct[0]", "ql.QuoteHandle", "ql.SimpleQuote", "ql.UnitedStates"],
            fields=[
                {"name": "rate", "value": f"{market['curve_quotes_pct'][0] / 100.0:.6f}", "notes": "Overnight quote converted from percent to decimal"},
                {"name": "tenor", "value": "ql.Period(1, ql.Days)", "notes": "One-day deposit anchor"},
                {"name": "fixingDays", "value": "0", "notes": "No extra fixing lag on the overnight helper"},
                {"name": "calendar", "value": "ql.UnitedStates(ql.UnitedStates.Settlement)", "notes": "Settlement calendar"},
                {"name": "convention", "value": "ql.Following", "notes": "Deposit helper roll convention"},
                {"name": "endOfMonth", "value": "False", "notes": "No end-of-month rule"},
                {"name": "dayCounter", "value": "ql.Actual360()", "notes": "SOFR-style money-market accrual basis"},
            ],
            enums=[
                _enum_member("ql.UnitedStates.Settlement", ql.UnitedStates.Settlement, "Calendar market"),
                _enum_member("ql.Following", ql.Following, "Business-day convention"),
                _enum_member("ql.Days", ql.Days, "Time unit"),
            ],
        ),
        _component_card(
            title="ql.OISRateHelper",
            family="Curve helper",
            factory="build_sofr_curve",
            signature="ql.OISRateHelper(settlementDays, tenor, fixedRate, overnightIndex)",
            purpose="Supplies the term OIS pillars used to bootstrap the rest of the curve.",
            dependencies=["market.curve_quotes_pct[1:]", "ql.Sofr()"],
            fields=[
                {"name": "settlementDays", "value": "2", "notes": "OIS helpers start from spot"},
                {"name": "overnightIndex", "value": "ql.Sofr()", "notes": "SOFR index without an attached handle during bootstrap"},
            ],
            table={
                "headers": ["Tenor", "Quote (%)", "Helper call"],
                "rows": [
                    {
                        "c1": label,
                        "c2": f"{market['curve_quotes_pct'][index + 1]:.2f}",
                        "c3": f"ql.OISRateHelper(2, ql.Period('{label}'), quote, ql.Sofr())",
                    }
                    for index, (label, _period, _kind) in enumerate(SOFR_CURVE_POINT_SPECS[1:])
                ],
            },
            enums=[
                _enum_member("ql.Weeks", ql.Weeks, "Short-dated OIS tenor unit"),
                _enum_member("ql.Months", ql.Months, "Monthly OIS tenor unit"),
                _enum_member("ql.Years", ql.Years, "Long-dated OIS tenor unit"),
            ],
        ),
        _component_card(
            title="ql.PiecewiseLogCubicDiscount",
            family="Term structure",
            factory="build_sofr_curve",
            signature="ql.PiecewiseLogCubicDiscount(referenceDate, helpers, dayCounter)",
            purpose="Bootstraps the discount curve used by every instrument and chart on the page.",
            dependencies=["deposit helper", "OIS helper strip", "ql.Actual360()"],
            fields=[
                {"name": "referenceDate", "value": today.ISO(), "notes": "Same as evaluation date"},
                {
                    "name": "helpers",
                    "value": f"{len(SOFR_CURVE_POINT_SPECS)} helpers",
                    "notes": "1 deposit helper plus the workbook OIS strip",
                },
                {"name": "dayCounter", "value": "ql.Actual360()", "notes": "Interpolation metric"},
                {
                    "name": "reportedZeroRateConvention",
                    "value": "Continuous / Actual365Fixed",
                    "notes": "Displayed zero rates satisfy df(x) = exp(-z * x / 365) using actual calendar days x",
                },
                {"name": "handle", "value": "ql.YieldTermStructureHandle(curve)", "notes": "Shared downstream by swaps, swaptions, and model"},
            ],
            table={
                "headers": ["Node", "Tenor", "Date", "Zero rate (% cc Act/365)", "Discount factor"],
                "rows": [
                    {
                        "c1": row["node"],
                        "c2": row["tenor"],
                        "c3": row["date_iso"],
                        "c4": f"{row['zero_rate_pct']:.4f}",
                        "c5": f"{row['discount_factor']:.6f}",
                    }
                    for row in curve_node_rows
                ],
            },
        ),
        _component_card(
            title="ql.Schedule",
            family="Cashflow schedule",
            factory="_make_ois_swap",
            signature=(
                "ql.Schedule(effectiveDate, terminationDate, tenor, calendar, convention, "
                "terminationDateConvention, rule, endOfMonth)"
            ),
            purpose="Defines the fixed and floating leg coupon dates for the live swap and both forward underlyings.",
            dependencies=["calendar", "trade start date", "trade maturity date"],
            fields=[
                {
                    "name": "fixedTenor",
                    "value": f"ql.Period({trades['swap']['payment_frequency_months']}, ql.Months)",
                    "notes": f"{frequency_label(trades['swap']['payment_frequency_months'])} fixed-leg payment schedule for the live swap",
                },
                {
                    "name": "floatingTenor",
                    "value": f"ql.Period({trades['swap']['reset_frequency_months']}, ql.Months)",
                    "notes": f"{frequency_label(trades['swap']['reset_frequency_months'])} overnight coupon periods for the live swap",
                },
                {"name": "calendar", "value": "ql.UnitedStates(ql.UnitedStates.Settlement)", "notes": "Shared calendar for all schedules"},
                {"name": "convention", "value": "ql.ModifiedFollowing", "notes": "Roll convention for start and coupon dates"},
                {"name": "terminationDateConvention", "value": "ql.ModifiedFollowing", "notes": "Termination-date convention"},
                {"name": "rule", "value": "ql.DateGeneration.Forward", "notes": "Schedule generation rule"},
                {"name": "endOfMonth", "value": "False", "notes": "No end-of-month adjustment"},
            ],
            table={
                "headers": ["Instance", "Start", "Maturity", "Comments"],
                "rows": [
                    {
                        "c1": schedule["name"],
                        "c2": schedule["start"],
                        "c3": schedule["maturity"],
                        "c4": f"fixed {schedule['fixed_tenor']} / float {schedule['floating_tenor']}, {schedule['convention']}, {schedule['rule']}",
                    }
                    for schedule in [
                        _schedule_summary(
                            "Live swap",
                            spot,
                            live_swap_maturity,
                            trades["swap"]["payment_frequency_months"],
                            trades["swap"]["reset_frequency_months"],
                        ),
                        _schedule_summary(
                            "European underlying swap",
                            european_exercise,
                            european_maturity,
                            trades["european_swaption"]["payment_frequency_months"],
                            trades["european_swaption"]["reset_frequency_months"],
                        ),
                        _schedule_summary(
                            "Bermudan underlying swap",
                            bermudan_first_exercise,
                            bermudan_maturity,
                            trades["bermudan_swaption"]["payment_frequency_months"],
                            trades["bermudan_swaption"]["reset_frequency_months"],
                        ),
                    ]
                ],
            },
            enums=[
                _enum_member("ql.ModifiedFollowing", ql.ModifiedFollowing, "Business-day convention"),
                _enum_member("ql.DateGeneration.Forward", ql.DateGeneration.Forward, "Schedule rule"),
            ],
        ),
        _component_card(
            title="ql.OvernightIndexedSwap",
            family="Instrument",
            factory="_make_ois_swap",
            signature=(
                "ql.OvernightIndexedSwap(type, fixedNominals, fixedSchedule, fixedRate, fixedDayCount, "
                "floatingNominals, floatingSchedule, overnightIndex, spread, ..., averagingMethod)"
            ),
            purpose="Provides one full overnight-indexed swap constructor for the live trade and for both swaption underlyings.",
            dependencies=["ql.Schedule", "ql.Sofr(curveHandle)", "trade terms", "ql.DiscountingSwapEngine"],
            fields=[
                {"name": "fixedDayCount", "value": "ql.Actual360()", "notes": "Fixed-leg accrual convention from the workbook trade"},
                {"name": "floatingIndex", "value": "ql.Sofr(curveHandle)", "notes": "Overnight floating leg projected from the same curve"},
                {"name": "spread", "value": "0.0", "notes": "No floating spread in this sandbox"},
                {"name": "averagingMethod", "value": "ql.RateAveraging.Compound", "notes": "Daily compounded overnight accrual within each coupon period"},
            ],
            table={
                "headers": ["Instance", "Type", "Nominal", "Rate input", "Start", "Maturity"],
                "rows": [
                    {
                        "c1": "Live swap",
                        "c2": _swap_type_label(trades["swap"]["direction"]),
                        "c3": f"{trades['swap']['notional']:.0f}",
                        "c4": f"fixed_rate_pct={trades['swap']['fixed_rate_pct']:.2f}%",
                        "c5": spot.ISO(),
                        "c6": live_swap_maturity.ISO(),
                    },
                    {
                        "c1": "European underlying",
                        "c2": _swap_type_label(trades["european_swaption"]["direction"]),
                        "c3": f"{trades['european_swaption']['notional']:.0f}",
                        "c4": f"strike_pct={trades['european_swaption']['strike_pct']:.2f}%",
                        "c5": european_exercise.ISO(),
                        "c6": european_maturity.ISO(),
                    },
                    {
                        "c1": "Bermudan underlying",
                        "c2": _swap_type_label(trades["bermudan_swaption"]["direction"]),
                        "c3": f"{trades['bermudan_swaption']['notional']:.0f}",
                        "c4": f"strike_pct={trades['bermudan_swaption']['strike_pct']:.2f}%",
                        "c5": bermudan_first_exercise.ISO(),
                        "c6": bermudan_maturity.ISO(),
                    },
                ],
            },
            enums=[
                _enum_member("ql.OvernightIndexedSwap.Payer", ql.OvernightIndexedSwap.Payer, "Pay fixed / receive SOFR"),
                _enum_member("ql.OvernightIndexedSwap.Receiver", ql.OvernightIndexedSwap.Receiver, "Receive fixed / pay SOFR"),
            ],
        ),
        _component_card(
            title="ql.DiscountingSwapEngine",
            family="Pricing engine",
            factory="_make_ois_swap",
            signature="ql.DiscountingSwapEngine(discountCurve)",
            purpose="Discounts the live swap and the calibration OIS instruments with the bootstrapped curve handle.",
            dependencies=["ql.YieldTermStructureHandle(curve)"],
            fields=[
                {"name": "discountCurve", "value": "curveHandle", "notes": "Shared across swap pricing and calibration"},
            ],
        ),
        _component_card(
            title="ql.EuropeanExercise + ql.BachelierSwaptionEngine",
            family="European option stack",
            factory="_create_european_swaption",
            signature=(
                "ql.EuropeanExercise(date), ql.Swaption(underlying, exercise), "
                "ql.BachelierSwaptionEngine(discountCurve, vol)"
            ),
            purpose="Prices the European swaption from the current ATM normal-vol matrix pillar.",
            dependencies=["forward-starting ql.OvernightIndexedSwap", "selected matrix vol", "curve handle"],
            fields=[
                {"name": "exerciseDate", "value": european_exercise.ISO(), "notes": "Spot plus option expiry"},
                {
                    "name": "normalVol",
                    "value": f"{lookup_swaption_normal_vol_bp(state, trades['european_swaption']['expiry_years'], trades['european_swaption']['swap_tenor_years']):.1f} bp",
                    "notes": "Selected from market.swaption_vol_matrix_bp",
                },
                {
                    "name": "volHandle",
                    "value": "ql.QuoteHandle(ql.SimpleQuote(normalVol / 10000.0))",
                    "notes": "Bachelier engine expects decimal normal vol",
                },
            ],
        ),
        _component_card(
            title="ql.FlatForward + ql.BlackConstantVol + ql.BlackScholesMertonProcess",
            family="Equity market model",
            factory="_create_equity_cliquet",
            signature=(
                "ql.FlatForward(today, q, dayCounter), ql.BlackConstantVol(today, calendar, vol, dayCounter), "
                "ql.BlackScholesMertonProcess(spot, dividendCurve, riskFreeCurve, volSurface)"
            ),
            purpose="Combines the shared SOFR discount curve with flat SPX dividend and volatility assumptions for the cliquet trade.",
            dependencies=["market.equity_spot", "market.equity_dividend_yield_pct", "market.equity_volatility_pct", "curve handle"],
            fields=[
                {"name": "spot", "value": f"{market['equity_spot']:.2f}", "notes": "Current S&P 500 index level"},
                {
                    "name": "dividendYield",
                    "value": f"{market['equity_dividend_yield_pct'] / 100.0:.6f}",
                    "notes": "Flat continuous dividend yield in decimal form",
                },
                {
                    "name": "riskFreeCurve",
                    "value": "ql.YieldTermStructureHandle(curve)",
                    "notes": "Shared SOFR curve reused as the discount curve for the equity trade",
                },
                {
                    "name": "flatVol",
                    "value": f"{market['equity_volatility_pct'] / 100.0:.6f}",
                    "notes": "Flat Black volatility in decimal form",
                },
                {
                    "name": "calendar",
                    "value": "ql.UnitedStates(ql.UnitedStates.NYSE)",
                    "notes": "Business-day adjustment for the SPX reset schedule",
                },
            ],
            enums=[_enum_member("ql.UnitedStates.NYSE", ql.UnitedStates.NYSE, "Equity reset calendar")],
        ),
        _component_card(
            title="ql.CliquetOption + ql.AnalyticCliquetEngine",
            family="Equity option stack",
            factory="_create_equity_cliquet",
            signature=(
                "ql.CliquetOption(ql.PercentageStrikePayoff(type, moneyness), "
                "ql.EuropeanExercise(maturity), resetDates), ql.AnalyticCliquetEngine(process)"
            ),
            purpose="Prices the SPX cliquet as a strip of forward-start percentage-strike options and exposes analytic Greeks.",
            dependencies=["ql.BlackScholesMertonProcess", "reset schedule", "trade quantity", "moneyness"],
            fields=[
                {
                    "name": "optionType",
                    "value": f"ql.Option.{trades['equity_cliquet']['option_type'].capitalize()}",
                    "notes": "Call or put strip across each reset period",
                },
                {
                    "name": "moneyness",
                    "value": f"{trades['equity_cliquet']['moneyness_pct'] / 100.0:.4f}",
                    "notes": "Percentage strike applied at each reset date",
                },
                {
                    "name": "quantity",
                    "value": f"{trades['equity_cliquet']['quantity']:.2f}",
                    "notes": "Number of SPX units multiplied by the unit cliquet price",
                },
                {
                    "name": "maturity",
                    "value": cliquet_maturity.ISO(),
                    "notes": "Final maturity date of the cliquet strip",
                },
                {
                    "name": "analyticGreeks",
                    "value": (
                        f"delta={cliquet_model['greeks']['delta']:.4f}, gamma={cliquet_model['greeks']['gamma']:.4f}, "
                        f"vega={cliquet_model['greeks']['vega']:.2f}"
                    ),
                    "notes": "Trade-level Greeks reported by QuantLib's analytic engine",
                },
            ],
            table={
                "headers": ["Period", "Start", "End", "Year frac", "Unit NPV", "Trade NPV"],
                "rows": [
                    {
                        "c1": row["period"],
                        "c2": row["start_date_iso"],
                        "c3": row["end_date_iso"],
                        "c4": f"{row['year_fraction']:.4f}",
                        "c5": f"{row['unit_npv']:.4f}",
                        "c6": f"{row['trade_npv']:.2f}",
                    }
                    for row in cliquet_model["period_rows"]
                ],
            },
            enums=[
                _enum_member("ql.Option.Call", ql.Option.Call, "Call cliquet leg"),
                _enum_member("ql.Option.Put", ql.Option.Put, "Put cliquet leg"),
            ],
        ),
        _component_card(
            title="ql.SwaptionHelper",
            family="Calibration helper strip",
            factory="build_bermudan_gsr_model",
            signature=(
                "ql.SwaptionHelper(maturity, length, volatility, index, fixedLegTenor, "
                "fixedLegDayCounter, floatingLegDayCounter, termStructure, errorType, strike, "
                "nominal, type, shift, settlementDays, averagingMethod)"
            ),
            purpose="Builds the diagonal ATM swaption strip used to calibrate the Bermudan Gaussian short-rate model.",
            dependencies=["diagonal market.swaption_vol_matrix_bp", "ql.Sofr(curveHandle)", "curve handle"],
            fields=[
                {"name": "index", "value": "ql.Sofr(curveHandle)", "notes": "Overnight index on the bootstrapped curve"},
                {"name": "fixedLegTenor", "value": "ql.Period('1Y')", "notes": "Annual fixed leg used by the helper swap"},
                {"name": "fixedLegDayCounter", "value": "ql.Actual360()", "notes": "Fixed-leg basis aligned to the workbook trade"},
                {"name": "floatingLegDayCounter", "value": "ql.Actual360()", "notes": "SOFR floating-leg basis"},
                {"name": "volatilityType", "value": "ql.Normal", "notes": "Helpers calibrate to ATM normal vols from the matrix"},
                {"name": "errorType", "value": "ql.BlackCalibrationHelper.RelativePriceError", "notes": "Calibration objective used by QuantLib"},
            ],
            table={
                "headers": ["Pillar", "Exercise", "Maturity", "Market vol (bp)", "Sigma seg (bp)", "Error"],
                "rows": [
                    {
                        "c1": row["label"],
                        "c2": row["exercise_date_iso"],
                        "c3": row["maturity_date_iso"],
                        "c4": f"{row['market_normal_vol_bp']:.1f}",
                        "c5": f"{row['segment_sigma_bp']:.2f}",
                        "c6": f"{row['calibration_error']:.6g}",
                    }
                    for row in bermudan_calibration_rows
                ],
            },
            enums=[
                _enum_member("ql.Normal", ql.Normal, "Normal-vol swaption helpers"),
                _enum_member("ql.RateAveraging.Compound", ql.RateAveraging.Compound, "SOFR compounding convention"),
            ],
        ),
        _component_card(
            title="ql.Gsr + ql.Gaussian1dSwaptionEngine",
            family="Callable calibration model",
            factory="build_bermudan_gsr_model",
            signature=(
                "ql.Gsr(termStructure, volstepdates, volatilities, reversions, T), "
                "ql.Gaussian1dSwaptionEngine(model, integrationPoints, stddevs, "
                "extrapolatePayoff, flatPayoffExtrapolation, discountCurve)"
            ),
            purpose="Fits a time-dependent sigma term structure to the feasible diagonal ATM strip and prices the Bermudan with the calibrated Gaussian model.",
            dependencies=["curve handle", "ql.SwaptionHelper strip", "Hull-White mean reversion"],
            fields=[
                {
                    "name": "volstepdates",
                    "value": ", ".join(row["exercise_date_iso"] for row in bermudan_calibration_rows) or "-",
                    "notes": "Annual diagonal expiry dates used as model volatility step dates",
                },
                {
                    "name": "meanReversion a",
                    "value": f"{bermudan_model['mean_reversion']:.4f}",
                    "notes": "Constant Hull-White mean reversion kept fixed during calibration",
                },
                {
                    "name": "integrationPoints",
                    "value": str(BERMUDAN_GSR_INTEGRATION_POINTS),
                    "notes": "Gaussian integration grid for the pricing engine",
                },
                {
                    "name": "stddevs",
                    "value": f"{BERMUDAN_GSR_STDDEVS:.1f}",
                    "notes": "Integration truncation width in standard deviations",
                },
                {
                    "name": "curveMaxDate",
                    "value": bermudan_model["curve_max_date_iso"],
                    "notes": "Upper horizon available from the bootstrapped SOFR curve",
                },
            ],
            table={
                "headers": ["Segment", "Start", "End", "Sigma (bp)"],
                "rows": [
                    {
                        "c1": row["segment"],
                        "c2": row["start_date_iso"],
                        "c3": row["end_date_iso"],
                        "c4": f"{row['sigma_bp']:.2f}",
                    }
                    for row in gsr_sigma_rows
                ],
            },
        ),
        _component_card(
            title="ql.BermudanExercise + ql.Swaption",
            family="Callable option stack",
            factory="_create_bermudan_swaption",
            signature="ql.BermudanExercise(dates), ql.Swaption(underlying, exercise)",
            purpose="Defines the Bermudan exercise schedule on top of the forward-starting swap; pricing is delegated to the calibrated Gaussian engine.",
            dependencies=["forward-starting ql.OvernightIndexedSwap", "exercise-date list", "ql.Gaussian1dSwaptionEngine"],
            fields=[
                {"name": "exerciseDates", "value": ", ".join(bermudan_exercise_dates), "notes": "Annual exercise dates until maturity"},
                {"name": "exerciseCount", "value": str(len(bermudan_exercise_dates)), "notes": "Actual exercise opportunities in the current trade"},
                {"name": "firstExercise", "value": bermudan_first_exercise.ISO(), "notes": "Spot plus non-call period"},
                {"name": "maturity", "value": bermudan_maturity.ISO(), "notes": "Fixed final maturity of the callable structure"},
            ],
        ),
        _component_card(
            title="ql.MakeOIS",
            family="Calibration instrument",
            factory="reprice_sofr_calibration_swaps",
            signature="ql.MakeOIS(swapTenor, overnightIndex, fixedRate, forwardStart)",
            purpose="Rebuilds quoted OIS pillars to confirm the curve reprices the input strip.",
            dependencies=["curve handle", "quoted OIS rates"],
            fields=[
                {"name": "overnightIndex", "value": "ql.Sofr(curveHandle)", "notes": "Calibration index attached to the bootstrapped curve"},
                {"name": "forwardStart", "value": "ql.Period(0, ql.Days)", "notes": "Start immediately from spot conventions"},
            ],
            table={
                "headers": ["Tenor", "Quote (%)", "Calibration object"],
                "rows": [
                    {
                        "c1": row["tenor"],
                        "c2": f"{row['quote_pct']:.2f}",
                        "c3": f"ql.MakeOIS(ql.Period('{row['tenor']}'), overnightIndex, {row['quote_pct'] / 100.0:.6f}, ql.Period(0, ql.Days))",
                    }
                    for row in curve_rows[1:]
                ],
            },
            enums=[_enum_member("ql.Days", ql.Days, "Time unit for forwardStart")],
        ),
    ]

    enum_sections = [
        {
            "title": "Calendars and conventions",
            "rows": [
                _enum_member("ql.UnitedStates.Settlement", ql.UnitedStates.Settlement, "Calendar market used across curve helpers and schedules"),
                _enum_member("ql.UnitedStates.NYSE", ql.UnitedStates.NYSE, "Calendar used for the SPX cliquet reset schedule"),
                _enum_member("ql.Following", ql.Following, "Deposit helper business-day convention"),
                _enum_member("ql.ModifiedFollowing", ql.ModifiedFollowing, "Schedule convention for swaps"),
                _enum_member("ql.DateGeneration.Forward", ql.DateGeneration.Forward, "Schedule generation rule"),
            ],
        },
        {
            "title": "Swap and day-count enums",
            "rows": [
                _enum_member("ql.OvernightIndexedSwap.Payer", ql.OvernightIndexedSwap.Payer, "Pay fixed / receive floating"),
                _enum_member("ql.OvernightIndexedSwap.Receiver", ql.OvernightIndexedSwap.Receiver, "Receive fixed / pay floating"),
                _enum_member("ql.Annual", ql.Annual, "Annual compounding/frequency enum used for zero-rate extraction"),
                _enum_member("ql.Normal", ql.Normal, "Normal-volatility type used for swaption calibration helpers"),
                _enum_member("ql.RateAveraging.Compound", ql.RateAveraging.Compound, "SOFR averaging method used by swaption helpers"),
            ],
        },
        {
            "title": "Time units",
            "rows": [
                _enum_member("ql.Days", ql.Days, "Overnight helper and one-day forward strip"),
                _enum_member("ql.Years", ql.Years, "OIS maturities and trade tenors"),
            ],
        },
    ]

    overview_cards = [
        {
            "label": "Curve helpers",
            "value": str(len(SOFR_CURVE_POINT_SPECS)),
            "detail": "1 deposit helper plus the workbook OIS strip",
        },
        {"label": "Priced instruments", "value": "4", "detail": "swap + European swaption + Bermudan swaption + SPX cliquet"},
        {"label": "Pricing engines", "value": "4", "detail": "discounting, Bachelier, Gaussian1d, analytic cliquet"},
        {
            "label": "Bermudan diag helpers",
            "value": str(len(bermudan_calibration_rows)),
            "detail": bermudan_calibration_rows[-1]["label"] if bermudan_calibration_rows else "none",
        },
        {
            "label": "Cliquet periods",
            "value": str(cliquet_model["reset_count"]),
            "detail": f"{cliquet_model['maturity_date_iso']} maturity",
        },
        {"label": "Curve outputs", "value": f"{len(curve_node_rows)} + {len(forward_points)}", "detail": "zero-rate nodes and one-day forwards shown on the dashboard"},
    ]

    research_sections = list(SWAPTION_RESEARCH_SECTIONS) + [CLIQUET_RESEARCH_SECTION]

    return {
        "overview_cards": overview_cards,
        "object_flow": object_flow,
        "state_sections": state_sections,
        "curve_rows": curve_rows,
        "curve_node_rows": curve_node_rows,
        "forward_summary_rows": forward_summary_rows,
        "bermudan_calibration_rows": bermudan_calibration_rows,
        "swaption_matrix_headers": list(SWAPTION_MATRIX_TENOR_LABELS),
        "swaption_matrix_rows": swaption_matrix_rows,
        "component_cards": component_cards,
        "enum_sections": enum_sections,
        "research_sections": research_sections,
        "curve_reference_date": curve.referenceDate().ISO(),
        "dashboard_url": url_for("workbench.dashboard"),
        "curve_debug_csv_url": url_for("workbench.curve_debug_download"),
        "curve_debug_csv_repo_path": current_app.config["CURVE_DEBUG_CSV_PATH"],
    }
