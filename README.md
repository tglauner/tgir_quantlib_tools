# QuantLib Test

This repository showcases small examples of using [QuantLib](https://www.quantlib.org/) from Python. It includes a session-protected Flask workbench for repricing a compact rates portfolio and a few stand-alone scripts for curve inspection and pricing checks.

## Repository Structure

| Path | Description |
| --- | --- |
| `app.py` | Thin Flask entrypoint that creates the web app and starts the local server. |
| `tgir_quantlib_tools/` | Internal Flask package with app factory, config loading, auth helpers, route registration, and dashboard/session utilities. |
| `portfolio.py` | Functions for bootstrapping a SOFR OIS curve, repricing quoted OIS swaps, storing the ATM swaption vol matrix, creating interest-rate swaps and swaptions, building the SPX cliquet trade analytics, and pricing the five-trade portfolio. |
| `build_SOFR_curve.py` | Script that constructs a SOFR OIS term structure from market quotes, prints discount factors for select maturities, and shows a repricing table for calibration swaps. |
| `price_bermudan_swaption.py` | Prints the Bermudan swaption mark from the shared portfolio pricing path. |
| `today.py` | Minimal example showing how to set QuantLib's evaluation date. |
| `templates/` | HTML templates used by the web app. `login.html` renders the sign-in screen, `dashboard.html` renders the workstation with rates and SPX market panels, `quantlib_model.html` renders the data-model and research page, `trade_form.html` renders the detailed trade editors, and `base.html` holds the shared styling. |
| `tests/` | Smoke tests for the Flask route and portfolio, OIS and Bermudan calibration repricing checks, and a dedicated cliquet identity suite. |
| `docs/` | Architecture notes, runbook notes, a research memo, and a full LaTeX documentation set for end users, quants, developers, IT, testing, and deployment. |
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

## Testing

Run the smoke tests with:

```bash
./.venv/bin/python -m unittest discover -s tests
```

The suite now covers:

- OIS calibration repricing
- Hull-White and G2++ Bermudan calibration sanity checks against the fixed-maturity call schedule
- Fixed-maturity Bermudan exercise schedule checks
- Bermudan benchmark call-schedule mapping and interpolated matrix-source checks
- Bermudan workbook-reference pricing under the default Hull-White 1F setup
- Flask route and session smoke tests
- A ten-case cliquet identity portfolio where the cliquet collapses to simpler instruments or deterministic limits

## LaTeX Documentation

The audience-specific LaTeX documentation set lives under `docs/latex/`.

For a concise production deploy checklist specific to `quant.tglauner.com`, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Build all PDFs with:

```bash
make -C docs/latex
```

That directory now includes:

- End-user guide and slides
- Quant guide and slides
- Developer guide and slides
- IT operations guide and slides
- A separate testing and regression guide
- A separate CI/CD and DigitalOcean deployment guide

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
