# Callable XCCY MCP Server

Status: reference integration
Last verified: 2026-08-15

## Purpose and boundary

`xccy_pricer_mcp.py` exposes the standalone callable EUR/USD XCCY pricer through the Model Context Protocol. It accepts one market-data object and one deal object per call. It does not persist inputs or results, invent missing economics, price portfolios, or make the research model production-approved.

The server uses the stable MCP Python SDK 2.0 and provides stdio for local MCP hosts plus Streamable HTTP for a process on the same machine. Valuations are serialized because QuantLib's evaluation date is process-global.

## Tools

### `xccy_validate_deal`

Checks both versioned JSON Schemas and the pricer's semantic rules. The request is:

```json
{
  "request": {
    "market_data": {"schema": "xccy-market/1.0"},
    "deal_data": {"schema": "callable-xccy-deal/1.0"}
  }
}
```

`READY` means the inputs contain enough valid data to attempt pricing. `NEEDS_INPUT` includes concrete questions for missing market data or economics. `INVALID` includes paths, validation messages, and correction questions. A calling model should ask those questions and resubmit; it must not infer missing values.

### `xccy_price_deal`

Validates and prices exactly one deal. In addition to `market_data` and `deal_data`, the request supports:

- `training_paths`, `pricing_paths`, and `seed` overrides;
- `detail`: `summary` or `full`;
- `include_risk`: central FX delta and parallel USD/EUR curve PV01; and
- `include_convergence`: independent half-sized versus requested-path comparison.

The normal status is `OK`. `CALIBRATION_WARNING` means numerical valuation fields are research diagnostics only. Incomplete or invalid requests return questions without running the simulation. Responses contain a request ID for log correlation.

## Start locally

Install dependencies once:

```bash
./.venv/bin/python -m pip install -r requirements.txt
```

For a desktop or command-line MCP host, configure it to launch:

```bash
./.venv/bin/python xccy_pricer_mcp.py --transport stdio
```

For Streamable HTTP on the same machine:

```bash
./.venv/bin/python xccy_pricer_mcp.py \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8765
```

The endpoint is `http://127.0.0.1:8765/mcp`. Stop it with `Ctrl-C`.

## Python client example

Start the HTTP server, then run this from another terminal:

```python
import asyncio
import json
from pathlib import Path
from mcp import Client

async def main():
    market = json.loads(Path("data/xccy_market_eurusd.json").read_text())
    deal = json.loads(Path("data/xccy_deal_10y_nc2.json").read_text())

    async with Client("http://127.0.0.1:8765/mcp") as client:
        validation = await client.call_tool(
            "xccy_validate_deal",
            {"request": {"market_data": market, "deal_data": deal}},
        )
        print(validation.structured_content)

        result = await client.call_tool(
            "xccy_price_deal",
            {
                "request": {
                    "market_data": market,
                    "deal_data": deal,
                    "training_paths": 10000,
                    "pricing_paths": 30000,
                    "include_risk": False,
                    "include_convergence": True,
                    "detail": "summary"
                }
            },
        )
        print(result.structured_content)

asyncio.run(main())
```

Always check `result.is_error`, the structured `status`, `validation.ready_to_price`, and `calibration.accepted` before consuming an NPV.

## Risk and convergence controls

The optional risk calculation fully recalibrates and reprices with identical seeds. It reports:

- EURUSD delta as USD value change for a proportional 1% spot move, scaling outright forwards with spot to hold `F/S` fixed;
- USD-SOFR parallel DV01 in USD per basis point;
- EUR-ESTR forecast-curve parallel DV01 in USD per basis point; and
- half-bump versus full-bump relative differences, with a rudimentary 20% stability tolerance.

The convergence check compares the requested result with an independently seeded run using half the training and pricing paths. It passes when the NPV difference is within four combined Monte Carlo standard errors.

These controls do not provide bucketed risk, vega, correlation risk, gamma, cross-currency-basis PV01, seed ensembles, LSM dual bounds, or independent implementation benchmarks.

## Security and deployment

This reference server has no authentication and intentionally refuses a non-loopback bind. Do not expose port 8765 directly. For another host or trading system, put it behind an authenticated reverse proxy using TLS and an explicit client allowlist, or add a validated MCP authorization provider before permitting remote binding. Do not log market or deal payloads.

The sample JSON contains illustrative data and must not be treated as an approved market snapshot.

## Validation commands

```bash
./.venv/bin/python -m unittest tests.test_xccy_pricer_mcp -v
./.venv/bin/python -m unittest tests.test_xccy_callable_pricer -v
./.venv/bin/python -m unittest discover -s tests -v
```

Rollback is limited to removing `xccy_pricer_mcp.py`, `xccy_pricer_diagnostics.py`, this guide, and the associated test file, then removing `mcp==2.0.0` from `requirements.txt`.
