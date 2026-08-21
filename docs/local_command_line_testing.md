# Local Command-Line Testing and Server Startup

Status: operational guide
Last verified: 2026-08-15

## What runs locally

This repository has one application server: the Flask web application. It does not require a database, cache, worker, or JavaScript development server. The SOFR curve builder and Bermudan pricer are stand-alone command-line programs, not servers.

All commands below assume the shell is in the repository root and use the required `.venv/` virtual environment.

## Current checkout result on 2026-08-15

- After `git fetch --prune origin`, `main` is `0` commits ahead and `0` behind `origin/main` at commit `d3b45a4`.
- The working tree is not clean; it already contains uncommitted application, template, deployment, and handoff changes.
- All seven callable-XCCY tests pass, including curve/model calibration, exact-variance and zero-volatility limits, martingales, reproducibility, and the independent training/pricing LSM identity checks.
- With all dependencies locally available, the complete suite runs 39 tests and passes; the SOFR calibration gate also passes and the Flask root-route gate returns `200`.
- On this Dropbox-hosted checkout, the complete suite can pause while macOS downloads a pandas module inside `.venv/`. Keep the project and `.venv/` available offline, or recreate `.venv/`, then rerun the complete command in section 3. An interrupted import is an environment failure, not a passing test result.

## 1. Check the checkout

Fetch remote metadata and compare the current branch with its upstream:

```bash
git fetch --prune origin
git status --short --branch
git rev-list --left-right --count HEAD...@{upstream}
```

The final command prints `<local-only> <remote-only>`. A result of `0 0` means the checked-out commit matches the upstream commit. A clean repository also has no file lines below the branch line from `git status`; uncommitted files do not mean the branch is behind, but they must be reviewed before pulling or switching branches.

## 2. Create or refresh the Python environment

Only do this when `.venv/` is absent, broken, or points to a previous location:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
```

For the production-like Gunicorn command in section 6, install the production requirements instead:

```bash
./.venv/bin/python -m pip install -r requirements-production.txt
```

## 3. Run the automated checks

Run the complete unit and smoke suite:

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

The QuantLib calibration and point-risk checks can take several minutes. A quiet terminal does not necessarily mean the process is stuck.

Run the two project quality-gate programs separately:

```bash
./.venv/bin/python build_SOFR_curve.py
./.venv/bin/python -c "from app import app; print(app.test_client().get('/').status_code)"
```

Expected outcomes:

- the unit-test command ends with `OK`;
- the SOFR script prints discount factors and calibration swaps with NPVs near zero; and
- the Flask smoke check prints `200`.

Optional stand-alone pricing check:

```bash
./.venv/bin/python price_bermudan_swaption.py
```

## 4. Run the callable EUR/USD XCCY pricer

The supplied market file is illustrative and must be replaced with an approved market snapshot before any controlled use. A quick smoke valuation is:

```bash
./.venv/bin/python standalone_xccy_pricer.py \
  --market data/xccy_market_eurusd.json \
  --deal data/xccy_deal_10y_nc2.json \
  --output result.json \
  --training-paths 1000 \
  --pricing-paths 2000
```

Run the sample deal at its JSON-configured defaults of 10,000 training and 30,000 independent pricing paths by omitting the two path overrides:

```bash
./.venv/bin/python standalone_xccy_pricer.py \
  --market data/xccy_market_eurusd.json \
  --deal data/xccy_deal_10y_nc2.json \
  --output result.json
```

The command prints the run ID, status, NPV, Monte Carlo standard error, and output location. Inspect the complete audit result without another dependency:

```bash
./.venv/bin/python -m json.tool result.json | less
```

Run only the pricer's quantitative regression suite with:

```bash
./.venv/bin/python -m unittest tests.test_xccy_callable_pricer -v
```

The output must show `status: OK` and `calibration.accepted: true`. Review the calibration residuals, Monte Carlo confidence intervals, martingale diagnostics, regression conditioning, exercise profile, input hash, and limitations; a single point estimate is not a validation result.

## 5. Start the callable-XCCY MCP server

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

Connect the MCP client to `http://127.0.0.1:8765/mcp`. The server exposes `xccy_validate_deal` and `xccy_price_deal`; see `docs/mcp_xccy_pricer.md` for request examples, questions returned for incomplete inputs, optional risk/convergence controls, and the security boundary.

Run its focused tests with:

```bash
./.venv/bin/python -m unittest tests.test_xccy_pricer_mcp -v
```

## 6. Start the local development server

The quickest local-only command is:

```bash
FLASK_DEBUG=1 PORT=5050 ./.venv/bin/python app.py
```

Open `http://127.0.0.1:5050/`. If no `.env` credentials exist, the development-only fallback login is username `demo` and password `demo-pass-change-me`. Never expose that fallback server outside the local machine.

For explicit local credentials, create `.env` once, edit its placeholder values, and then start normally:

```bash
test -f .env || cp .env.example .env
./.venv/bin/python app.py
```

The `.env` file is gitignored and must not be committed. Stop the server with `Ctrl-C`.

## 7. Check the running server from a second terminal

```bash
curl --fail --silent http://127.0.0.1:5050/health
curl --head http://127.0.0.1:5050/
```

The health request should return JSON and the root request should return an HTTP response from Flask. The protected dashboard requires a browser login.

## 8. Start a production-like local WSGI server

After installing `requirements-production.txt` and configuring real values in `.env`, run:

```bash
FLASK_DEBUG=0 ./.venv/bin/gunicorn --bind 127.0.0.1:5050 --workers 1 --threads 4 --timeout 120 wsgi:app
```

This is a local process-level test of the WSGI entrypoint. Apache and systemd are deployment concerns and are not needed for local pricing tests. Stop Gunicorn with `Ctrl-C`.

## 9. Troubleshooting

Check whether another process owns the port:

```bash
lsof -nP -iTCP:5050 -sTCP:LISTEN
```

Use a different port without editing files:

```bash
FLASK_DEBUG=1 PORT=5051 ./.venv/bin/python app.py
```

If a moved repository has a broken virtual environment, recreate `.venv/`; virtual-environment executables can contain absolute paths. If QuantLib reports a missing SOFR fixing, confirm the valuation date and spot-start schedule are consistent. If production mode refuses to start, configure `FLASK_SECRET_KEY` and either `APP_LOGIN_PASSWORD` or `APP_LOGIN_PASSWORD_HASH` in `.env`.

## Rollback

Removing this guide rolls back documentation only. The standalone pricer is independent of the Flask server, so running it does not alter application state; delete a generated `result.json` if it is no longer needed.
