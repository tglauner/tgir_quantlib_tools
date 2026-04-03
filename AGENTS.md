# AGENTS.md — tgir_quantlib_tools

## Mission
Maintain a small QuantLib sandbox with a Flask UI and stand-alone pricing scripts.

## Stack
- Flask for the demo web app
- QuantLib for curve construction and pricing
- pandas for tabular output
- unittest for smoke and curve calibration checks

## Repo Layout
- `app.py`: Flask entrypoint
- `portfolio.py`: SOFR curve bootstrap and pricing helpers
- `build_SOFR_curve.py`: curve inspection and calibration repricing script
- `price_bermudan_swaption.py`, `today.py`: stand-alone QuantLib examples
- `templates/`: Flask HTML templates
- `tests/`: smoke and curve repricing tests
- `docs/`: architecture and runbook notes

## Conventions
- Keep dependencies lean and prefer standard library first.
- Build SOFR curves from OIS market quotes, not generic deposit helpers.
- Use explicit business-day handling for swap starts and maturities.
- Keep the Flask app thin; place pricing logic in `portfolio.py`.
- Do not introduce secrets, databases, auth, or paid services unless explicitly requested.

## Quality Gates
- `./.venv/bin/python -m unittest discover -s tests`
- `./.venv/bin/python build_SOFR_curve.py`
- `./.venv/bin/python -c "from app import app; print(app.test_client().get('/').status_code)"`

## Deployment Default
- This repo is primarily local/demo oriented.
- If production deployment is later needed, prefer a single DigitalOcean droplet with Apache reverse proxying to a local WSGI service.

## Deviations From app_architecture
- This repo intentionally stays as a single Flask application instead of a React/FastAPI split.
- There is no database, auth layer, or payment system in scope.
