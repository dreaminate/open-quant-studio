from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import test_m3_formal_runs as formal_run_scenario
from quant_domain.domain import QuantDomain
from quant_domain.project_archive import export_project_archive, import_project_archive
from test_m1_http import HttpTestCase
from test_m2_session import (
    ACTIVITY_ID,
    CORRELATION_ID,
    PROJECT_ID,
    SENDER_SESSION_ID,
    bind_command,
    register_command,
)


FIXTURE_DIRECTORY = Path(__file__).resolve().parents[3] / "fixtures" / "market"
A_SHARE_SNAPSHOT_ID = "a7a7a7a7-a7a7-47a7-87a7-a7a7a7a7a7a7"
CRYPTO_SNAPSHOT_ID = "b7b7b7b7-b7b7-47b7-87b7-b7b7b7b7b7b7"
A_SHARE_COMMAND_ID = "c7c7c7c7-c7c7-47c7-87c7-c7c7c7c7c7c7"
CRYPTO_COMMAND_ID = "d7d7d7d7-d7d7-47d7-87d7-d7d7d7d7d7d7"
PORTFOLIO_SNAPSHOT_ID = "a8a8a8a8-a8a8-48a8-88a8-a8a8a8a8a8a8"
PORTFOLIO_COMMAND_ID = "b8b8b8b8-b8b8-48b8-88b8-b8b8b8b8b8b8"
NO_OP_STRATEGY = b"def on_start():\n    return []\n\ndef on_bar(bar):\n    return []\n"


def snapshot_command(
    *,
    command_id: str,
    snapshot_id: str,
    source: dict[str, object],
    source_format: str,
    file_name: str,
    mapping: dict[str, str],
    market: str,
    timezone: str,
    cutoff: str,
) -> dict[str, object]:
    return {
        "command_id": command_id,
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
            "source": source,
            "source_format": source_format,
            "file_name": file_name,
            "mapping": mapping,
            "market": market,
            "timezone": timezone,
            "price_basis": "raw",
            "cutoff": cutoff,
        },
    }


def artifact_ref(artifact: dict[str, object]) -> dict[str, object]:
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


class M7DataSnapshotDomainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = formal_run_scenario.M3FormalRunDomainTest(
            "test_merge_candidate_is_two_parent_immutable_and_moves_no_head"
        )
        self.scenario.setUp()
        self.domain = self.scenario.domain
        self.domain.submit_command(self.scenario._merge_command(NO_OP_STRATEGY))
        self.domain.submit_command(
            bind_command(
                command_id="e7e7e7e7-e7e7-47e7-87e7-e7e7e7e7e7e7",
                workbench_id="data-import",
            )
        )

    def tearDown(self) -> None:
        self.scenario.tearDown()

    def create_snapshot(
        self,
        *,
        file_name: str,
        source_format: str,
        market: str,
        timezone: str,
        cutoff: str,
        snapshot_id: str,
        command_id: str,
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        body = (FIXTURE_DIRECTORY / file_name).read_bytes()
        preview = self.domain.preview_data_import(body, file_name, source_format)
        source = preview["source"]
        self.assertIsInstance(source, dict)
        command = snapshot_command(
            command_id=command_id,
            snapshot_id=snapshot_id,
            source=source,
            source_format=source_format,
            file_name=file_name,
            mapping=preview["suggested_mapping"],
            market=market,
            timezone=timezone,
            cutoff=cutoff,
        )
        receipt = self.domain.submit_command(command)
        detail = self.domain.data_snapshot(PROJECT_ID, snapshot_id)
        self.assertIsNotNone(detail)
        return command, receipt, detail

    def test_snapshots_are_idempotent_readable_and_archive_round_trip(self) -> None:
        a_share_command, accepted, a_share = self.create_snapshot(
            file_name="m7-a-share-daily.csv",
            source_format="csv",
            market="a_share_daily",
            timezone="Asia/Shanghai",
            cutoff="2026-01-14T00:00:00Z",
            snapshot_id=A_SHARE_SNAPSHOT_ID,
            command_id=A_SHARE_COMMAND_ID,
        )
        replayed = self.domain.submit_command(copy.deepcopy(a_share_command))
        crypto_command, crypto_accepted, crypto = self.create_snapshot(
            file_name="m7-crypto-linear.csv",
            source_format="csv",
            market="crypto_linear_perp",
            timezone="UTC",
            cutoff="2026-01-02T08:00:00Z",
            snapshot_id=CRYPTO_SNAPSHOT_ID,
            command_id=CRYPTO_COMMAND_ID,
        )

        self.assertEqual(accepted["disposition"], "accepted")
        self.assertEqual(replayed["disposition"], "replayed")
        self.assertEqual(replayed["event"], accepted["event"])
        self.assertEqual(accepted["event"]["event_type"], "data.snapshot_created")
        self.assertEqual(accepted["event"]["payload"]["snapshot_id"], A_SHARE_SNAPSHOT_ID)
        self.assertEqual(a_share["row_count"], 8)
        self.assertEqual(a_share["symbol"], "SYNTH.XSHG")
        self.assertEqual(a_share["sample_start"], "2026-01-02T07:00:00Z")
        self.assertEqual(a_share["sample_end"], "2026-01-13T07:00:00Z")
        self.assertEqual(a_share["sha256"], a_share["normalized_sha256"])
        self.assertEqual(crypto_accepted["event"]["payload"]["market"], "crypto_linear_perp")
        self.assertEqual(crypto["symbol"], "BTCUSDT.PERP")
        self.assertEqual(crypto["row_count"], 8)
        self.assertEqual(
            [snapshot["snapshot_id"] for snapshot in self.domain.data_snapshots(PROJECT_ID)],
            [A_SHARE_SNAPSHOT_ID, CRYPTO_SNAPSHOT_ID],
        )

        content = self.domain.data_snapshot_market_input(PROJECT_ID, A_SHARE_SNAPSHOT_ID)
        self.assertIsNotNone(content)
        artifact, market_input_body = content
        market_input = json.loads(market_input_body)
        self.assertEqual(artifact["artifact_id"], a_share["market_input_artifact_id"])
        self.assertEqual(market_input["account"]["model"], "a_share_cash")
        self.assertEqual(market_input["bars"][0]["session_seq"], 1)
        self.assertEqual(market_input["funding_events"], [])
        self.assertEqual(market_input["intents"], [])

        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "m7.oqs.zip"
            export_project_archive(
                self.domain,
                project_id=PROJECT_ID,
                archive_path=archive_path,
            )
            restored = QuantDomain(Path(temporary) / "restored")
            import_project_archive(
                restored,
                archive_path,
                expected_project_id=PROJECT_ID,
            )
            self.assertEqual(
                restored.data_snapshot(PROJECT_ID, A_SHARE_SNAPSHOT_ID), a_share
            )
            self.assertEqual(
                restored.data_snapshot(PROJECT_ID, CRYPTO_SNAPSHOT_ID), crypto
            )

    def test_snapshot_market_input_completes_a_no_op_formal_run(self) -> None:
        _, _, snapshot = self.create_snapshot(
            file_name="m7-a-share-daily.csv",
            source_format="csv",
            market="a_share_daily",
            timezone="Asia/Shanghai",
            cutoff="2026-01-14T00:00:00Z",
            snapshot_id=A_SHARE_SNAPSHOT_ID,
            command_id=A_SHARE_COMMAND_ID,
        )
        content = self.domain.data_snapshot_market_input(PROJECT_ID, A_SHARE_SNAPSHOT_ID)
        self.assertIsNotNone(content)
        artifact, market_input_body = content
        self.assertEqual(hashlib.sha256(market_input_body).hexdigest(), artifact["sha256"])
        self.domain.submit_command(
            bind_command(
                command_id="f7f7f7f7-f7f7-47f7-87f7-f7f7f7f7f7f7",
                workbench_id="canvas",
            )
        )
        command = self.scenario._formal_run_command()
        payload = command["payload"]
        market_input = artifact_ref(artifact)
        market_input["artifact_id"] = "f9f9f9f9-f9f9-49f9-89f9-f9f9f9f9f9f9"
        market_input["provenance"]["source_ref"] = snapshot[
            "market_input_artifact_id"
        ]
        payload["market_input"] = market_input
        payload["data_snapshot_id"] = snapshot["snapshot_id"]
        payload["data_snapshot_sha256"] = snapshot["sha256"]
        payload["price_basis"] = snapshot["price_basis"]
        payload["cutoff"] = snapshot["cutoff"]
        payload["timezone"] = snapshot["timezone"]
        payload["sample_start"] = snapshot["sample_start"]
        payload["sample_end"] = snapshot["sample_end"]

        queued = self.domain.submit_command(command)
        completed = self.domain.run_next_job()
        rerun_command = copy.deepcopy(command)
        rerun_command["command_id"] = "f8f8f8f8-f8f8-48f8-88f8-f8f8f8f8f8f8"
        rerun_command["payload"]["run_id"] = formal_run_scenario.SECOND_RUN_ID
        rerun_command["payload"]["validation_id"] = formal_run_scenario.SECOND_VALIDATION_ID
        rerun_queued = self.domain.submit_command(rerun_command)
        rerun_completed = self.domain.run_next_job()

        self.assertEqual(queued["event"]["event_type"], "formal.run_queued")
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(
            self.domain.run(PROJECT_ID, formal_run_scenario.RUN_ID)["run_spec"][
                "market_input_artifact_id"
            ],
            snapshot["market_input_artifact_id"],
        )
        self.assertEqual(rerun_queued["event"]["event_type"], "formal.run_queued")
        self.assertEqual(rerun_completed["status"], "succeeded")
        self.assertEqual(
            self.domain.run(PROJECT_ID, formal_run_scenario.RUN_ID)["run"][
                "calculation_hash"
            ],
            self.domain.run(PROJECT_ID, formal_run_scenario.SECOND_RUN_ID)["run"][
                "calculation_hash"
            ],
        )

    def test_multi_symbol_snapshot_exposes_portfolio_sessions_and_metadata(self) -> None:
        _, accepted, snapshot = self.create_snapshot(
            file_name="m8-a-share-rotation.csv",
            source_format="csv",
            market="a_share_daily",
            timezone="Asia/Shanghai",
            cutoff="2026-02-10T00:00:00Z",
            snapshot_id=PORTFOLIO_SNAPSHOT_ID,
            command_id=PORTFOLIO_COMMAND_ID,
        )

        self.assertEqual(accepted["event"]["payload"]["schema_version"], 2)
        self.assertIsNone(snapshot["symbol"])
        self.assertEqual(snapshot["symbols"], ["AAA.XSHG", "BBB.XSHG", "CCC.XSHG"])
        self.assertEqual(snapshot["row_count"], 18)
        self.assertEqual(snapshot["session_count"], 6)
        content = self.domain.data_snapshot_market_input(
            PROJECT_ID, PORTFOLIO_SNAPSHOT_ID
        )
        self.assertIsNotNone(content)
        _, body = content
        market_input = json.loads(body)
        self.assertEqual(market_input["schema_version"], 2)
        self.assertEqual(
            market_input["account"]["symbols"],
            ["AAA.XSHG", "BBB.XSHG", "CCC.XSHG"],
        )
        self.assertEqual(len(market_input["sessions"]), 6)


class M7DataSnapshotHttpTest(HttpTestCase):
    def post_command(self, command: dict[str, object]) -> tuple[int, dict[str, object]]:
        status, _, body = self.request(
            "POST",
            "/v1/commands",
            body=json.dumps(command).encode(),
            headers={"Content-Type": "application/json"},
        )
        return status, json.loads(body)

    def test_http_preview_snapshot_list_detail_and_market_input(self) -> None:
        status, registered = self.post_command(register_command())
        self.assertEqual(status, 201, registered)
        status, bound = self.post_command(
            bind_command(
                command_id="11111111-1111-4111-8111-111111111117",
                workbench_id="data-import",
            )
        )
        self.assertEqual(status, 201, bound)
        body = (FIXTURE_DIRECTORY / "m7-a-share-daily.csv").read_bytes()
        target = (
            f"/v1/projects/{PROJECT_ID}/data-imports/preview"
            "?file_name=m7-a-share-daily.csv&source_format=csv"
        )
        status, _, response_body = self.request("POST", target, body=body)
        self.assertEqual(status, 200, response_body)
        preview = json.loads(response_body)
        source = preview["source"]
        command = snapshot_command(
            command_id=A_SHARE_COMMAND_ID,
            snapshot_id=A_SHARE_SNAPSHOT_ID,
            source=source,
            source_format="csv",
            file_name="m7-a-share-daily.csv",
            mapping=preview["suggested_mapping"],
            market="a_share_daily",
            timezone="Asia/Shanghai",
            cutoff="2026-01-14T00:00:00Z",
        )
        status, accepted = self.post_command(command)
        self.assertEqual(status, 201, accepted)
        status, replayed = self.post_command(command)
        self.assertEqual(status, 200, replayed)
        self.assertEqual(replayed["disposition"], "replayed")

        status, _, response_body = self.request(
            "GET", f"/v1/projects/{PROJECT_ID}/data-snapshots"
        )
        self.assertEqual(status, 200, response_body)
        snapshots = json.loads(response_body)["snapshots"]
        self.assertEqual([snapshot["snapshot_id"] for snapshot in snapshots], [A_SHARE_SNAPSHOT_ID])
        status, _, response_body = self.request(
            "GET", f"/v1/projects/{PROJECT_ID}/data-snapshots/{A_SHARE_SNAPSHOT_ID}"
        )
        self.assertEqual(status, 200, response_body)
        detail = json.loads(response_body)
        self.assertEqual(detail, snapshots[0])
        status, headers, response_body = self.request(
            "GET",
            f"/v1/projects/{PROJECT_ID}/data-snapshots/{A_SHARE_SNAPSHOT_ID}/market-input",
        )
        self.assertEqual(status, 200, response_body)
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(json.loads(response_body)["bars"][0]["session_seq"], 1)

    def test_http_lists_and_previews_configured_local_imports(self) -> None:
        imports = self.data_root / "imports"
        imports.mkdir()
        for file_name in ("m7-a-share-daily.csv", "m7-crypto-linear.csv"):
            shutil.copy(FIXTURE_DIRECTORY / file_name, imports / file_name)

        status, registered = self.post_command(register_command())
        self.assertEqual(status, 201, registered)
        status, bound = self.post_command(
            bind_command(
                command_id="12121212-1212-4212-8212-121212121217",
                workbench_id="data-import",
            )
        )
        self.assertEqual(status, 201, bound)

        status, _, response_body = self.request(
            "GET", f"/v1/projects/{PROJECT_ID}/data-imports/local-files"
        )
        self.assertEqual(status, 200, response_body)
        files = json.loads(response_body)["files"]
        self.assertEqual(
            [entry["file_name"] for entry in files],
            ["m7-a-share-daily.csv", "m7-crypto-linear.csv"],
        )
        self.assertEqual([entry["source_format"] for entry in files], ["csv", "csv"])
        status, _, response_body = self.request(
            "POST",
            f"/v1/projects/{PROJECT_ID}/data-imports/local-preview",
            body=json.dumps({"file_name": "m7-crypto-linear.csv"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200, response_body)
        preview = json.loads(response_body)
        self.assertEqual(preview["source_format"], "csv")
        self.assertEqual(preview["suggested_mapping"]["timestamp"], "datetime")
        self.assertEqual(preview["total_rows"], 8)
        status, accepted = self.post_command(
            snapshot_command(
                command_id=CRYPTO_COMMAND_ID,
                snapshot_id=CRYPTO_SNAPSHOT_ID,
                source=preview["source"],
                source_format="csv",
                file_name="m7-crypto-linear.csv",
                mapping=preview["suggested_mapping"],
                market="crypto_linear_perp",
                timezone="UTC",
                cutoff="2026-01-02T08:00:00Z",
            )
        )
        self.assertEqual(status, 201, accepted)
        self.assertEqual(accepted["event"]["payload"]["snapshot_id"], CRYPTO_SNAPSHOT_ID)


if __name__ == "__main__":
    unittest.main()
