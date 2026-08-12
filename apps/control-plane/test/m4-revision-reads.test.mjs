import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import { FetchQuantDomainRevisionClient } from "../dist/domain-revision-client.js";

const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const ARTIFACT_ID = "75757575-7575-4575-8575-757575757575";
const REVISION_ID = "30303030-3030-4030-8030-303030303030";
const CREATED_AT = "2026-08-12T00:00:00Z";
const SOURCE = new TextEncoder().encode("def on_start():\n    return []\n");
const SOURCE_SHA = createHash("sha256").update(SOURCE).digest("hex");

function client(fetchImplementation) {
  return new FetchQuantDomainRevisionClient({
    sessionClient: {
      baseUrl: "http://quant-domain.test",
      async stageJson() { throw new Error("not used"); },
      async stageText() { throw new Error("not used"); },
      async postCommand() { throw new Error("not used"); },
    },
    fetchImplementation,
  });
}

test("M4 revision client validates project and Activity read identities", async () => {
  const calls = [];
  const revisionClient = client(async (input) => {
    calls.push(input.toString());
    if (input.toString().endsWith("/v1/projects")) {
      return Response.json({
        projects: [{ project_id: PROJECT_ID, created_at: CREATED_AT }],
      });
    }
    return Response.json({
      activities: [{
        activity_id: ACTIVITY_ID,
        project_id: PROJECT_ID,
        created_at: CREATED_AT,
      }],
    });
  });

  assert.deepEqual(await revisionClient.listProjects(), {
    projects: [{ project_id: PROJECT_ID, created_at: CREATED_AT }],
  });
  assert.deepEqual(await revisionClient.listActivities(PROJECT_ID), {
    activities: [{
      activity_id: ACTIVITY_ID,
      project_id: PROJECT_ID,
      created_at: CREATED_AT,
    }],
  });
  assert.deepEqual(calls, [
    "http://quant-domain.test/v1/projects",
    `http://quant-domain.test/v1/projects/${PROJECT_ID}/activities`,
  ]);
});

test("M4 revision client verifies artifact metadata and returned bytes", async () => {
  const revisionClient = client(async (input) => {
    if (input.toString().endsWith("/content")) {
      return new Response(SOURCE, {
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      });
    }
    return Response.json({
      artifact_id: ARTIFACT_ID,
      project_id: PROJECT_ID,
      sha256: SOURCE_SHA,
      media_type: "text/plain",
      byte_size: SOURCE.byteLength,
      storage_uri: `cas://sha256/${SOURCE_SHA}`,
      producing_revision_id: REVISION_ID,
      producing_run_id: null,
      origin_kind: "service_generated",
      source_ref: REVISION_ID,
      created_at: CREATED_AT,
      revision_paths: [{ revision_id: REVISION_ID, path: "strategy.py" }],
      run_kinds: [],
    });
  });

  const artifact = await revisionClient.getArtifact(PROJECT_ID, ARTIFACT_ID);
  const body = await revisionClient.getArtifactContent(PROJECT_ID, artifact);
  assert.deepEqual(body, SOURCE);
});

test("M4 revision client rejects crossed Activity identity", async () => {
  const revisionClient = client(async () => Response.json({
    activities: [{
      activity_id: ACTIVITY_ID,
      project_id: "99999999-9999-4999-8999-999999999999",
      created_at: CREATED_AT,
    }],
  }));
  await assert.rejects(
    revisionClient.listActivities(PROJECT_ID),
    /crossed project identity/,
  );
});

test("M4 revision client rejects crossed artifact project identity", async () => {
  const revisionClient = client(async () => Response.json({
    artifact_id: ARTIFACT_ID,
    project_id: "99999999-9999-4999-8999-999999999999",
    sha256: SOURCE_SHA,
    media_type: "text/plain",
    byte_size: SOURCE.byteLength,
    storage_uri: `cas://sha256/${SOURCE_SHA}`,
    producing_revision_id: REVISION_ID,
    producing_run_id: null,
    origin_kind: "service_generated",
    source_ref: REVISION_ID,
    created_at: CREATED_AT,
    revision_paths: [{ revision_id: REVISION_ID, path: "strategy.py" }],
    run_kinds: [],
  }));
  await assert.rejects(
    revisionClient.getArtifact(PROJECT_ID, ARTIFACT_ID),
    /crossed request identity/,
  );
});

test("M4 revision client rejects foreign artifact metadata before reading content", async () => {
  let requestCount = 0;
  const revisionClient = client(async () => {
    requestCount += 1;
    return new Response(SOURCE, {
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  });
  const foreignArtifact = {
    artifact_id: ARTIFACT_ID,
    project_id: "99999999-9999-4999-8999-999999999999",
    sha256: SOURCE_SHA,
    media_type: "text/plain",
    byte_size: SOURCE.byteLength,
    storage_uri: `cas://sha256/${SOURCE_SHA}`,
    producing_revision_id: REVISION_ID,
    producing_run_id: null,
    origin_kind: "service_generated",
    source_ref: REVISION_ID,
    created_at: CREATED_AT,
    revision_paths: [{ revision_id: REVISION_ID, path: "strategy.py" }],
    run_kinds: [],
  };

  await assert.rejects(
    revisionClient.getArtifactContent(PROJECT_ID, foreignArtifact),
    /crossed request identity/,
  );
  assert.equal(requestCount, 0);
});
