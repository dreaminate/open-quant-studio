from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Event

from quant_domain.database import Database
from quant_domain.domain import (
    CommandIdConflict,
    ContractViolation,
    ContextConflict,
    JobTransitionConflict,
    QuantDomain,
)


PROJECT_ID = "22222222-2222-4222-8222-222222222222"
ACTIVITY_ID = "33333333-3333-4333-8333-333333333333"
CORRELATION_ID = "44444444-4444-4444-8444-444444444444"


def context_capture_command(
    *,
    command_id: str = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    context_item_id: str = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    artifact_id: str = "99999999-9999-4999-8999-999999999999",
    blob: bytes = b"m1 evidence\n",
    source_ref: str = "15151515-1515-4515-8515-151515151515",
) -> dict[str, object]:
    digest = hashlib.sha256(blob).hexdigest()
    return {
        "command_id": command_id,
        "schema_version": 1,
        "command_type": "context.capture",
        "project_id": PROJECT_ID,
        "activity_id": ACTIVITY_ID,
        "session_id": "pi:session:m1-test",
        "workbench_id": "canvas",
        "correlation_id": CORRELATION_ID,
        "expected_revision_id": None,
        "variant_id": None,
        "base_revision_id": None,
        "payload": {
            "context_item_id": context_item_id,
            "title": "M1 raw evidence",
            "trust_state": "raw_evidence",
            "artifact": {
                "artifact_id": artifact_id,
                "sha256": digest,
                "media_type": "text/plain",
                "byte_size": len(blob),
                "storage_uri": f"cas://sha256/{digest}",
                "producing_revision_id": None,
                "producing_run_id": None,
                "provenance": {
                    "origin_kind": "fixture",
                    "source_ref": source_ref,
                },
            },
        },
    }


class M1DomainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tempdir.name)
        self.domain = QuantDomain(self.data_root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def database_counts(self) -> dict[str, int]:
        tables = [
            "artifacts",
            "command_receipts",
            "context_items",
            "diagnostic_logs",
            "domain_events",
            "jobs",
            "outbox",
        ]
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            return {
                table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in tables
            }

    def test_migration_enables_wal_and_state_survives_reopen(self) -> None:
        with self.domain.database.connect() as connection:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
            migrations = connection.execute(
                "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
            ).fetchall()

        self.assertEqual(journal_mode, "wal")
        self.assertEqual(foreign_keys, 1)
        self.assertEqual(
            [tuple(row) for row in migrations],
            [
                ("001_m1_domain_core",),
                ("002_m1_immutability",),
                ("003_m2_session_fabric",),
                ("004_m3_revision_graph",),
                ("005_m3_formal_runs",),
            ],
        )

        command = context_capture_command()
        self.domain.submit_command(command)
        reopened = QuantDomain(self.data_root)
        self.assertEqual(len(reopened.events(PROJECT_ID, after_stream_seq=0)), 1)

    def test_migration_ledger_skips_a_non_repeatable_migration_on_reopen(self) -> None:
        migrations_dir = self.data_root / "test-migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_once.sql").write_text(
            "CREATE TABLE one_time_probe(value TEXT NOT NULL);\n"
            "INSERT INTO one_time_probe(value) VALUES ('once');\n"
        )
        database_path = self.data_root / "migration-probe.sqlite3"

        Database(database_path, migrations_dir=migrations_dir)
        reopened = Database(database_path, migrations_dir=migrations_dir)
        with reopened.connect() as connection:
            values = connection.execute("SELECT value FROM one_time_probe").fetchall()
            migrations = connection.execute(
                "SELECT migration_id FROM schema_migrations"
            ).fetchall()

        self.assertEqual([tuple(row) for row in values], [("once",)])
        self.assertEqual([tuple(row) for row in migrations], [("001_once",)])

    def test_m3_jobs_migration_preserves_an_existing_m1_verification_job(self) -> None:
        source_migrations = (
            Path(__file__).parents[1] / "src" / "quant_domain" / "migrations"
        )
        staged_migrations = self.data_root / "staged-migrations"
        staged_migrations.mkdir()
        for migration in sorted(source_migrations.glob("00[1-4]_*.sql")):
            shutil.copyfile(migration, staged_migrations / migration.name)
        database_path = self.data_root / "upgrade.sqlite3"
        legacy = Database(database_path, migrations_dir=staged_migrations)
        recorded_at = "2026-08-12T00:00:00Z"
        artifact_id = "99999999-9999-4999-8999-999999999999"
        command_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        event_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        job_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        with legacy.connect() as connection:
            connection.execute(
                "INSERT INTO research_projects(project_id, created_at) VALUES (?, ?)",
                (PROJECT_ID, recorded_at),
            )
            connection.execute(
                "INSERT INTO activities(activity_id, project_id, created_at) VALUES (?, ?, ?)",
                (ACTIVITY_ID, PROJECT_ID, recorded_at),
            )
            connection.execute(
                """
                INSERT INTO artifacts(
                    artifact_id, sha256, media_type, byte_size, storage_uri,
                    producing_revision_id, producing_run_id, origin_kind,
                    source_ref, created_at
                ) VALUES (?, ?, 'text/plain', 0, ?, NULL, NULL, 'fixture', ?, ?)
                """,
                (
                    artifact_id,
                    "0" * 64,
                    f"cas://sha256/{'0' * 64}",
                    artifact_id,
                    recorded_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO domain_events(
                    event_id, schema_version, event_type, project_id, activity_id,
                    session_id, workbench_id, correlation_id, causation_id,
                    recorded_at, variant_id, base_revision_id, payload_json
                ) VALUES (?, 1, 'artifact.verification_started', ?, ?, NULL, NULL,
                          ?, ?, ?, NULL, NULL, '{}')
                """,
                (event_id, PROJECT_ID, ACTIVITY_ID, CORRELATION_ID, job_id, recorded_at),
            )
            connection.execute(
                """
                INSERT INTO command_receipts(
                    command_id, command_hash, event_id, receipt_json, recorded_at
                ) VALUES (?, ?, ?, '{}', ?)
                """,
                (command_id, "1" * 64, event_id, recorded_at),
            )
            connection.execute(
                """
                INSERT INTO jobs(
                    job_id, command_id, job_type, project_id, activity_id,
                    session_id, workbench_id, correlation_id, artifact_id,
                    status, attempts, created_at
                ) VALUES (?, ?, 'artifact.verify_sha256', ?, ?, NULL, NULL, ?, ?,
                          'pending', 0, ?)
                """,
                (
                    job_id,
                    command_id,
                    PROJECT_ID,
                    ACTIVITY_ID,
                    CORRELATION_ID,
                    artifact_id,
                    recorded_at,
                ),
            )

        migration_005 = source_migrations / "005_m3_formal_runs.sql"
        shutil.copyfile(migration_005, staged_migrations / migration_005.name)
        upgraded = Database(database_path, migrations_dir=staged_migrations)
        with upgraded.connect() as connection:
            job = connection.execute(
                """
                SELECT job_id, job_type, status, attempts,
                       run_spec_id, run_id, validation_id, candidate_revision_id
                FROM jobs WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

        self.assertEqual(
            tuple(job),
            (job_id, "artifact.verify_sha256", "pending", 0, None, None, None, None),
        )
        self.assertEqual(foreign_key_errors, [])

    def test_context_capture_is_atomic_idempotent_and_immutable(self) -> None:
        command = context_capture_command()
        accepted = self.domain.submit_command(command)
        replayed = self.domain.submit_command(copy.deepcopy(command))

        self.assertEqual(accepted["disposition"], "accepted")
        self.assertEqual(replayed["disposition"], "replayed")
        self.assertEqual(accepted["event"], replayed["event"])
        self.assertEqual(
            self.database_counts(),
            {
                "artifacts": 1,
                "command_receipts": 1,
                "context_items": 1,
                "diagnostic_logs": 1,
                "domain_events": 1,
                "jobs": 1,
                "outbox": 1,
            },
        )

        changed = copy.deepcopy(command)
        changed["payload"]["title"] = "Changed envelope"
        with self.assertRaises(CommandIdConflict):
            self.domain.submit_command(changed)
        self.assertEqual(len(self.domain.events(PROJECT_ID, after_stream_seq=0)), 1)

        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE domain_events SET event_type = 'context.changed'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE artifacts SET media_type = 'application/octet-stream'"
                )

    def test_concurrent_identical_commands_create_one_outcome(self) -> None:
        command = context_capture_command()
        entered = [Event(), Event()]

        def submit(index: int) -> dict[str, object]:
            entered[index].set()
            return self.domain.submit_command(copy.deepcopy(command))

        with self.domain.database.connect() as locker:
            locker.execute("BEGIN IMMEDIATE")
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(submit, index) for index in range(2)]
                self.assertTrue(all(event.wait(timeout=1) for event in entered))
                self.assertTrue(all(not future.done() for future in futures))
                locker.execute("COMMIT")
                receipts = [future.result(timeout=5) for future in futures]

        self.assertEqual(
            sorted(receipt["disposition"] for receipt in receipts),
            ["accepted", "replayed"],
        )
        self.assertEqual(receipts[0]["event"], receipts[1]["event"])
        self.assertEqual(self.database_counts()["domain_events"], 1)
        self.assertEqual(self.database_counts()["command_receipts"], 1)

    def test_late_context_conflict_rolls_back_every_transactional_write(self) -> None:
        self.domain.submit_command(context_capture_command())
        before = self.database_counts()
        conflicting = context_capture_command(
            command_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            artifact_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
            blob=b"different artifact\n",
        )

        with self.assertRaises(ContextConflict):
            self.domain.submit_command(conflicting)

        self.assertEqual(self.database_counts(), before)
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            artifact = connection.execute(
                "SELECT artifact_id FROM artifacts WHERE artifact_id = ?",
                ("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",),
            ).fetchone()
        self.assertIsNone(artifact)

    def test_contract_rejection_precedes_database_writes(self) -> None:
        invalid_commands = []
        invalid_trust = context_capture_command()
        invalid_trust["payload"]["trust_state"] = "canonical"
        invalid_commands.append(invalid_trust)
        invalid_revision = context_capture_command()
        invalid_revision["variant_id"] = "55555555-5555-4555-8555-555555555555"
        invalid_revision["base_revision_id"] = "66666666-6666-4666-8666-666666666666"
        invalid_revision["payload"]["artifact"]["producing_revision_id"] = (
            "77777777-7777-4777-8777-777777777777"
        )
        invalid_revision["payload"]["artifact"]["producing_run_id"] = (
            "88888888-8888-4888-8888-888888888888"
        )
        invalid_commands.append(invalid_revision)
        invalid_storage = context_capture_command()
        invalid_storage["payload"]["artifact"]["storage_uri"] = (
            "cas://sha256/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        invalid_commands.append(invalid_storage)
        invalid_source = context_capture_command(source_ref="Bearer REVIEW-SECRET")
        invalid_commands.append(invalid_source)

        for command in invalid_commands:
            with self.subTest(command=command):
                with self.assertRaises(ContractViolation) as rejection:
                    self.domain.submit_command(command)
                self.assertNotIn("REVIEW-SECRET", json.dumps(rejection.exception.errors))

        self.assertEqual(
            self.database_counts(),
            {
                "artifacts": 0,
                "command_receipts": 0,
                "context_items": 0,
                "diagnostic_logs": 0,
                "domain_events": 0,
                "jobs": 0,
                "outbox": 0,
            },
        )

    def test_job_runner_records_deterministic_success_and_explicit_failure(self) -> None:
        blob = b"verified artifact\n"
        success_command = context_capture_command(blob=blob)
        digest = hashlib.sha256(blob).hexdigest()
        stored = self.domain.store_blob(digest, blob)
        self.assertEqual(stored["sha256"], digest)
        self.domain.submit_command(success_command)

        succeeded = self.domain.run_next_job()
        self.assertEqual(succeeded["status"], "succeeded")
        self.assertEqual(succeeded["attempts"], 1)
        self.assertEqual(succeeded["result"]["sha256"], digest)

        missing_command = context_capture_command(
            command_id="ffffffff-ffff-4fff-8fff-ffffffffffff",
            context_item_id="12121212-1212-4212-8212-121212121212",
            artifact_id="13131313-1313-4313-8313-131313131313",
            blob=b"missing blob\n",
        )
        self.domain.submit_command(missing_command)
        failed = self.domain.run_next_job()
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error_code"], "artifact_blob_missing")

        events = self.domain.events(PROJECT_ID, after_stream_seq=0)
        self.assertEqual(
            [event["event_type"] for event in events],
            [
                "context.captured",
                "artifact.verification_started",
                "artifact.verification_succeeded",
                "context.captured",
                "artifact.verification_started",
                "artifact.verification_failed",
            ],
        )
        self.assertEqual(
            [event["stream_seq"] for event in events], [1, 2, 3, 4, 5, 6]
        )

        logs = self.domain.logs(project_id=PROJECT_ID)
        required = {
            "timestamp",
            "level",
            "priority",
            "component",
            "event_code",
            "project_id",
            "activity_id",
            "session_id",
            "task_id",
            "job_id",
            "run_id",
            "correlation_id",
            "message",
        }
        self.assertTrue(all(set(log) == required for log in logs))
        self.assertEqual(
            [log["event_code"] for log in self.domain.logs(level="error", priority="p2")],
            ["artifact.verification.failed"],
        )

    def test_stale_job_finish_cannot_emit_an_extra_terminal_event(self) -> None:
        blob = b"stale finish probe\n"
        digest = hashlib.sha256(blob).hexdigest()
        self.domain.store_blob(digest, blob)
        self.domain.submit_command(context_capture_command(blob=blob))
        succeeded = self.domain.run_next_job()
        before = self.domain.events(PROJECT_ID, after_stream_seq=0)
        with self.domain.database.connect() as connection:
            stale = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (succeeded["job_id"],)
            ).fetchone()

        with self.assertRaises(JobTransitionConflict):
            self.domain._finish_job(
                stale,
                status="succeeded",
                result=succeeded["result"],
                error_code=None,
                error_message=None,
            )

        self.assertEqual(self.domain.events(PROJECT_ID, after_stream_seq=0), before)


if __name__ == "__main__":
    unittest.main()
