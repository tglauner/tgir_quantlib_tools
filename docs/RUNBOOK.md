# Runbook

## Setup
```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set at least:

```bash
FLASK_SECRET_KEY=<long-random-secret>
APP_LOGIN_USERNAME=<username>
APP_LOGIN_PASSWORD=<strong-password>
```

## Run The Flask App
```bash
./.venv/bin/python app.py
```

Open `http://127.0.0.1:5050/` after the server starts, sign in, and the app will redirect to `/dashboard`.

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

## Health Check
```bash
./.venv/bin/python -c "from app import app; print(app.test_client().get('/health').json)"
```

## Troubleshooting
- If `.venv/bin/pip` points to an old repo path after moving or renaming the project, recreate `.venv`.
- If QuantLib raises a missing SOFR fixing error, confirm the swap start date is on spot and not the evaluation date.
- If `127.0.0.1:5000` returns a `403`, use the default `5050` port in this repo instead; macOS services frequently occupy `5000`.
- If you want a different local port, run `PORT=5051 ./.venv/bin/python app.py`.
- If the app refuses to start with `FLASK_DEBUG=0`, confirm that both `FLASK_SECRET_KEY` and one of `APP_LOGIN_PASSWORD` or `APP_LOGIN_PASSWORD_HASH` are configured.
- To generate a password hash, run `./.venv/bin/python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('replace-me'))"`.
- If Git warns that the GitHub repository moved, update `origin` to `git@github.com:tglauner/tgir_quantlib_tools.git`.

## Rollback
```bash
git revert <commit-hash>
```
