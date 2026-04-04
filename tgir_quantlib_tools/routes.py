from __future__ import annotations

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from portfolio import default_portfolio_state

from .auth import (
    credentials_are_valid,
    is_authenticated,
    login_required,
    login_user,
    logout_user,
    redirect_target,
)
from .dashboard import (
    TRADE_FORM_DEFINITIONS,
    apply_realtime_tick,
    build_dashboard_context,
    build_realtime_payload,
    build_trade_editor_context,
    get_portfolio_state,
    save_portfolio_state,
    update_market_state,
    update_trade_state,
)


workbench_bp = Blueprint("workbench", __name__)


@workbench_bp.get("/")
def home():
    if is_authenticated():
        return redirect(url_for("workbench.dashboard"))
    return render_template("login.html", next_path=request.args.get("next", ""), username="")


@workbench_bp.route("/login", methods=["GET", "POST"])
def login():
    next_path = request.values.get("next", "")
    if is_authenticated():
        return redirect(redirect_target(next_path))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if credentials_are_valid(username, password):
            login_user(username)
            flash("Signed in.", "success")
            return redirect(redirect_target(next_path))
        flash("Invalid username or password.", "error")
        return render_template("login.html", next_path=next_path, username=username), 401

    return render_template("login.html", next_path=next_path, username="")


@workbench_bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("Signed out.", "success")
    return redirect(url_for("workbench.login"))


@workbench_bp.get("/health")
def health():
    return jsonify({"ok": True, "app": "tgir_quantlib_tools"})


@workbench_bp.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", **build_dashboard_context(get_portfolio_state()))


@workbench_bp.post("/market")
@login_required
def update_market():
    state = get_portfolio_state()
    update_market_state(state, request.form)
    save_portfolio_state(state)
    flash("Market settings updated.", "success")
    return redirect(url_for("workbench.dashboard"))


@workbench_bp.post("/reset")
@login_required
def reset_portfolio():
    save_portfolio_state(default_portfolio_state())
    flash("Portfolio reset to the demo defaults.", "success")
    return redirect(url_for("workbench.dashboard"))


@workbench_bp.post("/api/realtime/tick")
@login_required
def realtime_tick():
    state = get_portfolio_state()
    apply_realtime_tick(state)
    save_portfolio_state(state)
    return jsonify(build_realtime_payload(state))


@workbench_bp.route("/trade/<trade_type>", methods=["GET", "POST"])
@login_required
def edit_trade(trade_type):
    if trade_type not in TRADE_FORM_DEFINITIONS:
        abort(404)

    state = get_portfolio_state()
    if request.method == "POST":
        update_trade_state(state, trade_type, request.form)
        save_portfolio_state(state)
        flash(f"{TRADE_FORM_DEFINITIONS[trade_type]['title']} updated.", "success")
        return redirect(url_for("workbench.dashboard"))

    return render_template("trade_form.html", **build_trade_editor_context(state, trade_type))
