from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from quant_domain.git_workspace import GitRevisionIdentity, GitWorkspaceError, GitWorkspaceStore


PROJECT_ID = "11111111-1111-4111-8111-111111111111"
ROOT_REVISION_ID = "22222222-2222-4222-8222-222222222222"
CHILD_REVISION_ID = "33333333-3333-4333-8333-333333333333"
RECORDED_AT = "2026-08-11T10:11:12Z"
OID_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class M3GitWorkspaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tempdir.name)
        self.store = GitWorkspaceStore(self.data_root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_git(
        self,
        repository: Path,
        *args: str,
        input_bytes: bytes | None = None,
    ) -> bytes:
        environment = os.environ.copy()
        environment["GIT_DIR"] = str(repository)
        completed = subprocess.run(
            ["/usr/bin/git", *args],
            env=environment,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"git command failed: {args!r}: {completed.stderr.decode(errors='replace')}",
        )
        return completed.stdout

    def assert_identity_oids(self, identity: GitRevisionIdentity) -> None:
        self.assertRegex(identity.commit_oid, OID_PATTERN)
        self.assertRegex(identity.tree_oid, OID_PATTERN)
        for oid in identity.blob_oids.values():
            self.assertRegex(oid, OID_PATTERN)

    def test_root_commit_contains_nested_files_and_real_git_evidence(self) -> None:
        files = {
            "README.md": b"Open Quant Studio\n",
            "src/main.py": b"print('main')\n",
            "src/lib/util.py": b"VALUE = 42\n",
        }
        identity = self.store.create_commit(
            project_id=PROJECT_ID,
            revision_id=ROOT_REVISION_ID,
            files=files,
            parent_commit_oids=[],
            message="initial workspace",
            recorded_at=RECORDED_AT,
        )

        self.assert_identity_oids(identity)
        repository = self.store.repository_path(PROJECT_ID)
        self.assertEqual(repository, self.data_root / "git" / f"{PROJECT_ID}.git")
        self.assertTrue(repository.is_dir())

        commit_text = self.run_git(repository, "cat-file", "-p", identity.commit_oid).decode()
        self.assertIn(f"tree {identity.tree_oid}\n", commit_text)
        self.assertIn(ROOT_REVISION_ID, commit_text)
        self.assertIn("initial workspace", commit_text)
        self.assertNotIn("parent ", commit_text)

        names = self.run_git(
            repository,
            "ls-tree",
            "-r",
            "--name-only",
            identity.tree_oid,
        ).decode().splitlines()
        self.assertEqual(names, ["README.md", "src/lib/util.py", "src/main.py"])
        self.assertEqual(
            self.run_git(
                repository,
                "cat-file",
                "blob",
                identity.blob_oids["src/lib/util.py"],
            ),
            files["src/lib/util.py"],
        )

    def test_child_commit_has_exact_parent_and_no_refs_are_created(self) -> None:
        root = self.store.create_commit(
            project_id=PROJECT_ID,
            revision_id=ROOT_REVISION_ID,
            files={"strategy.py": b"signal = 1\n"},
            parent_commit_oids=[],
            message="root",
            recorded_at=RECORDED_AT,
        )
        child = self.store.create_commit(
            project_id=PROJECT_ID,
            revision_id=CHILD_REVISION_ID,
            files={"strategy.py": b"signal = 2\n"},
            parent_commit_oids=[root.commit_oid],
            message="child",
            recorded_at=RECORDED_AT,
        )

        self.assert_identity_oids(child)
        repository = self.store.repository_path(PROJECT_ID)
        commit_text = self.run_git(repository, "cat-file", "-p", child.commit_oid).decode()
        self.assertIn(f"parent {root.commit_oid}\n", commit_text)
        self.assertIn(CHILD_REVISION_ID, commit_text)

        self.assertEqual(
            self.run_git(repository, "for-each-ref", "--format=%(refname)"),
            b"",
        )
        refs_root = repository / "refs"
        self.assertFalse(any(path.is_file() for path in refs_root.rglob("*")))

    def test_same_frozen_inputs_are_deterministic_even_with_different_mapping_order(self) -> None:
        first = self.store.create_commit(
            project_id=PROJECT_ID,
            revision_id=ROOT_REVISION_ID,
            files={"z.txt": b"z\n", "a.txt": b"a\n"},
            parent_commit_oids=[],
            message="same inputs",
            recorded_at=RECORDED_AT,
        )
        second = self.store.create_commit(
            project_id=PROJECT_ID,
            revision_id=ROOT_REVISION_ID,
            files={"a.txt": b"a\n", "z.txt": b"z\n"},
            parent_commit_oids=[],
            message="same inputs",
            recorded_at=RECORDED_AT,
        )

        self.assertEqual(first, second)
        self.assert_identity_oids(first)

    def test_protected_revision_ref_survives_immediate_git_gc(self) -> None:
        identity = self.store.create_commit(
            project_id=PROJECT_ID,
            revision_id=ROOT_REVISION_ID,
            files={"strategy.py": b"signal = 1\n"},
            parent_commit_oids=[],
            message="protected",
            recorded_at=RECORDED_AT,
        )
        self.store.protect_revision(
            project_id=PROJECT_ID,
            revision_id=ROOT_REVISION_ID,
            commit_oid=identity.commit_oid,
        )
        repository = self.store.repository_path(PROJECT_ID)
        revision_ref = f"refs/oqs/revisions/{ROOT_REVISION_ID}"
        self.assertEqual(
            self.run_git(repository, "rev-parse", revision_ref).decode().strip(),
            identity.commit_oid,
        )
        self.run_git(repository, "gc", "--prune=now")
        self.run_git(repository, "cat-file", "-e", f"{identity.commit_oid}^{{commit}}")

    def test_multiple_parents_are_rejected_for_this_slice(self) -> None:
        with self.assertRaisesRegex(GitWorkspaceError, "one parent"):
            self.store.create_commit(
                project_id=PROJECT_ID,
                revision_id=ROOT_REVISION_ID,
                files={},
                parent_commit_oids=["a" * 40, "b" * 40],
                message="merge",
                recorded_at=RECORDED_AT,
            )

    def test_git_failure_has_bounded_message_without_command_output_or_file_bytes(self) -> None:
        secret = b"do-not-leak-this-file-content"
        with self.assertRaises(GitWorkspaceError) as raised:
            self.store.create_commit(
                project_id=PROJECT_ID,
                revision_id=ROOT_REVISION_ID,
                files={"secret.txt": secret},
                parent_commit_oids=["not-a-real-parent"],
                message="failure",
                recorded_at=RECORDED_AT,
            )

        error_message = str(raised.exception)
        self.assertLess(len(error_message), 256)
        self.assertNotIn(secret.decode(), error_message)
        self.assertNotIn("fatal:", error_message)

    def test_unsafe_and_file_directory_colliding_paths_are_rejected(self) -> None:
        unsafe_paths = [
            "strategy.py\n100644 blob aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\tinjected.py",
            ".GIT/config",
        ]
        for path in unsafe_paths:
            with self.subTest(path=path), self.assertRaisesRegex(
                GitWorkspaceError, "path"
            ):
                self.store.create_commit(
                    project_id=PROJECT_ID,
                    revision_id=ROOT_REVISION_ID,
                    files={path: b"content\n"},
                    parent_commit_oids=[],
                    message="unsafe",
                    recorded_at=RECORDED_AT,
                )

        with self.assertRaisesRegex(GitWorkspaceError, "path"):
            self.store.create_commit(
                project_id=PROJECT_ID,
                revision_id=ROOT_REVISION_ID,
                files={"strategy.py": b"file\n", "strategy.py/child": b"child\n"},
                parent_commit_oids=[],
                message="collision",
                recorded_at=RECORDED_AT,
            )


if __name__ == "__main__":
    unittest.main()
