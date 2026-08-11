import assert from "node:assert/strict";
import test from "node:test";

import {
  validateSessionEvent,
  validateSessionMessageAcknowledgeCommand,
  validateSessionMessageReceiveCommand,
  validateSessionMessageReplyCommand,
  validateSessionMessageSendCommand,
  validateSessionRegisterCommand,
  validateSessionWorkbenchBindCommand,
} from "../dist/index.js";

const projectId = "22222222-2222-4222-8222-222222222222";
const activityId = "33333333-3333-4333-8333-333333333333";
const senderSessionId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const receiverSessionId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const correlationId = "44444444-4444-4444-8444-444444444444";
const messageId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const artifactId = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const digest = "a".repeat(64);

function envelope(commandType, commandId, sessionId, payload) {
  return {
    command_id: commandId,
    schema_version: 1,
    command_type: commandType,
    project_id: projectId,
    activity_id: activityId,
    session_id: sessionId,
    workbench_id: "canvas",
    correlation_id: correlationId,
    expected_revision_id: null,
    variant_id: null,
    base_revision_id: null,
    payload,
  };
}

function artifact() {
  return {
    artifact_id: artifactId,
    sha256: digest,
    media_type: "text/plain",
    byte_size: 14,
    storage_uri: `cas://sha256/${digest}`,
    producing_revision_id: null,
    producing_run_id: null,
    provenance: {
      origin_kind: "fixture",
      source_ref: "15151515-1515-4515-8515-151515151515",
    },
  };
}

test("M2 command validators enforce registration and body-free message payloads", () => {
  const register = envelope(
    "session.register",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa01",
    senderSessionId,
    {
      pi_session_id: "pi-session-a",
      session_uri: "pi-jsonl://session/pi-session-a",
    },
  );
  assert.equal(validateSessionRegisterCommand(register).valid, true);

  const send = envelope(
    "session.message_send",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa02",
    senderSessionId,
    {
      message_id: messageId,
      recipient_session_id: receiverSessionId,
      message_kind: "send",
      reply_to: null,
      source_refs: [],
      artifact: artifact(),
    },
  );
  assert.equal(validateSessionMessageSendCommand(send).valid, true);
  const invalid = structuredClone(send);
  invalid.payload.body = "secret body";
  assert.equal(validateSessionMessageSendCommand(invalid).valid, false);

  const bind = envelope(
    "session.workbench_bind",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa06",
    senderSessionId,
    { workbench_id: "code" },
  );
  bind.workbench_id = "code";
  assert.equal(validateSessionWorkbenchBindCommand(bind).valid, true);

  const unboundedIdentity = structuredClone(bind);
  unboundedIdentity.session_id = "x".repeat(129);
  assert.equal(validateSessionWorkbenchBindCommand(unboundedIdentity).valid, false);
});

test("M2 reply and receipt commands validate the source and CAS state contract", () => {
  const reply = envelope(
    "session.message_reply",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa03",
    receiverSessionId,
    {
      message_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
      recipient_session_id: senderSessionId,
      message_kind: "reply",
      reply_to: messageId,
      source_refs: [
        {
          session_id: receiverSessionId,
          entry_id: "entry-1",
          leaf_id: "leaf-1",
          sha256: digest,
          source_uri: "pi-jsonl://session/pi-session-a#entry=entry-1",
        },
      ],
      artifact: artifact(),
    },
  );
  assert.equal(validateSessionMessageReplyCommand(reply).valid, true);
  const receive = envelope(
    "session.message_receive",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa04",
    receiverSessionId,
    { message_id: messageId, expected_state: "queued", expected_version: 0 },
  );
  assert.equal(validateSessionMessageReceiveCommand(receive).valid, true);
  const impossibleReceive = structuredClone(receive);
  impossibleReceive.payload.expected_state = "acknowledged";
  impossibleReceive.payload.expected_version = 3;
  assert.equal(validateSessionMessageReceiveCommand(impossibleReceive).valid, false);
  const acknowledge = envelope(
    "session.message_acknowledge",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa05",
    receiverSessionId,
    { message_id: messageId, expected_state: "injected", expected_version: 2 },
  );
  assert.equal(validateSessionMessageAcknowledgeCommand(acknowledge).valid, true);
  const impossibleAcknowledge = structuredClone(acknowledge);
  impossibleAcknowledge.payload.expected_state = "queued";
  impossibleAcknowledge.payload.expected_version = 0;
  assert.equal(
    validateSessionMessageAcknowledgeCommand(impossibleAcknowledge).valid,
    false,
  );
});

test("M2 events are accepted only through the explicit event registry", () => {
  const event = {
    event_id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
    stream_seq: 1,
    schema_version: 1,
    event_type: "session.message_queued",
    project_id: projectId,
    activity_id: activityId,
    session_id: senderSessionId,
    workbench_id: "canvas",
    correlation_id: correlationId,
    causation_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa02",
    recorded_at: "2026-08-11T00:00:00Z",
    variant_id: null,
    base_revision_id: null,
    payload: {
      message_id: messageId,
      recipient_session_id: receiverSessionId,
      message_kind: "send",
      artifact_id: artifactId,
      artifact_sha256: digest,
      state: "queued",
      receipt_version: 0,
      reply_to: null,
      source_refs: [],
    },
  };
  assert.equal(validateSessionEvent(event).valid, true);
  const impossibleState = structuredClone(event);
  impossibleState.payload.state = "acknowledged";
  impossibleState.payload.receipt_version = 3;
  assert.equal(validateSessionEvent(impossibleState).valid, false);
  const unknown = structuredClone(event);
  unknown.event_type = "session.unknown";
  assert.equal(validateSessionEvent(unknown).valid, false);

  const bound = {
    ...event,
    event_type: "session.workbench_bound",
    workbench_id: "code",
    payload: {
      session_id: senderSessionId,
      workbench_id: "code",
    },
  };
  assert.equal(validateSessionEvent(bound).valid, true);
});
