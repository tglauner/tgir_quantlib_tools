from datetime import datetime

import QuantLib as ql
import pandas as pd

from portfolio import (
    SOFR_CURVE_TENOR_LABELS,
    build_sofr_curve,
    reprice_sofr_calibration_swaps,
)


SOFR_QUOTES = [4.85, 4.98, 5.04, 5.09, 5.17, 5.22, 5.28, 5.31]


def main() -> None:
    today = ql.Date.todaysDate()
    ql.Settings.instance().evaluationDate = today
    sofr_curve = build_sofr_curve(today, SOFR_QUOTES)
    sofr_handle = ql.YieldTermStructureHandle(sofr_curve)

    print("SOFR Discount Factors:")
    overnight_date = today + ql.Period(1, ql.Days)
    print(f"{SOFR_CURVE_TENOR_LABELS[0]}: {sofr_handle.discount(overnight_date):.6f}")
    for years in [1, 2, 5, 7, 10, 12]:
        curve_date = today + ql.Period(years, ql.Years)
        print(f"{years}Y: {sofr_handle.discount(curve_date):.6f}")

    dates = []
    discount_factors = []
    for day_offset in range(366):
        curve_date = today + day_offset
        dates.append(datetime(curve_date.year(), curve_date.month(), curve_date.dayOfMonth()))
        discount_factors.append(sofr_handle.discount(curve_date))

    daily_curve = pd.DataFrame({"Date": dates, "Discount Factor": discount_factors})
    print(daily_curve.head())
    print("\nSOFR Calibration Swap Repricing:")
    print(reprice_sofr_calibration_swaps(sofr_curve, SOFR_QUOTES).to_string(index=False))


if __name__ == "__main__":
    main()
