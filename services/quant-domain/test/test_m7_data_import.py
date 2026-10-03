from __future__ import annotations

import io
import hashlib
import json
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pq

from quant_domain.data_import import (
    DataImportValidationError,
    build_data_snapshot,
    preview_data_import,
)


CSV_BODY = (
    b"date,ticker,open,high,low,close,vol\n"
    b"2026-01-02,600519.SH,1500.1000,1510.2000,1490.0000,1505.5000,1000\n"
    b"2026-01-05,600519.SH,1505.5000,1512.0000,1500.0000,1510.0000,1200\n"
)
V3_BASKET_BODY = (
    b"timestamp,symbol,open,high,low,close,volume\n"
    b"2026-01-02T07:00:00Z,AAA.XSHG,10.00,10.20,9.90,10.10,1000000\n"
    b"2026-01-02T07:00:00Z,BBB.XSHG,20.00,20.30,19.80,20.10,800000\n"
    b"2026-01-05T07:00:00Z,AAA.XSHG,10.10,10.40,10.00,10.30,1200000\n"
    b"2026-01-05T07:00:00Z,BBB.XSHG,20.10,20.40,20.00,20.30,900000\n"
)
FIXTURE_DIRECTORY = Path(__file__).resolve().parents[3] / "fixtures" / "market"


class DataImportPreviewTest(unittest.TestCase):
    def test_csv_preview_suggests_alias_mapping_and_has_stable_source_identity(self) -> None:
        first = preview_data_import(CSV_BODY, "m7-a-share-daily.csv", "csv")
        repeated = preview_data_import(CSV_BODY, "m7-a-share-daily.csv", "csv")

        self.assertEqual(first["source_format"], "csv")
        self.assertEqual(first["file_name"], "m7-a-share-daily.csv")
        self.assertEqual(
            first["columns"], ["date", "ticker", "open", "high", "low", "close", "vol"]
        )
        self.assertEqual(
            first["suggested_mapping"],
            {
                "timestamp": "date",
                "symbol": "ticker",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "vol",
            },
        )
        self.assertEqual(first["preview_rows"][0]["close"], "1505.5000")
        self.assertEqual(first["total_rows"], 2)
        self.assertEqual(first["source"], repeated["source"])
        self.assertEqual(first["source"]["provenance"]["origin_kind"], "user_upload")

    def test_parquet_preview_matches_csv_columns_mapping_and_rows(self) -> None:
        crypto_body = (FIXTURE_DIRECTORY / "m7-crypto-linear.csv").read_bytes()
        csv_preview = preview_data_import(
            crypto_body, "m7-crypto-linear.csv", "csv"
        )
        table = pa_csv.read_csv(
            pa.BufferReader(crypto_body),
            convert_options=pa_csv.ConvertOptions(default_column_type=pa.string()),
        )
        destination = io.BytesIO()
        pq.write_table(table, destination)

        parquet_preview = preview_data_import(
            destination.getvalue(), "m7-crypto-linear.parquet", "parquet"
        )

        self.assertEqual(parquet_preview["columns"], csv_preview["columns"])
        self.assertEqual(parquet_preview["suggested_mapping"], csv_preview["suggested_mapping"])
        self.assertEqual(parquet_preview["preview_rows"], csv_preview["preview_rows"])
        self.assertEqual(parquet_preview["total_rows"], 8)

    def test_missing_required_aliases_and_invalid_row_return_structured_details(self) -> None:
        with self.assertRaises(DataImportValidationError) as missing:
            preview_data_import(b"when,price\n2026-01-02,1\n", "missing.csv", "csv")
        self.assertEqual(
            missing.exception.details,
            [
                {
                    "row_number": 1,
                    "field": "timestamp",
                    "message": "required mapping is missing",
                },
                {
                    "row_number": 1,
                    "field": "symbol",
                    "message": "required mapping is missing",
                },
                {
                    "row_number": 1,
                    "field": "open",
                    "message": "required mapping is missing",
                },
                {
                    "row_number": 1,
                    "field": "high",
                    "message": "required mapping is missing",
                },
                {
                    "row_number": 1,
                    "field": "low",
                    "message": "required mapping is missing",
                },
                {
                    "row_number": 1,
                    "field": "close",
                    "message": "required mapping is missing",
                },
                {
                    "row_number": 1,
                    "field": "volume",
                    "message": "required mapping is missing",
                },
            ],
        )

    def test_explicit_alias_mapping_normalizes_legal_bars_and_engine_input(self) -> None:
        material = build_data_snapshot(
            CSV_BODY,
            source_format="csv",
            mapping={
                "timestamp": "date",
                "symbol": "ticker",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "vol",
            },
            market="a_share_daily",
            timezone="Asia/Shanghai",
            price_basis="raw",
            cutoff="2026-01-06T00:00:00Z",
        )

        normalized = json.loads(material.normalized_body)
        market_input = json.loads(material.market_input_body)
        self.assertEqual(material.symbol, "600519.SH")
        self.assertEqual(material.row_count, 2)
        self.assertEqual(normalized["bars"][0]["timestamp"], "2026-01-01T16:00:00Z")
        self.assertEqual(normalized["bars"][0]["open_atoms"], "15001000")
        self.assertEqual(normalized["bars"][0]["volume_atoms"], "10000000")
        self.assertEqual(market_input["account"], {
            "model": "a_share_cash",
            "symbol": "600519.SH",
            "price_scale": 10000,
            "cash_scale": 10000,
            "rate_scale": 1000000,
            "starting_balance_atoms": "1000000000",
            "lot_size": 100,
            "allow_research_short": True,
            "commission_rate_atoms": "600",
            "stamp_duty_rate_atoms": "1000",
            "maker_fee_rate_atoms": "0",
            "taker_fee_rate_atoms": "0",
            "slippage_atoms": "10",
        })
        self.assertEqual(market_input["bars"][0]["session_seq"], 1)
        self.assertNotIn("volume_atoms", market_input["bars"][0])
        self.assertEqual(market_input["funding_events"], [])
        self.assertEqual(market_input["intents"], [])

    def test_multi_symbol_a_share_input_builds_a_sorted_shared_cash_session_panel(self) -> None:
        body = (FIXTURE_DIRECTORY / "m8-a-share-rotation.csv").read_bytes()
        material = build_data_snapshot(
            body,
            source_format="csv",
            mapping={
                "timestamp": "timestamp",
                "symbol": "symbol",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            },
            market="a_share_daily",
            timezone="Asia/Shanghai",
            price_basis="raw",
            cutoff="2026-02-10T00:00:00Z",
        )

        normalized = json.loads(material.normalized_body)
        market_input = json.loads(material.market_input_body)
        self.assertIsNone(material.symbol)
        self.assertEqual(material.symbols, ("AAA.XSHG", "BBB.XSHG", "CCC.XSHG"))
        self.assertEqual(material.session_count, 6)
        self.assertEqual(material.row_count, 18)
        self.assertEqual(normalized["schema_version"], 2)
        self.assertEqual(normalized["symbols"], list(material.symbols))
        self.assertEqual(len(normalized["sessions"]), 6)
        self.assertEqual(
            [bar["symbol"] for bar in normalized["sessions"][0]["bars"]],
            list(material.symbols),
        )
        self.assertIn("volume_atoms", normalized["sessions"][0]["bars"][0])
        self.assertEqual(market_input["schema_version"], 2)
        self.assertEqual(market_input["account"]["model"], "a_share_portfolio_cash")
        self.assertEqual(market_input["account"]["symbols"], list(material.symbols))
        self.assertEqual(len(market_input["sessions"]), 6)
        self.assertNotIn("volume_atoms", market_input["sessions"][0]["bars"][0])
        self.assertEqual(market_input["intents"], [])

    def test_a_share_v3_profile_is_opt_in_and_emits_schema3_engine_input(self) -> None:
        material = build_data_snapshot(
            CSV_BODY,
            source_format="csv",
            mapping={
                "timestamp": "date",
                "symbol": "ticker",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "vol",
            },
            market="a_share_daily",
            timezone="Asia/Shanghai",
            price_basis="raw",
            cutoff="2026-01-06T00:00:00Z",
            execution_profile="a-share-v3",
        )
        normalized = json.loads(material.normalized_body)
        market_input = json.loads(material.market_input_body)
        self.assertEqual(material.execution_profile, "a-share-v3")
        self.assertEqual(material.schema_version, 3)
        self.assertEqual(material.symbol, "600519.SH")
        self.assertEqual(normalized["schema_version"], 3)
        self.assertEqual(normalized["execution_profile"], "a-share-v3")
        self.assertEqual(market_input["schema_version"], 3)
        self.assertEqual(market_input["account"]["symbols"], ["600519.SH"])
        self.assertEqual(len(market_input["sessions"]), 2)
        self.assertEqual(
            market_input["sessions"][0]["bars"][0]["raw"]["volume_quantity"],
            "1000",
        )
        self.assertEqual(
            market_input["account"]["max_participation_rate_atoms"], "100000"
        )

    def test_a_share_v3_preserves_typed_corporate_action_sidecar_in_both_hash_inputs(self) -> None:
        actions = [
            {
                "action_id": "dividend-1",
                "symbol": "600519.SH",
                "effective_at": {"session_seq": 2, "phase": "open", "stable_seq": 1},
                "action_type": "cash_dividend",
                "cash_per_share_atoms": "2",
                "numerator": None,
                "denominator": None,
                "settlement_price_atoms": None,
            }
        ]
        material = build_data_snapshot(
            CSV_BODY,
            source_format="csv",
            mapping={
                "timestamp": "date", "symbol": "ticker", "open": "open",
                "high": "high", "low": "low", "close": "close", "volume": "vol",
            },
            market="a_share_daily",
            timezone="Asia/Shanghai",
            price_basis="raw",
            cutoff="2026-01-06T00:00:00Z",
            execution_profile="a-share-v3",
            corporate_actions=actions,
        )
        normalized = json.loads(material.normalized_body)
        market_input = json.loads(material.market_input_body)
        self.assertEqual(normalized["corporate_actions"], actions)
        self.assertEqual(market_input["corporate_actions"], actions)
        self.assertNotEqual(material.normalized_sha256, hashlib.sha256(
            json.dumps({**normalized, "corporate_actions": []}, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest())

    def test_a_share_v3_groups_a_fixed_basket_and_keeps_volume_as_share_quantity(self) -> None:
        material = build_data_snapshot(
            V3_BASKET_BODY,
            source_format="csv",
            mapping={
                "timestamp": "timestamp", "symbol": "symbol", "open": "open",
                "high": "high", "low": "low", "close": "close", "volume": "volume",
            },
            market="a_share_daily",
            timezone="Asia/Shanghai",
            price_basis="raw",
            cutoff="2026-01-06T00:00:00Z",
            execution_profile="a-share-v3",
        )

        normalized = json.loads(material.normalized_body)
        market_input = json.loads(material.market_input_body)
        self.assertIsNone(material.symbol)
        self.assertEqual(material.symbols, ("AAA.XSHG", "BBB.XSHG"))
        self.assertEqual(material.session_count, 2)
        self.assertEqual(normalized["symbols"], ["AAA.XSHG", "BBB.XSHG"])
        self.assertEqual(
            [bar["symbol"] for bar in market_input["sessions"][0]["bars"]],
            ["AAA.XSHG", "BBB.XSHG"],
        )
        first_bar = market_input["sessions"][0]["bars"][0]
        self.assertEqual(first_bar["raw"]["volume_quantity"], "1000000")
        self.assertEqual(
            market_input["account"]["max_participation_rate_atoms"], "100000"
        )

    def test_a_share_v3_rejects_unknown_basket_gaps_without_forward_fill(self) -> None:
        gap_body = V3_BASKET_BODY.replace(
            b"2026-01-05T07:00:00Z,BBB.XSHG,20.10,20.40,20.00,20.30,900000\n",
            b"",
        )

        with self.assertRaises(DataImportValidationError) as invalid:
            build_data_snapshot(
                gap_body,
                source_format="csv",
                mapping={
                    "timestamp": "timestamp", "symbol": "symbol", "open": "open",
                    "high": "high", "low": "low", "close": "close", "volume": "volume",
                },
                market="a_share_daily",
                timezone="Asia/Shanghai",
                price_basis="raw",
                cutoff="2026-01-06T00:00:00Z",
                execution_profile="a-share-v3",
            )

        self.assertEqual(
            invalid.exception.details,
            [{
                "row_number": 1,
                "field": "symbol",
                "message": (
                    "unknown data gap at session 2: expected basket "
                    "AAA.XSHG, BBB.XSHG; missing BBB.XSHG"
                ),
            }],
        )

    def test_a_share_v3_rejects_non_raw_prices_and_unknown_market_state(self) -> None:
        for price_basis in ("qfq", "hfq"):
            with self.subTest(price_basis=price_basis):
                with self.assertRaises(DataImportValidationError) as adjusted:
                    build_data_snapshot(
                        CSV_BODY,
                        source_format="csv",
                        mapping={
                            "timestamp": "date", "symbol": "ticker", "open": "open",
                            "high": "high", "low": "low", "close": "close", "volume": "vol",
                        },
                        market="a_share_daily",
                        timezone="Asia/Shanghai",
                        price_basis=price_basis,
                        cutoff="2026-01-06T00:00:00Z",
                        execution_profile="a-share-v3",
                    )
                self.assertEqual(adjusted.exception.details[0]["field"], "price_basis")

        ambiguous = (
            b"timestamp,symbol,open,high,low,close,volume\n"
            b"2026-01-02T07:00:00Z,AAA.XSHG,10,10,10,10,1000000\n"
        )
        with self.assertRaises(DataImportValidationError) as unknown:
            build_data_snapshot(
                ambiguous,
                source_format="csv",
                mapping={
                    "timestamp": "timestamp", "symbol": "symbol", "open": "open",
                    "high": "high", "low": "low", "close": "close", "volume": "volume",
                },
                market="a_share_daily",
                timezone="Asia/Shanghai",
                price_basis="raw",
                cutoff="2026-01-06T00:00:00Z",
                execution_profile="a-share-v3",
            )
        self.assertEqual(unknown.exception.details[0]["field"], "market_state")

    def test_a_share_v3_accepts_explicit_status_and_limit_columns_for_ambiguous_bars(self) -> None:
        body = (
            b"timestamp,symbol,open,high,low,close,volume,trading_status,price_limit_state\n"
            b"2026-01-02T07:00:00Z,AAA.XSHG,10,10,10,10,0,suspended,none\n"
            b"2026-01-05T07:00:00Z,AAA.XSHG,11,11,11,11,0,tradable,limit_up\n"
        )

        material = build_data_snapshot(
            body,
            source_format="csv",
            mapping={
                "timestamp": "timestamp", "symbol": "symbol", "open": "open",
                "high": "high", "low": "low", "close": "close", "volume": "volume",
            },
            market="a_share_daily",
            timezone="Asia/Shanghai",
            price_basis="raw",
            cutoff="2026-01-06T00:00:00Z",
            execution_profile="a-share-v3",
        )

        market_input = json.loads(material.market_input_body)
        self.assertEqual(
            market_input["sessions"][0]["bars"][0]["trading_status"], "suspended"
        )
        self.assertEqual(
            market_input["sessions"][1]["bars"][0]["price_limit_state"], "limit_up"
        )
        normalized = json.loads(material.normalized_body)
        self.assertEqual(normalized["market_state_sources"], ["input-columns/v1"])

    def test_a_share_v3_parquet_fixed_basket_matches_csv_engine_input(self) -> None:
        table = pa_csv.read_csv(
            pa.BufferReader(V3_BASKET_BODY),
            convert_options=pa_csv.ConvertOptions(default_column_type=pa.string()),
        )
        destination = io.BytesIO()
        pq.write_table(table, destination)
        mapping = {
            "timestamp": "timestamp", "symbol": "symbol", "open": "open",
            "high": "high", "low": "low", "close": "close", "volume": "volume",
        }

        csv_material = build_data_snapshot(
            V3_BASKET_BODY,
            source_format="csv",
            mapping=mapping,
            market="a_share_daily",
            timezone="Asia/Shanghai",
            price_basis="raw",
            cutoff="2026-01-06T00:00:00Z",
            execution_profile="a-share-v3",
        )
        parquet_material = build_data_snapshot(
            destination.getvalue(),
            source_format="parquet",
            mapping=mapping,
            market="a_share_daily",
            timezone="Asia/Shanghai",
            price_basis="raw",
            cutoff="2026-01-06T00:00:00Z",
            execution_profile="a-share-v3",
        )

        self.assertEqual(parquet_material.market_input_body, csv_material.market_input_body)
        self.assertEqual(parquet_material.normalized_body, csv_material.normalized_body)

    def test_a_share_v3_rejects_non_a_share_inputs(self) -> None:
        with self.assertRaises(DataImportValidationError):
            build_data_snapshot(
                CSV_BODY,
                source_format="csv",
                mapping={
                    "timestamp": "date", "symbol": "ticker", "open": "open",
                    "high": "high", "low": "low", "close": "close", "volume": "vol",
                },
                market="crypto_linear_perp",
                timezone="UTC",
                price_basis="raw",
                cutoff="2026-01-06T00:00:00Z",
                execution_profile="a-share-v3",
            )

    def test_invalid_data_row_reports_csv_row_number_and_field(self) -> None:
        body = (
            b"timestamp,symbol,open,high,low,close,volume\n"
            b"2026-01-02T00:00:00Z,SYNTH.XSHG,10.00000,9.0,11.0,10.0,-1\n"
        )
        with self.assertRaises(DataImportValidationError) as invalid:
            build_data_snapshot(
                body,
                source_format="csv",
                mapping={
                    "timestamp": "timestamp",
                    "symbol": "symbol",
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "volume": "volume",
                },
                market="a_share_daily",
                timezone="UTC",
                price_basis="raw",
                cutoff="2026-01-03T00:00:00Z",
            )
        self.assertEqual(
            invalid.exception.details,
            [
                {
                    "row_number": 2,
                    "field": "volume",
                    "message": "must be greater than or equal to zero",
                },
                {
                    "row_number": 2,
                    "field": "high",
                    "message": "must be at least open and close",
                },
                {
                    "row_number": 2,
                    "field": "low",
                    "message": "must be at most open and close",
                },
                {
                    "row_number": 2,
                    "field": "high",
                    "message": "must be greater than or equal to low",
                },
                {
                    "row_number": 2,
                    "field": "open",
                    "message": "must use at most four decimal places",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
