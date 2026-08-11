from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import context_capture_errors, domain_event_errors
from .database import Database


class ContractViolation(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("command contract violation")
        self.errors = errors


class DomainConflict(RuntimeError):
    code = "domain_conflict"


class CommandIdConflict(DomainConflict):
    code = "command_id_conflict"


class ContextConflict(DomainConflict):
    code = "context_conflict"


class JobTransitionConflict(DomainConflict):
    code = "job_transition_conflict"


class BlobHashMismatch(ValueError):
    pass


class DomainEventContractError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class QuantDomain:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.database_path = data_root / "quant-domain.sqlite3"
        self.database = Database(self.database_path)

    def blob_path(self, sha256: str) -> Path:
        return self.data_root / "artifacts" / "sha256" / sha256[:2] / sha256

    def store_blob(self, expected_sha256: str, body: bytes) -> dict[str, object]:
        actual_sha256 = hashlib.sha256(body).hexdigest()
        if actual_sha256 != expected_sha256:
            raise BlobHashMismatch("request body does not match the SHA-256 path")
        destination = self.blob_path(actual_sha256)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4()}.tmp")
        temporary.write_bytes(body)
        temporary.replace(destination)
        return {
            "sha256": actual_sha256,
            "byte_size": len(body),
            "storage_uri": f"cas://sha256/{actual_sha256}",
        }

    def submit_command(self, command: dict[str, Any]) -> dict[str, Any]:
        errors = context_capture_errors(command)
        if errors:
            raise ContractViolation(errors)

        command_hash = hashlib.sha256(canonical_json(command).encode()).hexdigest()
        recorded_at = utc_now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            receipt_row = connection.execute(
                "SELECT command_hash, receipt_json FROM command_receipts WHERE command_id = ?",
                (command["command_id"],),
            ).fetchone()
            if receipt_row is not None:
                connection.execute("COMMIT")
                if receipt_row["command_hash"] != command_hash:
                    raise CommandIdConflict("command_id was already used by another envelope")
                receipt = json.loads(receipt_row["receipt_json"])
                receipt["disposition"] = "replayed"
                return receipt

            try:
                connection.execute(
                    "INSERT OR IGNORE INTO research_projects(project_id, created_at) VALUES (?, ?)",
                    (command["project_id"], recorded_at),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO activities(activity_id, project_id, created_at) VALUES (?, ?, ?)",
                    (command["activity_id"], command["project_id"], recorded_at),
                )
                artifact = command["payload"]["artifact"]
                connection.execute(
                    """
                    INSERT INTO artifacts(
                        artifact_id, sha256, media_type, byte_size, storage_uri,
                        producing_revision_id, producing_run_id, origin_kind,
                        source_ref, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact["artifact_id"],
                        artifact["sha256"],
                        artifact["media_type"],
                        artifact["byte_size"],
                        artifact["storage_uri"],
                        artifact["producing_revision_id"],
                        artifact["producing_run_id"],
                        artifact["provenance"]["origin_kind"],
                        artifact["provenance"]["source_ref"],
                        recorded_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO context_items(
                        context_item_id, project_id, activity_id, title,
                        trust_state, artifact_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        command["payload"]["context_item_id"],
                        command["project_id"],
                        command["activity_id"],
                        command["payload"]["title"],
                        command["payload"]["trust_state"],
                        artifact["artifact_id"],
                        recorded_at,
                    ),
                )
                event = self._insert_event(
                    connection,
                    event_type="context.captured",
                    project_id=command["project_id"],
                    activity_id=command["activity_id"],
                    session_id=command["session_id"],
                    workbench_id=command["workbench_id"],
                    correlation_id=command["correlation_id"],
                    causation_id=command["command_id"],
                    recorded_at=recorded_at,
                    variant_id=command["variant_id"],
                    base_revision_id=command["base_revision_id"],
                    payload=command["payload"],
                )
                self._insert_outbox(connection, event)
                receipt = {
                    "command_id": command["command_id"],
                    "disposition": "accepted",
                    "event": event,
                }
                connection.execute(
                    """
                    INSERT INTO command_receipts(
                        command_id, command_hash, event_id, receipt_json, recorded_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        command["command_id"],
                        command_hash,
                        event["event_id"],
                        canonical_json(receipt),
                        recorded_at,
                    ),
                )
                job_id = str(
                    uuid.uuid5(
                        uuid.UUID(command["command_id"]), "artifact.verify_sha256"
                    )
                )
                connection.execute(
                    """
                    INSERT INTO jobs(
                        job_id, command_id, job_type, project_id, activity_id,
                        session_id, workbench_id, correlation_id, artifact_id,
                        status, created_at
                    ) VALUES (?, ?, 'artifact.verify_sha256', ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        job_id,
                        command["command_id"],
                        command["project_id"],
                        command["activity_id"],
                        command["session_id"],
                        command["workbench_id"],
                        command["correlation_id"],
                        artifact["artifact_id"],
                        recorded_at,
                    ),
                )
                self._insert_log(
                    connection,
                    timestamp=recorded_at,
                    level="info",
                    priority="p3",
                    event_code="context.capture.accepted",
                    project_id=command["project_id"],
                    activity_id=command["activity_id"],
                    session_id=command["session_id"],
                    job_id=None,
                    correlation_id=command["correlation_id"],
                    message="Context evidence was captured",
                )
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                if "context_items.context_item_id" in str(error):
                    raise ContextConflict(
                        "context_item_id already belongs to immutable evidence"
                    ) from error
                raise DomainConflict(str(error)) from error
            connection.execute("COMMIT")
        return receipt

    def run_next_job(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            claimed = connection.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'pending'
                ORDER BY created_at, job_id
                LIMIT 1
                """
            ).fetchone()
            if claimed is None:
                connection.execute("COMMIT")
                return None
            started_at = utc_now()
            transition = connection.execute(
                """
                UPDATE jobs
                SET status = 'running', attempts = attempts + 1, started_at = ?
                WHERE job_id = ? AND status = 'pending'
                """,
                (started_at, claimed["job_id"]),
            )
            if transition.rowcount != 1:
                connection.execute("ROLLBACK")
                raise JobTransitionConflict("pending job claim was lost")
            started_event = self._insert_event(
                connection,
                event_type="artifact.verification_started",
                project_id=claimed["project_id"],
                activity_id=claimed["activity_id"],
                session_id=claimed["session_id"],
                workbench_id=claimed["workbench_id"],
                correlation_id=claimed["correlation_id"],
                causation_id=claimed["job_id"],
                recorded_at=started_at,
                variant_id=None,
                base_revision_id=None,
                payload={
                    "artifact_id": claimed["artifact_id"],
                    "job_id": claimed["job_id"],
                    "result": None,
                    "error_code": None,
                },
            )
            self._insert_outbox(connection, started_event)
            connection.execute("COMMIT")

        with self.database.connect() as connection:
            artifact = connection.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ?",
                (claimed["artifact_id"],),
            ).fetchone()
        path = self.blob_path(artifact["sha256"])
        if not path.exists():
            return self._finish_job(
                claimed,
                status="failed",
                result=None,
                error_code="artifact_blob_missing",
                error_message="Content-addressed artifact blob is missing",
            )

        body = path.read_bytes()
        actual_sha256 = hashlib.sha256(body).hexdigest()
        if actual_sha256 != artifact["sha256"] or len(body) != artifact["byte_size"]:
            return self._finish_job(
                claimed,
                status="failed",
                result=None,
                error_code="artifact_integrity_mismatch",
                error_message="Artifact bytes do not match registered identity",
            )

        return self._finish_job(
            claimed,
            status="succeeded",
            result={"sha256": actual_sha256, "byte_size": len(body)},
            error_code=None,
            error_message=None,
        )

    def _finish_job(
        self,
        claimed: sqlite3.Row,
        *,
        status: str,
        result: dict[str, object] | None,
        error_code: str | None,
        error_message: str | None,
    ) -> dict[str, Any]:
        finished_at = utc_now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            transition = connection.execute(
                """
                UPDATE jobs
                SET status = ?, result_json = ?, error_code = ?,
                    error_message = ?, finished_at = ?
                WHERE job_id = ? AND status = 'running'
                """,
                (
                    status,
                    canonical_json(result) if result is not None else None,
                    error_code,
                    error_message,
                    finished_at,
                    claimed["job_id"],
                ),
            )
            if transition.rowcount != 1:
                connection.execute("ROLLBACK")
                raise JobTransitionConflict("running job completion was stale")
            event_type = f"artifact.verification_{status}"
            payload = {
                "artifact_id": claimed["artifact_id"],
                "job_id": claimed["job_id"],
                "result": result,
                "error_code": error_code,
            }
            event = self._insert_event(
                connection,
                event_type=event_type,
                project_id=claimed["project_id"],
                activity_id=claimed["activity_id"],
                session_id=claimed["session_id"],
                workbench_id=claimed["workbench_id"],
                correlation_id=claimed["correlation_id"],
                causation_id=claimed["job_id"],
                recorded_at=finished_at,
                variant_id=None,
                base_revision_id=None,
                payload=payload,
            )
            self._insert_outbox(connection, event)
            self._insert_log(
                connection,
                timestamp=finished_at,
                level="info" if status == "succeeded" else "error",
                priority="p3" if status == "succeeded" else "p2",
                event_code=f"artifact.verification.{status}",
                project_id=claimed["project_id"],
                activity_id=claimed["activity_id"],
                session_id=claimed["session_id"],
                job_id=claimed["job_id"],
                correlation_id=claimed["correlation_id"],
                message=(
                    "Artifact integrity was verified"
                    if status == "succeeded"
                    else "Artifact integrity verification failed"
                ),
            )
            connection.execute("COMMIT")
        return self.job(claimed["job_id"])

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "job_id": row["job_id"],
            "job_type": row["job_type"],
            "status": row["status"],
            "attempts": row["attempts"],
            "result": json.loads(row["result_json"])
            if row["result_json"] is not None
            else None,
            "error_code": row["error_code"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    def events(self, project_id: str, *, after_stream_seq: int) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM domain_events
                WHERE project_id = ? AND stream_seq > ?
                ORDER BY stream_seq
                """,
                (project_id, after_stream_seq),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def logs(
        self,
        *,
        project_id: str | None = None,
        level: str | None = None,
        priority: str | None = None,
    ) -> list[dict[str, Any]]:
        predicates: list[str] = []
        parameters: list[str] = []
        if project_id is not None:
            predicates.append("project_id = ?")
            parameters.append(project_id)
        if level is not None:
            predicates.append("level = ?")
            parameters.append(level)
        if priority is not None:
            predicates.append("priority = ?")
            parameters.append(priority)
        where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT timestamp, level, priority, component, event_code,
                       project_id, activity_id, session_id, task_id, job_id,
                       run_id, correlation_id, message
                FROM diagnostic_logs
                {where}
                ORDER BY timestamp, log_id
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        *,
        event_type: str,
        project_id: str,
        activity_id: str,
        session_id: str | None,
        workbench_id: str | None,
        correlation_id: str,
        causation_id: str,
        recorded_at: str,
        variant_id: str | None,
        base_revision_id: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        event_id = str(uuid.uuid4())
        cursor = connection.execute(
            """
            INSERT INTO domain_events(
                event_id, schema_version, event_type, project_id, activity_id,
                session_id, workbench_id, correlation_id, causation_id,
                recorded_at, variant_id, base_revision_id, payload_json
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_type,
                project_id,
                activity_id,
                session_id,
                workbench_id,
                correlation_id,
                causation_id,
                recorded_at,
                variant_id,
                base_revision_id,
                canonical_json(payload),
            ),
        )
        event = {
            "event_id": event_id,
            "stream_seq": cursor.lastrowid,
            "schema_version": 1,
            "event_type": event_type,
            "project_id": project_id,
            "activity_id": activity_id,
            "session_id": session_id,
            "workbench_id": workbench_id,
            "correlation_id": correlation_id,
            "causation_id": causation_id,
            "recorded_at": recorded_at,
            "variant_id": variant_id,
            "base_revision_id": base_revision_id,
            "payload": payload,
        }
        errors = domain_event_errors(event)
        if errors:
            raise DomainEventContractError("; ".join(errors))
        return event

    def _event_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "stream_seq": row["stream_seq"],
            "schema_version": row["schema_version"],
            "event_type": row["event_type"],
            "project_id": row["project_id"],
            "activity_id": row["activity_id"],
            "session_id": row["session_id"],
            "workbench_id": row["workbench_id"],
            "correlation_id": row["correlation_id"],
            "causation_id": row["causation_id"],
            "recorded_at": row["recorded_at"],
            "variant_id": row["variant_id"],
            "base_revision_id": row["base_revision_id"],
            "payload": json.loads(row["payload_json"]),
        }

    def _insert_outbox(
        self, connection: sqlite3.Connection, event: dict[str, Any]
    ) -> None:
        connection.execute(
            """
            INSERT INTO outbox(event_id, stream_seq, recorded_at)
            VALUES (?, ?, ?)
            """,
            (event["event_id"], event["stream_seq"], event["recorded_at"]),
        )

    def _insert_log(
        self,
        connection: sqlite3.Connection,
        *,
        timestamp: str,
        level: str,
        priority: str,
        event_code: str,
        project_id: str | None,
        activity_id: str | None,
        session_id: str | None,
        job_id: str | None,
        correlation_id: str | None,
        message: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO diagnostic_logs(
                log_id, timestamp, level, priority, component, event_code,
                project_id, activity_id, session_id, task_id, job_id, run_id,
                correlation_id, message
            ) VALUES (?, ?, ?, ?, 'quant-domain', ?, ?, ?, ?, NULL, ?, NULL, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                timestamp,
                level,
                priority,
                event_code,
                project_id,
                activity_id,
                session_id,
                job_id,
                correlation_id,
                message,
            ),
        )
