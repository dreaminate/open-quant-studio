import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { once } from "node:events";
import { resolve } from "node:path";
import test from "node:test";

import {
  createOqsBrowserServer,
  loadM4FormalRunFixture,
} from "../dist/browser-server.js";
import { FetchQuantDomainRevisionClient } from "../dist/domain-revision-client.js";

const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const SESSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const VARIANT_ID = "55555555-5555-4555-8555-555555555555";
const CANDIDATE_REVISION_ID = "77777777-7777-4777-8777-777777777777";
const SNAPSHOT_ID = "23232323-2323-4232-8232-232323232323";
const SOURCE_ARTIFACT_ID = "24242424-2424-4242-8242-242424242424";
const NORMALIZED_ARTIFACT_ID = "25252525-2525-4252-8252-252525252525";
const MARKET_INPUT_ARTIFACT_ID = "26262626-2626-4262-8262-262626262626";
const SOURCE_REF = "27272727-2727-4272-8272-272727272727";
const RUN_ID = "18181818-1818-4181-8181-181818181818";
const CSV_BODY = new TextEncoder().encode(
  "date,ticker,open,high,low,close,vol\n2026-01-02,600519.SH,1500,1510,1490,1505,1000\n",
);
const MARKET_INPUT_JSON = JSON.stringify({ market: "a_share_daily", bars: [] });
const MARKET_INPUT_SHA256 = createHash("sha256").update(MARKET_INPUT_JSON).digest("hex");
const SOURCE_SHA256 = createHash("sha256").update(CSV_BODY).digest("hex");
const FIXTURE_PATH = resolve(
  import.meta.dirname,
  "../../../fixtures/backtests/m3-a-share-long-short-v1.json",
);
const FIXTURE = await loadM4FormalRunFixture(FIXTURE_PATH);

const MAPPING = {
  timestamp: "date",
  symbol: "ticker",
  open: "open",
  high: "high",
  low: "low",
  close: "close",
  volume: "vol",
};

const SOURCE = {
  artifact_id: SOURCE_ARTIFACT_ID,
  sha256: SOURCE_SHA256,
  media_type: "text/csv",
  byte_size: CSV_BODY.byteLength,
  storage_uri: `cas://sha256/${SOURCE_SHA256}`,
  producing_revision_id: null,
  producing_run_id: null,
  provenance: { origin_kind: "user_upload", source_ref: SOURCE_REF },
};

const PREVIEW = {
  source: SOURCE,
  source_format: "csv",
  file_name: "a-share.csv",
  columns: ["date", "ticker", "open", "high", "low", "close", "vol"],
  suggested_mapping: MAPPING,
  preview_rows: [{
    date: "2026-01-02",
    ticker: "600519.SH",
    open: "1500",
    high: "1510",
    low: "1490",
    close: "1505",
    vol: "1000",
  }],
  total_rows: 1,
};

const SNAPSHOT = {
  snapshot_id: SNAPSHOT_ID,
  source_artifact_id: SOURCE_ARTIFACT_ID,
  normalized_artifact_id: NORMALIZED_ARTIFACT_ID,
  market_input_artifact_id: MARKET_INPUT_ARTIFACT_ID,
  market: "a_share_daily",
  symbol: "600519.SH",
  symbols: ["600519.SH"],
  timezone: "Asia/Shanghai",
  price_basis: "raw",
  cutoff: "2026-12-31T23:59:59Z",
  schema_version: 1,
  sample_start: "2026-01-02T00:00:00Z",
  sample_end: "2026-01-02T23:59:59Z",
  row_count: 1,
  session_count: 1,
  sha256: "c".repeat(64),
  created_at: "2026-08-12T00:00:00Z",
  project_id: PROJECT_ID,
  mapping: MAPPING,
  source_sha256: SOURCE_SHA256,
  normalized_sha256: "d".repeat(64),
  market_input_sha256: MARKET_INPUT_SHA256,
};

function acceptedReceipt(commandId = "51515151-5151-4151-8151-515151515151") {
  return {
    command_id: commandId,
    disposition: "accepted",
    event: { event_type: "test", payload: { snapshot_id: SNAPSHOT_ID, run_id: RUN_ID } },
  };
}

function browserHarness() {
  const calls = [];
  const registry = {
    status(sessionId) {
      return sessionId === SESSION_ID
        ? {
            sessionId,
            projectId: PROJECT_ID,
            activityId: ACTIVITY_ID,
            activeWorkbenchId: "data",
            isStreaming: false,
          }
        : undefined;
    },
    get() { return undefined; },
  };
  const revisionClient = {
    async previewDataImport(projectId, fileName, sourceFormat, body) {
      calls.push(["upload-preview", projectId, fileName, sourceFormat, body]);
      return PREVIEW;
    },
    async listLocalDataImports(projectId) {
      calls.push(["local-files", projectId]);
      return [{ file_name: "a-share.csv", source_format: "csv", byte_size: CSV_BODY.byteLength }];
    },
    async previewLocalDataImport(projectId, fileName) {
      calls.push(["local-preview", projectId, fileName]);
      return PREVIEW;
    },
    async listDataSnapshots(projectId) {
      calls.push(["snapshot-list", projectId]);
      return { snapshots: [SNAPSHOT] };
    },
    async getDataSnapshot(projectId, snapshotId) {
      calls.push(["snapshot-detail", projectId, snapshotId]);
      return SNAPSHOT;
    },
    async getDataSnapshotMarketInput(projectId, snapshot) {
      calls.push(["market-input", projectId, snapshot.snapshot_id]);
      return MARKET_INPUT_JSON;
    },
    async createDataSnapshot(request) {
      calls.push(["snapshot-create", request]);
      return acceptedReceipt();
    },
    async getRevision(projectId, revisionId) {
      calls.push(["revision", projectId, revisionId]);
      return {
        revision_id: CANDIDATE_REVISION_ID,
        project_id: PROJECT_ID,
        activity_id: ACTIVITY_ID,
        variant_id: VARIANT_ID,
        git_tree_oid: "b".repeat(40),
        files: [],
      };
    },
    async requestFormalRun(request) {
      calls.push(["formal", request]);
      return acceptedReceipt();
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
  try {
    await run(`http://127.0.0.1:${address.port}`);
  } finally {
    setup.server.close();
    await once(setup.server, "close");
  }
}

test("browser facade completes upload/local preview, snapshot creation, and selected-snapshot Formal Run", async () => {
  const setup = browserHarness();
  await withServer(setup, async (baseUrl) => {
    const uploaded = await fetch(
      `${baseUrl}/api/v1/data-imports/preview?file_name=a-share.csv&source_format=csv`,
      { method: "POST", headers: { "Content-Type": "text/csv" }, body: CSV_BODY },
    );
    assert.equal(uploaded.status, 200);
    assert.deepEqual(await uploaded.json(), PREVIEW);
    assert.deepEqual(setup.calls[0], [
      "upload-preview",
      PROJECT_ID,
      "a-share.csv",
      "csv",
      CSV_BODY,
    ]);

    const localFiles = await fetch(`${baseUrl}/api/v1/data-imports/local-files`);
    assert.equal(localFiles.status, 200);
    assert.deepEqual(await localFiles.json(), {
      files: [{ file_name: "a-share.csv", source_format: "csv", byte_size: CSV_BODY.byteLength }],
    });
    const localPreview = await fetch(`${baseUrl}/api/v1/data-imports/local-preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_name: "a-share.csv" }),
    });
    assert.equal(localPreview.status, 200);
    assert.deepEqual(await localPreview.json(), PREVIEW);

    const createBody = {
      source: SOURCE,
      source_format: "csv",
      file_name: "a-share.csv",
      mapping: MAPPING,
      market: "a_share_daily",
      timezone: "Asia/Shanghai",
      price_basis: "raw",
      cutoff: "2026-12-31T23:59:59Z",
    };
    const created = await fetch(`${baseUrl}/api/v1/data-snapshots`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(createBody),
    });
    assert.equal(created.status, 200);
    assert.deepEqual(setup.calls.find(([kind]) => kind === "snapshot-create"), ["snapshot-create", {
      projectId: PROJECT_ID,
      activityId: ACTIVITY_ID,
      sessionId: SESSION_ID,
      workbenchId: "data",
      source: SOURCE,
      sourceFormat: "csv",
      fileName: "a-share.csv",
      mapping: MAPPING,
      market: "a_share_daily",
      timezone: "Asia/Shanghai",
      priceBasis: "raw",
      cutoff: "2026-12-31T23:59:59Z",
    }]);

    const listed = await fetch(`${baseUrl}/api/v1/data-snapshots`);
    assert.deepEqual(await listed.json(), { snapshots: [SNAPSHOT] });
    const detailed = await fetch(`${baseUrl}/api/v1/data-snapshots/${SNAPSHOT_ID}`);
    assert.deepEqual(await detailed.json(), SNAPSHOT);

    const formal = await fetch(
      `${baseUrl}/api/v1/revisions/${CANDIDATE_REVISION_ID}/runs`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data_snapshot_id: SNAPSHOT_ID }),
      },
    );
    assert.equal(formal.status, 200);
    assert.deepEqual(setup.calls.at(-1), ["formal", {
      projectId: PROJECT_ID,
      activityId: ACTIVITY_ID,
      sessionId: SESSION_ID,
      workbenchId: "data",
      candidateRevisionId: CANDIDATE_REVISION_ID,
      variantId: VARIANT_ID,
      strategyTreeOid: "b".repeat(40),
      marketInputJson: MARKET_INPUT_JSON,
      dataSnapshotId: SNAPSHOT_ID,
      dataSnapshotSha256: SNAPSHOT.sha256,
      parametersSha256: FIXTURE.parametersSha256,
      costModelSha256: FIXTURE.costModelSha256,
      environmentLockSha256: FIXTURE.environmentLockSha256,
      priceBasis: SNAPSHOT.price_basis,
      cutoff: SNAPSHOT.cutoff,
      timezone: SNAPSHOT.timezone,
      sampleStart: SNAPSHOT.sample_start,
      sampleEnd: SNAPSHOT.sample_end,
      randomSeed: FIXTURE.randomSeed,
      marketInputOriginKind: "service_generated",
      marketInputSourceRef: MARKET_INPUT_ARTIFACT_ID,
    }]);
  });
});

test("typed M7 client maps domain import/snapshot routes and creates the exact typed command", async () => {
  const requests = [];
  const commands = [];
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
    requests.push({ url, init });
    if (url.includes("/data-imports/preview?")) return Response.json(PREVIEW);
    if (url.endsWith("/data-imports/local-files")) {
      return Response.json({ files: [{ file_name: "a-share.csv", source_format: "csv", byte_size: CSV_BODY.byteLength }] });
    }
    if (url.endsWith("/data-imports/local-preview")) return Response.json(PREVIEW);
    if (url.endsWith(`/data-snapshots/${SNAPSHOT_ID}/market-input`)) {
      return new Response(MARKET_INPUT_JSON, { headers: { "Content-Type": "application/json" } });
    }
    if (url.endsWith(`/data-snapshots/${SNAPSHOT_ID}`)) return Response.json(SNAPSHOT);
    if (url.endsWith("/data-snapshots")) return Response.json({ snapshots: [SNAPSHOT] });
    throw new Error(`unexpected request ${url}`);
  });

  assert.deepEqual(
    await client.previewDataImport(PROJECT_ID, "a-share.csv", "csv", CSV_BODY),
    PREVIEW,
  );
  assert.equal(requests[0].init.method, "POST");
  assert.equal(requests[0].init.headers["Content-Type"], "text/csv");
  assert.deepEqual(requests[0].init.body, CSV_BODY);
  assert.deepEqual(await client.listLocalDataImports(PROJECT_ID), [
    { file_name: "a-share.csv", source_format: "csv", byte_size: CSV_BODY.byteLength },
  ]);
  assert.deepEqual(await client.previewLocalDataImport(PROJECT_ID, "a-share.csv"), PREVIEW);
  assert.equal(requests[2].init.body, JSON.stringify({ file_name: "a-share.csv" }));
  assert.deepEqual(await client.listDataSnapshots(PROJECT_ID), { snapshots: [SNAPSHOT] });
  assert.deepEqual(await client.getDataSnapshot(PROJECT_ID, SNAPSHOT_ID), SNAPSHOT);
  assert.equal(
    await client.getDataSnapshotMarketInput(PROJECT_ID, SNAPSHOT),
    MARKET_INPUT_JSON,
  );

  await client.createDataSnapshot({
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    sessionId: SESSION_ID,
    workbenchId: "data",
    commandId: "51515151-5151-4151-8151-515151515151",
    correlationId: "45454545-4545-4545-8545-454545454545",
    snapshotId: SNAPSHOT_ID,
    source: SOURCE,
    sourceFormat: "csv",
    fileName: "a-share.csv",
    mapping: MAPPING,
    market: "a_share_daily",
    timezone: "Asia/Shanghai",
    priceBasis: "raw",
    cutoff: "2026-12-31T23:59:59Z",
  });
  assert.deepEqual(commands[0], {
    command_id: "51515151-5151-4151-8151-515151515151",
    schema_version: 1,
    command_type: "data.snapshot_create",
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    session_id: SESSION_ID,
    workbench_id: "data",
    correlation_id: "45454545-4545-4545-8545-454545454545",
    expected_revision_id: null,
    variant_id: null,
    base_revision_id: null,
    payload: {
      snapshot_id: SNAPSHOT_ID,
      source: SOURCE,
      source_format: "csv",
      file_name: "a-share.csv",
      mapping: MAPPING,
      market: "a_share_daily",
      timezone: "Asia/Shanghai",
      price_basis: "raw",
      cutoff: "2026-12-31T23:59:59Z",
    },
  });
});
