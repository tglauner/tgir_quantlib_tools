from datetime import datetime

import QuantLib as ql
import pandas as pd

from portfolio import (
    SOFR_CURVE_TENOR_LABELS,
    build_sofr_curve,
    default_portfolio_state,
    reprice_sofr_calibration_swaps,
    valuation_date,
)


def main() -> None:
    state = default_portfolio_state()
    today = valuation_date(state)
    ql.Settings.instance().evaluationDate = today
    sofr_quotes = state["market"]["curve_quotes_pct"]
    sofr_curve = build_sofr_curve(today, sofr_quotes)
    sofr_handle = ql.YieldTermStructureHandle(sofr_curve)

    print("SOFR Discount Factors:")
    overnight_date = today + ql.Period(1, ql.Days)
    print(f"{SOFR_CURVE_TENOR_LABELS[0]}: {sofr_handle.discount(overnight_date):.6f}")
    for tenor_label in ["1M", "3M", "1Y", "5Y", "10Y", "30Y"]:
        curve_date = today + ql.Period(tenor_label)
        print(f"{tenor_label}: {sofr_handle.discount(curve_date):.6f}")

    dates = []
    discount_factors = []
    for day_offset in range(366):
        curve_date = today + day_offset
        dates.append(datetime(curve_date.year(), curve_date.month(), curve_date.dayOfMonth()))
        discount_factors.append(sofr_handle.discount(curve_date))

    daily_curve = pd.DataFrame({"Date": dates, "Discount Factor": discount_factors})
    print(daily_curve.head())
    print("\nSOFR Calibration Swap Repricing:")
    print(reprice_sofr_calibration_swaps(sofr_curve, sofr_quotes).to_string(index=False))


if __name__ == "__main__":
    main()
