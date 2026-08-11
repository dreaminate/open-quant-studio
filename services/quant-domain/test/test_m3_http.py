from __future__ import annotations

import hashlib
import json
import unittest
from urllib.parse import urlencode

from test_m1_http import HttpTestCase
from test_m3_revisions import (
    PROJECT_ID,
    REVISION_A_ID,
    REVISION_B_ID,
    ROOT_REVISION_ID,
    VARIANT_A_ID,
    VARIANT_B_ID,
    create_revision_command,
    create_variant_command,
    promote_command,
)
from test_m2_session import register_command


class M3HttpTest(HttpTestCase):
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
        self.assertEqual(json.loads(response_body)["sha256"], digest)
        return digest

    def test_real_http_revision_reads_and_stale_promotion_conflict(self) -> None:
        status, body = self.post_command(register_command())
        self.assertEqual(status, 201, body)

        root_files = [
            (
                "strategy.py",
                b"HTTP M3 ROOT SOURCE BODY\nsignal = close > open\n",
                "11111111-1111-4111-8111-111111111111",
            ),
            (
                "config/costs.json",
                b'{"fee_per_side":0.0006,"source":"HTTP M3 ROOT CONFIG BODY"}\n',
                "12121212-1212-4212-8212-121212121212",
            ),
        ]
        root_hashes = {self.stage_blob(body) for _, body, _ in root_files}
        status, body = self.post_command(
            create_revision_command(
                command_id="61616161-6161-4161-8161-616161616161",
                revision_id=ROOT_REVISION_ID,
                files=root_files,
            )
        )
        self.assertEqual(status, 201, body)
        root_receipt = json.loads(body)
        self.assertEqual(
            root_receipt["event"]["payload"]["revision_id"], ROOT_REVISION_ID
        )
        self.assertNotIn("HTTP M3 ROOT SOURCE BODY", body.decode())

        for command in (
            create_variant_command(
                command_id="62626262-6262-4262-8262-626262626262",
                variant_id=VARIANT_A_ID,
            ),
            create_variant_command(
                command_id="63636363-6363-4363-8363-636363636363",
                variant_id=VARIANT_B_ID,
            ),
        ):
            status, body = self.post_command(command)
            self.assertEqual(status, 201, body)

        child_specs = [
            (
                VARIANT_A_ID,
                REVISION_A_ID,
                "64646464-6464-4464-8464-646464646464",
                b"HTTP M3 VARIANT A SOURCE BODY\nsignal = close > moving_average\n",
                "13131313-1313-4313-8313-131313131313",
            ),
            (
                VARIANT_B_ID,
                REVISION_B_ID,
                "65656565-6565-4565-8565-656565656565",
                b"HTTP M3 VARIANT B SOURCE BODY\nsignal = momentum > 0\n",
                "14141414-1414-4414-8414-141414141414",
            ),
        ]
        child_hashes: set[str] = set()
        for variant_id, revision_id, command_id, source, artifact_id in child_specs:
            child_hashes.add(self.stage_blob(source))
            status, body = self.post_command(
                create_revision_command(
                    command_id=command_id,
                    revision_id=revision_id,
                    files=[("strategy.py", source, artifact_id)],
                    variant_id=variant_id,
                    base_revision_id=ROOT_REVISION_ID,
                )
            )
            self.assertEqual(status, 201, body)

        project_query = urlencode({"project_id": PROJECT_ID})
        status, _, body = self.request(
            "GET", f"/v1/revisions/{ROOT_REVISION_ID}?{project_query}"
        )
        self.assertEqual(status, 200, body)
        revision = json.loads(body)
        self.assertEqual(revision["revision_id"], ROOT_REVISION_ID)
        self.assertRegex(revision["git_commit_oid"], r"^[a-f0-9]{40}$")
        self.assertRegex(revision["git_tree_oid"], r"^[a-f0-9]{40}$")
        self.assertEqual(
            {file["sha256"] for file in revision["files"]}, root_hashes
        )
        self.assertNotIn("HTTP M3 ROOT SOURCE BODY", body.decode())
        self.assertNotIn("HTTP M3 ROOT CONFIG BODY", body.decode())

        status, _, body = self.request("GET", f"/v1/variants?{project_query}")
        self.assertEqual(status, 200, body)
        variants = json.loads(body)["variants"]
        self.assertEqual(
            {variant["variant_id"] for variant in variants},
            {VARIANT_A_ID, VARIANT_B_ID},
        )
        heads = {
            variant["variant_id"]: variant["head_revision_id"]
            for variant in variants
        }
        self.assertEqual(
            heads, {VARIANT_A_ID: REVISION_A_ID, VARIANT_B_ID: REVISION_B_ID}
        )
        self.assertNotIn("HTTP M3 VARIANT A SOURCE BODY", body.decode())
        self.assertNotIn("HTTP M3 VARIANT B SOURCE BODY", body.decode())

        compare_query = urlencode(
            {
                "project_id": PROJECT_ID,
                "left_revision_id": REVISION_A_ID,
                "right_revision_id": REVISION_B_ID,
            }
        )
        status, _, body = self.request(
            "GET", f"/v1/revisions/compare?{compare_query}"
        )
        self.assertEqual(status, 200, body)
        comparison = json.loads(body)
        self.assertEqual(comparison["left_revision_id"], REVISION_A_ID)
        self.assertEqual(comparison["right_revision_id"], REVISION_B_ID)
        self.assertEqual(
            [change["path"] for change in comparison["changes"]], ["strategy.py"]
        )
        self.assertEqual(
            {
                comparison["changes"][0]["left_sha256"],
                comparison["changes"][0]["right_sha256"],
            },
            child_hashes,
        )
        self.assertNotIn("HTTP M3 VARIANT A SOURCE BODY", body.decode())
        self.assertNotIn("HTTP M3 VARIANT B SOURCE BODY", body.decode())

        status, _, body = self.request(
            "GET", f"/v1/projects/{PROJECT_ID}/revision-head"
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["head_revision_id"], ROOT_REVISION_ID)

        status, body = self.post_command(
            promote_command(
                command_id="66666666-6666-4666-8666-666666666666",
                variant_id=VARIANT_A_ID,
                candidate_revision_id=REVISION_A_ID,
            )
        )
        self.assertEqual(status, 409, body)
        self.assertEqual(json.loads(body)["error"], "promotion_conflict")

        status, body = self.post_command(
            promote_command(
                command_id="67676767-6767-4767-8767-676767676767",
                variant_id=VARIANT_B_ID,
                candidate_revision_id=REVISION_B_ID,
            )
        )
        self.assertEqual(status, 409, body)
        self.assertEqual(json.loads(body)["error"], "promotion_conflict")
        self.assertNotIn("HTTP M3 VARIANT B SOURCE BODY", body.decode())

        status, _, body = self.request(
            "GET", f"/v1/projects/{PROJECT_ID}/revision-head"
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["head_revision_id"], ROOT_REVISION_ID)

    def test_revision_read_query_validation_and_missing_resources(self) -> None:
        status, _, body = self.request(
            "GET", f"/v1/revisions/{ROOT_REVISION_ID}"
        )
        self.assertEqual(status, 422, body)
        self.assertEqual(json.loads(body)["error"], "project_id_required")

        status, _, body = self.request("GET", "/v1/variants")
        self.assertEqual(status, 422, body)
        self.assertEqual(json.loads(body)["error"], "project_id_required")

        status, _, body = self.request(
            "GET",
            "/v1/revisions/compare?" + urlencode({"project_id": PROJECT_ID}),
        )
        self.assertEqual(status, 422, body)
        self.assertEqual(json.loads(body)["error"], "left_revision_id_required")

        status, _, body = self.request(
            "GET",
            "/v1/revisions/99999999-9999-4999-8999-999999999999?"
            + urlencode({"project_id": PROJECT_ID}),
        )
        self.assertEqual(status, 404, body)
        self.assertEqual(json.loads(body)["error"], "revision_not_found")

        status, _, body = self.request(
            "GET",
            "/v1/projects/99999999-9999-4999-8999-999999999999/revision-head",
        )
        self.assertEqual(status, 404, body)
        self.assertEqual(json.loads(body)["error"], "project_head_not_found")

        compare_query = urlencode(
            {
                "project_id": PROJECT_ID,
                "left_revision_id": ROOT_REVISION_ID,
                "right_revision_id": "99999999-9999-4999-8999-999999999999",
            }
        )
        status, _, body = self.request(
            "GET", f"/v1/revisions/compare?{compare_query}"
        )
        self.assertEqual(status, 409, body)
        self.assertEqual(json.loads(body)["error"], "revision_conflict")

        status, _, body = self.request(
            "GET", "/v1/projects/not-a-uuid/revision-head"
        )
        self.assertEqual(status, 422, body)
        self.assertEqual(json.loads(body)["error"], "invalid_project_id")


if __name__ == "__main__":
    unittest.main()
