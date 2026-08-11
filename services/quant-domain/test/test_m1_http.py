from __future__ import annotations

import copy
import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode

from test_m1_domain import PROJECT_ID, context_capture_command


def free_loopback_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def parse_sse(body: str) -> list[dict[str, object]]:
    events = []
    for frame in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in frame.splitlines())
        events.append(
            {
                "id": int(fields["id"]),
                "event": fields["event"],
                "data": json.loads(fields["data"]),
            }
        )
    return events


class M1HttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tempdir.name)
        self.port = free_loopback_port()
        repo_root = Path(__file__).resolve().parents[3]
        environment = os.environ.copy()
        environment["OQS_DATA_ROOT"] = str(self.data_root)
        environment["PYTHONPATH"] = str(repo_root / "services/quant-domain/src")
        self.server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "quant_domain.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--log-level",
                "warning",
            ],
            cwd=repo_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.server.poll() is not None:
                stdout, stderr = self.server.communicate()
                self.fail(f"server exited early\nstdout:\n{stdout}\nstderr:\n{stderr}")
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", self.port, timeout=0.2
                )
                connection.request("GET", "/health")
                response = connection.getresponse()
                response.read()
                connection.close()
                if response.status == 200:
                    return
            except OSError:
                time.sleep(0.05)
        self.fail("server did not become ready within 5 seconds")

    def tearDown(self) -> None:
        self.server.terminate()
        self.server.wait(timeout=5)
        self.server.stdout.close()
        self.server.stderr.close()
        self.tempdir.cleanup()

    def request(
        self,
        method: str,
        target: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(method, target, body=body, headers=headers or {})
        response = connection.getresponse()
        response_body = response.read()
        response_headers = {name.lower(): value for name, value in response.getheaders()}
        status = response.status
        connection.close()
        return status, response_headers, response_body

    def test_real_http_command_job_logs_and_resumable_sse_vertical_slice(self) -> None:
        blob = b"HTTP M1 raw evidence\n"
        digest = hashlib.sha256(blob).hexdigest()
        status, _, response_body = self.request(
            "PUT", f"/v1/artifact-blobs/{digest}", body=blob
        )
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(response_body)["sha256"], digest)

        secret = "Bearer REVIEW-SECRET"
        rejected = context_capture_command(blob=blob, source_ref=secret)
        status, _, response_body = self.request(
            "POST",
            "/v1/commands",
            body=json.dumps(rejected).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 422)
        self.assertNotIn("REVIEW-SECRET", response_body.decode())

        command = context_capture_command(blob=blob)
        encoded_command = json.dumps(command).encode()
        status, _, response_body = self.request(
            "POST",
            "/v1/commands",
            body=encoded_command,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 201)
        accepted = json.loads(response_body)
        self.assertEqual(accepted["disposition"], "accepted")
        self.assertNotIn("REVIEW-SECRET", json.dumps(accepted))

        status, _, response_body = self.request(
            "POST",
            "/v1/commands",
            body=encoded_command,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        replayed = json.loads(response_body)
        self.assertEqual(replayed["disposition"], "replayed")
        self.assertEqual(replayed["event"], accepted["event"])
        self.assertNotIn("REVIEW-SECRET", json.dumps(replayed))

        changed = copy.deepcopy(command)
        changed["payload"]["title"] = "Divergent duplicate"
        status, _, response_body = self.request(
            "POST",
            "/v1/commands",
            body=json.dumps(changed).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(response_body)["error"], "command_id_conflict")

        target = f"/v1/events?{urlencode({'project_id': PROJECT_ID})}"
        status, headers, response_body = self.request("GET", target)
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/event-stream; charset=utf-8")
        initial = parse_sse(response_body.decode())
        self.assertEqual([event["id"] for event in initial], [1])
        self.assertEqual(initial[0]["id"], initial[0]["data"]["stream_seq"])
        self.assertNotIn("REVIEW-SECRET", json.dumps(initial))

        status, _, response_body = self.request("POST", "/v1/jobs/run-next")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(response_body)["status"], "succeeded")

        status, _, response_body = self.request(
            "GET", target, headers={"Last-Event-ID": "1"}
        )
        self.assertEqual(status, 200)
        resumed = parse_sse(response_body.decode())
        self.assertEqual([event["id"] for event in resumed], [2, 3])
        self.assertEqual(resumed[0]["event"], "domain.event")
        self.assertEqual(
            [event["data"]["event_type"] for event in resumed],
            ["artifact.verification_started", "artifact.verification_succeeded"],
        )
        self.assertNotIn("REVIEW-SECRET", json.dumps(resumed))

        status, _, response_body = self.request(
            "GET", target, headers={"Last-Event-ID": "0"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            [event["id"] for event in parse_sse(response_body.decode())], [1, 2, 3]
        )

        status, _, response_body = self.request(
            "GET", target, headers={"Last-Event-ID": "not-a-cursor"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(response_body)["error"], "invalid_last_event_id")

        logs_target = "/v1/logs?" + urlencode(
            {"project_id": PROJECT_ID, "level": "info", "priority": "p3"}
        )
        status, _, response_body = self.request("GET", logs_target)
        self.assertEqual(status, 200)
        logs = json.loads(response_body)["logs"]
        self.assertEqual(len(logs), 2)
        self.assertNotIn("REVIEW-SECRET", json.dumps(logs))
        for path in self.data_root.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"REVIEW-SECRET", path.read_bytes())


if __name__ == "__main__":
    unittest.main()
