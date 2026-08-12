from __future__ import annotations

import json
import unittest
from pathlib import Path

import test_m3_formal_runs as formal_run_scenario
from jsonschema import Draft202012Validator, FormatChecker
from quant_domain.contracts import REGISTRY, SCHEMAS
from test_m2_session import PROJECT_ID, bind_command
from test_m7_data_snapshot_http import (
    A_SHARE_COMMAND_ID,
    A_SHARE_SNAPSHOT_ID,
    FIXTURE_DIRECTORY,
    PORTFOLIO_COMMAND_ID,
    PORTFOLIO_SNAPSHOT_ID,
    artifact_ref,
    snapshot_command,
)


STRATEGY_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "strategies"
    / "a_share_rotation"
    / "strategy.py"
).read_bytes()
TREND_STRATEGY_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "strategies"
    / "a_share_trend_breakout"
    / "strategy.py"
).read_bytes()


class M8SingleSymbolFormalRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = formal_run_scenario.M3FormalRunDomainTest(
            "test_merge_candidate_is_two_parent_immutable_and_moves_no_head"
        )
        self.scenario.setUp()
        self.domain = self.scenario.domain
        self.domain.submit_command(self.scenario._merge_command(TREND_STRATEGY_SOURCE))

    def tearDown(self) -> None:
        self.scenario.tearDown()

    def test_imported_single_symbol_snapshot_runs_the_builtin_strategy(self) -> None:
        self.domain.submit_command(
            bind_command(
                command_id="e8e8e8e8-e8e8-48e8-88e8-e8e8e8e8e8e8",
                workbench_id="data-import",
            )
        )
        file_name = "m7-a-share-daily.csv"
        preview = self.domain.preview_data_import(
            (FIXTURE_DIRECTORY / file_name).read_bytes(), file_name, "csv"
        )
        self.domain.submit_command(
            snapshot_command(
                command_id=A_SHARE_COMMAND_ID,
                snapshot_id=A_SHARE_SNAPSHOT_ID,
                source=preview["source"],
                source_format="csv",
                file_name=file_name,
                mapping=preview["suggested_mapping"],
                market="a_share_daily",
                timezone="Asia/Shanghai",
                cutoff="2026-01-14T00:00:00Z",
            )
        )
        snapshot = self.domain.data_snapshot(PROJECT_ID, A_SHARE_SNAPSHOT_ID)
        content = self.domain.data_snapshot_market_input(
            PROJECT_ID, A_SHARE_SNAPSHOT_ID
        )
        self.assertIsNotNone(content)
        artifact, _ = content
        self.domain.submit_command(
            bind_command(
                command_id="f8f8f8f8-f8f8-48f8-88f8-f8f8f8f8f8f8",
                workbench_id="canvas",
            )
        )
        command = self.scenario._formal_run_command()
        command["payload"].update(
            {
                "market_input": artifact_ref(artifact),
                "data_snapshot_id": snapshot["snapshot_id"],
                "data_snapshot_sha256": snapshot["sha256"],
                "price_basis": snapshot["price_basis"],
                "cutoff": snapshot["cutoff"],
                "timezone": snapshot["timezone"],
                "sample_start": snapshot["sample_start"],
                "sample_end": snapshot["sample_end"],
            }
        )

        self.domain.submit_command(command)
        completed = self.domain.run_next_job()
        detail = self.domain.run(PROJECT_ID, command["payload"]["run_id"])

        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertGreater(len(detail["engine_result"]["trades"]), 0)


class M8PortfolioFormalRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = formal_run_scenario.M3FormalRunDomainTest(
            "test_merge_candidate_is_two_parent_immutable_and_moves_no_head"
        )
        self.scenario.setUp()
        self.domain = self.scenario.domain
        self.domain.submit_command(self.scenario._merge_command(STRATEGY_SOURCE))

    def tearDown(self) -> None:
        self.scenario.tearDown()

    def test_rotation_snapshot_runs_through_checkpoint_v2_and_exposes_portfolio_result(self) -> None:
        self.domain.submit_command(
            bind_command(
                command_id="c8c8c8c8-c8c8-48c8-88c8-c8c8c8c8c8c8",
                workbench_id="data-import",
            )
        )
        file_name = "m8-a-share-rotation.csv"
        preview = self.domain.preview_data_import(
            (FIXTURE_DIRECTORY / file_name).read_bytes(), file_name, "csv"
        )
        self.domain.submit_command(
            snapshot_command(
                command_id=PORTFOLIO_COMMAND_ID,
                snapshot_id=PORTFOLIO_SNAPSHOT_ID,
                source=preview["source"],
                source_format="csv",
                file_name=file_name,
                mapping=preview["suggested_mapping"],
                market="a_share_daily",
                timezone="Asia/Shanghai",
                cutoff="2026-02-10T00:00:00Z",
            )
        )
        snapshot = self.domain.data_snapshot(PROJECT_ID, PORTFOLIO_SNAPSHOT_ID)
        content = self.domain.data_snapshot_market_input(
            PROJECT_ID, PORTFOLIO_SNAPSHOT_ID
        )
        self.assertIsNotNone(content)
        artifact, _ = content

        self.domain.submit_command(
            bind_command(
                command_id="d8d8d8d8-d8d8-48d8-88d8-d8d8d8d8d8d8",
                workbench_id="canvas",
            )
        )
        command = self.scenario._formal_run_command()
        payload = command["payload"]
        payload.update(
            {
                "market_input": artifact_ref(artifact),
                "data_snapshot_id": snapshot["snapshot_id"],
                "data_snapshot_sha256": snapshot["sha256"],
                "price_basis": snapshot["price_basis"],
                "cutoff": snapshot["cutoff"],
                "timezone": snapshot["timezone"],
                "sample_start": snapshot["sample_start"],
                "sample_end": snapshot["sample_end"],
                "engine_version": "oqs-quant-engine/0.2.0",
                "output_schema_version": 2,
                "gate_policy_version": "m8-v1",
                "strategy_protocol_version": "oqs-strategy-host/m8-portfolio-v1",
                "checkpoint_batch_size": 2,
                "engine_checkpoint_abi": "oqs-quant-engine/checkpoint-v2",
            }
        )

        queued = self.domain.submit_command(command)
        completed = self.domain.run_next_job()
        detail = self.domain.run(PROJECT_ID, payload["run_id"])

        self.assertEqual(queued["event"]["payload"]["lifecycle_version"], "m8-v1")
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual(completed["checkpoint_seq"], 3)
        self.assertEqual(detail["manifest"]["manifest_version"], "m8-v1")
        self.assertEqual(
            detail["manifest"]["checkpoint"]["final_next_session_index"], 6
        )
        self.assertEqual(detail["engine_result"]["schema_version"], 2)
        self.assertEqual(
            detail["engine_result"]["account_model"], "a_share_portfolio_cash"
        )
        self.assertGreater(len(detail["engine_result"]["trades"]), 0)
        self.assertEqual(len(detail["engine_result"]["equity_curve"]), 6)
        errors = list(
            Draft202012Validator(
                SCHEMAS["formal-run-read-model"],
                registry=REGISTRY,
                format_checker=FormatChecker(),
            ).iter_errors(detail)
        )
        self.assertEqual(errors, [], [error.message for error in errors])


if __name__ == "__main__":
    unittest.main()
