# QuantLib Test

This repository showcases small examples of using [QuantLib](https://www.quantlib.org/) from Python.  It includes a simple Flask web app for repricing a portfolio and several stand‑alone scripts that construct or price instruments.

## Repository Structure

| Path | Description |
| --- | --- |
| `app.py` | Flask application that displays a compact rates workstation with a live blotter, SOFR curve monitor, ATM swaption normal-vol matrix, and Bermudan pricing grid. |
| `portfolio.py` | Functions for bootstrapping a SOFR OIS curve, repricing quoted OIS swaps, storing the ATM swaption vol matrix, creating interest-rate swaps and swaptions, and pricing the three-trade portfolio. |
| `build_SOFR_curve.py` | Script that constructs a SOFR OIS term structure from market quotes, prints discount factors for select maturities, and shows a repricing table for calibration swaps. |
| `price_bermudan_swaption.py` | Demonstrates pricing a Bermudan swaption using the Hull–White short‑rate model and a tree swaption engine. |
| `read_rates_vols_from_Excel.py` | Placeholder for future functionality to load market data from Excel. |
| `today.py` | Minimal example showing how to set QuantLib's evaluation date. |
| `templates/` | HTML templates used by the web app. `dashboard.html` renders the workstation, `trade_form.html` renders the detailed trade editors, and `base.html` holds the shared styling. |
| `tests/` | Smoke tests for the Flask route and portfolio plus OIS curve repricing checks. |
| `docs/` | Architecture notes and a local runbook aligned to the sibling `app_architecture` guidance, with explicit repo-specific deviations. |
| `AGENTS.md` | Repo-specific Codex guidance for working in this codebase. |
| `.codex/config.toml` | Codex workspace defaults for this repository. |
| `requirements.txt` | Python dependencies. |
| `LICENSE` | Apache 2.0 license. |

## Installation

1. Create and activate a virtual environment (optional):

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

If the repository is moved or renamed, recreate `.venv` instead of reusing an older one. Python entrypoints inside a virtualenv can contain absolute paths.

## Usage

### Web Application

Run the Flask app and open `http://127.0.0.1:5050` in a browser:

```bash
./.venv/bin/python app.py
```

The page displays the marks of a swap, a European swaption, and a Bermudan swaption. You can adjust:

- Overnight SOFR plus `1Y`, `2Y`, `3Y`, `5Y`, `7Y`, `10Y`, and `12Y` OIS quotes
- A full ATM normal-vol matrix with annual expiries `1Y..10Y` and annual swap tenors `1Y..10Y`
- A separate flat callable normal vol used for Bermudan pricing

The app defaults to port `5050` because port `5000` is often occupied by macOS services on local machines.

### Stand‑alone Scripts

- **Build SOFR Curve**

  ```bash
  python build_SOFR_curve.py
  ```
  Prints sample discount factors and a table of daily factors.

- **Price Bermudan Swaption**

  ```bash
  python price_bermudan_swaption.py
  ```
  Computes the NPV of a Bermudan swaption using the Hull–White model.

- **Show Today's Date**

  ```bash
  python today.py
  ```
  Outputs the evaluation date currently set in QuantLib.

## License

This project is licensed under the terms of the [Apache License 2.0](LICENSE).

## Contributing

Issues and pull requests are welcome.  The repository is intended as a lightweight sandbox for experimenting with QuantLib in Python.

## Testing

Run the smoke tests with:

```bash
python -m unittest discover -s tests
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

This repository selectively adopts the documentation and workflow guidance from the sibling `app_architecture` template. It intentionally remains a compact Flask + QuantLib repo instead of being restructured into `frontend/` and `backend/`, and it does not add a database or production-only services that are irrelevant to this sandbox.
