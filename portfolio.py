import copy

import QuantLib as ql
import pandas as pd

SOFR_OVERNIGHT_DEFAULT_PCT = 4.85
SOFR_OIS_TENORS_YEARS = (1, 2, 3, 5, 7, 10, 12)
SOFR_CURVE_TENOR_LABELS = ("ON",) + tuple(f"{tenor}Y" for tenor in SOFR_OIS_TENORS_YEARS)
SOFR_DEFAULT_CURVE_QUOTES_PCT = (
    SOFR_OVERNIGHT_DEFAULT_PCT,
    4.98,
    5.04,
    5.09,
    5.17,
    5.22,
    5.28,
    5.31,
)

SWAPTION_MATRIX_EXPIRY_YEARS = tuple(range(1, 11))
SWAPTION_MATRIX_TENOR_YEARS = tuple(range(1, 11))
DEFAULT_CALLABLE_NORMAL_VOL_BP = 55.0

BERMUDAN_GRID_MATURITIES_YEARS = (2, 3, 5, 7, 10)
BERMUDAN_GRID_NONCALL_YEARS = tuple(range(1, 10))

TRADE_SEQUENCE = ("swap", "european_swaption", "bermudan_swaption")
TRADE_TITLES = {
    "swap": "Swap",
    "european_swaption": "European Swaption",
    "bermudan_swaption": "Bermudan Swaption",
}


def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _direction_or_default(value, default="payer"):
    return value if value in {"payer", "receiver"} else default


def _default_swaption_normal_vol_matrix_bp(base_vol_bp=62.0):
    matrix = []
    for expiry_years in SWAPTION_MATRIX_EXPIRY_YEARS:
        row = []
        for tenor_years in SWAPTION_MATRIX_TENOR_YEARS:
            level = (
                float(base_vol_bp)
                + 1.8 * (expiry_years - 1)
                + 1.1 * (tenor_years - 1)
                - 0.15 * abs(expiry_years - tenor_years)
            )
            row.append(round(level, 1))
        matrix.append(row)
    return matrix


def _normalize_curve_quotes(quotes):
    if not isinstance(quotes, list):
        return list(SOFR_DEFAULT_CURVE_QUOTES_PCT)

    if len(quotes) == len(SOFR_DEFAULT_CURVE_QUOTES_PCT):
        return [_safe_float(quote, default) for quote, default in zip(quotes, SOFR_DEFAULT_CURVE_QUOTES_PCT)]

    if len(quotes) == len(SOFR_OIS_TENORS_YEARS):
        return [SOFR_OVERNIGHT_DEFAULT_PCT] + [
            _safe_float(quote, default)
            for quote, default in zip(quotes, SOFR_DEFAULT_CURVE_QUOTES_PCT[1:])
        ]

    if len(quotes) == 6:
        overnight, one_year, two_year, three_year, five_year, ten_year = [
            _safe_float(quote, default)
            for quote, default in zip(
                quotes,
                (
                    SOFR_OVERNIGHT_DEFAULT_PCT,
                    SOFR_DEFAULT_CURVE_QUOTES_PCT[1],
                    SOFR_DEFAULT_CURVE_QUOTES_PCT[2],
                    SOFR_DEFAULT_CURVE_QUOTES_PCT[3],
                    SOFR_DEFAULT_CURVE_QUOTES_PCT[4],
                    SOFR_DEFAULT_CURVE_QUOTES_PCT[6],
                ),
            )
        ]
        seven_year = round((five_year + ten_year) / 2.0, 4)
        twelve_year = round(ten_year + max((ten_year - five_year) * 0.4, 0.03), 4)
        return [
            overnight,
            one_year,
            two_year,
            three_year,
            five_year,
            seven_year,
            ten_year,
            twelve_year,
        ]

    if len(quotes) == 5:
        return _normalize_curve_quotes([SOFR_OVERNIGHT_DEFAULT_PCT] + list(quotes))

    return list(SOFR_DEFAULT_CURVE_QUOTES_PCT)


def _normalize_swaption_vol_matrix(matrix_like, base_vol_bp):
    defaults = _default_swaption_normal_vol_matrix_bp(base_vol_bp)
    if not isinstance(matrix_like, list):
        return defaults

    matrix = []
    for expiry_idx in range(len(SWAPTION_MATRIX_EXPIRY_YEARS)):
        raw_row = matrix_like[expiry_idx] if expiry_idx < len(matrix_like) else []
        if not isinstance(raw_row, list):
            raw_row = []
        row = []
        for tenor_idx in range(len(SWAPTION_MATRIX_TENOR_YEARS)):
            default_value = defaults[expiry_idx][tenor_idx]
            try:
                row.append(float(raw_row[tenor_idx]))
            except (IndexError, TypeError, ValueError):
                row.append(default_value)
        matrix.append(row)
    return matrix


def _clamp_year(years, minimum, maximum):
    return max(minimum, min(int(years), maximum))


def lookup_swaption_normal_vol_bp(portfolio_state, expiry_years, swap_tenor_years):
    state = normalize_portfolio_state(portfolio_state)
    expiry_index = _clamp_year(expiry_years, 1, len(SWAPTION_MATRIX_EXPIRY_YEARS)) - 1
    tenor_index = _clamp_year(swap_tenor_years, 1, len(SWAPTION_MATRIX_TENOR_YEARS)) - 1
    return float(state["market"]["swaption_vol_matrix_bp"][expiry_index][tenor_index])


def default_portfolio_state():
    return copy.deepcopy(
        {
            "market": {
                "curve_quotes_pct": list(SOFR_DEFAULT_CURVE_QUOTES_PCT),
                "callable_normal_vol_bp": DEFAULT_CALLABLE_NORMAL_VOL_BP,
                "swaption_vol_matrix_bp": _default_swaption_normal_vol_matrix_bp(),
            },
            "trades": {
                "swap": {
                    "direction": "payer",
                    "notional": 1_000_000,
                    "fixed_rate_pct": 3.0,
                    "tenor_years": 5,
                },
                "european_swaption": {
                    "direction": "payer",
                    "notional": 1_000_000,
                    "strike_pct": 3.0,
                    "expiry_years": 1,
                    "swap_tenor_years": 4,
                },
                "bermudan_swaption": {
                    "direction": "payer",
                    "notional": 1_000_000,
                    "strike_pct": 3.0,
                    "first_exercise_years": 1,
                    "swap_tenor_years": 4,
                    "exercise_count": 3,
                },
            },
        }
    )


def normalize_portfolio_state(portfolio_state=None):
    state = default_portfolio_state()
    if not portfolio_state:
        return state

    if isinstance(portfolio_state, list):
        state["market"]["curve_quotes_pct"] = _normalize_curve_quotes(portfolio_state)
        return state

    market = portfolio_state.get("market", {})
    state["market"]["curve_quotes_pct"] = _normalize_curve_quotes(
        market.get("curve_quotes_pct", state["market"]["curve_quotes_pct"])
    )

    callable_normal_vol_bp = market.get(
        "callable_normal_vol_bp",
        market.get("normal_vol_bp", state["market"]["callable_normal_vol_bp"]),
    )
    try:
        state["market"]["callable_normal_vol_bp"] = max(float(callable_normal_vol_bp), 0.0)
    except (TypeError, ValueError):
        state["market"]["callable_normal_vol_bp"] = DEFAULT_CALLABLE_NORMAL_VOL_BP

    state["market"]["swaption_vol_matrix_bp"] = _normalize_swaption_vol_matrix(
        market.get("swaption_vol_matrix_bp"),
        max(state["market"]["callable_normal_vol_bp"] + 7.0, 62.0),
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

    state["trades"]["bermudan_swaption"]["direction"] = _direction_or_default(
        state["trades"]["bermudan_swaption"]["direction"],
        "payer",
    )
    state["trades"]["bermudan_swaption"]["notional"] = max(
        _safe_float(state["trades"]["bermudan_swaption"]["notional"], 1_000_000),
        1.0,
    )
    state["trades"]["bermudan_swaption"]["strike_pct"] = _safe_float(
        state["trades"]["bermudan_swaption"]["strike_pct"],
        3.0,
    )
    state["trades"]["bermudan_swaption"]["first_exercise_years"] = _clamp_year(
        state["trades"]["bermudan_swaption"]["first_exercise_years"],
        1,
        9,
    )
    state["trades"]["bermudan_swaption"]["swap_tenor_years"] = _clamp_year(
        state["trades"]["bermudan_swaption"]["swap_tenor_years"],
        1,
        10,
    )
    state["trades"]["bermudan_swaption"]["exercise_count"] = _clamp_year(
        state["trades"]["bermudan_swaption"]["exercise_count"],
        1,
        9,
    )

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
    overnight_quote = normalized_quotes[0]
    ois_quotes = normalized_quotes[1:]

    helpers = [
        ql.DepositRateHelper(
            ql.QuoteHandle(ql.SimpleQuote(overnight_quote / 100.0)),
            ql.Period(1, ql.Days),
            0,
            calendar,
            ql.Following,
            False,
            ql.Actual360(),
        )
    ]
    helpers.extend(
        ql.OISRateHelper(
            2,
            ql.Period(tenor_years, ql.Years),
            ql.QuoteHandle(ql.SimpleQuote(rate / 100.0)),
            ql.Sofr(),
        )
        for tenor_years, rate in zip(SOFR_OIS_TENORS_YEARS, ois_quotes)
    )
    return ql.PiecewiseLogCubicDiscount(today, helpers, ql.Actual360())


def _fixed_leg_direction(direction):
    return ql.VanillaSwap.Payer if direction == "payer" else ql.VanillaSwap.Receiver


def _spot_start_date(today, calendar):
    return calendar.advance(today, 2, ql.Days)


def _make_vanilla_swap(start, maturity, direction, notional, fixed_rate_pct, curve_handle):
    fixed_schedule = ql.Schedule(
        start,
        maturity,
        ql.Period("1Y"),
        ql.UnitedStates(ql.UnitedStates.Settlement),
        ql.ModifiedFollowing,
        ql.ModifiedFollowing,
        ql.DateGeneration.Forward,
        False,
    )
    float_schedule = fixed_schedule
    swap = ql.VanillaSwap(
        _fixed_leg_direction(direction),
        float(notional),
        fixed_schedule,
        fixed_rate_pct / 100.0,
        ql.Thirty360(ql.Thirty360.BondBasis),
        float_schedule,
        ql.Sofr(curve_handle),
        0.0,
        ql.Actual360(),
    )
    swap.setPricingEngine(ql.DiscountingSwapEngine(curve_handle))
    return swap


def _market_context(portfolio_state):
    state = normalize_portfolio_state(portfolio_state)
    today = ql.Date.todaysDate()
    ql.Settings.instance().evaluationDate = today
    curve = build_sofr_curve(today, state["market"]["curve_quotes_pct"])
    curve_handle = ql.YieldTermStructureHandle(curve)
    calendar = ql.UnitedStates(ql.UnitedStates.Settlement)
    return state, today, calendar, curve, curve_handle


def _format_notional(notional):
    if abs(notional) >= 1_000_000:
        return f"${notional / 1_000_000:.2f}mm"
    if abs(notional) >= 1_000:
        return f"${notional / 1_000:.0f}k"
    return f"${notional:,.0f}"


def trade_structure_summary(trade_type, trade, market):
    if trade_type == "swap":
        fixed_side = "Pay fixed" if trade["direction"] == "payer" else "Receive fixed"
        return (
            f"{fixed_side} | {trade['tenor_years']}Y | "
            f"{trade['fixed_rate_pct']:.2f}% | {_format_notional(trade['notional'])}"
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
            f"K {trade['strike_pct']:.2f}% | ATM {matrix_vol_bp:.1f}bp"
        )

    option_side = "Payer" if trade["direction"] == "payer" else "Receiver"
    return (
        f"{option_side} | {trade['first_exercise_years']}NC into "
        f"{trade['swap_tenor_years']}Y | {trade['exercise_count']} dates | "
        f"Flat {market['callable_normal_vol_bp']:.1f}bp"
    )


def trade_card_summary(trade_type, trade, market):
    if trade_type == "swap":
        headline = "Pay fixed" if trade["direction"] == "payer" else "Receive fixed"
        detail = (
            f"{trade['tenor_years']}Y maturity, {trade['fixed_rate_pct']:.2f}% fixed, "
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
            f"ATM {matrix_vol_bp:.1f}bp matrix"
        )
        return headline, detail

    headline = (
        f"{trade['first_exercise_years']}NC into {trade['swap_tenor_years']}Y "
        f"with {trade['exercise_count']} dates"
    )
    detail = (
        f"{'Payer' if trade['direction'] == 'payer' else 'Receiver'} style, "
        f"K {trade['strike_pct']:.2f}%, {_format_notional(trade['notional'])}, "
        f"flat callable {market['callable_normal_vol_bp']:.1f}bp"
    )
    return headline, detail


def _create_live_swap(trade, today, calendar, curve_handle):
    start = _spot_start_date(today, calendar)
    maturity = calendar.advance(start, int(trade["tenor_years"]), ql.Years)
    return _make_vanilla_swap(
        start,
        maturity,
        trade["direction"],
        trade["notional"],
        trade["fixed_rate_pct"],
        curve_handle,
    )


def _create_forward_swap(trade, start, maturity, curve_handle):
    return _make_vanilla_swap(
        start,
        maturity,
        trade["direction"],
        trade["notional"],
        trade["strike_pct"],
        curve_handle,
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


def _bermudan_exercise_dates(start, maturity, calendar, requested_count):
    exercise_dates = []
    for step in range(max(1, int(requested_count))):
        exercise_date = calendar.advance(start, step, ql.Years)
        if exercise_date < maturity:
            exercise_dates.append(exercise_date)
    if not exercise_dates:
        exercise_dates.append(start)
    return exercise_dates


def _create_bermudan_swaption(trade, today, calendar, curve_handle, normal_vol_bp):
    spot = _spot_start_date(today, calendar)
    first_exercise = calendar.advance(spot, int(trade["first_exercise_years"]), ql.Years)
    maturity = calendar.advance(first_exercise, int(trade["swap_tenor_years"]), ql.Years)
    underlying = _create_forward_swap(trade, first_exercise, maturity, curve_handle)
    exercise = ql.BermudanExercise(
        _bermudan_exercise_dates(
            first_exercise,
            maturity,
            calendar,
            trade["exercise_count"],
        )
    )
    model = ql.HullWhite(curve_handle, 0.03, _normal_vol_from_bp(normal_vol_bp))
    swaption = ql.Swaption(underlying, exercise)
    swaption.setPricingEngine(ql.TreeSwaptionEngine(model, 80))
    return swaption


def reprice_sofr_calibration_swaps(curve, sofr_rates, tenors_years=SOFR_OIS_TENORS_YEARS):
    normalized_quotes = _normalize_curve_quotes(list(sofr_rates))
    curve_handle = ql.YieldTermStructureHandle(curve)
    engine = ql.DiscountingSwapEngine(curve_handle)
    overnight_index = ql.Sofr(curve_handle)
    market_quotes = dict(zip(SOFR_OIS_TENORS_YEARS, normalized_quotes[1:]))
    repriced_swaps = []

    for tenor_years in tenors_years:
        fixed_rate = market_quotes[tenor_years]
        swap = ql.MakeOIS(
            ql.Period(tenor_years, ql.Years),
            overnight_index,
            fixed_rate / 100.0,
            ql.Period(0, ql.Days),
        )
        swap.setPricingEngine(engine)
        repriced_swaps.append(
            {
                "Tenor": f"{tenor_years}Y",
                "Market Quote (%)": fixed_rate,
                "Fair Rate (%)": swap.fairRate() * 100.0,
                "NPV": swap.NPV(),
            }
        )

    return pd.DataFrame(repriced_swaps)


def build_bermudan_pricing_grid(portfolio_state=None):
    state, today, calendar, _curve, curve_handle = _market_context(portfolio_state)
    template_trade = state["trades"]["bermudan_swaption"]
    callable_normal_vol_bp = state["market"]["callable_normal_vol_bp"]
    rows = []

    for noncall_years in BERMUDAN_GRID_NONCALL_YEARS:
        row = {"Non-call": f"{noncall_years}Y"}
        for maturity_years in BERMUDAN_GRID_MATURITIES_YEARS:
            if noncall_years >= maturity_years:
                row[f"{maturity_years}Y"] = None
                continue
            trade = dict(template_trade)
            trade["first_exercise_years"] = noncall_years
            trade["swap_tenor_years"] = maturity_years - noncall_years
            trade["exercise_count"] = maturity_years - noncall_years
            row[f"{maturity_years}Y"] = _create_bermudan_swaption(
                trade,
                today,
                calendar,
                curve_handle,
                callable_normal_vol_bp,
            ).NPV()
        rows.append(row)

    return pd.DataFrame(rows)


def price_portfolio(portfolio_state=None):
    state, today, calendar, _curve, curve_handle = _market_context(portfolio_state)
    market = state["market"]
    trades = state["trades"]

    european_matrix_vol_bp = lookup_swaption_normal_vol_bp(
        state,
        trades["european_swaption"]["expiry_years"],
        trades["european_swaption"]["swap_tenor_years"],
    )
    callable_normal_vol_bp = market["callable_normal_vol_bp"]

    swap = _create_live_swap(trades["swap"], today, calendar, curve_handle)
    european_swaption = _create_european_swaption(
        trades["european_swaption"],
        today,
        calendar,
        curve_handle,
        european_matrix_vol_bp,
    )
    bermudan_swaption = _create_bermudan_swaption(
        trades["bermudan_swaption"],
        today,
        calendar,
        curve_handle,
        callable_normal_vol_bp,
    )

    securities = [
        {
            "TradeKey": "swap",
            "Type": TRADE_TITLES["swap"],
            "Structure": trade_structure_summary("swap", trades["swap"], market),
            "MTM": swap.NPV(),
            "NPV": swap.NPV(),
        },
        {
            "TradeKey": "european_swaption",
            "Type": TRADE_TITLES["european_swaption"],
            "Structure": trade_structure_summary(
                "european_swaption",
                trades["european_swaption"],
                market,
            ),
            "MTM": european_swaption.NPV(),
            "NPV": european_swaption.NPV(),
        },
        {
            "TradeKey": "bermudan_swaption",
            "Type": TRADE_TITLES["bermudan_swaption"],
            "Structure": trade_structure_summary(
                "bermudan_swaption",
                trades["bermudan_swaption"],
                market,
            ),
            "MTM": bermudan_swaption.NPV(),
            "NPV": bermudan_swaption.NPV(),
        },
    ]
    return pd.DataFrame(securities)
