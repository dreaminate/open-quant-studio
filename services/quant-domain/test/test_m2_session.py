from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from quant_domain.domain import (
    ArtifactBlobMissing,
    ArtifactIntegrityMismatch,
    CommandIdConflict,
    ContractViolation,
    DomainConflict,
    MessageReceiptConflict,
    QuantDomain,
)


PROJECT_ID = "22222222-2222-4222-8222-222222222222"
OTHER_PROJECT_ID = "99999999-9999-4999-8999-999999999999"
ACTIVITY_ID = "33333333-3333-4333-8333-333333333333"
OTHER_ACTIVITY_ID = "88888888-8888-4888-8888-888888888888"
SENDER_SESSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
RECEIVER_SESSION_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
CORRELATION_ID = "44444444-4444-4444-8444-444444444444"


def artifact_for(blob: bytes, artifact_id: str) -> dict[str, object]:
    digest = hashlib.sha256(blob).hexdigest()
    return {
        "artifact_id": artifact_id,
        "sha256": digest,
        "media_type": "text/plain",
        "byte_size": len(blob),
        "storage_uri": f"cas://sha256/{digest}",
        "producing_revision_id": None,
        "producing_run_id": None,
        "provenance": {
            "origin_kind": "fixture",
            "source_ref": "15151515-1515-4515-8515-151515151515",
        },
    }


def session_command(
    command_type: str,
    *,
    command_id: str,
    actor_session_id: str,
    payload: dict[str, object],
    project_id: str = PROJECT_ID,
    activity_id: str = ACTIVITY_ID,
    workbench_id: str = "canvas",
    correlation_id: str = CORRELATION_ID,
) -> dict[str, object]:
    return {
        "command_id": command_id,
        "schema_version": 1,
        "command_type": command_type,
        "project_id": project_id,
        "activity_id": activity_id,
        "session_id": actor_session_id,
        "workbench_id": workbench_id,
        "correlation_id": correlation_id,
        "expected_revision_id": None,
        "variant_id": None,
        "base_revision_id": None,
        "payload": payload,
    }


def register_command(
    *,
    command_id: str = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa01",
    session_id: str = SENDER_SESSION_ID,
    pi_session_id: str = "pi-session-a",
    project_id: str = PROJECT_ID,
    activity_id: str = ACTIVITY_ID,
) -> dict[str, object]:
    return session_command(
        "session.register",
        command_id=command_id,
        actor_session_id=session_id,
        project_id=project_id,
        activity_id=activity_id,
        payload={
            "pi_session_id": pi_session_id,
            "session_uri": f"pi-jsonl://session/{pi_session_id}",
        },
    )


def source_ref(session_id: str = SENDER_SESSION_ID) -> dict[str, str]:
    entry_id = "entry-1"
    body = canonical_source_blob(entry_id)
    digest = hashlib.sha256(body).hexdigest()
    pi_session_id = {
        SENDER_SESSION_ID: "pi-session-a",
        RECEIVER_SESSION_ID: "pi-session-b",
    }[session_id]
    return {
        "session_id": session_id,
        "entry_id": entry_id,
        "leaf_id": "leaf-1",
        "sha256": digest,
        "source_uri": f"pi-jsonl://session/{pi_session_id}#entry={entry_id}",
    }


def canonical_source_blob(entry_id: str) -> bytes:
    return json.dumps(
        {"id": entry_id, "text": "canonical source witness"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def source_ref_for_body(
    body: bytes,
    *,
    entry_id: str = "entry-1",
    session_id: str = SENDER_SESSION_ID,
) -> dict[str, str]:
    pi_session_id = {
        SENDER_SESSION_ID: "pi-session-a",
        RECEIVER_SESSION_ID: "pi-session-b",
    }[session_id]
    return {
        "session_id": session_id,
        "entry_id": entry_id,
        "leaf_id": "leaf-1",
        "sha256": hashlib.sha256(body).hexdigest(),
        "source_uri": f"pi-jsonl://session/{pi_session_id}#entry={entry_id}",
    }


def send_command(
    *,
    command_id: str = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa02",
    message_id: str = "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    blob: bytes = b"M2 secret message body",
    sender_session_id: str = SENDER_SESSION_ID,
    recipient_session_id: str = RECEIVER_SESSION_ID,
    project_id: str = PROJECT_ID,
    activity_id: str = ACTIVITY_ID,
    workbench_id: str = "canvas",
    command_type: str = "session.message_send",
    reply_to: str | None = None,
    source_refs: list[dict[str, str]] | None = None,
    artifact_id: str | None = None,
    message_kind: str | None = None,
) -> tuple[dict[str, object], bytes, str]:
    artifact_id = artifact_id or "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    command = session_command(
        command_type,
        command_id=command_id,
        actor_session_id=sender_session_id,
        project_id=project_id,
        activity_id=activity_id,
        workbench_id=workbench_id,
        payload={
            "message_id": message_id,
            "recipient_session_id": recipient_session_id,
            "message_kind": message_kind or ("reply" if command_type == "session.message_reply" else "send"),
            "reply_to": reply_to,
            "source_refs": source_refs or [],
            "artifact": artifact_for(blob, artifact_id),
        },
    )
    return command, blob, artifact_id


def bind_command(
    *,
    command_id: str,
    session_id: str = SENDER_SESSION_ID,
    workbench_id: str = "code",
    correlation_id: str = CORRELATION_ID,
) -> dict[str, object]:
    return session_command(
        "session.workbench_bind",
        command_id=command_id,
        actor_session_id=session_id,
        workbench_id=workbench_id,
        correlation_id=correlation_id,
        payload={"workbench_id": workbench_id},
    )


class M2SessionDomainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tempdir.name)
        self.domain = QuantDomain(self.data_root)
        self.domain.submit_command(register_command())
        self.domain.submit_command(
            register_command(
                command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa03",
                session_id=RECEIVER_SESSION_ID,
                pi_session_id="pi-session-b",
            )
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_register_maps_pi_identity_without_transcript_or_active_claim(self) -> None:
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(agent_sessions)")
            }
            row = connection.execute(
                "SELECT session_id, project_id, activity_id, pi_session_id, session_uri FROM agent_sessions WHERE session_id = ?",
                (SENDER_SESSION_ID,),
            ).fetchone()
            self.assertNotIn("active", columns)
            self.assertNotIn("jsonl_path", columns)
            self.assertNotIn("transcript", columns)
        self.assertEqual(
            row,
            (
                SENDER_SESSION_ID,
                PROJECT_ID,
                ACTIVITY_ID,
                "pi-session-a",
                "pi-jsonl://session/pi-session-a",
            ),
        )
        event = self.domain.events(PROJECT_ID, after_stream_seq=0)[0]
        self.assertEqual(event["event_type"], "session.registered")
        self.assertEqual(
            event["payload"],
            {
                "session_id": SENDER_SESSION_ID,
                "pi_session_id": "pi-session-a",
                "session_uri": "pi-jsonl://session/pi-session-a",
                "workbench_id": "canvas",
            },
        )

    def test_message_send_is_atomic_idempotent_and_body_free(self) -> None:
        command, blob, artifact_id = send_command()
        digest = hashlib.sha256(blob).hexdigest()
        self.domain.store_blob(digest, blob)
        accepted = self.domain.submit_command(command)
        replayed = self.domain.submit_command(copy.deepcopy(command))
        self.assertEqual(accepted["disposition"], "accepted")
        self.assertEqual(replayed["disposition"], "replayed")
        self.assertEqual(accepted["event"], replayed["event"])
        self.assertEqual(
            accepted["event"]["payload"],
            {
                "message_id": command["payload"]["message_id"],
                "recipient_session_id": RECEIVER_SESSION_ID,
                "message_kind": "send",
                "artifact_id": artifact_id,
                "artifact_sha256": digest,
                "state": "queued",
                "receipt_version": 0,
                "reply_to": None,
                "source_refs": [],
            },
        )
        self.assertNotIn(blob.decode(), json.dumps(accepted))
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            for table in ("session_messages", "domain_events", "outbox", "command_receipts", "diagnostic_logs"):
                values = connection.execute(f"SELECT * FROM {table}").fetchall()
                self.assertNotIn(blob, b"".join(str(value).encode() for row in values for value in row))
            message = connection.execute(
                "SELECT project_id, activity_id, sender_session_id, recipient_session_id, artifact_id FROM session_messages WHERE message_id = ?",
                (command["payload"]["message_id"],),
            ).fetchone()
        self.assertEqual(
            message,
            (PROJECT_ID, ACTIVITY_ID, SENDER_SESSION_ID, RECEIVER_SESSION_ID, artifact_id),
        )

        detail = self.domain.message(
            command["payload"]["message_id"],
            project_id=PROJECT_ID,
            recipient_session_id=RECEIVER_SESSION_ID,
        )
        self.assertIsInstance(detail["created_at"], str)
        self.assertEqual(detail["inbox_seq"], accepted["event"]["stream_seq"])

        changed = copy.deepcopy(command)
        changed["payload"]["recipient_session_id"] = SENDER_SESSION_ID
        with self.assertRaises(CommandIdConflict):
            self.domain.submit_command(changed)

    def test_receipt_state_chain_uses_cas_and_stale_transition_is_side_effect_free(self) -> None:
        command, blob, _ = send_command()
        self.domain.store_blob(hashlib.sha256(blob).hexdigest(), blob)
        self.domain.submit_command(command)
        transitions = [
            ("session.message_receive", "receiver_received", 0, 1),
            ("session.message_mark_injected", "injected", 1, 2),
            ("session.message_acknowledge", "acknowledged", 2, 3),
        ]
        for index, (command_type, expected_state, expected_version, version) in enumerate(transitions):
            transition = session_command(
                command_type,
                command_id=f"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa{10 + index}",
                actor_session_id=RECEIVER_SESSION_ID,
                payload={
                    "message_id": command["payload"]["message_id"],
                    "expected_state": "queued" if expected_version == 0 else transitions[index - 1][1],
                    "expected_version": expected_version,
                },
            )
            accepted = self.domain.submit_command(transition)
            self.assertEqual(accepted["event"]["payload"]["state"], expected_state)
            self.assertEqual(accepted["event"]["payload"]["receipt_version"], version)

        before = self.domain.events(PROJECT_ID, after_stream_seq=0)
        stale = session_command(
            "session.message_acknowledge",
            command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa20",
            actor_session_id=RECEIVER_SESSION_ID,
            payload={
                "message_id": command["payload"]["message_id"],
                "expected_state": "injected",
                "expected_version": 2,
            },
        )
        with self.assertRaises(MessageReceiptConflict) as conflict:
            self.domain.submit_command(stale)
        self.assertEqual(conflict.exception.code, "message_receipt_conflict")
        self.assertEqual(self.domain.events(PROJECT_ID, after_stream_seq=0), before)

    def test_workbench_bind_switches_active_projection_and_retains_history(self) -> None:
        first = self.domain.submit_command(
            bind_command(
                command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa50",
                workbench_id="code",
            )
        )
        self.assertEqual(first["event"]["event_type"], "session.workbench_bound")
        second = self.domain.submit_command(
            bind_command(
                command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa51",
                workbench_id="run-detail",
            )
        )
        self.assertEqual(second["event"]["payload"], {
            "session_id": SENDER_SESSION_ID,
            "workbench_id": "run-detail",
        })
        sender = next(
            session
            for session in self.domain.sessions(PROJECT_ID)
            if session["session_id"] == SENDER_SESSION_ID
        )
        self.assertEqual(sender["workbench_ids"], ["canvas", "code", "run-detail"])
        self.assertEqual(sender["active_workbench_id"], "run-detail")
        with closing(sqlite3.connect(self.domain.database_path)) as connection:
            rows = connection.execute(
                """
                SELECT workbench_id, is_active
                FROM workbench_bindings
                WHERE session_id = ?
                ORDER BY workbench_id
                """,
                (SENDER_SESSION_ID,),
            ).fetchall()
        self.assertEqual(rows, [("canvas", 0), ("code", 0), ("run-detail", 1)])

    def test_message_and_receipt_require_active_workbench_and_stable_correlation(self) -> None:
        self.domain.submit_command(
            bind_command(
                command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa52",
                workbench_id="code",
            )
        )
        command, blob, _ = send_command(
            command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa53",
            workbench_id="canvas",
        )
        self.domain.store_blob(hashlib.sha256(blob).hexdigest(), blob)
        before = self.domain.events(PROJECT_ID, after_stream_seq=0)
        with self.assertRaises(DomainConflict):
            self.domain.submit_command(command)
        self.assertEqual(self.domain.events(PROJECT_ID, after_stream_seq=0), before)

        command["workbench_id"] = "code"
        accepted = self.domain.submit_command(command)
        self.domain.submit_command(
            bind_command(
                command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa55",
                session_id=RECEIVER_SESSION_ID,
                workbench_id="code",
            )
        )
        transition = session_command(
            "session.message_receive",
            command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa54",
            actor_session_id=RECEIVER_SESSION_ID,
            workbench_id="canvas",
            payload={
                "message_id": command["payload"]["message_id"],
                "expected_state": "queued",
                "expected_version": 0,
            },
        )
        before = self.domain.events(PROJECT_ID, after_stream_seq=0)
        with self.assertRaises(DomainConflict):
            self.domain.submit_command(transition)
        self.assertEqual(self.domain.events(PROJECT_ID, after_stream_seq=0), before)

        transition["workbench_id"] = "code"
        transition["correlation_id"] = "55555555-5555-4555-8555-555555555555"
        with self.assertRaises(MessageReceiptConflict):
            self.domain.submit_command(transition)
        self.assertEqual(self.domain.events(PROJECT_ID, after_stream_seq=0), before)
        self.assertEqual(accepted["event"]["correlation_id"], CORRELATION_ID)

    def test_source_refs_require_staged_canonical_entry_witness_and_rollback(self) -> None:
        ask, ask_blob, _ = send_command(
            command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa59",
            message_id="cccccccc-cccc-4ccc-8ccc-cccccccccc59",
            message_kind="ask",
        )
        self.domain.store_blob(hashlib.sha256(ask_blob).hexdigest(), ask_blob)
        self.domain.submit_command(ask)
        cases = [
            (
                "missing",
                source_ref(),
                None,
                ArtifactBlobMissing,
            ),
            (
                "invalid_json",
                source_ref_for_body(b"not json"),
                b"not json",
                ArtifactIntegrityMismatch,
            ),
            (
                "not_object",
                source_ref_for_body(b"[]"),
                b"[]",
                ArtifactIntegrityMismatch,
            ),
            (
                "wrong_entry_id",
                source_ref_for_body(canonical_source_blob("other-entry")),
                canonical_source_blob("other-entry"),
                ArtifactIntegrityMismatch,
            ),
        ]
        for index, (label, witness, staged, expected_error) in enumerate(cases):
            with self.subTest(label=label):
                command, blob, _ = send_command(
                    command_type="session.message_reply",
                    blob=f"reply body {index}".encode(),
                    command_id=f"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa{60 + index:02d}",
                    message_id=f"cccccccc-cccc-4ccc-8ccc-cccccccccc{60 + index:02d}",
                    sender_session_id=RECEIVER_SESSION_ID,
                    recipient_session_id=SENDER_SESSION_ID,
                    source_refs=[witness],
                    message_kind="reply",
                    reply_to=ask["payload"]["message_id"],
                    artifact_id=f"eeeeeeee-eeee-4eee-8eee-eeeeeeeeee{60 + index:02d}",
                )
                if staged is not None:
                    self.domain.store_blob(witness["sha256"], staged)
                self.domain.store_blob(hashlib.sha256(blob).hexdigest(), blob)
                before_events = self.domain.events(PROJECT_ID, after_stream_seq=0)
                with self.assertRaises(expected_error):
                    self.domain.submit_command(command)
                self.assertEqual(
                    self.domain.events(PROJECT_ID, after_stream_seq=0), before_events
                )
                with closing(sqlite3.connect(self.domain.database_path)) as connection:
                    self.assertIsNone(
                        connection.execute(
                            "SELECT 1 FROM session_messages WHERE message_id = ?",
                            (command["payload"]["message_id"],),
                        ).fetchone()
                    )

    def test_reply_requires_sources_and_preserves_correlation_without_body(self) -> None:
        ask, blob, _ = send_command(
            command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa30",
            message_id="cccccccc-cccc-4ccc-8ccc-cccccccccc30",
            source_refs=[],
            message_kind="ask",
        )
        self.domain.store_blob(hashlib.sha256(blob).hexdigest(), blob)
        self.domain.submit_command(ask)
        reply, reply_blob, _ = send_command(
            command_type="session.message_reply",
            command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa31",
            message_id="cccccccc-cccc-4ccc-8ccc-cccccccccc31",
            sender_session_id=RECEIVER_SESSION_ID,
            recipient_session_id=SENDER_SESSION_ID,
            blob=b"reply body",
            reply_to="cccccccc-cccc-4ccc-8ccc-cccccccccc30",
            source_refs=[source_ref()],
            artifact_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        )
        witness = source_ref()
        self.domain.store_blob(witness["sha256"], canonical_source_blob(witness["entry_id"]))
        reply["payload"]["source_refs"] = [witness]
        self.domain.store_blob(hashlib.sha256(reply_blob).hexdigest(), reply_blob)
        accepted = self.domain.submit_command(reply)
        self.assertEqual(accepted["event"]["event_type"], "session.message_queued")
        self.assertEqual(accepted["event"]["payload"]["reply_to"], ask["payload"]["message_id"])
        self.assertEqual(len(accepted["event"]["payload"]["source_refs"]), 1)

    def test_unknown_command_and_cross_project_write_fail_before_database_changes(self) -> None:
        before = self.domain.events(PROJECT_ID, after_stream_seq=0)
        unknown = session_command(
            "session.unknown",
            command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa40",
            actor_session_id=SENDER_SESSION_ID,
            payload={},
        )
        with self.assertRaises(ContractViolation):
            self.domain.submit_command(unknown)
        cross_project = register_command(
            command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa41",
            project_id=OTHER_PROJECT_ID,
            activity_id=OTHER_ACTIVITY_ID,
        )
        with self.assertRaises(DomainConflict):
            self.domain.submit_command(cross_project)
        self.assertEqual(self.domain.events(PROJECT_ID, after_stream_seq=0), before)


if __name__ == "__main__":
    unittest.main()
