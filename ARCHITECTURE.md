# Architecture

## Purpose
`tgir_quantlib_tools` is a lightweight QuantLib sandbox for inspecting a SOFR curve, repricing a compact rates-plus-equity portfolio, and running a few stand-alone pricing examples.

## Components
- Browser
- Login screen and protected Flask routes created by `tgir_quantlib_tools/app_factory.py`
- Session auth helpers and env-backed config in `tgir_quantlib_tools/`
- Pricing and curve helpers in `portfolio.py`
- QuantLib data-model manifest in `tgir_quantlib_tools/quantlib_model.py`
- Research metadata in `tgir_quantlib_tools/research.py`
- HTML templates in `templates/`
- Stand-alone scripts for curve inspection and isolated pricing checks

## Data Flow
Browser -> login route -> Flask session auth -> protected route -> shared portfolio state -> SOFR OIS curve bootstrap + swaption-vol inputs + SPX equity inputs -> QuantLib pricing engines -> curve table / optional forward diagnostics / vol matrix / callable grid + workstation HTML response

Browser -> QuantLib data-model route -> shared portfolio state -> QuantLib object manifest builder + research metadata -> educational / QA page with constructors, dependencies, enum values, and paper lists

Script -> shared QuantLib helpers -> stdout tables and diagnostics

## SOFR Curve Conventions
- The configured valuation date defaults to `2026-03-10` and is stored in the portfolio session state, so all pricing, schedules, forward strips, and exported dates stay aligned to the same reference date until the user changes it.
- The curve is bootstrapped from the workbook SOFR strip: `1D`, `1W`, `2W`, `3W`, `1M`, `2M`, `3M`, `6M`, `9M`, `1Y`, `2Y`, `3Y`, `4Y`, `5Y`, `6Y`, `7Y`, `8Y`, `10Y`, `12Y`, `15Y`, `20Y`, and `30Y`.
- The front-end `1D` point is modeled as an overnight deposit helper and the rest of the curve as SOFR OIS helpers.
- Calibration checks reprice each quoted OIS pillar to near-zero NPV.
- The dashboard curve panel now shows a compact `term / market rate / zero rate` table, with QuantLib-derived zero rates at the actual node dates reported as continuous-compounded spot rates on an Actual/365 basis rather than raw input quotes.
- The dashboard header keeps the core controls at the top of the screen: dashboard and model navigation, a direct research shortcut into the paper list, the upstream QuantLib GitHub link, the curve CSV export, the realtime toggle, and the reset action.
- A separate on-demand dashboard panel shows daily one-day simple forward rates implied by that same SOFR curve over the next ten years, with annual date ticks on the x-axis.
- The live demo swap starts on a spot business date so the app does not depend on loading historical SOFR fixings.

## Volatility Conventions
- European swaptions calibrate `ql.HullWhite` to a full ATM normal-vol matrix with short expiries from `1M` onward, annual expiries through `10Y`, then `12Y`, `15Y`, `20Y`, and `25Y`, against underlying swap tenors `1Y..10Y`, `12Y`, `15Y`, `20Y`, `25Y`, and `30Y`, then price with `ql.JamshidianSwaptionEngine`.
- The dashboard matrix uses the exact workbook expiry and tenor axes. When the Bermudan calibration needs a `3Y` expiry, the model linearly interpolates it between the workbook `2Y` and `4Y` rows.
- Bermudan swaptions default to `ql.HullWhite` calibrated to the trade's own fixed-maturity call schedule and priced with `ql.TreeSwaptionEngine`. The detail page also lets the user switch the same trade to `ql.G2` to compare value and risk differences under the same market data.
- Each exercise date is matched to the remaining underlying swap tenor implied by the common final maturity, so a `5Y NC 2Y` strip calibrates to `2Y x 3Y`, `3Y x 2Y`, and `4Y x 1Y` rather than `2Y x 2Y`, `3Y x 3Y`, and `4Y x 4Y`.
- When a required expiry is not on the workbook axes, the model interpolates that expiry in the expiry dimension only and records the exact matrix source points used by the helper.
- All rates trades are modeled as `ql.OvernightIndexedSwap` instruments with daily compounded SOFR coupons and editable payment/reset frequencies. The workbook comparison uses annual pay and annual reset.
- Default market data and trade defaults are stored in `data/default_market_data.json` and `data/default_trades.json`, then copied into the Flask session for interactive edits. The four rates trades seed at `100,000,000.00` notionals by default; the cliquet remains quantity based.

## Equity Cliquet Conventions
- The SPX trade is modeled as a `ql.CliquetOption` priced with `ql.AnalyticCliquetEngine`.
- The equity market stack uses a live spot, a flat dividend yield, a flat Black volatility, and the shared SOFR curve for discounting.
- Reset dates include the current evaluation date and then advance in fixed month increments until maturity, so the trade is represented as a strip of forward-start percentage-strike options.
- The cliquet editor exposes analytic Greeks, reset-by-reset decomposition, a deterministic spot/vol scenario grid, and a Monte Carlo payoff distribution.

## Bermudan Grid
- The workstation shows a Bermudan pricing grid with columns for final maturity `2Y`, `3Y`, `5Y`, `7Y`, and `10Y`.
- Rows are non-call periods `1Y..9Y`.
- For a valid cell, the trade is booked off a fixed final maturity. The remaining underlying tenor at each exercise date is implied by that fixed maturity, and call dates are generated off the payment schedule through the remaining life of the deal.
- Example: `5Y NC 2Y` means the trade can exercise after `2Y` into the remaining `3Y` swap, after `3Y` into the remaining `2Y` swap, and after `4Y` into the remaining `1Y` swap when annual payment dates are used.
- The Bermudan trade-detail page also shows this mapping directly, including the exercised-into swap, the calibration pillar label, and the matrix source points used for each exercise date. QuantLib's Python bindings do not expose exact Bermudan exercise probabilities from the tree swaption engines, so the UI reports that limitation explicitly instead of inventing probabilities.

## Testing Strategy
- Route smoke test for the login screen and protected dashboard
- Protected-route smoke test for the QuantLib data-model page
- Login flow test for session-protected workstation access
- Portfolio smoke test for returned instruments and NPVs
- Curve calibration test for all quoted SOFR OIS pillars plus derived zero-rate and forward-rate outputs
- Bermudan short-rate calibration sanity test for every helper used by the fixed-maturity trade calibration strip
- Shape test for the workbook ATM normal-vol matrix and the Bermudan grid
- Bermudan fixed-maturity schedule test for rolling exercise tenors
- Workbook-reference Bermudan price check against the QL screenshot
- Identity test portfolio for the cliquet trade where it collapses to simpler options or deterministic limits

## Deviations From app_architecture
- No `frontend/` and `backend/` split: the repo is intentionally a compact Flask + QuantLib codebase.
- No database, Stripe, Brevo, or Apify integration.
- The wider standard prefers Clerk auth; this repo uses a simple env-backed Flask login instead because the sandbox remains single-app and local/demo oriented.
- No production infra is committed; if the app is deployed later, prefer a single-host Apache + WSGI setup.
