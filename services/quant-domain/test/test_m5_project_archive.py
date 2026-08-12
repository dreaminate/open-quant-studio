from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from quant_domain.domain import QuantDomain
from quant_domain.project_archive import export_project_archive, import_project_archive
from test_m1_domain import context_capture_command
from test_m1_http import HttpTestCase
from test_m2_session import (
    ACTIVITY_ID,
    CORRELATION_ID,
    OTHER_ACTIVITY_ID,
    OTHER_PROJECT_ID,
    PROJECT_ID,
    SENDER_SESSION_ID,
    register_command,
)
import test_m3_formal_runs as _m3


class ProjectArchiveRoundTripTest(unittest.TestCase):
    """Normal one-project archive exports and restores the durable research graph."""

    def setUp(self) -> None:
        self.fixture = _m3.M3FormalRunDomainTest(
            "test_merge_candidate_is_two_parent_immutable_and_moves_no_head"
        )
        self.fixture.setUp()
        self.domain = self.fixture.domain
        self.domain.submit_command(self.fixture._merge_command())
        command = self.fixture._formal_run_command()
        self.domain.submit_command(command)
        with patch("quant_domain.domain.run_strategy_host", return_value=[]):
            completed = self.domain.run_next_job()
        self.assertEqual(completed["status"], "succeeded")
        self.other_project_blob = b"normal second project context\n"
        self.domain.store_blob(
            hashlib.sha256(self.other_project_blob).hexdigest(), self.other_project_blob
        )
        other_project_command = context_capture_command(
            command_id="c1c1c1c1-c1c1-41c1-81c1-c1c1c1c1c1c1",
            context_item_id="b1b1b1b1-b1b1-41b1-81b1-b1b1b1b1b1b1",
            artifact_id="d1d1d1d1-d1d1-41d1-81d1-d1d1d1d1d1d1",
            blob=self.other_project_blob,
        )
        other_project_command["project_id"] = OTHER_PROJECT_ID
        other_project_command["activity_id"] = OTHER_ACTIVITY_ID
        self.domain.submit_command(other_project_command)
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tempdir.cleanup()
        self.fixture.tearDown()

    def test_export_then_import_preserves_project_git_runs_and_artifacts(self) -> None:
        archive_path = Path(self.tempdir.name) / "project.oqs.zip"
        exported = export_project_archive(
            self.domain,
            project_id=PROJECT_ID,
            archive_path=archive_path,
            selected_logs="full",
        )
        repeated_archive_path = Path(self.tempdir.name) / "project-repeat.oqs.zip"
        repeated = export_project_archive(
            self.domain,
            project_id=PROJECT_ID,
            archive_path=repeated_archive_path,
            selected_logs="full",
        )

        self.assertTrue(archive_path.is_file())
        self.assertEqual(archive_path.read_bytes(), repeated_archive_path.read_bytes())
        self.assertEqual(exported.manifest, repeated.manifest)
        self.assertEqual(exported.manifest["project_id"], PROJECT_ID)
        self.assertEqual(exported.manifest["run_ids"], [_m3.RUN_ID])
        self.assertEqual(exported.manifest["selected_logs"], "full")
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            self.assertIn("manifest.json", names)
            self.assertIn("data/project.sqlite", names)
            self.assertIn("git/project.bundle", names)
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest, exported.manifest)
            strategy = self._strategy_artifact(self.domain)
            strategy_member = f"cas/sha256/{strategy['sha256'][:2]}/{strategy['sha256']}"
            self.assertIn(strategy_member, names)
            self.assertEqual(archive.read(strategy_member), self.domain.blob_path(strategy["sha256"]).read_bytes())
            other_sha256 = hashlib.sha256(self.other_project_blob).hexdigest()
            self.assertNotIn(f"cas/sha256/{other_sha256[:2]}/{other_sha256}", names)

        target_root = Path(self.tempdir.name) / "imported"
        target = QuantDomain(target_root)
        imported = import_project_archive(
            target, archive_path, expected_project_id=PROJECT_ID
        )

        self.assertEqual(imported.restored_project_id, PROJECT_ID)
        self.assertEqual(imported.run_count, 1)
        self.assertGreater(imported.artifact_count, 0)
        self.assertEqual(imported.git_ref_count, len(exported.manifest["git"]["refs"]))
        self.assertEqual(
            target.projects(),
            [project for project in self.domain.projects() if project["project_id"] == PROJECT_ID],
        )
        self.assertEqual(
            target.revision(PROJECT_ID, _m3.MERGE_REVISION_ID),
            self.domain.revision(PROJECT_ID, _m3.MERGE_REVISION_ID),
        )
        self.assertEqual(
            target.run(PROJECT_ID, _m3.RUN_ID)["run"]["calculation_hash"],
            self.domain.run(PROJECT_ID, _m3.RUN_ID)["run"]["calculation_hash"],
        )
        restored_strategy = self._strategy_artifact(target)
        self.assertEqual(restored_strategy["artifact_id"], strategy["artifact_id"])
        restored_body = target.blob_path(restored_strategy["sha256"]).read_bytes()
        self.assertEqual(hashlib.sha256(restored_body).hexdigest(), restored_strategy["sha256"])

    def test_typed_import_command_restores_an_empty_domain_and_replays(self) -> None:
        archive_path = Path(self.tempdir.name) / "command-import.oqs.zip"
        export_project_archive(
            self.domain,
            project_id=PROJECT_ID,
            archive_path=archive_path,
            selected_logs="warn_error",
        )
        archive_body = archive_path.read_bytes()
        archive_sha256 = hashlib.sha256(archive_body).hexdigest()
        target = QuantDomain(Path(self.tempdir.name) / "command-target")
        target.store_blob(archive_sha256, archive_body)
        command = {
            "command_id": "e1e1e1e1-e1e1-41e1-81e1-e1e1e1e1e1e1",
            "schema_version": 1,
            "command_type": "project.archive_import",
            "project_id": PROJECT_ID,
            "activity_id": ACTIVITY_ID,
            "session_id": SENDER_SESSION_ID,
            "workbench_id": "canvas",
            "correlation_id": CORRELATION_ID,
            "expected_revision_id": None,
            "variant_id": None,
            "base_revision_id": None,
            "payload": {
                "expected_project_id": PROJECT_ID,
                "archive": {
                    "artifact_id": "f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1",
                    "sha256": archive_sha256,
                    "media_type": "application/vnd.open-quant-studio.project-archive+zip",
                    "byte_size": len(archive_body),
                    "storage_uri": f"cas://sha256/{archive_sha256}",
                    "producing_revision_id": None,
                    "producing_run_id": None,
                    "provenance": {
                        "origin_kind": "user_upload",
                        "source_ref": "a2a2a2a2-a2a2-42a2-82a2-a2a2a2a2a2a2",
                    },
                },
            },
        }

        accepted = target.submit_command(command)
        replayed = target.submit_command(command)

        self.assertEqual(accepted["event"]["event_type"], "project.archive_imported")
        self.assertEqual(accepted["event"]["payload"]["restored_project_id"], PROJECT_ID)
        self.assertEqual(accepted["event"]["payload"]["run_count"], 1)
        self.assertEqual(replayed["disposition"], "replayed")
        self.assertEqual(
            target.run(PROJECT_ID, _m3.RUN_ID)["run"]["calculation_hash"],
            self.domain.run(PROJECT_ID, _m3.RUN_ID)["run"]["calculation_hash"],
        )

    def test_importing_the_same_archive_verifies_an_existing_project(self) -> None:
        archive_path = Path(self.tempdir.name) / "same-project.oqs.zip"
        exported = export_project_archive(
            self.domain,
            project_id=PROJECT_ID,
            archive_path=archive_path,
            selected_logs="full",
        )
        target = QuantDomain(Path(self.tempdir.name) / "same-project-target")

        first = import_project_archive(
            target,
            archive_path,
            expected_project_id=PROJECT_ID,
        )
        second = import_project_archive(
            target,
            archive_path,
            expected_project_id=PROJECT_ID,
        )

        self.assertEqual(first, second)
        self.assertEqual(second.archive_sha256, exported.archive_sha256)
        self.assertEqual(
            target.run(PROJECT_ID, _m3.RUN_ID)["run"]["calculation_hash"],
            self.domain.run(PROJECT_ID, _m3.RUN_ID)["run"]["calculation_hash"],
        )

    @staticmethod
    def _strategy_artifact(domain: QuantDomain) -> sqlite3.Row:
        with domain.database.connect() as connection:
            row = connection.execute(
                """
                SELECT a.*
                FROM revision_files AS f
                JOIN artifacts AS a ON a.artifact_id = f.artifact_id
                WHERE f.project_id = ? AND f.path = 'strategy.py'
                ORDER BY f.revision_id DESC
                LIMIT 1
                """,
                (PROJECT_ID,),
            ).fetchone()
        assert row is not None
        return row


class ProjectArchiveHttpTest(HttpTestCase):
    def test_export_endpoint_returns_a_reimportable_project_archive(self) -> None:
        scenario = _m3.M3FormalRunDomainTest(
            "test_merge_candidate_is_two_parent_immutable_and_moves_no_head"
        )
        scenario.data_root = self.data_root
        scenario.domain = QuantDomain(self.data_root)
        scenario.domain.submit_command(register_command())
        scenario._create_variant_revision()
        scenario.domain.submit_command(scenario._merge_command())
        scenario.domain.submit_command(scenario._formal_run_command())
        with patch("quant_domain.domain.run_strategy_host", return_value=[]):
            self.assertEqual(scenario.domain.run_next_job()["status"], "succeeded")

        status, headers, body = self.request(
            "GET",
            f"/v1/projects/{PROJECT_ID}/archive?selected_logs=none",
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(
            headers["content-type"],
            "application/vnd.open-quant-studio.project-archive+zip",
        )
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["project_id"], PROJECT_ID)
        self.assertEqual(manifest["selected_logs"], "none")


if __name__ == "__main__":
    unittest.main()
