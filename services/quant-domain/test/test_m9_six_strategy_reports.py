from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from oqs_quant_engine import run_engine_v1, run_engine_v2

from quant_domain.formal_runner import run_strategy_host
from quant_domain.run_report import build_run_report
import test_m8_strategy_library as _m8


ROOT = Path(__file__).resolve().parents[3]


def report_detail(
    result: dict[str, object], strategy_id: str, ordinal: int
) -> dict[str, object]:
    result_body = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    result_sha256 = hashlib.sha256(result_body).hexdigest()
    digit = str(ordinal)
    run_id = f"9{digit}{digit}{digit}{digit}{digit}{digit}{digit}-{digit}{digit}{digit}{digit}-4{digit}{digit}{digit}-8{digit}{digit}{digit}-{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}"
    spec_id = f"8{digit}{digit}{digit}{digit}{digit}{digit}{digit}-{digit}{digit}{digit}{digit}-4{digit}{digit}{digit}-8{digit}{digit}{digit}-{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}"
    artifact_id = f"7{digit}{digit}{digit}{digit}{digit}{digit}{digit}-{digit}{digit}{digit}{digit}-4{digit}{digit}{digit}-8{digit}{digit}{digit}-{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}"
    manifest_id = f"6{digit}{digit}{digit}{digit}{digit}{digit}{digit}-{digit}{digit}{digit}{digit}-4{digit}{digit}{digit}-8{digit}{digit}{digit}-{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}{digit}"
    run_spec = {
        "run_spec_id": spec_id,
        "project_id": "11111111-1111-4111-8111-111111111111",
        "activity_id": "22222222-2222-4222-8222-222222222222",
        "variant_id": "33333333-3333-4333-8333-333333333333",
        "candidate_revision_id": "44444444-4444-4444-8444-444444444444",
        "data_snapshot_id": "55555555-5555-4555-8555-555555555555",
        "data_snapshot_sha256": "a" * 64,
        "strategy_tree_oid": "b" * 40,
        "parameters_sha256": hashlib.sha256(strategy_id.encode()).hexdigest(),
        "cost_model_sha256": "c" * 64,
        "environment_lock_sha256": "d" * 64,
        "price_basis": "raw",
        "cutoff": "2026-12-31T00:00:00Z",
        "timezone": "Asia/Shanghai",
        "sample_start": "2026-01-01T00:00:00Z",
        "sample_end": "2026-12-31T00:00:00Z",
    }
    return {
        "run": {
            "run_id": run_id,
            "run_spec_id": spec_id,
            "project_id": run_spec["project_id"],
            "activity_id": run_spec["activity_id"],
            "variant_id": run_spec["variant_id"],
            "candidate_revision_id": run_spec["candidate_revision_id"],
            "status": "succeeded",
            "calculation_hash": result_sha256,
            "finished_at": "2026-12-31T00:00:00Z",
            "engine_result_artifact_id": artifact_id,
            "manifest_artifact_id": manifest_id,
        },
        "run_spec": run_spec,
        "manifest": {"run_spec": run_spec},
        "artifacts": {
            "engine_result": {"artifact_id": artifact_id, "sha256": result_sha256},
            "manifest": {"artifact_id": manifest_id, "sha256": "e" * 64},
        },
        "engine_result": result,
    }


class M9SixStrategyReportsTest(unittest.TestCase):
    def test_all_six_strategy_results_reconcile_into_reports(self) -> None:
        reports: dict[str, dict[str, object]] = {}
        for ordinal, (strategy_id, case) in enumerate(_m8.SINGLE_SYMBOL_CASES.items(), 1):
            source = (ROOT / _m8.strategy_record(strategy_id)["source"]).read_bytes()
            emitted = run_strategy_host(
                source,
                _m8.market_input(case["symbol"], case["closes"]),
            )
            self.assertIsNotNone(emitted)
            account_model = (
                "a_share_cash"
                if strategy_id.startswith("a_share_")
                else "crypto_linear_perp"
            )
            result = json.loads(
                run_engine_v1(
                    _m8.formal_input(
                        case["symbol"], case["closes"], emitted, account_model
                    )
                )
            )
            reports[strategy_id] = build_run_report(
                report_detail(result, strategy_id, ordinal)
            )

        rotation_source = (
            ROOT / _m8.strategy_record("a_share_rotation")["source"]
        ).read_bytes()
        rotation_intents = run_strategy_host(
            rotation_source, _m8.rotation_input()
        )
        self.assertIsNotNone(rotation_intents)
        fixture = json.loads(
            (ROOT / "fixtures/backtests/m8-a-share-rotation-v2.json").read_text()
        )
        fixture["input"]["account"]["starting_balance_atoms"] = "20000"
        fixture["input"]["intents"] = rotation_intents
        rotation_result = json.loads(
            run_engine_v2(
                json.dumps(fixture["input"], separators=(",", ":")).encode()
            )
        )
        reports["a_share_rotation"] = build_run_report(
            report_detail(rotation_result, "a_share_rotation", 6)
        )

        self.assertEqual(len(reports), 6)
        for strategy_id, report in reports.items():
            with self.subTest(strategy_id=strategy_id):
                self.assertTrue(report["reconciliation"]["passed"])
                self.assertEqual(report["summary"]["fill_count"], 2 if strategy_id != "a_share_rotation" else 3)
                self.assertGreater(report["period"]["session_count"], 0)


if __name__ == "__main__":
    unittest.main()
