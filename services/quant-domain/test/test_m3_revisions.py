from __future__ import annotations

import copy
import hashlib
import sqlite3
import subprocess
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from quant_domain.domain import (
    CommandIdConflict,
    PromotionConflict,
    QuantDomain,
    RevisionConflict,
)
from test_m2_session import (
    ACTIVITY_ID,
    CORRELATION_ID,
    PROJECT_ID,
    SENDER_SESSION_ID,
    artifact_for,
    register_command,
)


ROOT_REVISION_ID = "10101010-1010-4010-8010-101010101010"
VARIANT_A_ID = "20202020-2020-4020-8020-202020202020"
VARIANT_B_ID = "30303030-3030-4030-8030-303030303030"
VARIANT_C_ID = "31313131-3131-4131-8131-313131313131"
REVISION_A_ID = "40404040-4040-4040-8040-404040404040"
REVISION_B_ID = "50505050-5050-4050-8050-505050505050"


def revision_command(
    command_type: str,
    *,
    command_id: str,
    payload: dict[str, object],
    expected_revision_id: str | None,
    variant_id: str | None,
    base_revision_id: str | None,
    project_id: str = PROJECT_ID,
) -> dict[str, object]:
    return {
        "command_id": command_id,
        "schema_version": 1,
        "command_type": command_type,
        "project_id": project_id,
        "activity_id": ACTIVITY_ID,
        "session_id": SENDER_SESSION_ID,
        "workbench_id": "canvas",
        "correlation_id": CORRELATION_ID,
        "expected_revision_id": expected_revision_id,
        "variant_id": variant_id,
        "base_revision_id": base_revision_id,
        "payload": payload,
    }


def create_revision_command(
    *,
    command_id: str,
    revision_id: str,
    files: list[tuple[str, bytes, str]],
    variant_id: str | None = None,
    base_revision_id: str | None = None,
    removed_paths: list[str] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "revision_id": revision_id,
        "message": f"Create {revision_id}",
        "files": [
            {
                "path": path,
                "artifact": artifact_for(body, artifact_id),
            }
            for path, body, artifact_id in files
        ],
    }
    if removed_paths is not None:
        payload["removed_paths"] = removed_paths
    return revision_command(
        "workspace.revision_create",
        command_id=command_id,
        expected_revision_id=base_revision_id,
        variant_id=variant_id,
        base_revision_id=base_revision_id,
        payload=payload,
    )


def create_variant_command(
    *, command_id: str, variant_id: str, base_revision_id: str = ROOT_REVISION_ID
) -> dict[str, object]:
    return revision_command(
        "strategy.variant_create",
        command_id=command_id,
        expected_revision_id=None,
        variant_id=variant_id,
        base_revision_id=base_revision_id,
        payload={
            "variant_id": variant_id,
            "base_revision_id": base_revision_id,
        },
    )


def promote_command(
    *,
    command_id: str,
    variant_id: str,
    candidate_revision_id: str,
    expected_revision_id: str = ROOT_REVISION_ID,
    validation_id: str = "71717171-7171-4171-8171-717171717171",
) -> dict[str, object]:
    return revision_command(
        "workspace.revision_promote",
        command_id=command_id,
        expected_revision_id=expected_revision_id,
        variant_id=variant_id,
        base_revision_id=expected_revision_id,
        payload={
            "variant_id": variant_id,
            "candidate_revision_id": candidate_revision_id,
            "validation_id": validation_id,
        },
    )


class M3RevisionDomainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tempdir.name)
        self.domain = QuantDomain(self.data_root)
        self.domain.submit_command(register_command())

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def stage_files(self, files: list[tuple[str, bytes, str]]) -> None:
        for _, body, _ in files:
            self.domain.store_blob(hashlib.sha256(body).hexdigest(), body)

    def create_root(self) -> dict[str, object]:
        files = [
            (
                "strategy.py",
                b"signal = close > open\n",
                "11111111-1111-4111-8111-111111111111",
            ),
            (
                "config/costs.json",
                b'{"fee_per_side":0.0006}\n',
                "12121212-1212-4212-8212-121212121212",
            ),
        ]
        self.stage_files(files)
        command = create_revision_command(
            command_id="61616161-6161-4161-8161-616161616161",
            revision_id=ROOT_REVISION_ID,
            files=files,
        )
        return self.domain.submit_command(command)

    def create_variants_and_children(self) -> None:
        self.create_root()
        self.domain.submit_command(
            create_variant_command(
                command_id="62626262-6262-4262-8262-626262626262",
                variant_id=VARIANT_A_ID,
            )
        )
        self.domain.submit_command(
            create_variant_command(
                command_id="63636363-6363-4363-8363-636363636363",
                variant_id=VARIANT_B_ID,
            )
        )
        changes = [
            (
                VARIANT_A_ID,
                REVISION_A_ID,
                "64646464-6464-4464-8464-646464646464",
                b"signal = close > moving_average\n",
                "13131313-1313-4313-8313-131313131313",
            ),
            (
                VARIANT_B_ID,
                REVISION_B_ID,
                "65656565-6565-4565-8565-656565656565",
                b"signal = momentum > 0\n",
                "14141414-1414-4414-8414-141414141414",
            ),
        ]
        for variant_id, revision_id, command_id, body, artifact_id in changes:
            files = [("strategy.py", body, artifact_id)]
            self.stage_files(files)
            self.domain.submit_command(
                create_revision_command(
                    command_id=command_id,
                    revision_id=revision_id,
                    files=files,
                    variant_id=variant_id,
                    base_revision_id=ROOT_REVISION_ID,
                )
            )

    def test_root_revision_is_a_real_immutable_git_commit_and_replays(self) -> None:
        accepted = self.create_root()
        event = accepted["event"]
        self.assertEqual(event["event_type"], "workspace.revision_created")
        self.assertIsNone(event["variant_id"])
        self.assertIsNone(event["base_revision_id"])
        self.assertRegex(event["payload"]["git_commit_oid"], r"^[a-f0-9]{40}$")
        self.assertRegex(event["payload"]["git_tree_oid"], r"^[a-f0-9]{40}$")
        self.assertNotIn("signal =", str(accepted))

        command = create_revision_command(
            command_id="61616161-6161-4161-8161-616161616161",
            revision_id=ROOT_REVISION_ID,
            files=[
                (
                    "strategy.py",
                    b"signal = close > open\n",
                    "11111111-1111-4111-8111-111111111111",
                ),
                (
                    "config/costs.json",
                    b'{"fee_per_side":0.0006}\n',
                    "12121212-1212-4212-8212-121212121212",
                ),
            ],
        )
        replayed = self.domain.submit_command(command)
        self.assertEqual(replayed["disposition"], "replayed")
        self.assertEqual(replayed["event"], event)
        changed = copy.deepcopy(command)
        changed["payload"]["message"] = "Divergent duplicate"
        with self.assertRaises(CommandIdConflict):
            self.domain.submit_command(changed)

        repository = self.data_root / "git" / f"{PROJECT_ID}.git"
        revision_ref = f"refs/oqs/revisions/{ROOT_REVISION_ID}"
        resolved_ref = subprocess.run(
            [
                "/usr/bin/git",
                f"--git-dir={repository}",
                "rev-parse",
                revision_ref,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(resolved_ref, event["payload"]["git_commit_oid"])
        subprocess.run(
            ["/usr/bin/git", f"--git-dir={repository}", "gc", "--prune=now"],
            check=True,
        )
        subprocess.run(
            [
                "/usr/bin/git",
                f"--git-dir={repository}",
                "cat-file",
                "-e",
                f"{event['payload']['git_commit_oid']}^{{commit}}",
            ],
            check=True,
        )
        detail = self.domain.revision(PROJECT_ID, ROOT_REVISION_ID)
        self.assertEqual(detail["git_tree_oid"], event["payload"]["git_tree_oid"])
        self.assertEqual(
            [file["path"] for file in detail["files"]],
            ["config/costs.json", "strategy.py"],
        )
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE workspace_revisions SET message = 'mutated' WHERE revision_id = ?",
                    (ROOT_REVISION_ID,),
                )

    def test_two_variants_keep_independent_child_revisions_and_compare(self) -> None:
        self.create_variants_and_children()
        variants = {
            row["variant_id"]: row for row in self.domain.variants(PROJECT_ID)
        }
        self.assertEqual(variants[VARIANT_A_ID]["head_revision_id"], REVISION_A_ID)
        self.assertEqual(variants[VARIANT_B_ID]["head_revision_id"], REVISION_B_ID)
        revision_a = self.domain.revision(PROJECT_ID, REVISION_A_ID)
        revision_b = self.domain.revision(PROJECT_ID, REVISION_B_ID)
        self.assertEqual(revision_a["base_revision_id"], ROOT_REVISION_ID)
        self.assertEqual(revision_b["base_revision_id"], ROOT_REVISION_ID)
        self.assertNotEqual(revision_a["git_tree_oid"], revision_b["git_tree_oid"])
        comparison = self.domain.compare_revisions(
            PROJECT_ID, REVISION_A_ID, REVISION_B_ID
        )
        self.assertEqual(comparison["left_revision_id"], REVISION_A_ID)
        self.assertEqual(comparison["right_revision_id"], REVISION_B_ID)
        self.assertEqual(
            [change["path"] for change in comparison["changes"]], ["strategy.py"]
        )
        self.assertNotEqual(
            comparison["changes"][0]["left_sha256"],
            comparison["changes"][0]["right_sha256"],
        )
        self.assertEqual(self.domain.project_head(PROJECT_ID), ROOT_REVISION_ID)
        repository = self.data_root / "git" / f"{PROJECT_ID}.git"
        refs = subprocess.run(
            [
                "/usr/bin/git",
                f"--git-dir={repository}",
                "for-each-ref",
                "--format=%(refname)",
                "refs/oqs/revisions",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(
            refs,
            sorted(
                f"refs/oqs/revisions/{revision_id}"
                for revision_id in [ROOT_REVISION_ID, REVISION_A_ID, REVISION_B_ID]
            ),
        )

    def test_child_revision_removes_one_inherited_file_and_keeps_the_new_source(self) -> None:
        self.create_root()
        self.domain.submit_command(
            create_variant_command(
                command_id="72727272-7272-4272-8272-727272727272",
                variant_id=VARIANT_A_ID,
            )
        )
        source = b"signal = close > moving_average\n"
        files = [
            (
                "strategy.py",
                source,
                "73737373-7373-4373-8373-737373737373",
            )
        ]
        self.stage_files(files)
        self.domain.submit_command(
            create_revision_command(
                command_id="74747474-7474-4474-8474-747474747474",
                revision_id=REVISION_A_ID,
                files=files,
                variant_id=VARIANT_A_ID,
                base_revision_id=ROOT_REVISION_ID,
                removed_paths=["config/costs.json"],
            )
        )

        revision = self.domain.revision(PROJECT_ID, REVISION_A_ID)
        self.assertEqual(
            [(file["path"], file["sha256"]) for file in revision["files"]],
            [("strategy.py", hashlib.sha256(source).hexdigest())],
        )

    def test_raw_variant_heads_cannot_bypass_merge_validation(self) -> None:
        self.create_variants_and_children()
        commands = [
            promote_command(
                command_id="66666666-6666-4666-8666-666666666666",
                variant_id=VARIANT_A_ID,
                candidate_revision_id=REVISION_A_ID,
            ),
            promote_command(
                command_id="67676767-6767-4767-8767-676767676767",
                variant_id=VARIANT_B_ID,
                candidate_revision_id=REVISION_B_ID,
            ),
        ]
        for command in commands:
            with self.assertRaises(PromotionConflict):
                self.domain.submit_command(command)
        self.assertEqual(self.domain.project_head(PROJECT_ID), ROOT_REVISION_ID)
        promoted_events = [
            event
            for event in self.domain.events(PROJECT_ID, after_stream_seq=0)
            if event["event_type"] == "workspace.revision_promoted"
        ]
        self.assertEqual(promoted_events, [])
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            receipts = connection.execute(
                "SELECT command_id FROM command_receipts WHERE command_id IN (?, ?)",
                (commands[0]["command_id"], commands[1]["command_id"]),
            ).fetchall()
        self.assertEqual(receipts, [])

    def test_unvalidated_revision_cannot_enter_project_history_or_enable_aba(self) -> None:
        self.create_variants_and_children()
        self.domain.submit_command(
            create_variant_command(
                command_id="78787878-7878-4878-8878-787878787878",
                variant_id=VARIANT_C_ID,
            )
        )
        first = promote_command(
            command_id="79797979-7979-4979-8979-797979797979",
            variant_id=VARIANT_A_ID,
            candidate_revision_id=REVISION_A_ID,
        )
        with self.assertRaises(PromotionConflict):
            self.domain.submit_command(first)
        revert = promote_command(
            command_id="80808080-8080-4080-8080-808080808080",
            variant_id=VARIANT_C_ID,
            candidate_revision_id=ROOT_REVISION_ID,
            expected_revision_id=ROOT_REVISION_ID,
        )
        with self.assertRaises(PromotionConflict):
            self.domain.submit_command(revert)
        self.assertEqual(self.domain.project_head(PROJECT_ID), ROOT_REVISION_ID)
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            history = connection.execute(
                """
                SELECT head_revision_id, head_version
                FROM project_revision_head_history
                WHERE project_id = ?
                ORDER BY head_version
                """,
                (PROJECT_ID,),
            ).fetchall()
            receipt = connection.execute(
                "SELECT 1 FROM command_receipts WHERE command_id = ?",
                (revert["command_id"],),
            ).fetchone()
        self.assertEqual(history, [(ROOT_REVISION_ID, 0)])
        self.assertIsNone(receipt)

    def test_duplicate_revision_id_fails_before_writing_more_git_objects(self) -> None:
        self.create_variants_and_children()
        repository = self.data_root / "git" / f"{PROJECT_ID}.git"

        def loose_objects() -> int:
            output = subprocess.run(
                ["/usr/bin/git", f"--git-dir={repository}", "count-objects", "-v"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            return int(
                next(line.removeprefix("count: ") for line in output.splitlines() if line.startswith("count: "))
            )

        before = loose_objects()
        body = b"duplicate revision id must not reach Git\n"
        self.stage_files(
            [("strategy.py", body, "81818181-8181-4181-8181-818181818181")]
        )
        duplicate = create_revision_command(
            command_id="82828282-8282-4282-8282-828282828282",
            revision_id=REVISION_A_ID,
            files=[
                (
                    "strategy.py",
                    body,
                    "81818181-8181-4181-8181-818181818181",
                )
            ],
            variant_id=VARIANT_B_ID,
            base_revision_id=REVISION_B_ID,
        )
        with self.assertRaises(RevisionConflict):
            self.domain.submit_command(duplicate)
        self.assertEqual(loose_objects(), before)

    def test_project_variant_catalog_is_bounded_at_sixty_four(self) -> None:
        self.create_root()
        for index in range(64):
            self.domain.submit_command(
                create_variant_command(
                    command_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"command:{index}")),
                    variant_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"variant:{index}")),
                )
            )
        self.assertEqual(len(self.domain.variants(PROJECT_ID)), 64)
        overflow = create_variant_command(
            command_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "command:overflow")),
            variant_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "variant:overflow")),
        )
        with self.assertRaises(RevisionConflict):
            self.domain.submit_command(overflow)
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            receipt = connection.execute(
                "SELECT 1 FROM command_receipts WHERE command_id = ?",
                (overflow["command_id"],),
            ).fetchone()
        self.assertIsNone(receipt)

    def test_invalid_lineage_writes_no_revision_event_or_receipt(self) -> None:
        self.create_root()
        command = create_variant_command(
            command_id="68686868-6868-4868-8868-686868686868",
            variant_id=VARIANT_A_ID,
            base_revision_id="99999999-9999-4999-8999-999999999999",
        )
        before = self.domain.events(PROJECT_ID, after_stream_seq=0)
        with self.assertRaises(RevisionConflict):
            self.domain.submit_command(command)
        self.assertEqual(self.domain.events(PROJECT_ID, after_stream_seq=0), before)
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            receipt = connection.execute(
                "SELECT 1 FROM command_receipts WHERE command_id = ?",
                (command["command_id"],),
            ).fetchone()
        self.assertIsNone(receipt)


if __name__ == "__main__":
    unittest.main()
