"""Asynchronous, in-memory validation portfolio for the callable-XCCY lab.

The reference pricer and QuantLib evaluation date are process-global.  Jobs are
therefore deliberately serialized through one worker and one pricing lock.  The
web request only starts or polls a job; it never waits for 20 Monte Carlo runs.
"""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import threading
import uuid
from typing import Any, Mapping

from standalone_xccy_pricer import price


PRICING_ENGINE_LOCK = threading.Lock()
_PORTFOLIO_NUMERICS = {"training_paths": 512, "pricing_paths": 1_024, "chunk_size": 1_024}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _copy_with_numerics(deal: dict[str, Any], seed: int) -> dict[str, Any]:
    value = copy.deepcopy(deal)
    value.setdefault("numerics", {}).update({**_PORTFOLIO_NUMERICS, "seed": seed})
    return value


def build_validation_portfolio(base_deal: Mapping[str, Any], spot: float) -> list[dict[str, Any]]:
    """Create 20 transparent EUR/USD callable trades for regression validation."""

    maturities = ("5Y", "7Y", "10Y", "10Y", "7Y")
    non_calls = ("1Y", "1Y", "2Y", "3Y", "2Y")
    rates = (0.0325, 0.0360, 0.0390, 0.0425, 0.0460)
    notionals = (25_000_000.0, 50_000_000.0, 75_000_000.0, 100_000_000.0)
    spreads = (-0.0005, 0.0, 0.0005, 0.0010)
    trades: list[dict[str, Any]] = []
    for index in range(20):
        trade = _copy_with_numerics(dict(base_deal), 20_000 + index)
        usd_notional = notionals[index % len(notionals)]
        trade["trade_id"] = f"VAL-EURUSD-{index + 1:02d}"
        trade["maturity"] = maturities[index % len(maturities)]
        trade["exercise"]["non_call"] = non_calls[index % len(non_calls)]
        trade["notionals"]["USD"] = usd_notional
        trade["notionals"]["EUR"] = round(usd_notional / spot, 2)
        for leg in trade["legs"]:
            if leg["currency"] == "USD":
                leg["fixed_rate"] = rates[index % len(rates)]
            else:
                leg["spread"] = spreads[index % len(spreads)]
        trades.append(trade)
    return trades


def _price(market: dict[str, Any], deal: dict[str, Any]) -> dict[str, Any]:
    with PRICING_ENGINE_LOCK:
        return price(market, deal)


def _curve_bump(market: dict[str, Any], name: str, bump_bp: float) -> dict[str, Any]:
    bumped = copy.deepcopy(market)
    for row in bumped["curves"][name]["instruments"]:
        row["rate"] = float(row["rate"]) + bump_bp * 1.0e-4
    return bumped


def _rate_vol_bump(market: dict[str, Any], currency: str, bump_bp: float) -> dict[str, Any]:
    bumped = copy.deepcopy(market)
    for row in bumped["swaptions"][currency]["points"]:
        row["normal_vol_bp"] = max(0.1, float(row["normal_vol_bp"]) + bump_bp)
    return bumped


def _fx_vol_bump(market: dict[str, Any], bump_vol_points: float) -> dict[str, Any]:
    bumped = copy.deepcopy(market)
    for row in bumped["fx_options"]["points"]:
        row["black_vol"] = max(1.0e-4, float(row["black_vol"]) + bump_vol_points * 0.01)
    return bumped


def _fx_spot_bump(market: dict[str, Any], bump_percent: float) -> dict[str, Any]:
    bumped = copy.deepcopy(market)
    multiplier = 1.0 + bump_percent / 100.0
    bumped["fx"]["spot"] = float(bumped["fx"]["spot"]) * multiplier
    for row in bumped["fx"]["forwards"]:
        row["outright"] = float(row["outright"]) * multiplier
    return bumped


def _central_value(
    market: dict[str, Any], deal: dict[str, Any], bump_market: Any, bump: float
) -> float:
    up = _price(bump_market(market, bump), deal)["valuation"]["callable_npv"]["mean"]
    down = _price(bump_market(market, -bump), deal)["valuation"]["callable_npv"]["mean"]
    return float(up - down) / 2.0


def factor_risk(market: dict[str, Any], deal: dict[str, Any]) -> dict[str, float]:
    """Central-bump factor risk using common seeds embedded in a validation trade."""

    return {
        "usd_hw_dv01": _central_value(market, deal, lambda value, bump: _curve_bump(value, "USD-SOFR", bump), 1.0),
        "eur_hw_dv01": _central_value(market, deal, lambda value, bump: _curve_bump(value, "EUR-ESTR", bump), 1.0),
        "usd_hw_vega": _central_value(market, deal, lambda value, bump: _rate_vol_bump(value, "USD", bump), 1.0),
        "eur_hw_vega": _central_value(market, deal, lambda value, bump: _rate_vol_bump(value, "EUR", bump), 1.0),
        "eurusd_delta": _central_value(market, deal, _fx_spot_bump, 1.0),
        "eurusd_vega": _central_value(market, deal, _fx_vol_bump, 1.0),
    }


class XccyPortfolioManager:
    """Small retry-safe job registry; data is intentionally process-local for the demo."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xccy-portfolio")
        self._latest_valuation_id: str | None = None

    def _new_job(self, kind: str, total: int) -> dict[str, Any]:
        job = {
            "job_id": str(uuid.uuid4()), "type": kind, "status": "QUEUED", "started_at": None,
            "finished_at": None, "error": None, "logs_path": None, "completed": 0, "total": total,
            "current_trade": None, "rows": [], "summary": {},
        }
        self._jobs[job["job_id"]] = job
        return job

    def _active(self, kind: str) -> dict[str, Any] | None:
        return next((job for job in self._jobs.values() if job["type"] == kind and job["status"] in {"QUEUED", "RUNNING"}), None)

    def start_valuation(self, market: Mapping[str, Any], deal: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            active = self._active("XCCY_VALIDATION_PORTFOLIO")
            if active:
                return self.snapshot(active["job_id"])
            job = self._new_job("XCCY_VALIDATION_PORTFOLIO", 20)
            market_copy, deal_copy = copy.deepcopy(dict(market)), copy.deepcopy(dict(deal))
            self._executor.submit(self._run_valuation, job["job_id"], market_copy, deal_copy)
            return self.snapshot(job["job_id"])

    def start_risk(self, market: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            active = self._active("XCCY_FACTOR_RISK")
            if active:
                return self.snapshot(active["job_id"])
            if not self._latest_valuation_id:
                raise ValueError("Run the 20-trade valuation portfolio before requesting factor risk.")
            valuation = self._jobs[self._latest_valuation_id]
            if valuation["status"] != "COMPLETED":
                raise ValueError("The valuation portfolio is not complete yet.")
            job = self._new_job("XCCY_FACTOR_RISK", len(valuation["trades"]))
            self._executor.submit(self._run_risk, job["job_id"], copy.deepcopy(dict(market)), copy.deepcopy(valuation["trades"]))
            return self.snapshot(job["job_id"])

    def snapshot(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return {key: copy.deepcopy(value) for key, value in job.items() if key != "trades"}

    def _run_valuation(self, job_id: str, market: dict[str, Any], base_deal: dict[str, Any]) -> None:
        trades = build_validation_portfolio(base_deal, float(market["fx"]["spot"]))
        with self._lock:
            self._jobs[job_id].update({"status": "RUNNING", "started_at": _utc_now(), "trades": trades})
        try:
            for index, trade in enumerate(trades, 1):
                with self._lock:
                    self._jobs[job_id]["current_trade"] = trade["trade_id"]
                result = _price(market, trade)
                row = {
                    "trade_id": trade["trade_id"], "maturity": trade["maturity"],
                    "non_call": trade["exercise"]["non_call"], "usd_notional": trade["notionals"]["USD"],
                    "fixed_rate": next(leg["fixed_rate"] for leg in trade["legs"] if leg["currency"] == "USD"),
                    "npv": result["valuation"]["callable_npv"]["mean"],
                    "standard_error": result["valuation"]["callable_npv"]["standard_error"], "status": result["status"],
                }
                with self._lock:
                    self._jobs[job_id]["rows"].append(row)
                    self._jobs[job_id]["completed"] = index
            with self._lock:
                job = self._jobs[job_id]
                job.update({
                    "status": "COMPLETED", "finished_at": _utc_now(), "current_trade": None,
                    "summary": {"portfolio_npv": sum(row["npv"] for row in job["rows"]), "trade_count": len(job["rows"])},
                })
                self._latest_valuation_id = job_id
        except Exception as exc:
            with self._lock:
                self._jobs[job_id].update({"status": "FAILED", "finished_at": _utc_now(), "error": str(exc)})

    def _run_risk(self, job_id: str, market: dict[str, Any], trades: list[dict[str, Any]]) -> None:
        with self._lock:
            self._jobs[job_id].update({"status": "RUNNING", "started_at": _utc_now()})
        try:
            for index, trade in enumerate(trades, 1):
                with self._lock:
                    self._jobs[job_id]["current_trade"] = trade["trade_id"]
                row = {"trade_id": trade["trade_id"], **factor_risk(market, trade)}
                with self._lock:
                    self._jobs[job_id]["rows"].append(row)
                    self._jobs[job_id]["completed"] = index
            with self._lock:
                job = self._jobs[job_id]
                totals = {key: sum(float(row[key]) for row in job["rows"]) for key in ("usd_hw_dv01", "eur_hw_dv01", "usd_hw_vega", "eur_hw_vega", "eurusd_delta", "eurusd_vega")}
                job.update({"status": "COMPLETED", "finished_at": _utc_now(), "current_trade": None, "summary": totals})
        except Exception as exc:
            with self._lock:
                self._jobs[job_id].update({"status": "FAILED", "finished_at": _utc_now(), "error": str(exc)})


_PORTFOLIO_MANAGER = XccyPortfolioManager()


def xccy_portfolio_manager() -> XccyPortfolioManager:
    return _PORTFOLIO_MANAGER
