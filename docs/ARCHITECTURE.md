# Architecture

## Purpose
`tgir_quantlib_tools` is a lightweight QuantLib sandbox for inspecting a SOFR curve, repricing a small rates portfolio, and running a few stand-alone pricing examples.

## Components
- Browser
- Flask application in `app.py`
- Pricing and curve helpers in `portfolio.py`
- HTML templates in `templates/`
- Stand-alone scripts for curve inspection and isolated pricing checks

## Data Flow
Browser -> Flask route -> `price_portfolio()` -> SOFR OIS curve bootstrap -> QuantLib pricing engines -> HTML table response

Script -> shared QuantLib helpers -> stdout tables and diagnostics

## SOFR Curve Conventions
- The curve is bootstrapped from `1Y`, `2Y`, `3Y`, `5Y`, and `10Y` SOFR OIS quotes.
- Calibration checks require `2Y`, `5Y`, and `10Y` OIS swaps to reprice to near-zero NPV.
- The live demo swap starts on a spot business date so the app does not depend on loading historical SOFR fixings.

## Testing Strategy
- Route smoke test for the Flask homepage
- Portfolio smoke test for returned instruments and NPVs
- Curve calibration test for `2Y`, `5Y`, and `10Y` SOFR OIS repricing

## Deviations From app_architecture
- No `frontend/` and `backend/` split: the repo is intentionally a compact Flask + QuantLib codebase.
- No database, auth, Stripe, Brevo, or Apify integration.
- No production infra is committed; if the app is deployed later, prefer a single-host Apache + WSGI setup.
