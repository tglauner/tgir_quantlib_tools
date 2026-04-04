# Runbook

## Setup
```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

## Run The Flask App
```bash
./.venv/bin/python app.py
```

Open `http://127.0.0.1:5050/` after the server starts.

## Run The Curve Demo
```bash
./.venv/bin/python build_SOFR_curve.py
```

## Run The Tests
```bash
./.venv/bin/python -m unittest discover -s tests
```

## Flask Smoke Check
```bash
./.venv/bin/python -c "from app import app; print(app.test_client().get('/').status_code)"
```

## Troubleshooting
- If `.venv/bin/pip` points to an old repo path after moving or renaming the project, recreate `.venv`.
- If QuantLib raises a missing SOFR fixing error, confirm the swap start date is on spot and not the evaluation date.
- If `127.0.0.1:5000` returns a `403`, use the default `5050` port in this repo instead; macOS services frequently occupy `5000`.
- If you want a different local port, run `PORT=5051 ./.venv/bin/python app.py`.
- If Git warns that the GitHub repository moved, update `origin` to `git@github.com:tglauner/tgir_quantlib_tools.git`.

## Rollback
```bash
git revert <commit-hash>
```
