"""M9 Run report reference calculations and deterministic renderers.

The formal engine remains the source of the immutable result artifact.  This
module only derives the values displayed by a Run report from that result and
reconciles the derived values with the engine's published metrics and costs.
"""

from __future__ import annotations

import html
import json
from typing import Any


RATE_SCALE = 1_000_000

_PERIOD_FIELDS = ("start_at", "end_at", "session_count")
_SUMMARY_FIELDS = (
    "starting_equity_atoms",
    "ending_equity_atoms",
    "net_pnl_atoms",
    "total_return_rate_atoms",
    "max_drawdown_atoms",
    "max_drawdown_rate_atoms",
    "gross_exposure_atoms",
    "net_exposure_atoms",
    "total_fees_atoms",
    "total_stamp_duty_atoms",
    "total_funding_atoms",
    "total_slippage_atoms",
    "order_count",
    "fill_count",
    "closed_trade_count",
    "open_position_count",
)


def canonical_report_json(report: dict[str, Any]) -> bytes:
    """Return the byte identity used by the JSON and HTML report artifacts."""

    return json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _atom(value: Any) -> str:
    return str(int(value))


def _trunc_div(numerator: int, denominator: int) -> int:
    if denominator == 0:
        return 0
    quotient = abs(numerator) // abs(denominator)
    return -quotient if (numerator < 0) != (denominator < 0) else quotient


def _artifact_id(detail: dict[str, Any], kind: str) -> str | None:
    run = detail["run"]
    direct_key = f"{kind}_artifact_id"
    direct = run.get(direct_key)
    if direct is not None:
        return direct
    artifact = detail.get("artifacts", {}).get(kind)
    if artifact is not None:
        return artifact["artifact_id"]
    return None


def _artifact_sha256(detail: dict[str, Any]) -> str | None:
    artifact = detail.get("artifacts", {}).get("engine_result")
    if artifact is not None:
        return artifact["sha256"]
    manifest = detail.get("manifest")
    if manifest is not None:
        result = manifest.get("engine_result")
        if result is not None:
            return result["sha256"]
    return detail["run"].get("calculation_hash")


def _period(result: dict[str, Any]) -> dict[str, Any]:
    curve = result.get("equity_curve", [])
    session_seqs = {point["session_seq"] for point in curve}
    return {
        "start_at": curve[0]["timestamp"] if curve else None,
        "end_at": curve[-1]["timestamp"] if curve else None,
        "session_count": len(session_seqs),
    }


def _reference_summary(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result["metrics"]
    curve = result.get("equity_curve", [])
    trades = result.get("trades", [])
    orders = result.get("orders", [])
    positions = result.get("positions", [])
    funding_ledger = result.get("funding_ledger", [])
    starting_equity = int(metrics["starting_equity_atoms"])
    ending_equity = int(curve[-1]["equity_atoms"]) if curve else starting_equity
    net_pnl = ending_equity - starting_equity
    total_return_rate = _trunc_div(net_pnl * RATE_SCALE, starting_equity)

    peak_equity = starting_equity
    max_drawdown = 0
    max_drawdown_rate = 0
    for point in curve:
        equity = int(point["equity_atoms"])
        peak_equity = max(peak_equity, equity)
        drawdown = equity - peak_equity
        drawdown_rate = _trunc_div(drawdown * RATE_SCALE, peak_equity)
        max_drawdown = min(max_drawdown, drawdown)
        max_drawdown_rate = min(max_drawdown_rate, drawdown_rate)

    total_fees = sum(int(trade["fee_atoms"]) for trade in trades)
    total_stamp_duty = sum(int(trade["stamp_duty_atoms"]) for trade in trades)
    total_slippage = sum(int(trade["slippage_atoms"]) for trade in trades)
    # The engine's funding metric is a cost: wallet deltas are the cash-side
    # movement, so the cost is their sign inverse for both long and short.
    total_funding = -sum(
        int(entry["wallet_delta_atoms"]) for entry in funding_ledger
    )
    closed_trade_count = sum(
        trade["position_effect"] == "close" for trade in trades
    )

    last_positions: dict[str, int] = {}
    for position in positions:
        symbol = position.get("symbol", "__single_account__")
        last_positions[symbol] = int(position["signed_quantity"])
    open_position_count = sum(quantity != 0 for quantity in last_positions.values())

    if curve:
        final_point = curve[-1]
        if result["schema_version"] == 2:
            net_exposure = int(final_point["market_value_atoms"])
            gross_exposure = net_exposure
        else:
            net_exposure = int(final_point["equity_atoms"]) - int(
                final_point["cash_atoms"]
            )
            gross_exposure = abs(net_exposure)
    else:
        gross_exposure = 0
        net_exposure = 0

    return {
        "starting_equity_atoms": _atom(starting_equity),
        "ending_equity_atoms": _atom(ending_equity),
        "net_pnl_atoms": _atom(net_pnl),
        "total_return_rate_atoms": _atom(total_return_rate),
        "max_drawdown_atoms": _atom(max_drawdown),
        "max_drawdown_rate_atoms": _atom(max_drawdown_rate),
        "gross_exposure_atoms": _atom(gross_exposure),
        "net_exposure_atoms": _atom(net_exposure),
        "total_fees_atoms": _atom(total_fees),
        "total_stamp_duty_atoms": _atom(total_stamp_duty),
        "total_funding_atoms": _atom(total_funding),
        "total_slippage_atoms": _atom(total_slippage),
        "order_count": len(orders),
        "fill_count": len(trades),
        "closed_trade_count": closed_trade_count,
        "open_position_count": open_position_count,
    }


def _definitions() -> list[dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {
        "start_at": {
            "name": "Period start",
            "unit": "RFC3339 timestamp",
            "formula": "first equity_curve[].timestamp",
            "inputs": ["equity_curve[].timestamp"],
            "empty_behavior": "null when equity_curve is empty",
        },
        "end_at": {
            "name": "Period end",
            "unit": "RFC3339 timestamp",
            "formula": "last equity_curve[].timestamp",
            "inputs": ["equity_curve[].timestamp"],
            "empty_behavior": "null when equity_curve is empty",
        },
        "session_count": {
            "name": "Sessions",
            "unit": "count",
            "formula": "count distinct equity_curve[].session_seq",
            "inputs": ["equity_curve[].session_seq"],
            "empty_behavior": "0 when equity_curve is empty",
        },
        "starting_equity_atoms": {
            "name": "Starting equity",
            "unit": "account atoms",
            "formula": "engine metrics starting_equity_atoms",
            "inputs": ["metrics.starting_equity_atoms"],
            "empty_behavior": "engine starting equity",
        },
        "ending_equity_atoms": {
            "name": "Ending equity",
            "unit": "account atoms",
            "formula": "last equity_curve[].equity_atoms",
            "inputs": ["equity_curve[].equity_atoms"],
            "empty_behavior": "starting equity when equity_curve is empty",
        },
        "net_pnl_atoms": {
            "name": "Net P&L",
            "unit": "account atoms",
            "formula": "ending equity - starting equity",
            "inputs": ["ending_equity_atoms", "starting_equity_atoms"],
            "empty_behavior": "0 when equity_curve is empty",
        },
        "total_return_rate_atoms": {
            "name": "Total return",
            "unit": "rate atoms (1e-6)",
            "formula": "trunc_toward_zero(net P&L * 1000000 / starting equity)",
            "inputs": ["net_pnl_atoms", "starting_equity_atoms", "rate_scale=1000000"],
            "empty_behavior": "0 when starting equity is zero",
        },
        "max_drawdown_atoms": {
            "name": "Maximum drawdown",
            "unit": "account atoms",
            "formula": "minimum equity - running peak",
            "inputs": ["equity_curve[].equity_atoms"],
            "empty_behavior": "0 when equity_curve is empty",
        },
        "max_drawdown_rate_atoms": {
            "name": "Maximum drawdown rate",
            "unit": "rate atoms (1e-6)",
            "formula": "trunc_toward_zero(drawdown * 1000000 / running peak)",
            "inputs": ["equity_curve[].equity_atoms", "rate_scale=1000000"],
            "empty_behavior": "0 when equity_curve is empty",
        },
        "gross_exposure_atoms": {
            "name": "Gross exposure",
            "unit": "account atoms",
            "formula": "abs(v1 equity - cash) or v2 market value",
            "inputs": ["equity_curve[].equity_atoms", "equity_curve[].cash_atoms", "equity_curve[].market_value_atoms"],
            "empty_behavior": "0 when equity_curve is empty",
        },
        "net_exposure_atoms": {
            "name": "Net exposure",
            "unit": "account atoms",
            "formula": "v1 equity - cash or v2 market value",
            "inputs": ["equity_curve[].equity_atoms", "equity_curve[].cash_atoms", "equity_curve[].market_value_atoms"],
            "empty_behavior": "0 when equity_curve is empty",
        },
        "total_fees_atoms": {
            "name": "Fees",
            "unit": "account atoms",
            "formula": "sum trades[].fee_atoms",
            "inputs": ["trades[].fee_atoms"],
            "empty_behavior": "0 when trades is empty",
        },
        "total_stamp_duty_atoms": {
            "name": "Stamp duty",
            "unit": "account atoms",
            "formula": "sum trades[].stamp_duty_atoms",
            "inputs": ["trades[].stamp_duty_atoms"],
            "empty_behavior": "0 when trades is empty",
        },
        "total_funding_atoms": {
            "name": "Funding",
            "unit": "account atoms",
            "formula": "-sum funding_ledger[].wallet_delta_atoms (funding cost)",
            "inputs": ["funding_ledger[].wallet_delta_atoms"],
            "empty_behavior": "0 when funding_ledger is empty",
        },
        "total_slippage_atoms": {
            "name": "Slippage",
            "unit": "account atoms",
            "formula": "sum trades[].slippage_atoms",
            "inputs": ["trades[].slippage_atoms"],
            "empty_behavior": "0 when trades is empty",
        },
        "order_count": {
            "name": "Orders",
            "unit": "count",
            "formula": "len(orders)",
            "inputs": ["orders"],
            "empty_behavior": "0 when orders is empty",
        },
        "fill_count": {
            "name": "Fills",
            "unit": "count",
            "formula": "len(trades)",
            "inputs": ["trades"],
            "empty_behavior": "0 when trades is empty",
        },
        "closed_trade_count": {
            "name": "Closed trades",
            "unit": "count",
            "formula": "count trades[].position_effect == close",
            "inputs": ["trades[].position_effect"],
            "empty_behavior": "0 when trades is empty",
        },
        "open_position_count": {
            "name": "Open positions",
            "unit": "count",
            "formula": "count symbols whose last signed_quantity is non-zero",
            "inputs": ["positions[].signed_quantity", "positions[].symbol"],
            "empty_behavior": "0 when positions is empty",
        },
    }
    return [
        {"field": field, **definitions[field]}
        for field in (*_PERIOD_FIELDS, *_SUMMARY_FIELDS)
    ]


def _reconciliation(result: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    metrics = result["metrics"]
    costs = result["costs"]
    checks: list[dict[str, Any]] = []
    metric_fields = (
        "starting_equity_atoms",
        "ending_equity_atoms",
        "net_pnl_atoms",
        "total_return_rate_atoms",
        "max_drawdown_atoms",
        "max_drawdown_rate_atoms",
        "total_fees_atoms",
        "total_stamp_duty_atoms",
        "total_funding_atoms",
        "total_slippage_atoms",
        "fill_count",
        "closed_trade_count",
        "open_position_count",
    )
    for field in metric_fields:
        expected = (
            int(metrics[field])
            if field in {"fill_count", "closed_trade_count", "open_position_count"}
            else _atom(metrics[field])
        )
        actual = summary[field]
        checks.append({"field": f"metrics.{field}", "expected": expected, "actual": actual, "passed": expected == actual})
    cost_pairs = {
        "commission_atoms": "total_fees_atoms",
        "stamp_duty_atoms": "total_stamp_duty_atoms",
        "funding_atoms": "total_funding_atoms",
        "slippage_atoms": "total_slippage_atoms",
    }
    for cost_field, summary_field in cost_pairs.items():
        expected = _atom(costs[cost_field])
        actual = summary[summary_field]
        checks.append({"field": f"costs.{cost_field}", "expected": expected, "actual": actual, "passed": expected == actual})
    return {"passed": all(check["passed"] for check in checks), "checks": checks}


def build_run_report(run_detail: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical M9 report from one succeeded Run read model."""

    run = run_detail["run"]
    result = run_detail["engine_result"]
    spec = run_detail.get("run_spec") or run_detail["manifest"]["run_spec"]
    report_period = _period(result)
    summary = _reference_summary(result)
    engine_result_sha256 = _artifact_sha256(run_detail)
    return {
        "report_version": "m9-v1",
        "run": {
            "run_id": run["run_id"],
            "run_spec_id": run["run_spec_id"],
            "project_id": run["project_id"],
            "activity_id": run["activity_id"],
            "variant_id": run["variant_id"],
            "candidate_revision_id": run["candidate_revision_id"],
            "status": "succeeded",
            "calculation_hash": run["calculation_hash"],
            "finished_at": run["finished_at"],
        },
        "identities": {
            "engine_result_sha256": engine_result_sha256,
            "engine_version": result["engine_version"],
            "engine_schema_version": result["schema_version"],
            "account_model": result["account_model"],
            "data_snapshot_id": spec["data_snapshot_id"],
            "data_snapshot_sha256": spec["data_snapshot_sha256"],
            "strategy_tree_oid": spec["strategy_tree_oid"],
            "parameters_sha256": spec["parameters_sha256"],
            "cost_model_sha256": spec["cost_model_sha256"],
            "environment_lock_sha256": spec["environment_lock_sha256"],
            "price_basis": spec["price_basis"],
            "cutoff": spec["cutoff"],
            "timezone": spec["timezone"],
            "sample_start": spec["sample_start"],
            "sample_end": spec["sample_end"],
        },
        "period": report_period,
        "summary": summary,
        "reconciliation": _reconciliation(result, summary),
        "definitions": _definitions(),
        "source": {
            "engine_result_artifact_id": _artifact_id(run_detail, "engine_result"),
            "manifest_artifact_id": _artifact_id(run_detail, "manifest"),
        },
    }


def _escaped(value: Any) -> str:
    return html.escape("null" if value is None else str(value), quote=True)


def render_run_report_html(report: dict[str, Any]) -> bytes:
    """Render a dependency-free HTML report with the exact canonical JSON."""

    identities = report["identities"]
    period = report["period"]
    summary = report["summary"]
    reconciliation = report["reconciliation"]
    definition_rows = "".join(
        "<tr>"
        f"<td>{_escaped(definition['field'])}</td>"
        f"<td>{_escaped(definition['name'])}</td>"
        f"<td>{_escaped(definition['unit'])}</td>"
        f"<td>{_escaped(definition['formula'])}</td>"
        f"<td>{_escaped(', '.join(definition['inputs']))}</td>"
        f"<td>{_escaped(definition['empty_behavior'])}</td>"
        "</tr>"
        for definition in report["definitions"]
    )
    identity_rows = "".join(
        f"<tr><th>{_escaped(key)}</th><td>{_escaped(value)}</td></tr>"
        for key, value in identities.items()
    )
    period_rows = "".join(
        f"<tr><th>{_escaped(key)}</th><td>{_escaped(value)}</td></tr>"
        for key, value in period.items()
    )
    summary_rows = "".join(
        f"<tr><th>{_escaped(key)}</th><td>{_escaped(value)}</td></tr>"
        for key, value in summary.items()
    )
    reconciliation_rows = "".join(
        "<tr>"
        f"<td>{_escaped(check['field'])}</td>"
        f"<td>{_escaped(check['expected'])}</td>"
        f"<td>{_escaped(check['actual'])}</td>"
        f"<td>{_escaped(check['passed'])}</td>"
        "</tr>"
        for check in reconciliation["checks"]
    )
    canonical_json = canonical_report_json(report).decode("utf-8")
    document = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Open Quant Studio Run Report</title></head>
<body>
<main>
<h1>Open Quant Studio Run Report</h1>
<h2>Identities</h2><table><tbody>{identity_rows}</tbody></table>
<h2>Period</h2><table><tbody>{period_rows}</tbody></table>
<h2>Summary</h2><table><tbody>{summary_rows}</tbody></table>
<h2>Reconciliation</h2><p>passed: {_escaped(reconciliation['passed'])}</p>
<table><thead><tr><th>field</th><th>expected</th><th>actual</th><th>passed</th></tr></thead><tbody>{reconciliation_rows}</tbody></table>
<h2>Definitions</h2>
<table><thead><tr><th>field</th><th>name</th><th>unit</th><th>formula</th><th>inputs</th><th>empty behavior</th></tr></thead><tbody>{definition_rows}</tbody></table>
</main>
<script id="oqs-run-report" type="application/json">{canonical_json}</script>
</body>
</html>
"""
    return document.encode("utf-8")


__all__ = [
    "build_run_report",
    "canonical_report_json",
    "render_run_report_html",
]
