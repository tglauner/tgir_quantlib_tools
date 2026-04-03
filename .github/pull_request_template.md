## What Changed

-

## Why

-

## Validation

- [ ] `./.venv/bin/python -m unittest discover -s tests`
- [ ] `./.venv/bin/python build_SOFR_curve.py`
- [ ] `./.venv/bin/python -c "from app import app; print(app.test_client().get('/').status_code)"`

## Rollback

- `git revert <commit-hash>`

## Notes

- Document any deviations from the repo architecture guidance here.
