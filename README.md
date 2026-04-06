# QuantLib Test

This repository showcases small examples of using [QuantLib](https://www.quantlib.org/) from Python. It includes a session-protected Flask workbench for repricing a compact rates portfolio and a few stand-alone scripts for curve inspection and pricing checks.

## Repository Structure

| Path | Description |
| --- | --- |
| `app.py` | Thin Flask entrypoint that creates the web app and starts the local server. |
| `tgir_quantlib_tools/` | Internal Flask package with app factory, config loading, auth helpers, route registration, and dashboard/session utilities. |
| `portfolio.py` | Functions for bootstrapping a SOFR OIS curve, repricing quoted OIS swaps, storing the ATM swaption vol matrix, creating interest-rate swaps and swaptions, and pricing the three-trade portfolio. |
| `build_SOFR_curve.py` | Script that constructs a SOFR OIS term structure from market quotes, prints discount factors for select maturities, and shows a repricing table for calibration swaps. |
| `price_bermudan_swaption.py` | Prints the Bermudan swaption mark from the shared portfolio pricing path. |
| `today.py` | Minimal example showing how to set QuantLib's evaluation date. |
| `templates/` | HTML templates used by the web app. `login.html` renders the sign-in screen, `dashboard.html` renders the workstation with QuantLib-derived zero-rate and forward-rate charts, `quantlib_model.html` renders the data-model page, `trade_form.html` renders the detailed trade editors, and `base.html` holds the shared styling. |
| `tests/` | Smoke tests for the Flask route and portfolio plus OIS curve repricing checks. |
| `docs/` | Architecture notes and a local runbook aligned to the sibling `app_architecture` guidance, with explicit repo-specific deviations. |
| `AGENTS.md` | Repo-specific Codex guidance for working in this codebase. |
| `.codex/config.toml` | Codex workspace defaults for this repository. |
| `.env.example` | Example local configuration for Flask secret and login credentials. |
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

The root route shows a login screen. After signing in, the workstation displays the marks of a swap, a European swaption, and a Bermudan swaption. You can adjust:

- Overnight SOFR plus `1Y`, `2Y`, `3Y`, `5Y`, `7Y`, `10Y`, and `12Y` OIS quotes
- A full ATM normal-vol matrix with annual expiries `1Y..10Y` and annual swap tenors `1Y..10Y`
- A separate Bermudan GSR sigma seed used to initialize diagonal swaption calibration

The dashboard then derives and displays:

- QuantLib zero rates at the actual curve node dates
- A separate daily one-day SOFR forward strip over the next ten years with annual date ticks
- A dedicated QuantLib data-model page at `/quantlib-data-model` showing the live object graph, constructor signatures, dependencies, and enum values used by the app
- A generated repo copy of the curve debug file at `debug/curve_debug.csv`, refreshed by the app and also downloadable at `/curve-debug.csv`

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

This repository does not auto-download live ICE data. The matrix is an editable demo surface laid out on those same annual ATM pillars so the QuantLib examples remain self-contained.

## Deviations From `app_architecture`

This repository selectively adopts the documentation and workflow guidance from the sibling `app_architecture` template. It intentionally remains a compact Flask + QuantLib repo instead of being restructured into `frontend/` and `backend/`. It also uses an env-configured session login rather than Clerk so the repo stays local, dependency-light, and aligned to its demo scope.

## License

This project is licensed under the terms of the [Apache License 2.0](LICENSE).
