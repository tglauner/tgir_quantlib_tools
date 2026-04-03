import QuantLib as ql
import pandas as pd
from datetime import datetime

from portfolio import build_sofr_curve, reprice_sofr_calibration_swaps

SOFR_QUOTES = [5.0, 5.1, 5.2, 5.3, 5.4]

today = ql.Date.todaysDate()
ql.Settings.instance().evaluationDate = today
sofr_curve = build_sofr_curve(today, SOFR_QUOTES)
sofr_handle = ql.YieldTermStructureHandle(sofr_curve)

# Print discount factors for different maturities
print("SOFR Discount Factors:")
for years in [1, 2, 5, 10]:
    date = today + ql.Period(years, ql.Years)
    discount_factor = sofr_handle.discount(date)
    print(f"{years}Y: {discount_factor:.6f}")

# Generate daily discount factors for one year
dates, discount_factors = [], []
for day_offset in range(366):
    date = today + day_offset
    dates.append(datetime(date.year(), date.month(), date.dayOfMonth()))
    discount_factors.append(sofr_handle.discount(date))

# Create DataFrame
df_daily = pd.DataFrame({'Date': dates, 'Discount Factor': discount_factors})

# Display DataFrame to user
print(df_daily.head())
print("\nSOFR Calibration Swap Repricing:")
print(reprice_sofr_calibration_swaps(sofr_curve, SOFR_QUOTES).to_string(index=False))
