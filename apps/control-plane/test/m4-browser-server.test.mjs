import assert from "node:assert/strict";
import { once } from "node:events";
import { createServer } from "node:http";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

import { QuantDomainHttpError } from "../dist/domain-session-client.js";
import {
  createOqsBrowserServer,
  loadM4FormalRunFixture,
} from "../dist/browser-server.js";
import {
  resolveM4DataRoot,
  waitForDomain,
} from "../../../scripts/run-m4-local.mjs";

const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const SESSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const VARIANT_ID = "20202020-2020-4020-8020-202020202020";
const ROOT_REVISION_ID = "10101010-1010-4010-8010-101010101010";
const VARIANT_REVISION_ID = "30303030-3030-4030-8030-303030303030";
const CANDIDATE_REVISION_ID = "40404040-4040-4040-8040-404040404040";
const RUN_ID = "72727272-7272-4272-8272-727272727272";
const VALIDATION_ID = "73737373-7373-4373-8373-737373737373";
const SOURCE_ARTIFACT_ID = "75757575-7575-4575-8575-757575757575";
const REPO_ROOT = resolve(import.meta.dirname, "../../..");
const FIXTURE_PATH = resolve(
  REPO_ROOT,
  "fixtures/backtests/m3-a-share-long-short-v1.json",
);
const FIXTURE = await loadM4FormalRunFixture(FIXTURE_PATH);

function acceptedReceipt() {
  return { command_id: SESSION_ID, disposition: "accepted", event: { event_type: "test" } };
}

function revision(revisionId, variantId = VARIANT_ID) {
  return {
    revision_id: revisionId,
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    variant_id: variantId,
    base_revision_id: ROOT_REVISION_ID,
    git_commit_oid: "a".repeat(40),
    git_tree_oid: "b".repeat(40),
    message: "test revision",
    created_by_session_id: SESSION_ID,
    created_at: "2026-08-12T00:00:00Z",
    files: [],
  };
}

function runDetail(activityId = ACTIVITY_ID) {
  return {
    run: {
      run_id: RUN_ID,
      project_id: PROJECT_ID,
      activity_id: activityId,
      variant_id: VARIANT_ID,
      candidate_revision_id: CANDIDATE_REVISION_ID,
      status: "succeeded",
    },
    validation: { validation_id: VALIDATION_ID, outcome: "passed" },
  };
}

function harness(overrides = {}) {
  const calls = [];
  const listeners = new Set();
  const adapter = {
    async prompt(text) {
      calls.push(["prompt", text]);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
  const registry = {
    status(sessionId) {
      return sessionId === SESSION_ID
        ? {
            sessionId,
            projectId: PROJECT_ID,
            activityId: ACTIVITY_ID,
            activeWorkbenchId: "canvas",
            isStreaming: false,
          }
        : undefined;
    },
    get(sessionId) {
      return sessionId === SESSION_ID ? adapter : undefined;
    },
  };
  const revisionClient = {
    async listProjects() {
      return { projects: [{ project_id: PROJECT_ID, created_at: "2026-08-12T00:00:00Z" }] };
    },
    async listActivities() {
      return { activities: [{ activity_id: ACTIVITY_ID, project_id: PROJECT_ID, created_at: "2026-08-12T00:00:00Z" }] };
    },
    async getProjectRevisionHead() {
      return { project_id: PROJECT_ID, head_revision_id: ROOT_REVISION_ID };
    },
    async listVariants() {
      return [{
        variant_id: VARIANT_ID,
        project_id: PROJECT_ID,
        activity_id: ACTIVITY_ID,
        base_revision_id: ROOT_REVISION_ID,
        created_by_session_id: SESSION_ID,
        created_at: "2026-08-12T00:00:00Z",
        head_revision_id: VARIANT_REVISION_ID,
        version: 1,
        updated_at: "2026-08-12T00:00:00Z",
      }];
    },
    async getRevision(_projectId, revisionId) {
      return revision(revisionId);
    },
    async compareRevisions(_projectId, leftRevisionId, rightRevisionId) {
      return { project_id: PROJECT_ID, left_revision_id: leftRevisionId, right_revision_id: rightRevisionId, changes: [] };
    },
    async listRuns() {
      return { runs: [] };
    },
    async getRun() {
      return runDetail();
    },
    async createStrategyVariant(request) {
      calls.push(["variant", request]);
      return acceptedReceipt();
    },
    async createRevisionChild(request) {
      calls.push(["child", request]);
      return acceptedReceipt();
    },
    async createMergeCandidate(request) {
      calls.push(["merge", request]);
      return acceptedReceipt();
    },
    async requestFormalRun(request) {
      calls.push(["formal", request]);
      return acceptedReceipt();
    },
    async promoteRevision(request) {
      calls.push(["promote", request]);
      return acceptedReceipt();
    },
    ...overrides.revisionClient,
  };
  const server = createOqsBrowserServer({
    activeSessionId: SESSION_ID,
    registry,
    revisionClient,
    formalRunFixture: FIXTURE,
    webRoot: overrides.webRoot,
  });
  return { adapter, calls, listeners, registry, revisionClient, server };
}

async function withServer(setup, run) {
  setup.server.listen(0, "127.0.0.1");
  await once(setup.server, "listening");
  const address = setup.server.address();
  const baseUrl = `http://127.0.0.1:${address.port}`;
  try {
    await run(baseUrl);
  } finally {
    setup.server.close();
    await once(setup.server, "close");
  }
}

test("trusted Formal Run fixture is canonical and hash-bound at server startup", async (t) => {
  const fixture = await loadM4FormalRunFixture(FIXTURE_PATH);
  assert.equal(new TextEncoder().encode(fixture.engineInputJson).byteLength, 2470);
  assert.equal(
    fixture.dataSnapshotSha256,
    "520d7c4b4faecbd63b21fa761a741f76e8aa961c09af244348441236ea854699",
  );
  assert.equal(fixture.priceBasis, "raw");
  assert.equal(fixture.randomSeed, 0);
  const engineInputJson = fixture.engineInputJson;
  assert.throws(() => {
    fixture.engineInputJson = "{}";
  }, TypeError);
  assert.equal(fixture.engineInputJson, engineInputJson);

  const tempDirectory = await mkdtemp(join(tmpdir(), "oqs-m4-fixture-"));
  t.after(() => rm(tempDirectory, { recursive: true, force: true }));
  const tampered = JSON.parse(await readFile(FIXTURE_PATH, "utf8"));
  tampered.input.account.starting_balance_atoms = "999999999";
  const tamperedPath = join(tempDirectory, "tampered.json");
  await writeFile(tamperedPath, JSON.stringify(tampered));
  await assert.rejects(
    loadM4FormalRunFixture(tamperedPath),
    /fixture input identity is invalid/,
  );
});

test("M4 launcher confines durable state to a named repository var instance", () => {
  assert.equal(
    resolveM4DataRoot("var/reviewer-instance"),
    resolve(REPO_ROOT, "var/reviewer-instance"),
  );
  assert.throws(() => resolveM4DataRoot("var"), /must stay inside/);
  assert.throws(() => resolveM4DataRoot("../outside"), /must stay inside/);
  assert.throws(() => resolveM4DataRoot("/"), /must stay inside/);
});

test("M4 launcher rejects health from a different quant-domain instance", async () => {
  const incumbent = createServer((_request, response) => {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify({
      status: "ok",
      service: "quant-domain",
      instance_token: "incumbent-instance",
    }));
  });
  incumbent.listen(0, "127.0.0.1");
  await once(incumbent, "listening");
  const address = incumbent.address();
  assert.notEqual(typeof address, "string");
  assert.notEqual(address, null);
  try {
    await assert.rejects(
      waitForDomain(
        `http://127.0.0.1:${address.port}`,
        { exitCode: null },
        "new-launcher-instance",
      ),
      /port is owned by a different instance/,
    );
  } finally {
    incumbent.close();
    await once(incumbent, "close");
  }
});

test("browser server serves the built SPA and only bounded asset paths", async (t) => {
  const webRoot = await mkdtemp(join(tmpdir(), "oqs-m4-web-"));
  t.after(() => rm(webRoot, { recursive: true, force: true }));
  await mkdir(join(webRoot, "assets"));
  await writeFile(join(webRoot, "index.html"), "<!doctype html><title>OQS M4</title>");
  await writeFile(join(webRoot, "assets", "app.js"), "globalThis.oqs = true;\n");
  const setup = harness({ webRoot });

  await withServer(setup, async (baseUrl) => {
    const index = await fetch(`${baseUrl}/`);
    assert.equal(index.status, 200);
    assert.equal(index.headers.get("content-type"), "text/html; charset=utf-8");
    assert.match(await index.text(), /OQS M4/);

    const asset = await fetch(`${baseUrl}/assets/app.js`);
    assert.equal(asset.status, 200);
    assert.equal(asset.headers.get("content-type"), "text/javascript; charset=utf-8");
    assert.match(await asset.text(), /globalThis\.oqs/);

    const unlisted = await fetch(`${baseUrl}/package.json`);
    assert.equal(unlisted.status, 404);
  });
});

test("browser actor is server-sealed and child edits use a fresh variant head", async () => {
  const setup = harness();
  await withServer(setup, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/api/v1/variants/${VARIANT_ID}/revisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: "Raise entry threshold",
        files: [{ path: "strategy.py", body: "def on_start():\n    return []\n" }],
      }),
    });
    assert.equal(response.status, 200);
    assert.deepEqual(setup.calls[0], ["child", {
      projectId: PROJECT_ID,
      activityId: ACTIVITY_ID,
      sessionId: SESSION_ID,
      workbenchId: "canvas",
      variantId: VARIANT_ID,
      baseRevisionId: VARIANT_REVISION_ID,
      expectedRevisionId: VARIANT_REVISION_ID,
      message: "Raise entry threshold",
      files: [{ path: "strategy.py", body: "def on_start():\n    return []\n" }],
    }]);

    const rejected = await fetch(`${baseUrl}/api/v1/variants/${VARIANT_ID}/revisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        projectId: PROJECT_ID,
        message: "forged actor",
        files: [{ path: "strategy.py", body: "pass\n" }],
      }),
    });
    assert.equal(rejected.status, 422);
    assert.deepEqual(await rejected.json(), { error: "invalid_request" });
    assert.equal(setup.calls.length, 1);
  });
});

test("Formal Run accepts no browser authority and injects the trusted fixture", async () => {
  assert.throws(
    () => createOqsBrowserServer({
      activeSessionId: SESSION_ID,
      registry: harness().registry,
      revisionClient: harness().revisionClient,
    }),
    /formal Run fixture is required/,
  );
  assert.throws(
    () => createOqsBrowserServer({
      activeSessionId: SESSION_ID,
      registry: harness().registry,
      revisionClient: harness().revisionClient,
      formalRunFixture: { ...FIXTURE },
    }),
    /formal Run fixture must be loaded from the pinned fixture/,
  );
  const setup = harness();
  await withServer(setup, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/api/v1/revisions/${CANDIDATE_REVISION_ID}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    assert.equal(response.status, 200);
    assert.deepEqual(setup.calls[0], ["formal", {
      projectId: PROJECT_ID,
      activityId: ACTIVITY_ID,
      sessionId: SESSION_ID,
      workbenchId: "canvas",
      candidateRevisionId: CANDIDATE_REVISION_ID,
      variantId: VARIANT_ID,
      strategyTreeOid: "b".repeat(40),
      ...FIXTURE,
    }]);

    const rejected = await fetch(`${baseUrl}/api/v1/revisions/${CANDIDATE_REVISION_ID}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engineInputJson: "{}" }),
    });
    assert.equal(rejected.status, 422);
    assert.equal(setup.calls.length, 1);
  });
});

test("Promote derives validation and fresh project head state", async () => {
  const setup = harness();
  await withServer(setup, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/api/v1/runs/${RUN_ID}/promote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    assert.equal(response.status, 200);
    assert.deepEqual(setup.calls[0], ["promote", {
      projectId: PROJECT_ID,
      activityId: ACTIVITY_ID,
      sessionId: SESSION_ID,
      workbenchId: "canvas",
      expectedRevisionId: ROOT_REVISION_ID,
      variantId: VARIANT_ID,
      candidateRevisionId: CANDIDATE_REVISION_ID,
      validationId: VALIDATION_ID,
    }]);
  });
});

test("Promote preserves bounded upstream conflicts", async () => {
  const setup = harness({
    revisionClient: {
      async promoteRevision() {
        throw new QuantDomainHttpError({ status: 409, code: "promotion_conflict" });
      },
    },
  });
  await withServer(setup, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/api/v1/runs/${RUN_ID}/promote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    assert.equal(response.status, 409);
    assert.deepEqual(await response.json(), { error: "promotion_conflict" });
  });
});

test("Pi browser boundary accepts only prompt text and projects safe SSE events", async () => {
  const setup = harness();
  await withServer(setup, async (baseUrl) => {
    const prompt = await fetch(`${baseUrl}/api/v1/chat/prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "Explain this strategy change." }),
    });
    assert.equal(prompt.status, 204);
    assert.deepEqual(setup.calls, [["prompt", "Explain this strategy change."]]);

    const forged = await fetch(`${baseUrl}/api/v1/chat/prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "hello", sessionId: SESSION_ID }),
    });
    assert.equal(forged.status, 422);

    const abort = new AbortController();
    const stream = await fetch(`${baseUrl}/api/v1/chat/events`, { signal: abort.signal });
    assert.equal(stream.headers.get("content-type"), "text/event-stream; charset=utf-8");
    const reader = stream.body.getReader();
    await reader.read();
    for (const listener of setup.listeners) {
      listener({ type: "assistant_text_delta", delta: "Bounded answer" });
    }
    const frame = new TextDecoder().decode((await reader.read()).value);
    assert.match(frame, /event: pi\.chat/);
    assert.match(frame, /"delta":"Bounded answer"/);
    assert.doesNotMatch(frame, /tool|prompt|sessionFile|usage/);
    abort.abort();
  });
});

test("read scope and public surface fail closed", async () => {
  const setup = harness({
    revisionClient: {
      async getRun() {
        return runDetail("55555555-5555-4555-8555-555555555555");
      },
    },
  });
  await withServer(setup, async (baseUrl) => {
    const context = await fetch(`${baseUrl}/api/v1/context`);
    assert.deepEqual(await context.json(), {
      sessionId: SESSION_ID,
      projectId: PROJECT_ID,
      activityId: ACTIVITY_ID,
      activeWorkbenchId: "canvas",
      isStreaming: false,
    });
    const crossed = await fetch(`${baseUrl}/api/v1/runs/${RUN_ID}`);
    assert.equal(crossed.status, 404);
    assert.deepEqual(await crossed.json(), { error: "resource_not_found" });
    for (const path of ["commands", "artifact-blobs", "jobs", "logs", "pi-state"]) {
      const response = await fetch(`${baseUrl}/api/v1/${path}`);
      assert.equal(response.status, 404);
    }
  });
});

test("source bytes require both revision-file membership and verified artifact scope", async () => {
  const source = new TextEncoder().encode("def on_start():\n    return []\n");
  const setup = harness({
    revisionClient: {
      async getRevision(_projectId, revisionId) {
        return {
          ...revision(revisionId),
          files: [{
            path: "strategy.py",
            artifact_id: SOURCE_ARTIFACT_ID,
            git_blob_oid: "c".repeat(40),
            sha256: "d".repeat(64),
            byte_size: source.byteLength,
            media_type: "text/plain",
            storage_uri: `cas://sha256/${"d".repeat(64)}`,
          }],
        };
      },
      async getArtifact() {
        return {
          artifact_id: SOURCE_ARTIFACT_ID,
          project_id: PROJECT_ID,
          media_type: "text/plain",
          revision_paths: [{ revision_id: VARIANT_REVISION_ID, path: "strategy.py" }],
        };
      },
      async getArtifactContent() {
        return source;
      },
    },
  });
  await withServer(setup, async (baseUrl) => {
    const allowed = await fetch(
      `${baseUrl}/api/v1/revisions/${VARIANT_REVISION_ID}/files/${SOURCE_ARTIFACT_ID}/content`,
    );
    assert.equal(allowed.status, 200);
    assert.equal(await allowed.text(), "def on_start():\n    return []\n");

    const crossed = await fetch(
      `${baseUrl}/api/v1/revisions/${CANDIDATE_REVISION_ID}/files/${SOURCE_ARTIFACT_ID}/content`,
    );
    assert.equal(crossed.status, 404);
    assert.deepEqual(await crossed.json(), { error: "resource_not_found" });
  });
});
