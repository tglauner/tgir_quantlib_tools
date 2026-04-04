# Architecture

## Purpose
`tgir_quantlib_tools` is a lightweight QuantLib sandbox for inspecting a SOFR curve, repricing a small rates portfolio, and running a few stand-alone pricing examples.

## Components
- Browser
- Login screen and protected Flask routes created by `tgir_quantlib_tools/app_factory.py`
- Session auth helpers and env-backed config in `tgir_quantlib_tools/`
- Pricing and curve helpers in `portfolio.py`
- HTML templates in `templates/`
- Stand-alone scripts for curve inspection and isolated pricing checks

## Data Flow
Browser -> login route -> Flask session auth -> protected route -> shared portfolio state -> SOFR OIS curve bootstrap and swaption-vol inputs -> QuantLib pricing engines -> HTML workstation response

Script -> shared QuantLib helpers -> stdout tables and diagnostics

## SOFR Curve Conventions
- The curve is bootstrapped from `ON`, `1Y`, `2Y`, `3Y`, `5Y`, `7Y`, `10Y`, and `12Y` SOFR quotes.
- The front-end `ON` point is modeled as an overnight deposit helper and the rest of the curve as SOFR OIS helpers.
- Calibration checks reprice each quoted OIS pillar to near-zero NPV.
- The live demo swap starts on a spot business date so the app does not depend on loading historical SOFR fixings.

## Volatility Conventions
- European swaptions are priced from a full ATM normal-vol matrix with annual expiries `1Y..10Y` and annual underlying swap tenors `1Y..10Y`.
- Bermudan swaptions are intentionally simpler: they use a flat callable normal-vol input as a Hull-White sigma proxy, not a full Bermudan calibration.
- The UI shows both concepts separately so the market surface and the callable proxy are not conflated.

## Bermudan Grid
- The workstation shows a Bermudan pricing grid with columns for final maturity `2Y`, `3Y`, `5Y`, `7Y`, and `10Y`.
- Rows are non-call periods `1Y..9Y`.
- For a valid cell, the underlying swap tenor is computed as `maturity - noncall`, and annual call dates are generated through the remaining life of the deal.

## Testing Strategy
- Route smoke test for the login screen and protected dashboard
- Login flow test for session-protected workstation access
- Portfolio smoke test for returned instruments and NPVs
- Curve calibration test for all quoted SOFR OIS pillars
- Shape test for the `10x10` ATM normal-vol matrix and the Bermudan grid

## Deviations From app_architecture
- No `frontend/` and `backend/` split: the repo is intentionally a compact Flask + QuantLib codebase.
- No database, Stripe, Brevo, or Apify integration.
- The wider standard prefers Clerk auth; this repo uses a simple env-backed Flask login instead because the sandbox remains single-app and local/demo oriented.
- No production infra is committed; if the app is deployed later, prefer a single-host Apache + WSGI setup.
