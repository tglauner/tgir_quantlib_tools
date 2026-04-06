from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any
import os


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_local_env(env_path: Path | None = None) -> None:
    path = env_path or _repo_root() / ".env"
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key or key in os.environ:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


def env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def _override_or_env(overrides: dict[str, Any], key: str, env_name: str | None = None, default=None):
    if key in overrides:
        return overrides[key]
    return os.environ.get(env_name or key, default)


@dataclass(frozen=True)
class AppConfig:
    secret_key: str
    auth_username: str
    auth_password: str | None
    auth_password_hash: str | None
    debug_enabled: bool
    local_dev_host: str
    local_dev_port: int
    curve_debug_csv_path: str

    @classmethod
    def from_env(cls, overrides: dict[str, Any] | None = None) -> "AppConfig":
        load_local_env()
        overrides = overrides or {}

        debug_enabled = bool(_override_or_env(overrides, "FLASK_DEBUG", default=env_flag("FLASK_DEBUG", True)))
        testing_enabled = bool(_override_or_env(overrides, "TESTING", default=env_flag("TESTING", False)))
        strict_mode = not debug_enabled and not testing_enabled

        secret_key = _override_or_env(overrides, "SECRET_KEY", "FLASK_SECRET_KEY")
        if not secret_key:
            if strict_mode:
                raise RuntimeError(
                    "Set FLASK_SECRET_KEY in the environment or .env before starting the app."
                )
            secret_key = "tgir-quantlib-tools-local-dev-secret"

        auth_password_hash = _override_or_env(overrides, "AUTH_PASSWORD_HASH", "APP_LOGIN_PASSWORD_HASH")
        auth_password = _override_or_env(overrides, "AUTH_PASSWORD", "APP_LOGIN_PASSWORD")
        if not auth_password_hash and not auth_password:
            if strict_mode:
                raise RuntimeError(
                    "Set APP_LOGIN_PASSWORD or APP_LOGIN_PASSWORD_HASH in the environment or .env "
                    "before starting the app."
                )
            auth_password = "demo-pass-change-me"

        return cls(
            secret_key=secret_key,
            auth_username=_override_or_env(overrides, "AUTH_USERNAME", "APP_LOGIN_USERNAME", "demo"),
            auth_password=auth_password,
            auth_password_hash=auth_password_hash,
            debug_enabled=debug_enabled,
            local_dev_host=_override_or_env(overrides, "LOCAL_DEV_HOST", "FLASK_RUN_HOST", "127.0.0.1"),
            local_dev_port=int(
                _override_or_env(
                    overrides,
                    "LOCAL_DEV_PORT",
                    default=os.environ.get("PORT", os.environ.get("FLASK_RUN_PORT", "5050")),
                )
            ),
            curve_debug_csv_path=str(
                _override_or_env(
                    overrides,
                    "CURVE_DEBUG_CSV_PATH",
                    default=_repo_root() / "debug" / "curve_debug.csv",
                )
            ),
        )

    def to_flask_config(self) -> dict[str, Any]:
        return {
            "SECRET_KEY": self.secret_key,
            "AUTH_SESSION_KEY": "authenticated_user",
            "SESSION_STATE_KEY": "portfolio_state",
            "AUTH_USERNAME": self.auth_username,
            "AUTH_PASSWORD": self.auth_password,
            "AUTH_PASSWORD_HASH": self.auth_password_hash,
            "LOCAL_DEV_HOST": self.local_dev_host,
            "LOCAL_DEV_PORT": self.local_dev_port,
            "CURVE_DEBUG_CSV_PATH": self.curve_debug_csv_path,
            "FLASK_DEBUG": self.debug_enabled,
            "SESSION_COOKIE_HTTPONLY": True,
            "SESSION_COOKIE_SAMESITE": "Lax",
            "SESSION_COOKIE_SECURE": not self.debug_enabled,
            "PERMANENT_SESSION_LIFETIME": timedelta(hours=12),
        }
