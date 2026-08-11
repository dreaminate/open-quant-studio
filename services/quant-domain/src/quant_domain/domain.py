from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import command_errors, context_capture_errors, domain_event_errors
from .database import Database
from .git_workspace import GitRevisionIdentity, GitWorkspaceError, GitWorkspaceStore


MAX_PROJECT_VARIANTS = 64


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


class ArtifactBlobMissing(DomainConflict):
    code = "artifact_blob_missing"


class ArtifactIntegrityMismatch(DomainConflict):
    code = "artifact_integrity_mismatch"


class SessionIdentityConflict(DomainConflict):
    code = "session_identity_conflict"


class MessageReceiptConflict(DomainConflict):
    code = "message_receipt_conflict"


class MessageAccessDenied(DomainConflict):
    code = "message_access_denied"


class MessageBodyTooLarge(DomainConflict):
    code = "message_body_too_large"


class RevisionConflict(DomainConflict):
    code = "revision_conflict"


class PromotionConflict(DomainConflict):
    code = "promotion_conflict"


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
        self.git_workspace = GitWorkspaceStore(data_root)

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
        errors = command_errors(command)
        if errors:
            raise ContractViolation(errors)

        if command["command_type"] in {
            "workspace.revision_create",
            "strategy.variant_create",
            "workspace.revision_promote",
        }:
            return self._submit_revision_command(command)

        if command["command_type"] != "context.capture":
            return self._submit_session_command(command)

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

    def _submit_revision_command(self, command: dict[str, Any]) -> dict[str, Any]:
        command_hash = hashlib.sha256(canonical_json(command).encode()).hexdigest()
        recorded_at = utc_now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT command_hash, receipt_json FROM command_receipts WHERE command_id = ?",
                (command["command_id"],),
            ).fetchone()
            if existing is not None:
                connection.execute("COMMIT")
                if existing["command_hash"] != command_hash:
                    raise CommandIdConflict(
                        "command_id was already used by another envelope"
                    )
                replayed = json.loads(existing["receipt_json"])
                replayed["disposition"] = "replayed"
                return replayed

            promotion: tuple[str, str, int, int] | None = None
            head_change: tuple[str, int] | None = None
            revision_identity: GitRevisionIdentity | None = None
            try:
                command_type = command["command_type"]
                if command_type == "workspace.revision_create":
                    event, revision_identity = self._create_revision(
                        connection, command, recorded_at
                    )
                    if command["variant_id"] is None:
                        head_change = (command["payload"]["revision_id"], 0)
                elif command_type == "strategy.variant_create":
                    event = self._create_variant(connection, command, recorded_at)
                elif command_type == "workspace.revision_promote":
                    event, promotion = self._promote_revision(
                        connection, command, recorded_at
                    )
                else:
                    raise ContractViolation([f"unsupported command type {command_type}"])

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
                if head_change is None and promotion is not None:
                    head_change = (promotion[1], promotion[3])
                if head_change is not None:
                    connection.execute(
                        """
                        INSERT INTO project_revision_head_history(
                            project_id, head_revision_id, head_version,
                            command_id, event_id, recorded_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            command["project_id"],
                            head_change[0],
                            head_change[1],
                            command["command_id"],
                            event["event_id"],
                            recorded_at,
                        ),
                    )
                if promotion is not None:
                    (
                        previous_revision_id,
                        promoted_revision_id,
                        previous_head_version,
                        resulting_head_version,
                    ) = promotion
                    connection.execute(
                        """
                        INSERT INTO revision_promotions(
                            promotion_id, project_id, activity_id, variant_id,
                            previous_revision_id, promoted_revision_id,
                            previous_head_version, resulting_head_version,
                            command_id, event_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(
                                uuid.uuid5(
                                    uuid.UUID(command["command_id"]),
                                    "workspace.revision_promote",
                                )
                            ),
                            command["project_id"],
                            command["activity_id"],
                            command["variant_id"],
                            previous_revision_id,
                            promoted_revision_id,
                            previous_head_version,
                            resulting_head_version,
                            command["command_id"],
                            event["event_id"],
                            recorded_at,
                        ),
                    )
                self._insert_log(
                    connection,
                    timestamp=recorded_at,
                    level="info",
                    priority="p2",
                    event_code=command_type.replace("_", "."),
                    project_id=command["project_id"],
                    activity_id=command["activity_id"],
                    session_id=command["session_id"],
                    job_id=None,
                    correlation_id=command["correlation_id"],
                    message=(
                        "Workspace revision was created"
                        if command_type == "workspace.revision_create"
                        else "Strategy variant was created"
                        if command_type == "strategy.variant_create"
                        else "Workspace revision was promoted"
                    ),
                )
            except DomainConflict:
                connection.execute("ROLLBACK")
                raise
            except GitWorkspaceError as error:
                connection.execute("ROLLBACK")
                raise RevisionConflict("Git workspace operation failed") from error
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise RevisionConflict(
                    "revision graph constraint rejected the command"
                ) from error
            protected_revision: tuple[str, str, str] | None = None
            if revision_identity is not None:
                try:
                    self.git_workspace.protect_revision(
                        project_id=command["project_id"],
                        revision_id=command["payload"]["revision_id"],
                        commit_oid=revision_identity.commit_oid,
                    )
                    protected_revision = (
                        command["project_id"],
                        command["payload"]["revision_id"],
                        revision_identity.commit_oid,
                    )
                except GitWorkspaceError as error:
                    connection.execute("ROLLBACK")
                    raise RevisionConflict(
                        "Git revision protection failed"
                    ) from error
            try:
                connection.execute("COMMIT")
            except sqlite3.Error:
                connection.execute("ROLLBACK")
                if protected_revision is not None:
                    self.git_workspace.release_revision(
                        project_id=protected_revision[0],
                        revision_id=protected_revision[1],
                        commit_oid=protected_revision[2],
                    )
                raise
        return receipt

    def _create_revision(
        self,
        connection: sqlite3.Connection,
        command: dict[str, Any],
        recorded_at: str,
    ) -> tuple[dict[str, Any], GitRevisionIdentity]:
        self._validate_active_workbench(connection, command)
        payload = command["payload"]
        variant_id = command["variant_id"]
        base_revision_id = command["base_revision_id"]
        parent_commit_oids: list[str] = []
        file_artifacts: dict[str, str] = {}

        existing_revision = connection.execute(
            "SELECT 1 FROM workspace_revisions WHERE revision_id = ?",
            (payload["revision_id"],),
        ).fetchone()
        if existing_revision is not None:
            raise RevisionConflict("revision_id already belongs to immutable state")

        if variant_id is None:
            existing_head = connection.execute(
                "SELECT head_revision_id FROM project_revision_heads WHERE project_id = ?",
                (command["project_id"],),
            ).fetchone()
            if existing_head is not None:
                raise RevisionConflict("project workspace already has a root revision")
        else:
            variant = connection.execute(
                """
                SELECT v.project_id, v.activity_id, h.head_revision_id,
                       r.git_commit_oid
                FROM strategy_variants AS v
                JOIN strategy_variant_heads AS h
                  ON h.variant_id = v.variant_id
                 AND h.project_id = v.project_id
                 AND h.activity_id = v.activity_id
                JOIN workspace_revisions AS r
                  ON r.revision_id = h.head_revision_id
                WHERE v.variant_id = ?
                """,
                (variant_id,),
            ).fetchone()
            if (
                variant is None
                or variant["project_id"] != command["project_id"]
                or variant["activity_id"] != command["activity_id"]
                or variant["head_revision_id"] != base_revision_id
                or command["expected_revision_id"] != base_revision_id
            ):
                raise RevisionConflict("variant head does not match the revision base")
            parent_commit_oids.append(variant["git_commit_oid"])
            file_artifacts.update(
                {
                    row["path"]: row["artifact_id"]
                    for row in connection.execute(
                        """
                        SELECT path, artifact_id
                        FROM revision_files
                        WHERE revision_id = ? AND project_id = ? AND activity_id = ?
                        """,
                        (
                            base_revision_id,
                            command["project_id"],
                            command["activity_id"],
                        ),
                    )
                }
            )

        for file in payload["files"]:
            artifact = file["artifact"]
            self._register_message_artifact(connection, artifact, recorded_at)
            file_artifacts[file["path"]] = artifact["artifact_id"]
        if len(file_artifacts) > 32:
            raise RevisionConflict("workspace revision exceeds the 32-file POC bound")

        file_bytes: dict[str, bytes] = {}
        for path, artifact_id in sorted(file_artifacts.items()):
            artifact = connection.execute(
                "SELECT sha256, byte_size FROM artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            artifact_path = self.blob_path(artifact["sha256"])
            if not artifact_path.exists():
                raise ArtifactBlobMissing("revision file artifact blob is not staged")
            body = artifact_path.read_bytes()
            if (
                hashlib.sha256(body).hexdigest() != artifact["sha256"]
                or len(body) != artifact["byte_size"]
            ):
                raise ArtifactIntegrityMismatch(
                    "revision file bytes do not match registered artifact identity"
                )
            file_bytes[path] = body

        git_identity = self.git_workspace.create_commit(
            project_id=command["project_id"],
            revision_id=payload["revision_id"],
            files=file_bytes,
            parent_commit_oids=parent_commit_oids,
            message=payload["message"],
            recorded_at=recorded_at,
        )
        connection.execute(
            """
            INSERT INTO workspace_revisions(
                revision_id, project_id, activity_id, variant_id,
                base_revision_id, git_commit_oid, git_tree_oid, message,
                created_by_session_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["revision_id"],
                command["project_id"],
                command["activity_id"],
                variant_id,
                base_revision_id,
                git_identity.commit_oid,
                git_identity.tree_oid,
                payload["message"],
                command["session_id"],
                recorded_at,
            ),
        )
        for path, artifact_id in sorted(file_artifacts.items()):
            connection.execute(
                """
                INSERT INTO revision_files(
                    revision_id, project_id, activity_id, path,
                    artifact_id, git_blob_oid
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["revision_id"],
                    command["project_id"],
                    command["activity_id"],
                    path,
                    artifact_id,
                    git_identity.blob_oids[path],
                ),
            )
        if variant_id is None:
            connection.execute(
                """
                INSERT INTO project_revision_heads(
                    project_id, head_revision_id, version, updated_at
                ) VALUES (?, ?, 0, ?)
                """,
                (command["project_id"], payload["revision_id"], recorded_at),
            )
        else:
            updated = connection.execute(
                """
                UPDATE strategy_variant_heads
                SET head_revision_id = ?, version = version + 1, updated_at = ?
                WHERE variant_id = ? AND project_id = ? AND activity_id = ?
                  AND head_revision_id = ?
                """,
                (
                    payload["revision_id"],
                    recorded_at,
                    variant_id,
                    command["project_id"],
                    command["activity_id"],
                    base_revision_id,
                ),
            )
            if updated.rowcount != 1:
                raise RevisionConflict("variant head changed before revision creation")

        event = self._insert_event(
            connection,
            event_type="workspace.revision_created",
            project_id=command["project_id"],
            activity_id=command["activity_id"],
            session_id=command["session_id"],
            workbench_id=command["workbench_id"],
            correlation_id=command["correlation_id"],
            causation_id=command["command_id"],
            recorded_at=recorded_at,
            variant_id=variant_id,
            base_revision_id=base_revision_id,
            payload={
                "revision_id": payload["revision_id"],
                "parent_revision_id": base_revision_id,
                "git_commit_oid": git_identity.commit_oid,
                "git_tree_oid": git_identity.tree_oid,
                "file_count": len(file_artifacts),
            },
        )
        return event, git_identity

    def _create_variant(
        self,
        connection: sqlite3.Connection,
        command: dict[str, Any],
        recorded_at: str,
    ) -> dict[str, Any]:
        self._validate_active_workbench(connection, command)
        base_revision_id = command["base_revision_id"]
        base = connection.execute(
            """
            SELECT revision_id
            FROM workspace_revisions
            WHERE revision_id = ? AND project_id = ? AND activity_id = ?
            """,
            (base_revision_id, command["project_id"], command["activity_id"]),
        ).fetchone()
        if base is None:
            raise RevisionConflict("variant base revision is outside the project activity")
        variant_count = connection.execute(
            "SELECT COUNT(*) FROM strategy_variants WHERE project_id = ?",
            (command["project_id"],),
        ).fetchone()[0]
        if variant_count >= MAX_PROJECT_VARIANTS:
            raise RevisionConflict("project variant limit reached")
        connection.execute(
            """
            INSERT INTO strategy_variants(
                variant_id, project_id, activity_id, base_revision_id,
                created_by_session_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                command["variant_id"],
                command["project_id"],
                command["activity_id"],
                base_revision_id,
                command["session_id"],
                recorded_at,
            ),
        )
        connection.execute(
            """
            INSERT INTO strategy_variant_heads(
                variant_id, project_id, activity_id, head_revision_id,
                version, updated_at
            ) VALUES (?, ?, ?, ?, 0, ?)
            """,
            (
                command["variant_id"],
                command["project_id"],
                command["activity_id"],
                base_revision_id,
                recorded_at,
            ),
        )
        return self._insert_event(
            connection,
            event_type="strategy.variant_created",
            project_id=command["project_id"],
            activity_id=command["activity_id"],
            session_id=command["session_id"],
            workbench_id=command["workbench_id"],
            correlation_id=command["correlation_id"],
            causation_id=command["command_id"],
            recorded_at=recorded_at,
            variant_id=command["variant_id"],
            base_revision_id=base_revision_id,
            payload={
                "variant_id": command["variant_id"],
                "revision_id": base_revision_id,
            },
        )

    def _promote_revision(
        self,
        connection: sqlite3.Connection,
        command: dict[str, Any],
        recorded_at: str,
    ) -> tuple[dict[str, Any], tuple[str, str, int, int]]:
        self._validate_active_workbench(connection, command)
        candidate_revision_id = command["payload"]["candidate_revision_id"]
        if candidate_revision_id == command["expected_revision_id"]:
            raise PromotionConflict("candidate revision is already the project head")
        candidate = connection.execute(
            """
            SELECT r.git_commit_oid, r.git_tree_oid, h.head_revision_id,
                   v.project_id, v.activity_id
            FROM strategy_variants AS v
            JOIN strategy_variant_heads AS h
              ON h.variant_id = v.variant_id
             AND h.project_id = v.project_id
             AND h.activity_id = v.activity_id
            JOIN workspace_revisions AS r
              ON r.revision_id = h.head_revision_id
            WHERE v.variant_id = ?
            """,
            (command["variant_id"],),
        ).fetchone()
        if (
            candidate is None
            or candidate["project_id"] != command["project_id"]
            or candidate["activity_id"] != command["activity_id"]
            or candidate["head_revision_id"] != candidate_revision_id
        ):
            raise PromotionConflict("candidate is not the current variant head")
        project_head = connection.execute(
            """
            SELECT head_revision_id, version
            FROM project_revision_heads
            WHERE project_id = ?
            """,
            (command["project_id"],),
        ).fetchone()
        if (
            project_head is None
            or project_head["head_revision_id"] != command["expected_revision_id"]
        ):
            raise PromotionConflict("project head changed before promotion")
        prior_head = connection.execute(
            """
            SELECT 1
            FROM project_revision_head_history
            WHERE project_id = ? AND head_revision_id = ?
            """,
            (command["project_id"], candidate_revision_id),
        ).fetchone()
        if prior_head is not None:
            raise PromotionConflict("candidate revision was already a project head")
        resulting_head_version = project_head["version"] + 1
        updated = connection.execute(
            """
            UPDATE project_revision_heads
            SET head_revision_id = ?, version = version + 1, updated_at = ?
            WHERE project_id = ? AND head_revision_id = ? AND version = ?
            """,
            (
                candidate_revision_id,
                recorded_at,
                command["project_id"],
                command["expected_revision_id"],
                project_head["version"],
            ),
        )
        if updated.rowcount != 1:
            raise PromotionConflict("project head changed before promotion")
        event = self._insert_event(
            connection,
            event_type="workspace.revision_promoted",
            project_id=command["project_id"],
            activity_id=command["activity_id"],
            session_id=command["session_id"],
            workbench_id=command["workbench_id"],
            correlation_id=command["correlation_id"],
            causation_id=command["command_id"],
            recorded_at=recorded_at,
            variant_id=command["variant_id"],
            base_revision_id=command["base_revision_id"],
            payload={
                "variant_id": command["variant_id"],
                "previous_revision_id": command["expected_revision_id"],
                "promoted_revision_id": candidate_revision_id,
                "git_commit_oid": candidate["git_commit_oid"],
                "git_tree_oid": candidate["git_tree_oid"],
            },
        )
        return event, (
            command["expected_revision_id"],
            candidate_revision_id,
            project_head["version"],
            resulting_head_version,
        )

    def _submit_session_command(self, command: dict[str, Any]) -> dict[str, Any]:
        command_hash = hashlib.sha256(canonical_json(command).encode()).hexdigest()
        recorded_at = utc_now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT command_hash, receipt_json FROM command_receipts WHERE command_id = ?",
                (command["command_id"],),
            ).fetchone()
            if existing is not None:
                connection.execute("COMMIT")
                if existing["command_hash"] != command_hash:
                    raise CommandIdConflict(
                        "command_id was already used by another envelope"
                    )
                replayed = json.loads(existing["receipt_json"])
                replayed["disposition"] = "replayed"
                return replayed

            try:
                command_type = command["command_type"]
                transition: tuple[str, str, int, int] | None = None
                if command_type == "session.register":
                    event = self._register_session(connection, command, recorded_at)
                elif command_type == "session.workbench_bind":
                    event = self._bind_workbench(connection, command, recorded_at)
                elif command_type in {
                    "session.message_send",
                    "session.message_reply",
                }:
                    event = self._queue_message(connection, command, recorded_at)
                elif command_type in {
                    "session.message_receive",
                    "session.message_mark_injected",
                    "session.message_acknowledge",
                }:
                    event, transition = self._transition_message_receipt(
                        connection, command, recorded_at
                    )
                else:
                    raise ContractViolation([f"unsupported command type {command_type}"])

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
                if transition is not None:
                    message_id, from_state, expected_version, resulting_version = transition
                    connection.execute(
                        """
                        INSERT INTO message_receipt_transitions(
                            transition_id, message_id, project_id, activity_id,
                            from_state, to_state, expected_version, resulting_version,
                            command_id, event_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            message_id,
                            command["project_id"],
                            command["activity_id"],
                            from_state,
                            event["payload"]["state"],
                            expected_version,
                            resulting_version,
                            command["command_id"],
                            event["event_id"],
                            recorded_at,
                        ),
                    )
                self._insert_log(
                    connection,
                    timestamp=recorded_at,
                    level="info",
                    priority="p3",
                    event_code=command_type.replace("_", "."),
                    project_id=command["project_id"],
                    activity_id=command["activity_id"],
                    session_id=command["session_id"],
                    job_id=None,
                    correlation_id=command["correlation_id"],
                    message=(
                        "Session was registered"
                        if command_type == "session.register"
                        else "Session workbench was bound"
                        if command_type == "session.workbench_bind"
                        else "Session message state was durably recorded"
                    ),
                )
            except DomainConflict:
                connection.execute("ROLLBACK")
                raise
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise DomainConflict(str(error)) from error
            connection.execute("COMMIT")
        return receipt

    def _register_session(
        self,
        connection: sqlite3.Connection,
        command: dict[str, Any],
        recorded_at: str,
    ) -> dict[str, Any]:
        payload = command["payload"]
        pi_session_id = payload["pi_session_id"]
        expected_uri = f"pi-jsonl://session/{pi_session_id}"
        if payload["session_uri"] != expected_uri:
            raise ContractViolation(["/payload/session_uri must match pi_session_id"])
        connection.execute(
            "INSERT OR IGNORE INTO research_projects(project_id, created_at) VALUES (?, ?)",
            (command["project_id"], recorded_at),
        )
        connection.execute(
            "INSERT OR IGNORE INTO activities(activity_id, project_id, created_at) VALUES (?, ?, ?)",
            (command["activity_id"], command["project_id"], recorded_at),
        )
        existing = connection.execute(
            "SELECT project_id, activity_id, pi_session_id, session_uri FROM agent_sessions WHERE session_id = ?",
            (command["session_id"],),
        ).fetchone()
        if existing is not None:
            raise SessionIdentityConflict("session_id is already registered")
        connection.execute(
            """
            INSERT INTO agent_sessions(
                session_id, project_id, activity_id, pi_session_id, session_uri, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                command["session_id"],
                command["project_id"],
                command["activity_id"],
                pi_session_id,
                payload["session_uri"],
                recorded_at,
            ),
        )
        connection.execute(
            """
            INSERT INTO workbench_bindings(
                project_id, activity_id, session_id, workbench_id,
                is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                command["project_id"],
                command["activity_id"],
                command["session_id"],
                command["workbench_id"],
                recorded_at,
                recorded_at,
            ),
        )
        return self._insert_event(
            connection,
            event_type="session.registered",
            project_id=command["project_id"],
            activity_id=command["activity_id"],
            session_id=command["session_id"],
            workbench_id=command["workbench_id"],
            correlation_id=command["correlation_id"],
            causation_id=command["command_id"],
            recorded_at=recorded_at,
            variant_id=None,
            base_revision_id=None,
            payload={
                "session_id": command["session_id"],
                "pi_session_id": pi_session_id,
                "session_uri": payload["session_uri"],
                "workbench_id": command["workbench_id"],
            },
        )

    def _bind_workbench(
        self,
        connection: sqlite3.Connection,
        command: dict[str, Any],
        recorded_at: str,
    ) -> dict[str, Any]:
        payload = command["payload"]
        session = connection.execute(
            """
            SELECT project_id, activity_id
            FROM agent_sessions
            WHERE session_id = ?
            """,
            (command["session_id"],),
        ).fetchone()
        if session is None:
            raise SessionIdentityConflict("session is not registered")
        if (
            session["project_id"] != command["project_id"]
            or session["activity_id"] != command["activity_id"]
        ):
            raise SessionIdentityConflict("session identity is outside the project activity")
        if payload["workbench_id"] != command["workbench_id"]:
            raise ContractViolation(["/payload/workbench_id must match /workbench_id"])

        connection.execute(
            """
            UPDATE workbench_bindings
            SET is_active = 0, updated_at = ?
            WHERE project_id = ? AND activity_id = ? AND session_id = ?
              AND is_active = 1
            """,
            (
                recorded_at,
                command["project_id"],
                command["activity_id"],
                command["session_id"],
            ),
        )
        existing = connection.execute(
            """
            SELECT 1
            FROM workbench_bindings
            WHERE project_id = ? AND activity_id = ? AND session_id = ?
              AND workbench_id = ?
            """,
            (
                command["project_id"],
                command["activity_id"],
                command["session_id"],
                command["workbench_id"],
            ),
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO workbench_bindings(
                    project_id, activity_id, session_id, workbench_id,
                    is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    command["project_id"],
                    command["activity_id"],
                    command["session_id"],
                    command["workbench_id"],
                    recorded_at,
                    recorded_at,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE workbench_bindings
                SET is_active = 1, updated_at = ?
                WHERE project_id = ? AND activity_id = ? AND session_id = ?
                  AND workbench_id = ?
                """,
                (
                    recorded_at,
                    command["project_id"],
                    command["activity_id"],
                    command["session_id"],
                    command["workbench_id"],
                ),
            )
        return self._insert_event(
            connection,
            event_type="session.workbench_bound",
            project_id=command["project_id"],
            activity_id=command["activity_id"],
            session_id=command["session_id"],
            workbench_id=command["workbench_id"],
            correlation_id=command["correlation_id"],
            causation_id=command["command_id"],
            recorded_at=recorded_at,
            variant_id=None,
            base_revision_id=None,
            payload={
                "session_id": command["session_id"],
                "workbench_id": command["workbench_id"],
            },
        )

    def _validate_active_workbench(
        self,
        connection: sqlite3.Connection,
        command: dict[str, Any],
    ) -> None:
        binding = connection.execute(
            """
            SELECT workbench_id
            FROM workbench_bindings
            WHERE project_id = ? AND activity_id = ? AND session_id = ?
              AND is_active = 1
            """,
            (
                command["project_id"],
                command["activity_id"],
                command["session_id"],
            ),
        ).fetchone()
        if binding is None or binding["workbench_id"] != command["workbench_id"]:
            raise DomainConflict("command workbench is not the session's active binding")

    def _register_message_artifact(
        self,
        connection: sqlite3.Connection,
        artifact: dict[str, Any],
        recorded_at: str,
    ) -> None:
        if artifact["media_type"] != "text/plain":
            raise ContractViolation(["/payload/artifact/media_type must be text/plain"])
        if artifact["byte_size"] > 64 * 1024:
            raise ContractViolation(["/payload/artifact/byte_size exceeds 65536"])
        path = self.blob_path(artifact["sha256"])
        if not path.exists():
            raise ArtifactBlobMissing("message artifact blob is not staged")
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != artifact["sha256"] or len(body) != artifact["byte_size"]:
            raise ArtifactIntegrityMismatch("message artifact bytes do not match registered identity")
        try:
            body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ArtifactIntegrityMismatch("message artifact body is not valid UTF-8") from error
        existing = connection.execute(
            "SELECT sha256, media_type, byte_size, storage_uri, producing_revision_id, producing_run_id, origin_kind, source_ref FROM artifacts WHERE artifact_id = ?",
            (artifact["artifact_id"],),
        ).fetchone()
        expected = (
            artifact["sha256"],
            artifact["media_type"],
            artifact["byte_size"],
            artifact["storage_uri"],
            artifact["producing_revision_id"],
            artifact["producing_run_id"],
            artifact["provenance"]["origin_kind"],
            artifact["provenance"]["source_ref"],
        )
        if existing is not None:
            if tuple(existing) != expected:
                raise DomainConflict("artifact_id is already registered with different metadata")
            return
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

    def _queue_message(
        self,
        connection: sqlite3.Connection,
        command: dict[str, Any],
        recorded_at: str,
    ) -> dict[str, Any]:
        payload = command["payload"]
        artifact = payload["artifact"]
        self._validate_active_workbench(connection, command)
        self._validate_source_refs(connection, command, payload["source_refs"])
        if payload["reply_to"] is not None:
            parent = connection.execute(
                "SELECT message_id, project_id, activity_id, sender_session_id, recipient_session_id, message_kind, correlation_id FROM session_messages WHERE message_id = ?",
                (payload["reply_to"],),
            ).fetchone()
            if parent is None or parent["project_id"] != command["project_id"] or parent["activity_id"] != command["activity_id"]:
                raise DomainConflict("reply_to message is outside the project activity")
            if parent["message_kind"] != "ask":
                raise DomainConflict("reply_to message must be an ask")
            if (
                command["session_id"] != parent["recipient_session_id"]
                or payload["recipient_session_id"] != parent["sender_session_id"]
            ):
                raise DomainConflict("reply sender and recipient must reverse the ask")
            if command["correlation_id"] != parent["correlation_id"]:
                raise DomainConflict("reply correlation_id must match the ask")
        self._register_message_artifact(connection, artifact, recorded_at)
        connection.execute(
            """
            INSERT INTO session_messages(
                message_id, project_id, activity_id, sender_session_id,
                recipient_session_id, correlation_id, message_kind, artifact_id,
                reply_to, source_refs_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["message_id"],
                command["project_id"],
                command["activity_id"],
                command["session_id"],
                payload["recipient_session_id"],
                command["correlation_id"],
                payload["message_kind"],
                artifact["artifact_id"],
                payload["reply_to"],
                canonical_json(payload["source_refs"]),
                recorded_at,
            ),
        )
        connection.execute(
            """
            INSERT INTO message_receipts(
                message_id, project_id, activity_id, state, version, created_at, updated_at
            ) VALUES (?, ?, ?, 'queued', 0, ?, ?)
            """,
            (
                payload["message_id"],
                command["project_id"],
                command["activity_id"],
                recorded_at,
                recorded_at,
            ),
        )
        return self._insert_event(
            connection,
            event_type="session.message_queued",
            project_id=command["project_id"],
            activity_id=command["activity_id"],
            session_id=command["session_id"],
            workbench_id=command["workbench_id"],
            correlation_id=command["correlation_id"],
            causation_id=command["command_id"],
            recorded_at=recorded_at,
            variant_id=None,
            base_revision_id=None,
            payload={
                "message_id": payload["message_id"],
                "recipient_session_id": payload["recipient_session_id"],
                "message_kind": payload["message_kind"],
                "artifact_id": artifact["artifact_id"],
                "artifact_sha256": artifact["sha256"],
                "state": "queued",
                "receipt_version": 0,
                "reply_to": payload["reply_to"],
                "source_refs": payload["source_refs"],
            },
        )

    def _validate_source_refs(
        self,
        connection: sqlite3.Connection,
        command: dict[str, Any],
        source_refs: list[dict[str, Any]],
    ) -> None:
        for source in source_refs:
            session = connection.execute(
                "SELECT project_id, activity_id, pi_session_id FROM agent_sessions WHERE session_id = ?",
                (source["session_id"],),
            ).fetchone()
            if session is None:
                raise DomainConflict("source reference session is not registered")
            if (
                session["project_id"] != command["project_id"]
                or session["activity_id"] != command["activity_id"]
            ):
                raise DomainConflict("source reference crosses project or activity boundary")
            expected_uri = (
                f"pi-jsonl://session/{session['pi_session_id']}#entry={source['entry_id']}"
            )
            if source["source_uri"] != expected_uri:
                raise DomainConflict("source reference URI does not match its session identity")
            path = self.blob_path(source["sha256"])
            if not path.exists():
                raise ArtifactBlobMissing("source reference witness blob is not staged")
            body = path.read_bytes()
            if hashlib.sha256(body).hexdigest() != source["sha256"]:
                raise ArtifactIntegrityMismatch(
                    "source reference witness bytes do not match its SHA-256"
                )
            try:
                decoded = body.decode("utf-8")
                witness = json.loads(decoded)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ArtifactIntegrityMismatch(
                    "source reference witness is not valid UTF-8 JSON"
                ) from error
            if not isinstance(witness, dict):
                raise ArtifactIntegrityMismatch(
                    "source reference witness must be a JSON object"
                )
            if witness.get("id") != source["entry_id"]:
                raise ArtifactIntegrityMismatch(
                    "source reference witness id does not match entry_id"
                )

    def _transition_message_receipt(
        self,
        connection: sqlite3.Connection,
        command: dict[str, Any],
        recorded_at: str,
    ) -> tuple[dict[str, Any], tuple[str, str, int, int]]:
        transitions = {
            "session.message_receive": (
                "queued",
                "receiver_received",
                "session.message_receiver_received",
            ),
            "session.message_mark_injected": (
                "receiver_received",
                "injected",
                "session.message_injected",
            ),
            "session.message_acknowledge": (
                "injected",
                "acknowledged",
                "session.message_acknowledged",
            ),
        }
        required_state, next_state, event_type = transitions[command["command_type"]]
        payload = command["payload"]
        row = connection.execute(
            """
            SELECT m.*, r.state, r.version
            FROM session_messages AS m
            JOIN message_receipts AS r
              ON r.message_id = m.message_id
             AND r.project_id = m.project_id
             AND r.activity_id = m.activity_id
            WHERE m.message_id = ? AND m.project_id = ? AND m.activity_id = ?
            """,
            (payload["message_id"], command["project_id"], command["activity_id"]),
        ).fetchone()
        if row is None:
            raise MessageReceiptConflict("message receipt does not exist")
        self._validate_active_workbench(connection, command)
        if row["recipient_session_id"] != command["session_id"]:
            raise MessageAccessDenied("only the recipient session may transition a receipt")
        if command["correlation_id"] != row["correlation_id"]:
            raise MessageReceiptConflict("message receipt correlation_id is immutable")
        if (
            payload["expected_state"] != required_state
            or payload["expected_version"] != row["version"]
            or row["state"] != required_state
        ):
            raise MessageReceiptConflict("message receipt expected state or version is stale")
        resulting_version = row["version"] + 1
        updated = connection.execute(
            """
            UPDATE message_receipts
            SET state = ?, version = ?, updated_at = ?
            WHERE message_id = ? AND project_id = ? AND activity_id = ?
              AND state = ? AND version = ?
            """,
            (
                next_state,
                resulting_version,
                recorded_at,
                payload["message_id"],
                command["project_id"],
                command["activity_id"],
                required_state,
                payload["expected_version"],
            ),
        )
        if updated.rowcount != 1:
            raise MessageReceiptConflict("message receipt expected state or version is stale")
        source_refs = json.loads(row["source_refs_json"])
        event = self._insert_event(
            connection,
            event_type=event_type,
            project_id=command["project_id"],
            activity_id=command["activity_id"],
            session_id=command["session_id"],
            workbench_id=command["workbench_id"],
            correlation_id=command["correlation_id"],
            causation_id=command["command_id"],
            recorded_at=recorded_at,
            variant_id=None,
            base_revision_id=None,
            payload={
                "message_id": row["message_id"],
                "recipient_session_id": row["recipient_session_id"],
                "message_kind": row["message_kind"],
                "artifact_id": row["artifact_id"],
                "artifact_sha256": connection.execute(
                    "SELECT sha256 FROM artifacts WHERE artifact_id = ?",
                    (row["artifact_id"],),
                ).fetchone()[0],
                "state": next_state,
                "receipt_version": resulting_version,
                "reply_to": row["reply_to"],
                "source_refs": source_refs,
            },
        )
        return event, (
            payload["message_id"],
            required_state,
            payload["expected_version"],
            resulting_version,
        )

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

    def sessions(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.session_id, s.project_id, s.activity_id,
                       s.pi_session_id, s.session_uri, s.created_at,
                       w.workbench_id, w.is_active
                FROM agent_sessions AS s
                LEFT JOIN workbench_bindings AS w
                  ON w.project_id = s.project_id
                 AND w.activity_id = s.activity_id
                 AND w.session_id = s.session_id
                WHERE s.project_id = ?
                ORDER BY s.created_at, s.session_id, w.workbench_id
                """,
                (project_id,),
            ).fetchall()
        sessions: dict[str, dict[str, Any]] = {}
        for row in rows:
            session = sessions.setdefault(
                row["session_id"],
                {
                    "session_id": row["session_id"],
                    "project_id": row["project_id"],
                    "activity_id": row["activity_id"],
                    "pi_session_id": row["pi_session_id"],
                    "session_uri": row["session_uri"],
                    "created_at": row["created_at"],
                    "workbench_ids": [],
                    "active_workbench_id": None,
                },
            )
            if row["workbench_id"] is not None:
                session["workbench_ids"].append(row["workbench_id"])
                if row["is_active"] == 1:
                    session["active_workbench_id"] = row["workbench_id"]
        return list(sessions.values())

    def revision(
        self, project_id: str, revision_id: str
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT revision_id, project_id, activity_id, variant_id,
                       base_revision_id, git_commit_oid, git_tree_oid, message,
                       created_by_session_id, created_at
                FROM workspace_revisions
                WHERE project_id = ? AND revision_id = ?
                """,
                (project_id, revision_id),
            ).fetchone()
            if row is None:
                return None
            files = connection.execute(
                """
                SELECT f.path, f.artifact_id, f.git_blob_oid,
                       a.sha256, a.byte_size, a.media_type, a.storage_uri
                FROM revision_files AS f
                JOIN artifacts AS a ON a.artifact_id = f.artifact_id
                WHERE f.project_id = ? AND f.revision_id = ?
                ORDER BY f.path
                """,
                (project_id, revision_id),
            ).fetchall()
        detail = dict(row)
        detail["files"] = [dict(file) for file in files]
        return detail

    def variants(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT v.variant_id, v.project_id, v.activity_id,
                       v.base_revision_id, v.created_by_session_id,
                       v.created_at, h.head_revision_id, h.version,
                       h.updated_at
                FROM strategy_variants AS v
                JOIN strategy_variant_heads AS h
                  ON h.variant_id = v.variant_id
                 AND h.project_id = v.project_id
                 AND h.activity_id = v.activity_id
                WHERE v.project_id = ?
                ORDER BY v.created_at, v.variant_id
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def project_head(self, project_id: str) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT head_revision_id
                FROM project_revision_heads
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
        return None if row is None else row["head_revision_id"]

    def compare_revisions(
        self,
        project_id: str,
        left_revision_id: str,
        right_revision_id: str,
    ) -> dict[str, Any]:
        left = self.revision(project_id, left_revision_id)
        right = self.revision(project_id, right_revision_id)
        if left is None or right is None:
            raise RevisionConflict("revision comparison is outside the project")
        left_files = {file["path"]: file for file in left["files"]}
        right_files = {file["path"]: file for file in right["files"]}
        changes = []
        for path in sorted(left_files.keys() | right_files.keys()):
            left_file = left_files.get(path)
            right_file = right_files.get(path)
            if left_file is not None and right_file is not None:
                if left_file["artifact_id"] == right_file["artifact_id"]:
                    continue
            changes.append(
                {
                    "path": path,
                    "left_artifact_id": (
                        None if left_file is None else left_file["artifact_id"]
                    ),
                    "left_sha256": (
                        None if left_file is None else left_file["sha256"]
                    ),
                    "right_artifact_id": (
                        None if right_file is None else right_file["artifact_id"]
                    ),
                    "right_sha256": (
                        None if right_file is None else right_file["sha256"]
                    ),
                }
            )
        return {
            "project_id": project_id,
            "left_revision_id": left_revision_id,
            "right_revision_id": right_revision_id,
            "changes": changes,
        }

    def inbox(
        self,
        project_id: str,
        session_id: str,
        *,
        after: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT e.stream_seq, m.message_id, m.project_id, m.activity_id,
                       m.sender_session_id, m.recipient_session_id,
                       m.correlation_id, m.message_kind, m.artifact_id,
                       a.sha256 AS artifact_sha256, m.reply_to,
                       m.source_refs_json, m.created_at,
                       r.state, r.version
                FROM session_messages AS m
                JOIN message_receipts AS r
                  ON r.message_id = m.message_id
                 AND r.project_id = m.project_id
                 AND r.activity_id = m.activity_id
                JOIN artifacts AS a ON a.artifact_id = m.artifact_id
                JOIN domain_events AS e
                  ON e.project_id = m.project_id
                 AND e.activity_id = m.activity_id
                 AND e.event_type = 'session.message_queued'
                 AND json_extract(e.payload_json, '$.message_id') = m.message_id
                WHERE m.project_id = ?
                  AND m.recipient_session_id = ?
                  AND e.stream_seq > ?
                ORDER BY e.stream_seq
                LIMIT ?
                """,
                (project_id, session_id, after, limit),
            ).fetchall()
        return [
            {
                "inbox_seq": row["stream_seq"],
                "message_id": row["message_id"],
                "project_id": row["project_id"],
                "activity_id": row["activity_id"],
                "sender_session_id": row["sender_session_id"],
                "recipient_session_id": row["recipient_session_id"],
                "correlation_id": row["correlation_id"],
                "message_kind": row["message_kind"],
                "artifact_id": row["artifact_id"],
                "artifact_sha256": row["artifact_sha256"],
                "reply_to": row["reply_to"],
                "source_refs": json.loads(row["source_refs_json"]),
                "created_at": row["created_at"],
                "state": row["state"],
                "receipt_version": row["version"],
            }
            for row in rows
        ]

    def message(
        self,
        message_id: str,
        *,
        project_id: str,
        recipient_session_id: str,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT m.*, r.state, r.version,
                       a.sha256 AS artifact_sha256, a.byte_size, a.media_type,
                       a.storage_uri, e.stream_seq AS inbox_seq
                FROM session_messages AS m
                JOIN message_receipts AS r
                  ON r.message_id = m.message_id
                 AND r.project_id = m.project_id
                 AND r.activity_id = m.activity_id
                JOIN artifacts AS a ON a.artifact_id = m.artifact_id
                JOIN domain_events AS e
                  ON e.project_id = m.project_id
                 AND e.activity_id = m.activity_id
                 AND e.event_type = 'session.message_queued'
                 AND json_extract(e.payload_json, '$.message_id') = m.message_id
                WHERE m.message_id = ? AND m.project_id = ?
                """,
                (message_id, project_id),
            ).fetchone()
            if row is None:
                return None
            if row["recipient_session_id"] != recipient_session_id:
                raise MessageAccessDenied("message recipient identity does not match")
        if row["media_type"] != "text/plain":
            raise ArtifactIntegrityMismatch("message artifact media type is not text/plain")
        if row["byte_size"] > 64 * 1024:
            raise MessageBodyTooLarge("message body exceeds the bounded retrieval limit")
        path = self.blob_path(row["artifact_sha256"])
        if not path.exists():
            raise ArtifactBlobMissing("message artifact blob is not staged")
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != row["artifact_sha256"] or len(body) != row["byte_size"]:
            raise ArtifactIntegrityMismatch("message artifact bytes do not match registered identity")
        try:
            decoded = body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise DomainConflict("message artifact body is not valid UTF-8") from error
        return {
            "message_id": row["message_id"],
            "project_id": row["project_id"],
            "activity_id": row["activity_id"],
            "sender_session_id": row["sender_session_id"],
            "recipient_session_id": row["recipient_session_id"],
            "correlation_id": row["correlation_id"],
            "message_kind": row["message_kind"],
            "artifact_id": row["artifact_id"],
            "artifact_sha256": row["artifact_sha256"],
            "reply_to": row["reply_to"],
            "source_refs": json.loads(row["source_refs_json"]),
            "inbox_seq": row["inbox_seq"],
            "created_at": row["created_at"],
            "state": row["state"],
            "receipt_version": row["version"],
            "body": decoded,
        }

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
