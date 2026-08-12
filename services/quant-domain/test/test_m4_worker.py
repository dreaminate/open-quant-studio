from __future__ import annotations

import copy
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Event

import test_m3_formal_runs as formal_run_scenario
from quant_domain.domain import QuantDomain
from test_m2_session import PROJECT_ID, register_command
from test_m3_revisions import create_revision_command, create_variant_command


class M4WorkerProcessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tempdir.name)
        self.domain = QuantDomain(self.data_root)
        self.domain.submit_command(register_command())
        scenario = formal_run_scenario.M3FormalRunDomainTest(
            "test_formal_run_persists_a_hash_bound_manifest_without_recalculation"
        )
        scenario.data_root = self.data_root
        scenario.domain = self.domain
        scenario._create_variant_revision()
        self.slow_strategy = scenario._strategy_source().replace(
            b"def on_start():\n",
            b"def on_start():\n    import time\n    time.sleep(2.0)\n",
        )
        self.domain.submit_command(scenario._merge_command(self.slow_strategy))
        self.domain.submit_command(scenario._formal_run_command())
        self.scenario = scenario

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def queue_second_formal_run(
        self,
        *,
        domain: QuantDomain | None = None,
        scenario: formal_run_scenario.M3FormalRunDomainTest | None = None,
        slow_strategy: bytes | None = None,
    ) -> None:
        target = self.domain if domain is None else domain
        fixture = self.scenario if scenario is None else scenario
        source = self.slow_strategy if slow_strategy is None else slow_strategy
        target.submit_command(
            create_variant_command(
                command_id="97979797-9797-4797-8797-979797979797",
                variant_id=formal_run_scenario.RACING_VARIANT_ID,
                base_revision_id=formal_run_scenario.ROOT_REVISION_ID,
            )
        )
        racing_child = b"def on_bar(bar):\n    return []  # racing variant\n"
        fixture._stage(racing_child)
        target.submit_command(
            create_revision_command(
                command_id="96969696-9696-4696-8696-969696969696",
                revision_id=formal_run_scenario.RACING_VARIANT_REVISION_ID,
                files=[
                    (
                        "strategy.py",
                        racing_child,
                        "acacacac-acac-4cac-8cac-acacacacacac",
                    )
                ],
                variant_id=formal_run_scenario.RACING_VARIANT_ID,
                base_revision_id=formal_run_scenario.ROOT_REVISION_ID,
            )
        )
        racing_merge = copy.deepcopy(
            fixture._merge_command(source)
        )
        racing_merge["command_id"] = "98989898-9898-4898-8898-989898989898"
        racing_merge["variant_id"] = formal_run_scenario.RACING_VARIANT_ID
        racing_merge["base_revision_id"] = (
            formal_run_scenario.RACING_VARIANT_REVISION_ID
        )
        racing_merge["payload"]["candidate_revision_id"] = (
            formal_run_scenario.RACING_MERGE_REVISION_ID
        )
        target.submit_command(racing_merge)

        racing_formal = copy.deepcopy(fixture._formal_run_command())
        racing_candidate = target.revision(
            PROJECT_ID, formal_run_scenario.RACING_MERGE_REVISION_ID
        )
        racing_formal["command_id"] = "99999999-9999-4999-8999-999999999999"
        racing_formal["expected_revision_id"] = (
            formal_run_scenario.RACING_MERGE_REVISION_ID
        )
        racing_formal["variant_id"] = formal_run_scenario.RACING_VARIANT_ID
        racing_formal["base_revision_id"] = (
            formal_run_scenario.RACING_MERGE_REVISION_ID
        )
        racing_formal["payload"]["run_spec_id"] = (
            formal_run_scenario.RACING_RUN_SPEC_ID
        )
        racing_formal["payload"]["run_id"] = formal_run_scenario.RACING_RUN_ID
        racing_formal["payload"]["validation_id"] = (
            formal_run_scenario.RACING_VALIDATION_ID
        )
        racing_formal["payload"]["candidate_revision_id"] = (
            formal_run_scenario.RACING_MERGE_REVISION_ID
        )
        racing_formal["payload"]["strategy_tree_oid"] = racing_candidate[
            "git_tree_oid"
        ]
        target.submit_command(racing_formal)

    def test_worker_process_claims_formal_job_and_stops_cleanly(self) -> None:
        environment = os.environ.copy()
        environment["OQS_DATA_ROOT"] = str(self.data_root)
        worker = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "quant_domain.worker",
                "--data-root",
                str(self.data_root),
                "--poll-interval",
                "0.01",
            ],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 10
        detail = None
        worker_error = None
        while time.monotonic() < deadline:
            if worker.poll() is not None:
                stdout, stderr = worker.communicate()
                worker_error = (
                    "worker exited before completing the Formal Run\n"
                    f"stdout:\n{stdout}\nstderr:\n{stderr}"
                )
                break
            detail = self.domain.run(PROJECT_ID, formal_run_scenario.RUN_ID)
            if detail is not None and detail["run"]["status"] in {
                "succeeded",
                "failed",
                "cancelled",
            }:
                break
            time.sleep(0.02)

        if worker.poll() is None:
            worker.terminate()
        stdout, stderr = worker.communicate(timeout=5)
        self.assertIsNone(worker_error, worker_error)
        self.assertIsNotNone(detail, "worker did not complete the Formal Run")
        self.assertEqual(detail["run"]["status"], "succeeded")
        self.assertEqual(worker.returncode, 0, f"stdout:\n{stdout}\nstderr:\n{stderr}")

    def test_two_workers_never_claim_two_formal_runs_concurrently(self) -> None:
        self.queue_second_formal_run()
        release = Event()

        def run_one(domain: QuantDomain) -> dict[str, object] | None:
            release.wait()
            return domain.run_next_job()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(run_one, QuantDomain(self.data_root)),
                executor.submit(run_one, QuantDomain(self.data_root)),
            ]
            release.set()
            time.sleep(0.4)
            with closing(sqlite3.connect(self.domain.database_path)) as connection:
                running = connection.execute(
                    """
                    SELECT count(*)
                    FROM jobs
                    WHERE job_type = 'formal.run' AND status = 'running'
                    """
                ).fetchone()[0]
            results = [future.result(timeout=10) for future in futures]

        self.assertLessEqual(running, 1)
        self.assertEqual(
            sum(result is not None and result["status"] == "succeeded" for result in results),
            1,
        )
        remaining = self.domain.run_next_job()
        self.assertEqual(remaining["status"], "succeeded")
        self.assertEqual(
            {run["run_id"] for run in self.domain.runs(PROJECT_ID)},
            {formal_run_scenario.RUN_ID, formal_run_scenario.RACING_RUN_ID},
        )

if __name__ == "__main__":
    unittest.main()
