"""M9 Run report reference calculations and deterministic renderers.

The formal engine remains the source of the immutable result artifact.  This
module only derives the values displayed by a Run report from that result and
reconciles the derived values with the engine's published metrics and costs.
"""

from __future__ import annotations

import html
import json
from collections import defaultdict
from typing import Any


RATE_SCALE = 1_000_000

_V3_TOP_LEVEL_FIELDS = (
    "schema_version",
    "engine_version",
    "account_model",
    "orders",
    "fills",
    "positions",
    "cash_ledger",
    "corporate_action_ledger",
    "equity_curve",
    "drawdown_curve",
    "metrics",
    "costs",
    "assumptions",
)
_V3_ORDER_FIELDS = (
    "intent_id",
    "intent_seq",
    "symbol",
    "book",
    "status",
    "reject_reason",
    "side",
    "position_effect",
    "order_type",
    "quantity",
    "remaining_quantity",
    "filled_session_seq",
    "filled_phase",
    "cancelled_intent_id",
    "condition_intent_id",
)
_V3_FILL_FIELDS = (
    "fill_id",
    "intent_id",
    "intent_seq",
    "symbol",
    "book",
    "session_seq",
    "side",
    "position_effect",
    "quantity",
    "fill_price_atoms",
    "notional_atoms",
    "fee_atoms",
    "stamp_duty_atoms",
    "slippage_atoms",
    "liquidity",
    "volume_before",
    "volume_after",
    "remaining_quantity",
    "frozen_margin_delta_atoms",
    "isolated_proceeds_delta_atoms",
    "condition_intent_id",
)
_V3_POSITION_FIELDS = (
    "intent_id",
    "symbol",
    "book",
    "session_seq",
    "signed_quantity",
    "eligible_quantity",
)
_V3_CASH_FIELDS = (
    "intent_id",
    "symbol",
    "book",
    "session_seq",
    "notional_delta_atoms",
    "fee_delta_atoms",
    "stamp_duty_delta_atoms",
    "realized_pnl_delta_atoms",
    "resulting_available_cash_atoms",
    "frozen_margin_delta_atoms",
    "isolated_proceeds_delta_atoms",
)
_V3_CORPORATE_FIELDS = (
    "action_id",
    "symbol",
    "session_seq",
    "action_type",
    "book",
    "quantity_before",
    "quantity_after",
    "available_cash_delta_atoms",
    "frozen_margin_delta_atoms",
    "isolated_proceeds_delta_atoms",
    "realized_pnl_delta_atoms",
    "resulting_available_cash_atoms",
    "resulting_frozen_margin_atoms",
    "resulting_isolated_proceeds_atoms",
)
_V3_EQUITY_FIELDS = (
    "session_seq",
    "timestamp",
    "available_cash_atoms",
    "long_market_value_atoms",
    "short_liability_atoms",
    "gross_market_value_atoms",
    "net_market_value_atoms",
    "market_value_atoms",
    "equity_atoms",
    "frozen_margin_atoms",
    "isolated_short_proceeds_atoms",
)
_V3_DRAWDOWN_FIELDS = (
    "session_seq",
    "equity_atoms",
    "peak_equity_atoms",
    "drawdown_atoms",
    "drawdown_rate_atoms",
)
_V3_METRIC_ATOM_FIELDS = (
    "starting_equity_atoms",
    "ending_equity_atoms",
    "net_pnl_atoms",
    "total_return_rate_atoms",
    "max_drawdown_atoms",
    "max_drawdown_rate_atoms",
    "total_fees_atoms",
    "total_stamp_duty_atoms",
    "total_slippage_atoms",
)
_V3_METRIC_COUNT_FIELDS = (
    "fill_count",
    "closed_trade_count",
    "open_position_count",
)
_V3_COST_FIELDS = (
    "commission_atoms",
    "stamp_duty_atoms",
    "slippage_atoms",
)
_V3_ASSUMPTION_FIELDS = (
    "fill_model",
    "partial_fills",
    "liquidate_on_end",
    "cash_long",
    "research_short",
    "limit_orders",
    "corporate_actions",
    "tradability_gates",
    "t_plus_one",
)

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


class _V3InvariantErrors:
    """Keep reconciliation output bounded while retaining the first failure."""

    def __init__(self) -> None:
        self._failures: dict[str, tuple[int, str]] = {}

    def require(self, group: str, condition: bool, detail: str) -> None:
        if condition:
            return
        count, first = self._failures.get(group, (0, detail))
        self._failures[group] = (count + 1, first)

    def check(self, group: str) -> dict[str, Any]:
        failure = self._failures.get(group)
        if failure is None:
            return {
                "field": group,
                "expected": "valid",
                "actual": "valid",
                "passed": True,
            }
        count, first = failure
        return {
            "field": group,
            "expected": "valid",
            "actual": f"{count} failure(s); first: {first}",
            "passed": False,
        }


def _v3_is_atom(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if value == "0":
        return True
    digits = value[1:] if value.startswith("-") else value
    return bool(digits) and digits[0] != "0" and digits.isdigit()


def _v3_atom(
    record: dict[str, Any],
    field: str,
    path: str,
    errors: _V3InvariantErrors,
) -> int | None:
    value = record.get(field)
    valid = _v3_is_atom(value)
    errors.require(
        "v3.required_fields",
        valid,
        f"{path}.{field} is not a canonical integer atom",
    )
    return int(value) if valid else None


def _v3_count(
    record: dict[str, Any],
    field: str,
    path: str,
    errors: _V3InvariantErrors,
) -> int | None:
    value = record.get(field)
    valid = type(value) is int and value >= 0
    errors.require(
        "v3.required_fields",
        valid,
        f"{path}.{field} is not a non-negative integer",
    )
    return value if valid else None


def _v3_require_fields(
    record: Any,
    fields: tuple[str, ...],
    path: str,
    errors: _V3InvariantErrors,
) -> bool:
    if not isinstance(record, dict):
        errors.require("v3.required_fields", False, f"{path} is not an object")
        return False
    missing = [field for field in fields if field not in record]
    errors.require(
        "v3.required_fields",
        not missing,
        f"{path} is missing {','.join(missing)}",
    )
    return not missing


def _v3_list(
    result: dict[str, Any],
    field: str,
    errors: _V3InvariantErrors,
) -> list[Any]:
    value = result.get(field)
    valid = isinstance(value, list)
    errors.require(
        "v3.required_fields",
        valid,
        f"result.{field} is not an array",
    )
    return value if valid else []


def _v3_key(record: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (
        record.get("intent_id"),
        record.get("symbol"),
        record.get("book"),
        record.get("session_seq"),
    )


def _v3_reconciliation_value(value: int | None) -> str | int:
    return "<missing-or-invalid>" if value is None else value


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
    if result.get("schema_version") == 3:
        if not isinstance(curve, list):
            curve = []
        first = curve[0] if curve and isinstance(curve[0], dict) else {}
        last = curve[-1] if curve and isinstance(curve[-1], dict) else {}
        session_seqs = {
            point.get("session_seq")
            for point in curve
            if isinstance(point, dict) and type(point.get("session_seq")) is int
        }
        return {
            "start_at": first.get("timestamp"),
            "end_at": last.get("timestamp"),
            "session_count": len(session_seqs),
        }
    session_seqs = {point["session_seq"] for point in curve}
    return {
        "start_at": curve[0]["timestamp"] if curve else None,
        "end_at": curve[-1]["timestamp"] if curve else None,
        "session_count": len(session_seqs),
    }


def _v3_reference_and_reconciliation(
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Replay the public v3 ledgers without trusting Rust summary fields."""

    errors = _V3InvariantErrors()
    _v3_require_fields(result, _V3_TOP_LEVEL_FIELDS, "result", errors)
    errors.require(
        "v3.required_fields",
        result.get("schema_version") == 3,
        "result.schema_version is not 3",
    )
    errors.require(
        "v3.required_fields",
        result.get("engine_version") == "oqs-quant-engine/0.3.0",
        "result.engine_version is not oqs-quant-engine/0.3.0",
    )
    errors.require(
        "v3.required_fields",
        result.get("account_model") == "a_share_portfolio_research",
        "result.account_model is not a_share_portfolio_research",
    )

    orders = _v3_list(result, "orders", errors)
    raw_fills = _v3_list(result, "fills", errors)
    raw_positions = _v3_list(result, "positions", errors)
    raw_cash = _v3_list(result, "cash_ledger", errors)
    raw_corporate = _v3_list(result, "corporate_action_ledger", errors)
    raw_equity = _v3_list(result, "equity_curve", errors)
    raw_drawdown = _v3_list(result, "drawdown_curve", errors)
    assumptions = result.get("assumptions")
    errors.require(
        "v3.required_fields",
        isinstance(assumptions, dict),
        "result.assumptions is not an object",
    )
    _v3_require_fields(
        assumptions,
        _V3_ASSUMPTION_FIELDS,
        "assumptions",
        errors,
    )
    if isinstance(assumptions, dict):
        expected_assumptions = {
            "fill_model": "a_share_dual_book_market_open_v3",
            "partial_fills": True,
            "liquidate_on_end": False,
            "cash_long": True,
            "research_short": True,
            "limit_orders": True,
            "corporate_actions": True,
            "tradability_gates": True,
            "t_plus_one": True,
        }
        errors.require(
            "v3.required_fields",
            all(
                assumptions.get(field) == value
                for field, value in expected_assumptions.items()
            ),
            "assumptions do not match the v3 A-share execution model",
        )
    order_by_intent: dict[str, dict[str, Any]] = {}
    for index, order in enumerate(orders):
        path = f"orders[{index}]"
        if not _v3_require_fields(order, _V3_ORDER_FIELDS, path, errors):
            if not isinstance(order, dict):
                continue
        assert isinstance(order, dict)
        intent_id = order.get("intent_id")
        parsed_order = {
            **order,
            "index": index,
            "intent_seq_value": _v3_count(order, "intent_seq", path, errors),
            "quantity_value": _v3_atom(order, "quantity", path, errors),
            "remaining_value": _v3_atom(
                order, "remaining_quantity", path, errors
            ),
        }
        errors.require(
            "v3.required_fields",
            isinstance(intent_id, str) and bool(intent_id),
            f"{path}.intent_id is not a non-empty string",
        )
        errors.require(
            "v3.fill_accounting",
            isinstance(intent_id, str) and intent_id not in order_by_intent,
            f"{path}.intent_id is duplicated",
        )
        errors.require(
            "v3.fill_accounting",
            parsed_order["quantity_value"] is not None
            and parsed_order["quantity_value"] >= 0
            and parsed_order["remaining_value"] is not None
            and 0
            <= parsed_order["remaining_value"]
            <= parsed_order["quantity_value"],
            f"{path} has an invalid quantity/remaining quantity",
        )
        if isinstance(intent_id, str):
            order_by_intent[intent_id] = parsed_order

    metrics = result.get("metrics")
    _v3_require_fields(
        metrics,
        (*_V3_METRIC_ATOM_FIELDS, *_V3_METRIC_COUNT_FIELDS),
        "metrics",
        errors,
    )
    if not isinstance(metrics, dict):
        metrics = {}
    metric_atoms = {
        field: _v3_atom(metrics, field, "metrics", errors)
        for field in _V3_METRIC_ATOM_FIELDS
    }
    metric_counts = {
        field: _v3_count(metrics, field, "metrics", errors)
        for field in _V3_METRIC_COUNT_FIELDS
    }
    starting_equity = metric_atoms["starting_equity_atoms"]
    errors.require(
        "v3.required_fields",
        starting_equity is not None and starting_equity > 0,
        "metrics.starting_equity_atoms is not positive",
    )
    starting_cash = starting_equity if starting_equity is not None else 0

    costs = result.get("costs")
    _v3_require_fields(costs, _V3_COST_FIELDS, "costs", errors)
    if not isinstance(costs, dict):
        costs = {}
    cost_atoms = {
        field: _v3_atom(costs, field, "costs", errors)
        for field in _V3_COST_FIELDS
    }

    fills: list[dict[str, Any]] = []
    fill_ids: set[str] = set()
    for index, record in enumerate(raw_fills):
        path = f"fills[{index}]"
        if not _v3_require_fields(record, _V3_FILL_FIELDS, path, errors):
            if not isinstance(record, dict):
                continue
        assert isinstance(record, dict)
        parsed = {
            **record,
            "index": index,
            "intent_seq_value": _v3_count(record, "intent_seq", path, errors),
            "session_value": _v3_count(record, "session_seq", path, errors),
        }
        for field in (
            "quantity",
            "fill_price_atoms",
            "notional_atoms",
            "fee_atoms",
            "stamp_duty_atoms",
            "slippage_atoms",
            "volume_before",
            "volume_after",
            "remaining_quantity",
            "frozen_margin_delta_atoms",
            "isolated_proceeds_delta_atoms",
        ):
            parsed[f"{field}_value"] = _v3_atom(record, field, path, errors)
        identity_valid = all(
            isinstance(record.get(field), str) and bool(record[field])
            for field in ("fill_id", "intent_id", "symbol")
        )
        errors.require(
            "v3.required_fields", identity_valid, f"{path} has an invalid identity"
        )
        fill_id = record.get("fill_id")
        errors.require(
            "v3.fill_accounting",
            isinstance(fill_id, str) and fill_id not in fill_ids,
            f"{path}.fill_id is duplicated",
        )
        if isinstance(fill_id, str):
            fill_ids.add(fill_id)
        quantity = parsed["quantity_value"]
        price = parsed["fill_price_atoms_value"]
        notional = parsed["notional_atoms_value"]
        volume_before = parsed["volume_before_value"]
        volume_after = parsed["volume_after_value"]
        remaining = parsed["remaining_quantity_value"]
        fee = parsed["fee_atoms_value"]
        stamp = parsed["stamp_duty_atoms_value"]
        slippage = parsed["slippage_atoms_value"]
        errors.require(
            "v3.fill_accounting",
            quantity is not None and quantity > 0,
            f"{path}.quantity is not positive",
        )
        errors.require(
            "v3.fill_accounting",
            price is not None and price > 0,
            f"{path}.fill_price_atoms is not positive",
        )
        errors.require(
            "v3.fill_accounting",
            None not in (quantity, price, notional) and notional == quantity * price,
            f"{path}.notional_atoms != quantity * fill_price_atoms",
        )
        errors.require(
            "v3.fill_accounting",
            None not in (volume_before, volume_after, quantity)
            and volume_before >= quantity
            and volume_after == volume_before - quantity,
            f"{path}.volume_after != volume_before - quantity",
        )
        errors.require(
            "v3.fill_accounting",
            remaining is not None and remaining >= 0,
            f"{path}.remaining_quantity is negative",
        )
        errors.require(
            "v3.fill_accounting",
            all(value is not None and value >= 0 for value in (fee, stamp, slippage)),
            f"{path} has a negative execution cost",
        )
        valid_combinations = {
            ("cash_long", "buy", "open"),
            ("cash_long", "sell", "close"),
            ("research_short", "sell", "open"),
            ("research_short", "buy", "close"),
        }
        errors.require(
            "v3.fill_accounting",
            (
                record.get("book"),
                record.get("side"),
                record.get("position_effect"),
            )
            in valid_combinations,
            f"{path} has an invalid book/side/effect combination",
        )
        errors.require(
            "v3.fill_accounting",
            record.get("liquidity") == "taker",
            f"{path}.liquidity is not taker",
        )
        fills.append(parsed)

    filled_by_intent: dict[str, int] = defaultdict(int)
    for fill in fills:
        intent_id = fill.get("intent_id")
        detail = f"fills[{fill['index']}]"
        order = order_by_intent.get(intent_id) if isinstance(intent_id, str) else None
        errors.require(
            "v3.fill_accounting",
            order is not None,
            f"{detail} has no matching order",
        )
        if order is None or not isinstance(intent_id, str):
            continue
        for field in ("intent_seq", "symbol", "book", "side", "position_effect"):
            fill_value = (
                fill["intent_seq_value"] if field == "intent_seq" else fill.get(field)
            )
            order_value = (
                order["intent_seq_value"]
                if field == "intent_seq"
                else order.get(field)
            )
            errors.require(
                "v3.fill_accounting",
                fill_value == order_value,
                f"{detail}.{field} does not match orders[{order['index']}]",
            )
        quantity = fill["quantity_value"]
        if quantity is None:
            continue
        filled_by_intent[intent_id] += quantity
        expected_remaining = (
            order["quantity_value"] - filled_by_intent[intent_id]
            if order["quantity_value"] is not None
            else None
        )
        errors.require(
            "v3.fill_accounting",
            expected_remaining is not None
            and expected_remaining >= 0
            and fill["remaining_quantity_value"] == expected_remaining,
            f"{detail}.remaining_quantity does not match cumulative fills",
        )
    for intent_id, filled_quantity in filled_by_intent.items():
        order = order_by_intent[intent_id]
        quantity = order["quantity_value"]
        remaining = order["remaining_value"]
        errors.require(
            "v3.fill_accounting",
            quantity is not None
            and remaining is not None
            and filled_quantity + remaining == quantity,
            f"orders[{order['index']}] quantity does not equal filled + remaining",
        )

    positions: list[dict[str, Any]] = []
    for index, record in enumerate(raw_positions):
        path = f"positions[{index}]"
        if not _v3_require_fields(record, _V3_POSITION_FIELDS, path, errors):
            if not isinstance(record, dict):
                continue
        assert isinstance(record, dict)
        positions.append(
            {
                **record,
                "index": index,
                "session_value": _v3_count(record, "session_seq", path, errors),
                "signed_value": _v3_atom(
                    record, "signed_quantity", path, errors
                ),
                "eligible_value": _v3_atom(
                    record, "eligible_quantity", path, errors
                ),
            }
        )

    cash_records: list[dict[str, Any]] = []
    for index, record in enumerate(raw_cash):
        path = f"cash_ledger[{index}]"
        if not _v3_require_fields(record, _V3_CASH_FIELDS, path, errors):
            if not isinstance(record, dict):
                continue
        assert isinstance(record, dict)
        parsed = {
            **record,
            "index": index,
            "session_value": _v3_count(record, "session_seq", path, errors),
        }
        for field in (
            "notional_delta_atoms",
            "fee_delta_atoms",
            "stamp_duty_delta_atoms",
            "realized_pnl_delta_atoms",
            "resulting_available_cash_atoms",
            "frozen_margin_delta_atoms",
            "isolated_proceeds_delta_atoms",
        ):
            parsed[f"{field}_value"] = _v3_atom(record, field, path, errors)
        cash_records.append(parsed)

    corporate: list[dict[str, Any]] = []
    for index, record in enumerate(raw_corporate):
        path = f"corporate_action_ledger[{index}]"
        if not _v3_require_fields(record, _V3_CORPORATE_FIELDS, path, errors):
            if not isinstance(record, dict):
                continue
        assert isinstance(record, dict)
        parsed = {
            **record,
            "index": index,
            "session_value": _v3_count(record, "session_seq", path, errors),
        }
        for field in (
            "quantity_before",
            "quantity_after",
            "available_cash_delta_atoms",
            "frozen_margin_delta_atoms",
            "isolated_proceeds_delta_atoms",
            "realized_pnl_delta_atoms",
            "resulting_available_cash_atoms",
            "resulting_frozen_margin_atoms",
            "resulting_isolated_proceeds_atoms",
        ):
            parsed[f"{field}_value"] = _v3_atom(record, field, path, errors)
        corporate.append(parsed)

    equity: list[dict[str, Any]] = []
    for index, record in enumerate(raw_equity):
        path = f"equity_curve[{index}]"
        if not _v3_require_fields(record, _V3_EQUITY_FIELDS, path, errors):
            if not isinstance(record, dict):
                continue
        assert isinstance(record, dict)
        parsed = {
            **record,
            "index": index,
            "session_value": _v3_count(record, "session_seq", path, errors),
        }
        for field in (
            "available_cash_atoms",
            "long_market_value_atoms",
            "short_liability_atoms",
            "gross_market_value_atoms",
            "net_market_value_atoms",
            "market_value_atoms",
            "equity_atoms",
            "frozen_margin_atoms",
            "isolated_short_proceeds_atoms",
        ):
            parsed[f"{field}_value"] = _v3_atom(record, field, path, errors)
        errors.require(
            "v3.required_fields",
            isinstance(record.get("timestamp"), str) and bool(record["timestamp"]),
            f"{path}.timestamp is not a non-empty string",
        )
        equity.append(parsed)

    drawdown: list[dict[str, Any]] = []
    for index, record in enumerate(raw_drawdown):
        path = f"drawdown_curve[{index}]"
        if not _v3_require_fields(record, _V3_DRAWDOWN_FIELDS, path, errors):
            if not isinstance(record, dict):
                continue
        assert isinstance(record, dict)
        parsed = {
            **record,
            "index": index,
            "session_value": _v3_count(record, "session_seq", path, errors),
        }
        for field in (
            "equity_atoms",
            "peak_equity_atoms",
            "drawdown_atoms",
            "drawdown_rate_atoms",
        ):
            parsed[f"{field}_value"] = _v3_atom(record, field, path, errors)
        drawdown.append(parsed)

    for values, group, label in (
        (fills, "v3.fill_accounting", "fills"),
        (cash_records, "v3.cash_ledger", "cash_ledger"),
        (positions, "v3.position_ledger", "positions"),
        (corporate, "v3.corporate_action_ledger", "corporate_action_ledger"),
        (equity, "v3.equity_curve", "equity_curve"),
        (drawdown, "v3.drawdown_curve", "drawdown_curve"),
    ):
        sessions = [row["session_value"] for row in values]
        errors.require(
            group,
            all(session is not None for session in sessions)
            and sessions == sorted(sessions),
            f"{label} is not ordered by session_seq",
        )

    cash_by_key: dict[tuple[Any, Any, Any, Any], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for record in cash_records:
        cash_by_key[_v3_key(record)].append(record)
    position_by_key: dict[tuple[Any, Any, Any, Any], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for record in positions:
        position_by_key[_v3_key(record)].append(record)
    cash_key_offsets: dict[tuple[Any, Any, Any, Any], int] = defaultdict(int)
    position_key_offsets: dict[tuple[Any, Any, Any, Any], int] = defaultdict(int)
    consumed_cash: set[int] = set()
    consumed_positions: set[int] = set()
    cash_order_cursor = 0
    position_order_cursor = 0

    def take_cash(
        key: tuple[Any, Any, Any, Any], detail: str
    ) -> dict[str, Any] | None:
        nonlocal cash_order_cursor
        offset = cash_key_offsets[key]
        matches = cash_by_key.get(key, [])
        if offset >= len(matches):
            errors.require(
                "v3.cash_ledger", False, f"{detail} has no matching cash row"
            )
            return None
        record = matches[offset]
        cash_key_offsets[key] += 1
        index = record["index"]
        errors.require(
            "v3.cash_ledger",
            index == cash_order_cursor,
            f"cash_ledger[{index}] is out of replay order",
        )
        cash_order_cursor += 1
        consumed_cash.add(index)
        return record

    def take_position(
        key: tuple[Any, Any, Any, Any], detail: str
    ) -> dict[str, Any] | None:
        nonlocal position_order_cursor
        offset = position_key_offsets[key]
        matches = position_by_key.get(key, [])
        if offset >= len(matches):
            errors.require(
                "v3.position_ledger",
                False,
                f"{detail} has no matching position row",
            )
            return None
        record = matches[offset]
        position_key_offsets[key] += 1
        index = record["index"]
        errors.require(
            "v3.position_ledger",
            index == position_order_cursor,
            f"positions[{index}] is out of replay order",
        )
        position_order_cursor += 1
        consumed_positions.add(index)
        return record

    lots: dict[tuple[str, str], list[dict[str, int]]] = defaultdict(list)

    def lot_quantity(key: tuple[str, str]) -> int:
        return sum(lot["quantity"] for lot in lots[key])

    def signed_quantity(key: tuple[str, str]) -> int:
        quantity = lot_quantity(key)
        return -quantity if key[1] == "research_short" else quantity

    def eligible_quantity(key: tuple[str, str], session_seq: int) -> int:
        quantity = sum(
            lot["quantity"]
            for lot in lots[key]
            if lot["acquired_session_seq"] < session_seq
        )
        return -quantity if key[1] == "research_short" else quantity

    def consume_lots(
        key: tuple[str, str], quantity: int, session_seq: int, detail: str
    ) -> tuple[int, int, int]:
        remaining = quantity
        basis = 0
        margin = 0
        proceeds = 0
        for lot in lots[key]:
            if remaining == 0:
                break
            if lot["acquired_session_seq"] >= session_seq:
                continue
            original_quantity = lot["quantity"]
            consumed = min(original_quantity, remaining)
            allocations: dict[str, int] = {}
            for field in ("basis", "margin", "proceeds"):
                original = lot[field]
                allocations[field] = (
                    original
                    if consumed == original_quantity
                    else original * consumed // original_quantity
                )
                lot[field] -= allocations[field]
            lot["quantity"] -= consumed
            remaining -= consumed
            basis += allocations["basis"]
            margin += allocations["margin"]
            proceeds += allocations["proceeds"]
        lots[key] = [lot for lot in lots[key] if lot["quantity"] != 0]
        errors.require(
            "v3.position_ledger",
            remaining == 0,
            f"{detail} closes more T+1 eligible quantity than the replay owns",
        )
        return basis, margin, proceeds

    fills_by_session: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for fill in fills:
        session = fill["session_value"]
        if session is not None:
            fills_by_session[session].append(fill)
    corporate_by_session: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for action in corporate:
        session = action["session_value"]
        if session is not None:
            corporate_by_session[session].append(action)
    equity_by_session: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for point in equity:
        session = point["session_value"]
        if session is not None:
            equity_by_session[session].append(point)

    available_cash = starting_cash
    frozen_margin = 0
    isolated_proceeds = 0
    closed_trade_count = 0
    dividend_per_share: dict[str, int] = {}
    split_ratios: dict[str, tuple[int, int]] = {}

    def reconcile_corporate(action: dict[str, Any]) -> None:
        nonlocal available_cash, frozen_margin, isolated_proceeds
        nonlocal closed_trade_count
        index = action["index"]
        detail = f"corporate_action_ledger[{index}]"
        action_id = action.get("action_id")
        symbol = action.get("symbol")
        book = action.get("book")
        session = action["session_value"]
        action_type = action.get("action_type")
        errors.require(
            "v3.corporate_action_ledger",
            isinstance(action_id, str)
            and bool(action_id)
            and isinstance(symbol, str)
            and bool(symbol),
            f"{detail} has an invalid identity",
        )
        errors.require(
            "v3.corporate_action_ledger",
            book in {"cash_long", "research_short"},
            f"{detail}.book is invalid",
        )
        errors.require(
            "v3.corporate_action_ledger",
            action_type
            in {"cash_dividend", "split", "reverse_split", "delist_settlement"},
            f"{detail}.action_type is invalid",
        )
        if not isinstance(symbol, str) or not isinstance(book, str) or session is None:
            return
        lot_key = (symbol, book)
        quantity_before = action["quantity_before_value"]
        quantity_after = action["quantity_after_value"]
        owned_before = lot_quantity(lot_key)
        errors.require(
            "v3.corporate_action_ledger",
            quantity_before is not None
            and quantity_before > 0
            and quantity_before == owned_before,
            f"{detail}.quantity_before does not match the replayed {lot_key} book",
        )
        errors.require(
            "v3.corporate_action_ledger",
            quantity_after is not None and quantity_after >= 0,
            f"{detail}.quantity_after is negative",
        )

        synthetic_intent = f"corporate:{action_id}"
        event_key = (synthetic_intent, symbol, book, session)
        cash_record = (
            take_cash(event_key, detail)
            if action_type in {"cash_dividend", "delist_settlement"}
            else None
        )
        cash_delta_expected = 0
        margin_delta_expected = 0
        proceeds_delta_expected = 0
        realized_expected = 0
        if action_type == "cash_dividend":
            errors.require(
                "v3.corporate_action_ledger",
                quantity_after == quantity_before,
                f"{detail} changes quantity for a cash dividend",
            )
            if cash_record is not None:
                cash_delta_expected = (
                    cash_record["realized_pnl_delta_atoms_value"] or 0
                )
                errors.require(
                    "v3.cash_ledger",
                    cash_record["notional_delta_atoms_value"] == 0,
                    f"cash_ledger[{cash_record['index']}] dividend notional is not zero",
                )
            realized_expected = cash_delta_expected
            errors.require(
                "v3.corporate_action_ledger",
                (book == "cash_long" and cash_delta_expected > 0)
                or (book == "research_short" and cash_delta_expected < 0),
                f"{detail} has the wrong dividend cash sign",
            )
            if quantity_before:
                errors.require(
                    "v3.corporate_action_ledger",
                    cash_delta_expected % quantity_before == 0,
                    f"{detail} dividend is not integral per share",
                )
                per_share = abs(cash_delta_expected) // quantity_before
                prior = dividend_per_share.setdefault(str(action_id), per_share)
                errors.require(
                    "v3.corporate_action_ledger",
                    prior == per_share,
                    f"{detail} disagrees on per-share dividend across books",
                )
        elif action_type in {"split", "reverse_split"}:
            errors.require(
                "v3.corporate_action_ledger",
                quantity_before is not None
                and quantity_after is not None
                and (
                    (action_type == "split" and quantity_after > quantity_before)
                    or (
                        action_type == "reverse_split"
                        and 0 < quantity_after < quantity_before
                    )
                ),
                f"{detail} has an invalid split direction",
            )
            for field in (
                "available_cash_delta_atoms_value",
                "frozen_margin_delta_atoms_value",
                "isolated_proceeds_delta_atoms_value",
                "realized_pnl_delta_atoms_value",
            ):
                errors.require(
                    "v3.corporate_action_ledger",
                    action[field] == 0,
                    f"{detail} has a non-zero financial split delta",
                )
            if quantity_before and quantity_after is not None:
                ratio = (quantity_after, quantity_before)
                prior_ratio = split_ratios.setdefault(str(action_id), ratio)
                errors.require(
                    "v3.corporate_action_ledger",
                    prior_ratio[0] * ratio[1] == ratio[0] * prior_ratio[1],
                    f"{detail} disagrees on split ratio across books",
                )
        elif action_type == "delist_settlement":
            errors.require(
                "v3.corporate_action_ledger",
                quantity_after == 0,
                f"{detail} does not close the delisted book",
            )
            if cash_record is not None:
                notional_delta = cash_record["notional_delta_atoms_value"]
                if book == "cash_long":
                    settlement = notional_delta if notional_delta is not None else 0
                    basis = sum(lot["basis"] for lot in lots[lot_key])
                    cash_delta_expected = settlement
                    realized_expected = settlement - basis
                else:
                    settlement = -notional_delta if notional_delta is not None else 0
                    released_margin = sum(lot["margin"] for lot in lots[lot_key])
                    released_proceeds = sum(
                        lot["proceeds"] for lot in lots[lot_key]
                    )
                    margin_delta_expected = -released_margin
                    proceeds_delta_expected = -released_proceeds
                    cash_delta_expected = (
                        released_margin + released_proceeds - settlement
                    )
                    realized_expected = released_proceeds - settlement
            if owned_before > 0:
                closed_trade_count += 1

        action_cash_delta = action["available_cash_delta_atoms_value"]
        action_margin_delta = action["frozen_margin_delta_atoms_value"]
        action_proceeds_delta = action["isolated_proceeds_delta_atoms_value"]
        action_realized = action["realized_pnl_delta_atoms_value"]
        errors.require(
            "v3.corporate_action_ledger",
            action_cash_delta == cash_delta_expected,
            f"{detail}.available_cash_delta_atoms does not replay",
        )
        errors.require(
            "v3.corporate_action_ledger",
            action_margin_delta == margin_delta_expected,
            f"{detail}.frozen_margin_delta_atoms does not replay",
        )
        errors.require(
            "v3.corporate_action_ledger",
            action_proceeds_delta == proceeds_delta_expected,
            f"{detail}.isolated_proceeds_delta_atoms does not replay",
        )
        errors.require(
            "v3.corporate_action_ledger",
            action_realized == realized_expected,
            f"{detail}.realized_pnl_delta_atoms does not replay",
        )

        available_cash += cash_delta_expected
        frozen_margin += margin_delta_expected
        isolated_proceeds += proceeds_delta_expected
        errors.require(
            "v3.corporate_action_ledger",
            frozen_margin >= 0 and isolated_proceeds >= 0,
            f"{detail} makes an isolated short pool negative",
        )
        errors.require(
            "v3.corporate_action_ledger",
            action["resulting_available_cash_atoms_value"] == available_cash,
            f"{detail}.resulting_available_cash_atoms breaks the cash chain",
        )
        errors.require(
            "v3.corporate_action_ledger",
            action["resulting_frozen_margin_atoms_value"] == frozen_margin,
            f"{detail}.resulting_frozen_margin_atoms breaks the pool chain",
        )
        errors.require(
            "v3.corporate_action_ledger",
            action["resulting_isolated_proceeds_atoms_value"] == isolated_proceeds,
            f"{detail}.resulting_isolated_proceeds_atoms breaks the pool chain",
        )

        if cash_record is not None:
            cash_index = cash_record["index"]
            errors.require(
                "v3.cash_ledger",
                cash_record["fee_delta_atoms_value"] == 0
                and cash_record["stamp_duty_delta_atoms_value"] == 0,
                f"cash_ledger[{cash_index}] corporate costs are non-zero",
            )
            errors.require(
                "v3.cash_ledger",
                cash_record["realized_pnl_delta_atoms_value"] == realized_expected,
                f"cash_ledger[{cash_index}] corporate realized P&L does not replay",
            )
            errors.require(
                "v3.cash_ledger",
                cash_record["frozen_margin_delta_atoms_value"]
                == margin_delta_expected
                and cash_record["isolated_proceeds_delta_atoms_value"]
                == proceeds_delta_expected,
                f"cash_ledger[{cash_index}] corporate pool deltas do not replay",
            )
            errors.require(
                "v3.cash_ledger",
                cash_record["resulting_available_cash_atoms_value"] == available_cash,
                f"cash_ledger[{cash_index}] breaks the resulting cash chain",
            )

        if action_type in {"split", "reverse_split"}:
            if quantity_before and quantity_after is not None:
                for lot in lots[lot_key]:
                    adjusted = lot["quantity"] * quantity_after
                    errors.require(
                        "v3.position_ledger",
                        adjusted % quantity_before == 0,
                        f"{detail} creates a fractional replay lot",
                    )
                    lot["quantity"] = adjusted // quantity_before
        elif action_type == "delist_settlement":
            lots[lot_key] = []

        errors.require(
            "v3.position_ledger",
            quantity_after is not None and lot_quantity(lot_key) == quantity_after,
            f"{detail}.quantity_after does not match replayed lots",
        )
        if action_type in {"split", "reverse_split", "delist_settlement"}:
            position = take_position(event_key, detail)
            if position is not None:
                expected_signed = signed_quantity(lot_key)
                expected_eligible = eligible_quantity(lot_key, session)
                errors.require(
                    "v3.position_ledger",
                    position["signed_value"] == expected_signed,
                    f"positions[{position['index']}].signed_quantity does not replay",
                )
                errors.require(
                    "v3.position_ledger",
                    position["eligible_value"] == expected_eligible,
                    f"positions[{position['index']}].eligible_quantity does not replay",
                )

    last_volume_after: dict[tuple[int, str], int] = {}

    def reconcile_fill(fill: dict[str, Any]) -> None:
        nonlocal available_cash, frozen_margin, isolated_proceeds
        nonlocal closed_trade_count
        index = fill["index"]
        detail = f"fills[{index}]"
        intent_id = fill.get("intent_id")
        symbol = fill.get("symbol")
        book = fill.get("book")
        side = fill.get("side")
        effect = fill.get("position_effect")
        session = fill["session_value"]
        quantity = fill["quantity_value"]
        notional = fill["notional_atoms_value"]
        fee = fill["fee_atoms_value"]
        stamp = fill["stamp_duty_atoms_value"]
        if (
            not isinstance(intent_id, str)
            or not isinstance(symbol, str)
            or not isinstance(book, str)
            or session is None
            or quantity is None
            or quantity <= 0
            or notional is None
            or fee is None
            or stamp is None
        ):
            return
        event_key = (intent_id, symbol, book, session)
        lot_key = (symbol, book)
        cash_record = take_cash(event_key, detail)
        if cash_record is None:
            return
        cash_index = cash_record["index"]
        errors.require(
            "v3.cash_ledger",
            cash_record["fee_delta_atoms_value"] == -fee,
            f"cash_ledger[{cash_index}].fee_delta_atoms != -fill fee",
        )
        errors.require(
            "v3.cash_ledger",
            cash_record["stamp_duty_delta_atoms_value"] == -stamp,
            f"cash_ledger[{cash_index}].stamp_duty_delta_atoms != -fill stamp duty",
        )
        errors.require(
            "v3.fill_accounting",
            side == "sell" or stamp == 0,
            f"{detail} charges stamp duty on a buy",
        )
        volume_key = (session, symbol)
        prior_volume = last_volume_after.get(volume_key)
        if prior_volume is not None:
            errors.require(
                "v3.fill_accounting",
                fill["volume_before_value"] == prior_volume,
                f"{detail}.volume_before breaks the per-bar volume chain",
            )
        if fill["volume_after_value"] is not None:
            last_volume_after[volume_key] = fill["volume_after_value"]

        basis_released = 0
        margin_released = 0
        proceeds_released = 0
        if effect == "close":
            basis_released, margin_released, proceeds_released = consume_lots(
                lot_key, quantity, session, detail
            )

        expected_notional_delta = (
            notional
            if (book, side, effect) == ("cash_long", "sell", "close")
            else -notional
        )
        expected_margin_delta = 0
        expected_proceeds_delta = 0
        expected_realized = 0
        if (book, side, effect) == ("cash_long", "buy", "open"):
            pass
        elif (book, side, effect) == ("cash_long", "sell", "close"):
            expected_realized = notional - basis_released
        elif (book, side, effect) == (
            "research_short",
            "sell",
            "open",
        ):
            expected_margin_delta = (
                cash_record["frozen_margin_delta_atoms_value"] or 0
            )
            expected_proceeds_delta = notional
            errors.require(
                "v3.cash_ledger",
                expected_margin_delta >= 0,
                f"cash_ledger[{cash_index}] has negative opened short margin",
            )
        elif (book, side, effect) == (
            "research_short",
            "buy",
            "close",
        ):
            expected_margin_delta = -margin_released
            expected_proceeds_delta = -proceeds_released
            expected_realized = proceeds_released - notional

        errors.require(
            "v3.cash_ledger",
            cash_record["notional_delta_atoms_value"] == expected_notional_delta,
            f"cash_ledger[{cash_index}].notional_delta_atoms does not replay",
        )
        errors.require(
            "v3.cash_ledger",
            cash_record["realized_pnl_delta_atoms_value"] == expected_realized,
            f"cash_ledger[{cash_index}].realized_pnl_delta_atoms does not replay",
        )
        errors.require(
            "v3.cash_ledger",
            cash_record["frozen_margin_delta_atoms_value"]
            == expected_margin_delta,
            f"cash_ledger[{cash_index}].frozen_margin_delta_atoms does not replay",
        )
        errors.require(
            "v3.cash_ledger",
            cash_record["isolated_proceeds_delta_atoms_value"]
            == expected_proceeds_delta,
            f"cash_ledger[{cash_index}].isolated_proceeds_delta_atoms does not replay",
        )
        errors.require(
            "v3.fill_accounting",
            fill["frozen_margin_delta_atoms_value"] == expected_margin_delta,
            f"{detail}.frozen_margin_delta_atoms does not replay",
        )
        errors.require(
            "v3.fill_accounting",
            fill["isolated_proceeds_delta_atoms_value"]
            == expected_proceeds_delta,
            f"{detail}.isolated_proceeds_delta_atoms does not replay",
        )

        cash_delta = expected_notional_delta - fee - stamp
        if (book, side, effect) == (
            "research_short",
            "buy",
            "close",
        ):
            cash_delta -= expected_margin_delta + expected_proceeds_delta
        available_cash += cash_delta
        frozen_margin += expected_margin_delta
        isolated_proceeds += expected_proceeds_delta
        errors.require(
            "v3.cash_ledger",
            frozen_margin >= 0 and isolated_proceeds >= 0,
            f"cash_ledger[{cash_index}] makes a short pool negative",
        )
        errors.require(
            "v3.cash_ledger",
            cash_record["resulting_available_cash_atoms_value"] == available_cash,
            f"cash_ledger[{cash_index}].resulting_available_cash_atoms breaks the chain",
        )

        if effect == "open":
            lots[lot_key].append(
                {
                    "quantity": quantity,
                    "acquired_session_seq": session,
                    "basis": notional if book == "cash_long" else 0,
                    "margin": expected_margin_delta,
                    "proceeds": expected_proceeds_delta,
                }
            )
        if effect == "close" and signed_quantity(lot_key) == 0:
            closed_trade_count += 1

        position = take_position(event_key, detail)
        if position is not None:
            expected_signed = signed_quantity(lot_key)
            expected_eligible = eligible_quantity(lot_key, session)
            errors.require(
                "v3.position_ledger",
                position["signed_value"] == expected_signed,
                f"positions[{position['index']}].signed_quantity does not replay",
            )
            errors.require(
                "v3.position_ledger",
                position["eligible_value"] == expected_eligible,
                f"positions[{position['index']}].eligible_quantity does not replay",
            )

    all_sessions = sorted(
        set(fills_by_session) | set(corporate_by_session) | set(equity_by_session)
    )
    for session in all_sessions:
        for action in corporate_by_session.get(session, []):
            reconcile_corporate(action)
        for fill in fills_by_session.get(session, []):
            reconcile_fill(fill)

        expected_margin = sum(
            lot["margin"]
            for key, book_lots in lots.items()
            if key[1] == "research_short"
            for lot in book_lots
        )
        expected_proceeds = sum(
            lot["proceeds"]
            for key, book_lots in lots.items()
            if key[1] == "research_short"
            for lot in book_lots
        )
        errors.require(
            "v3.cash_ledger",
            frozen_margin == expected_margin
            and isolated_proceeds == expected_proceeds
            and frozen_margin >= 0
            and isolated_proceeds >= 0,
            f"session {session} isolated short pools do not match open short lots",
        )

        points = equity_by_session.get(session, [])
        errors.require(
            "v3.equity_curve",
            len(points) == 1,
            f"session {session} has {len(points)} equity points",
        )
        if not points:
            continue
        point = points[0]
        point_index = point["index"]
        point_cash = point["available_cash_atoms_value"]
        long_value = point["long_market_value_atoms_value"]
        short_liability = point["short_liability_atoms_value"]
        gross_value = point["gross_market_value_atoms_value"]
        net_value = point["net_market_value_atoms_value"]
        legacy_value = point["market_value_atoms_value"]
        point_equity = point["equity_atoms_value"]
        point_margin = point["frozen_margin_atoms_value"]
        point_proceeds = point["isolated_short_proceeds_atoms_value"]
        errors.require(
            "v3.equity_curve",
            point_cash == available_cash,
            f"equity_curve[{point_index}].available_cash_atoms does not match ledger replay",
        )
        errors.require(
            "v3.equity_curve",
            point_margin == frozen_margin,
            f"equity_curve[{point_index}].frozen_margin_atoms does not match ledger replay",
        )
        errors.require(
            "v3.equity_curve",
            point_proceeds == isolated_proceeds,
            f"equity_curve[{point_index}].isolated_short_proceeds_atoms does not match ledger replay",
        )
        errors.require(
            "v3.equity_curve",
            long_value is not None
            and short_liability is not None
            and long_value >= 0
            and short_liability >= 0,
            f"equity_curve[{point_index}] has a negative long value or short liability",
        )
        errors.require(
            "v3.equity_curve",
            None not in (long_value, short_liability, gross_value)
            and gross_value == long_value + short_liability,
            f"equity_curve[{point_index}].gross_market_value_atoms does not equal long + short",
        )
        errors.require(
            "v3.equity_curve",
            None not in (long_value, short_liability, net_value)
            and net_value == long_value - short_liability,
            f"equity_curve[{point_index}].net_market_value_atoms does not equal long - short",
        )
        errors.require(
            "v3.equity_curve",
            legacy_value == net_value,
            f"equity_curve[{point_index}].market_value_atoms does not equal net market value",
        )
        errors.require(
            "v3.equity_curve",
            None
            not in (
                point_cash,
                net_value,
                point_margin,
                point_proceeds,
                point_equity,
            )
            and point_equity
            == point_cash + net_value + point_margin + point_proceeds,
            f"equity_curve[{point_index}].equity_atoms breaks the v3 balance-sheet identity",
        )
        has_long = any(
            key[1] == "cash_long" and lot_quantity(key) != 0 for key in lots
        )
        has_short = any(
            key[1] == "research_short" and lot_quantity(key) != 0 for key in lots
        )
        errors.require(
            "v3.equity_curve",
            has_long or long_value == 0,
            f"equity_curve[{point_index}] has long value without a long position",
        )
        errors.require(
            "v3.equity_curve",
            has_short or short_liability == 0,
            f"equity_curve[{point_index}] has short liability without a short position",
        )

    errors.require(
        "v3.cash_ledger",
        len(consumed_cash) == len(cash_records),
        f"{len(cash_records) - len(consumed_cash)} cash row(s) are not backed by fills/actions",
    )
    errors.require(
        "v3.position_ledger",
        len(consumed_positions) == len(positions),
        f"{len(positions) - len(consumed_positions)} position row(s) are not backed by fills/actions",
    )

    peak_equity = starting_cash
    max_drawdown = 0
    max_drawdown_rate = 0
    errors.require(
        "v3.drawdown_curve",
        len(drawdown) == len(equity),
        "drawdown_curve length does not equal equity_curve length",
    )
    for index, point in enumerate(equity):
        if index >= len(drawdown):
            break
        draw = drawdown[index]
        point_equity = point["equity_atoms_value"]
        if point_equity is None:
            continue
        peak_equity = max(peak_equity, point_equity)
        expected_drawdown = point_equity - peak_equity
        expected_rate = _trunc_div(
            expected_drawdown * RATE_SCALE, peak_equity
        )
        max_drawdown = min(max_drawdown, expected_drawdown)
        max_drawdown_rate = min(max_drawdown_rate, expected_rate)
        errors.require(
            "v3.drawdown_curve",
            draw["session_value"] == point["session_value"],
            f"drawdown_curve[{index}].session_seq does not match equity_curve",
        )
        errors.require(
            "v3.drawdown_curve",
            draw["equity_atoms_value"] == point_equity,
            f"drawdown_curve[{index}].equity_atoms does not match equity_curve",
        )
        errors.require(
            "v3.drawdown_curve",
            draw["peak_equity_atoms_value"] == peak_equity,
            f"drawdown_curve[{index}].peak_equity_atoms does not replay",
        )
        errors.require(
            "v3.drawdown_curve",
            draw["drawdown_atoms_value"] == expected_drawdown,
            f"drawdown_curve[{index}].drawdown_atoms does not replay",
        )
        errors.require(
            "v3.drawdown_curve",
            draw["drawdown_rate_atoms_value"] == expected_rate,
            f"drawdown_curve[{index}].drawdown_rate_atoms does not replay",
        )

    ending_equity = starting_cash
    gross_exposure = 0
    net_exposure = 0
    if equity:
        final_point = equity[-1]
        if final_point["equity_atoms_value"] is not None:
            ending_equity = final_point["equity_atoms_value"]
        if final_point["gross_market_value_atoms_value"] is not None:
            gross_exposure = final_point["gross_market_value_atoms_value"]
        if final_point["net_market_value_atoms_value"] is not None:
            net_exposure = final_point["net_market_value_atoms_value"]
    net_pnl = ending_equity - starting_cash
    total_return_rate = _trunc_div(net_pnl * RATE_SCALE, starting_cash)
    total_fees = sum(fill["fee_atoms_value"] or 0 for fill in fills)
    total_stamp_duty = sum(
        fill["stamp_duty_atoms_value"] or 0 for fill in fills
    )
    total_slippage = sum(
        fill["slippage_atoms_value"] or 0 for fill in fills
    )
    open_position_count = sum(lot_quantity(key) != 0 for key in lots)
    summary = {
        "starting_equity_atoms": _atom(starting_cash),
        "ending_equity_atoms": _atom(ending_equity),
        "net_pnl_atoms": _atom(net_pnl),
        "total_return_rate_atoms": _atom(total_return_rate),
        "max_drawdown_atoms": _atom(max_drawdown),
        "max_drawdown_rate_atoms": _atom(max_drawdown_rate),
        "gross_exposure_atoms": _atom(gross_exposure),
        "net_exposure_atoms": _atom(net_exposure),
        "total_fees_atoms": _atom(total_fees),
        "total_stamp_duty_atoms": _atom(total_stamp_duty),
        "total_funding_atoms": "0",
        "total_slippage_atoms": _atom(total_slippage),
        "order_count": len(orders),
        "fill_count": len(fills),
        "closed_trade_count": closed_trade_count,
        "open_position_count": open_position_count,
    }

    checks = [
        errors.check(group)
        for group in (
            "v3.required_fields",
            "v3.fill_accounting",
            "v3.cash_ledger",
            "v3.position_ledger",
            "v3.corporate_action_ledger",
            "v3.equity_curve",
            "v3.drawdown_curve",
        )
    ]
    metric_summary_fields = {
        "starting_equity_atoms": "starting_equity_atoms",
        "ending_equity_atoms": "ending_equity_atoms",
        "net_pnl_atoms": "net_pnl_atoms",
        "total_return_rate_atoms": "total_return_rate_atoms",
        "max_drawdown_atoms": "max_drawdown_atoms",
        "max_drawdown_rate_atoms": "max_drawdown_rate_atoms",
        "total_fees_atoms": "total_fees_atoms",
        "total_stamp_duty_atoms": "total_stamp_duty_atoms",
        "total_slippage_atoms": "total_slippage_atoms",
    }
    for metric_field, summary_field in metric_summary_fields.items():
        metric_value = metric_atoms[metric_field]
        expected = (
            "<missing-or-invalid>" if metric_value is None else _atom(metric_value)
        )
        actual = summary[summary_field]
        checks.append(
            {
                "field": f"metrics.{metric_field}",
                "expected": expected,
                "actual": actual,
                "passed": metric_value is not None and expected == actual,
            }
        )
    for metric_field in _V3_METRIC_COUNT_FIELDS:
        metric_value = metric_counts[metric_field]
        actual = summary[metric_field]
        checks.append(
            {
                "field": f"metrics.{metric_field}",
                "expected": _v3_reconciliation_value(metric_value),
                "actual": actual,
                "passed": metric_value is not None and metric_value == actual,
            }
        )
    cost_summary_fields = {
        "commission_atoms": "total_fees_atoms",
        "stamp_duty_atoms": "total_stamp_duty_atoms",
        "slippage_atoms": "total_slippage_atoms",
    }
    for cost_field, summary_field in cost_summary_fields.items():
        cost_value = cost_atoms[cost_field]
        expected = "<missing-or-invalid>" if cost_value is None else _atom(cost_value)
        actual = summary[summary_field]
        checks.append(
            {
                "field": f"costs.{cost_field}",
                "expected": expected,
                "actual": actual,
                "passed": cost_value is not None
                and cost_value >= 0
                and expected == actual,
            }
        )
    reconciliation = {
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }
    return summary, reconciliation


def validate_v3_engine_result(result: object) -> dict[str, Any]:
    """Run the independent v3 ledger replay as a durable execution gate.

    The report path intentionally exposes reconciliation details for users.  The
    worker needs the same calculation before publishing a succeeded Run, but it
    must also fail closed when a malformed extension payload would otherwise
    raise while being inspected.
    """

    if not isinstance(result, dict):
        return {
            "passed": False,
            "checks": [
                {
                    "field": "v3.required_fields",
                    "expected": "object",
                    "actual": type(result).__name__,
                    "passed": False,
                }
            ],
        }
    try:
        _summary, reconciliation = _v3_reference_and_reconciliation(result)
    except (IndexError, KeyError, TypeError, ValueError, OverflowError) as error:
        return {
            "passed": False,
            "checks": [
                {
                    "field": "v3.replay_exception",
                    "expected": "replayable result",
                    "actual": str(error),
                    "passed": False,
                }
            ],
        }
    return reconciliation


def _reference_summary(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result["metrics"]
    curve = result.get("equity_curve", [])
    # v1/v2 called executions ``trades``; the additive A-share v3 contract
    # calls them ``fills`` so that an order can have multiple partial fills.
    trades = result.get("trades") or result.get("fills", [])
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
    close_intent_ids = {
        trade["intent_id"]
        for trade in trades
        if trade["position_effect"] == "close"
    }
    closed_trade_count = sum(
        position["intent_id"] in close_intent_ids
        and int(position["signed_quantity"]) == 0
        for position in positions
    )

    last_positions: dict[tuple[str, str], int] = {}
    for position in positions:
        symbol = position.get("symbol", "__single_account__")
        book = position.get("book", "__account__")
        last_positions[(symbol, book)] = int(position["signed_quantity"])
    open_position_count = sum(quantity != 0 for quantity in last_positions.values())

    if curve:
        final_point = curve[-1]
        if result["schema_version"] == 2:
            net_exposure = int(final_point["market_value_atoms"])
            gross_exposure = net_exposure
        elif result["schema_version"] == 3:
            # v3 publishes the signed marked market value for the dual books
            # when available.  Fall back to equity minus public cash for early
            # v3 outputs, keeping report generation deterministic.
            if "net_market_value_atoms" in final_point:
                net_exposure = int(final_point["net_market_value_atoms"])
                gross_exposure = abs(int(final_point.get("gross_market_value_atoms", net_exposure)))
            elif "available_cash_atoms" in final_point:
                net_exposure = int(final_point["equity_atoms"]) - int(final_point["available_cash_atoms"])
                gross_exposure = abs(net_exposure)
            else:
                net_exposure = 0
                gross_exposure = 0
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
            "formula": "count close fills whose resulting signed position is zero",
            "inputs": [
                "trades[].intent_id",
                "trades[].position_effect",
                "positions[].intent_id",
                "positions[].signed_quantity",
            ],
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
        # A-share v3 has no funding leg.  Treat the omitted field as the
        # contract's additive zero rather than making report rendering fail
        # for an otherwise valid dual-book result.
        metric_value = metrics.get(field, 0)
        expected = (
            int(metric_value)
            if field in {"fill_count", "closed_trade_count", "open_position_count"}
            else _atom(metric_value)
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
        # Funding is not part of the v3 A-share cost model.  Its absence is
        # equivalent to an explicit zero and keeps the report oracle
        # additive across the legacy and v3 result shapes.
        expected = _atom(costs.get(cost_field, 0))
        actual = summary[summary_field]
        checks.append({"field": f"costs.{cost_field}", "expected": expected, "actual": actual, "passed": expected == actual})
    return {"passed": all(check["passed"] for check in checks), "checks": checks}


def build_run_report(run_detail: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical M9 report from one succeeded Run read model."""

    run = run_detail["run"]
    result = run_detail["engine_result"]
    spec = run_detail.get("run_spec") or run_detail["manifest"]["run_spec"]
    report_period = _period(result)
    if result.get("schema_version") == 3:
        summary, reconciliation = _v3_reference_and_reconciliation(result)
    else:
        summary = _reference_summary(result)
        reconciliation = _reconciliation(result, summary)
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
        "reconciliation": reconciliation,
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
    "validate_v3_engine_result",
]
