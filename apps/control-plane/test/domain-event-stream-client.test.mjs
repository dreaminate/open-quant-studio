import assert from "node:assert/strict";
import test from "node:test";

import { FetchDomainEventStreamClient } from "../dist/domain-event-stream-client.js";


const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ARTIFACT = {
  artifact_id: "99999999-9999-4999-8999-999999999999",
  sha256: "5106492190b928ce9c92f7d0e78571f0da8b3800651b9c1cc9983025ba9e1dc2",
  media_type: "text/csv",
  byte_size: 256,
  storage_uri:
    "cas://sha256/5106492190b928ce9c92f7d0e78571f0da8b3800651b9c1cc9983025ba9e1dc2",
  producing_revision_id: null,
  producing_run_id: null,
  provenance: {
    origin_kind: "fixture",
    source_ref: "15151515-1515-4515-8515-151515151515",
  },
};

function event(streamSeq, eventType = "context.captured") {
  return {
    event_id:
      streamSeq === 1
        ? "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        : "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    stream_seq: streamSeq,
    schema_version: 1,
    event_type: eventType,
    project_id: PROJECT_ID,
    activity_id: "33333333-3333-4333-8333-333333333333",
    session_id: "pi:session:m1-test",
    workbench_id: "canvas",
    correlation_id: "44444444-4444-4444-8444-444444444444",
    causation_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    recorded_at: "2026-08-11T19:00:00+08:00",
    variant_id: null,
    base_revision_id: null,
    payload:
      eventType === "context.captured"
        ? {
            context_item_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            title: "Frozen M0 market fixture",
            trust_state: "raw_evidence",
            artifact: ARTIFACT,
          }
        : {
            artifact_id: ARTIFACT.artifact_id,
            job_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
            result: { sha256: ARTIFACT.sha256, byte_size: ARTIFACT.byte_size },
            error_code: null,
          },
  };
}

function sse(...events) {
  const body = events
    .map(
      (domainEvent) =>
        `id: ${domainEvent.stream_seq}\nevent: domain.event\ndata: ${JSON.stringify(domainEvent)}\n\n`,
    )
    .join("");
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream; charset=utf-8" },
  });
}

test("fetch SSE reader advances only after ordered callbacks acknowledge events", async () => {
  const calls = [];
  const fetchImpl = async (input, init) => {
    calls.push({ input, headers: new Headers(init.headers) });
    return sse(event(1), event(2, "artifact.verification_succeeded"));
  };
  const client = new FetchDomainEventStreamClient(
    "http://127.0.0.1:8777",
    fetchImpl,
  );
  const received = [];

  const acknowledged = await client.read({
    projectId: PROJECT_ID,
    lastAcknowledgedStreamSeq: 0,
    signal: new AbortController().signal,
    onEvent: async (domainEvent) => received.push(domainEvent.stream_seq),
  });

  assert.equal(acknowledged, 2);
  assert.deepEqual(received, [1, 2]);
  assert.equal(calls[0].headers.has("Last-Event-ID"), false);
  assert.equal(
    calls[0].input,
    `http://127.0.0.1:8777/v1/events?project_id=${PROJECT_ID}`,
  );
});

test("callback failure preserves the caller's acknowledged cursor for redelivery", async () => {
  const calls = [];
  const fetchImpl = async (_input, init) => {
    calls.push(new Headers(init.headers).get("Last-Event-ID"));
    return sse(event(2, "artifact.verification_succeeded"));
  };
  const client = new FetchDomainEventStreamClient(
    "http://127.0.0.1:8777",
    fetchImpl,
  );
  const request = {
    projectId: PROJECT_ID,
    lastAcknowledgedStreamSeq: 1,
    signal: new AbortController().signal,
  };

  await assert.rejects(
    client.read({
      ...request,
      onEvent: async () => {
        throw new Error("projection failed");
      },
    }),
    /projection failed/,
  );
  const acknowledged = await client.read({
    ...request,
    onEvent: async () => undefined,
  });

  assert.equal(acknowledged, 2);
  assert.deepEqual(calls, ["1", "1"]);
});

test("SSE id must equal the validated event stream sequence", async () => {
  const wrongFrame = new Response(
    `id: 7\nevent: domain.event\ndata: ${JSON.stringify(event(2))}\n\n`,
    {
      headers: { "Content-Type": "text/event-stream" },
    },
  );
  const client = new FetchDomainEventStreamClient(
    "http://127.0.0.1:8777",
    async () => wrongFrame,
  );

  await assert.rejects(
    client.read({
      projectId: PROJECT_ID,
      lastAcknowledgedStreamSeq: 1,
      signal: new AbortController().signal,
      onEvent: async () => undefined,
    }),
    /SSE id does not match event stream_seq/,
  );
});

test("known event types must satisfy their concrete payload contract", async () => {
  const invalid = event(1);
  invalid.payload = {};
  const client = new FetchDomainEventStreamClient(
    "http://127.0.0.1:8777",
    async () => sse(invalid),
  );

  await assert.rejects(
    client.read({
      projectId: PROJECT_ID,
      lastAcknowledgedStreamSeq: 0,
      signal: new AbortController().signal,
      onEvent: async () => undefined,
    }),
    /domain event contract violation/,
  );
});
