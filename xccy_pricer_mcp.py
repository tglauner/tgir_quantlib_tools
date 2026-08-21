"""MCP server for validating and pricing one callable EUR/USD XCCY deal.

The server exposes structured, read-only tools over stdio or Streamable HTTP.
It does not persist requests or valuations.  QuantLib valuation work is
serialized because its evaluation date is process-global.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator, FormatChecker
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from standalone_xccy_pricer import PricingError, price, validate_inputs
from xccy_pricer_diagnostics import bump_revaluation_diagnostics, path_convergence_diagnostics


LOGGER = logging.getLogger("xccy_pricer_mcp")
ROOT = Path(__file__).resolve().parent
MAX_INPUT_BYTES = 3_500_000
_PRICING_LOCK = threading.Lock()


class StrictModel(BaseModel):
    """Base model that rejects misspelled MCP request fields."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DealInputs(StrictModel):
    market_data: dict[str, Any] | None = Field(
        default=None,
        description="Complete xccy-market/1.0 object containing curves, forwards, volatilities, and correlations.",
    )
    deal_data: dict[str, Any] | None = Field(
        default=None,
        description="Complete callable-xccy-deal/1.0 object for one EUR/USD callable swap.",
    )


class PriceRequest(DealInputs):
    training_paths: int | None = Field(
        default=None,
        ge=128,
        le=2_000_000,
        description="Optional LSM training-path override; otherwise use deal.numerics or 10,000.",
    )
    pricing_paths: int | None = Field(
        default=None,
        ge=128,
        le=5_000_000,
        description="Optional independent pricing-path override; otherwise use deal.numerics or 30,000.",
    )
    seed: int | None = Field(
        default=None,
        ge=0,
        le=2**63 - 1,
        description="Optional deterministic base seed override.",
    )
    include_risk: bool = Field(
        default=False,
        description="Run central FX delta and parallel USD/EUR curve PV01 with half-bump stability checks.",
    )
    include_convergence: bool = Field(
        default=False,
        description="Compare the requested valuation with an independent half-sized path sample.",
    )
    detail: Literal["summary", "full"] = Field(
        default="summary",
        description="Return compact calibration metrics or the complete standalone-pricer audit result.",
    )


class ValidationIssue(StrictModel):
    path: str
    message: str
    question: str


class ValidationResponse(StrictModel):
    status: Literal["READY", "NEEDS_INPUT", "INVALID"]
    ready_to_price: bool
    market_schema: str | None = None
    deal_schema: str | None = None
    questions: list[str] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)


class PriceResponse(StrictModel):
    status: Literal["OK", "CALIBRATION_WARNING", "NEEDS_INPUT", "INVALID", "ERROR"]
    request_id: str
    trade_id: str | None = None
    validation: ValidationResponse
    questions: list[str] = Field(default_factory=list)
    valuation: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None
    convergence: dict[str, Any] | None = None
    error: str | None = None


def _load_schema(name: str) -> dict[str, Any]:
    path = ROOT / "data" / "schemas" / name
    return json.loads(path.read_text(encoding="utf-8"))


MARKET_VALIDATOR = Draft202012Validator(
    _load_schema("xccy_market_1_0.schema.json"), format_checker=FormatChecker()
)
DEAL_VALIDATOR = Draft202012Validator(
    _load_schema("callable_xccy_deal_1_0.schema.json"), format_checker=FormatChecker()
)


def _error_path(error: Any, root: str) -> str:
    path = root
    for item in error.absolute_path:
        path += f"[{item}]" if isinstance(item, int) else f".{item}"
    return path


def _question(path: str, message: str) -> str:
    prompts = {
        "market": "Please provide the complete market-data object.",
        "deal": "Please provide the complete deal object.",
        "deal.legs": "Please provide exactly one USD fixed leg and one EUR €STR leg, including pay/receive direction.",
        "deal.notionals": "What are the USD and EUR notionals?",
        "deal.exercise": "What are the call holder, NC period, call frequency, settlement amount, and event ordering?",
        "market.fx": "What are EURUSD spot and collateralized outright forward quotes in USD per EUR?",
        "market.curves": "Please provide complete USD-SOFR and EUR-ESTR OIS curves through the deal maturity.",
        "market.swaptions": "Please provide USD and EUR normal swaption calibration points aligned with the call schedule.",
        "market.fx_options": "Please provide ATM EURUSD Black volatilities through the deal maturity.",
        "market.correlation": "What are the USD/EUR-rate, USD-rate/FX, and EUR-rate/FX correlations?",
    }
    for prefix, prompt in prompts.items():
        if path.startswith(prefix):
            return prompt
    return f"Please provide or correct {path}: {message}"


def _schema_issues(
    validator: Draft202012Validator,
    instance: dict[str, Any],
    root: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    errors = sorted(validator.iter_errors(instance), key=lambda item: (list(item.absolute_path), item.message))
    for error in errors[:30]:
        base_path = _error_path(error, root)
        if error.validator == "required" and isinstance(error.instance, dict):
            missing = sorted(set(error.validator_value).difference(error.instance))
            for field in missing:
                path = f"{base_path}.{field}"
                issues.append(ValidationIssue(path=path, message="required field is missing", question=_question(path, error.message)))
        else:
            issues.append(
                ValidationIssue(path=base_path, message=error.message, question=_question(base_path, error.message))
            )
    return issues


def validate_deal_inputs(market_data: dict[str, Any] | None, deal_data: dict[str, Any] | None) -> ValidationResponse:
    """Validate completeness, schemas, and semantic pricing prerequisites."""

    issues: list[ValidationIssue] = []
    if market_data is None:
        issues.append(
            ValidationIssue(path="market", message="market data is missing", question=_question("market", "missing"))
        )
    if deal_data is None:
        issues.append(ValidationIssue(path="deal", message="deal data is missing", question=_question("deal", "missing")))
    if issues:
        return ValidationResponse(
            status="NEEDS_INPUT",
            ready_to_price=False,
            questions=list(dict.fromkeys(issue.question for issue in issues)),
            issues=issues,
        )

    assert market_data is not None and deal_data is not None
    payload_size = len(json.dumps({"market": market_data, "deal": deal_data}, separators=(",", ":")).encode("utf-8"))
    if payload_size > MAX_INPUT_BYTES:
        issue = ValidationIssue(
            path="$",
            message=f"combined input is {payload_size} bytes; limit is {MAX_INPUT_BYTES}",
            question="Please reduce the market/deal payload to the required pricing fields and approved calibration points.",
        )
        return ValidationResponse(
            status="INVALID", ready_to_price=False, questions=[issue.question], issues=[issue]
        )

    issues.extend(_schema_issues(MARKET_VALIDATOR, market_data, "market"))
    issues.extend(_schema_issues(DEAL_VALIDATOR, deal_data, "deal"))
    if issues:
        missing = any("missing" in issue.message for issue in issues)
        return ValidationResponse(
            status="NEEDS_INPUT" if missing else "INVALID",
            ready_to_price=False,
            market_schema=market_data.get("schema"),
            deal_schema=deal_data.get("schema"),
            questions=list(dict.fromkeys(issue.question for issue in issues)),
            issues=issues,
        )

    try:
        validate_inputs(market_data, deal_data)
    except (PricingError, KeyError, TypeError, ValueError) as exc:
        message = str(exc) or type(exc).__name__
        issue = ValidationIssue(
            path="$",
            message=message,
            question=f"Please correct the economic or market-data inconsistency: {message}",
        )
        return ValidationResponse(
            status="INVALID",
            ready_to_price=False,
            market_schema=market_data.get("schema"),
            deal_schema=deal_data.get("schema"),
            questions=[issue.question],
            issues=[issue],
        )
    return ValidationResponse(
        status="READY",
        ready_to_price=True,
        market_schema=market_data.get("schema"),
        deal_schema=deal_data.get("schema"),
    )


def _summary_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": result["schema"],
        "status": result["status"],
        "run_id": result["run_id"],
        "trade_id": result["trade_id"],
        "as_of": result["as_of"],
        "currency": result["currency"],
        "model": result["model"],
        "valuation": result["valuation"],
        "exercise": result["exercise"],
        "calibration": {
            "accepted": result["calibration"]["accepted"],
            "metrics": result["calibration"]["metrics"],
        },
        "martingale_diagnostics": result["martingale_diagnostics"],
        "regression": result["regression"],
        "numerics": result["numerics"],
        "provenance": result["provenance"],
        "limitations": result["limitations"],
    }


def _run_price_request(request: PriceRequest, validation: ValidationResponse) -> PriceResponse:
    request_id = str(uuid.uuid4())
    if not validation.ready_to_price:
        return PriceResponse(
            status=validation.status,
            request_id=request_id,
            trade_id=(request.deal_data or {}).get("trade_id"),
            validation=validation,
            questions=validation.questions,
        )

    assert request.market_data is not None and request.deal_data is not None
    numerics = request.deal_data.get("numerics", {})
    training_paths = int(request.training_paths or numerics.get("training_paths", 10_000))
    pricing_paths = int(request.pricing_paths or numerics.get("pricing_paths", 30_000))
    seed = int(request.seed if request.seed is not None else numerics.get("seed", 1_729))
    overrides = {
        "training_paths": training_paths,
        "pricing_paths": pricing_paths,
        "chunk_size": min(pricing_paths, int(numerics.get("chunk_size", 10_000))),
        "seed": seed,
    }
    with _PRICING_LOCK:
        try:
            result = price(request.market_data, request.deal_data, overrides)
            risk = (
                bump_revaluation_diagnostics(
                    request.market_data, request.deal_data, training_paths, pricing_paths, seed
                )
                if request.include_risk
                else None
            )
            convergence = (
                path_convergence_diagnostics(
                    request.market_data,
                    request.deal_data,
                    result,
                    training_paths,
                    pricing_paths,
                    seed,
                )
                if request.include_convergence
                else None
            )
        except PricingError as exc:
            message = str(exc)
            invalid = ValidationResponse(
                status="INVALID",
                ready_to_price=False,
                market_schema=request.market_data.get("schema"),
                deal_schema=request.deal_data.get("schema"),
                questions=[f"Please correct the pricing input or numerical setting: {message}"],
                issues=[ValidationIssue(path="$", message=message, question=f"Please correct: {message}")],
            )
            return PriceResponse(
                status="INVALID",
                request_id=request_id,
                trade_id=request.deal_data.get("trade_id"),
                validation=invalid,
                questions=invalid.questions,
                error=message,
            )
        except Exception:
            LOGGER.exception("Unexpected XCCY MCP valuation failure request_id=%s", request_id)
            return PriceResponse(
                status="ERROR",
                request_id=request_id,
                trade_id=request.deal_data.get("trade_id"),
                validation=validation,
                error="Unexpected internal pricing error. Review the server log using the request_id.",
            )
    return PriceResponse(
        status=result["status"],
        request_id=request_id,
        trade_id=result.get("trade_id"),
        validation=validation,
        valuation=result if request.detail == "full" else _summary_result(result),
        risk=risk,
        convergence=convergence,
    )


mcp = MCPServer(
    name="xccy_pricer_mcp",
    version="1.0.0",
    instructions=(
        "Validate and price exactly one callable EUR/USD cross-currency swap. "
        "Call xccy_validate_deal first when inputs may be incomplete. If a response contains questions, "
        "obtain those answers and call again; never invent market data or trade economics."
    ),
)


READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


@mcp.tool(
    name="xccy_validate_deal",
    title="Validate Callable XCCY Deal",
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def xccy_validate_deal(request: DealInputs) -> ValidationResponse:
    """Check whether one callable EUR/USD deal has enough data to price.

    Returns READY only after JSON-Schema and semantic validation. Incomplete
    inputs return NEEDS_INPUT plus specific questions that the calling system or
    model should ask before attempting valuation. This tool never prices a deal.
    """

    return validate_deal_inputs(request.market_data, request.deal_data)


@mcp.tool(
    name="xccy_price_deal",
    title="Price One Callable XCCY Deal",
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def xccy_price_deal(request: PriceRequest) -> PriceResponse:
    """Validate and price exactly one callable EUR/USD XCCY swap.

    The result contains NPV, Monte Carlo error, exercise profile, calibration,
    martingale, regression, and provenance diagnostics. Optional risk performs
    full-recalibration central bumps; optional convergence compares independent
    path counts. Missing data returns questions instead of guessed values.
    """

    validation = validate_deal_inputs(request.market_data, request.deal_data)
    return await asyncio.to_thread(_run_price_request, request, validation)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport; stdio is for a local host process.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind address; loopback only in this reference server.")
    parser.add_argument("--port", type=int, default=8765, help="Streamable HTTP port.")
    return parser.parse_args()


def main() -> int:
    arguments = _parse_args()
    try:
        if arguments.transport == "streamable-http":
            if arguments.host not in {"127.0.0.1", "localhost", "::1"}:
                raise SystemExit(
                    "Remote binding is disabled because this reference server has no authentication. "
                    "Bind to loopback and expose it only through an authenticated reverse proxy."
                )
            mcp.run(
                transport="streamable-http",
                host=arguments.host,
                port=arguments.port,
                streamable_http_path="/mcp",
                stateless_http=True,
                json_response=True,
            )
        else:
            mcp.run(transport="stdio")
    except KeyboardInterrupt:
        LOGGER.info("XCCY MCP server stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
