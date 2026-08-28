# TGIR QuantLib Tools

This repository is a compact Python and [QuantLib](https://www.quantlib.org/) pricing sandbox. It includes a session-protected Flask workbench for rates and equity examples, stand-alone curve and pricing scripts, and a reference callable EUR/USD cross-currency swap pricer using two one-factor Hull–White rate models, lognormal FX, Monte Carlo, and Longstaff–Schwartz regression.

The callable-XCCY functionality is available both from the command line and through a read-only Model Context Protocol (MCP) server. It is a transparent research/reference implementation—not a production-approved or independently validated bank model.

## Repository Structure

| Path | Description |
| --- | --- |
| `app.py` | Thin Flask entrypoint that creates the web app and starts the local server. |
| `tgir_quantlib_tools/` | Internal Flask package with app factory, config loading, auth helpers, route registration, and dashboard/session utilities. |
| `portfolio.py` | Functions for bootstrapping a SOFR OIS curve, repricing quoted OIS swaps, storing the ATM swaption vol matrix, creating interest-rate swaps and swaptions, building the SPX cliquet trade analytics, and pricing the five-trade portfolio. |
| `build_SOFR_curve.py` | Script that constructs a SOFR OIS term structure from market quotes, prints discount factors for select maturities, and shows a repricing table for calibration swaps. |
| `price_bermudan_swaption.py` | Prints the Bermudan swaption mark from the shared portfolio pricing path. |
| `standalone_xccy_pricer.py` | Stand-alone callable EUR/USD XCCY pricer with OIS bootstraps, Hull–White and FX calibration, exact joint Gaussian simulation, and two-pass Bermudan LSM. |
| `xccy_pricer_diagnostics.py` | Common-random-number bump-and-revalue Greeks, half-bump stability checks, and an independent path-count convergence diagnostic. |
| `xccy_pricer_mcp.py` | MCP 2.0 server exposing structured single-deal validation and pricing tools over stdio or loopback Streamable HTTP. |
| `today.py` | Minimal example showing how to set QuantLib's evaluation date. |
| `data/xccy_*.json` | Illustrative EUR/USD market snapshot and 10Y NC2 receive-€STR/pay-USD-fixed sample deal. |
| `data/schemas/` | Versioned JSON Schemas for callable-XCCY market and deal inputs. |
| `templates/` | HTML templates used by the web app. `login.html` renders the sign-in screen, `dashboard.html` renders the workstation with rates and SPX market panels, `quantlib_model.html` renders the data-model and research page, `trade_form.html` renders the detailed trade editors, and `base.html` holds the shared styling. |
| `tests/` | Flask and portfolio smoke tests, curve/model calibration checks, cliquet identities, callable-XCCY quantitative tests, and MCP/risk/convergence tests. |
| `docs/` | Architecture and runbook notes, callable-XCCY specifications, MCP and REST integration guides, research material, and the LaTeX documentation set. |
| `deploy/` | Example production environment, systemd, and Apache templates for DigitalOcean deployment. |
| `.github/workflows/` | GitHub Actions workflows for CI and DigitalOcean CD. |
| `AGENTS.md` | Repo-specific Codex guidance for working in this codebase. |
| `.codex/config.toml` | Codex workspace defaults for this repository. |
| `.env.example` | Example local configuration for Flask secret and login credentials. |
| `requirements-production.txt` | Production dependency set, extending the base requirements with `gunicorn`. |
| `wsgi.py` | Production WSGI entrypoint for the local app service. |
| `requirements.txt` | Python dependencies. |
| `LICENSE` | Apache 2.0 license. |

## Installation

1. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Copy the local config and set a strong secret and password:

   ```bash
   cp .env.example .env
   ```

If the repository is moved or renamed, recreate `.venv` instead of reusing an older one. Python entrypoints inside a virtualenv can contain absolute paths.

## Usage

### Web Application

Run the Flask app and open `http://127.0.0.1:5050` in a browser:

```bash
./.venv/bin/python app.py
```

The root route shows a login screen. After signing in, the workstation displays the marks of a swap, a European swaption, two Bermudan swaptions, and an SPX equity cliquet. The top bar keeps dashboard navigation, the QuantLib model view, a direct research shortcut, the official QuantLib GitHub link, the curve CSV export, the realtime toggle, and reset controls in one place. You can adjust:

- A configurable valuation date, defaulting to `2026-03-10`, that anchors all curve builds, pricing, and schedule generation
- A workbook-based SOFR strip from `1D`, `1W`, `2W`, `3W`, `1M`, `2M`, `3M`, `6M`, `9M`, `1Y`, `2Y`, `3Y`, `4Y`, `5Y`, `6Y`, `7Y`, `8Y`, `10Y`, `12Y`, `15Y`, `20Y`, and `30Y`
- A full ATM normal-vol matrix on the exact workbook expiry and tenor axes, with any internal `3Y` expiry interpolation reserved for model calibration rather than the on-screen matrix
- A shared mean-reversion input, shown as a percentage on screen, used while the rates models calibrate to the ATM swaption matrix
- SPX spot, flat dividend yield, and flat Black volatility inputs used by the cliquet trade

The swap, European swaption, and Bermudan swaption editors all expose payment frequency and reset frequency. The four rates trades now default to `100,000,000.00` notionals, while the equity cliquet keeps its quantity-based setup. Bermudan trades are entered with a fixed final maturity rather than a fixed underlying tenor, so a `5Y NC 2Y` structure exercises into the remaining `3Y`, `2Y`, and `1Y` swaps along its annual call schedule. `Bermudan Swaption 2` is seeded with the QL workbook benchmark trade so you can compare model marks against the spreadsheet reference out of the box.

Default market and trade values are loaded from:

- `data/default_market_data.json`
- `data/default_trades.json`

The default market-data JSON now carries lightweight metadata as well as quotes: the SOFR curve block includes `ccy` and `index`, the swaption surface includes a market `key`, and the SPX equity block includes the ticker plus a flat-volatility `key`.

The dashboard then derives and displays:

- A compact SOFR curve table with `term / market rate / zero rate`, where zero rates are QuantLib spot zeros at the actual node dates, reported as continuous-compounded rates on an Actual/365 basis so that `df(x) = exp(-z * x / 365)` for `x` actual calendar days from the valuation date
- An on-demand daily one-day SOFR forward strip over the next ten years with annual date ticks
- An on-demand OIS repricing table across the quoted SOFR pillars
- A Bermudan pricing grid plus Bermudan trade-detail call-schedule rows showing each exercise date, the remaining swap it exercises into, and the matrix source points used by calibration
- A dedicated QuantLib data-model page at `/quantlib-data-model`, with a top-bar `Research` shortcut to the paper list and a `QuantLib GitHub` link to the upstream library repo
- A dedicated callable-XCCY quantitative page at `/xccy-callable`, opened from the dashboard’s `Open XCCY callable lab` button, with deal terms, typeset model dynamics, editable validated correlations, full recalibration/repricing, calibration fits, valuation, exercise probabilities, LSM diagnostics, martingale checks, limitations, and authenticated raw JSON views
- An SPX cliquet editor page with analytic Greeks, reset-by-reset decomposition, a spot-vol scenario grid, and a Monte Carlo payoff profile
- A downloadable curve debug file at `/curve-debug.csv`

The app defaults to port `5050` because port `5000` is often occupied by macOS services on local machines.

When `FLASK_DEBUG=1`, the app falls back to a local development password if you have not configured one yet. Keep that mode local only and set explicit credentials in `.env` before using the app anywhere else.

### Stand-alone Scripts

- **Build SOFR Curve**

  ```bash
  ./.venv/bin/python build_SOFR_curve.py
  ```

- **Price Bermudan Swaption**

  ```bash
  ./.venv/bin/python price_bermudan_swaption.py
  ```

- **Show Today's Date**

  ```bash
  ./.venv/bin/python today.py
  ```

### Callable EUR/USD Cross-Currency Swap

The supplied example is a constant-notional 10Y NC2 swap in which the option holder receives quarterly compounded EUR €STR and pays semiannual USD fixed at 4%. It has annual cancellation dates from year 2 through year 9, USD collateral/reporting, explicit EUR and USD notionals, and initial and final notional exchanges.

Run the JSON-driven valuation with:

```bash
./.venv/bin/python standalone_xccy_pricer.py \
  --market data/xccy_market_eurusd.json \
  --deal data/xccy_deal_10y_nc2.json \
  --output result.json
```

For a quicker smoke valuation:

```bash
./.venv/bin/python standalone_xccy_pricer.py \
  --market data/xccy_market_eurusd.json \
  --deal data/xccy_deal_10y_nc2.json \
  --output result.json \
  --training-paths 1000 \
  --pricing-paths 2000
```

The result contains callable and non-callable NPV, Monte Carlo standard errors and confidence intervals, the embedded cancellation value, leg PVs, exercise probabilities, calibration residuals, martingale diagnostics, LSM regression diagnostics, numerical settings, software versions, and a normalized input hash.

The model is simulated under the USD money-market measure:

- one-factor Hull–White dynamics for USD and EUR rates;
- the negative foreign-rate quanto drift for EURUSD quoted as USD per EUR;
- piecewise-constant ATM Black FX volatility;
- exact affine OU state transitions with joint rate/FX covariance integration;
- pathwise USD discounting and EUR cash-flow conversion; and
- backward LSM training followed by a frozen policy on an independently seeded pricing sample.

QuantLib supplies dates, calendars, OIS helpers, curve bootstraps, swaption helpers, Hull–White calibration, and Jamshidian benchmark engines. The complete correlated cross-currency simulation and callable LSM engine are explicit Python because QuantLib does not provide this full hybrid product engine natively.

Version 1 deliberately uses one constant Hull–White volatility per currency, deterministic forecast/discount and cross-currency basis, ATM-only FX volatility, and the continuous-time bank-account equivalent of compounded €STR with zero lookback and lockout. The LSM value is a lower-bound estimate and requires convergence and independent model validation before controlled use. The sample market JSON is illustrative and must be replaced with an approved snapshot.

Detailed documents:

- [Callable-XCCY pricing specification](docs/callable_bermudan_xccy_swap_pricing_spec.md)
- [Quantitative two-pager](docs/callable_bermudan_xccy_quant_two_pager.md)
- [Three-page implementation specification](docs/latex/standalone_callable_xccy_pricer_spec.tex)
- [Local command-line guide](docs/local_command_line_testing.md)
- [Compiled papers](docs/papers/)
- [Lecture sources and PDFs](docs/lectures/)

### MCP Single-Deal Pricing

The MCP server exposes two structured, read-only tools:

- `xccy_validate_deal` checks the versioned schemas and semantic pricing prerequisites. It returns `READY`, `NEEDS_INPUT`, or `INVALID`; incomplete requests include concrete questions for the calling system to ask rather than guessed values.
- `xccy_price_deal` validates and prices exactly one deal. Optional flags add common-random-number Greeks, half-bump stability, path-count convergence, and full versus summarized audit output.

For a local MCP host using stdio:

```bash
./.venv/bin/python xccy_pricer_mcp.py --transport stdio
```

For another process on the same machine using Streamable HTTP:

```bash
./.venv/bin/python xccy_pricer_mcp.py \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8765
```

Connect to `http://127.0.0.1:8765/mcp`. The reference server deliberately refuses non-loopback binding because it does not implement authentication. Remote use requires an authenticated TLS reverse proxy or a validated MCP authorization provider. See [docs/mcp_xccy_pricer.md](docs/mcp_xccy_pricer.md) for the request contract, Python client example, diagnostics, and security boundary.

## Testing

Run the smoke tests with:

```bash
./.venv/bin/python -m unittest discover -s tests
```

The current suite contains 46 tests and covers:

- OIS calibration repricing
- Hull-White and G2++ Bermudan calibration sanity checks against the fixed-maturity call schedule
- Fixed-maturity Bermudan exercise schedule checks
- Bermudan benchmark call-schedule mapping and interpolated matrix-source checks
- Bermudan workbook-reference pricing under the default Hull-White 1F setup
- Flask route and session smoke tests
- Callable-XCCY page access control, dashboard navigation, quantitative content, JSON views, correlation validation, and safe result refresh tests
- A ten-case cliquet identity portfolio where the cliquet collapses to simpler instruments or deterministic limits
- Callable-XCCY JSON and semantic validation, NC2 schedules, calibration tolerances, exact FX-variance and zero-volatility limits
- Domestic-discount, discounted-FX, and FX-converted foreign-bank-account martingale checks
- Reproducible two-pass LSM training/pricing, value identities, and exercise-probability conservation
- MCP tool discovery, structured output, incomplete-deal questions, and a complete single-deal valuation
- Common-random-number FX delta and parallel USD/EUR DV01 half-bump stability
- Independent low/high path-count convergence within a four-combined-standard-error tolerance

Run only the callable-XCCY and MCP controls with:

```bash
./.venv/bin/python -m unittest \
  tests.test_xccy_callable_pricer \
  tests.test_xccy_pricer_mcp \
  -v
```

These controls are appropriate for a transparent reference implementation. They are not a substitute for an independent implementation, multi-exercise dual upper bounds, seed ensembles, historical calibration studies, comprehensive Greeks, or formal model-risk approval.

## LaTeX Documentation

The audience-specific LaTeX documentation set lives under `docs/latex/`.

For a concise production deploy checklist specific to `quant.tglauner.com`, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Build all PDFs with:

```bash
make -C docs/latex
```

Final PDFs are collected in `docs/papers/`. LaTeX intermediate files are isolated in the ignored `docs/latex/build/` subdirectory.

That directory now includes:

- End-user guide and slides
- Quant guide and slides
- Developer guide and slides
- IT operations guide and slides
- A separate testing and regression guide
- A separate CI/CD and DigitalOcean deployment guide
- A three-page stand-alone callable-XCCY implementation specification

Useful route checks:

```bash
./.venv/bin/python - <<'PY'
from tgir_quantlib_tools import create_app

app = create_app({
    "TESTING": True,
    "SECRET_KEY": "smoke-secret",
    "AUTH_USERNAME": "tester",
    "AUTH_PASSWORD": "secret-pass",
    "AUTH_PASSWORD_HASH": None,
    "SESSION_COOKIE_SECURE": False,
})
client = app.test_client()
client.post("/login", data={"username": "tester", "password": "secret-pass"})
for path in ["/dashboard", "/quantlib-data-model"]:
    print(path, client.get(path).status_code)
PY
```

## Market Data Note

The workstation exposes a full ATM swaption normal-vol matrix because the pricing surface is naturally organized by swaption expiry and underlying swap length. The implementation documentation references ICE SDX help pages because they explicitly describe:

- A swaption volatility surface with mid implied volatilities and normal vols, with market data obtained from multiple data sources and initially displayed as real-time market data
- A swaption forward-rates page that shows forward rate, straddle price, ATM volatility, and ATM normal volatility for each expiry and swap length

Source references:

- https://idd.ice.com/IRHelp/Content/FM/Swaption_Volatility_Surf.htm
- https://idd.ice.com/IRHelp/Content/FM/Swaption_Forward_Rates.htm

This repository does not auto-download live ICE data. The matrix is an editable workbook-derived demo surface, including the interpolated `3Y` expiry row that keeps the annual diagonal strip continuous for Bermudan calibration.

## Research Note

The full paper list used for the swaption and equity cliquet extension lives in [docs/RESEARCH.md](docs/RESEARCH.md). The data-model page also renders the same references directly in the web UI.

## Deviations From `app_architecture`

This repository selectively adopts the documentation and workflow guidance from the sibling `app_architecture` template. It intentionally remains a compact Flask + QuantLib repo instead of being restructured into `frontend/` and `backend/`. It also uses an env-configured session login rather than Clerk so the repo stays local, dependency-light, and aligned to its demo scope.

## License

This project is licensed under the terms of the [Apache License 2.0](LICENSE).
