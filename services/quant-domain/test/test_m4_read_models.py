from __future__ import annotations

import hashlib
import json
from urllib.parse import urlencode

import test_m3_formal_runs as formal_run_scenario
from quant_domain.domain import QuantDomain
from test_m1_http import HttpTestCase
from test_m2_session import ACTIVITY_ID, PROJECT_ID, register_command
from test_m3_revisions import ROOT_REVISION_ID, create_revision_command


SOURCE_ARTIFACT_ID = "17171717-1717-4717-8717-171717171717"
SOURCE_BODY = b"def on_bar(bar):\n    return []\n"
RUN_ID = formal_run_scenario.RUN_ID
RUN_SPEC_ID = formal_run_scenario.RUN_SPEC_ID
VALIDATION_ID = formal_run_scenario.VALIDATION_ID


class M4ReadModelsHttpTest(HttpTestCase):
    def post_command(self, command: dict[str, object]) -> tuple[int, bytes]:
        status, _, body = self.request(
            "POST",
            "/v1/commands",
            body=json.dumps(command).encode(),
            headers={"Content-Type": "application/json"},
        )
        return status, body

    def stage_blob(self, body: bytes) -> str:
        digest = hashlib.sha256(body).hexdigest()
        status, _, response_body = self.request(
            "PUT", f"/v1/artifact-blobs/{digest}", body=body
        )
        self.assertEqual(status, 201, response_body)
        return digest

    def create_project_revision(self) -> str:
        status, body = self.post_command(register_command())
        self.assertEqual(status, 201, body)
        digest = self.stage_blob(SOURCE_BODY)
        status, body = self.post_command(
            create_revision_command(
                command_id="18181818-1818-4818-8818-181818181818",
                revision_id=ROOT_REVISION_ID,
                files=[("strategy.py", SOURCE_BODY, SOURCE_ARTIFACT_ID)],
            )
        )
        self.assertEqual(status, 201, body)
        return digest

    def create_completed_formal_run(self) -> QuantDomain:
        scenario = formal_run_scenario.M3FormalRunDomainTest(
            "test_formal_run_persists_a_hash_bound_manifest_without_recalculation"
        )
        scenario.data_root = self.data_root
        scenario.domain = QuantDomain(self.data_root)
        scenario.domain.submit_command(register_command())
        scenario._create_variant_revision()
        scenario.domain.submit_command(scenario._merge_command())
        scenario.domain.submit_command(scenario._formal_run_command())

        status, _, body = self.request(
            "GET",
            f"/v1/projects/{PROJECT_ID}/runs?"
            + urlencode({"activity_id": ACTIVITY_ID}),
        )
        self.assertEqual(status, 200, body)
        pending_runs = json.loads(body)["runs"]
        self.assertEqual(len(pending_runs), 1)
        self.assertEqual(pending_runs[0]["run_id"], RUN_ID)
        self.assertEqual(pending_runs[0]["status"], "pending")
        self.assertIsNone(pending_runs[0]["engine_result_artifact_id"])
        self.assertIsNone(pending_runs[0]["manifest_artifact_id"])

        job = scenario.domain.run_next_job()
        self.assertEqual(job["status"], "succeeded")
        return scenario.domain

    def create_failed_formal_run(self) -> QuantDomain:
        scenario = formal_run_scenario.M3FormalRunDomainTest(
            "test_failed_strategy_gate_retains_candidate_and_cannot_promote"
        )
        scenario.data_root = self.data_root
        scenario.domain = QuantDomain(self.data_root)
        scenario.domain.submit_command(register_command())
        scenario._create_variant_revision()
        scenario.domain.submit_command(
            scenario._merge_command(b"raise RuntimeError('blocked')\n")
        )
        scenario.domain.submit_command(scenario._formal_run_command())
        job = scenario.domain.run_next_job()
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error_code"], "strategy_import_failed")
        return scenario.domain

    def test_project_and_activity_lists_are_stable_read_models(self) -> None:
        status, body = self.post_command(register_command())
        self.assertEqual(status, 201, body)

        status, _, body = self.request("GET", "/v1/projects")
        self.assertEqual(status, 200, body)
        projects = json.loads(body)["projects"]
        self.assertEqual([project["project_id"] for project in projects], [PROJECT_ID])
        self.assertRegex(projects[0]["created_at"], r"Z$")

        status, _, body = self.request(
            "GET", f"/v1/projects/{PROJECT_ID}/activities"
        )
        self.assertEqual(status, 200, body)
        activities = json.loads(body)["activities"]
        self.assertEqual(
            activities,
            [
                {
                    "activity_id": ACTIVITY_ID,
                    "project_id": PROJECT_ID,
                    "created_at": activities[0]["created_at"],
                }
            ],
        )
        self.assertRegex(activities[0]["created_at"], r"Z$")

    def test_project_artifact_metadata_and_content_are_readable(self) -> None:
        digest = self.create_project_revision()

        status, _, body = self.request(
            "GET",
            f"/v1/projects/{PROJECT_ID}/artifacts/{SOURCE_ARTIFACT_ID}",
        )
        self.assertEqual(status, 200, body)
        artifact = json.loads(body)
        self.assertEqual(artifact["artifact_id"], SOURCE_ARTIFACT_ID)
        self.assertEqual(artifact["project_id"], PROJECT_ID)
        self.assertEqual(artifact["sha256"], digest)
        self.assertEqual(artifact["byte_size"], len(SOURCE_BODY))
        self.assertEqual(artifact["media_type"], "text/plain")
        self.assertEqual(
            artifact["revision_paths"],
            [{"revision_id": ROOT_REVISION_ID, "path": "strategy.py"}],
        )

        status, headers, body = self.request(
            "GET",
            f"/v1/projects/{PROJECT_ID}/artifacts/{SOURCE_ARTIFACT_ID}/content",
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(headers["content-type"], "text/plain; charset=utf-8")
        self.assertEqual(body, SOURCE_BODY)


    def test_completed_formal_run_list_and_detail_are_read_only_artifact_views(self) -> None:
        domain = self.create_completed_formal_run()
        with domain.database.connect() as connection:
            before = connection.execute(
                "SELECT (SELECT count(*) FROM domain_events), "
                "(SELECT count(*) FROM jobs)"
            ).fetchone()

        status, _, body = self.request(
            "GET",
            f"/v1/projects/{PROJECT_ID}/runs?"
            + urlencode({"activity_id": ACTIVITY_ID}),
        )
        self.assertEqual(status, 200, body)
        runs = json.loads(body)["runs"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_id"], RUN_ID)
        self.assertEqual(runs[0]["run_spec_id"], RUN_SPEC_ID)
        self.assertEqual(runs[0]["status"], "succeeded")
        self.assertEqual(runs[0]["validation_id"], VALIDATION_ID)

        status, _, body = self.request(
            "GET", f"/v1/projects/{PROJECT_ID}/runs/{RUN_ID}"
        )
        self.assertEqual(status, 200, body)
        detail = json.loads(body)
        self.assertEqual(detail["run"]["run_id"], RUN_ID)
        self.assertEqual(detail["run_spec"]["run_spec_id"], RUN_SPEC_ID)
        self.assertEqual(detail["validation"]["validation_id"], VALIDATION_ID)
        self.assertEqual(
            detail["validation"]["gates"],
            {
                "contract": "passed",
                "strategy_import": "passed",
                "smoke_run": "passed",
            },
        )
        self.assertEqual(
            set(detail["artifacts"]), {"intent_tape", "engine_result", "manifest"}
        )
        self.assertEqual(detail["manifest"]["run_id"], RUN_ID)
        self.assertEqual(
            detail["manifest"]["engine_result"]["sha256"],
            detail["run"]["calculation_hash"],
        )
        self.assertEqual(
            detail["engine_result"]["metrics"]["ending_equity_atoms"], "1025534"
        )
        self.assertEqual(len(detail["engine_result"]["orders"]), 4)
        self.assertEqual(len(detail["engine_result"]["trades"]), 4)
        self.assertEqual(len(detail["engine_result"]["positions"]), 4)
        self.assertEqual(len(detail["engine_result"]["cash_ledger"]), 4)
        self.assertEqual(len(detail["engine_result"]["equity_curve"]), 4)
        self.assertEqual(len(detail["engine_result"]["drawdown_curve"]), 4)
        self.assertEqual(len(detail["intent_tape"]), 4)

        with domain.database.connect() as connection:
            after = connection.execute(
                "SELECT (SELECT count(*) FROM domain_events), "
                "(SELECT count(*) FROM jobs)"
            ).fetchone()
        self.assertEqual(tuple(after), tuple(before))

    def test_failed_formal_run_detail_has_no_result_artifacts(self) -> None:
        self.create_failed_formal_run()

        status, _, body = self.request(
            "GET", f"/v1/projects/{PROJECT_ID}/runs/{RUN_ID}"
        )
        self.assertEqual(status, 200, body)
        detail = json.loads(body)
        self.assertEqual(detail["run"]["status"], "failed")
        self.assertEqual(detail["run"]["error_code"], "strategy_import_failed")
        self.assertEqual(detail["run_spec"]["run_spec_id"], RUN_SPEC_ID)
        self.assertEqual(
            detail["validation"]["gates"],
            {
                "contract": "passed",
                "strategy_import": "failed",
                "smoke_run": "failed",
            },
        )
        self.assertEqual(detail["validation"]["outcome"], "failed")
        self.assertEqual(detail["artifacts"], {})
        self.assertIsNone(detail["manifest"])
        self.assertIsNone(detail["engine_result"])
        self.assertIsNone(detail["intent_tape"])

    def test_m4_read_model_id_validation_and_missing_resources(self) -> None:
        status, _, body = self.request("GET", "/v1/projects/not-a-uuid/activities")
        self.assertEqual(status, 422, body)
        self.assertEqual(json.loads(body)["error"], "invalid_project_id")

        status, _, body = self.request(
            "GET",
            "/v1/projects/99999999-9999-4999-8999-999999999999/artifacts/"
            "88888888-8888-4888-8888-888888888888?"
            + urlencode({"unused": "ignored"}),
        )
        self.assertEqual(status, 404, body)
        self.assertEqual(json.loads(body)["error"], "artifact_not_found")


if __name__ == "__main__":
    import unittest

    unittest.main()
