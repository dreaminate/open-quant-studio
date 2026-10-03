from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Event

from quant_domain.domain import (
    ContractViolation,
    DomainConflict,
    PromotionConflict,
    QuantDomain,
    RevisionConflict,
    _canonicalize_a_share_v3_intents,
)
from quant_domain.formal_runner import run_strategy_host
from test_m2_session import (
    ACTIVITY_ID,
    CORRELATION_ID,
    PROJECT_ID,
    SENDER_SESSION_ID,
    artifact_for,
    bind_command,
    register_command,
)
from test_m3_revisions import create_revision_command, create_variant_command


ROOT_REVISION_ID = "10101010-1010-4010-8010-101010101010"
VARIANT_ID = "20202020-2020-4020-8020-202020202020"
VARIANT_REVISION_ID = "30303030-3030-4030-8030-303030303030"
MERGE_REVISION_ID = "40404040-4040-4040-8040-404040404040"
RUN_SPEC_ID = "71717171-7171-4171-8171-717171717171"
RUN_ID = "72727272-7272-4272-8272-727272727272"
VALIDATION_ID = "73737373-7373-4373-8373-737373737373"
SECOND_RUN_ID = "81818181-8181-4181-8181-818181818181"
SECOND_VALIDATION_ID = "82828282-8282-4282-8282-828282828282"
RACING_VARIANT_ID = "90909090-9090-4090-8090-909090909090"
RACING_VARIANT_REVISION_ID = "91919191-9191-4191-8191-919191919191"
RACING_MERGE_REVISION_ID = "92929292-9292-4292-8292-929292929292"
RACING_RUN_SPEC_ID = "93939393-9393-4393-8393-939393939393"
RACING_RUN_ID = "94949494-9494-4494-8494-949494949494"
RACING_VALIDATION_ID = "95959595-9595-4595-8595-959595959595"
CONFIG_BODY = b'{"commission_rate_atoms":"600"}\n'
CONFIG_ARTIFACT_ID = "85858585-8585-4585-8585-858585858585"
DATA_SNAPSHOT_ID = "77777777-7777-4777-8777-777777777777"
DATA_SNAPSHOT_COMMAND_ID = "67676767-6767-4767-8767-676767676767"


class M3FormalRunDomainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tempdir.name)
        self.domain = QuantDomain(self.data_root)
        self.domain.submit_command(register_command())
        self._create_variant_revision()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _stage(self, body: bytes) -> None:
        self.domain.store_blob(hashlib.sha256(body).hexdigest(), body)

    def _formal_fixture(self) -> dict[str, object]:
        fixture_path = (
            Path(__file__).parents[3]
            / "fixtures"
            / "backtests"
            / "m3-a-share-long-short-v1.json"
        )
        return json.loads(fixture_path.read_text())

    def _strategy_source(self) -> bytes:
        fixture = self._formal_fixture()
        templates: dict[int, list[dict[str, object]]] = {}
        for intent in fixture["input"]["intents"]:
            template = {
                key: value
                for key, value in intent.items()
                if key not in {"known_at", "effective_at"}
            }
            known_session = intent["known_at"]["session_seq"]
            templates.setdefault(known_session, []).append(template)
        return (
            f"INTENTS = {templates!r}\n"
            "def on_start():\n"
            "    return INTENTS.get(0, [])\n"
            "def on_bar(bar):\n"
            "    return INTENTS.get(bar['session_seq'], [])\n"
        ).encode()

    def _v3_strategy_source(self) -> bytes:
        fixture = self._formal_fixture()
        templates: dict[int, list[dict[str, object]]] = {}
        for intent in fixture["input"]["intents"]:
            template = {
                key: value
                for key, value in intent.items()
                if key
                not in {
                    "known_at",
                    "effective_at",
                    "stop_price_atoms",
                    "oco_group",
                }
            }
            template["intent_kind"] = "order"
            template["book"] = (
                "research_short"
                if str(intent["intent_id"]).startswith("research-short")
                else "cash_long"
            )
            known_session = intent["known_at"]["session_seq"]
            templates.setdefault(known_session, []).append(template)
        return (
            f"INTENTS = {templates!r}\n"
            "def on_start():\n"
            "    return INTENTS.get(0, [])\n"
            "def on_bar(bar):\n"
            "    return INTENTS.get(bar['session_seq'], [])\n"
        ).encode()

    def _create_variant_revision(self) -> None:
        root_body = b"def on_bar(bar):\n    return []\n"
        self._stage(root_body)
        self._stage(CONFIG_BODY)
        self.domain.submit_command(
            create_revision_command(
                command_id="51515151-5151-4151-8151-515151515151",
                revision_id=ROOT_REVISION_ID,
                files=[
                    (
                        "strategy.py",
                        root_body,
                        "61616161-6161-4161-8161-616161616161",
                    ),
                    ("config/costs.json", CONFIG_BODY, CONFIG_ARTIFACT_ID),
                ],
            )
        )
        self.domain.submit_command(
            create_variant_command(
                command_id="62626262-6262-4262-8262-626262626262",
                variant_id=VARIANT_ID,
                base_revision_id=ROOT_REVISION_ID,
            )
        )
        child_body = b"def on_bar(bar):\n    return [{'side': 'buy'}]\n"
        self._stage(child_body)
        self.domain.submit_command(
            create_revision_command(
                command_id="63636363-6363-4363-8363-636363636363",
                revision_id=VARIANT_REVISION_ID,
                files=[
                    (
                        "strategy.py",
                        child_body,
                        "64646464-6464-4464-8464-646464646464",
                    )
                ],
                variant_id=VARIANT_ID,
                base_revision_id=ROOT_REVISION_ID,
            )
        )

    def _ensure_formal_data_snapshot(self) -> dict[str, object]:
        snapshot = self.domain.data_snapshot(PROJECT_ID, DATA_SNAPSHOT_ID)
        if snapshot is not None:
            return snapshot

        fixture_path = (
            Path(__file__).parents[3]
            / "fixtures"
            / "market"
            / "m3-a-share-daily.csv"
        )
        body = fixture_path.read_bytes()
        preview = self.domain.preview_data_import(body, fixture_path.name, "csv")
        self.domain.submit_command(
            bind_command(
                command_id="68686868-6868-4868-8868-686868686868",
                workbench_id="data-import",
            )
        )
        self.domain.submit_command(
            {
                "command_id": DATA_SNAPSHOT_COMMAND_ID,
                "schema_version": 1,
                "command_type": "data.snapshot_create",
                "project_id": PROJECT_ID,
                "activity_id": ACTIVITY_ID,
                "session_id": SENDER_SESSION_ID,
                "workbench_id": "data-import",
                "correlation_id": CORRELATION_ID,
                "expected_revision_id": None,
                "variant_id": None,
                "base_revision_id": None,
                "payload": {
                    "snapshot_id": DATA_SNAPSHOT_ID,
                    "source": preview["source"],
                    "source_format": "csv",
                    "file_name": fixture_path.name,
                    "mapping": preview["suggested_mapping"],
                    "market": "a_share_daily",
                    "timezone": "Asia/Shanghai",
                    "price_basis": "raw",
                    "cutoff": "2026-01-08T00:00:00Z",
                },
            }
        )
        self.domain.submit_command(
            bind_command(
                command_id="69696969-6969-4969-8969-696969696969",
                workbench_id="canvas",
            )
        )
        snapshot = self.domain.data_snapshot(PROJECT_ID, DATA_SNAPSHOT_ID)
        self.assertIsNotNone(snapshot)
        return snapshot

    @staticmethod
    def _artifact_ref(artifact: dict[str, object]) -> dict[str, object]:
        return {
            "artifact_id": artifact["artifact_id"],
            "sha256": artifact["sha256"],
            "media_type": artifact["media_type"],
            "byte_size": artifact["byte_size"],
            "storage_uri": artifact["storage_uri"],
            "producing_revision_id": artifact["producing_revision_id"],
            "producing_run_id": artifact["producing_run_id"],
            "provenance": {
                "origin_kind": artifact["origin_kind"],
                "source_ref": artifact["source_ref"],
            },
        }

    def _merge_command(
        self,
        merged_body: bytes | None = None,
    ) -> dict[str, object]:
        if merged_body is None:
            merged_body = self._strategy_source()
        self._stage(merged_body)
        return {
            "command_id": "65656565-6565-4565-8565-656565656565",
            "schema_version": 1,
            "command_type": "workspace.merge_create",
            "project_id": PROJECT_ID,
            "activity_id": ACTIVITY_ID,
            "session_id": SENDER_SESSION_ID,
            "workbench_id": "canvas",
            "correlation_id": CORRELATION_ID,
            "expected_revision_id": ROOT_REVISION_ID,
            "variant_id": VARIANT_ID,
            "base_revision_id": VARIANT_REVISION_ID,
            "payload": {
                "candidate_revision_id": MERGE_REVISION_ID,
                "message": "Resolved merge candidate",
                "files": [
                    {
                        "path": "strategy.py",
                        "artifact": artifact_for(
                            merged_body,
                            "66666666-6666-4666-8666-666666666666",
                        ),
                    },
                    {
                        "path": "config/costs.json",
                        "artifact": artifact_for(CONFIG_BODY, CONFIG_ARTIFACT_ID),
                    },
                ],
            },
        }

    def _formal_run_command(self) -> dict[str, object]:
        snapshot = self._ensure_formal_data_snapshot()
        content = self.domain.data_snapshot_market_input(PROJECT_ID, DATA_SNAPSHOT_ID)
        self.assertIsNotNone(content)
        market_input_artifact, _ = content
        candidate = self.domain.revision(PROJECT_ID, MERGE_REVISION_ID)
        return {
            "command_id": "74747474-7474-4474-8474-747474747474",
            "schema_version": 1,
            "command_type": "formal.run_request",
            "project_id": PROJECT_ID,
            "activity_id": ACTIVITY_ID,
            "session_id": SENDER_SESSION_ID,
            "workbench_id": "canvas",
            "correlation_id": CORRELATION_ID,
            "expected_revision_id": MERGE_REVISION_ID,
            "variant_id": VARIANT_ID,
            "base_revision_id": MERGE_REVISION_ID,
            "payload": {
                "run_spec_id": RUN_SPEC_ID,
                "run_id": RUN_ID,
                "validation_id": VALIDATION_ID,
                "candidate_revision_id": MERGE_REVISION_ID,
                "market_input": self._artifact_ref(market_input_artifact),
                "data_snapshot_id": snapshot["snapshot_id"],
                "data_snapshot_sha256": snapshot["sha256"],
                "strategy_tree_oid": candidate["git_tree_oid"],
                "parameters_sha256": hashlib.sha256(b"{}").hexdigest(),
                "cost_model_sha256": hashlib.sha256(b"m3-fixture-costs").hexdigest(),
                "environment_lock_sha256": hashlib.sha256(b"test-lock").hexdigest(),
                "engine_version": "oqs-quant-engine/0.1.0",
                "price_basis": snapshot["price_basis"],
                "cutoff": snapshot["cutoff"],
                "timezone": snapshot["timezone"],
                "sample_start": snapshot["sample_start"],
                "sample_end": snapshot["sample_end"],
                "random_seed": 0,
                "output_schema_version": 1,
                "gate_policy_version": "m5-v1",
                "strategy_protocol_version": "oqs-strategy-host/m5-stream-v2",
                "checkpoint_batch_size": 2,
                "engine_checkpoint_abi": "oqs-quant-engine/checkpoint-v1",
            },
        }

    def _promote_command(
        self,
        validation_id: str = VALIDATION_ID,
        command_id: str = "78787878-7878-4878-8878-787878787878",
    ) -> dict[str, object]:
        return {
            "command_id": command_id,
            "schema_version": 1,
            "command_type": "workspace.revision_promote",
            "project_id": PROJECT_ID,
            "activity_id": ACTIVITY_ID,
            "session_id": SENDER_SESSION_ID,
            "workbench_id": "canvas",
            "correlation_id": CORRELATION_ID,
            "expected_revision_id": ROOT_REVISION_ID,
            "variant_id": VARIANT_ID,
            "base_revision_id": ROOT_REVISION_ID,
            "payload": {
                "variant_id": VARIANT_ID,
                "candidate_revision_id": MERGE_REVISION_ID,
                "validation_id": validation_id,
            },
        }

    def test_merge_candidate_is_two_parent_immutable_and_moves_no_head(self) -> None:
        receipt = self.domain.submit_command(self._merge_command())

        self.assertEqual(
            receipt["event"]["event_type"], "workspace.merge_candidate_created"
        )
        self.assertEqual(self.domain.project_head(PROJECT_ID), ROOT_REVISION_ID)
        variant = next(
            row
            for row in self.domain.variants(PROJECT_ID)
            if row["variant_id"] == VARIANT_ID
        )
        self.assertEqual(variant["head_revision_id"], VARIANT_REVISION_ID)
        candidate = self.domain.revision(PROJECT_ID, MERGE_REVISION_ID)
        repository = self.data_root / "git" / f"{PROJECT_ID}.git"
        commit = subprocess.run(
            [
                "/usr/bin/git",
                f"--git-dir={repository}",
                "cat-file",
                "-p",
                candidate["git_commit_oid"],
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        parent_lines = [
            line for line in commit.splitlines() if line.startswith("parent ")
        ]
        root = self.domain.revision(PROJECT_ID, ROOT_REVISION_ID)
        variant_revision = self.domain.revision(PROJECT_ID, VARIANT_REVISION_ID)
        self.assertEqual(
            parent_lines,
            [
                f"parent {root['git_commit_oid']}",
                f"parent {variant_revision['git_commit_oid']}",
            ],
        )

    def test_merge_candidate_rejects_a_partial_resolved_parent_tree(self) -> None:
        command = self._merge_command()
        command["payload"]["files"] = [
            file
            for file in command["payload"]["files"]
            if file["path"] == "strategy.py"
        ]

        with self.assertRaises(RevisionConflict):
            self.domain.submit_command(command)

        self.assertIsNone(self.domain.revision(PROJECT_ID, MERGE_REVISION_ID))
        self.assertEqual(self.domain.project_head(PROJECT_ID), ROOT_REVISION_ID)

    def test_formal_run_persists_a_hash_bound_manifest_without_recalculation(self) -> None:
        self.domain.submit_command(self._merge_command())
        queued = self.domain.submit_command(self._formal_run_command())
        self.assertEqual(queued["event"]["event_type"], "formal.run_queued")

        job = self.domain.run_next_job()
        self.assertEqual(job["job_type"], "formal.run")
        self.assertEqual(job["status"], "succeeded")
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            run = connection.execute(
                "SELECT * FROM formal_runs WHERE run_id = ?", (RUN_ID,)
            ).fetchone()
            validation = connection.execute(
                "SELECT * FROM merge_validations WHERE validation_id = ?",
                (VALIDATION_ID,),
            ).fetchone()
            manifest_artifact = connection.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ?",
                (run["manifest_artifact_id"],),
            ).fetchone()
            run_artifacts = connection.execute(
                "SELECT kind, artifact_id FROM run_artifacts WHERE run_id = ?",
                (RUN_ID,),
            ).fetchall()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE formal_runs SET status = 'failed' WHERE run_id = ?",
                    (RUN_ID,),
                )
        manifest = json.loads(
            self.domain.blob_path(manifest_artifact["sha256"]).read_bytes()
        )
        self.assertEqual(manifest["run_id"], RUN_ID)
        self.assertEqual(manifest["run_spec"]["run_spec_id"], RUN_SPEC_ID)
        self.assertEqual(
            manifest["engine_result"]["sha256"], run["calculation_hash"]
        )
        intent_tape = manifest["strategy_execution"]
        self.assertEqual(
            intent_tape["intent_tape_sha256"],
            hashlib.sha256(
                json.dumps(
                    self._formal_fixture()["input"]["intents"],
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
        )
        run_artifact_identities = {
            (row["kind"], row["artifact_id"]) for row in run_artifacts
        }
        self.assertEqual(
            {kind for kind, _ in run_artifact_identities},
            {"intent_tape", "engine_result", "manifest"},
        )
        self.assertIn(
            ("intent_tape", intent_tape["intent_tape_artifact_id"]),
            run_artifact_identities,
        )
        self.assertEqual(validation["outcome"], "passed")
        self.assertEqual(validation["contract_outcome"], "passed")
        self.assertEqual(validation["strategy_import_outcome"], "passed")
        self.assertEqual(validation["smoke_run_outcome"], "passed")

    def test_a_share_v3_snapshot_dispatches_real_engine_and_report(self) -> None:
        self.domain.submit_command(self._merge_command(self._v3_strategy_source()))
        fixture_path = (
            Path(__file__).parents[3]
            / "fixtures"
            / "market"
            / "m3-a-share-daily.csv"
        )
        body = fixture_path.read_bytes()
        preview = self.domain.preview_data_import(body, fixture_path.name, "csv")
        snapshot_id = "a2a2a2a2-a2a2-42a2-82a2-a2a2a2a2a2a2"
        self.domain.submit_command(
            bind_command(
                command_id="a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1",
                workbench_id="data-import",
            )
        )
        self.domain.submit_command(
            {
                "command_id": "a3a3a3a3-a3a3-43a3-83a3-a3a3a3a3a3a3",
                "schema_version": 1,
                "command_type": "data.snapshot_create",
                "project_id": PROJECT_ID,
                "activity_id": ACTIVITY_ID,
                "session_id": SENDER_SESSION_ID,
                "workbench_id": "data-import",
                "correlation_id": CORRELATION_ID,
                "expected_revision_id": None,
                "variant_id": None,
                "base_revision_id": None,
                "payload": {
                    "snapshot_id": snapshot_id,
                    "source": preview["source"],
                    "source_format": "csv",
                    "file_name": fixture_path.name,
                    "mapping": preview["suggested_mapping"],
                    "market": "a_share_daily",
                    "timezone": "Asia/Shanghai",
                    "price_basis": "raw",
                    "cutoff": "2026-01-08T00:00:00Z",
                    "execution_profile": "a-share-v3",
                },
            }
        )
        self.domain.submit_command(
            bind_command(
                command_id="a8a8a8a8-a8a8-48a8-88a8-a8a8a8a8a8a8",
                workbench_id="canvas",
            )
        )
        snapshot = self.domain.data_snapshot(PROJECT_ID, snapshot_id)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["schema_version"], 3)
        self.assertEqual(snapshot["execution_profile"], "a-share-v3")
        market_input_artifact, _ = self.domain.data_snapshot_market_input(
            PROJECT_ID, snapshot_id
        )
        candidate = self.domain.revision(PROJECT_ID, MERGE_REVISION_ID)
        run_id = "a5a5a5a5-a5a5-45a5-85a5-a5a5a5a5a5a5"
        validation_id = "a6a6a6a6-a6a6-46a6-86a6-a6a6a6a6a6a6"
        command = {
            "command_id": "a7a7a7a7-a7a7-47a7-87a7-a7a7a7a7a7a7",
            "schema_version": 1,
            "command_type": "formal.run_request",
            "project_id": PROJECT_ID,
            "activity_id": ACTIVITY_ID,
            "session_id": SENDER_SESSION_ID,
            "workbench_id": "canvas",
            "correlation_id": CORRELATION_ID,
            "expected_revision_id": MERGE_REVISION_ID,
            "variant_id": VARIANT_ID,
            "base_revision_id": MERGE_REVISION_ID,
            "payload": {
                "run_spec_id": "a4a4a4a4-a4a4-44a4-84a4-a4a4a4a4a4a4",
                "run_id": run_id,
                "validation_id": validation_id,
                "candidate_revision_id": MERGE_REVISION_ID,
                "market_input": self._artifact_ref(market_input_artifact),
                "data_snapshot_id": snapshot_id,
                "data_snapshot_sha256": snapshot["sha256"],
                "strategy_tree_oid": candidate["git_tree_oid"],
                "parameters_sha256": hashlib.sha256(b"{}").hexdigest(),
                "cost_model_sha256": hashlib.sha256(
                    b"oqs-a-share-v3-default-costs"
                ).hexdigest(),
                "environment_lock_sha256": hashlib.sha256(
                    b"oqs-local-environment"
                ).hexdigest(),
                "engine_version": "oqs-quant-engine/0.3.0",
                "price_basis": snapshot["price_basis"],
                "cutoff": snapshot["cutoff"],
                "timezone": snapshot["timezone"],
                "sample_start": snapshot["sample_start"],
                "sample_end": snapshot["sample_end"],
                "random_seed": 0,
                "output_schema_version": 3,
                "gate_policy_version": "a-share-v3",
                "strategy_protocol_version": "oqs-strategy-host/a-share-v3",
                "checkpoint_batch_size": 2,
                "engine_checkpoint_abi": "oqs-quant-engine/checkpoint-v3",
                "review_attestation": {
                    "status": "approved",
                    "candidate_revision_id": MERGE_REVISION_ID,
                    "strategy_tree_oid": candidate["git_tree_oid"],
                    "data_snapshot_sha256": snapshot["sha256"],
                    "parameters_sha256": hashlib.sha256(b"{}").hexdigest(),
                    "cost_model_sha256": hashlib.sha256(
                        b"oqs-a-share-v3-default-costs"
                    ).hexdigest(),
                    "attestation_id": "a9a9a9a9-a9a9-49a9-89a9-a9a9a9a9a9a9",
                    "reviewer_id": "test-user",
                    "reviewed_at": "2026-08-13T00:00:00Z",
                },
            },
        }

        missing_attestation = copy.deepcopy(command)
        del missing_attestation["payload"]["review_attestation"]
        with self.assertRaises(ContractViolation):
            self.domain.submit_command(missing_attestation)
        mismatched_attestation = copy.deepcopy(command)
        mismatched_attestation["payload"]["review_attestation"]["cost_model_sha256"] = hashlib.sha256(
            b"different-costs"
        ).hexdigest()
        with self.assertRaises(ContractViolation):
            self.domain.submit_command(mismatched_attestation)

        queued = self.domain.submit_command(command)
        self.assertEqual(queued["event"]["event_type"], "formal.run_queued")
        with self.domain.database.connect() as connection:
            attestation_row = connection.execute(
                "SELECT status, candidate_revision_id, strategy_tree_oid, data_snapshot_sha256, parameters_sha256, cost_model_sha256, attestation_json FROM review_attestations"
            ).fetchone()
            run_spec_row = connection.execute(
                "SELECT review_attestation_id, review_attestation_sha256, review_attestation_json FROM run_specs WHERE run_spec_id = ?",
                (command["payload"]["run_spec_id"],),
            ).fetchone()
        self.assertEqual(attestation_row["status"], "approved")
        self.assertEqual(
            json.loads(attestation_row["attestation_json"]),
            command["payload"]["review_attestation"] | {
                "reviewer_id": "test-user",
                "reviewed_at": "2026-08-13T00:00:00Z",
            },
        )
        self.assertEqual(
            json.loads(run_spec_row["review_attestation_json"]),
            json.loads(attestation_row["attestation_json"]),
        )
        job = self.domain.run_next_job()
        self.assertEqual(job["status"], "succeeded")
        detail = self.domain.run(PROJECT_ID, run_id)
        self.assertEqual(detail["run"]["status"], "succeeded")
        self.assertEqual(detail["manifest"]["manifest_version"], "a-share-v3")
        self.assertEqual(detail["run_spec"]["execution_profile"], "a-share-v3")
        result = detail["engine_result"]
        self.assertEqual(result["schema_version"], 3)
        self.assertEqual(result["engine_version"], "oqs-quant-engine/0.3.0")
        self.assertEqual(len(result["orders"]), 4)
        self.assertEqual(len(result["fills"]), 4)
        self.assertEqual(
            {position["book"] for position in result["positions"]},
            {"cash_long", "research_short"},
        )
        self.assertEqual(
            detail["artifacts"]["engine_result"]["sha256"],
            detail["run"]["calculation_hash"],
        )
        report = self.domain.run_report(PROJECT_ID, run_id)
        self.assertTrue(report["report"]["reconciliation"]["passed"])

    def test_a_share_v3_strategy_requires_explicit_book_and_compiled_conditions(
        self,
    ) -> None:
        explicit = {
            "intent_kind": "order",
            "intent_id": "long-entry",
            "intent_seq": 1,
            "symbol": "SYNTH.XSHG",
            "book": "cash_long",
            "side": "buy",
            "position_effect": "open",
            "quantity": "100",
            "order_type": "market",
            "known_at": {"session_seq": 0, "phase": "close", "stable_seq": 1},
            "effective_at": {"session_seq": 1, "phase": "open", "stable_seq": 1},
            "limit_price_atoms": None,
            "time_in_force": "day",
            "condition_intent_id": "condition-breakout-1",
        }
        self.assertEqual(_canonicalize_a_share_v3_intents([explicit]), [explicit])

        implicit_book = dict(explicit)
        implicit_book.pop("book")
        self.assertIsNone(_canonicalize_a_share_v3_intents([implicit_book]))
        uncompiled_stop = dict(explicit) | {"stop_price_atoms": "9900"}
        self.assertIsNone(_canonicalize_a_share_v3_intents([uncompiled_stop]))

    def test_same_runspec_rerun_has_a_new_run_identity_and_same_calculation_hash(
        self,
    ) -> None:
        self.domain.submit_command(self._merge_command())
        first_command = self._formal_run_command()
        self.domain.submit_command(first_command)
        self.assertEqual(self.domain.run_next_job()["status"], "succeeded")

        second_command = copy.deepcopy(first_command)
        second_command["command_id"] = "83838383-8383-4383-8383-838383838383"
        second_command["payload"]["run_id"] = SECOND_RUN_ID
        second_command["payload"]["validation_id"] = SECOND_VALIDATION_ID
        self.domain.submit_command(second_command)
        self.assertEqual(self.domain.run_next_job()["status"], "succeeded")

        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            runs = connection.execute(
                """
                SELECT run_id, run_spec_id, calculation_hash
                FROM formal_runs
                ORDER BY run_id
                """
            ).fetchall()
            run_specs = connection.execute("SELECT COUNT(*) FROM run_specs").fetchone()[0]
        self.assertEqual({run[0] for run in runs}, {RUN_ID, SECOND_RUN_ID})
        self.assertEqual({run[1] for run in runs}, {RUN_SPEC_ID})
        self.assertEqual(len({run[2] for run in runs}), 1)
        self.assertEqual(run_specs, 1)

    def test_validation_identity_is_reserved_before_a_second_job_can_run(self) -> None:
        self.domain.submit_command(self._merge_command())
        first_command = self._formal_run_command()
        self.domain.submit_command(first_command)
        self.assertEqual(self.domain.run_next_job()["status"], "succeeded")
        duplicate = copy.deepcopy(first_command)
        duplicate["command_id"] = "86868686-8686-4686-8686-868686868686"
        duplicate["payload"]["run_id"] = SECOND_RUN_ID

        with self.assertRaises(DomainConflict):
            self.domain.submit_command(duplicate)

        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            job = connection.execute(
                "SELECT status FROM jobs WHERE run_id = ?", (SECOND_RUN_ID,)
            ).fetchone()
            receipt = connection.execute(
                "SELECT 1 FROM command_receipts WHERE command_id = ?",
                (duplicate["command_id"],),
            ).fetchone()
        self.assertIsNone(job)
        self.assertIsNone(receipt)

    def test_failed_strategy_gate_retains_candidate_and_cannot_promote(self) -> None:
        self.domain.submit_command(self._merge_command(b"raise RuntimeError('blocked')\n"))
        self.domain.submit_command(self._formal_run_command())

        job = self.domain.run_next_job()

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error_code"], "strategy_import_failed")
        self.assertEqual(self.domain.project_head(PROJECT_ID), ROOT_REVISION_ID)
        variant = next(
            row
            for row in self.domain.variants(PROJECT_ID)
            if row["variant_id"] == VARIANT_ID
        )
        self.assertEqual(variant["head_revision_id"], VARIANT_REVISION_ID)
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            run = connection.execute(
                "SELECT status, manifest_artifact_id FROM formal_runs WHERE run_id = ?",
                (RUN_ID,),
            ).fetchone()
            validation = connection.execute(
                "SELECT outcome, strategy_import_outcome FROM merge_validations WHERE validation_id = ?",
                (VALIDATION_ID,),
            ).fetchone()
        self.assertEqual(run, ("failed", None))
        self.assertEqual(validation, ("failed", "failed"))
        with self.assertRaises(PromotionConflict):
            self.domain.submit_command(self._promote_command())

    def test_strategy_output_is_authoritative_for_the_resolved_engine_input(self) -> None:
        source = (
            b"def on_start():\n    return []\n"
            b"def on_bar(bar):\n    return []\n"
        )
        self.domain.submit_command(self._merge_command(source))
        self.domain.submit_command(self._formal_run_command())

        job = self.domain.run_next_job()

        self.assertEqual(job["status"], "succeeded")
        detail = self.domain.run(PROJECT_ID, RUN_ID)
        self.assertEqual(detail["engine_result"]["orders"], [])
        self.assertEqual(detail["engine_result"]["trades"], [])

    def test_strategy_can_request_a_later_future_open_without_forging_known_at(
        self,
    ) -> None:
        source = (
            b"def on_start():\n"
            b"    return [{\n"
            b"        'intent_id': 'delayed', 'intent_seq': 1,\n"
            b"        'effective_at': {\n"
            b"            'session_seq': 2, 'phase': 'open', 'stable_seq': 7\n"
            b"        }\n"
            b"    }]\n"
            b"def on_bar(bar):\n    return []\n"
        )
        engine_input = b'{"bars":[{"session_seq":1},{"session_seq":2}],"intents":[]}'

        emitted = run_strategy_host(source, engine_input)

        self.assertEqual(emitted[0]["known_at"], {
            "session_seq": 0,
            "phase": "close",
            "stable_seq": 1,
        })
        self.assertEqual(emitted[0]["effective_at"], {
            "session_seq": 2,
            "phase": "open",
            "stable_seq": 7,
        })

    def test_strategy_effective_at_rejects_unknown_contract_fields(self) -> None:
        source = (
            b"def on_start():\n"
            b"    return [{\n"
            b"        'intent_id': 'unknown-field', 'intent_seq': 1,\n"
            b"        'effective_at': {\n"
            b"            'session_seq': 1, 'phase': 'open', 'stable_seq': 1,\n"
            b"            'unexpected': True\n"
            b"        }\n"
            b"    }]\n"
            b"def on_bar(bar):\n    return []\n"
        )
        engine_input = b'{"bars":[{"session_seq":1}],"intents":[]}'

        emitted = run_strategy_host(source, engine_input)

        self.assertIsNone(emitted)

    def test_only_the_exact_passed_validation_can_promote_both_heads(self) -> None:
        self.domain.submit_command(self._merge_command())
        self.domain.submit_command(self._formal_run_command())
        self.assertEqual(self.domain.run_next_job()["status"], "succeeded")

        forged = self._promote_command(
            "79797979-7979-4979-8979-797979797979",
            "80808080-8080-4080-8080-808080808080",
        )
        with self.assertRaises(PromotionConflict):
            self.domain.submit_command(forged)
        receipt = self.domain.submit_command(self._promote_command())

        self.assertEqual(
            receipt["event"]["payload"]["validation_id"], VALIDATION_ID
        )
        self.assertEqual(self.domain.project_head(PROJECT_ID), MERGE_REVISION_ID)
        variant = next(
            row
            for row in self.domain.variants(PROJECT_ID)
            if row["variant_id"] == VARIANT_ID
        )
        self.assertEqual(variant["head_revision_id"], MERGE_REVISION_ID)
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            linked = connection.execute(
                "SELECT validation_id FROM revision_promotion_validations"
            ).fetchone()
            forged_receipt = connection.execute(
                "SELECT 1 FROM command_receipts WHERE command_id = ?",
                (forged["command_id"],),
            ).fetchone()
        self.assertEqual(linked[0], VALIDATION_ID)
        self.assertIsNone(forged_receipt)

    def test_two_validated_candidates_race_and_only_one_cas_promote_wins(self) -> None:
        self.domain.submit_command(self._merge_command())
        self.domain.submit_command(self._formal_run_command())
        self.assertEqual(self.domain.run_next_job()["status"], "succeeded")

        self.domain.submit_command(
            create_variant_command(
                command_id="97979797-9797-4797-8797-979797979797",
                variant_id=RACING_VARIANT_ID,
                base_revision_id=ROOT_REVISION_ID,
            )
        )
        racing_child = b"def on_bar(bar):\n    return []  # racing variant\n"
        self._stage(racing_child)
        self.domain.submit_command(
            create_revision_command(
                command_id="96969696-9696-4696-8696-969696969696",
                revision_id=RACING_VARIANT_REVISION_ID,
                files=[
                    (
                        "strategy.py",
                        racing_child,
                        "acacacac-acac-4cac-8cac-acacacacacac",
                    )
                ],
                variant_id=RACING_VARIANT_ID,
                base_revision_id=ROOT_REVISION_ID,
            )
        )
        racing_merge = copy.deepcopy(self._merge_command())
        racing_merge["command_id"] = "98989898-9898-4898-8898-989898989898"
        racing_merge["variant_id"] = RACING_VARIANT_ID
        racing_merge["base_revision_id"] = RACING_VARIANT_REVISION_ID
        racing_merge["payload"]["candidate_revision_id"] = RACING_MERGE_REVISION_ID
        self.domain.submit_command(racing_merge)

        racing_formal = copy.deepcopy(self._formal_run_command())
        racing_candidate = self.domain.revision(PROJECT_ID, RACING_MERGE_REVISION_ID)
        racing_formal["command_id"] = "99999999-9999-4999-8999-999999999999"
        racing_formal["expected_revision_id"] = RACING_MERGE_REVISION_ID
        racing_formal["variant_id"] = RACING_VARIANT_ID
        racing_formal["base_revision_id"] = RACING_MERGE_REVISION_ID
        racing_formal["payload"]["run_spec_id"] = RACING_RUN_SPEC_ID
        racing_formal["payload"]["run_id"] = RACING_RUN_ID
        racing_formal["payload"]["validation_id"] = RACING_VALIDATION_ID
        racing_formal["payload"]["candidate_revision_id"] = RACING_MERGE_REVISION_ID
        racing_formal["payload"]["strategy_tree_oid"] = racing_candidate["git_tree_oid"]
        self.domain.submit_command(racing_formal)
        self.assertEqual(self.domain.run_next_job()["status"], "succeeded")

        first = self._promote_command()
        second = copy.deepcopy(first)
        second["command_id"] = "abababab-abab-4bab-8bab-abababababab"
        second["variant_id"] = RACING_VARIANT_ID
        second["payload"]["variant_id"] = RACING_VARIANT_ID
        second["payload"]["candidate_revision_id"] = RACING_MERGE_REVISION_ID
        second["payload"]["validation_id"] = RACING_VALIDATION_ID
        release = Event()

        def submit(command: dict[str, object]) -> tuple[str, dict[str, object] | None]:
            release.wait()
            try:
                return "promoted", self.domain.submit_command(command)
            except PromotionConflict:
                return "conflict", None

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(submit, command) for command in (first, second)]
            release.set()
            outcomes = [future.result(timeout=5) for future in futures]

        self.assertEqual(sorted(outcome for outcome, _ in outcomes), ["conflict", "promoted"])
        promoted = next(receipt for outcome, receipt in outcomes if outcome == "promoted")
        promoted_revision_id = promoted["event"]["payload"]["promoted_revision_id"]
        self.assertEqual(self.domain.project_head(PROJECT_ID), promoted_revision_id)
        self.assertIn(
            promoted_revision_id,
            {MERGE_REVISION_ID, RACING_MERGE_REVISION_ID},
        )
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            promoted_events = connection.execute(
                "SELECT COUNT(*) FROM domain_events WHERE event_type = 'workspace.revision_promoted'"
            ).fetchone()[0]
            promotion_receipts = connection.execute(
                "SELECT COUNT(*) FROM command_receipts WHERE command_id IN (?, ?)",
                (first["command_id"], second["command_id"]),
            ).fetchone()[0]
        self.assertEqual(promoted_events, 1)
        self.assertEqual(promotion_receipts, 1)


if __name__ == "__main__":
    unittest.main()
