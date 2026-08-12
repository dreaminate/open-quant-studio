from __future__ import annotations

import copy
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from quant_domain.domain import QuantDomain
from test_m2_session import (
    ACTIVITY_ID,
    CORRELATION_ID,
    PROJECT_ID,
    SENDER_SESSION_ID,
    bind_command,
    register_command,
)


class M5DiagnosticLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tempdir.name)
        self.domain = QuantDomain(self.data_root)
        self.domain.submit_command(register_command())
        self.domain.submit_command(
            bind_command(
                command_id="51515151-5151-4151-8151-515151515151",
                workbench_id="logs",
            )
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _insert_log(
        self,
        *,
        timestamp: str,
        level: str,
        priority: str,
        message: str,
        event_code: str,
    ) -> str:
        with self.domain.database.connect() as connection:
            self.domain._insert_log(
                connection,
                timestamp=timestamp,
                level=level,
                priority=priority,
                event_code=event_code,
                project_id=PROJECT_ID,
                activity_id=ACTIVITY_ID,
                session_id=SENDER_SESSION_ID,
                job_id=None,
                correlation_id=CORRELATION_ID,
                message=message,
            )
            row = connection.execute(
                "SELECT log_id FROM diagnostic_logs WHERE event_code = ?",
                (event_code,),
            ).fetchone()
        return row["log_id"]

    @staticmethod
    def _delete_command(log_id: str) -> dict[str, object]:
        return {
            "command_id": "52525252-5252-4252-8252-525252525252",
            "schema_version": 1,
            "command_type": "diagnostic.log_delete",
            "project_id": PROJECT_ID,
            "activity_id": ACTIVITY_ID,
            "session_id": SENDER_SESSION_ID,
            "workbench_id": "logs",
            "correlation_id": CORRELATION_ID,
            "expected_revision_id": None,
            "variant_id": None,
            "base_revision_id": None,
            "payload": {"selection": {"log_ids": [log_id]}},
        }

    @staticmethod
    def _retention_command(quota_bytes: int = 2_147_483_648) -> dict[str, object]:
        return {
            "command_id": "53535353-5353-4353-8353-535353535353",
            "schema_version": 1,
            "command_type": "diagnostic.log_retention_configure",
            "project_id": PROJECT_ID,
            "activity_id": ACTIVITY_ID,
            "session_id": SENDER_SESSION_ID,
            "workbench_id": "logs",
            "correlation_id": CORRELATION_ID,
            "expected_revision_id": None,
            "variant_id": None,
            "base_revision_id": None,
            "payload": {
                "debug_days": 7,
                "info_days": 30,
                "warn_days": 90,
                "quota_bytes": quota_bytes,
            },
        }

    def test_delete_removes_the_log_body_and_full_text_match_idempotently(self) -> None:
        log_id = self._insert_log(
            timestamp="2026-08-12T00:00:00Z",
            level="info",
            priority="p3",
            message="uniquedeletionwitness",
            event_code="m5.delete.witness",
        )
        command = self._delete_command(log_id)

        accepted = self.domain.submit_command(command)
        replayed = self.domain.submit_command(copy.deepcopy(command))

        self.assertEqual(accepted["event"]["payload"]["deleted_count"], 1)
        self.assertEqual(replayed["disposition"], "replayed")
        with self.domain.database.connect() as connection:
            row = connection.execute(
                "SELECT message FROM diagnostic_logs WHERE log_id = ?", (log_id,)
            ).fetchone()
            fts = connection.execute(
                "SELECT rowid FROM diagnostic_logs_fts WHERE diagnostic_logs_fts MATCH ?",
                ("uniquedeletionwitness",),
            ).fetchall()
        self.assertIsNone(row)
        self.assertEqual(fts, [])

    def test_retention_expires_debug_info_warn_but_never_error_or_p1(self) -> None:
        for level, priority in (
            ("debug", "p4"),
            ("info", "p3"),
            ("warn", "p2"),
            ("error", "p2"),
            ("debug", "p1"),
        ):
            self._insert_log(
                timestamp="2000-01-01T00:00:00Z",
                level=level,
                priority=priority,
                message=f"retention-{level}-{priority}",
                event_code=f"m5.retention.{level}.{priority}",
            )

        receipt = self.domain.submit_command(self._retention_command())
        remaining = self.domain.logs(project_id=PROJECT_ID)

        self.assertEqual(receipt["event"]["payload"]["deleted_count"], 3)
        retained_codes = {log["event_code"] for log in remaining}
        self.assertIn("m5.retention.error.p2", retained_codes)
        self.assertIn("m5.retention.debug.p1", retained_codes)
        self.assertNotIn("m5.retention.debug.p4", retained_codes)
        self.assertNotIn("m5.retention.info.p3", retained_codes)
        self.assertNotIn("m5.retention.warn.p2", retained_codes)

    def test_quota_evicts_debug_before_older_info_and_warn_by_utf8_bytes(self) -> None:
        payload = "量" * 160_000
        self._insert_log(
            timestamp="2026-08-09T00:00:00Z",
            level="warn",
            priority="p2",
            message=payload,
            event_code="m5.quota.warn",
        )
        self._insert_log(
            timestamp="2026-08-10T00:00:00Z",
            level="info",
            priority="p3",
            message=payload,
            event_code="m5.quota.info",
        )
        self._insert_log(
            timestamp="2026-08-11T00:00:00Z",
            level="debug",
            priority="p4",
            message=payload,
            event_code="m5.quota.debug",
        )

        self.domain.submit_command(self._retention_command(quota_bytes=1_048_576))
        remaining = self.domain.logs(project_id=PROJECT_ID)
        retained_codes = {log["event_code"] for log in remaining}

        self.assertNotIn("m5.quota.debug", retained_codes)
        self.assertIn("m5.quota.info", retained_codes)
        self.assertIn("m5.quota.warn", retained_codes)

    def test_reopen_applies_documented_default_retention_without_policy_row(self) -> None:
        self._insert_log(
            timestamp="2000-01-01T00:00:00Z",
            level="debug",
            priority="p4",
            message="default-retention-witness",
            event_code="m5.default.retention",
        )

        reopened = QuantDomain(self.data_root)

        self.assertNotIn(
            "m5.default.retention",
            {log["event_code"] for log in reopened.logs(project_id=PROJECT_ID)},
        )


if __name__ == "__main__":
    unittest.main()
