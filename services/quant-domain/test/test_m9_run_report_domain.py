from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

from quant_domain.contracts import REGISTRY, SCHEMAS
from quant_domain.project_archive import export_project_archive, import_project_archive
from quant_domain.domain import QuantDomain
from test_m1_http import HttpTestCase
from test_m2_session import PROJECT_ID, register_command
import test_m3_formal_runs as _m3


class M9RunReportDomainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _m3.M3FormalRunDomainTest(
            "test_merge_candidate_is_two_parent_immutable_and_moves_no_head"
        )
        self.fixture.setUp()
        self.domain = self.fixture.domain
        self.domain.submit_command(self.fixture._merge_command())
        self.command = self.fixture._formal_run_command()
        self.command["payload"]["checkpoint_batch_size"] = 1
        self.domain.submit_command(self.command)
        with patch("quant_domain.domain.run_strategy_host", return_value=[]):
            completed = self.domain.run_next_job()
        self.assertEqual(completed["status"], "succeeded")

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def test_report_materializes_once_and_remains_part_of_run_and_archive(self) -> None:
        run_id = self.command["payload"]["run_id"]

        first = self.domain.run_report(PROJECT_ID, run_id)
        second = self.domain.run_report(PROJECT_ID, run_id)

        self.assertEqual(first, second)
        self.assertEqual(first["report"]["run"]["run_id"], run_id)
        self.assertTrue(first["report"]["reconciliation"]["passed"])
        errors = list(
            Draft202012Validator(
                SCHEMAS["run-report"],
                registry=REGISTRY,
                format_checker=FormatChecker(),
            ).iter_errors(first)
        )
        self.assertEqual(errors, [], [error.message for error in errors])
        self.assertEqual(
            first["json_artifact"]["media_type"],
            "application/vnd.open-quant-studio.run-report+json",
        )
        self.assertEqual(
            first["html_artifact"]["media_type"],
            "application/vnd.open-quant-studio.run-report+html",
        )
        detail = self.domain.run(PROJECT_ID, run_id)
        self.assertEqual(
            set(detail["artifacts"]),
            {"intent_tape", "engine_result", "manifest", "report_json", "report_html"},
        )
        detail_errors = list(
            Draft202012Validator(
                SCHEMAS["formal-run-read-model"],
                registry=REGISTRY,
                format_checker=FormatChecker(),
            ).iter_errors(detail)
        )
        self.assertEqual(
            detail_errors, [], [error.message for error in detail_errors]
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_path = Path(temporary_directory) / "report.oqs.zip"
            exported = export_project_archive(
                self.domain,
                project_id=PROJECT_ID,
                archive_path=archive_path,
                selected_logs="none",
            )
            self.assertEqual(
                exported.manifest["report_artifact_ids"],
                sorted(
                    [
                        first["json_artifact"]["artifact_id"],
                        first["html_artifact"]["artifact_id"],
                    ]
                ),
            )
            with zipfile.ZipFile(archive_path) as archive:
                members = set(archive.namelist())
                for artifact in (first["json_artifact"], first["html_artifact"]):
                    self.assertIn(
                        f"cas/sha256/{artifact['sha256'][:2]}/{artifact['sha256']}",
                        members,
                    )
            restored = QuantDomain(Path(temporary_directory) / "restored")
            import_project_archive(
                restored, archive_path, expected_project_id=PROJECT_ID
            )
            self.assertEqual(restored.run_report(PROJECT_ID, run_id), first)

    def test_report_is_available_only_for_a_succeeded_run(self) -> None:
        pending_command = self.fixture._formal_run_command()
        pending_command["command_id"] = "8a8a8a8a-8a8a-4a8a-8a8a-8a8a8a8a8a8a"
        pending_command["payload"]["run_id"] = "8b8b8b8b-8b8b-4b8b-8b8b-8b8b8b8b8b8b"
        pending_command["payload"]["run_spec_id"] = "8c8c8c8c-8c8c-4c8c-8c8c-8c8c8c8c8c8c"
        pending_command["payload"]["validation_id"] = "8d8d8d8d-8d8d-4d8d-8d8d-8d8d8d8d8d8d"
        self.domain.submit_command(pending_command)

        self.assertIsNone(
            self.domain.run_report(PROJECT_ID, pending_command["payload"]["run_id"])
        )


class M9RunReportHttpTest(HttpTestCase):
    def test_report_endpoint_materializes_json_and_html_artifacts(self) -> None:
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

        status, _, body = self.request(
            "GET", f"/v1/projects/{PROJECT_ID}/runs/{_m3.RUN_ID}/report"
        )

        self.assertEqual(status, 200, body)
        read_model = json.loads(body)
        self.assertEqual(read_model["report"]["run"]["run_id"], _m3.RUN_ID)
        self.assertTrue(read_model["report"]["reconciliation"]["passed"])
        for artifact_name in ("json_artifact", "html_artifact"):
            artifact = read_model[artifact_name]
            artifact_status, headers, artifact_body = self.request(
                "GET",
                f"/v1/projects/{PROJECT_ID}/artifacts/{artifact['artifact_id']}/content",
            )
            self.assertEqual(artifact_status, 200, artifact_body)
            self.assertEqual(headers["content-type"], artifact["media_type"])
            self.assertEqual(len(artifact_body), artifact["byte_size"])


if __name__ == "__main__":
    unittest.main()
