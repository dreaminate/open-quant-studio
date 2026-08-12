import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { once } from "node:events";
import { resolve } from "node:path";
import test from "node:test";

import {
  createOqsBrowserServer,
  loadM4FormalRunFixture,
} from "../dist/browser-server.js";
import {
  FetchQuantDomainRevisionClient,
  PROJECT_ARCHIVE_MEDIA_TYPE,
} from "../dist/domain-revision-client.js";
import { FetchQuantDomainSessionClient } from "../dist/domain-session-client.js";

const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const SESSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const VARIANT_ID = "55555555-5555-4555-8555-555555555555";
const CANDIDATE_REVISION_ID = "77777777-7777-4777-8777-777777777777";
const RUN_ID = "18181818-1818-4181-8181-181818181818";
const FORWARD_TEST_ID = "52525252-5252-4252-8252-525252525252";
const FIXTURE_PATH = resolve(
  import.meta.dirname,
  "../../../fixtures/backtests/m3-a-share-long-short-v1.json",
);
const FIXTURE = await loadM4FormalRunFixture(FIXTURE_PATH);

function forwardTest(forwardTestId = FORWARD_TEST_ID) {
  return {
    forward_test_id: forwardTestId,
    source_run_id: RUN_ID,
    source_revision_id: CANDIDATE_REVISION_ID,
    data_snapshot_id: "23232323-2323-4232-8232-232323232323",
    protocol_version: "oqs-forward-replay/m5-v1",
    released_bar_count: 1024,
    transcript_artifact_id: "54545454-5454-4454-8454-545454545454",
    transcript_sha256: "a".repeat(64),
    intent_tape_sha256: "b".repeat(64),
    status: "passed",
    error_code: null,
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    variant_id: VARIANT_ID,
    created_at: "2026-08-12T02:05:00Z",
  };
}

function acceptedReceipt(commandId = "51515151-5151-4151-8151-515151515151") {
  return {
    command_id: commandId,
    disposition: "accepted",
    event: { event_type: "test" },
  };
}

function browserHarness() {
  const calls = [];
  const adapter = {
    async prompt() {},
    subscribe() {
      return () => {};
    },
  };
  const registry = {
    status(sessionId) {
      return sessionId === SESSION_ID
        ? {
            sessionId,
            projectId: PROJECT_ID,
            activityId: ACTIVITY_ID,
            activeWorkbenchId: "forward-test",
            isStreaming: false,
          }
        : undefined;
    },
    get(sessionId) {
      return sessionId === SESSION_ID ? adapter : undefined;
    },
  };
  const revisionClient = {
    async listProjects() { return { projects: [] }; },
    async listActivities() { return { activities: [] }; },
    async getProjectRevisionHead() {
      return { project_id: PROJECT_ID, head_revision_id: CANDIDATE_REVISION_ID };
    },
    async listVariants() { return []; },
    async getRevision() { throw new Error("not used"); },
    async compareRevisions() { throw new Error("not used"); },
    async listRuns() { return { runs: [] }; },
    async getRun() {
      return {
        run: {
          run_id: RUN_ID,
          project_id: PROJECT_ID,
          activity_id: ACTIVITY_ID,
          variant_id: VARIANT_ID,
          candidate_revision_id: CANDIDATE_REVISION_ID,
          status: "succeeded",
        },
      };
    },
    async createStrategyVariant() { throw new Error("not used"); },
    async createRevisionChild() { throw new Error("not used"); },
    async createMergeCandidate() { throw new Error("not used"); },
    async requestFormalRun() { throw new Error("not used"); },
    async promoteRevision() { throw new Error("not used"); },
    async requestForwardTest(request) {
      calls.push(["forward-request", request]);
      return acceptedReceipt();
    },
    async getForwardTest(_projectId, forwardTestId) {
      calls.push(["forward-read", forwardTestId]);
      return forwardTest(forwardTestId);
    },
    async getProjectArchive(projectId, selectedLogs) {
      calls.push(["archive-export", projectId, selectedLogs]);
      return new TextEncoder().encode("oqs project archive");
    },
    async importProjectArchive(request) {
      calls.push(["archive-import", request]);
      return acceptedReceipt("46464646-4646-4646-8646-464646464646");
    },
  };
  return {
    calls,
    server: createOqsBrowserServer({
      activeSessionId: SESSION_ID,
      registry,
      revisionClient,
      formalRunFixture: FIXTURE,
    }),
  };
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

test("browser facade completes Forward Test and project archive user flows", async () => {
  const setup = browserHarness();
  await withServer(setup, async (baseUrl) => {
    const requested = await fetch(`${baseUrl}/api/v1/runs/${RUN_ID}/forward-tests`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    assert.equal(requested.status, 200);
    assert.equal(setup.calls[0][0], "forward-request");
    assert.deepEqual(setup.calls[0][1], {
      projectId: PROJECT_ID,
      activityId: ACTIVITY_ID,
      sessionId: SESSION_ID,
      workbenchId: "forward-test",
      sourceRunId: RUN_ID,
      sourceRevisionId: CANDIDATE_REVISION_ID,
      variantId: VARIANT_ID,
    });

    const viewed = await fetch(`${baseUrl}/api/v1/forward-tests/${FORWARD_TEST_ID}`);
    assert.equal(viewed.status, 200);
    assert.deepEqual(await viewed.json(), forwardTest());

    const exported = await fetch(
      `${baseUrl}/api/v1/projects/${PROJECT_ID}/archive?selected_logs=warn_error`,
    );
    assert.equal(exported.status, 200);
    assert.equal(exported.headers.get("content-type"), PROJECT_ARCHIVE_MEDIA_TYPE);
    assert.equal(await exported.text(), "oqs project archive");
    assert.deepEqual(setup.calls[2], ["archive-export", PROJECT_ID, "warn_error"]);

    const archive = new Uint8Array([0x50, 0x4b, 0x03, 0x04]);
    const imported = await fetch(`${baseUrl}/api/v1/project-archives/import`, {
      method: "POST",
      headers: { "Content-Type": PROJECT_ARCHIVE_MEDIA_TYPE },
      body: archive,
    });
    assert.equal(imported.status, 200);
    assert.equal(setup.calls[3][0], "archive-import");
    assert.deepEqual(setup.calls[3][1], {
      projectId: PROJECT_ID,
      activityId: ACTIVITY_ID,
      sessionId: SESSION_ID,
      workbenchId: "forward-test",
      archive,
    });
  });
});

test("session client accepts a project archive import receipt", async () => {
  const command = {
    command_id: "46464646-4646-4646-8646-464646464646",
    schema_version: 1,
    command_type: "project.archive_import",
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    session_id: SESSION_ID,
    workbench_id: "projects",
    correlation_id: "44444444-4444-4444-8444-444444444444",
    expected_revision_id: null,
    variant_id: null,
    base_revision_id: null,
    payload: {
      expected_project_id: PROJECT_ID,
      archive: {
        artifact_id: "47474747-4747-4747-8747-474747474747",
        sha256: "e".repeat(64),
        media_type: PROJECT_ARCHIVE_MEDIA_TYPE,
        byte_size: 8192,
        storage_uri: `cas://sha256/${"e".repeat(64)}`,
        producing_revision_id: null,
        producing_run_id: null,
        provenance: {
          origin_kind: "user_upload",
          source_ref: "49494949-4949-4949-8949-494949494949",
        },
      },
    },
  };
  const client = new FetchQuantDomainSessionClient(
    "http://quant-domain.test",
    async () => Response.json({
      command_id: command.command_id,
      disposition: "accepted",
      event: {
        event_id: "48484848-4848-4848-8848-484848484848",
        stream_seq: 18,
        schema_version: 1,
        event_type: "project.archive_imported",
        project_id: command.project_id,
        activity_id: command.activity_id,
        session_id: command.session_id,
        workbench_id: command.workbench_id,
        correlation_id: command.correlation_id,
        causation_id: command.command_id,
        recorded_at: "2026-08-12T02:04:00Z",
        variant_id: null,
        base_revision_id: null,
        payload: {
          archive_artifact_id: command.payload.archive.artifact_id,
          archive_sha256: command.payload.archive.sha256,
          manifest_sha256: "f".repeat(64),
          restored_project_id: command.project_id,
          run_count: 1,
          artifact_count: 1,
          git_ref_count: 1,
        },
      },
    }),
  );

  const receipt = await client.postCommand(command);

  assert.equal(receipt.event.event_type, "project.archive_imported");
});

test("typed M5 client stages archive bytes and maps domain Forward Test and archive routes", async () => {
  const commands = [];
  const staged = [];
  const archive = new Uint8Array([0x50, 0x4b, 0x03, 0x04]);
  const archiveSha256 = createHash("sha256").update(archive).digest("hex");
  const sessionClient = {
    baseUrl: "http://quant-domain.test",
    async stageText() { throw new Error("not used"); },
    async stageJson() { throw new Error("not used"); },
    async postCommand(command) {
      commands.push(command);
      return acceptedReceipt(command.command_id);
    },
  };
  const client = new FetchQuantDomainRevisionClient(sessionClient, async (input, init = {}) => {
    const url = String(input);
    if (init.method === "PUT") {
      staged.push({ url, init });
      return Response.json({
        sha256: archiveSha256,
        byte_size: archive.byteLength,
        storage_uri: `cas://sha256/${archiveSha256}`,
      });
    }
    if (url.endsWith(`/v1/projects/${PROJECT_ID}/forward-tests/${FORWARD_TEST_ID}`)) {
      return Response.json(forwardTest());
    }
    if (url.endsWith(`/v1/projects/${PROJECT_ID}/archive?selected_logs=none`)) {
      return new Response(archive, {
        headers: { "Content-Type": PROJECT_ARCHIVE_MEDIA_TYPE },
      });
    }
    throw new Error(`unexpected request ${url}`);
  });

  await client.requestForwardTest({
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    sessionId: SESSION_ID,
    workbenchId: "forward-test",
    sourceRunId: RUN_ID,
    sourceRevisionId: CANDIDATE_REVISION_ID,
    variantId: VARIANT_ID,
    commandId: "51515151-5151-4151-8151-515151515151",
  });
  await client.importProjectArchive({
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    sessionId: SESSION_ID,
    workbenchId: "projects",
    archive,
    commandId: "46464646-4646-4646-8646-464646464646",
  });

  assert.equal(commands[0].command_type, "forward_test.request");
  assert.equal(commands[0].expected_revision_id, CANDIDATE_REVISION_ID);
  assert.equal(commands[0].base_revision_id, CANDIDATE_REVISION_ID);
  assert.match(
    commands[0].payload.forward_test_id,
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
  );
  assert.equal(commands[0].payload.source_run_id, RUN_ID);
  assert.equal(commands[0].payload.protocol_version, "oqs-forward-replay/m5-v1");
  assert.equal(commands[1].command_type, "project.archive_import");
  assert.equal(commands[1].payload.expected_project_id, PROJECT_ID);
  assert.equal(commands[1].payload.archive.media_type, PROJECT_ARCHIVE_MEDIA_TYPE);
  assert.equal(commands[1].payload.archive.sha256, archiveSha256);
  assert.equal(commands[1].payload.archive.byte_size, archive.byteLength);
  assert.equal(staged.length, 1);
  assert.equal(staged[0].url, `http://quant-domain.test/v1/artifact-blobs/${archiveSha256}`);
  assert.equal(staged[0].init.headers["Content-Type"], PROJECT_ARCHIVE_MEDIA_TYPE);
  assert.deepEqual(new Uint8Array(staged[0].init.body), archive);

  assert.deepEqual(await client.getForwardTest(PROJECT_ID, FORWARD_TEST_ID), forwardTest());
  assert.deepEqual(await client.getProjectArchive(PROJECT_ID, "none"), archive);
});
