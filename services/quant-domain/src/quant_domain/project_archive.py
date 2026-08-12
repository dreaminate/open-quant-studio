from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from jsonschema import Draft202012Validator, FormatChecker

from .contracts import REGISTRY, SCHEMAS
from .database import Database
from .git_workspace import GitWorkspaceStore


_GIT = Path("/usr/bin/git")
_ARCHIVE_SCHEMA_VERSION = "oqs-project-archive/v1"
_MANIFEST_MEMBER = "manifest.json"
_DATABASE_MEMBER = "data/project.sqlite"
_BUNDLE_MEMBER = "git/project.bundle"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_ARCHIVE_TABLES = (
    "schema_migrations",
    "research_projects",
    "activities",
    "artifacts",
    "context_items",
    "domain_events",
    "outbox",
    "command_receipts",
    "jobs",
    "diagnostic_logs",
    "agent_sessions",
    "workbench_bindings",
    "session_messages",
    "message_receipts",
    "message_receipt_transitions",
    "workspace_revisions",
    "strategy_variants",
    "strategy_variant_heads",
    "project_revision_heads",
    "project_revision_head_history",
    "revision_files",
    "revision_promotions",
    "run_specs",
    "workspace_merge_candidates",
    "formal_runs",
    "run_artifacts",
    "merge_validations",
    "revision_promotion_validations",
    "formal_run_preparations",
    "formal_run_checkpoints",
    "diagnostic_log_retention",
    "diagnostic_log_delete_receipts",
    "forward_tests",
    "data_snapshots",
)
_PROJECT_TABLES = (
    "research_projects",
    "activities",
    "context_items",
    "domain_events",
    "jobs",
    "agent_sessions",
    "workbench_bindings",
    "session_messages",
    "message_receipts",
    "message_receipt_transitions",
    "workspace_revisions",
    "strategy_variants",
    "strategy_variant_heads",
    "project_revision_heads",
    "project_revision_head_history",
    "revision_files",
    "revision_promotions",
    "run_specs",
    "workspace_merge_candidates",
    "formal_runs",
    "merge_validations",
    "diagnostic_log_retention",
    "diagnostic_log_delete_receipts",
    "forward_tests",
    "data_snapshots",
)
_REPORT_MEDIA_TYPES = {
    "application/pdf",
    "application/xhtml+xml",
    "application/vnd.open-quant-studio.run-report+json",
    "application/vnd.open-quant-studio.run-report+html",
    "text/html",
}
_MANIFEST_VALIDATOR = Draft202012Validator(
    SCHEMAS["project-archive-manifest"],
    registry=REGISTRY,
    format_checker=FormatChecker(),
)


class ArchiveDomain(Protocol):
    data_root: Path
    database_path: Path
    database: Database
    git_workspace: GitWorkspaceStore

    def blob_path(self, sha256: str) -> Path: ...

    def store_blob(self, expected_sha256: str, body: bytes) -> dict[str, object]: ...


class ProjectArchiveError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectArchiveExport:
    archive_path: Path
    archive_sha256: str
    byte_size: int
    manifest: dict[str, Any]
    manifest_sha256: str


@dataclass(frozen=True)
class ProjectArchiveImport:
    archive_sha256: str
    manifest_sha256: str
    restored_project_id: str
    run_count: int
    artifact_count: int
    git_ref_count: int


@dataclass(frozen=True)
class _TableRows:
    columns: tuple[str, ...]
    values: tuple[tuple[Any, ...], ...]


def export_project_archive(
    domain: ArchiveDomain,
    *,
    project_id: str,
    archive_path: Path,
    selected_logs: Literal["full", "warn_error", "none"] = "full",
) -> ProjectArchiveExport:
    """Create a deterministic one-project `.oqs.zip` from normal OQS state."""
    if selected_logs not in {"full", "warn_error", "none"}:
        raise ProjectArchiveError("selected_logs must be full, warn_error, or none")
    archive_path = Path(archive_path)
    if archive_path.exists():
        raise ProjectArchiveError("archive output already exists")
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=archive_path.parent) as temporary_directory:
        temporary_root = Path(temporary_directory)
        portable_database = temporary_root / "project.sqlite"
        rows_by_table = _export_portable_database(
            domain.database_path,
            portable_database,
            project_id,
            selected_logs,
        )
        project_row = _single_project_row(rows_by_table, project_id)
        refs = _project_refs(domain.git_workspace.repository_path(project_id), rows_by_table)
        bundle_path = temporary_root / "project.bundle"
        _create_bundle(
            domain.git_workspace.repository_path(project_id),
            bundle_path,
            [ref["name"] for ref in refs],
        )
        bundle_body = bundle_path.read_bytes()
        cas_objects, cas_bodies = _cas_objects(domain, rows_by_table)
        manifest = {
            "schema_version": 1,
            "archive_schema_version": _ARCHIVE_SCHEMA_VERSION,
            "project_id": project_id,
            "activity_ids": _column_values(rows_by_table["activities"], "activity_id"),
            "selected_logs": selected_logs,
            "created_at": project_row["created_at"],
            "git": {
                "bundle_path": _BUNDLE_MEMBER,
                "sha256": hashlib.sha256(bundle_body).hexdigest(),
                "byte_size": len(bundle_body),
                "object_format": "sha1",
                "refs": refs,
            },
            "run_spec_ids": _column_values(rows_by_table["run_specs"], "run_spec_id"),
            "run_ids": _run_ids(rows_by_table),
            "report_artifact_ids": _report_artifact_ids(rows_by_table),
            "cas_objects": cas_objects,
        }
        _validate_manifest(manifest)
        manifest_body = _canonical_json(manifest).encode()
        archive_temporary_path = temporary_root / archive_path.name
        with zipfile.ZipFile(
            archive_temporary_path,
            mode="w",
            compression=zipfile.ZIP_STORED,
            strict_timestamps=True,
        ) as archive:
            _write_zip_entry(archive, _MANIFEST_MEMBER, manifest_body)
            _write_zip_entry(archive, _DATABASE_MEMBER, portable_database.read_bytes())
            _write_zip_entry(archive, _BUNDLE_MEMBER, bundle_body)
            for entry in cas_objects:
                _write_zip_entry(archive, entry["path"], cas_bodies[entry["sha256"]])
        archive_temporary_path.replace(archive_path)

    archive_body = archive_path.read_bytes()
    return ProjectArchiveExport(
        archive_path=archive_path,
        archive_sha256=hashlib.sha256(archive_body).hexdigest(),
        byte_size=len(archive_body),
        manifest=manifest,
        manifest_sha256=hashlib.sha256(manifest_body).hexdigest(),
    )


def import_project_archive(
    domain: ArchiveDomain,
    archive_path: Path,
    *,
    expected_project_id: str | None = None,
) -> ProjectArchiveImport:
    """Restore an archive into an empty root or verify an identical local project."""
    archive_path = Path(archive_path)
    archive_body = archive_path.read_bytes()
    archive_sha256 = hashlib.sha256(archive_body).hexdigest()
    with zipfile.ZipFile(archive_path) as archive:
        manifest_body = archive.read(_MANIFEST_MEMBER)
        manifest = json.loads(manifest_body)
        _validate_manifest(manifest)
        if expected_project_id is not None and manifest["project_id"] != expected_project_id:
            raise ProjectArchiveError("archive project identity did not match the request")
        portable_database_body = archive.read(_DATABASE_MEMBER)
        bundle_body = archive.read(_BUNDLE_MEMBER)
        if hashlib.sha256(bundle_body).hexdigest() != manifest["git"]["sha256"]:
            raise ProjectArchiveError("archive Git bundle hash did not match the manifest")
        if len(bundle_body) != manifest["git"]["byte_size"]:
            raise ProjectArchiveError("archive Git bundle size did not match the manifest")
        cas_bodies = {
            entry["sha256"]: archive.read(entry["path"])
            for entry in manifest["cas_objects"]
        }

    with tempfile.TemporaryDirectory(dir=domain.data_root.parent) as temporary_directory:
        temporary_root = Path(temporary_directory)
        portable_database = temporary_root / "project.sqlite"
        portable_database.write_bytes(portable_database_body)
        bundle_path = temporary_root / "project.bundle"
        bundle_path.write_bytes(bundle_body)
        _validate_portable_database(portable_database, manifest, cas_bodies)
        staged_data_root = temporary_root / "staged-data"
        staged_workspace = GitWorkspaceStore(staged_data_root)
        staged_repository = staged_workspace.repository_path(manifest["project_id"])
        _restore_bundle(staged_repository, bundle_path, manifest["git"]["refs"])
        _validate_git_identities(staged_repository, portable_database, manifest)
        target_repository = domain.git_workspace.repository_path(manifest["project_id"])
        if _target_project_ids(domain):
            _validate_existing_target(domain, target_repository, manifest, cas_bodies)
        else:
            _validate_empty_target(domain)
            for entry in manifest["cas_objects"]:
                domain.store_blob(entry["sha256"], cas_bodies[entry["sha256"]])
            target_repository.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staged_repository, target_repository)
            _restore_database(portable_database, domain.database_path)
            _validate_portable_database(domain.database_path, manifest, cas_bodies)
            _validate_git_identities(target_repository, domain.database_path, manifest)

    return ProjectArchiveImport(
        archive_sha256=archive_sha256,
        manifest_sha256=hashlib.sha256(manifest_body).hexdigest(),
        restored_project_id=manifest["project_id"],
        run_count=len(manifest["run_ids"]),
        artifact_count=len(manifest["cas_objects"]),
        git_ref_count=len(manifest["git"]["refs"]),
    )


def _export_portable_database(
    source_path: Path,
    destination_path: Path,
    project_id: str,
    selected_logs: str,
) -> dict[str, _TableRows]:
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    source.execute("PRAGMA foreign_keys=ON")
    source.execute("BEGIN")
    try:
        rows_by_table = _collect_project_rows(source, project_id, selected_logs)
    finally:
        source.execute("ROLLBACK")
        source.close()

    Database(destination_path)
    destination = sqlite3.connect(destination_path)
    destination.execute("PRAGMA foreign_keys=OFF")
    destination.execute("BEGIN")
    try:
        destination.execute("DELETE FROM schema_migrations")
        for table in _ARCHIVE_TABLES:
            table_rows = rows_by_table[table]
            if not table_rows.values:
                continue
            columns = ", ".join(table_rows.columns)
            placeholders = ", ".join("?" for _ in table_rows.columns)
            destination.executemany(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                table_rows.values,
            )
        destination.execute("COMMIT")
    except sqlite3.Error:
        destination.execute("ROLLBACK")
        destination.close()
        raise
    destination.execute("PRAGMA foreign_keys=ON")
    issues = destination.execute("PRAGMA foreign_key_check").fetchall()
    if issues:
        destination.close()
        raise ProjectArchiveError("portable project database has foreign key errors")
    destination.execute("PRAGMA journal_mode=DELETE")
    destination.execute("VACUUM")
    destination.close()
    return rows_by_table


def _collect_project_rows(
    connection: sqlite3.Connection,
    project_id: str,
    selected_logs: str,
) -> dict[str, _TableRows]:
    rows_by_table: dict[str, _TableRows] = {
        "schema_migrations": _rows(
            connection, "SELECT * FROM schema_migrations ORDER BY migration_id"
        )
    }
    for table in _PROJECT_TABLES:
        rows_by_table[table] = _rows(
            connection,
            f"SELECT * FROM {table} WHERE project_id = ? ORDER BY rowid",
            (project_id,),
        )
    if selected_logs == "full":
        logs_query = "SELECT * FROM diagnostic_logs WHERE project_id = ? ORDER BY log_seq"
        logs_parameters = (project_id,)
    elif selected_logs == "warn_error":
        logs_query = (
            "SELECT * FROM diagnostic_logs WHERE project_id = ? "
            "AND level IN ('warn', 'error') ORDER BY log_seq"
        )
        logs_parameters = (project_id,)
    else:
        logs_query = "SELECT * FROM diagnostic_logs WHERE 0"
        logs_parameters = ()
    rows_by_table["diagnostic_logs"] = _rows(
        connection, logs_query, logs_parameters
    )
    rows_by_table["outbox"] = _rows(
        connection,
        """
        SELECT o.* FROM outbox AS o
        JOIN domain_events AS e ON e.event_id = o.event_id
        WHERE e.project_id = ?
        ORDER BY o.outbox_id
        """,
        (project_id,),
    )
    rows_by_table["command_receipts"] = _rows(
        connection,
        """
        SELECT c.* FROM command_receipts AS c
        JOIN domain_events AS e ON e.event_id = c.event_id
        WHERE e.project_id = ?
        ORDER BY c.rowid
        """,
        (project_id,),
    )
    rows_by_table["run_artifacts"] = _rows(
        connection,
        """
        SELECT a.* FROM run_artifacts AS a
        JOIN formal_runs AS r ON r.run_id = a.run_id
        WHERE r.project_id = ?
        ORDER BY a.rowid
        """,
        (project_id,),
    )
    rows_by_table["revision_promotion_validations"] = _rows(
        connection,
        """
        SELECT v.* FROM revision_promotion_validations AS v
        JOIN revision_promotions AS p ON p.promotion_id = v.promotion_id
        WHERE p.project_id = ?
        ORDER BY v.rowid
        """,
        (project_id,),
    )
    rows_by_table["formal_run_preparations"] = _rows(
        connection,
        """
        SELECT p.* FROM formal_run_preparations AS p
        JOIN jobs AS j ON j.job_id = p.job_id
        WHERE j.project_id = ?
        ORDER BY p.rowid
        """,
        (project_id,),
    )
    rows_by_table["formal_run_checkpoints"] = _rows(
        connection,
        """
        SELECT c.* FROM formal_run_checkpoints AS c
        JOIN jobs AS j ON j.job_id = c.job_id
        WHERE j.project_id = ?
        ORDER BY c.rowid
        """,
        (project_id,),
    )

    artifact_ids = _artifact_ids(rows_by_table)
    revision_ids = set(_column_values(rows_by_table["workspace_revisions"], "revision_id"))
    run_ids = set(_run_ids(rows_by_table))
    artifact_ids.update(
        _artifact_ids_for_producer(connection, "producing_revision_id", revision_ids)
    )
    artifact_ids.update(_artifact_ids_for_producer(connection, "producing_run_id", run_ids))
    rows_by_table["artifacts"] = _rows_for_ids(
        connection, "artifacts", "artifact_id", artifact_ids
    )
    return rows_by_table


def _rows(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[object, ...] = (),
) -> _TableRows:
    cursor = connection.execute(query, parameters)
    columns = tuple(description[0] for description in cursor.description)
    return _TableRows(columns=columns, values=tuple(tuple(row) for row in cursor))


def _rows_for_ids(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    values: set[str],
) -> _TableRows:
    columns = tuple(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))
    rows: list[tuple[Any, ...]] = []
    for batch in _batches(sorted(values), 500):
        placeholders = ", ".join("?" for _ in batch)
        cursor = connection.execute(
            f"SELECT * FROM {table} WHERE {column} IN ({placeholders}) ORDER BY {column}",
            batch,
        )
        rows.extend(tuple(row) for row in cursor)
    index = columns.index(column)
    rows.sort(key=lambda row: str(row[index]))
    return _TableRows(columns=columns, values=tuple(rows))


def _artifact_ids_for_producer(
    connection: sqlite3.Connection,
    column: str,
    values: set[str],
) -> set[str]:
    artifact_ids: set[str] = set()
    for batch in _batches(sorted(values), 500):
        placeholders = ", ".join("?" for _ in batch)
        artifact_ids.update(
            row[0]
            for row in connection.execute(
                f"SELECT artifact_id FROM artifacts WHERE {column} IN ({placeholders})",
                batch,
            )
        )
    return artifact_ids


def _batches(values: list[str], size: int) -> list[tuple[str, ...]]:
    return [tuple(values[index : index + size]) for index in range(0, len(values), size)]


def _artifact_ids(rows_by_table: dict[str, _TableRows]) -> set[str]:
    artifact_ids: set[str] = set()
    for table_rows in rows_by_table.values():
        for index, column in enumerate(table_rows.columns):
            if column == "artifact_id" or column.endswith("_artifact_id"):
                artifact_ids.update(
                    str(row[index]) for row in table_rows.values if row[index] is not None
                )
    return artifact_ids


def _column_values(table_rows: _TableRows, column: str) -> list[str]:
    index = table_rows.columns.index(column)
    return sorted(str(row[index]) for row in table_rows.values)


def _run_ids(rows_by_table: dict[str, _TableRows]) -> list[str]:
    jobs = rows_by_table["jobs"]
    job_type_index = jobs.columns.index("job_type")
    run_id_index = jobs.columns.index("run_id")
    return sorted(
        str(row[run_id_index])
        for row in jobs.values
        if row[job_type_index] == "formal.run" and row[run_id_index] is not None
    )


def _single_project_row(
    rows_by_table: dict[str, _TableRows], project_id: str
) -> dict[str, Any]:
    projects = rows_by_table["research_projects"]
    if len(projects.values) != 1:
        raise ProjectArchiveError("project archive requires exactly one existing project")
    project = dict(zip(projects.columns, projects.values[0], strict=True))
    if project["project_id"] != project_id:
        raise ProjectArchiveError("project archive project identity did not match")
    return project


def _project_refs(
    repository: Path, rows_by_table: dict[str, _TableRows]
) -> list[dict[str, str]]:
    if not repository.is_dir():
        raise ProjectArchiveError("project Git repository is unavailable")
    revision_rows = rows_by_table["workspace_revisions"]
    revision_index = revision_rows.columns.index("revision_id")
    commit_index = revision_rows.columns.index("git_commit_oid")
    expected = {
        f"refs/oqs/revisions/{row[revision_index]}": str(row[commit_index])
        for row in revision_rows.values
    }
    if not expected:
        raise ProjectArchiveError("project archive requires at least one Git revision")
    output = _git(
        repository,
        [
            "for-each-ref",
            "--sort=refname",
            "--format=%(refname) %(objectname)",
            "refs/oqs/revisions/",
        ],
    ).decode()
    actual = {
        line.partition(" ")[0]: line.partition(" ")[2]
        for line in output.splitlines()
        if line
    }
    if actual != expected:
        raise ProjectArchiveError("project Git refs did not match durable revisions")
    return [
        {"name": name, "oid": actual[name]}
        for name in sorted(actual)
    ]


def _create_bundle(repository: Path, bundle_path: Path, refs: list[str]) -> None:
    _git(repository, ["bundle", "create", str(bundle_path), *refs])
    _git(repository, ["bundle", "verify", str(bundle_path)])


def _cas_objects(
    domain: ArchiveDomain,
    rows_by_table: dict[str, _TableRows],
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    artifacts = rows_by_table["artifacts"]
    indexes = {column: artifacts.columns.index(column) for column in artifacts.columns}
    entries: list[dict[str, Any]] = []
    bodies: dict[str, bytes] = {}
    for row in artifacts.values:
        sha256 = str(row[indexes["sha256"]])
        body = domain.blob_path(sha256).read_bytes()
        if hashlib.sha256(body).hexdigest() != sha256:
            raise ProjectArchiveError("artifact blob hash did not match durable metadata")
        if len(body) != row[indexes["byte_size"]]:
            raise ProjectArchiveError("artifact blob size did not match durable metadata")
        if row[indexes["storage_uri"]] != f"cas://sha256/{sha256}":
            raise ProjectArchiveError("artifact storage URI did not match its hash")
        bodies[sha256] = body
        entries.append(
            {
                "sha256": sha256,
                "path": f"cas/sha256/{sha256[:2]}/{sha256}",
                "byte_size": len(body),
            }
        )
    entries.sort(key=lambda entry: entry["path"])
    return entries, bodies


def _report_artifact_ids(rows_by_table: dict[str, _TableRows]) -> list[str]:
    artifacts = rows_by_table["artifacts"]
    indexes = {column: artifacts.columns.index(column) for column in artifacts.columns}
    run_ids = set(_run_ids(rows_by_table))
    return sorted(
        str(row[indexes["artifact_id"]])
        for row in artifacts.values
        if row[indexes["producing_run_id"]] in run_ids
        and (
            row[indexes["media_type"]] in _REPORT_MEDIA_TYPES
            or "report" in str(row[indexes["source_ref"]]).lower()
        )
    )


def _validate_manifest(manifest: dict[str, Any]) -> None:
    errors = sorted(
        _MANIFEST_VALIDATOR.iter_errors(manifest), key=lambda error: list(error.path)
    )
    if errors:
        raise ProjectArchiveError(
            "project archive manifest does not match the contract: "
            + "; ".join(error.message for error in errors)
        )


def _write_zip_entry(archive: zipfile.ZipFile, name: str, body: bytes) -> None:
    entry = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    entry.compress_type = zipfile.ZIP_STORED
    entry.create_system = 3
    entry.external_attr = 0o100644 << 16
    archive.writestr(entry, body)


def _validate_portable_database(
    database_path: Path,
    manifest: dict[str, Any],
    cas_bodies: dict[str, bytes],
) -> None:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        issues = connection.execute("PRAGMA foreign_key_check").fetchall()
        if issues:
            raise ProjectArchiveError("archive project database has foreign key errors")
        project_ids = [
            row[0]
            for row in connection.execute(
                "SELECT project_id FROM research_projects ORDER BY project_id"
            )
        ]
        if project_ids != [manifest["project_id"]]:
            raise ProjectArchiveError("archive project database did not contain one manifest project")
        activity_ids = [
            row[0]
            for row in connection.execute(
                "SELECT activity_id FROM activities WHERE project_id = ? ORDER BY activity_id",
                (manifest["project_id"],),
            )
        ]
        if activity_ids != manifest["activity_ids"]:
            raise ProjectArchiveError("archive activities did not match the manifest")
        run_spec_ids = [
            row[0]
            for row in connection.execute(
                "SELECT run_spec_id FROM run_specs WHERE project_id = ? ORDER BY run_spec_id",
                (manifest["project_id"],),
            )
        ]
        if run_spec_ids != manifest["run_spec_ids"]:
            raise ProjectArchiveError("archive RunSpecs did not match the manifest")
        run_ids = [
            row[0]
            for row in connection.execute(
                """
                SELECT run_id FROM jobs
                WHERE project_id = ? AND job_type = 'formal.run'
                ORDER BY run_id
                """,
                (manifest["project_id"],),
            )
        ]
        if run_ids != manifest["run_ids"]:
            raise ProjectArchiveError("archive Runs did not match the manifest")
        artifact_rows = connection.execute(
            "SELECT artifact_id, sha256, byte_size FROM artifacts ORDER BY sha256"
        ).fetchall()
        expected_hashes = [entry["sha256"] for entry in manifest["cas_objects"]]
        if [row["sha256"] for row in artifact_rows] != expected_hashes:
            raise ProjectArchiveError("archive artifacts did not match the manifest")
        artifact_ids = {row["artifact_id"] for row in artifact_rows}
        if not set(manifest["report_artifact_ids"]).issubset(artifact_ids):
            raise ProjectArchiveError("archive report artifacts were unavailable")
        for row in artifact_rows:
            body = cas_bodies.get(row["sha256"])
            if body is None:
                raise ProjectArchiveError("archive artifact body was unavailable")
            if hashlib.sha256(body).hexdigest() != row["sha256"]:
                raise ProjectArchiveError("archive artifact hash did not match metadata")
            if len(body) != row["byte_size"]:
                raise ProjectArchiveError("archive artifact size did not match metadata")
        log_rows = connection.execute(
            "SELECT level FROM diagnostic_logs WHERE project_id = ?",
            (manifest["project_id"],),
        ).fetchall()
        if manifest["selected_logs"] == "none" and log_rows:
            raise ProjectArchiveError("archive unexpectedly contained diagnostic logs")
        if manifest["selected_logs"] == "warn_error" and any(
            row["level"] not in {"warn", "error"} for row in log_rows
        ):
            raise ProjectArchiveError("archive log selection did not match the manifest")
    finally:
        connection.close()


def _restore_bundle(
    repository: Path,
    bundle_path: Path,
    refs: list[dict[str, str]],
) -> None:
    repository.parent.mkdir(parents=True, exist_ok=True)
    _git_init(repository)
    _git(repository, ["bundle", "unbundle", str(bundle_path)])
    for ref in refs:
        _git(repository, ["update-ref", ref["name"], ref["oid"]])


def _validate_git_identities(
    repository: Path,
    database_path: Path,
    manifest: dict[str, Any],
) -> None:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        revisions = {
            row["revision_id"]: row
            for row in connection.execute(
                "SELECT revision_id, git_commit_oid, git_tree_oid FROM workspace_revisions"
            )
        }
    finally:
        connection.close()
    for ref in manifest["git"]["refs"]:
        revision_id = ref["name"].rsplit("/", 1)[1]
        revision = revisions.get(revision_id)
        if revision is None:
            raise ProjectArchiveError("archive Git ref did not have a WorkspaceRevision")
        commit = _git(repository, ["rev-parse", ref["name"]]).decode().strip()
        tree = _git(repository, ["rev-parse", f"{ref['name']}^{{tree}}"]).decode().strip()
        if commit != ref["oid"] or commit != revision["git_commit_oid"]:
            raise ProjectArchiveError("archive Git commit identity did not match the Run graph")
        if tree != revision["git_tree_oid"]:
            raise ProjectArchiveError("archive Git tree identity did not match the Run graph")


def _validate_empty_target(domain: ArchiveDomain) -> None:
    project_count = len(_target_project_ids(domain))
    with domain.database.connect() as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    if project_count != 0:
        raise ProjectArchiveError("project archive import requires an empty data root")
    if domain.git_workspace.repository_path("00000000-0000-4000-8000-000000000000").parent.exists():
        git_root = domain.git_workspace.repository_path(
            "00000000-0000-4000-8000-000000000000"
        ).parent
        if any(git_root.iterdir()):
            raise ProjectArchiveError("project archive import requires an empty Git root")


def _target_project_ids(domain: ArchiveDomain) -> list[str]:
    with domain.database.connect() as connection:
        return [
            str(row[0])
            for row in connection.execute(
                "SELECT project_id FROM research_projects ORDER BY project_id"
            )
        ]


def _validate_existing_target(
    domain: ArchiveDomain,
    target_repository: Path,
    manifest: dict[str, Any],
    cas_bodies: dict[str, bytes],
) -> None:
    if _target_project_ids(domain) != [manifest["project_id"]]:
        raise ProjectArchiveError(
            "project archive import requires an empty or identical project data root"
        )
    _validate_portable_database(domain.database_path, manifest, cas_bodies)
    _validate_git_identities(target_repository, domain.database_path, manifest)
    for entry in manifest["cas_objects"]:
        body = domain.blob_path(entry["sha256"]).read_bytes()
        if body != cas_bodies[entry["sha256"]]:
            raise ProjectArchiveError("existing project artifact did not match the archive")


def _restore_database(source_path: Path, destination_path: Path) -> None:
    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def _git_init(repository: Path) -> None:
    completed = subprocess.run(
        [str(_GIT), "init", "--bare", "--object-format=sha1", str(repository)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise ProjectArchiveError("Git repository initialization failed")


def _git(repository: Path, arguments: list[str]) -> bytes:
    environment = os.environ.copy()
    environment["GIT_DIR"] = str(repository)
    environment.pop("GIT_WORK_TREE", None)
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    completed = subprocess.run(
        [str(_GIT), *arguments],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise ProjectArchiveError("Git archive command failed")
    return completed.stdout


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
