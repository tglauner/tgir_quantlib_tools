from __future__ import annotations

from functools import wraps
from urllib.parse import urlparse

from flask import current_app, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash


def current_username() -> str | None:
    return session.get(current_app.config["AUTH_SESSION_KEY"])


def is_authenticated() -> bool:
    return bool(current_username())


def login_user(username: str) -> None:
    session[current_app.config["AUTH_SESSION_KEY"]] = username
    session.permanent = True
    session.modified = True


def logout_user() -> None:
    session.pop(current_app.config["AUTH_SESSION_KEY"], None)
    session.pop(current_app.config["SESSION_STATE_KEY"], None)
    session.modified = True


def credentials_are_valid(username: str, password: str) -> bool:
    expected_username = current_app.config["AUTH_USERNAME"]
    if username != expected_username:
        return False

    expected_hash = current_app.config.get("AUTH_PASSWORD_HASH")
    if expected_hash:
        return check_password_hash(expected_hash, password)

    expected_password = current_app.config.get("AUTH_PASSWORD")
    return bool(expected_password) and password == expected_password


def is_safe_next_path(target: str | None) -> bool:
    if not target:
        return False

    parsed = urlparse(target)
    return parsed.scheme == "" and parsed.netloc == "" and target.startswith("/")


def redirect_target(target: str | None) -> str:
    if is_safe_next_path(target):
        return target
    return url_for("workbench.dashboard")


def _auth_failure_response():
    login_url = url_for("workbench.login", next=request.full_path.rstrip("?") or request.path)
    if request.path.startswith("/api/") or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"error": "authentication required", "login_url": login_url}), 401
    return redirect(login_url)


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if is_authenticated():
            return view_func(*args, **kwargs)
        return _auth_failure_response()

    return wrapped


def register_auth(app) -> None:
    @app.context_processor
    def inject_auth_state():
        return {
            "auth_state": {
                "is_authenticated": is_authenticated(),
                "username": current_username(),
            }
        }
