from __future__ import annotations

import io
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
