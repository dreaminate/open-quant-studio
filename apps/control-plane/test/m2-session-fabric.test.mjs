import assert from "node:assert/strict";
import test from "node:test";

import { SessionFabric } from "../dist/session-fabric.js";
import { FetchQuantDomainSessionClient } from "../dist/domain-session-client.js";
import { createSessionFabricTools } from "../dist/session-tools.js";

const UUID_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const UUID_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const UUID_C = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";

test("session client validates and stages bounded UTF-8 text without exposing bodies in errors", async () => {
  const calls = [];
  const fetchImpl = async (input, init = {}) => {
    calls.push({ input: String(input), init });
    if (String(input).endsWith("/v1/artifact-blobs/" + "a".repeat(64))) {
      return new Response(JSON.stringify({
        sha256: "a".repeat(64),
        byte_size: 5,
        storage_uri: "cas://sha256/" + "a".repeat(64),
      }), { status: 201, headers: { "content-type": "application/json" } });
    }
    return new Response(JSON.stringify({ error: "contract_violation" }), {
      status: 422,
      headers: { "content-type": "application/json" },
    });
  };
  const client = new FetchQuantDomainSessionClient("http://127.0.0.1:8777", fetchImpl);
  await assert.rejects(
    client.stageText("x".repeat(65537)),
    /65536/,
  );
  await assert.rejects(
    client.postCommand({ command_type: "not-typed" }),
    /contract/i,
  );
  assert.equal(calls.length, 0);
});

test("fabric leaves messages queued while offline and only injects once after a mark failure", async () => {
  const calls = [];
  let active = false;
  let markerWritten = false;
  let current = {
    inbox_seq: 1,
    message_id: UUID_A,
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    sender_session_id: "session-a",
    recipient_session_id: "session-b",
    correlation_id: UUID_C,
    message_kind: "ask",
    artifact_id: UUID_B,
    artifact_sha256: "d".repeat(64),
    reply_to: null,
    source_refs: [],
    created_at: "2026-08-11T00:00:00Z",
    state: "queued",
    receipt_version: 0,
  };
  const client = {
    baseUrl: "http://127.0.0.1:8777",
    async listSessions() { return []; },
    async inbox() { return [{ ...current }]; },
    async getMessage() { return { ...current, body: "body" }; },
    async transitionReceipt(request) {
      calls.push(request);
      if (request.commandType === "session.message_mark_injected" && calls.filter((entry) => entry.commandType === request.commandType).length === 1) {
        throw new Error("injected transition failed");
      }
      if (request.commandType === "session.message_receive") {
        current = { ...current, state: "receiver_received", receipt_version: 1 };
      }
      if (request.commandType === "session.message_mark_injected") {
        current = { ...current, state: "injected", receipt_version: 2 };
      }
      const state = current.state;
      const eventType = request.commandType === "session.message_receive"
        ? "session.message_receiver_received"
        : request.commandType === "session.message_mark_injected"
          ? "session.message_injected"
          : "session.message_acknowledged";
      return {
        disposition: "accepted",
        event: {
          event_id: UUID_B,
          stream_seq: current.receipt_version,
          schema_version: 1,
          event_type: eventType,
          project_id: PROJECT_ID,
          activity_id: ACTIVITY_ID,
          session_id: "session-b",
          workbench_id: "canvas",
          correlation_id: UUID_C,
          causation_id: UUID_A,
          recorded_at: "2026-08-11T00:00:00Z",
          variant_id: null,
          base_revision_id: null,
          payload: {
            message_id: UUID_A,
            recipient_session_id: "session-b",
            message_kind: "ask",
            artifact_id: UUID_B,
            artifact_sha256: "d".repeat(64),
            state,
            receipt_version: current.receipt_version,
            reply_to: null,
            source_refs: [],
          },
        },
      };
    },
  };
  const adapter = {
    sessionId: "session-b",
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    piSessionId: "pi-session-b",
    entries: [],
    currentLeafId: "leaf-b",
    isStreaming: false,
    async hasMessageMarker() { return markerWritten; },
    async followUp(input, options) {
      calls.push({ kind: "followUp", input, options });
      markerWritten = true;
      return { accepted: true, duplicate: false, marker: `[oqs-message:${input.messageId}]` };
    },
    dispose() {},
  };
  const registry = {
    get(sessionId) { return active && sessionId === "session-b" ? adapter : undefined; },
    status(sessionId) { return sessionId === "session-b" ? { sessionId, projectId: PROJECT_ID, activityId: ACTIVITY_ID, workbenchIds: ["canvas"], piSessionId: "pi-session-b", isStreaming: false } : undefined; },
    list() { return [this.status("session-b")]; },
  };
  const recall = { async search() { return []; }, async context() { return {}; } };
  const fabric = new SessionFabric({ client, registry, recall, projectId: PROJECT_ID, activityId: ACTIVITY_ID, workbenchId: "canvas" });
  const offline = await fabric.deliver("session-b");
  assert.equal(offline[0].message.state, "queued");
  assert.equal(offline[0].delivered, false);
  assert.equal(calls.length, 0);
  active = true;
  await assert.rejects(fabric.deliver("session-b", { wake: true }), /injected transition failed/);
  const delivered = await fabric.deliver("session-b", { wake: true });
  assert.equal(delivered[0].injected, true);
  assert.equal(calls.filter((entry) => entry.kind === "followUp").length, 1);
  assert.equal(calls.filter((entry) => entry.commandType === "session.message_mark_injected").length, 2);
});

test("fabric tools are exactly the bounded OQS session tool set", async () => {
  const actorCalls = [];
  const fabric = {
    list: async () => [],
    status: async () => ({}),
    search: async () => [],
    context: async () => ({}),
    send: async (request) => { actorCalls.push(request); return {}; },
    ask: async (request) => { actorCalls.push(request); return {}; },
    reply: async (request) => { actorCalls.push(request); return {}; },
    pull: async (sessionId) => { actorCalls.push({ sessionId }); return []; },
    acknowledge: async (sessionId) => { actorCalls.push({ sessionId }); return {}; },
  };
  const tools = createSessionFabricTools(fabric, { sessionId: "session-b", workbenchId: "canvas" });
  assert.deepEqual(tools.map((tool) => tool.name), [
    "session_list", "session_status", "session_search", "session_context",
    "session_send", "session_ask", "session_reply", "inbox_pull", "inbox_ack",
  ]);
  assert.equal(tools.some((tool) => ["read", "bash", "edit", "write"].includes(tool.name)), false);
  assert.equal("session_id" in tools.find((tool) => tool.name === "session_ask").parameters.properties, false);
  assert.equal(
    tools.find((tool) => tool.name === "session_reply")
      .parameters.properties.source_refs.items.type,
    "object",
  );
  await tools.find((tool) => tool.name === "session_ask").execute("call", {
    recipient_session_id: "session-a",
    body: "actor binding",
  });
  assert.equal(actorCalls[0].sessionId, "session-b");
});

test("session status never exposes an active session from another project", async () => {
  const registry = {
    status: () => ({
      sessionId: "foreign-session",
      piSessionId: "foreign-pi",
      projectId: "foreign-project",
      activityId: ACTIVITY_ID,
      workbenchIds: ["canvas"],
      activeWorkbenchId: "canvas",
      isStreaming: false,
    }),
  };
  const client = {
    baseUrl: "http://127.0.0.1:8777",
    async listSessions() { return []; },
  };
  const fabric = new SessionFabric({
    client,
    registry,
    recall: {},
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    workbenchId: "canvas",
  });
  assert.equal(await fabric.status("foreign-session"), undefined);
});

test("queued SSE delivery fetches the exact event message instead of the first inbox page", async () => {
  let state = "queued";
  let receiptVersion = 0;
  let inboxCalls = 0;
  const message = {
    inbox_seq: 101,
    message_id: UUID_A,
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    sender_session_id: "session-a",
    recipient_session_id: "session-b",
    correlation_id: UUID_C,
    message_kind: "send",
    artifact_id: UUID_B,
    artifact_sha256: "d".repeat(64),
    reply_to: null,
    source_refs: [],
    created_at: "2026-08-11T00:00:00Z",
    state,
    receipt_version: receiptVersion,
    body: "message 101",
  };
  const transitionEvent = (request) => {
    if (request.commandType === "session.message_receive") {
      state = "receiver_received";
      receiptVersion = 1;
    } else {
      state = "injected";
      receiptVersion = 2;
    }
    return {
      event_id: request.commandType === "session.message_receive" ? UUID_B : UUID_C,
      stream_seq: receiptVersion + 101,
      schema_version: 1,
      event_type: request.commandType === "session.message_receive"
        ? "session.message_receiver_received"
        : "session.message_injected",
      project_id: PROJECT_ID,
      activity_id: ACTIVITY_ID,
      session_id: "session-b",
      workbench_id: "canvas",
      correlation_id: UUID_C,
      causation_id: UUID_A,
      recorded_at: "2026-08-11T00:00:00Z",
      variant_id: null,
      base_revision_id: null,
      payload: {
        message_id: UUID_A,
        recipient_session_id: "session-b",
        message_kind: "send",
        artifact_id: UUID_B,
        artifact_sha256: "d".repeat(64),
        state,
        receipt_version: receiptVersion,
        reply_to: null,
        source_refs: [],
      },
    };
  };
  const client = {
    baseUrl: "http://127.0.0.1:8777",
    async listSessions() { return []; },
    async inbox() {
      inboxCalls += 1;
      return [];
    },
    async getMessage(request) {
      assert.equal(request.messageId, UUID_A);
      return { ...message, state, receipt_version: receiptVersion };
    },
    async transitionReceipt(request) {
      return { disposition: "accepted", event: transitionEvent(request) };
    },
  };
  const adapter = {
    sessionId: "session-b",
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    async hasMessageMarker() { return false; },
    async followUp(input) {
      return {
        accepted: true,
        duplicate: false,
        marker: `[oqs-message:${input.messageId}]`,
      };
    },
  };
  const registry = {
    get: (sessionId) => sessionId === "session-b" ? adapter : undefined,
    status: (sessionId) => sessionId === "session-b" ? {
      sessionId,
      piSessionId: "pi-session-b",
      projectId: PROJECT_ID,
      activityId: ACTIVITY_ID,
      workbenchIds: ["canvas"],
      activeWorkbenchId: "canvas",
      isStreaming: false,
    } : undefined,
  };
  const eventStreamClient = {
    async read(request) {
      assert.equal(request.waitForEvent, true);
      await request.onEvent({
        event_type: "session.message_queued",
        activity_id: ACTIVITY_ID,
        payload: { recipient_session_id: "session-b", message_id: UUID_A },
      });
      return 101;
    },
  };
  const fabric = new SessionFabric({
    client,
    registry,
    recall: {},
    eventStreamClient,
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    workbenchId: "canvas",
  });
  const cursor = await fabric.readEvents({
    lastAcknowledgedStreamSeq: 100,
    signal: new AbortController().signal,
    wake: true,
  });
  assert.equal(cursor, 101);
  assert.equal(inboxCalls, 0);
  assert.equal(state, "injected");
});

test("project SSE advances past queued events owned by another activity", async () => {
  let messageReads = 0;
  const adapter = {
    sessionId: "session-foreign-activity",
    projectId: PROJECT_ID,
    activityId: "44444444-4444-4444-8444-444444444444",
  };
  const registry = {
    get: (sessionId) => sessionId === adapter.sessionId ? adapter : undefined,
    status: () => undefined,
  };
  const client = {
    baseUrl: "http://127.0.0.1:8777",
    async getMessage() {
      messageReads += 1;
      throw new Error("foreign activity message must not enter this fabric");
    },
  };
  const eventStreamClient = {
    async read(request) {
      await request.onEvent({
        event_type: "session.message_queued",
        activity_id: adapter.activityId,
        payload: {
          recipient_session_id: adapter.sessionId,
          message_id: UUID_A,
        },
      });
      return 7;
    },
  };
  const fabric = new SessionFabric({
    client,
    registry,
    recall: {},
    eventStreamClient,
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    workbenchId: "canvas",
  });
  const cursor = await fabric.readEvents({
    lastAcknowledgedStreamSeq: 6,
    signal: new AbortController().signal,
  });
  assert.equal(cursor, 7);
  assert.equal(messageReads, 0);
});
