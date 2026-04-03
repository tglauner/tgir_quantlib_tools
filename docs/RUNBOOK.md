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

Open `http://127.0.0.1:5000/` after the server starts.

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
- If Git warns that the GitHub repository moved, update `origin` to `git@github.com:tglauner/tgir_quantlib_tools.git`.

## Rollback
```bash
git revert <commit-hash>
```
