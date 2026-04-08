import math
import unittest

import QuantLib as ql


def _normal_cdf(value):
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _flat_process(today, spot, risk_free_rate, dividend_yield, volatility):
    return ql.BlackScholesMertonProcess(
        ql.QuoteHandle(ql.SimpleQuote(spot)),
        ql.YieldTermStructureHandle(ql.FlatForward(today, dividend_yield, ql.Actual365Fixed())),
        ql.YieldTermStructureHandle(ql.FlatForward(today, risk_free_rate, ql.Actual365Fixed())),
        ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(today, ql.NullCalendar(), volatility, ql.Actual365Fixed())
        ),
    )


def _cliquet_price(today, option_type, spot, risk_free_rate, dividend_yield, volatility, moneyness, reset_dates, maturity):
    ql.Settings.instance().evaluationDate = today
    process = _flat_process(today, spot, risk_free_rate, dividend_yield, volatility)
    option = ql.CliquetOption(
        ql.PercentageStrikePayoff(option_type, moneyness),
        ql.EuropeanExercise(maturity),
        reset_dates,
    )
    option.setPricingEngine(ql.AnalyticCliquetEngine(process))
    return option.NPV()


def _vanilla_price(today, option_type, spot, risk_free_rate, dividend_yield, volatility, strike, maturity):
    ql.Settings.instance().evaluationDate = today
    process = _flat_process(today, spot, risk_free_rate, dividend_yield, volatility)
    option = ql.VanillaOption(
        ql.PlainVanillaPayoff(option_type, strike),
        ql.EuropeanExercise(maturity),
    )
    option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
    return option.NPV()


def _forward_start_strip_price(today, option_type, spot, risk_free_rate, dividend_yield, volatility, moneyness, period_dates):
    ql.Settings.instance().evaluationDate = today
    risk_free_curve = ql.FlatForward(today, risk_free_rate, ql.Actual365Fixed())
    dividend_curve = ql.FlatForward(today, dividend_yield, ql.Actual365Fixed())
    day_count = ql.Actual365Fixed()
    total_price = 0.0

    for start_date, end_date in zip(period_dates[:-1], period_dates[1:]):
        tau = day_count.yearFraction(start_date, end_date)
        discount_to_start = risk_free_curve.discount(start_date)
        discount_to_end = risk_free_curve.discount(end_date)
        dividend_to_start = dividend_curve.discount(start_date)
        dividend_to_end = dividend_curve.discount(end_date)
        discount_period = discount_to_end / discount_to_start
        dividend_period = dividend_to_end / dividend_to_start
        forward_ratio = dividend_period / discount_period

        if volatility <= 0.0:
            intrinsic = max(
                (forward_ratio - moneyness) if option_type == ql.Option.Call else (moneyness - forward_ratio),
                0.0,
            )
            total_price += spot * dividend_to_start * discount_period * intrinsic
            continue

        std_dev = volatility * math.sqrt(tau)
        d1 = (math.log(forward_ratio / moneyness) + 0.5 * volatility * volatility * tau) / std_dev
        d2 = d1 - std_dev
        if option_type == ql.Option.Call:
            total_price += spot * dividend_to_start * (
                dividend_period * _normal_cdf(d1) - moneyness * discount_period * _normal_cdf(d2)
            )
        else:
            total_price += spot * dividend_to_start * (
                moneyness * discount_period * _normal_cdf(-d2) - dividend_period * _normal_cdf(-d1)
            )

    return total_price


class CliquetIdentityTests(unittest.TestCase):
    def setUp(self):
        self.today = ql.Date(5, 4, 2026)
        ql.Settings.instance().evaluationDate = self.today

    def test_cliquet_identity_portfolio(self):
        today = self.today
        one_year = today + ql.Period(1, ql.Years)
        three_months = today + ql.Period(3, ql.Months)
        six_months = today + ql.Period(6, ql.Months)
        nine_months = today + ql.Period(9, ql.Months)
        quarter_1 = today + 90
        quarter_2 = today + 180
        quarter_3 = today + 270
        quarter_4 = today + 360

        cases = [
            {
                "name": "single-period ATM call reduces to vanilla call",
                "type": ql.Option.Call,
                "spot": 100.0,
                "r": 0.04,
                "q": 0.01,
                "vol": 0.20,
                "moneyness": 1.0,
                "reset_dates": [today],
                "maturity": one_year,
                "expected": lambda c: _vanilla_price(
                    today,
                    c["type"],
                    c["spot"],
                    c["r"],
                    c["q"],
                    c["vol"],
                    c["spot"] * c["moneyness"],
                    c["maturity"],
                ),
                "tol": 1e-10,
            },
            {
                "name": "single-period ATM put reduces to vanilla put",
                "type": ql.Option.Put,
                "spot": 100.0,
                "r": 0.04,
                "q": 0.01,
                "vol": 0.20,
                "moneyness": 1.0,
                "reset_dates": [today],
                "maturity": one_year,
                "expected": lambda c: _vanilla_price(
                    today,
                    c["type"],
                    c["spot"],
                    c["r"],
                    c["q"],
                    c["vol"],
                    c["spot"] * c["moneyness"],
                    c["maturity"],
                ),
                "tol": 1e-10,
            },
            {
                "name": "single-period 110pct call reduces to OTM vanilla call",
                "type": ql.Option.Call,
                "spot": 100.0,
                "r": 0.03,
                "q": 0.00,
                "vol": 0.25,
                "moneyness": 1.10,
                "reset_dates": [today],
                "maturity": one_year,
                "expected": lambda c: _vanilla_price(
                    today,
                    c["type"],
                    c["spot"],
                    c["r"],
                    c["q"],
                    c["vol"],
                    c["spot"] * c["moneyness"],
                    c["maturity"],
                ),
                "tol": 1e-10,
            },
            {
                "name": "single-period 90pct put reduces to ITM vanilla put",
                "type": ql.Option.Put,
                "spot": 100.0,
                "r": 0.03,
                "q": 0.00,
                "vol": 0.25,
                "moneyness": 0.90,
                "reset_dates": [today],
                "maturity": one_year,
                "expected": lambda c: _vanilla_price(
                    today,
                    c["type"],
                    c["spot"],
                    c["r"],
                    c["q"],
                    c["vol"],
                    c["spot"] * c["moneyness"],
                    c["maturity"],
                ),
                "tol": 1e-10,
            },
            {
                "name": "two-period call equals sum of two forward-start calls",
                "type": ql.Option.Call,
                "spot": 100.0,
                "r": 0.05,
                "q": 0.02,
                "vol": 0.20,
                "moneyness": 1.0,
                "reset_dates": [today, six_months],
                "maturity": one_year,
                "expected": lambda c: _forward_start_strip_price(
                    today,
                    c["type"],
                    c["spot"],
                    c["r"],
                    c["q"],
                    c["vol"],
                    c["moneyness"],
                    [today, six_months, one_year],
                ),
                "tol": 5e-10,
            },
            {
                "name": "two-period put equals sum of two forward-start puts",
                "type": ql.Option.Put,
                "spot": 100.0,
                "r": 0.05,
                "q": 0.02,
                "vol": 0.20,
                "moneyness": 1.0,
                "reset_dates": [today, six_months],
                "maturity": one_year,
                "expected": lambda c: _forward_start_strip_price(
                    today,
                    c["type"],
                    c["spot"],
                    c["r"],
                    c["q"],
                    c["vol"],
                    c["moneyness"],
                    [today, six_months, one_year],
                ),
                "tol": 5e-10,
            },
            {
                "name": "four equal-quarter call strip collapses to four identical quarter calls when q is zero",
                "type": ql.Option.Call,
                "spot": 100.0,
                "r": 0.03,
                "q": 0.00,
                "vol": 0.18,
                "moneyness": 1.0,
                "reset_dates": [today, quarter_1, quarter_2, quarter_3],
                "maturity": quarter_4,
                "expected": lambda c: 4.0
                * _cliquet_price(
                    today,
                    c["type"],
                    c["spot"],
                    c["r"],
                    c["q"],
                    c["vol"],
                    c["moneyness"],
                    [today],
                    quarter_1,
                ),
                "tol": 2e-7,
            },
            {
                "name": "four equal-quarter put strip collapses to four identical quarter puts when q is zero",
                "type": ql.Option.Put,
                "spot": 100.0,
                "r": 0.03,
                "q": 0.00,
                "vol": 0.18,
                "moneyness": 1.0,
                "reset_dates": [today, quarter_1, quarter_2, quarter_3],
                "maturity": quarter_4,
                "expected": lambda c: 4.0
                * _cliquet_price(
                    today,
                    c["type"],
                    c["spot"],
                    c["r"],
                    c["q"],
                    c["vol"],
                    c["moneyness"],
                    [today],
                    quarter_1,
                ),
                "tol": 2e-7,
            },
            {
                "name": "zero-volatility call strip reduces to discounted deterministic intrinsic values",
                "type": ql.Option.Call,
                "spot": 100.0,
                "r": 0.04,
                "q": 0.01,
                "vol": 0.0,
                "moneyness": 1.0,
                "reset_dates": [today, six_months],
                "maturity": one_year,
                "expected": lambda c: _forward_start_strip_price(
                    today,
                    c["type"],
                    c["spot"],
                    c["r"],
                    c["q"],
                    c["vol"],
                    c["moneyness"],
                    [today, six_months, one_year],
                ),
                "tol": 1e-10,
            },
            {
                "name": "zero-volatility put strip reduces to discounted deterministic intrinsic values",
                "type": ql.Option.Put,
                "spot": 100.0,
                "r": 0.01,
                "q": 0.05,
                "vol": 0.0,
                "moneyness": 1.0,
                "reset_dates": [today, six_months],
                "maturity": one_year,
                "expected": lambda c: _forward_start_strip_price(
                    today,
                    c["type"],
                    c["spot"],
                    c["r"],
                    c["q"],
                    c["vol"],
                    c["moneyness"],
                    [today, six_months, one_year],
                ),
                "tol": 1e-10,
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                cliquet_value = _cliquet_price(
                    today,
                    case["type"],
                    case["spot"],
                    case["r"],
                    case["q"],
                    case["vol"],
                    case["moneyness"],
                    case["reset_dates"],
                    case["maturity"],
                )
                expected_value = case["expected"](case)
                self.assertAlmostEqual(cliquet_value, expected_value, delta=case["tol"])


if __name__ == "__main__":
    unittest.main()
