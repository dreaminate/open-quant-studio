from __future__ import annotations

import hashlib
import html
import json
import unittest
from pathlib import Path

import oqs_quant_engine

from quant_domain.run_report import (
    build_run_report,
    canonical_report_json,
    render_run_report_html,
)


ROOT = Path(__file__).resolve().parents[3]
RATE_SCALE = 1_000_000


def _detail(result: dict[str, object], *, run_id: str = "run-m9") -> dict[str, object]:
    result_bytes = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    result_hash = hashlib.sha256(result_bytes).hexdigest()
    run_spec = {
        "run_spec_id": "spec-m9",
        "project_id": "project-m9",
        "activity_id": "activity-m9",
        "variant_id": "variant-m9",
        "candidate_revision_id": "revision-m9",
        "data_snapshot_id": "snapshot-m9",
        "data_snapshot_sha256": "a" * 64,
        "strategy_tree_oid": "b" * 40,
        "parameters_sha256": "c" * 64,
        "cost_model_sha256": "d" * 64,
        "environment_lock_sha256": "e" * 64,
        "engine_version": result["engine_version"],
        "price_basis": "raw",
        "cutoff": "2026-01-01T00:00:00Z",
        "timezone": "Asia/Shanghai",
        "sample_start": "2026-01-01T00:00:00Z",
        "sample_end": "2026-01-31T23:59:59Z",
    }
    manifest = {
        "run_spec": run_spec,
        "engine_result": {
            "artifact_id": "engine-result-m9",
            "sha256": result_hash,
        },
    }
    return {
        "run": {
            "run_id": run_id,
            "run_spec_id": run_spec["run_spec_id"],
            "project_id": run_spec["project_id"],
            "activity_id": run_spec["activity_id"],
            "variant_id": run_spec["variant_id"],
            "candidate_revision_id": run_spec["candidate_revision_id"],
            "status": "succeeded",
            "calculation_hash": result_hash,
            "finished_at": "2026-02-01T00:00:00Z",
            "engine_result_artifact_id": "engine-result-m9",
            "manifest_artifact_id": "manifest-m9",
        },
        "run_spec": run_spec,
        "manifest": manifest,
        "artifacts": {
            "engine_result": {
                "artifact_id": "engine-result-m9",
                "sha256": result_hash,
            },
            "manifest": {
                "artifact_id": "manifest-m9",
                "sha256": "f" * 64,
            },
        },
        "engine_result": result,
    }


def _v1_result() -> dict[str, object]:
    fixture = json.loads(
        (ROOT / "fixtures/backtests/m3-a-share-long-short-v1.json").read_text()
    )
    return json.loads(
        oqs_quant_engine.run_engine_v1(
            json.dumps(fixture["input"], separators=(",", ":")).encode()
        )
    )


def _v2_result() -> dict[str, object]:
    fixture = json.loads(
        (ROOT / "fixtures/backtests/m8-a-share-rotation-v2.json").read_text()
    )
    return json.loads(
        oqs_quant_engine.run_engine_v2(
            json.dumps(fixture["input"], separators=(",", ":")).encode()
        )
    )


def _crypto_result() -> dict[str, object]:
    bars = [
        {
            "session_seq": 1,
            "timestamp": "2026-03-01T00:00:00Z",
            "open_atoms": "1000",
            "high_atoms": "1100",
            "low_atoms": "900",
            "close_atoms": "1000",
            "can_buy": True,
            "can_sell": True,
        },
        {
            "session_seq": 2,
            "timestamp": "2026-03-02T00:00:00Z",
            "open_atoms": "900",
            "high_atoms": "950",
            "low_atoms": "850",
            "close_atoms": "900",
            "can_buy": True,
            "can_sell": True,
        },
        {
            "session_seq": 3,
            "timestamp": "2026-03-03T00:00:00Z",
            "open_atoms": "800",
            "high_atoms": "850",
            "low_atoms": "750",
            "close_atoms": "800",
            "can_buy": True,
            "can_sell": True,
        },
    ]

    def intent(intent_id: str, seq: int, side: str, effect: str, session: int) -> dict[str, object]:
        return {
            "intent_id": intent_id,
            "intent_seq": seq,
            "symbol": "BTC-PERP",
            "side": side,
            "position_effect": effect,
            "quantity": "1",
            "order_type": "market",
            "known_at": {"session_seq": session - 1, "phase": "close", "stable_seq": seq},
            "effective_at": {"session_seq": session, "phase": "open", "stable_seq": seq},
            "limit_price_atoms": None,
            "stop_price_atoms": None,
            "time_in_force": "day",
            "oco_group": None,
        }

    engine_input = {
        "schema_version": 1,
        "account": {
            "model": "crypto_linear_perp",
            "symbol": "BTC-PERP",
            "price_scale": 100,
            "cash_scale": 100,
            "rate_scale": RATE_SCALE,
            "starting_balance_atoms": "1000000",
            "lot_size": 1,
            "allow_research_short": False,
            "commission_rate_atoms": "0",
            "stamp_duty_rate_atoms": "0",
            "maker_fee_rate_atoms": "200",
            "taker_fee_rate_atoms": "600",
            "slippage_atoms": "0",
        },
        "bars": bars,
        "funding_events": [
            {
                "event_id": "funding-1",
                "session_seq": 2,
                "phase": "close",
                "stable_seq": 1,
                "rate_atoms": "1000",
                "mark_price_atoms": "900",
            }
        ],
        "intents": [
            intent("short", 1, "sell", "open", 1),
            intent("cover", 2, "buy", "close", 3),
        ],
    }
    return json.loads(
        oqs_quant_engine.run_engine_v1(
            json.dumps(engine_input, separators=(",", ":")).encode()
        )
    )


class M9RunReportTest(unittest.TestCase):
    def test_v1_reference_matches_rust_metrics_and_definitions(self) -> None:
        report = build_run_report(_detail(_v1_result()))

        self.assertEqual(report["report_version"], "m9-v1")
        self.assertEqual(report["summary"]["starting_equity_atoms"], "1000000")
        self.assertEqual(report["summary"]["ending_equity_atoms"], "1025534")
        self.assertEqual(report["summary"]["net_pnl_atoms"], "25534")
        self.assertEqual(report["summary"]["max_drawdown_atoms"], "-1159")
        self.assertEqual(report["summary"]["max_drawdown_rate_atoms"], "-1138")
        self.assertEqual(report["summary"]["gross_exposure_atoms"], "0")
        self.assertEqual(report["summary"]["net_exposure_atoms"], "0")
        self.assertEqual(report["summary"]["total_fees_atoms"], "248")
        self.assertEqual(report["summary"]["total_stamp_duty_atoms"], "218")
        self.assertEqual(report["summary"]["total_slippage_atoms"], "4000")
        self.assertEqual(report["summary"]["closed_trade_count"], 2)
        self.assertTrue(report["reconciliation"]["passed"])
        expected_fields = {
            "start_at",
            "end_at",
            "session_count",
            *report["summary"].keys(),
        }
        self.assertEqual(
            {definition["field"] for definition in report["definitions"]},
            expected_fields,
        )

    def test_crypto_funding_and_short_are_reconciled(self) -> None:
        result = _crypto_result()
        report = build_run_report(_detail(result, run_id="crypto-run"))

        self.assertEqual(report["identities"]["account_model"], "crypto_linear_perp")
        self.assertEqual(report["summary"]["total_funding_atoms"], "-1")
        self.assertEqual(report["summary"]["closed_trade_count"], 1)
        self.assertEqual(report["summary"]["open_position_count"], 0)
        self.assertTrue(report["reconciliation"]["passed"])

    def test_v2_portfolio_uses_market_value_for_exposure(self) -> None:
        report = build_run_report(_detail(_v2_result(), run_id="portfolio-run"))

        self.assertEqual(report["period"], {
            "start_at": "2026-02-02T07:00:00Z",
            "end_at": "2026-02-05T07:00:00Z",
            "session_count": 4,
        })
        self.assertEqual(report["summary"]["gross_exposure_atoms"], "0")
        self.assertEqual(report["summary"]["net_exposure_atoms"], "0")
        self.assertEqual(report["summary"]["ending_equity_atoms"], "16000")
        self.assertTrue(report["reconciliation"]["passed"])

    def test_zero_trade_output_uses_starting_equity_and_empty_period(self) -> None:
        fixture = json.loads(
            (ROOT / "fixtures/backtests/m3-a-share-long-short-v1.json").read_text()
        )
        engine_input = dict(fixture["input"])
        engine_input["bars"] = []
        engine_input["intents"] = []
        result = json.loads(
            oqs_quant_engine.run_engine_v1(
                json.dumps(engine_input, separators=(",", ":")).encode()
            )
        )

        report = build_run_report(_detail(result, run_id="zero-run"))

        self.assertEqual(report["period"], {"start_at": None, "end_at": None, "session_count": 0})
        self.assertEqual(report["summary"]["ending_equity_atoms"], "1000000")
        self.assertEqual(report["summary"]["total_return_rate_atoms"], "0")
        self.assertTrue(report["reconciliation"]["passed"])

    def test_html_contains_exact_canonical_json_and_escaped_values(self) -> None:
        report = build_run_report(_detail(_v1_result()))
        encoded = canonical_report_json(report)
        document = render_run_report_html(report).decode()

        self.assertIn(
            '<script id="oqs-run-report" type="application/json">'
            + encoded.decode()
            + "</script>",
            document,
        )
        self.assertIn(html.escape("oqs-quant-engine/0.1.0", quote=True), document)
        self.assertNotIn("<script src=", document)
        self.assertNotIn("<script>\n", document)


if __name__ == "__main__":
    unittest.main()
