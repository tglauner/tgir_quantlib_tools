import QuantLib as ql
import pandas as pd


def build_sofr_curve(today, sofr_rates):
    helpers = [
        ql.DepositRateHelper(
            ql.QuoteHandle(ql.SimpleQuote(rate / 100)),
            ql.Period(i + 1, ql.Years),
            2,
            ql.UnitedStates(ql.UnitedStates.Settlement),
            ql.ModifiedFollowing,
            False,
            ql.Actual360(),
        )
        for i, rate in enumerate(sofr_rates)
    ]
    curve = ql.PiecewiseLinearZero(today, helpers, ql.Actual360())
    return curve

def create_swap(start, maturity, rate, curve):
    fixed_leg_tenor = ql.Period('1Y')
    fixed_schedule = ql.Schedule(start, maturity, fixed_leg_tenor,
                                 ql.UnitedStates(ql.UnitedStates.Settlement),
                                 ql.ModifiedFollowing, ql.ModifiedFollowing,
                                 ql.DateGeneration.Forward, False)
    float_schedule = fixed_schedule
    swap = ql.VanillaSwap(ql.VanillaSwap.Payer, 1000000,
                          fixed_schedule, rate/100, ql.Thirty360(ql.Thirty360.BondBasis),
                          float_schedule, ql.Sofr(ql.YieldTermStructureHandle(curve)), 0.0, ql.Actual360())
    engine = ql.DiscountingSwapEngine(ql.YieldTermStructureHandle(curve))
    swap.setPricingEngine(engine)
    return swap

def create_european_swaption(swap, curve, exercise_date):
    exercise = ql.EuropeanExercise(exercise_date)
    swaption = ql.Swaption(swap, exercise)
    model = ql.BlackSwaptionEngine(
        ql.YieldTermStructureHandle(curve),
        ql.QuoteHandle(ql.SimpleQuote(0.01))
    )
    swaption.setPricingEngine(model)
    return swaption

def create_bermudan_swaption(swap, curve, exercise_dates):
    exercise = ql.BermudanExercise(exercise_dates)
    swaption = ql.Swaption(swap, exercise)
    model = ql.HullWhite(ql.YieldTermStructureHandle(curve))
    engine = ql.TreeSwaptionEngine(model, 50)
    swaption.setPricingEngine(engine)
    return swaption


def price_portfolio(sofr_rates):
    today = ql.Date.todaysDate()
    ql.Settings.instance().evaluationDate = today
    curve = build_sofr_curve(today, sofr_rates)
    calendar = ql.UnitedStates(ql.UnitedStates.Settlement)

    # Start the live swap on a business-day spot date so the first coupon
    # does not require historical SOFR fixings that this demo app does not load.
    swap_start = calendar.advance(today, 2, ql.Days)
    swap = create_swap(
        swap_start,
        calendar.advance(swap_start, 5, ql.Years),
        3.0,
        curve,
    )

    # Forward-starting swap used for swaptions
    swaption_start = calendar.advance(swap_start, 1, ql.Years)
    swaption_swap = create_swap(
        swaption_start,
        calendar.advance(swaption_start, 4, ql.Years),
        3.0,
        curve,
    )

    european_swaption = create_european_swaption(
        swaption_swap, curve, swaption_start)
    bermudan_dates = [
        calendar.advance(swaption_start, i, ql.Years) for i in range(1, 4)
    ]
    bermudan_swaption = create_bermudan_swaption(swaption_swap, curve, bermudan_dates)

    securities = [
        {'Type': 'Swap', 'NPV': swap.NPV()},
        {'Type': 'European Swaption', 'NPV': european_swaption.NPV()},
        {'Type': 'Bermudan Swaption', 'NPV': bermudan_swaption.NPV()}
    ]
    return pd.DataFrame(securities)
