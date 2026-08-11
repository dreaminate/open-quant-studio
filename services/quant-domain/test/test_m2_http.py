from __future__ import annotations

import hashlib
import json
import threading
import time
from urllib.parse import urlencode

from test_m1_http import HttpTestCase
from test_m2_session import (
    PROJECT_ID,
    RECEIVER_SESSION_ID,
    SENDER_SESSION_ID,
    bind_command,
    register_command,
    send_command,
)


class M2HttpTest(HttpTestCase):
    def register_sessions(self) -> None:
        for command in (
            register_command(),
            register_command(
                command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa03",
                session_id=RECEIVER_SESSION_ID,
                pi_session_id="pi-session-b",
            ),
        ):
            status, _, body = self.request(
                "POST",
                "/v1/commands",
                body=json.dumps(command).encode(),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 201, body)

    def test_sessions_inbox_and_identity_checked_message_body(self) -> None:
        self.register_sessions()
        blob = b"HTTP M2 secret body"
        command, _, _ = send_command(blob=blob)
        digest = hashlib.sha256(blob).hexdigest()
        status, _, body = self.request(
            "PUT", f"/v1/artifact-blobs/{digest}", body=blob
        )
        self.assertEqual(status, 201, body)
        status, _, body = self.request(
            "POST",
            "/v1/commands",
            body=json.dumps(command).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 201, body)
        message_id = command["payload"]["message_id"]

        status, _, body = self.request(
            "GET", "/v1/sessions?" + urlencode({"project_id": PROJECT_ID})
        )
        self.assertEqual(status, 200, body)
        sessions = json.loads(body)["sessions"]
        self.assertEqual({session["session_id"] for session in sessions}, {SENDER_SESSION_ID, RECEIVER_SESSION_ID})
        self.assertNotIn('"active":', json.dumps(sessions))
        self.assertNotIn("jsonl_path", json.dumps(sessions))
        sender = next(session for session in sessions if session["session_id"] == SENDER_SESSION_ID)
        self.assertEqual(sender["workbench_ids"], ["canvas"])
        self.assertEqual(sender["active_workbench_id"], "canvas")

        inbox_target = "/v1/inbox?" + urlencode(
            {
                "project_id": PROJECT_ID,
                "session_id": RECEIVER_SESSION_ID,
                "after": "0",
                "limit": "1",
            }
        )
        status, _, body = self.request("GET", inbox_target)
        self.assertEqual(status, 200, body)
        inbox = json.loads(body)
        self.assertEqual(inbox["messages"][0]["message_id"], message_id)
        self.assertEqual(inbox["messages"][0]["state"], "queued")
        self.assertNotIn("HTTP M2 secret body", body.decode())

        message_target = "/v1/messages/" + str(message_id) + "?" + urlencode(
            {
                "project_id": PROJECT_ID,
                "recipient_session_id": RECEIVER_SESSION_ID,
            }
        )
        status, _, body = self.request("GET", message_target)
        self.assertEqual(status, 200, body)
        message = json.loads(body)
        self.assertEqual(message["body"], blob.decode())
        self.assertIsInstance(message["created_at"], str)
        self.assertIsInstance(message["inbox_seq"], int)

        wrong_identity = "/v1/messages/" + str(message_id) + "?" + urlencode(
            {"project_id": PROJECT_ID, "recipient_session_id": SENDER_SESSION_ID}
        )
        status, _, body = self.request("GET", wrong_identity)
        self.assertEqual(status, 403, body)
        self.assertNotIn("HTTP M2 secret body", body.decode())

    def test_workbench_bind_http_event_and_active_projection(self) -> None:
        self.register_sessions()
        command = bind_command(
            command_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa56",
            workbench_id="code",
        )
        status, _, body = self.request(
            "POST",
            "/v1/commands",
            body=json.dumps(command).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 201, body)
        receipt = json.loads(body)
        self.assertEqual(receipt["event"]["event_type"], "session.workbench_bound")
        sessions_status, _, sessions_body = self.request(
            "GET", "/v1/sessions?" + urlencode({"project_id": PROJECT_ID})
        )
        self.assertEqual(sessions_status, 200, sessions_body)
        sender = next(
            session
            for session in json.loads(sessions_body)["sessions"]
            if session["session_id"] == SENDER_SESSION_ID
        )
        self.assertEqual(sender["workbench_ids"], ["canvas", "code"])
        self.assertEqual(sender["active_workbench_id"], "code")

    def test_m2_events_are_sse_safe_and_inbox_cursor_is_bounded(self) -> None:
        self.register_sessions()
        blob = b"M2 SSE secret"
        command, _, _ = send_command(blob=blob)
        digest = hashlib.sha256(blob).hexdigest()
        self.assertEqual(
            self.request("PUT", f"/v1/artifact-blobs/{digest}", body=blob)[0], 201
        )
        self.assertEqual(
            self.request(
                "POST",
                "/v1/commands",
                body=json.dumps(command).encode(),
                headers={"Content-Type": "application/json"},
            )[0],
            201,
        )
        events_target = "/v1/events?" + urlencode({"project_id": PROJECT_ID})
        status, _, body = self.request("GET", events_target)
        self.assertEqual(status, 200, body)
        self.assertNotIn("M2 SSE secret", body.decode())
        self.assertNotIn('"body"', body.decode())

        invalid_after = "/v1/inbox?" + urlencode(
            {
                "project_id": PROJECT_ID,
                "session_id": RECEIVER_SESSION_ID,
                "after": "-1",
                "limit": "1",
            }
        )
        status, _, body = self.request("GET", invalid_after)
        self.assertEqual(status, 422, body)

    def test_events_wait_one_long_polls_until_a_later_event_and_rejects_invalid_wait(self) -> None:
        self.register_sessions()
        events_target = "/v1/events?" + urlencode(
            {"project_id": PROJECT_ID, "wait": "1"}
        )
        status, _, body = self.request(
            "GET",
            "/v1/events?" + urlencode({"project_id": PROJECT_ID, "wait": "maybe"}),
        )
        self.assertEqual(status, 422, body)

        response: dict[str, object] = {}

        def read_waiting_events() -> None:
            response["result"] = self.request(
                "GET", events_target, headers={"Last-Event-ID": "2"}
            )

        reader = threading.Thread(target=read_waiting_events)
        reader.start()
        time.sleep(0.1)
        blob = b"HTTP M2 wait body"
        command, _, _ = send_command(blob=blob)
        digest = hashlib.sha256(blob).hexdigest()
        self.assertEqual(
            self.request("PUT", f"/v1/artifact-blobs/{digest}", body=blob)[0], 201
        )
        self.assertEqual(
            self.request(
                "POST",
                "/v1/commands",
                body=json.dumps(command).encode(),
                headers={"Content-Type": "application/json"},
            )[0],
            201,
        )
        reader.join(timeout=5)
        self.assertFalse(reader.is_alive())
        status, _, body = response["result"]
        self.assertEqual(status, 200, body)
        self.assertIn("session.message_queued", body.decode())
        self.assertNotIn("HTTP M2 wait body", body.decode())


if __name__ == "__main__":
    import unittest

    unittest.main()
