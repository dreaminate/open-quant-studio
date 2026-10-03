from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class DatabaseConfigurationError(RuntimeError):
    pass


class Database:
    def __init__(self, database_path: Path, *, migrations_dir: Path | None = None) -> None:
        self.path = database_path
        self.migrations_dir = migrations_dir or Path(__file__).with_name("migrations")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, autocommit=True, timeout=5.0)
        connection.row_factory = sqlite3.Row
        journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if journal_mode != "wal":
            connection.close()
            raise DatabaseConfigurationError("SQLite WAL mode is required")
        connection.execute("PRAGMA foreign_keys=ON")
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        if foreign_keys != 1:
            connection.close()
            raise DatabaseConfigurationError("SQLite foreign keys are required")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA synchronous=FULL")
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_id TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                ) STRICT
                """
            )
            for migration_path in sorted(self.migrations_dir.glob("*.sql")):
                migration_id = migration_path.stem
                # 011 and 012 rebuild immutable tables whose CHECK constraints
                # are part of the v3 contract.  SQLite cannot toggle
                # `foreign_keys` while a transaction is active, and renaming
                # a referenced table otherwise leaves child FKs pointing at
                # the temporary name.  The migration script performs a
                # validated sqlite_master reference repair after copying the
                # rows; run that bounded rebuild with FK enforcement paused,
                # then verify and restore the invariant before returning.
                rebuild_with_foreign_keys_off = migration_id.startswith(("011_", "012_"))
                connection.execute("BEGIN IMMEDIATE")
                already_applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE migration_id = ?",
                    (migration_id,),
                ).fetchone()
                if already_applied is not None:
                    connection.execute("COMMIT")
                    continue
                if rebuild_with_foreign_keys_off:
                    connection.execute("ROLLBACK")
                    connection.execute("PRAGMA foreign_keys=OFF")
                    connection.execute("BEGIN IMMEDIATE")
                try:
                    for statement in migration_statements(migration_path.read_text()):
                        connection.execute(statement)
                    connection.execute(
                        """
                        INSERT INTO schema_migrations(migration_id, applied_at)
                        VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                        """,
                        (migration_id,),
                    )
                except sqlite3.Error:
                    connection.execute("ROLLBACK")
                    if rebuild_with_foreign_keys_off:
                        connection.execute("PRAGMA foreign_keys=ON")
                    raise
                connection.execute("COMMIT")
                if rebuild_with_foreign_keys_off:
                    connection.execute("PRAGMA foreign_keys=ON")
                    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                        raise DatabaseConfigurationError(
                            "SQLite foreign keys could not be restored after v3 migration"
                        )
                    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                        raise DatabaseConfigurationError(
                            "v3 migration left an invalid SQLite foreign-key reference"
                        )


def migration_statements(script: str) -> Iterator[str]:
    pending = ""
    for line in script.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending.strip()
            pending = ""
    if pending.strip():
        raise ValueError("incomplete SQL migration statement")
