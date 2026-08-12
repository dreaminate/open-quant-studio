from __future__ import annotations

import copy
import json
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

from test_m2_session import PROJECT_ID
import test_m3_formal_runs as _m3


class M5FormalRunLifecycleTest(unittest.TestCase):
    """Durable M5 lifecycle checks; strategy execution is mocked at its fixed boundary."""

    def setUp(self) -> None:
        self.fixture = _m3.M3FormalRunDomainTest("test_merge_candidate_is_two_parent_immutable_and_moves_no_head")
        self.fixture.setUp()
        self.domain = self.fixture.domain

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def _merge_command(self, *args: object, **kwargs: object) -> dict[str, object]:
        return self.fixture._merge_command(*args, **kwargs)

    def _formal_run_command(self) -> dict[str, object]:
        return self.fixture._formal_run_command()

    def _m5_command(self) -> dict[str, object]:
        command = self._formal_run_command()
        payload = command["payload"]
        payload["checkpoint_batch_size"] = 1
        return command

    def test_pending_and_success_are_durable_and_manifest_is_m5(self) -> None:
        self.domain.submit_command(self._merge_command())
        command = self._m5_command()
        self.domain.submit_command(command)
        run_id = command["payload"]["run_id"]
        pending = self.domain.run(PROJECT_ID, run_id)
        self.assertEqual(pending["run"]["status"], "pending")
        self.assertEqual(pending["run"]["checkpoint_seq"], 0)

        with patch("quant_domain.domain.run_strategy_host", return_value=[]):
            completed = self.domain.run_next_job()
        self.assertEqual(completed["status"], "succeeded")
        detail = self.domain.run(PROJECT_ID, run_id)
        self.assertEqual(detail["manifest"]["manifest_version"], "m5-v1")
        self.assertEqual(completed["checkpoint_seq"], 4)
        self.assertEqual(detail["run_spec"]["gate_policy_version"], "m5-v1")

    def test_real_streamed_strategy_and_pyo3_complete_on_the_current_platform(self) -> None:
        self.domain.submit_command(self._merge_command())
        command = self._m5_command()
        self.domain.submit_command(command)

        completed = self.domain.run_next_job()

        self.assertEqual(completed["status"], "succeeded")
        detail = self.domain.run(PROJECT_ID, command["payload"]["run_id"])
        self.assertEqual(detail["run"]["status"], "succeeded")
        self.assertEqual(detail["manifest"]["manifest_version"], "m5-v1")

    def test_cancelled_run_is_visible_without_result_artifacts(self) -> None:
        self.domain.submit_command(self._merge_command())
        command = self._m5_command()
        self.domain.submit_command(command)
        cancel = copy.deepcopy(command)
        cancel["command_id"] = "31313131-3131-4131-8131-313131313131"
        cancel["command_type"] = "formal.run_cancel"
        cancel["payload"] = {
            "run_id": command["payload"]["run_id"],
            "expected_status": "pending",
            "expected_execution_version": 0,
            "reason": "user_requested",
        }
        self.domain.submit_command(cancel)
        detail = self.domain.run(PROJECT_ID, command["payload"]["run_id"])
        self.assertEqual(detail["run"]["status"], "cancelled")
        self.assertEqual(detail["artifacts"], {})
        self.assertIsNone(detail["manifest"])

    def test_retry_reserves_a_new_run_and_reuses_the_immutable_spec(self) -> None:
        self.domain.submit_command(self._merge_command(b"raise RuntimeError('blocked')\n"))
        source = self._m5_command()
        self.domain.submit_command(source)
        with patch("quant_domain.domain.run_strategy_host", return_value=None):
            self.assertEqual(self.domain.run_next_job()["status"], "failed")

        retry = {
            **source,
            "command_id": "32323232-3232-4232-8232-323232323232",
            "command_type": "formal.run_retry",
            "payload": {
                "source_run_id": source["payload"]["run_id"],
                "source_execution_version": 1,
                "run_id": "33333333-3333-4333-8333-333333333339",
                "validation_id": "34343434-3434-4434-8434-343434343434",
            },
        }
        self.domain.submit_command(retry)
        with patch("quant_domain.domain.run_strategy_host", return_value=[]):
            self.assertEqual(self.domain.run_next_job()["status"], "succeeded")
        rows = self.domain.runs(PROJECT_ID)
        self.assertEqual({row["run_spec_id"] for row in rows}, {source["payload"]["run_spec_id"]})
        self.assertEqual({row["status"] for row in rows}, {"failed", "succeeded"})

    def test_same_legal_input_can_run_twice_with_distinct_immutable_runs(self) -> None:
        self.domain.submit_command(self._merge_command())
        first = self._m5_command()
        self.domain.submit_command(first)
        with patch("quant_domain.domain.run_strategy_host", return_value=[]):
            self.assertEqual(self.domain.run_next_job()["status"], "succeeded")

        second = copy.deepcopy(first)
        second["command_id"] = "35353535-3535-4535-8535-353535353535"
        second["payload"]["run_id"] = "36363636-3636-4636-8636-363636363636"
        second["payload"]["validation_id"] = (
            "37373737-3737-4737-8737-373737373737"
        )
        self.domain.submit_command(second)
        with patch("quant_domain.domain.run_strategy_host", return_value=[]):
            self.assertEqual(self.domain.run_next_job()["status"], "succeeded")

        first_detail = self.domain.run(PROJECT_ID, first["payload"]["run_id"])
        second_detail = self.domain.run(PROJECT_ID, second["payload"]["run_id"])
        self.assertEqual(first_detail["run"]["status"], "succeeded")
        self.assertEqual(second_detail["run"]["status"], "succeeded")
        self.assertEqual(
            first_detail["run"]["calculation_hash"],
            second_detail["run"]["calculation_hash"],
        )
        self.assertNotEqual(
            first_detail["artifacts"]["manifest"]["artifact_id"],
            second_detail["artifacts"]["manifest"]["artifact_id"],
        )

    def test_reopen_resumes_from_the_last_persisted_checkpoint(self) -> None:
        self.domain.submit_command(self._merge_command())
        command = self._m5_command()
        self.domain.submit_command(command)
        import oqs_quant_engine

        original_step = oqs_quant_engine.step_engine_checkpoint_v1
        calls = 0

        def stop_after_first(input_body: bytes, context: str, checkpoint: bytes) -> bytes:
            nonlocal calls
            calls += 1
            result = original_step(input_body, context, checkpoint)
            if calls == 2:
                raise RuntimeError("simulated worker interruption")
            return result

        with patch("quant_domain.domain.run_strategy_host", return_value=[]), patch.object(
            oqs_quant_engine, "step_engine_checkpoint_v1", side_effect=stop_after_first
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated worker interruption"):
                self.domain.run_next_job()
        interrupted = self.domain.job(
            str(__import__("uuid").uuid5(__import__("uuid").UUID(command["command_id"]), "formal.run"))
        )
        self.assertEqual(interrupted["status"], "running")
        self.assertEqual(interrupted["checkpoint_seq"], 1)
        with closing(
            sqlite3.connect(self.domain.database_path, autocommit=True)
        ) as connection:
            connection.execute(
                "UPDATE jobs SET lease_expires_at = '1970-01-01T00:00:00.000Z' WHERE job_id = ?",
                (interrupted["job_id"],),
            )
        with patch("quant_domain.domain.run_strategy_host", return_value=[]):
            resumed = self.domain.run_next_job()
        self.assertEqual(resumed["status"], "succeeded")
        self.assertGreater(resumed["checkpoint_seq"], 1)

if __name__ == "__main__":
    unittest.main()
