from __future__ import annotations

from pathlib import Path

from flask import Flask

from .auth import register_auth
from .config import AppConfig
from .dashboard import register_template_filters
from .routes import workbench_bp


def create_app(test_config=None) -> Flask:
    config = AppConfig.from_env(test_config or {})
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parents[1] / "templates"),
    )
    app.config.update(config.to_flask_config())
    if test_config:
        app.config.update(test_config)

    register_template_filters(app)
    register_auth(app)
    app.register_blueprint(workbench_bp)
    return app
