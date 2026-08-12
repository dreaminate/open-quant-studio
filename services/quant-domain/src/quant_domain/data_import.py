from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import BinaryIO
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pa_parquet


MAX_DATA_ROWS = 250_000
PRICE_SCALE = 10_000
RATE_SCALE = 1_000_000
_SOURCE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "open-quant-studio/data-import/v1")
_MAPPING_ALIASES = {
    "timestamp": ("timestamp", "date", "datetime"),
    "symbol": ("symbol", "ticker"),
    "open": ("open",),
    "high": ("high",),
    "low": ("low",),
    "close": ("close",),
    "volume": ("volume", "vol"),
}
_REQUIRED_MAPPING_FIELDS = tuple(_MAPPING_ALIASES)


class DataImportValidationError(ValueError):
    def __init__(self, details: list[dict[str, object]]) -> None:
        super().__init__("data import is invalid")
        self.details = details


@dataclass(frozen=True)
class DataSnapshotMaterial:
    symbol: str | None
    symbols: tuple[str, ...]
    session_count: int
    schema_version: int
    sample_start: str
    sample_end: str
    row_count: int
    normalized_body: bytes
    market_input_body: bytes

    @property
    def normalized_sha256(self) -> str:
        return hashlib.sha256(self.normalized_body).hexdigest()

    @property
    def market_input_sha256(self) -> str:
        return hashlib.sha256(self.market_input_body).hexdigest()


def preview_data_import(
    body: bytes | BinaryIO,
    file_name: str,
    source_format: str,
) -> dict[str, object]:
    source_body = _body_bytes(body)
    columns, rows = read_data_import(source_body, source_format)
    mapping = suggest_mapping(columns)
    source_sha256 = hashlib.sha256(source_body).hexdigest()
    source_id = _deterministic_uuid(f"source:{source_sha256}")
    return {
        "source": {
            "artifact_id": source_id,
            "sha256": source_sha256,
            "media_type": _source_media_type(source_format),
            "byte_size": len(source_body),
            "storage_uri": f"cas://sha256/{source_sha256}",
            "producing_revision_id": None,
            "producing_run_id": None,
            "provenance": {
                "origin_kind": "user_upload",
                "source_ref": _deterministic_uuid(f"source-ref:{source_sha256}"),
            },
        },
        "source_format": source_format,
        "file_name": file_name,
        "columns": columns,
        "suggested_mapping": mapping,
        "preview_rows": [
            {column: _string_value(row.get(column)) for column in columns}
            for row in rows[:20]
        ],
        "total_rows": len(rows),
    }


def read_data_import(
    body: bytes | BinaryIO,
    source_format: str,
) -> tuple[list[str], list[dict[str, object]]]:
    source_body = _body_bytes(body)
    try:
        if source_format == "csv":
            table = pa_csv.read_csv(
                pa.BufferReader(source_body),
                convert_options=pa_csv.ConvertOptions(default_column_type=pa.string()),
            )
        elif source_format == "parquet":
            table = pa_parquet.read_table(pa.BufferReader(source_body))
        else:
            raise DataImportValidationError(
                [{"row_number": 1, "field": "source_format", "message": "must be csv or parquet"}]
            )
    except pa.ArrowException as error:
        raise DataImportValidationError(
            [{"row_number": 1, "field": "source", "message": str(error)}]
        ) from error
    columns = [str(column) for column in table.column_names]
    rows = [dict(row) for row in table.to_pylist()]
    if not rows:
        raise DataImportValidationError(
            [{"row_number": 1, "field": "source", "message": "must contain at least one data row"}]
        )
    if len(rows) > MAX_DATA_ROWS:
        raise DataImportValidationError(
            [
                {
                    "row_number": 1,
                    "field": "source",
                    "message": f"must contain at most {MAX_DATA_ROWS} data rows",
                }
            ]
        )
    return columns, rows


def suggest_mapping(columns: list[str]) -> dict[str, str]:
    by_lower = {column.lower(): column for column in columns}
    mapping = {
        field: next(
            (by_lower[alias] for alias in aliases if alias in by_lower), None
        )
        for field, aliases in _MAPPING_ALIASES.items()
    }
    errors = [
        {
            "row_number": 1,
            "field": field,
            "message": "required mapping is missing",
        }
        for field in _REQUIRED_MAPPING_FIELDS
        if mapping[field] is None
    ]
    if errors:
        raise DataImportValidationError(errors)
    return {field: mapping[field] for field in _REQUIRED_MAPPING_FIELDS}


def build_data_snapshot(
    body: bytes | BinaryIO,
    *,
    source_format: str,
    mapping: dict[str, str],
    market: str,
    timezone: str,
    price_basis: str,
    cutoff: str,
) -> DataSnapshotMaterial:
    columns, rows = read_data_import(body, source_format)
    _validate_mapping(columns, mapping)
    zone = _timezone(timezone)
    normalized_rows = _normalize_rows(rows, mapping, zone)
    symbols = tuple(sorted({row["symbol"] for row in normalized_rows}))
    if len(symbols) > 1:
        if market != "a_share_daily":
            raise DataImportValidationError(
                [
                    {
                        "row_number": 1,
                        "field": "symbol",
                        "message": "multi-symbol snapshots require the A-share daily market",
                    }
                ]
            )
        return _build_portfolio_data_snapshot(
            normalized_rows,
            symbols=symbols,
            market=market,
            timezone=timezone,
            price_basis=price_basis,
            cutoff=cutoff,
        )

    symbol = symbols[0]
    normalized_snapshot = {
        "schema_version": 1,
        "market": market,
        "symbol": symbol,
        "timezone": timezone,
        "price_basis": price_basis,
        "cutoff": cutoff,
        "price_scale": PRICE_SCALE,
        "cash_scale": PRICE_SCALE,
        "volume_scale": PRICE_SCALE,
        "bars": normalized_rows,
    }
    normalized_body = _canonical_json_bytes(normalized_snapshot)
    market_input = {
        "schema_version": 1,
        "account": _market_account(market, symbol),
        "bars": [
            {
                "session_seq": index,
                "timestamp": row["timestamp"],
                "open_atoms": row["open_atoms"],
                "high_atoms": row["high_atoms"],
                "low_atoms": row["low_atoms"],
                "close_atoms": row["close_atoms"],
                "can_buy": True,
                "can_sell": True,
            }
            for index, row in enumerate(normalized_rows, start=1)
        ],
        "funding_events": [],
        "intents": [],
    }
    return DataSnapshotMaterial(
        symbol=symbol,
        symbols=symbols,
        session_count=len(normalized_rows),
        schema_version=1,
        sample_start=normalized_rows[0]["timestamp"],
        sample_end=normalized_rows[-1]["timestamp"],
        row_count=len(normalized_rows),
        normalized_body=normalized_body,
        market_input_body=_canonical_json_bytes(market_input),
    )


def _build_portfolio_data_snapshot(
    normalized_rows: list[dict[str, str]],
    *,
    symbols: tuple[str, ...],
    market: str,
    timezone: str,
    price_basis: str,
    cutoff: str,
) -> DataSnapshotMaterial:
    rows = sorted(normalized_rows, key=lambda row: (row["timestamp"], row["symbol"]))
    sessions: list[dict[str, object]] = []
    for row in rows:
        if not sessions or sessions[-1]["timestamp"] != row["timestamp"]:
            sessions.append({"timestamp": row["timestamp"], "bars": []})
        bars = sessions[-1]["bars"]
        assert isinstance(bars, list)
        bars.append({key: value for key, value in row.items() if key != "timestamp"})
    expected_symbols = list(symbols)
    for session_index, session in enumerate(sessions, start=1):
        bars = session["bars"]
        assert isinstance(bars, list)
        if [bar["symbol"] for bar in bars] != expected_symbols:
            raise DataImportValidationError(
                [
                    {
                        "row_number": 1,
                        "field": "symbol",
                        "message": f"session {session_index} must contain every portfolio symbol exactly once",
                    }
                ]
            )

    normalized_snapshot = {
        "schema_version": 2,
        "market": market,
        "symbols": expected_symbols,
        "timezone": timezone,
        "price_basis": price_basis,
        "cutoff": cutoff,
        "price_scale": PRICE_SCALE,
        "cash_scale": PRICE_SCALE,
        "volume_scale": PRICE_SCALE,
        "sessions": sessions,
    }
    market_input = {
        "schema_version": 2,
        "account": _portfolio_market_account(expected_symbols),
        "sessions": [
            {
                "session_seq": session_index,
                "timestamp": session["timestamp"],
                "bars": [
                    {
                        **{
                            key: value
                            for key, value in bar.items()
                            if key != "volume_atoms"
                        },
                        "can_buy": True,
                        "can_sell": True,
                    }
                    for bar in session["bars"]
                ],
            }
            for session_index, session in enumerate(sessions, start=1)
        ],
        "intents": [],
    }
    normalized_body = _canonical_json_bytes(normalized_snapshot)
    return DataSnapshotMaterial(
        symbol=None,
        symbols=symbols,
        session_count=len(sessions),
        schema_version=2,
        sample_start=str(sessions[0]["timestamp"]),
        sample_end=str(sessions[-1]["timestamp"]),
        row_count=len(rows),
        normalized_body=normalized_body,
        market_input_body=_canonical_json_bytes(market_input),
    )


def deterministic_artifact_id(kind: str, sha256: str) -> str:
    return _deterministic_uuid(f"{kind}:{sha256}")


def _normalize_rows(
    rows: list[dict[str, object]],
    mapping: dict[str, str],
    zone: ZoneInfo,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    details: list[dict[str, object]] = []
    previous_timestamp_by_symbol: dict[str, datetime] = {}
    observed_keys: set[tuple[datetime, str]] = set()
    for row_index, row in enumerate(rows, start=2):
        timestamp = _timestamp(row.get(mapping["timestamp"]), zone, row_index, details)
        row_symbol = _required_text(row.get(mapping["symbol"]), "symbol", row_index, details)
        values = {
            field: _decimal(row.get(mapping[field]), field, row_index, details)
            for field in ("open", "high", "low", "close", "volume")
        }
        if any(value is None for value in values.values()) or timestamp is None or row_symbol is None:
            continue
        open_price = values["open"]
        high_price = values["high"]
        low_price = values["low"]
        close_price = values["close"]
        volume = values["volume"]
        assert open_price is not None
        assert high_price is not None
        assert low_price is not None
        assert close_price is not None
        assert volume is not None
        previous_timestamp = previous_timestamp_by_symbol.get(row_symbol)
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            details.append(
                {
                    "row_number": row_index,
                    "field": "timestamp",
                    "message": "must be strictly increasing within each symbol",
                }
            )
        previous_timestamp_by_symbol[row_symbol] = timestamp
        if (timestamp, row_symbol) in observed_keys:
            details.append(
                {
                    "row_number": row_index,
                    "field": "symbol",
                    "message": "must be unique within each timestamp",
                }
            )
        observed_keys.add((timestamp, row_symbol))
        for field, value in (("open", open_price), ("high", high_price), ("low", low_price), ("close", close_price)):
            if value <= 0:
                details.append(
                    {"row_number": row_index, "field": field, "message": "must be greater than zero"}
                )
        if volume < 0:
            details.append(
                {"row_number": row_index, "field": "volume", "message": "must be greater than or equal to zero"}
            )
        if high_price < max(open_price, close_price):
            details.append(
                {"row_number": row_index, "field": "high", "message": "must be at least open and close"}
            )
        if low_price > min(open_price, close_price):
            details.append(
                {"row_number": row_index, "field": "low", "message": "must be at most open and close"}
            )
        if high_price < low_price:
            details.append(
                {"row_number": row_index, "field": "high", "message": "must be greater than or equal to low"}
            )
        atoms = {
            field: _atoms(value, field, row_index, details)
            for field, value in values.items()
        }
        if any(value is None for value in atoms.values()):
            continue
        normalized.append(
            {
                "timestamp": _utc_timestamp(timestamp),
                "symbol": row_symbol,
                "open_atoms": atoms["open"],
                "high_atoms": atoms["high"],
                "low_atoms": atoms["low"],
                "close_atoms": atoms["close"],
                "volume_atoms": atoms["volume"],
            }
        )
    if details:
        raise DataImportValidationError(details)
    return normalized


def _validate_mapping(columns: list[str], mapping: dict[str, str]) -> None:
    details = [
        {
            "row_number": 1,
            "field": field,
            "message": "mapped column is unavailable",
        }
        for field in _REQUIRED_MAPPING_FIELDS
        if mapping.get(field) not in columns
    ]
    if details:
        raise DataImportValidationError(details)


def _timestamp(
    value: object,
    zone: ZoneInfo,
    row_number: int,
    details: list[dict[str, object]],
) -> datetime | None:
    text = _string_value(value).strip()
    if not text:
        details.append({"row_number": row_number, "field": "timestamp", "message": "is required"})
        return None
    try:
        if "T" not in text and " " not in text:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time(), zone)
        else:
            parsed = datetime.fromisoformat(text.removesuffix("Z") + ("+00:00" if text.endswith("Z") else ""))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=zone)
        return parsed.astimezone(UTC)
    except ValueError:
        details.append(
            {"row_number": row_number, "field": "timestamp", "message": "must be an RFC3339 timestamp or ISO date"}
        )
        return None


def _utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _required_text(
    value: object,
    field: str,
    row_number: int,
    details: list[dict[str, object]],
) -> str | None:
    text = _string_value(value).strip()
    if text:
        return text
    details.append({"row_number": row_number, "field": field, "message": "is required"})
    return None


def _decimal(
    value: object,
    field: str,
    row_number: int,
    details: list[dict[str, object]],
) -> Decimal | None:
    text = _string_value(value).strip()
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        details.append({"row_number": row_number, "field": field, "message": "must be a finite decimal"})
        return None
    if not parsed.is_finite():
        details.append({"row_number": row_number, "field": field, "message": "must be a finite decimal"})
        return None
    return parsed


def _atoms(
    value: Decimal,
    field: str,
    row_number: int,
    details: list[dict[str, object]],
) -> str | None:
    if value.as_tuple().exponent < -4:
        details.append(
            {"row_number": row_number, "field": field, "message": "must use at most four decimal places"}
        )
        return None
    return str(int(value * PRICE_SCALE))


def _market_account(market: str, symbol: str) -> dict[str, object]:
    if market == "a_share_daily":
        return {
            "model": "a_share_cash",
            "symbol": symbol,
            "price_scale": PRICE_SCALE,
            "cash_scale": PRICE_SCALE,
            "rate_scale": RATE_SCALE,
            "starting_balance_atoms": "1000000000",
            "lot_size": 100,
            "allow_research_short": True,
            "commission_rate_atoms": "600",
            "stamp_duty_rate_atoms": "1000",
            "maker_fee_rate_atoms": "0",
            "taker_fee_rate_atoms": "0",
            "slippage_atoms": "10",
        }
    if market == "crypto_linear_perp":
        return {
            "model": "crypto_linear_perp",
            "symbol": symbol,
            "price_scale": PRICE_SCALE,
            "cash_scale": PRICE_SCALE,
            "rate_scale": RATE_SCALE,
            "starting_balance_atoms": "1000000000",
            "lot_size": 1,
            "allow_research_short": False,
            "commission_rate_atoms": "0",
            "stamp_duty_rate_atoms": "0",
            "maker_fee_rate_atoms": "200",
            "taker_fee_rate_atoms": "600",
            "slippage_atoms": "10",
        }
    raise DataImportValidationError(
        [{"row_number": 1, "field": "market", "message": "must be a_share_daily or crypto_linear_perp"}]
    )


def _portfolio_market_account(symbols: list[str]) -> dict[str, object]:
    return {
        "model": "a_share_portfolio_cash",
        "symbols": symbols,
        "price_scale": PRICE_SCALE,
        "cash_scale": PRICE_SCALE,
        "rate_scale": RATE_SCALE,
        "starting_balance_atoms": "1000000000",
        "lot_size": 100,
        "commission_rate_atoms": "600",
        "stamp_duty_rate_atoms": "1000",
        "slippage_atoms": "10",
    }


def _timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise DataImportValidationError(
            [{"row_number": 1, "field": "timezone", "message": "must be an IANA timezone"}]
        ) from error


def _source_media_type(source_format: str) -> str:
    if source_format == "csv":
        return "text/csv"
    if source_format == "parquet":
        return "application/vnd.apache.parquet"
    raise DataImportValidationError(
        [{"row_number": 1, "field": "source_format", "message": "must be csv or parquet"}]
    )


def _body_bytes(body: bytes | BinaryIO) -> bytes:
    if isinstance(body, bytes):
        return body
    return body.read()


def _canonical_json_bytes(value: object) -> bytes:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _deterministic_uuid(name: str) -> str:
    return str(uuid.uuid5(_SOURCE_NAMESPACE, name))


def _string_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
