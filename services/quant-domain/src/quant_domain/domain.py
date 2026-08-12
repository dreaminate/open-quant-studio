from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import command_errors, context_capture_errors, domain_event_errors
from .data_import import (
    DataImportValidationError,
    build_data_snapshot,
    deterministic_artifact_id,
    preview_data_import,
)
from .database import Database
from .formal_runner import execute_formal_run, run_strategy_host
from .forward_replay import replay_forward_test
from .git_workspace import GitRevisionIdentity, GitWorkspaceError, GitWorkspaceStore
from .project_archive import ProjectArchiveError, import_project_archive
from .run_report import build_run_report, canonical_report_json, render_run_report_html


MAX_PROJECT_VARIANTS = 64
DEFAULT_DEBUG_RETENTION_DAYS = 7
DEFAULT_INFO_RETENTION_DAYS = 30
DEFAULT_WARN_RETENTION_DAYS = 90
DEFAULT_DIAGNOSTIC_LOG_QUOTA_BYTES = 2_147_483_648


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


class FormalRunLifecycleConflict(DomainConflict):
    code = "formal_run_lifecycle_conflict"


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
        self.apply_log_retention()

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
            "workspace.merge_create",
            "workspace.revision_promote",
        }:
            return self._submit_revision_command(command)

        if command["command_type"] in {
            "formal.run_request",
            "formal.run_cancel",
            "formal.run_retry",
        }:
            return self._submit_formal_run_command(command)

        if command["command_type"] in {
            "diagnostic.log_delete",
            "diagnostic.log_retention_configure",
        }:
            return self._submit_diagnostic_command(command)

        if command["command_type"] == "forward_test.request":
            return self._submit_forward_test_command(command)

        if command["command_type"] == "project.archive_import":
            return self._submit_project_archive_import(command)

        if command["command_type"] == "data.snapshot_create":
            return self._submit_data_snapshot_command(command)

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

    def _submit_data_snapshot_command(self, command: dict[str, Any]) -> dict[str, Any]:
        command_hash = hashlib.sha256(canonical_json(command).encode()).hexdigest()
        payload = command["payload"]
        source = payload["source"]
        source_path = self.blob_path(source["sha256"])
        if not source_path.exists():
            raise ArtifactBlobMissing("data import source blob is not staged")
        source_body = source_path.read_bytes()
        if (
            hashlib.sha256(source_body).hexdigest() != source["sha256"]
            or len(source_body) != source["byte_size"]
        ):
            raise ArtifactIntegrityMismatch(
                "data import source bytes do not match registered identity"
            )
        material = build_data_snapshot(
            source_body,
            source_format=payload["source_format"],
            mapping=payload["mapping"],
            market=payload["market"],
            timezone=payload["timezone"],
            price_basis=payload["price_basis"],
            cutoff=payload["cutoff"],
        )
        normalized_sha256 = material.normalized_sha256
        market_input_sha256 = material.market_input_sha256
        normalized_artifact_id = deterministic_artifact_id(
            "normalized", normalized_sha256
        )
        market_input_artifact_id = deterministic_artifact_id(
            "market-input", market_input_sha256
        )
        self.store_blob(normalized_sha256, material.normalized_body)
        self.store_blob(market_input_sha256, material.market_input_body)
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
                    raise CommandIdConflict("command_id was already used by another envelope")
                receipt = json.loads(existing["receipt_json"])
                receipt["disposition"] = "replayed"
                return receipt
            try:
                self._validate_active_workbench(connection, command)
                self._register_data_snapshot_artifact(
                    connection, source, recorded_at
                )
                normalized_artifact = self._data_snapshot_artifact(
                    artifact_id=normalized_artifact_id,
                    sha256=normalized_sha256,
                    body=material.normalized_body,
                    media_type="application/vnd.open-quant-studio.data-snapshot+json",
                    source_ref=payload["snapshot_id"],
                )
                market_input_artifact = self._data_snapshot_artifact(
                    artifact_id=market_input_artifact_id,
                    sha256=market_input_sha256,
                    body=material.market_input_body,
                    media_type="application/json",
                    source_ref=payload["snapshot_id"],
                )
                self._register_data_snapshot_artifact(
                    connection, normalized_artifact, recorded_at
                )
                self._register_data_snapshot_artifact(
                    connection, market_input_artifact, recorded_at
                )
                snapshot_sha256 = normalized_sha256
                connection.execute(
                    """
                    INSERT INTO data_snapshots(
                        snapshot_id, project_id, source_artifact_id,
                        normalized_artifact_id, market_input_artifact_id, market,
                        symbol, symbols_json, timezone, price_basis, cutoff, schema_version,
                        mapping_json, sample_start, sample_end, row_count, session_count, sha256,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["snapshot_id"],
                        command["project_id"],
                        source["artifact_id"],
                        normalized_artifact_id,
                        market_input_artifact_id,
                        payload["market"],
                        material.symbol,
                        canonical_json(material.symbols),
                        payload["timezone"],
                        payload["price_basis"],
                        payload["cutoff"],
                        material.schema_version,
                        canonical_json(payload["mapping"]),
                        material.sample_start,
                        material.sample_end,
                        material.row_count,
                        material.session_count,
                        snapshot_sha256,
                        recorded_at,
                    ),
                )
                event_payload = {
                    "snapshot_id": payload["snapshot_id"],
                    "source_artifact_id": source["artifact_id"],
                    "normalized_artifact_id": normalized_artifact_id,
                    "market_input_artifact_id": market_input_artifact_id,
                    "market": payload["market"],
                    "symbol": material.symbol,
                    "symbols": list(material.symbols),
                    "timezone": payload["timezone"],
                    "price_basis": payload["price_basis"],
                    "cutoff": payload["cutoff"],
                    "schema_version": material.schema_version,
                    "sample_start": material.sample_start,
                    "sample_end": material.sample_end,
                    "row_count": material.row_count,
                    "session_count": material.session_count,
                    "sha256": snapshot_sha256,
                    "created_at": recorded_at,
                }
                event = self._insert_event(
                    connection,
                    event_type="data.snapshot_created",
                    project_id=command["project_id"],
                    activity_id=command["activity_id"],
                    session_id=command["session_id"],
                    workbench_id=command["workbench_id"],
                    correlation_id=command["correlation_id"],
                    causation_id=command["command_id"],
                    recorded_at=recorded_at,
                    variant_id=None,
                    base_revision_id=None,
                    payload=event_payload,
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
                self._insert_log(
                    connection,
                    timestamp=recorded_at,
                    level="info",
                    priority="p2",
                    event_code="data.snapshot.created",
                    project_id=command["project_id"],
                    activity_id=command["activity_id"],
                    session_id=command["session_id"],
                    job_id=None,
                    correlation_id=command["correlation_id"],
                    message="Data snapshot was created",
                )
            except (DomainConflict, DataImportValidationError):
                connection.execute("ROLLBACK")
                raise
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise DomainConflict("data snapshot constraint rejected the command") from error
            connection.execute("COMMIT")
        return receipt

    def _submit_formal_run_command(self, command: dict[str, Any]) -> dict[str, Any]:
        if command["command_type"] == "formal.run_cancel":
            return self._cancel_formal_run(command)
        if command["command_type"] == "formal.run_retry":
            return self._retry_formal_run(command)
        command_hash = hashlib.sha256(canonical_json(command).encode()).hexdigest()
        recorded_at = utc_now()
        payload = command["payload"]
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
                self._validate_active_workbench(connection, command)
                candidate = connection.execute(
                    """
                    SELECT c.*, r.git_tree_oid,
                           ph.head_revision_id AS project_head_revision_id,
                           ph.version AS project_head_version,
                           vh.head_revision_id AS variant_head_revision_id,
                           vh.version AS variant_head_version
                    FROM workspace_merge_candidates AS c
                    JOIN workspace_revisions AS r
                      ON r.revision_id = c.candidate_revision_id
                     AND r.project_id = c.project_id
                     AND r.activity_id = c.activity_id
                    JOIN project_revision_heads AS ph
                      ON ph.project_id = c.project_id
                    JOIN strategy_variant_heads AS vh
                      ON vh.variant_id = c.variant_id
                     AND vh.project_id = c.project_id
                     AND vh.activity_id = c.activity_id
                    WHERE c.candidate_revision_id = ?
                    """,
                    (payload["candidate_revision_id"],),
                ).fetchone()
                if (
                    candidate is None
                    or candidate["project_id"] != command["project_id"]
                    or candidate["activity_id"] != command["activity_id"]
                    or candidate["variant_id"] != command["variant_id"]
                    or candidate["git_tree_oid"] != payload["strategy_tree_oid"]
                ):
                    raise DomainConflict(
                        "formal RunSpec is not bound to the requested merge candidate"
                    )
                if (
                    candidate["project_head_revision_id"]
                    != candidate["project_parent_revision_id"]
                    or candidate["project_head_version"]
                    != candidate["expected_project_head_version"]
                    or candidate["variant_head_revision_id"]
                    != candidate["variant_parent_revision_id"]
                    or candidate["variant_head_version"]
                    != candidate["expected_variant_head_version"]
                ):
                    raise DomainConflict(
                        "merge candidate parents changed before formal validation"
                    )
                active_job = connection.execute(
                    """
                    SELECT job_id
                    FROM jobs
                    WHERE candidate_revision_id = ?
                      AND job_type = 'formal.run'
                      AND status IN ('pending', 'running')
                    """,
                    (payload["candidate_revision_id"],),
                ).fetchone()
                if active_job is not None:
                    raise DomainConflict(
                        "merge candidate already has an active formal validation"
                    )
                validation_owner = connection.execute(
                    "SELECT job_id FROM jobs WHERE validation_id = ?",
                    (payload["validation_id"],),
                ).fetchone()
                if validation_owner is not None:
                    raise DomainConflict(
                        "validation_id already belongs to another formal Run"
                    )

                is_checkpointed = payload["gate_policy_version"] in {"m5-v1", "m8-v1"}
                engine_input = payload["market_input"] if is_checkpointed else payload["engine_input"]
                engine_input = {
                    **engine_input,
                    "artifact_id": self._register_formal_input_artifact(
                        connection, engine_input, recorded_at
                    ),
                }
                snapshot = connection.execute(
                    """
                    SELECT sha256, market_input_artifact_id
                    FROM data_snapshots
                    WHERE snapshot_id = ? AND project_id = ?
                    """,
                    (payload["data_snapshot_id"], command["project_id"]),
                ).fetchone()
                if snapshot is not None and (
                    snapshot["sha256"] != payload["data_snapshot_sha256"]
                    or snapshot["market_input_artifact_id"] != engine_input["artifact_id"]
                ):
                    raise DomainConflict(
                        "formal Run input does not match the selected data snapshot"
                    )
                spec_identity = {
                    "schema_version": 1,
                    "project_id": command["project_id"],
                    "activity_id": command["activity_id"],
                    "variant_id": command["variant_id"],
                    "candidate_revision_id": payload["candidate_revision_id"],
                    ("market_input_sha256" if is_checkpointed else "engine_input_sha256"): engine_input["sha256"],
                    "data_snapshot_id": payload["data_snapshot_id"],
                    "data_snapshot_sha256": payload["data_snapshot_sha256"],
                    "strategy_tree_oid": payload["strategy_tree_oid"],
                    "parameters_sha256": payload["parameters_sha256"],
                    "cost_model_sha256": payload["cost_model_sha256"],
                    "environment_lock_sha256": payload["environment_lock_sha256"],
                    "engine_version": payload["engine_version"],
                    "price_basis": payload["price_basis"],
                    "cutoff": payload["cutoff"],
                    "timezone": payload["timezone"],
                    "sample_start": payload["sample_start"],
                    "sample_end": payload["sample_end"],
                    "random_seed": payload["random_seed"],
                    "output_schema_version": payload["output_schema_version"],
                    "gate_policy_version": payload["gate_policy_version"],
                }
                if is_checkpointed:
                    spec_identity.update(
                        {
                            "strategy_protocol_version": payload["strategy_protocol_version"],
                            "checkpoint_batch_size": payload["checkpoint_batch_size"],
                            "engine_checkpoint_abi": payload["engine_checkpoint_abi"],
                        }
                    )
                run_spec_hash = hashlib.sha256(
                    canonical_json(spec_identity).encode()
                ).hexdigest()
                existing_spec = connection.execute(
                    "SELECT spec_hash FROM run_specs WHERE run_spec_id = ?",
                    (payload["run_spec_id"],),
                ).fetchone()
                if existing_spec is not None:
                    if existing_spec["spec_hash"] != run_spec_hash:
                        raise DomainConflict(
                            "run_spec_id already belongs to another immutable RunSpec"
                        )
                else:
                    if is_checkpointed:
                        connection.execute(
                        """
                        INSERT INTO run_specs(
                            run_spec_id, project_id, activity_id, variant_id,
                            candidate_revision_id, market_input_artifact_id,
                            data_snapshot_id, data_snapshot_sha256,
                            strategy_tree_oid, parameters_sha256,
                            cost_model_sha256, environment_lock_sha256,
                            engine_version, price_basis, cutoff, timezone,
                            sample_start, sample_end, random_seed,
                            output_schema_version, gate_policy_version,
                            strategy_protocol_version, checkpoint_batch_size,
                            engine_checkpoint_abi, spec_hash, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            payload["run_spec_id"],
                            command["project_id"],
                            command["activity_id"],
                            command["variant_id"],
                            payload["candidate_revision_id"],
                            engine_input["artifact_id"],
                            payload["data_snapshot_id"],
                            payload["data_snapshot_sha256"],
                            payload["strategy_tree_oid"],
                            payload["parameters_sha256"],
                            payload["cost_model_sha256"],
                            payload["environment_lock_sha256"],
                            payload["engine_version"],
                            payload["price_basis"],
                            payload["cutoff"],
                            payload["timezone"],
                            payload["sample_start"],
                            payload["sample_end"],
                            payload["random_seed"],
                            payload["output_schema_version"],
                            payload["gate_policy_version"],
                            payload["strategy_protocol_version"],
                            payload["checkpoint_batch_size"],
                            payload["engine_checkpoint_abi"],
                            run_spec_hash,
                            recorded_at,
                            ),
                        )
                    else:
                        connection.execute(
                            """
                            INSERT INTO run_specs(
                                run_spec_id, project_id, activity_id, variant_id,
                                candidate_revision_id, engine_input_artifact_id,
                                data_snapshot_id, data_snapshot_sha256,
                                strategy_tree_oid, parameters_sha256,
                                cost_model_sha256, environment_lock_sha256,
                                engine_version, price_basis, cutoff, timezone,
                                sample_start, sample_end, random_seed,
                                output_schema_version, gate_policy_version,
                                spec_hash, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                payload["run_spec_id"], command["project_id"], command["activity_id"],
                                command["variant_id"], payload["candidate_revision_id"], engine_input["artifact_id"],
                                payload["data_snapshot_id"], payload["data_snapshot_sha256"], payload["strategy_tree_oid"],
                                payload["parameters_sha256"], payload["cost_model_sha256"], payload["environment_lock_sha256"],
                                payload["engine_version"], payload["price_basis"], payload["cutoff"], payload["timezone"],
                                payload["sample_start"], payload["sample_end"], payload["random_seed"], payload["output_schema_version"],
                                payload["gate_policy_version"], run_spec_hash, recorded_at,
                            ),
                        )

                job_id = str(uuid.uuid5(uuid.UUID(command["command_id"]), "formal.run"))
                queued_payload = {
                    "job_id": job_id,
                    "run_spec_id": payload["run_spec_id"],
                    "run_id": payload["run_id"],
                    "validation_id": payload["validation_id"],
                    "candidate_revision_id": payload["candidate_revision_id"],
                    "run_spec_hash": run_spec_hash,
                }
                if is_checkpointed:
                    queued_payload.update(
                        {
                            "lifecycle_version": payload["gate_policy_version"],
                            "execution_version": 0,
                        }
                    )
                event = self._insert_event(
                    connection,
                    event_type="formal.run_queued",
                    project_id=command["project_id"],
                    activity_id=command["activity_id"],
                    session_id=command["session_id"],
                    workbench_id=command["workbench_id"],
                    correlation_id=command["correlation_id"],
                    causation_id=command["command_id"],
                    recorded_at=recorded_at,
                    variant_id=command["variant_id"],
                    base_revision_id=payload["candidate_revision_id"],
                    payload=queued_payload,
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
                connection.execute(
                    """
                    INSERT INTO jobs(
                        job_id, command_id, job_type, project_id, activity_id,
                        session_id, workbench_id, correlation_id, artifact_id,
                        run_spec_id, run_id, validation_id,
                        candidate_revision_id, status, created_at
                    ) VALUES (?, ?, 'formal.run', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        job_id,
                        command["command_id"],
                        command["project_id"],
                        command["activity_id"],
                        command["session_id"],
                        command["workbench_id"],
                        command["correlation_id"],
                        engine_input["artifact_id"],
                        payload["run_spec_id"],
                        payload["run_id"],
                        payload["validation_id"],
                        payload["candidate_revision_id"],
                        recorded_at,
                    ),
                )
                self._insert_log(
                    connection,
                    timestamp=recorded_at,
                    level="info",
                    priority="p2",
                    event_code="formal.run.queued",
                    project_id=command["project_id"],
                    activity_id=command["activity_id"],
                    session_id=command["session_id"],
                    job_id=job_id,
                    correlation_id=command["correlation_id"],
                    message="Formal validation Run was queued",
                )
            except DomainConflict:
                connection.execute("ROLLBACK")
                raise
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise DomainConflict(
                    "formal Run constraint rejected the command"
                ) from error
            connection.execute("COMMIT")
        return receipt

    def _cancel_formal_run(self, command: dict[str, Any]) -> dict[str, Any]:
        command_hash = hashlib.sha256(canonical_json(command).encode()).hexdigest()
        recorded_at = utc_now()
        payload = command["payload"]
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

            self._validate_active_workbench(connection, command)
            row = connection.execute(
                """
                SELECT j.*, rs.variant_id, rs.spec_hash, rs.gate_policy_version,
                       rs.engine_version
                FROM jobs AS j
                JOIN run_specs AS rs ON rs.run_spec_id = j.run_spec_id
                WHERE j.run_id = ? AND j.job_type = 'formal.run'
                  AND j.project_id = ? AND j.activity_id = ?
                """,
                (payload["run_id"], command["project_id"], command["activity_id"]),
            ).fetchone()
            if (
                row is None
                or row["variant_id"] != command["variant_id"]
                or row["candidate_revision_id"] != command["base_revision_id"]
                or row["status"] != payload["expected_status"]
                or row["execution_version"]
                != payload["expected_execution_version"]
            ):
                connection.execute("ROLLBACK")
                raise FormalRunLifecycleConflict(
                    "formal Run cancel precondition did not match active execution"
                )

            execution_version = row["execution_version"] + 1
            transition = connection.execute(
                """
                UPDATE jobs
                SET status = 'cancelled', execution_version = ?,
                    claim_token = NULL, lease_expires_at = NULL,
                    result_json = NULL, error_code = NULL, error_message = NULL,
                    finished_at = ?
                WHERE job_id = ? AND status = ? AND execution_version = ?
                """,
                (
                    execution_version,
                    recorded_at,
                    row["job_id"],
                    payload["expected_status"],
                    payload["expected_execution_version"],
                ),
            )
            if transition.rowcount != 1:
                connection.execute("ROLLBACK")
                raise FormalRunLifecycleConflict("formal Run cancel CAS was stale")

            connection.execute(
                """
                INSERT INTO formal_runs(
                    run_id, run_spec_id, project_id, activity_id, variant_id,
                    candidate_revision_id, status, execution_version,
                    retry_of_run_id, engine_result_artifact_id,
                    manifest_artifact_id, calculation_hash, error_code,
                    cancel_reason, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'cancelled', ?, ?, NULL, NULL, NULL, NULL,
                          'user_requested', ?)
                """,
                (
                    row["run_id"],
                    row["run_spec_id"],
                    row["project_id"],
                    row["activity_id"],
                    row["variant_id"],
                    row["candidate_revision_id"],
                    execution_version,
                    row["retry_of_run_id"],
                    recorded_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO merge_validations(
                    validation_id, project_id, activity_id, variant_id,
                    candidate_revision_id, run_id, gate_policy_version,
                    engine_version, contract_outcome,
                    strategy_import_outcome, smoke_run_outcome, outcome,
                    manifest_artifact_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'not_run', 'not_run',
                          'not_run', 'not_run', NULL, ?)
                """,
                (
                    row["validation_id"],
                    row["project_id"],
                    row["activity_id"],
                    row["variant_id"],
                    row["candidate_revision_id"],
                    row["run_id"],
                    row["gate_policy_version"],
                    row["engine_version"],
                    recorded_at,
                ),
            )
            gates = {
                "contract": "not_run",
                "strategy_import": "not_run",
                "smoke_run": "not_run",
            }
            event = self._insert_event(
                connection,
                event_type="formal.run_cancelled",
                project_id=row["project_id"],
                activity_id=row["activity_id"],
                session_id=command["session_id"],
                workbench_id=command["workbench_id"],
                correlation_id=command["correlation_id"],
                causation_id=command["command_id"],
                recorded_at=recorded_at,
                variant_id=row["variant_id"],
                base_revision_id=row["candidate_revision_id"],
                payload={
                    "lifecycle_version": row["gate_policy_version"],
                    "job_id": row["job_id"],
                    "run_spec_id": row["run_spec_id"],
                    "run_id": row["run_id"],
                    "validation_id": row["validation_id"],
                    "candidate_revision_id": row["candidate_revision_id"],
                    "run_spec_hash": row["spec_hash"],
                    "execution_version": execution_version,
                    "status": "cancelled",
                    "validation_outcome": "not_run",
                    "gates": gates,
                    "engine_result_artifact_id": None,
                    "manifest_artifact_id": None,
                    "calculation_hash": None,
                    "error_code": None,
                    "cancel_reason": "user_requested",
                },
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
            self._insert_log(
                connection,
                timestamp=recorded_at,
                level="info",
                priority="p2",
                event_code="formal.run.cancelled",
                project_id=row["project_id"],
                activity_id=row["activity_id"],
                session_id=command["session_id"],
                job_id=row["job_id"],
                correlation_id=command["correlation_id"],
                message="Formal Run was cancelled",
                run_id=row["run_id"],
            )
            connection.execute("COMMIT")
        return receipt

    def _retry_formal_run(self, command: dict[str, Any]) -> dict[str, Any]:
        command_hash = hashlib.sha256(canonical_json(command).encode()).hexdigest()
        recorded_at = utc_now()
        payload = command["payload"]
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

            self._validate_active_workbench(connection, command)
            source = connection.execute(
                """
                SELECT r.*, j.artifact_id, rs.spec_hash, rs.gate_policy_version
                FROM formal_runs AS r
                JOIN jobs AS j ON j.run_id = r.run_id
                JOIN run_specs AS rs ON rs.run_spec_id = r.run_spec_id
                WHERE r.run_id = ? AND r.project_id = ? AND r.activity_id = ?
                """,
                (
                    payload["source_run_id"],
                    command["project_id"],
                    command["activity_id"],
                ),
            ).fetchone()
            if (
                source is None
                or source["status"] not in {"failed", "cancelled"}
                or source["execution_version"]
                != payload["source_execution_version"]
                or source["variant_id"] != command["variant_id"]
                or source["candidate_revision_id"] != command["base_revision_id"]
            ):
                connection.execute("ROLLBACK")
                raise FormalRunLifecycleConflict(
                    "formal Run retry source is not the expected failed or cancelled execution"
                )

            job_id = str(uuid.uuid5(uuid.UUID(command["command_id"]), "formal.run"))
            event = self._insert_event(
                connection,
                event_type="formal.run_retried",
                project_id=source["project_id"],
                activity_id=source["activity_id"],
                session_id=command["session_id"],
                workbench_id=command["workbench_id"],
                correlation_id=command["correlation_id"],
                causation_id=command["command_id"],
                recorded_at=recorded_at,
                variant_id=source["variant_id"],
                base_revision_id=source["candidate_revision_id"],
                payload={
                    "lifecycle_version": source["gate_policy_version"],
                    "job_id": job_id,
                    "run_spec_id": source["run_spec_id"],
                    "run_id": payload["run_id"],
                    "validation_id": payload["validation_id"],
                    "candidate_revision_id": source["candidate_revision_id"],
                    "run_spec_hash": source["spec_hash"],
                    "execution_version": 0,
                    "source_run_id": source["run_id"],
                },
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
            connection.execute(
                """
                INSERT INTO jobs(
                    job_id, command_id, job_type, project_id, activity_id,
                    session_id, workbench_id, correlation_id, artifact_id,
                    run_spec_id, run_id, validation_id,
                    candidate_revision_id, status, retry_of_run_id, created_at
                ) VALUES (?, ?, 'formal.run', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'pending', ?, ?)
                """,
                (
                    job_id,
                    command["command_id"],
                    source["project_id"],
                    source["activity_id"],
                    command["session_id"],
                    command["workbench_id"],
                    command["correlation_id"],
                    source["artifact_id"],
                    source["run_spec_id"],
                    payload["run_id"],
                    payload["validation_id"],
                    source["candidate_revision_id"],
                    source["run_id"],
                    recorded_at,
                ),
            )
            self._insert_log(
                connection,
                timestamp=recorded_at,
                level="info",
                priority="p2",
                event_code="formal.run.retried",
                project_id=source["project_id"],
                activity_id=source["activity_id"],
                session_id=command["session_id"],
                job_id=job_id,
                correlation_id=command["correlation_id"],
                message="Formal Run retry was queued",
                run_id=payload["run_id"],
            )
            connection.execute("COMMIT")
        return receipt

    def _submit_diagnostic_command(self, command: dict[str, Any]) -> dict[str, Any]:
        command_hash = hashlib.sha256(canonical_json(command).encode()).hexdigest()
        completed_at = utc_now()
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

            self._validate_active_workbench(connection, command)
            if command["command_type"] == "diagnostic.log_delete":
                selection = command["payload"]["selection"]
                where, parameters = self._diagnostic_selection_sql(selection)
                selected = connection.execute(
                    f"""
                    SELECT log_seq
                    FROM diagnostic_logs
                    WHERE project_id = ? AND ({where})
                    """,
                    [command["project_id"], *parameters],
                ).fetchall()
                if selected:
                    placeholders = ",".join("?" for _ in selected)
                    connection.execute(
                        f"DELETE FROM diagnostic_logs WHERE log_seq IN ({placeholders})",
                        [row["log_seq"] for row in selected],
                    )
                reason = "user"
                selection_identity = selection
                event_type = "diagnostic.logs_deleted"
            else:
                payload = command["payload"]
                connection.execute(
                    """
                    INSERT INTO diagnostic_log_retention(
                        project_id, debug_days, info_days, warn_days,
                        quota_bytes, configured_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id) DO UPDATE SET
                        debug_days = excluded.debug_days,
                        info_days = excluded.info_days,
                        warn_days = excluded.warn_days,
                        quota_bytes = excluded.quota_bytes,
                        configured_at = excluded.configured_at
                    """,
                    (
                        command["project_id"],
                        payload["debug_days"],
                        payload["info_days"],
                        payload["warn_days"],
                        payload["quota_bytes"],
                        completed_at,
                    ),
                )
                selected = self._delete_expired_logs(
                    connection,
                    command["project_id"],
                    payload["debug_days"],
                    payload["info_days"],
                    payload["warn_days"],
                    payload["quota_bytes"],
                )
                reason = "retention"
                selection_identity = payload
                event_type = "diagnostic.retention_applied"

            selection_sha256 = hashlib.sha256(
                canonical_json(selection_identity).encode()
            ).hexdigest()
            receipt_id = str(
                uuid.uuid5(uuid.UUID(command["command_id"]), "diagnostic-receipt")
            )
            connection.execute(
                """
                INSERT INTO diagnostic_log_delete_receipts(
                    receipt_id, project_id, reason, selection_sha256,
                    deleted_count, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt_id,
                    command["project_id"],
                    reason,
                    selection_sha256,
                    len(selected),
                    completed_at,
                ),
            )
            event = self._insert_event(
                connection,
                event_type=event_type,
                project_id=command["project_id"],
                activity_id=command["activity_id"],
                session_id=command["session_id"],
                workbench_id=command["workbench_id"],
                correlation_id=command["correlation_id"],
                causation_id=command["command_id"],
                recorded_at=completed_at,
                variant_id=None,
                base_revision_id=None,
                payload={
                    "receipt_id": receipt_id,
                    "reason": reason,
                    "selection_sha256": selection_sha256,
                    "deleted_count": len(selected),
                    "completed_at": completed_at,
                },
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
                    completed_at,
                ),
            )
            connection.execute("COMMIT")
        return receipt

    def _submit_forward_test_command(
        self, command: dict[str, Any]
    ) -> dict[str, Any]:
        command_hash = hashlib.sha256(canonical_json(command).encode()).hexdigest()
        completed_at = utc_now()
        payload = command["payload"]
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT command_hash, receipt_json FROM command_receipts WHERE command_id = ?",
                (command["command_id"],),
            ).fetchone()
            if existing is not None:
                if existing["command_hash"] != command_hash:
                    raise CommandIdConflict(
                        "command_id was already used by another envelope"
                    )
                replayed = json.loads(existing["receipt_json"])
                replayed["disposition"] = "replayed"
                return replayed
            self._validate_active_workbench(connection, command)

        source = self.run(command["project_id"], payload["source_run_id"])
        if (
            source is None
            or source["run"]["activity_id"] != command["activity_id"]
            or source["run"]["variant_id"] != command["variant_id"]
            or source["run"]["candidate_revision_id"] != command["base_revision_id"]
        ):
            raise DomainConflict("Forward Test source Run did not match the request")
        manifest = source["manifest"]
        if manifest is None or manifest.get("manifest_version") != "m5-v1":
            raise FormalRunLifecycleConflict(
                "Forward Test requires a succeeded M5 source Run"
            )
        strategy_artifact_id = manifest["revision"]["strategy_artifact_id"]
        market_artifact_id = manifest["market_input"]["artifact_id"]
        intent_artifact_id = manifest["strategy_execution"][
            "intent_tape_artifact_id"
        ]
        strategy_content = self.artifact_content(
            command["project_id"], strategy_artifact_id
        )
        market_content = self.artifact_content(
            command["project_id"], market_artifact_id
        )
        intent_content = self.artifact_content(
            command["project_id"], intent_artifact_id
        )
        if (
            strategy_content is None
            or market_content is None
            or intent_content is None
        ):
            raise ArtifactIntegrityMismatch(
                "Forward Test source artifacts are incomplete"
            )
        result = replay_forward_test(
            forward_test_id=payload["forward_test_id"],
            source_run=source["run"],
            source_manifest=manifest,
            strategy_source=strategy_content[1],
            market_input=market_content[1],
            source_intent_tape=intent_content[1],
        )
        transcript_artifact = self._m5_artifact_descriptor(
            str(
                uuid.uuid5(
                    uuid.UUID(payload["forward_test_id"]),
                    "forward-test-transcript",
                )
            ),
            result.transcript,
            media_type="application/vnd.open-quant-studio.forward-test+json",
            source_ref=payload["forward_test_id"],
        )
        self.store_blob(result.transcript_sha256, result.transcript)

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
            self._validate_active_workbench(connection, command)
            prior_forward_test = connection.execute(
                "SELECT 1 FROM forward_tests WHERE forward_test_id = ?",
                (payload["forward_test_id"],),
            ).fetchone()
            if prior_forward_test is not None:
                connection.execute("ROLLBACK")
                raise DomainConflict("forward_test_id already exists")
            self._register_generated_artifact(
                connection, transcript_artifact, completed_at
            )
            connection.execute(
                """
                INSERT INTO forward_tests(
                    forward_test_id, source_run_id, source_revision_id,
                    data_snapshot_id, protocol_version, released_bar_count,
                    transcript_artifact_id, transcript_sha256,
                    intent_tape_sha256, status, error_code, project_id,
                    activity_id, variant_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.forward_test_id,
                    result.source_run_id,
                    result.source_revision_id,
                    result.data_snapshot_id,
                    result.protocol_version,
                    result.released_bar_count,
                    transcript_artifact["artifact_id"],
                    result.transcript_sha256,
                    result.intent_tape_sha256,
                    result.status,
                    result.error_code,
                    command["project_id"],
                    command["activity_id"],
                    command["variant_id"],
                    completed_at,
                ),
            )
            event = self._insert_event(
                connection,
                event_type="forward_test.completed",
                project_id=command["project_id"],
                activity_id=command["activity_id"],
                session_id=command["session_id"],
                workbench_id=command["workbench_id"],
                correlation_id=command["correlation_id"],
                causation_id=command["command_id"],
                recorded_at=completed_at,
                variant_id=command["variant_id"],
                base_revision_id=command["base_revision_id"],
                payload={
                    "forward_test_id": result.forward_test_id,
                    "source_run_id": result.source_run_id,
                    "source_revision_id": result.source_revision_id,
                    "data_snapshot_id": result.data_snapshot_id,
                    "protocol_version": result.protocol_version,
                    "released_bar_count": result.released_bar_count,
                    "transcript_artifact_id": transcript_artifact["artifact_id"],
                    "transcript_sha256": result.transcript_sha256,
                    "intent_tape_sha256": result.intent_tape_sha256,
                    "status": result.status,
                    "error_code": result.error_code,
                },
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
                    completed_at,
                ),
            )
            self._insert_log(
                connection,
                timestamp=completed_at,
                level="info" if result.status == "passed" else "warn",
                priority="p2",
                event_code=f"forward.test.{result.status}",
                project_id=command["project_id"],
                activity_id=command["activity_id"],
                session_id=command["session_id"],
                job_id=None,
                correlation_id=command["correlation_id"],
                message=f"Forward Test {result.status}",
                run_id=result.source_run_id,
            )
            connection.execute("COMMIT")
        return receipt

    def _submit_project_archive_import(
        self, command: dict[str, Any]
    ) -> dict[str, Any]:
        command_hash = hashlib.sha256(canonical_json(command).encode()).hexdigest()
        payload = command["payload"]
        archive = payload["archive"]
        archive_path = self.blob_path(archive["sha256"])
        if not archive_path.exists():
            raise ArtifactBlobMissing("project archive blob is not staged")
        archive_body = archive_path.read_bytes()
        if (
            hashlib.sha256(archive_body).hexdigest() != archive["sha256"]
            or len(archive_body) != archive["byte_size"]
        ):
            raise ArtifactIntegrityMismatch(
                "project archive bytes do not match registered identity"
            )
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT command_hash, receipt_json FROM command_receipts WHERE command_id = ?",
                (command["command_id"],),
            ).fetchone()
            if existing is not None:
                if existing["command_hash"] != command_hash:
                    raise CommandIdConflict(
                        "command_id was already used by another envelope"
                    )
                replayed = json.loads(existing["receipt_json"])
                replayed["disposition"] = "replayed"
                return replayed

        try:
            imported = import_project_archive(
                self,
                archive_path,
                expected_project_id=payload["expected_project_id"],
            )
        except ProjectArchiveError as error:
            raise DomainConflict(str(error)) from error

        completed_at = utc_now()
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
            self._validate_active_workbench(connection, command)
            self._register_formal_input_artifact(connection, archive, completed_at)
            event = self._insert_event(
                connection,
                event_type="project.archive_imported",
                project_id=command["project_id"],
                activity_id=command["activity_id"],
                session_id=command["session_id"],
                workbench_id=command["workbench_id"],
                correlation_id=command["correlation_id"],
                causation_id=command["command_id"],
                recorded_at=completed_at,
                variant_id=None,
                base_revision_id=None,
                payload={
                    "archive_artifact_id": archive["artifact_id"],
                    "archive_sha256": imported.archive_sha256,
                    "manifest_sha256": imported.manifest_sha256,
                    "restored_project_id": imported.restored_project_id,
                    "run_count": imported.run_count,
                    "artifact_count": imported.artifact_count,
                    "git_ref_count": imported.git_ref_count,
                },
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
                    completed_at,
                ),
            )
            self._insert_log(
                connection,
                timestamp=completed_at,
                level="info",
                priority="p2",
                event_code="project.archive.imported",
                project_id=command["project_id"],
                activity_id=command["activity_id"],
                session_id=command["session_id"],
                job_id=None,
                correlation_id=command["correlation_id"],
                message="Project archive was imported",
            )
            connection.execute("COMMIT")
        return receipt

    @staticmethod
    def _diagnostic_selection_sql(
        selection: dict[str, Any],
    ) -> tuple[str, list[str]]:
        if "log_ids" in selection:
            placeholders = ",".join("?" for _ in selection["log_ids"])
            return f"log_id IN ({placeholders})", list(selection["log_ids"])

        predicates: list[str] = []
        parameters: list[str] = []
        for key, column in (
            ("activity_id", "activity_id"),
            ("session_id", "session_id"),
            ("run_id", "run_id"),
        ):
            if key in selection:
                predicates.append(f"{column} = ?")
                parameters.append(selection[key])
        if "from" in selection:
            predicates.append("timestamp >= ?")
            parameters.append(selection["from"])
        if "to" in selection:
            predicates.append("timestamp <= ?")
            parameters.append(selection["to"])
        for key, column in (("levels", "level"), ("priorities", "priority")):
            if key in selection:
                placeholders = ",".join("?" for _ in selection[key])
                predicates.append(f"{column} IN ({placeholders})")
                parameters.extend(selection[key])
        if "query" in selection:
            predicates.append(
                "log_seq IN (SELECT rowid FROM diagnostic_logs_fts "
                "WHERE diagnostic_logs_fts MATCH ?)"
            )
            parameters.append(selection["query"])
        return " AND ".join(predicates), parameters

    @staticmethod
    def _delete_expired_logs(
        connection: sqlite3.Connection,
        project_id: str,
        debug_days: int,
        info_days: int,
        warn_days: int,
        quota_bytes: int,
    ) -> list[sqlite3.Row]:
        expired = connection.execute(
            """
            SELECT log_seq
            FROM diagnostic_logs
            WHERE project_id = ? AND priority != 'p1' AND level != 'error'
              AND (
                (level = 'debug' AND timestamp < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', ?)) OR
                (level = 'info' AND timestamp < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', ?)) OR
                (level = 'warn' AND timestamp < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', ?))
              )
            """,
            (
                project_id,
                f"-{debug_days} days",
                f"-{info_days} days",
                f"-{warn_days} days",
            ),
        ).fetchall()
        removed = list(expired)
        if expired:
            placeholders = ",".join("?" for _ in expired)
            connection.execute(
                f"DELETE FROM diagnostic_logs WHERE log_seq IN ({placeholders})",
                [row["log_seq"] for row in expired],
            )
        retained_bytes = connection.execute(
            """
            SELECT COALESCE(SUM(length(CAST(message AS BLOB))), 0)
            FROM diagnostic_logs
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()[0]
        if retained_bytes > quota_bytes:
            candidates = connection.execute(
                """
                SELECT log_seq, length(CAST(message AS BLOB)) AS byte_size
                FROM diagnostic_logs
                WHERE project_id = ? AND priority != 'p1' AND level != 'error'
                ORDER BY CASE level
                    WHEN 'debug' THEN 0
                    WHEN 'info' THEN 1
                    ELSE 2
                END, timestamp, log_seq
                """,
                (project_id,),
            ).fetchall()
            quota_rows = []
            for row in candidates:
                if retained_bytes <= quota_bytes:
                    break
                quota_rows.append(row)
                retained_bytes -= row["byte_size"]
            if quota_rows:
                placeholders = ",".join("?" for _ in quota_rows)
                connection.execute(
                    f"DELETE FROM diagnostic_logs WHERE log_seq IN ({placeholders})",
                    [row["log_seq"] for row in quota_rows],
                )
                removed.extend(quota_rows)
        return removed

    def apply_log_retention(self) -> None:
        with self.database.connect() as connection:
            policies = connection.execute(
                """
                SELECT p.project_id,
                       COALESCE(r.debug_days, ?) AS debug_days,
                       COALESCE(r.info_days, ?) AS info_days,
                       COALESCE(r.warn_days, ?) AS warn_days,
                       COALESCE(r.quota_bytes, ?) AS quota_bytes
                FROM research_projects AS p
                LEFT JOIN diagnostic_log_retention AS r
                  ON r.project_id = p.project_id
                ORDER BY p.project_id
                """,
                (
                    DEFAULT_DEBUG_RETENTION_DAYS,
                    DEFAULT_INFO_RETENTION_DAYS,
                    DEFAULT_WARN_RETENTION_DAYS,
                    DEFAULT_DIAGNOSTIC_LOG_QUOTA_BYTES,
                ),
            ).fetchall()
        for policy in policies:
            with self.database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._delete_expired_logs(
                    connection,
                    policy["project_id"],
                    policy["debug_days"],
                    policy["info_days"],
                    policy["warn_days"],
                    policy["quota_bytes"],
                )
                connection.execute("COMMIT")

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
            merge_candidate: tuple[str, str, int, int] | None = None
            head_change: tuple[str, int] | None = None
            revision_identity: GitRevisionIdentity | None = None
            revision_id_to_protect: str | None = None
            try:
                command_type = command["command_type"]
                if command_type == "workspace.revision_create":
                    event, revision_identity = self._create_revision(
                        connection, command, recorded_at
                    )
                    revision_id_to_protect = command["payload"]["revision_id"]
                    if command["variant_id"] is None:
                        head_change = (command["payload"]["revision_id"], 0)
                elif command_type == "strategy.variant_create":
                    event = self._create_variant(connection, command, recorded_at)
                elif command_type == "workspace.merge_create":
                    event, revision_identity, merge_candidate = (
                        self._create_merge_candidate(connection, command, recorded_at)
                    )
                    revision_id_to_protect = command["payload"][
                        "candidate_revision_id"
                    ]
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
                    promotion_id = str(
                        uuid.uuid5(
                            uuid.UUID(command["command_id"]),
                            "workspace.revision_promote",
                        )
                    )
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
                            promotion_id,
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
                    connection.execute(
                        """
                        INSERT INTO revision_promotion_validations(
                            promotion_id, validation_id, created_at
                        ) VALUES (?, ?, ?)
                        """,
                        (
                            promotion_id,
                            command["payload"]["validation_id"],
                            recorded_at,
                        ),
                    )
                if merge_candidate is not None:
                    (
                        project_parent_revision_id,
                        variant_parent_revision_id,
                        project_head_version,
                        variant_head_version,
                    ) = merge_candidate
                    connection.execute(
                        """
                        INSERT INTO workspace_merge_candidates(
                            candidate_revision_id, project_id, activity_id,
                            variant_id, project_parent_revision_id,
                            variant_parent_revision_id,
                            expected_project_head_version,
                            expected_variant_head_version,
                            created_by_command_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            command["payload"]["candidate_revision_id"],
                            command["project_id"],
                            command["activity_id"],
                            command["variant_id"],
                            project_parent_revision_id,
                            variant_parent_revision_id,
                            project_head_version,
                            variant_head_version,
                            command["command_id"],
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
                        else "Workspace merge candidate was created"
                        if command_type == "workspace.merge_create"
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
            if revision_identity is not None and revision_id_to_protect is not None:
                try:
                    self.git_workspace.protect_revision(
                        project_id=command["project_id"],
                        revision_id=revision_id_to_protect,
                        commit_oid=revision_identity.commit_oid,
                    )
                    protected_revision = (
                        command["project_id"],
                        revision_id_to_protect,
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

        for path in payload.get("removed_paths", []):
            if path not in file_artifacts:
                raise RevisionConflict("removed path does not exist in the base revision")
            del file_artifacts[path]

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

    def _create_merge_candidate(
        self,
        connection: sqlite3.Connection,
        command: dict[str, Any],
        recorded_at: str,
    ) -> tuple[
        dict[str, Any],
        GitRevisionIdentity,
        tuple[str, str, int, int],
    ]:
        self._validate_active_workbench(connection, command)
        payload = command["payload"]
        candidate_revision_id = payload["candidate_revision_id"]
        existing = connection.execute(
            "SELECT 1 FROM workspace_revisions WHERE revision_id = ?",
            (candidate_revision_id,),
        ).fetchone()
        if existing is not None:
            raise RevisionConflict("candidate revision already belongs to immutable state")

        project_parent = connection.execute(
            """
            SELECT h.head_revision_id, h.version, r.git_commit_oid
            FROM project_revision_heads AS h
            JOIN workspace_revisions AS r
              ON r.revision_id = h.head_revision_id
             AND r.project_id = h.project_id
            WHERE h.project_id = ?
            """,
            (command["project_id"],),
        ).fetchone()
        variant_parent = connection.execute(
            """
            SELECT h.head_revision_id, h.version, r.git_commit_oid,
                   v.project_id, v.activity_id
            FROM strategy_variant_heads AS h
            JOIN strategy_variants AS v
              ON v.variant_id = h.variant_id
             AND v.project_id = h.project_id
             AND v.activity_id = h.activity_id
            JOIN workspace_revisions AS r
              ON r.revision_id = h.head_revision_id
             AND r.project_id = h.project_id
             AND r.activity_id = h.activity_id
            WHERE h.variant_id = ?
            """,
            (command["variant_id"],),
        ).fetchone()
        if (
            project_parent is None
            or project_parent["head_revision_id"]
            != command["expected_revision_id"]
        ):
            raise RevisionConflict("project head changed before merge creation")
        if (
            variant_parent is None
            or variant_parent["project_id"] != command["project_id"]
            or variant_parent["activity_id"] != command["activity_id"]
            or variant_parent["head_revision_id"] != command["base_revision_id"]
        ):
            raise RevisionConflict("variant head changed before merge creation")

        parent_paths = {
            row["path"]
            for row in connection.execute(
                """
                SELECT path
                FROM revision_files
                WHERE project_id = ? AND activity_id = ?
                  AND revision_id IN (?, ?)
                """,
                (
                    command["project_id"],
                    command["activity_id"],
                    project_parent["head_revision_id"],
                    variant_parent["head_revision_id"],
                ),
            ).fetchall()
        }
        if {file["path"] for file in payload["files"]} != parent_paths:
            raise RevisionConflict(
                "merge payload must contain the complete resolved parent tree"
            )

        file_artifacts: dict[str, str] = {}
        for file in payload["files"]:
            artifact = file["artifact"]
            self._register_message_artifact(connection, artifact, recorded_at)
            file_artifacts[file["path"]] = artifact["artifact_id"]

        file_bytes: dict[str, bytes] = {}
        for path, artifact_id in sorted(file_artifacts.items()):
            artifact = connection.execute(
                "SELECT sha256, byte_size FROM artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            artifact_path = self.blob_path(artifact["sha256"])
            if not artifact_path.exists():
                raise ArtifactBlobMissing("merge file artifact blob is not staged")
            body = artifact_path.read_bytes()
            if (
                hashlib.sha256(body).hexdigest() != artifact["sha256"]
                or len(body) != artifact["byte_size"]
            ):
                raise ArtifactIntegrityMismatch(
                    "merge file bytes do not match registered artifact identity"
                )
            file_bytes[path] = body

        git_identity = self.git_workspace.create_merge_commit(
            project_id=command["project_id"],
            revision_id=candidate_revision_id,
            files=file_bytes,
            project_parent_commit_oid=project_parent["git_commit_oid"],
            variant_parent_commit_oid=variant_parent["git_commit_oid"],
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
                candidate_revision_id,
                command["project_id"],
                command["activity_id"],
                command["variant_id"],
                command["base_revision_id"],
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
                    candidate_revision_id,
                    command["project_id"],
                    command["activity_id"],
                    path,
                    artifact_id,
                    git_identity.blob_oids[path],
                ),
            )
        event = self._insert_event(
            connection,
            event_type="workspace.merge_candidate_created",
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
                "candidate_revision_id": candidate_revision_id,
                "project_parent_revision_id": project_parent["head_revision_id"],
                "variant_parent_revision_id": variant_parent["head_revision_id"],
                "git_commit_oid": git_identity.commit_oid,
                "git_tree_oid": git_identity.tree_oid,
                "file_count": len(file_artifacts),
            },
        )
        return event, git_identity, (
            project_parent["head_revision_id"],
            variant_parent["head_revision_id"],
            project_parent["version"],
            variant_parent["version"],
        )

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
            SELECT r.git_commit_oid, r.git_tree_oid,
                   merge.project_id, merge.activity_id, merge.variant_id,
                   merge.project_parent_revision_id,
                   merge.variant_parent_revision_id,
                   merge.expected_project_head_version,
                   merge.expected_variant_head_version,
                   validation.outcome AS validation_outcome,
                   validation.gate_policy_version,
                   project_head.head_revision_id AS project_head_revision_id,
                   project_head.version AS project_head_version,
                   variant_head.head_revision_id AS variant_head_revision_id,
                   variant_head.version AS variant_head_version
            FROM workspace_merge_candidates AS merge
            JOIN workspace_revisions AS r
              ON r.revision_id = merge.candidate_revision_id
             AND r.project_id = merge.project_id
             AND r.activity_id = merge.activity_id
            JOIN merge_validations AS validation
              ON validation.validation_id = ?
             AND validation.candidate_revision_id = merge.candidate_revision_id
             AND validation.project_id = merge.project_id
             AND validation.activity_id = merge.activity_id
             AND validation.variant_id = merge.variant_id
            JOIN project_revision_heads AS project_head
              ON project_head.project_id = merge.project_id
            JOIN strategy_variant_heads AS variant_head
              ON variant_head.variant_id = merge.variant_id
             AND variant_head.project_id = merge.project_id
             AND variant_head.activity_id = merge.activity_id
            WHERE merge.candidate_revision_id = ?
            """,
            (command["payload"]["validation_id"], candidate_revision_id),
        ).fetchone()
        if (
            candidate is None
            or candidate["project_id"] != command["project_id"]
            or candidate["activity_id"] != command["activity_id"]
            or candidate["variant_id"] != command["variant_id"]
            or candidate["validation_outcome"] != "passed"
            or candidate["gate_policy_version"] not in {"m3-v1", "m5-v1", "m8-v1"}
        ):
            raise PromotionConflict(
                "promotion requires a passed validation for the exact merge candidate"
            )
        if (
            candidate["project_parent_revision_id"]
            != command["expected_revision_id"]
            or candidate["project_head_revision_id"]
            != candidate["project_parent_revision_id"]
            or candidate["project_head_version"]
            != candidate["expected_project_head_version"]
        ):
            raise PromotionConflict("project head changed before promotion")
        if (
            candidate["variant_head_revision_id"]
            != candidate["variant_parent_revision_id"]
            or candidate["variant_head_version"]
            != candidate["expected_variant_head_version"]
        ):
            raise PromotionConflict("variant head changed before promotion")
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
        resulting_head_version = candidate["project_head_version"] + 1
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
                candidate["project_head_version"],
            ),
        )
        if updated.rowcount != 1:
            raise PromotionConflict("project head changed before promotion")
        variant_updated = connection.execute(
            """
            UPDATE strategy_variant_heads
            SET head_revision_id = ?, version = version + 1, updated_at = ?
            WHERE variant_id = ? AND project_id = ? AND activity_id = ?
              AND head_revision_id = ? AND version = ?
            """,
            (
                candidate_revision_id,
                recorded_at,
                command["variant_id"],
                command["project_id"],
                command["activity_id"],
                candidate["variant_parent_revision_id"],
                candidate["variant_head_version"],
            ),
        )
        if variant_updated.rowcount != 1:
            raise PromotionConflict("variant head changed before promotion")
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
                "validation_id": command["payload"]["validation_id"],
                "git_commit_oid": candidate["git_commit_oid"],
                "git_tree_oid": candidate["git_tree_oid"],
            },
        )
        return event, (
            command["expected_revision_id"],
            candidate_revision_id,
            candidate["project_head_version"],
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

    def _register_formal_input_artifact(
        self,
        connection: sqlite3.Connection,
        artifact: dict[str, Any],
        recorded_at: str,
    ) -> str:
        path = self.blob_path(artifact["sha256"])
        if not path.exists():
            raise ArtifactBlobMissing("formal engine input blob is not staged")
        body = path.read_bytes()
        if (
            hashlib.sha256(body).hexdigest() != artifact["sha256"]
            or len(body) != artifact["byte_size"]
        ):
            raise ArtifactIntegrityMismatch(
                "formal engine input bytes do not match registered identity"
            )
        existing = connection.execute(
            """
            SELECT sha256, media_type, byte_size, storage_uri,
                   producing_revision_id, producing_run_id, origin_kind, source_ref
            FROM artifacts
            WHERE artifact_id = ?
            """,
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
                raise DomainConflict(
                    "artifact_id is already registered with different metadata"
                )
            return artifact["artifact_id"]
        content_owner = connection.execute(
            "SELECT artifact_id FROM artifacts WHERE sha256 = ? AND storage_uri = ?",
            (artifact["sha256"], artifact["storage_uri"]),
        ).fetchone()
        if content_owner is not None:
            return content_owner["artifact_id"]
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
        return artifact["artifact_id"]

    def _data_snapshot_artifact(
        self,
        *,
        artifact_id: str,
        sha256: str,
        body: bytes,
        media_type: str,
        source_ref: str,
    ) -> dict[str, Any]:
        return {
            "artifact_id": artifact_id,
            "sha256": sha256,
            "media_type": media_type,
            "byte_size": len(body),
            "storage_uri": f"cas://sha256/{sha256}",
            "producing_revision_id": None,
            "producing_run_id": None,
            "provenance": {
                "origin_kind": "service_generated",
                "source_ref": source_ref,
            },
        }

    def _register_data_snapshot_artifact(
        self,
        connection: sqlite3.Connection,
        artifact: dict[str, Any],
        recorded_at: str,
    ) -> str:
        return self._register_formal_input_artifact(connection, artifact, recorded_at)

    def _register_generated_artifact(
        self,
        connection: sqlite3.Connection,
        artifact: dict[str, Any],
        recorded_at: str,
    ) -> None:
        path = self.blob_path(artifact["sha256"])
        body = path.read_bytes()
        if (
            hashlib.sha256(body).hexdigest() != artifact["sha256"]
            or len(body) != artifact["byte_size"]
        ):
            raise ArtifactIntegrityMismatch(
                "generated artifact bytes do not match their content identity"
            )
        existing = connection.execute(
            """
            SELECT sha256, media_type, byte_size, storage_uri,
                   producing_revision_id, producing_run_id, origin_kind, source_ref
            FROM artifacts
            WHERE artifact_id = ?
            """,
            (artifact["artifact_id"],),
        ).fetchone()
        expected = (
            artifact["sha256"],
            artifact["media_type"],
            artifact["byte_size"],
            artifact["storage_uri"],
            artifact["producing_revision_id"],
            artifact["producing_run_id"],
            artifact["origin_kind"],
            artifact["source_ref"],
        )
        if existing is not None:
            if tuple(existing) != expected:
                raise ArtifactIntegrityMismatch(
                    "generated artifact_id has conflicting immutable metadata"
                )
            return
        content_owner = connection.execute(
            "SELECT artifact_id FROM artifacts WHERE sha256 = ? AND storage_uri = ?",
            (artifact["sha256"], artifact["storage_uri"]),
        ).fetchone()
        if content_owner is not None:
            raise ArtifactIntegrityMismatch(
                "generated artifact content has a conflicting artifact identity"
            )
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
                artifact["origin_kind"],
                artifact["source_ref"],
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
                SELECT pending.*
                FROM jobs AS pending
                WHERE (
                    pending.status = 'pending'
                    OR (
                        pending.job_type = 'formal.run'
                        AND pending.status = 'running'
                        AND pending.lease_expires_at <= strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    )
                )
                  AND (
                    pending.job_type != 'formal.run'
                    OR pending.status = 'running'
                    OR NOT EXISTS (
                        SELECT 1
                        FROM jobs AS active
                        WHERE active.job_type = 'formal.run'
                          AND active.status = 'running'
                    )
                  )
                ORDER BY pending.created_at, pending.job_id
                LIMIT 1
                """
            ).fetchone()
            if claimed is None:
                connection.execute("COMMIT")
                return None
            started_at = utc_now()
            was_running = claimed["status"] == "running"
            if claimed["job_type"] == "formal.run":
                claim_token = str(uuid.uuid4())
                transition = connection.execute(
                    """
                    UPDATE jobs
                    SET status = 'running', attempts = attempts + 1,
                        execution_version = execution_version + 1,
                        claim_epoch = claim_epoch + 1, claim_token = ?,
                        lease_expires_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '+30 seconds'),
                        started_at = COALESCE(started_at, ?), finished_at = NULL
                    WHERE job_id = ? AND status = ?
                      AND (
                        ? = 'pending'
                        OR lease_expires_at <= strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                      )
                    """,
                    (
                        claim_token,
                        started_at,
                        claimed["job_id"],
                        claimed["status"],
                        claimed["status"],
                    ),
                )
            else:
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
            claimed = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (claimed["job_id"],)
            ).fetchone()
            if claimed["job_type"] == "formal.run":
                run_spec = connection.execute(
                    """
                    SELECT spec_hash, variant_id, gate_policy_version
                    FROM run_specs WHERE run_spec_id = ?
                    """,
                    (claimed["run_spec_id"],),
                ).fetchone()
                event_type = "formal.run_started"
                payload = {
                    "job_id": claimed["job_id"],
                    "run_spec_id": claimed["run_spec_id"],
                    "run_id": claimed["run_id"],
                    "validation_id": claimed["validation_id"],
                    "candidate_revision_id": claimed["candidate_revision_id"],
                    "run_spec_hash": run_spec["spec_hash"],
                }
                if run_spec["gate_policy_version"] in {"m5-v1", "m8-v1"}:
                    payload.update(
                        {
                            "lifecycle_version": run_spec["gate_policy_version"],
                            "execution_version": claimed["execution_version"],
                        }
                    )
                    if was_running and claimed["checkpoint_seq"] > 0:
                        checkpoint = connection.execute(
                            """
                            SELECT a.sha256
                            FROM artifacts AS a
                            WHERE a.artifact_id = ?
                            """,
                            (claimed["checkpoint_artifact_id"],),
                        ).fetchone()
                        event_type = "formal.run_resumed"
                        payload.update(
                            {
                                "claim_epoch": claimed["claim_epoch"],
                                "checkpoint_seq": claimed["checkpoint_seq"],
                                "checkpoint_artifact_id": claimed[
                                    "checkpoint_artifact_id"
                                ],
                                "checkpoint_sha256": checkpoint["sha256"],
                                "calculation_context_sha256": claimed[
                                    "calculation_context_sha256"
                                ],
                            }
                        )
                        payload[
                            "next_session_index"
                            if run_spec["gate_policy_version"] == "m8-v1"
                            else "next_bar_index"
                        ] = claimed["next_bar_index"]
                started_event = self._insert_event(
                    connection,
                    event_type=event_type,
                    project_id=claimed["project_id"],
                    activity_id=claimed["activity_id"],
                    session_id=claimed["session_id"],
                    workbench_id=claimed["workbench_id"],
                    correlation_id=claimed["correlation_id"],
                    causation_id=claimed["job_id"],
                    recorded_at=started_at,
                    variant_id=run_spec["variant_id"],
                    base_revision_id=claimed["candidate_revision_id"],
                    payload=payload,
                )
            else:
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

        if claimed["job_type"] == "formal.run":
            return self._run_formal_job(claimed)

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

    def _run_formal_job(self, claimed: sqlite3.Row) -> dict[str, Any]:
        with self.database.connect() as connection:
            run_spec = connection.execute(
                """
                SELECT rs.*, input.sha256 AS engine_input_sha256,
                       input.media_type AS engine_input_media_type,
                       input.byte_size AS engine_input_byte_size,
                       input.storage_uri AS engine_input_storage_uri,
                       market.sha256 AS market_input_sha256,
                       market.media_type AS market_input_media_type,
                       market.byte_size AS market_input_byte_size,
                       market.storage_uri AS market_input_storage_uri,
                       candidate.project_parent_revision_id,
                       candidate.variant_parent_revision_id,
                       candidate.expected_project_head_version,
                       candidate.expected_variant_head_version,
                       revision.git_commit_oid AS candidate_commit_oid,
                       revision.git_tree_oid AS candidate_tree_oid
                FROM run_specs AS rs
                LEFT JOIN artifacts AS input
                  ON input.artifact_id = rs.engine_input_artifact_id
                LEFT JOIN artifacts AS market
                  ON market.artifact_id = rs.market_input_artifact_id
                JOIN workspace_merge_candidates AS candidate
                  ON candidate.candidate_revision_id = rs.candidate_revision_id
                 AND candidate.project_id = rs.project_id
                 AND candidate.activity_id = rs.activity_id
                JOIN workspace_revisions AS revision
                  ON revision.revision_id = rs.candidate_revision_id
                 AND revision.project_id = rs.project_id
                 AND revision.activity_id = rs.activity_id
                WHERE rs.run_spec_id = ?
                """,
                (claimed["run_spec_id"],),
            ).fetchone()
            strategy = connection.execute(
                """
                SELECT file.git_blob_oid, artifact.*
                FROM revision_files AS file
                JOIN artifacts AS artifact
                  ON artifact.artifact_id = file.artifact_id
                WHERE file.revision_id = ?
                  AND file.project_id = ?
                  AND file.activity_id = ?
                  AND file.path = 'strategy.py'
                """,
                (
                    claimed["candidate_revision_id"],
                    claimed["project_id"],
                    claimed["activity_id"],
                ),
                ).fetchone()

        if run_spec["gate_policy_version"] in {"m5-v1", "m8-v1"}:
            return self._run_m5_formal_job(claimed, run_spec, strategy)

        input_path = self.blob_path(run_spec["engine_input_sha256"])
        failed_gates = {
            "contract": "failed",
            "strategy_import": "failed",
            "smoke_run": "failed",
        }
        if not input_path.exists():
            return self._finish_formal_job(
                claimed,
                run_spec,
                gates=failed_gates,
                engine_result_artifact=None,
                manifest_artifact=None,
                calculation_hash=None,
                error_code="engine_input_missing",
            )
        engine_input = input_path.read_bytes()
        if (
            hashlib.sha256(engine_input).hexdigest()
            != run_spec["engine_input_sha256"]
            or len(engine_input) != run_spec["engine_input_byte_size"]
        ):
            return self._finish_formal_job(
                claimed,
                run_spec,
                gates=failed_gates,
                engine_result_artifact=None,
                manifest_artifact=None,
                calculation_hash=None,
                error_code="engine_input_integrity_mismatch",
            )

        import_failed_gates = {
            "contract": "passed",
            "strategy_import": "failed",
            "smoke_run": "failed",
        }
        if strategy is None:
            return self._finish_formal_job(
                claimed,
                run_spec,
                gates=import_failed_gates,
                engine_result_artifact=None,
                manifest_artifact=None,
                calculation_hash=None,
                error_code="strategy_import_failed",
            )
        strategy_path = self.blob_path(strategy["sha256"])
        if not strategy_path.exists():
            return self._finish_formal_job(
                claimed,
                run_spec,
                gates=import_failed_gates,
                engine_result_artifact=None,
                manifest_artifact=None,
                calculation_hash=None,
                error_code="strategy_import_failed",
            )
        strategy_source = strategy_path.read_bytes()
        if (
            hashlib.sha256(strategy_source).hexdigest() != strategy["sha256"]
            or len(strategy_source) != strategy["byte_size"]
        ):
            return self._finish_formal_job(
                claimed,
                run_spec,
                gates=import_failed_gates,
                engine_result_artifact=None,
                manifest_artifact=None,
                calculation_hash=None,
                error_code="strategy_import_failed",
            )

        execution = execute_formal_run(
            strategy_source=strategy_source,
            engine_input=engine_input,
            expected_engine_version=run_spec["engine_version"],
            expected_output_schema_version=run_spec["output_schema_version"],
        )
        if execution.error_code is not None:
            return self._finish_formal_job(
                claimed,
                run_spec,
                gates=execution.gates,
                engine_result_artifact=None,
                manifest_artifact=None,
                calculation_hash=None,
                error_code=execution.error_code,
            )

        engine_result = execution.engine_result
        calculation_hash = hashlib.sha256(engine_result).hexdigest()
        intent_tape = execution.intent_tape
        intent_tape_hash = hashlib.sha256(intent_tape).hexdigest()
        intent_tape_artifact_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"https://open-quant-studio.local/artifacts/intent-tape/{intent_tape_hash}",
            )
        )
        intent_tape_artifact = {
            "artifact_id": intent_tape_artifact_id,
            "sha256": intent_tape_hash,
            "media_type": "application/vnd.open-quant-studio.order-intents+json",
            "byte_size": len(intent_tape),
            "storage_uri": f"cas://sha256/{intent_tape_hash}",
            "producing_revision_id": None,
            "producing_run_id": None,
            "origin_kind": "service_generated",
            "source_ref": str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"https://open-quant-studio.local/artifacts/intent-tape-source/{intent_tape_hash}",
                )
            ),
        }
        engine_result_artifact_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"https://open-quant-studio.local/artifacts/engine-result/{calculation_hash}",
            )
        )
        engine_result_artifact = {
            "artifact_id": engine_result_artifact_id,
            "sha256": calculation_hash,
            "media_type": "application/json",
            "byte_size": len(engine_result),
            "storage_uri": f"cas://sha256/{calculation_hash}",
            "producing_revision_id": None,
            "producing_run_id": None,
            "origin_kind": "service_generated",
            "source_ref": str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"https://open-quant-studio.local/artifacts/engine-result-source/{calculation_hash}",
                )
            ),
        }
        manifest_artifact_id = str(
            uuid.uuid5(uuid.UUID(claimed["run_id"]), "formal-run-manifest")
        )
        manifest = {
            "schema_version": 1,
            "manifest_version": "m3-v1",
            "run_id": claimed["run_id"],
            "validation_id": claimed["validation_id"],
            "run_spec": self._formal_run_spec_manifest(run_spec),
            "revision": {
                "candidate_revision_id": claimed["candidate_revision_id"],
                "git_commit_oid": run_spec["candidate_commit_oid"],
                "git_tree_oid": run_spec["candidate_tree_oid"],
                "strategy_path": "strategy.py",
                "strategy_artifact_id": strategy["artifact_id"],
                "strategy_sha256": strategy["sha256"],
                "strategy_git_blob_oid": strategy["git_blob_oid"],
                "project_parent_revision_id": run_spec[
                    "project_parent_revision_id"
                ],
                "variant_parent_revision_id": run_spec[
                    "variant_parent_revision_id"
                ],
                "expected_project_head_version": run_spec[
                    "expected_project_head_version"
                ],
                "expected_variant_head_version": run_spec[
                    "expected_variant_head_version"
                ],
            },
            "engine_input": {
                "artifact_id": run_spec["engine_input_artifact_id"],
                "sha256": run_spec["engine_input_sha256"],
                "media_type": run_spec["engine_input_media_type"],
                "byte_size": run_spec["engine_input_byte_size"],
                "storage_uri": run_spec["engine_input_storage_uri"],
            },
            "strategy_execution": {
                "intent_tape_artifact_id": intent_tape_artifact_id,
                "intent_tape_sha256": intent_tape_hash,
                "intent_tape_byte_size": len(intent_tape),
                "intent_tape_storage_uri": f"cas://sha256/{intent_tape_hash}",
                "timing_authority": "oqs-strategy-host/m3-v1",
            },
            "engine_result": {
                "artifact_id": engine_result_artifact_id,
                "sha256": calculation_hash,
                "media_type": "application/json",
                "byte_size": len(engine_result),
                "storage_uri": f"cas://sha256/{calculation_hash}",
                "schema_version": run_spec["output_schema_version"],
                "engine_version": run_spec["engine_version"],
            },
            "gates": execution.gates,
            "logs": {
                "run_id": claimed["run_id"],
                "deletable": True,
                "included_in_calculation_hash": False,
            },
        }
        manifest_bytes = canonical_json(manifest).encode()
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_artifact = {
            "artifact_id": manifest_artifact_id,
            "sha256": manifest_hash,
            "media_type": "application/vnd.open-quant-studio.formal-run-manifest+json",
            "byte_size": len(manifest_bytes),
            "storage_uri": f"cas://sha256/{manifest_hash}",
            "producing_revision_id": claimed["candidate_revision_id"],
            "producing_run_id": claimed["run_id"],
            "origin_kind": "service_generated",
            "source_ref": claimed["validation_id"],
        }
        self.store_blob(intent_tape_hash, intent_tape)
        self.store_blob(calculation_hash, engine_result)
        self.store_blob(manifest_hash, manifest_bytes)
        return self._finish_formal_job(
            claimed,
            run_spec,
            gates=execution.gates,
            intent_tape_artifact=intent_tape_artifact,
            engine_result_artifact=engine_result_artifact,
            manifest_artifact=manifest_artifact,
            calculation_hash=calculation_hash,
            error_code=None,
        )

    def _m5_artifact_body(
        self,
        artifact: sqlite3.Row,
    ) -> bytes:
        path = self.blob_path(artifact["sha256"])
        if not path.exists():
            raise ArtifactBlobMissing("formal Run artifact blob is not staged")
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != artifact["sha256"] or len(body) != artifact["byte_size"]:
            raise ArtifactIntegrityMismatch("formal Run artifact bytes do not match registered identity")
        return body

    def _m5_artifact_descriptor(
        self,
        artifact_id: str,
        body: bytes,
        *,
        media_type: str,
        source_ref: str,
    ) -> dict[str, Any]:
        sha256 = hashlib.sha256(body).hexdigest()
        return {
            "artifact_id": artifact_id,
            "sha256": sha256,
            "media_type": media_type,
            "byte_size": len(body),
            "storage_uri": f"cas://sha256/{sha256}",
            "producing_revision_id": None,
            "producing_run_id": None,
            "origin_kind": "service_generated",
            "source_ref": source_ref,
        }

    def _m5_live_claim(
        self,
        connection: sqlite3.Connection,
        claimed: sqlite3.Row,
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT * FROM jobs
            WHERE job_id = ? AND job_type = 'formal.run' AND status = 'running'
              AND claim_token = ? AND execution_version = ? AND claim_epoch = ?
              AND lease_expires_at > strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                claimed["job_id"],
                claimed["claim_token"],
                claimed["execution_version"],
                claimed["claim_epoch"],
            ),
        ).fetchone()
        if row is None:
            raise JobTransitionConflict("formal Run claim fence was stale")
        return row

    def _m5_preparation(
        self,
        claimed: sqlite3.Row,
        run_spec: sqlite3.Row,
        strategy: sqlite3.Row | None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Prepare one immutable strategy tape and resolved engine input.

        The strategy host is deliberately invoked outside the database transaction.  The
        transaction below is the authority that publishes the resulting CAS identities and
        fences them to the exact running claim.
        """
        is_portfolio = (
            run_spec["engine_checkpoint_abi"]
            == "oqs-quant-engine/checkpoint-v2"
        )
        unit_key = "sessions" if is_portfolio else "bars"
        with self.database.connect() as connection:
            existing = connection.execute(
                """
                SELECT p.*, intent.sha256 AS intent_sha256, intent.byte_size AS intent_byte_size,
                       resolved.sha256 AS resolved_sha256, resolved.byte_size AS resolved_byte_size
                FROM formal_run_preparations AS p
                JOIN artifacts AS intent ON intent.artifact_id = p.intent_tape_artifact_id
                JOIN artifacts AS resolved ON resolved.artifact_id = p.resolved_engine_input_artifact_id
                WHERE p.job_id = ?
                """,
                (claimed["job_id"],),
            ).fetchone()
            market = connection.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ?",
                (run_spec["market_input_artifact_id"],),
            ).fetchone()
        if existing is not None:
            if market is None:
                raise ArtifactIntegrityMismatch("M5 market input artifact is missing")
            market_body = self._m5_artifact_body(market)
            try:
                market_input = json.loads(market_body)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ArtifactIntegrityMismatch("M5 market input is not valid JSON") from error
            if (
                not isinstance(market_input, dict)
                or not isinstance(market_input.get(unit_key), list)
                or len(market_input[unit_key]) != existing["total_bar_count"]
            ):
                raise ArtifactIntegrityMismatch("market input unit count is inconsistent")
            with self.database.connect() as connection:
                intent_row = connection.execute(
                    "SELECT * FROM artifacts WHERE artifact_id = ?",
                    (existing["intent_tape_artifact_id"],),
                ).fetchone()
                resolved_row = connection.execute(
                    "SELECT * FROM artifacts WHERE artifact_id = ?",
                    (existing["resolved_engine_input_artifact_id"],),
                ).fetchone()
            intent_body = self._m5_artifact_body(intent_row)
            resolved_body = self._m5_artifact_body(resolved_row)
            try:
                resolved_input = json.loads(resolved_body)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ArtifactIntegrityMismatch("resolved M5 input is not valid JSON") from error
            if (
                not isinstance(resolved_input, dict)
                or not isinstance(resolved_input.get(unit_key), list)
                or len(resolved_input[unit_key]) != existing["total_bar_count"]
            ):
                raise ArtifactIntegrityMismatch("resolved input unit count is inconsistent")
            return (
                {
                    "intent_artifact": dict(intent_row),
                    "resolved_artifact": dict(resolved_row),
                    "intent_body": intent_body,
                    "resolved_body": resolved_body,
                    "context": existing["calculation_context_sha256"],
                    "total_bar_count": existing["total_bar_count"],
                },
                None,
            )

        if market is None:
            return None, "contract_gate_failed"
        market_body = self._m5_artifact_body(market)
        try:
            market_input = json.loads(market_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, "contract_gate_failed"
        units = market_input.get(unit_key) if isinstance(market_input, dict) else None
        if (
            not isinstance(units, list)
            or not 1 <= len(units) <= 250000
            or any(
                not isinstance(unit, dict)
                or not isinstance(unit.get("session_seq"), int)
                or (
                    is_portfolio
                    and (
                        not isinstance(unit.get("bars"), list)
                        or not unit["bars"]
                    )
                )
                for unit in units
            )
        ):
            return None, "contract_gate_failed"
        if strategy is None:
            return None, "strategy_import_failed"
        with self.database.connect() as connection:
            strategy_body = self._m5_artifact_body(strategy)
        if is_portfolio:
            streamed_bars: list[dict[str, Any]] = []
            for session in units:
                for index, bar in enumerate(session["bars"]):
                    streamed_bars.append(
                        dict(bar)
                        | {
                            "session_seq": session["session_seq"],
                            "timestamp": session["timestamp"],
                            "session_end": index == len(session["bars"]) - 1,
                        }
                    )
            strategy_input_body = canonical_json(
                {"schema_version": 2, "bars": streamed_bars, "intents": []}
            ).encode()
        else:
            symbol = market_input["account"]["symbol"]
            strategy_input_body = canonical_json(
                {
                    "schema_version": 1,
                    "bars": [dict(bar) | {"symbol": symbol} for bar in units],
                    "intents": [],
                }
            ).encode()
        emitted = run_strategy_host(strategy_body, strategy_input_body)
        if emitted is None:
            return None, "strategy_import_failed"
        intent_body = canonical_json(emitted).encode()
        resolved_input = dict(market_input)
        # Caller-supplied intents are deliberately overwritten; only the fenced host tape is
        # authoritative for the formal calculation.
        resolved_input["intents"] = emitted
        resolved_body = canonical_json(resolved_input).encode()
        intent_hash = hashlib.sha256(intent_body).hexdigest()
        resolved_hash = hashlib.sha256(resolved_body).hexdigest()
        intent_artifact = self._m5_artifact_descriptor(
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"oqs:m5:intent:{intent_hash}")),
            intent_body,
            media_type="application/vnd.open-quant-studio.order-intents+json",
            source_ref=f"oqs:m5:intent:{intent_hash}",
        )
        resolved_artifact = self._m5_artifact_descriptor(
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"oqs:m5:resolved:{resolved_hash}")),
            resolved_body,
            media_type="application/json",
            source_ref=f"oqs:m5:resolved:{resolved_hash}",
        )
        context = hashlib.sha256(
            canonical_json(
                {
                    "run_id": claimed["run_id"],
                    "run_spec_hash": run_spec["spec_hash"],
                    "market_input_sha256": market["sha256"],
                    "intent_tape_sha256": intent_hash,
                    "resolved_engine_input_sha256": resolved_hash,
                    "engine_version": run_spec["engine_version"],
                    "engine_checkpoint_abi": run_spec["engine_checkpoint_abi"],
                }
            ).encode()
        ).hexdigest()
        self.store_blob(intent_hash, intent_body)
        self.store_blob(resolved_hash, resolved_body)
        prepared_at = utc_now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._m5_live_claim(connection, claimed)
            for descriptor in (intent_artifact, resolved_artifact):
                existing_content = connection.execute(
                    "SELECT artifact_id FROM artifacts WHERE sha256 = ? AND storage_uri = ?",
                    (descriptor["sha256"], descriptor["storage_uri"]),
                ).fetchone()
                if existing_content is None:
                    self._register_generated_artifact(connection, descriptor, prepared_at)
                else:
                    descriptor["artifact_id"] = existing_content["artifact_id"]
            connection.execute(
                """
                INSERT INTO formal_run_preparations(
                    job_id, intent_tape_artifact_id, resolved_engine_input_artifact_id,
                    calculation_context_sha256, total_bar_count, prepared_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    claimed["job_id"],
                    intent_artifact["artifact_id"],
                    resolved_artifact["artifact_id"],
                    context,
                    len(units),
                    prepared_at,
                ),
            )
            event = self._insert_event(
                connection,
                event_type="formal.run_prepared",
                project_id=claimed["project_id"],
                activity_id=claimed["activity_id"],
                session_id=claimed["session_id"],
                workbench_id=claimed["workbench_id"],
                correlation_id=claimed["correlation_id"],
                causation_id=claimed["job_id"],
                recorded_at=prepared_at,
                variant_id=run_spec["variant_id"],
                base_revision_id=claimed["candidate_revision_id"],
                payload={
                    "lifecycle_version": run_spec["gate_policy_version"],
                    "job_id": claimed["job_id"],
                    "run_spec_id": claimed["run_spec_id"],
                    "run_id": claimed["run_id"],
                    "validation_id": claimed["validation_id"],
                    "candidate_revision_id": claimed["candidate_revision_id"],
                    "run_spec_hash": run_spec["spec_hash"],
                    "execution_version": claimed["execution_version"],
                },
            )
            self._insert_outbox(connection, event)
            self._insert_log(
                connection,
                timestamp=prepared_at,
                level="info",
                priority="p2",
                event_code="formal.run.prepared",
                project_id=claimed["project_id"],
                activity_id=claimed["activity_id"],
                session_id=claimed["session_id"],
                job_id=claimed["job_id"],
                correlation_id=claimed["correlation_id"],
                message="Formal validation Run preparation was published",
                run_id=claimed["run_id"],
            )
            connection.execute("COMMIT")
        return (
            {
                "intent_artifact": intent_artifact,
                "resolved_artifact": resolved_artifact,
                "intent_body": intent_body,
                "resolved_body": resolved_body,
                "context": context,
                "total_bar_count": len(units),
            },
            None,
        )

    def _persist_m5_checkpoint(
        self,
        claimed: sqlite3.Row,
        run_spec: sqlite3.Row,
        preparation: dict[str, Any],
        checkpoint_body: bytes,
        previous_seq: int,
        previous_next: int,
    ) -> dict[str, Any]:
        decoded = json.loads(checkpoint_body)
        is_portfolio = (
            run_spec["engine_checkpoint_abi"]
            == "oqs-quant-engine/checkpoint-v2"
        )
        cursor_key = (
            "next_unprocessed_session_index"
            if is_portfolio
            else "next_unprocessed_bar_index"
        )
        next_index = decoded[cursor_key]
        if next_index <= previous_next or next_index > preparation["total_bar_count"]:
            raise ArtifactIntegrityMismatch("checkpoint cursor did not advance")
        sequence = previous_seq + 1
        checkpoint_hash = hashlib.sha256(checkpoint_body).hexdigest()
        artifact = self._m5_artifact_descriptor(
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"oqs:m5:checkpoint:{claimed['job_id']}:{sequence}:{checkpoint_hash}")),
            checkpoint_body,
            media_type="application/vnd.open-quant-studio.engine-checkpoint+json",
            source_ref=f"oqs:m5:checkpoint:{claimed['run_id']}:{sequence}",
        )
        self.store_blob(checkpoint_hash, checkpoint_body)
        created_at = utc_now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            live = self._m5_live_claim(connection, claimed)
            if (
                live["checkpoint_seq"] != previous_seq
                or live["next_bar_index"] != previous_next
                or live["calculation_context_sha256"] not in (None, preparation["context"])
            ):
                connection.execute("ROLLBACK")
                raise JobTransitionConflict("checkpoint predecessor fence was stale")
            self._register_generated_artifact(connection, artifact, created_at)
            changed = connection.execute(
                """
                UPDATE jobs
                SET checkpoint_seq = ?, next_bar_index = ?, checkpoint_artifact_id = ?,
                    calculation_context_sha256 = ?,
                    lease_expires_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '+30 seconds')
                WHERE job_id = ? AND status = 'running' AND claim_token = ?
                  AND execution_version = ? AND claim_epoch = ?
                  AND checkpoint_seq = ? AND next_bar_index = ?
                  AND (calculation_context_sha256 IS NULL OR calculation_context_sha256 = ?)
                  AND lease_expires_at > strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                (
                    sequence,
                    next_index,
                    artifact["artifact_id"],
                    preparation["context"],
                    claimed["job_id"],
                    claimed["claim_token"],
                    claimed["execution_version"],
                    claimed["claim_epoch"],
                    previous_seq,
                    previous_next,
                    preparation["context"],
                ),
            )
            if changed.rowcount != 1:
                connection.execute("ROLLBACK")
                raise JobTransitionConflict("checkpoint update fence was stale")
            connection.execute(
                """
                INSERT INTO formal_run_checkpoints(
                    job_id, checkpoint_seq, next_bar_index, execution_version,
                    claim_epoch, artifact_id, calculation_context_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claimed["job_id"],
                    sequence,
                    next_index,
                    claimed["execution_version"],
                    claimed["claim_epoch"],
                    artifact["artifact_id"],
                    preparation["context"],
                    created_at,
                ),
            )
            checkpoint_payload = {
                "lifecycle_version": run_spec["gate_policy_version"],
                "job_id": claimed["job_id"],
                "run_spec_id": claimed["run_spec_id"],
                "run_id": claimed["run_id"],
                "validation_id": claimed["validation_id"],
                "candidate_revision_id": claimed["candidate_revision_id"],
                "run_spec_hash": run_spec["spec_hash"],
                "execution_version": claimed["execution_version"],
                "claim_epoch": claimed["claim_epoch"],
                "checkpoint_seq": sequence,
                "checkpoint_artifact_id": artifact["artifact_id"],
                "checkpoint_sha256": checkpoint_hash,
                "calculation_context_sha256": preparation["context"],
            }
            checkpoint_payload[
                "next_session_index" if is_portfolio else "next_bar_index"
            ] = next_index
            event = self._insert_event(
                connection,
                event_type="formal.run_checkpointed",
                project_id=claimed["project_id"],
                activity_id=claimed["activity_id"],
                session_id=claimed["session_id"],
                workbench_id=claimed["workbench_id"],
                correlation_id=claimed["correlation_id"],
                causation_id=claimed["job_id"],
                recorded_at=created_at,
                variant_id=run_spec["variant_id"],
                base_revision_id=claimed["candidate_revision_id"],
                payload=checkpoint_payload,
            )
            self._insert_outbox(connection, event)
            self._insert_log(
                connection,
                timestamp=created_at,
                level="debug",
                priority="p3",
                event_code="formal.run.checkpointed",
                project_id=claimed["project_id"],
                activity_id=claimed["activity_id"],
                session_id=claimed["session_id"],
                job_id=claimed["job_id"],
                correlation_id=claimed["correlation_id"],
                message=f"Formal validation checkpoint {sequence} persisted",
                run_id=claimed["run_id"],
            )
            connection.execute("COMMIT")
        return {"artifact": artifact, "seq": sequence, "next": next_index}

    def _run_m5_formal_job(
        self,
        claimed: sqlite3.Row,
        run_spec: sqlite3.Row,
        strategy: sqlite3.Row | None,
    ) -> dict[str, Any]:
        failed_gates = {"contract": "failed", "strategy_import": "failed", "smoke_run": "failed"}
        import_gates = {"contract": "passed", "strategy_import": "failed", "smoke_run": "failed"}
        try:
            preparation, preparation_error = self._m5_preparation(claimed, run_spec, strategy)
        except (ArtifactBlobMissing, ArtifactIntegrityMismatch):
            return self._finish_formal_job(
                claimed, run_spec, gates=import_gates, engine_result_artifact=None,
                manifest_artifact=None, calculation_hash=None,
                error_code="checkpoint_integrity_mismatch",
            )
        if preparation_error is not None:
            gates = failed_gates if preparation_error == "contract_gate_failed" else import_gates
            return self._finish_formal_job(
                claimed, run_spec, gates=gates, engine_result_artifact=None,
                manifest_artifact=None, calculation_hash=None, error_code=preparation_error,
            )

        from oqs_quant_engine import (
            finalize_engine_checkpoint_v1,
            finalize_engine_checkpoint_v2,
            start_engine_checkpoint_v1,
            start_engine_checkpoint_v2,
            step_engine_checkpoint_v1,
            step_engine_checkpoint_v2,
        )

        is_portfolio = (
            run_spec["engine_checkpoint_abi"]
            == "oqs-quant-engine/checkpoint-v2"
        )
        start_checkpoint = (
            start_engine_checkpoint_v2 if is_portfolio else start_engine_checkpoint_v1
        )
        step_checkpoint = (
            step_engine_checkpoint_v2 if is_portfolio else step_engine_checkpoint_v1
        )
        finalize_checkpoint = (
            finalize_engine_checkpoint_v2
            if is_portfolio
            else finalize_engine_checkpoint_v1
        )

        checkpoint_seq = 0
        next_bar_index = 0
        checkpoint_artifact: dict[str, Any] | None = None
        with self.database.connect() as connection:
            latest = connection.execute(
                """
                SELECT c.*, a.sha256, a.byte_size
                FROM formal_run_checkpoints AS c
                JOIN artifacts AS a ON a.artifact_id = c.artifact_id
                WHERE c.job_id = ? ORDER BY c.checkpoint_seq DESC LIMIT 1
                """,
                (claimed["job_id"],),
            ).fetchone()
        if latest is None:
            try:
                checkpoint_body = start_checkpoint(
                    preparation["resolved_body"], preparation["context"], run_spec["checkpoint_batch_size"]
                )
            except ValueError:
                return self._finish_formal_job(
                    claimed, run_spec, gates=import_gates, engine_result_artifact=None,
                    manifest_artifact=None, calculation_hash=None,
                    error_code="smoke_run_failed",
                )
        else:
            with self.database.connect() as connection:
                checkpoint_row = connection.execute(
                    "SELECT * FROM artifacts WHERE artifact_id = ?",
                    (latest["artifact_id"],),
                ).fetchone()
            try:
                checkpoint_body = self._m5_artifact_body(checkpoint_row)
            except (ArtifactBlobMissing, ArtifactIntegrityMismatch):
                return self._finish_formal_job(
                    claimed, run_spec, gates=import_gates, engine_result_artifact=None,
                    manifest_artifact=None, calculation_hash=None,
                    error_code="checkpoint_integrity_mismatch",
                    m5_context=latest["calculation_context_sha256"],
                    m5_checkpoint_seq=latest["checkpoint_seq"],
                    m5_next_bar_index=latest["next_bar_index"],
                )
            if latest["calculation_context_sha256"] != preparation["context"]:
                return self._finish_formal_job(
                    claimed, run_spec, gates=import_gates, engine_result_artifact=None,
                    manifest_artifact=None, calculation_hash=None,
                    error_code="checkpoint_integrity_mismatch",
                )
            checkpoint_seq = latest["checkpoint_seq"]
            next_bar_index = latest["next_bar_index"]
            checkpoint_artifact = dict(checkpoint_row)

        while json.loads(checkpoint_body)["status"] != "complete":
            try:
                checkpoint_body = step_checkpoint(
                    preparation["resolved_body"], preparation["context"], checkpoint_body
                )
            except (ValueError, json.JSONDecodeError):
                return self._finish_formal_job(
                    claimed, run_spec, gates=import_gates, engine_result_artifact=None,
                    manifest_artifact=None, calculation_hash=None,
                    error_code="checkpoint_integrity_mismatch",
                    **(
                        {
                            "m5_context": preparation["context"],
                            "m5_checkpoint_seq": checkpoint_seq,
                            "m5_next_bar_index": next_bar_index,
                        }
                        if checkpoint_seq > 0
                        else {}
                    ),
                )
            persisted = self._persist_m5_checkpoint(
                claimed,
                run_spec,
                preparation,
                checkpoint_body,
                checkpoint_seq,
                next_bar_index,
            )
            checkpoint_seq = persisted["seq"]
            next_bar_index = persisted["next"]
            checkpoint_artifact = persisted["artifact"]

        try:
            engine_result = finalize_checkpoint(
                preparation["resolved_body"], preparation["context"], checkpoint_body
            )
        except ValueError as error:
            message = str(error)
            checkpoint_prefix = "[checkpoint_v2:" if is_portfolio else "[checkpoint_v1:"
            code = "checkpoint_integrity_mismatch" if message.startswith(checkpoint_prefix) else "smoke_run_failed"
            return self._finish_formal_job(
                claimed, run_spec, gates=import_gates, engine_result_artifact=None,
                manifest_artifact=None, calculation_hash=None, error_code=code,
                m5_context=preparation["context"], m5_checkpoint_seq=checkpoint_seq,
                m5_next_bar_index=next_bar_index,
            )
        engine_result_hash = hashlib.sha256(engine_result).hexdigest()
        engine_result_artifact = self._m5_artifact_descriptor(
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"oqs:m5:result:{engine_result_hash}")),
            engine_result,
            media_type="application/json",
            source_ref=f"oqs:m5:result:{engine_result_hash}",
        )
        checkpoint = json.loads(checkpoint_body)
        manifest = {
            "schema_version": 1,
            "manifest_version": run_spec["gate_policy_version"],
            "run_id": claimed["run_id"],
            "validation_id": claimed["validation_id"],
            "run_spec": self._formal_run_spec_manifest(run_spec),
            "revision": {
                "candidate_revision_id": claimed["candidate_revision_id"],
                "git_commit_oid": run_spec["candidate_commit_oid"],
                "git_tree_oid": run_spec["candidate_tree_oid"],
                "strategy_path": "strategy.py",
                "strategy_artifact_id": strategy["artifact_id"],
                "strategy_sha256": strategy["sha256"],
                "strategy_git_blob_oid": strategy["git_blob_oid"],
                "project_parent_revision_id": run_spec["project_parent_revision_id"],
                "variant_parent_revision_id": run_spec["variant_parent_revision_id"],
                "expected_project_head_version": run_spec["expected_project_head_version"],
                "expected_variant_head_version": run_spec["expected_variant_head_version"],
            },
            "market_input": {
                "artifact_id": run_spec["market_input_artifact_id"],
                "sha256": run_spec["market_input_sha256"],
                "media_type": run_spec["market_input_media_type"],
                "byte_size": run_spec["market_input_byte_size"],
                "storage_uri": run_spec["market_input_storage_uri"],
            },
            "strategy_execution": {
                "intent_tape_artifact_id": preparation["intent_artifact"]["artifact_id"],
                "intent_tape_sha256": preparation["intent_artifact"]["sha256"],
                "intent_tape_byte_size": preparation["intent_artifact"]["byte_size"],
                "intent_tape_storage_uri": preparation["intent_artifact"]["storage_uri"],
                "timing_authority": run_spec["strategy_protocol_version"],
                "frozen": True,
            },
            "resolved_engine_input": {
                "artifact_id": preparation["resolved_artifact"]["artifact_id"],
                "sha256": preparation["resolved_artifact"]["sha256"],
                "media_type": preparation["resolved_artifact"]["media_type"],
                "byte_size": preparation["resolved_artifact"]["byte_size"],
                "storage_uri": preparation["resolved_artifact"]["storage_uri"],
            },
            "checkpoint": {
                "engine_checkpoint_abi": run_spec["engine_checkpoint_abi"],
                "checkpoint_batch_size": run_spec["checkpoint_batch_size"],
                "final_checkpoint_seq": checkpoint_seq,
                "calculation_context_sha256": preparation["context"],
            },
            "engine_result": {
                "artifact_id": engine_result_artifact["artifact_id"],
                "sha256": engine_result_hash,
                "media_type": "application/json",
                "byte_size": len(engine_result),
                "storage_uri": engine_result_artifact["storage_uri"],
                "schema_version": run_spec["output_schema_version"],
                "engine_version": run_spec["engine_version"],
            },
            "gates": {"contract": "passed", "strategy_import": "passed", "smoke_run": "passed"},
            "logs": {"run_id": claimed["run_id"], "deletable": True, "included_in_calculation_hash": False},
        }
        manifest["checkpoint"][
            "final_next_session_index" if is_portfolio else "final_next_bar_index"
        ] = next_bar_index
        manifest_body = canonical_json(manifest).encode()
        manifest_hash = hashlib.sha256(manifest_body).hexdigest()
        manifest_artifact = self._m5_artifact_descriptor(
            str(uuid.uuid5(uuid.UUID(claimed["run_id"]), "formal-run-manifest")),
            manifest_body,
            media_type="application/vnd.open-quant-studio.formal-run-manifest+json",
            source_ref=claimed["validation_id"],
        )
        self.store_blob(engine_result_hash, engine_result)
        self.store_blob(manifest_hash, manifest_body)
        return self._finish_formal_job(
            claimed,
            run_spec,
            gates={"contract": "passed", "strategy_import": "passed", "smoke_run": "passed"},
            intent_tape_artifact=preparation["intent_artifact"],
            engine_result_artifact=engine_result_artifact,
            manifest_artifact=manifest_artifact,
            calculation_hash=engine_result_hash,
            error_code=None,
            m5_context=preparation["context"],
            m5_checkpoint_seq=checkpoint_seq,
            m5_next_bar_index=next_bar_index,
        )

    def _formal_run_spec_manifest(self, run_spec: sqlite3.Row) -> dict[str, Any]:
        manifest = {
            "run_spec_id": run_spec["run_spec_id"],
            "spec_hash": run_spec["spec_hash"],
            "project_id": run_spec["project_id"],
            "activity_id": run_spec["activity_id"],
            "variant_id": run_spec["variant_id"],
            "candidate_revision_id": run_spec["candidate_revision_id"],
            "data_snapshot_id": run_spec["data_snapshot_id"],
            "data_snapshot_sha256": run_spec["data_snapshot_sha256"],
            "strategy_tree_oid": run_spec["strategy_tree_oid"],
            "parameters_sha256": run_spec["parameters_sha256"],
            "cost_model_sha256": run_spec["cost_model_sha256"],
            "environment_lock_sha256": run_spec["environment_lock_sha256"],
            "engine_version": run_spec["engine_version"],
            "price_basis": run_spec["price_basis"],
            "cutoff": run_spec["cutoff"],
            "timezone": run_spec["timezone"],
            "sample_start": run_spec["sample_start"],
            "sample_end": run_spec["sample_end"],
            "random_seed": run_spec["random_seed"],
            "output_schema_version": run_spec["output_schema_version"],
            "gate_policy_version": run_spec["gate_policy_version"],
        }
        if run_spec["gate_policy_version"] in {"m5-v1", "m8-v1"}:
            manifest.update(
                {
                    "market_input_artifact_id": run_spec["market_input_artifact_id"],
                    "strategy_protocol_version": run_spec["strategy_protocol_version"],
                    "checkpoint_batch_size": run_spec["checkpoint_batch_size"],
                    "engine_checkpoint_abi": run_spec["engine_checkpoint_abi"],
                }
            )
        else:
            manifest["engine_input_artifact_id"] = run_spec["engine_input_artifact_id"]
        return manifest

    def _run_spec_read_model(self, run_spec: sqlite3.Row) -> dict[str, Any]:
        detail = dict(run_spec)
        if run_spec["gate_policy_version"] in {"m5-v1", "m8-v1"}:
            detail.pop("engine_input_artifact_id", None)
        else:
            for key in (
                "market_input_artifact_id",
                "strategy_protocol_version",
                "checkpoint_batch_size",
                "engine_checkpoint_abi",
            ):
                detail.pop(key, None)
        return detail

    def _finish_formal_job(
        self,
        claimed: sqlite3.Row,
        run_spec: sqlite3.Row,
        *,
        gates: dict[str, str],
        intent_tape_artifact: dict[str, Any] | None = None,
        engine_result_artifact: dict[str, Any] | None,
        manifest_artifact: dict[str, Any] | None,
        calculation_hash: str | None,
        error_code: str | None,
        m5_context: str | None = None,
        m5_checkpoint_seq: int | None = None,
        m5_next_bar_index: int | None = None,
    ) -> dict[str, Any]:
        status = "succeeded" if error_code is None else "failed"
        finished_at = utc_now()
        result = {
            "run_id": claimed["run_id"],
            "validation_id": claimed["validation_id"],
            "gates": gates,
            "calculation_hash": calculation_hash,
        }
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if (
                intent_tape_artifact is not None
                and engine_result_artifact is not None
                and manifest_artifact is not None
            ):
                self._register_generated_artifact(
                    connection, intent_tape_artifact, finished_at
                )
                self._register_generated_artifact(
                    connection, engine_result_artifact, finished_at
                )
                self._register_generated_artifact(
                    connection, manifest_artifact, finished_at
                )
            transition = connection.execute(
                """
                UPDATE jobs
                SET status = ?, result_json = ?, error_code = ?,
                    error_message = ?, finished_at = ?,
                    claim_token = NULL, lease_expires_at = NULL
                WHERE job_id = ? AND status = 'running'
                  AND claim_token = ? AND execution_version = ?
                  AND claim_epoch = ?
                  AND (? IS NULL OR checkpoint_seq = ?)
                  AND (? IS NULL OR next_bar_index = ?)
                  AND (? IS NULL OR calculation_context_sha256 = ?)
                  AND lease_expires_at > strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                (
                    status,
                    canonical_json(result),
                    error_code,
                    None if error_code is None else error_code.replace("_", " "),
                    finished_at,
                    claimed["job_id"],
                    claimed["claim_token"],
                    claimed["execution_version"],
                    claimed["claim_epoch"],
                    m5_checkpoint_seq,
                    m5_checkpoint_seq,
                    m5_next_bar_index,
                    m5_next_bar_index,
                    m5_context,
                    m5_context,
                ),
            )
            if transition.rowcount != 1:
                connection.execute("ROLLBACK")
                raise JobTransitionConflict("running formal job completion was stale")
            connection.execute(
                """
                INSERT INTO formal_runs(
                    run_id, run_spec_id, project_id, activity_id, variant_id,
                    candidate_revision_id, status, engine_result_artifact_id,
                    manifest_artifact_id, calculation_hash, error_code,
                    execution_version, retry_of_run_id, cancel_reason, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    claimed["run_id"],
                    claimed["run_spec_id"],
                    claimed["project_id"],
                    claimed["activity_id"],
                    run_spec["variant_id"],
                    claimed["candidate_revision_id"],
                    status,
                    None
                    if engine_result_artifact is None
                    else engine_result_artifact["artifact_id"],
                    None
                    if manifest_artifact is None
                    else manifest_artifact["artifact_id"],
                    calculation_hash,
                    error_code,
                    claimed["execution_version"],
                    claimed["retry_of_run_id"],
                    finished_at,
                ),
            )
            if (
                intent_tape_artifact is not None
                and engine_result_artifact is not None
                and manifest_artifact is not None
            ):
                connection.executemany(
                    "INSERT INTO run_artifacts(run_id, kind, artifact_id) VALUES (?, ?, ?)",
                    [
                        (
                            claimed["run_id"],
                            "intent_tape",
                            intent_tape_artifact["artifact_id"],
                        ),
                        (
                            claimed["run_id"],
                            "engine_result",
                            engine_result_artifact["artifact_id"],
                        ),
                        (
                            claimed["run_id"],
                            "manifest",
                            manifest_artifact["artifact_id"],
                        ),
                    ],
                )
            connection.execute(
                """
                INSERT INTO merge_validations(
                    validation_id, project_id, activity_id, variant_id,
                    candidate_revision_id, run_id, gate_policy_version,
                    engine_version, contract_outcome,
                    strategy_import_outcome, smoke_run_outcome,
                    outcome, manifest_artifact_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claimed["validation_id"],
                    claimed["project_id"],
                    claimed["activity_id"],
                    run_spec["variant_id"],
                    claimed["candidate_revision_id"],
                    claimed["run_id"],
                    run_spec["gate_policy_version"],
                    run_spec["engine_version"],
                    gates["contract"],
                    gates["strategy_import"],
                    gates["smoke_run"],
                    "passed" if status == "succeeded" else "failed",
                    None
                    if manifest_artifact is None
                    else manifest_artifact["artifact_id"],
                    finished_at,
                ),
            )
            event_payload = {
                "job_id": claimed["job_id"],
                "run_spec_id": claimed["run_spec_id"],
                "run_id": claimed["run_id"],
                "validation_id": claimed["validation_id"],
                "candidate_revision_id": claimed["candidate_revision_id"],
                "run_spec_hash": run_spec["spec_hash"],
                "status": status,
                "gates": gates,
                "engine_result_artifact_id": None
                if engine_result_artifact is None
                else engine_result_artifact["artifact_id"],
                "engine_result_sha256": None
                if engine_result_artifact is None
                else engine_result_artifact["sha256"],
                "manifest_artifact_id": None
                if manifest_artifact is None
                else manifest_artifact["artifact_id"],
                "manifest_sha256": None
                if manifest_artifact is None
                else manifest_artifact["sha256"],
                "calculation_hash": calculation_hash,
                "error_code": error_code,
            }
            if run_spec["gate_policy_version"] in {"m5-v1", "m8-v1"}:
                event_payload.update(
                    {
                        "lifecycle_version": run_spec["gate_policy_version"],
                        "execution_version": claimed["execution_version"],
                    }
                )
            event = self._insert_event(
                connection,
                event_type="formal.run_completed",
                project_id=claimed["project_id"],
                activity_id=claimed["activity_id"],
                session_id=claimed["session_id"],
                workbench_id=claimed["workbench_id"],
                correlation_id=claimed["correlation_id"],
                causation_id=claimed["job_id"],
                recorded_at=finished_at,
                variant_id=run_spec["variant_id"],
                base_revision_id=claimed["candidate_revision_id"],
                payload=event_payload,
            )
            self._insert_outbox(connection, event)
            self._insert_log(
                connection,
                timestamp=finished_at,
                level="info" if status == "succeeded" else "error",
                priority="p2" if status == "succeeded" else "p1",
                event_code=f"formal.run.{status}",
                project_id=claimed["project_id"],
                activity_id=claimed["activity_id"],
                session_id=claimed["session_id"],
                job_id=claimed["job_id"],
                correlation_id=claimed["correlation_id"],
                message=(
                    "Formal validation Run completed"
                    if status == "succeeded"
                    else "Formal validation Run failed"
                ),
                run_id=claimed["run_id"],
            )
            connection.execute("COMMIT")
        return self.job(claimed["job_id"])

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
                WHERE job_id = ? AND status = 'running' AND attempts = ?
                """,
                (
                    status,
                    canonical_json(result) if result is not None else None,
                    error_code,
                    error_message,
                    finished_at,
                    claimed["job_id"],
                    claimed["attempts"],
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
            "execution_version": row["execution_version"],
            "claim_epoch": row["claim_epoch"],
            "checkpoint_seq": row["checkpoint_seq"],
            "next_bar_index": row["next_bar_index"],
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
        activity_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
        levels: list[str] | None = None,
        priorities: list[str] | None = None,
        query: str | None = None,
        after_log_seq: int = 0,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        predicates: list[str] = []
        parameters: list[str | int] = []
        if project_id is not None:
            predicates.append("project_id = ?")
            parameters.append(project_id)
        if level is not None:
            predicates.append("level = ?")
            parameters.append(level)
        if priority is not None:
            predicates.append("priority = ?")
            parameters.append(priority)
        for value, column in (
            (activity_id, "activity_id"),
            (session_id, "session_id"),
            (run_id, "run_id"),
        ):
            if value is not None:
                predicates.append(f"{column} = ?")
                parameters.append(value)
        if from_timestamp is not None:
            predicates.append("timestamp >= ?")
            parameters.append(from_timestamp)
        if to_timestamp is not None:
            predicates.append("timestamp <= ?")
            parameters.append(to_timestamp)
        for values, column in ((levels, "level"), (priorities, "priority")):
            if values:
                placeholders = ",".join("?" for _ in values)
                predicates.append(f"{column} IN ({placeholders})")
                parameters.extend(values)
        if query is not None:
            predicates.append(
                "log_seq IN (SELECT rowid FROM diagnostic_logs_fts "
                "WHERE diagnostic_logs_fts MATCH ?)"
            )
            parameters.append(query)
        predicates.append("log_seq > ?")
        parameters.append(after_log_seq)
        where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT log_id, log_seq, timestamp, level, priority,
                       component, event_code,
                       project_id, activity_id, session_id, task_id, job_id,
                       run_id, correlation_id, message
                FROM diagnostic_logs
                {where}
                ORDER BY log_seq
                LIMIT ?
                """,
                [*parameters, limit],
            ).fetchall()
        return [dict(row) for row in rows]

    def log_page(self, **filters: Any) -> dict[str, Any]:
        limit = filters.pop("limit", 1000)
        logs = self.logs(limit=limit, **filters)
        return {
            "logs": logs,
            "next_after_log_seq": logs[-1]["log_seq"] if len(logs) == limit else None,
        }

    def projects(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT project_id, created_at
                FROM research_projects
                ORDER BY created_at, project_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def activities(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT activity_id, project_id, created_at
                FROM activities
                WHERE project_id = ?
                ORDER BY created_at, activity_id
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def preview_data_import(
        self, body: bytes, file_name: str, source_format: str
    ) -> dict[str, object]:
        preview = preview_data_import(body, file_name, source_format)
        source = preview["source"]
        self.store_blob(source["sha256"], body)
        return preview

    def local_data_imports(self) -> list[dict[str, object]]:
        imports = self.data_root / "imports"
        if not imports.exists():
            return []
        files = [
            {
                "file_name": entry.name,
                "source_format": "csv" if entry.suffix.lower() == ".csv" else "parquet",
                "byte_size": entry.stat().st_size,
            }
            for entry in imports.iterdir()
            if entry.is_file() and entry.suffix.lower() in {".csv", ".parquet"}
        ]
        return sorted(files, key=lambda item: str(item["file_name"]))

    def preview_local_data_import(self, file_name: str) -> dict[str, object]:
        candidate = self.data_root / "imports" / file_name
        if candidate.name != file_name or not candidate.is_file():
            raise DataImportValidationError(
                [{"row_number": 1, "field": "file_name", "message": "is not available"}]
            )
        source_format = "csv" if candidate.suffix.lower() == ".csv" else "parquet"
        if candidate.suffix.lower() not in {".csv", ".parquet"}:
            raise DataImportValidationError(
                [{"row_number": 1, "field": "file_name", "message": "must name a csv or parquet file"}]
            )
        return self.preview_data_import(
            candidate.read_bytes(), candidate.name, source_format
        )

    def data_snapshots(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT d.*, source.sha256 AS source_sha256,
                       normalized.sha256 AS normalized_sha256,
                       market_input.sha256 AS market_input_sha256
                FROM data_snapshots AS d
                JOIN artifacts AS source ON source.artifact_id = d.source_artifact_id
                JOIN artifacts AS normalized ON normalized.artifact_id = d.normalized_artifact_id
                JOIN artifacts AS market_input ON market_input.artifact_id = d.market_input_artifact_id
                WHERE d.project_id = ?
                ORDER BY d.created_at, d.snapshot_id
                """,
                (project_id,),
            ).fetchall()
        return [self._data_snapshot_read_model(row) for row in rows]

    def data_snapshot(
        self, project_id: str, snapshot_id: str
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT d.*, source.sha256 AS source_sha256,
                       normalized.sha256 AS normalized_sha256,
                       market_input.sha256 AS market_input_sha256
                FROM data_snapshots AS d
                JOIN artifacts AS source ON source.artifact_id = d.source_artifact_id
                JOIN artifacts AS normalized ON normalized.artifact_id = d.normalized_artifact_id
                JOIN artifacts AS market_input ON market_input.artifact_id = d.market_input_artifact_id
                WHERE d.project_id = ? AND d.snapshot_id = ?
                """,
                (project_id, snapshot_id),
            ).fetchone()
        return None if row is None else self._data_snapshot_read_model(row)

    def data_snapshot_market_input(
        self, project_id: str, snapshot_id: str
    ) -> tuple[dict[str, Any], bytes] | None:
        snapshot = self.data_snapshot(project_id, snapshot_id)
        if snapshot is None:
            return None
        content = self.artifact_content(project_id, snapshot["market_input_artifact_id"])
        if content is None:
            return None
        return content

    @staticmethod
    def _data_snapshot_read_model(row: sqlite3.Row) -> dict[str, Any]:
        snapshot = dict(row)
        snapshot["mapping"] = json.loads(snapshot.pop("mapping_json"))
        snapshot["symbols"] = json.loads(snapshot.pop("symbols_json"))
        return snapshot

    def forward_test(
        self, project_id: str, forward_test_id: str
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM forward_tests
                WHERE project_id = ? AND forward_test_id = ?
                """,
                (project_id, forward_test_id),
            ).fetchone()
        return None if row is None else dict(row)

    def runs(
        self, project_id: str, *, activity_id: str | None = None
    ) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT j.run_id, j.job_id, j.run_spec_id, j.project_id, j.activity_id,
                       rs.variant_id, j.candidate_revision_id,
                       COALESCE(r.status, j.status) AS status,
                       r.engine_result_artifact_id, r.manifest_artifact_id,
                       r.calculation_hash, r.error_code, r.finished_at,
                       j.created_at AS queued_at, j.started_at,
                       j.finished_at AS job_finished_at, j.execution_version,
                       j.checkpoint_seq, j.next_bar_index, j.retry_of_run_id,
                       j.validation_id, v.outcome AS validation_outcome,
                       v.contract_outcome, v.strategy_import_outcome,
                       v.smoke_run_outcome
                FROM jobs AS j
                JOIN run_specs AS rs ON rs.run_spec_id = j.run_spec_id
                LEFT JOIN formal_runs AS r
                  ON r.run_id = j.run_id AND r.project_id = j.project_id
                LEFT JOIN merge_validations AS v
                  ON v.run_id = j.run_id AND v.project_id = j.project_id
                WHERE j.job_type = 'formal.run' AND j.project_id = ?
                  AND (? IS NULL OR j.activity_id = ?)
                ORDER BY COALESCE(r.finished_at, j.created_at), j.run_id
                """,
                (project_id, activity_id, activity_id),
            ).fetchall()
        results = []
        for row in rows:
            run = dict(row)
            if run["validation_outcome"] is None:
                run["validation_outcome"] = "not_run"
            if run["contract_outcome"] is None:
                run["contract_outcome"] = "not_run"
            if run["strategy_import_outcome"] is None:
                run["strategy_import_outcome"] = "not_run"
            if run["smoke_run_outcome"] is None:
                run["smoke_run_outcome"] = "not_run"
            run["gates"] = {
                "contract": run.pop("contract_outcome"),
                "strategy_import": run.pop("strategy_import_outcome"),
                "smoke_run": run.pop("smoke_run_outcome"),
            }
            if run["status"] in {"pending", "running"}:
                results.append(run)
                continue
            if run["status"] == "cancelled":
                results.append(
                    {
                        key: run[key]
                        for key in (
                            "run_id", "run_spec_id", "project_id", "activity_id", "variant_id",
                            "candidate_revision_id", "status", "engine_result_artifact_id",
                            "manifest_artifact_id", "calculation_hash", "error_code", "queued_at",
                            "started_at", "finished_at", "execution_version", "checkpoint_seq",
                            "next_bar_index", "retry_of_run_id", "validation_id", "validation_outcome",
                            "gates",
                        )
                    }
                    | {"cancel_reason": "user_requested"}
                )
                continue
            results.append(
                {
                    key: run[key]
                    for key in (
                        "run_id", "run_spec_id", "project_id", "activity_id", "variant_id",
                        "candidate_revision_id", "status", "engine_result_artifact_id",
                        "manifest_artifact_id", "calculation_hash", "error_code", "finished_at",
                        "validation_id", "validation_outcome", "gates",
                    )
                }
            )
        return results

    def run(self, project_id: str, run_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT r.*, j.run_id AS job_run_id, j.job_id, j.project_id AS job_project_id,
                       j.activity_id AS job_activity_id, j.run_spec_id AS job_run_spec_id,
                       rs.variant_id AS job_variant_id, j.candidate_revision_id AS job_candidate_revision_id,
                       j.status AS job_status, j.validation_id AS job_validation_id,
                       j.retry_of_run_id AS job_retry_of_run_id,
                       j.created_at AS queued_at, j.started_at,
                       j.finished_at AS job_finished_at, j.execution_version AS job_execution_version,
                       j.checkpoint_seq, j.next_bar_index
                FROM jobs AS j
                JOIN run_specs AS rs ON rs.run_spec_id = j.run_spec_id
                LEFT JOIN formal_runs AS r
                  ON r.run_id = j.run_id
                 AND r.project_id = j.project_id
                 AND r.activity_id = j.activity_id
                WHERE j.project_id = ? AND j.run_id = ?
                """,
                (project_id, run_id),
            ).fetchone()
            if row is None:
                return None
            run_spec = connection.execute(
                """
                SELECT *
                FROM run_specs
                WHERE run_spec_id = ? AND project_id = ? AND activity_id = ?
                """,
                (row["run_spec_id"] or row["job_run_spec_id"], project_id, row["activity_id"] or row["job_activity_id"]),
            ).fetchone()
            validation = connection.execute(
                """
                SELECT *
                FROM merge_validations
                WHERE run_id = ? AND project_id = ? AND activity_id = ?
                """,
                (run_id, project_id, row["activity_id"] or row["job_activity_id"]),
            ).fetchone()
            artifact_rows = connection.execute(
                """
                SELECT ra.kind, a.*
                FROM run_artifacts AS ra
                JOIN artifacts AS a ON a.artifact_id = ra.artifact_id
                WHERE ra.run_id = ?
                ORDER BY ra.kind
                """,
                (run_id,),
                ).fetchall()
            log_rows = connection.execute(
                """
                SELECT log_id, log_seq, timestamp, level, priority, component, event_code,
                       project_id, activity_id, session_id, task_id, job_id,
                       run_id, correlation_id, message
                FROM diagnostic_logs
                WHERE project_id = ? AND run_id = ?
                ORDER BY log_seq
                """,
                (project_id, run_id),
            ).fetchall()

        if row["status"] is None:
            run_detail = {
                "run_id": row["job_run_id"],
                "run_spec_id": row["job_run_spec_id"],
                "project_id": project_id,
                "activity_id": row["job_activity_id"],
                "variant_id": row["job_variant_id"],
                "candidate_revision_id": row["job_candidate_revision_id"],
                "status": row["job_status"],
                "engine_result_artifact_id": None,
                "manifest_artifact_id": None,
                "calculation_hash": None,
                "error_code": None,
                "queued_at": row["queued_at"],
                "started_at": row["started_at"],
                "finished_at": None,
                "execution_version": row["job_execution_version"],
                "checkpoint_seq": row["checkpoint_seq"],
                "next_bar_index": row["next_bar_index"],
                "retry_of_run_id": row["job_retry_of_run_id"],
                "validation_id": row["job_validation_id"],
                "validation_outcome": "not_run",
                "gates": {"contract": "not_run", "strategy_import": "not_run", "smoke_run": "not_run"},
                "job_id": row["job_id"],
                "job_finished_at": None,
            }
            return {
                "run": run_detail,
                "run_spec": self._run_spec_read_model(run_spec),
                "validation": {
                    "validation_id": row["job_validation_id"],
                    "gate_policy_version": run_spec["gate_policy_version"],
                    "engine_version": run_spec["engine_version"],
                    "gates": {"contract": "not_run", "strategy_import": "not_run", "smoke_run": "not_run"},
                    "outcome": "not_run",
                    "manifest_artifact_id": None,
                    "created_at": row["queued_at"],
                },
                "artifacts": {},
                "manifest": None,
                "engine_result": None,
                "intent_tape": None,
                "logs": [dict(log) for log in log_rows],
            }
        if run_spec is None or validation is None:
            raise ArtifactIntegrityMismatch("formal Run lineage is incomplete")
        artifacts = {artifact["kind"]: dict(artifact) for artifact in artifact_rows}
        run_detail = {
            "run_id": row["run_id"],
            "run_spec_id": row["run_spec_id"],
            "project_id": row["project_id"],
            "activity_id": row["activity_id"],
            "variant_id": row["variant_id"],
            "candidate_revision_id": row["candidate_revision_id"],
            "status": row["status"],
            "engine_result_artifact_id": row["engine_result_artifact_id"],
            "manifest_artifact_id": row["manifest_artifact_id"],
            "calculation_hash": row["calculation_hash"],
            "error_code": row["error_code"],
            "finished_at": row["finished_at"],
            "job_id": row["job_id"],
            "queued_at": row["queued_at"],
            "started_at": row["started_at"],
            "job_finished_at": row["job_finished_at"],
        }
        validation_detail = {
            "validation_id": validation["validation_id"],
            "gate_policy_version": validation["gate_policy_version"],
            "engine_version": validation["engine_version"],
            "gates": {
                "contract": validation["contract_outcome"],
                "strategy_import": validation["strategy_import_outcome"],
                "smoke_run": validation["smoke_run_outcome"],
            },
            "outcome": validation["outcome"],
            "manifest_artifact_id": validation["manifest_artifact_id"],
            "created_at": validation["created_at"],
        }
        if row["status"] == "cancelled":
            if (
                artifacts
                or row["engine_result_artifact_id"] is not None
                or row["manifest_artifact_id"] is not None
                or row["calculation_hash"] is not None
                or validation["manifest_artifact_id"] is not None
                or validation["outcome"] != "not_run"
            ):
                raise ArtifactIntegrityMismatch("cancelled formal Run has result artifact state")
            cancelled_run = {
                "run_id": row["run_id"],
                "run_spec_id": row["run_spec_id"],
                "project_id": row["project_id"],
                "activity_id": row["activity_id"],
                "variant_id": row["variant_id"],
                "candidate_revision_id": row["candidate_revision_id"],
                "status": "cancelled",
                "engine_result_artifact_id": None,
                "manifest_artifact_id": None,
                "calculation_hash": None,
                "error_code": None,
                "queued_at": row["queued_at"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "execution_version": row["execution_version"],
                "checkpoint_seq": row["checkpoint_seq"],
                "next_bar_index": row["next_bar_index"],
                "retry_of_run_id": row["retry_of_run_id"],
                "validation_id": validation["validation_id"],
                "validation_outcome": "not_run",
                "gates": validation_detail["gates"],
                "cancel_reason": row["cancel_reason"],
                "job_id": row["job_id"],
                "job_finished_at": row["job_finished_at"],
            }
            return {
                "run": cancelled_run,
                "run_spec": self._run_spec_read_model(run_spec),
                "validation": validation_detail,
                "artifacts": {},
                "manifest": None,
                "engine_result": None,
                "intent_tape": None,
                "logs": [dict(log) for log in log_rows],
            }
        if row["status"] == "failed":
            if (
                artifacts
                or row["engine_result_artifact_id"] is not None
                or row["manifest_artifact_id"] is not None
                or row["calculation_hash"] is not None
                or validation["manifest_artifact_id"] is not None
                or validation["outcome"] != "failed"
            ):
                raise ArtifactIntegrityMismatch(
                    "failed formal Run has result artifact state"
                )
            return {
                "run": run_detail,
                "run_spec": self._run_spec_read_model(run_spec),
                "validation": validation_detail,
                "artifacts": {},
                "manifest": None,
                "engine_result": None,
                "intent_tape": None,
                "logs": [dict(log) for log in log_rows],
            }

        core_artifact_kinds = {"intent_tape", "engine_result", "manifest"}
        report_artifact_kinds = {"report_json", "report_html"}
        if not core_artifact_kinds.issubset(artifacts) or not set(artifacts).issubset(
            core_artifact_kinds | report_artifact_kinds
        ):
            raise ArtifactIntegrityMismatch("formal Run artifact set is incomplete")
        if bool(report_artifact_kinds & set(artifacts)) and not report_artifact_kinds.issubset(
            artifacts
        ):
            raise ArtifactIntegrityMismatch("formal Run report artifact set is incomplete")
        if (
            artifacts["engine_result"]["artifact_id"]
            != row["engine_result_artifact_id"]
            or artifacts["manifest"]["artifact_id"] != row["manifest_artifact_id"]
            or artifacts["engine_result"]["sha256"] != row["calculation_hash"]
            or validation["manifest_artifact_id"] != row["manifest_artifact_id"]
            or validation["outcome"] != "passed"
        ):
            raise ArtifactIntegrityMismatch("formal Run artifact identity is inconsistent")

        content: dict[str, object] = {}
        artifact_details: dict[str, dict[str, Any]] = {}
        for kind, artifact in artifacts.items():
            loaded = self.artifact_content(project_id, artifact["artifact_id"])
            if loaded is None:
                raise ArtifactIntegrityMismatch("formal Run artifact lost project ownership")
            detail, body = loaded
            if kind in core_artifact_kinds:
                try:
                    content[kind] = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError) as error:
                    raise ArtifactIntegrityMismatch(
                        "formal Run artifact is not valid JSON"
                    ) from error
            artifact_details[kind] = detail

        manifest = content["manifest"]
        try:
            manifest_matches = (
                manifest["run_id"] == run_id
                and manifest["validation_id"] == validation["validation_id"]
                and manifest["run_spec"]["run_spec_id"] == row["run_spec_id"]
                and manifest["engine_result"]["artifact_id"]
                == artifacts["engine_result"]["artifact_id"]
                and manifest["engine_result"]["sha256"] == row["calculation_hash"]
                and manifest["strategy_execution"]["intent_tape_artifact_id"]
                == artifacts["intent_tape"]["artifact_id"]
                and manifest["strategy_execution"]["intent_tape_sha256"]
                == artifacts["intent_tape"]["sha256"]
            )
        except (KeyError, TypeError) as error:
            raise ArtifactIntegrityMismatch(
                "formal Run manifest identity is incomplete"
            ) from error
        if not manifest_matches:
            raise ArtifactIntegrityMismatch("formal Run manifest identity is inconsistent")
        return {
            "run": run_detail,
                "run_spec": self._run_spec_read_model(run_spec),
            "validation": validation_detail,
            "artifacts": artifact_details,
            "manifest": content["manifest"],
            "engine_result": content["engine_result"],
            "intent_tape": content["intent_tape"],
            "logs": [dict(log) for log in log_rows],
        }

    def run_report(
        self, project_id: str, run_id: str
    ) -> dict[str, Any] | None:
        detail = self.run(project_id, run_id)
        if detail is None or detail["run"]["status"] != "succeeded":
            return None

        report_kinds = {"report_json", "report_html"}
        existing_kinds = report_kinds & set(detail["artifacts"])
        if existing_kinds:
            if existing_kinds != report_kinds:
                raise ArtifactIntegrityMismatch("formal Run report artifact set is incomplete")
            report_content = self.artifact_content(
                project_id, detail["artifacts"]["report_json"]["artifact_id"]
            )
            if report_content is None:
                raise ArtifactIntegrityMismatch("formal Run report artifact is unavailable")
            _, report_body = report_content
            try:
                report = json.loads(report_body)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise ArtifactIntegrityMismatch(
                    "formal Run report artifact is not valid JSON"
                ) from error
            return self._run_report_read_model(detail["artifacts"], report)

        report = build_run_report(detail)
        report_body = canonical_report_json(report)
        html_body = render_run_report_html(report)
        descriptors = {
            "report_json": self._run_report_artifact_descriptor(
                run_id,
                "report_json",
                report_body,
                "application/vnd.open-quant-studio.run-report+json",
            ),
            "report_html": self._run_report_artifact_descriptor(
                run_id,
                "report_html",
                html_body,
                "application/vnd.open-quant-studio.run-report+html",
            ),
        }
        for artifact in descriptors.values():
            self.store_blob(artifact["sha256"], report_body if artifact["media_type"].endswith("+json") else html_body)

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = {
                row["kind"]: row["artifact_id"]
                for row in connection.execute(
                    "SELECT kind, artifact_id FROM run_artifacts WHERE run_id = ? AND kind IN ('report_json', 'report_html')",
                    (run_id,),
                ).fetchall()
            }
            if current:
                if set(current) != report_kinds:
                    connection.execute("ROLLBACK")
                    raise ArtifactIntegrityMismatch(
                        "formal Run report artifact set is incomplete"
                    )
            else:
                for kind, artifact in descriptors.items():
                    self._register_generated_artifact(
                        connection, artifact, detail["run"]["finished_at"]
                    )
                    connection.execute(
                        "INSERT INTO run_artifacts(run_id, kind, artifact_id) VALUES (?, ?, ?)",
                        (run_id, kind, artifact["artifact_id"]),
                    )
            connection.execute("COMMIT")

        materialized = self.run(project_id, run_id)
        if materialized is None:
            raise ArtifactIntegrityMismatch("formal Run report lost its Run")
        return self._run_report_read_model(materialized["artifacts"], report)

    @staticmethod
    def _run_report_artifact_descriptor(
        run_id: str,
        kind: str,
        body: bytes,
        media_type: str,
    ) -> dict[str, Any]:
        sha256 = hashlib.sha256(body).hexdigest()
        return {
            "artifact_id": str(uuid.uuid5(uuid.UUID(run_id), kind)),
            "sha256": sha256,
            "media_type": media_type,
            "byte_size": len(body),
            "storage_uri": f"cas://sha256/{sha256}",
            "producing_revision_id": None,
            "producing_run_id": run_id,
            "origin_kind": "service_generated",
            "source_ref": f"oqs:m9:run-report:{run_id}:{kind}",
        }

    @staticmethod
    def _run_report_read_model(
        artifacts: dict[str, dict[str, Any]], report: dict[str, Any]
    ) -> dict[str, Any]:
        def pointer(kind: str) -> dict[str, Any]:
            artifact = artifacts[kind]
            return {
                key: artifact[key]
                for key in (
                    "artifact_id",
                    "sha256",
                    "media_type",
                    "byte_size",
                    "storage_uri",
                )
            }

        return {
            "report": report,
            "json_artifact": pointer("report_json"),
            "html_artifact": pointer("report_html"),
        }

    def artifact(
        self, project_id: str, artifact_id: str
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT a.*
                FROM artifacts AS a
                WHERE a.artifact_id = ?
                  AND (
                    EXISTS (
                        SELECT 1
                        FROM revision_files AS f
                        WHERE f.artifact_id = a.artifact_id
                          AND f.project_id = ?
                    ) OR EXISTS (
                        SELECT 1
                        FROM context_items AS c
                        WHERE c.artifact_id = a.artifact_id
                          AND c.project_id = ?
                    ) OR EXISTS (
                        SELECT 1
                        FROM run_specs AS rs
                        WHERE (rs.engine_input_artifact_id = a.artifact_id
                           OR rs.market_input_artifact_id = a.artifact_id)
                          AND rs.project_id = ?
                    ) OR EXISTS (
                        SELECT 1
                        FROM run_artifacts AS ra
                        JOIN formal_runs AS r ON r.run_id = ra.run_id
                        WHERE ra.artifact_id = a.artifact_id
                          AND r.project_id = ?
                    ) OR EXISTS (
                        SELECT 1
                        FROM formal_run_preparations AS p
                        JOIN jobs AS j ON j.job_id = p.job_id
                        WHERE (p.intent_tape_artifact_id = a.artifact_id
                           OR p.resolved_engine_input_artifact_id = a.artifact_id)
                          AND j.project_id = ?
                    ) OR EXISTS (
                        SELECT 1
                        FROM formal_run_checkpoints AS c
                        JOIN jobs AS j ON j.job_id = c.job_id
                        WHERE c.artifact_id = a.artifact_id
                          AND j.project_id = ?
                    ) OR EXISTS (
                        SELECT 1
                        FROM forward_tests AS f
                        WHERE f.transcript_artifact_id = a.artifact_id
                          AND f.project_id = ?
                    ) OR EXISTS (
                        SELECT 1
                        FROM data_snapshots AS d
                        WHERE (
                            d.source_artifact_id = a.artifact_id
                            OR d.normalized_artifact_id = a.artifact_id
                            OR d.market_input_artifact_id = a.artifact_id
                        ) AND d.project_id = ?
                    )
                  )
                """,
                (
                    artifact_id,
                    project_id,
                    project_id,
                    project_id,
                    project_id,
                    project_id,
                    project_id,
                    project_id,
                    project_id,
                ),
            ).fetchone()
            if row is None:
                return None
            revision_paths = connection.execute(
                """
                SELECT revision_id, path
                FROM revision_files
                WHERE project_id = ? AND artifact_id = ?
                ORDER BY revision_id, path
                """,
                (project_id, artifact_id),
            ).fetchall()
            run_kinds = connection.execute(
                """
                SELECT ra.run_id, ra.kind
                FROM run_artifacts AS ra
                JOIN formal_runs AS r ON r.run_id = ra.run_id
                WHERE r.project_id = ? AND ra.artifact_id = ?
                ORDER BY ra.run_id, ra.kind
                """,
                (project_id, artifact_id),
            ).fetchall()
        detail = dict(row)
        detail["project_id"] = project_id
        detail["revision_paths"] = [dict(item) for item in revision_paths]
        detail["run_kinds"] = [dict(item) for item in run_kinds]
        return detail

    def artifact_content(
        self, project_id: str, artifact_id: str
    ) -> tuple[dict[str, Any], bytes] | None:
        artifact = self.artifact(project_id, artifact_id)
        if artifact is None:
            return None
        path = self.blob_path(artifact["sha256"])
        if not path.exists():
            raise ArtifactBlobMissing("artifact blob is not staged")
        body = path.read_bytes()
        if (
            hashlib.sha256(body).hexdigest() != artifact["sha256"]
            or len(body) != artifact["byte_size"]
        ):
            raise ArtifactIntegrityMismatch(
                "artifact bytes do not match registered identity"
            )
        return artifact, body

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
        run_id: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO diagnostic_logs(
                log_id, timestamp, level, priority, component, event_code,
                project_id, activity_id, session_id, task_id, job_id, run_id,
                correlation_id, message
            ) VALUES (?, ?, ?, ?, 'quant-domain', ?, ?, ?, ?, NULL, ?, ?, ?, ?)
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
                run_id,
                correlation_id,
                message,
            ),
        )
