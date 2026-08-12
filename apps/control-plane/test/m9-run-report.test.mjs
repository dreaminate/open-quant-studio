import assert from "node:assert/strict";
import { once } from "node:events";
import { resolve } from "node:path";
import test from "node:test";

import {
  createOqsBrowserServer,
  loadM4FormalRunFixture,
} from "../dist/browser-server.js";

const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const SESSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const RUN_ID = "72727272-7272-4272-8272-727272727272";
const JSON_ARTIFACT_ID = "73737373-7373-4373-8373-737373737373";
const HTML_ARTIFACT_ID = "74747474-7474-4474-8474-747474747474";
const JSON_BYTES = new TextEncoder().encode("{\"report_version\":\"m9-v1\"}");
const HTML_BYTES = new TextEncoder().encode("<!doctype html><title>OQS report</title>");
const report = {
  report_version: "m9-v1",
  run: {
    run_id: RUN_ID,
    run_spec_id: "75757575-7575-4575-8575-757575757575",
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    variant_id: "76767676-7676-4676-8676-767676767676",
    candidate_revision_id: "77777777-7777-4777-8777-777777777777",
    status: "succeeded",
    calculation_hash: "a".repeat(64),
    finished_at: "2026-08-12T00:05:00Z",
  },
  identities: {
    engine_result_sha256: "b".repeat(64),
    engine_version: "oqs-quant-engine/0.2.0",
    engine_schema_version: 2,
    account_model: "cash",
    data_snapshot_id: "78787878-7878-4787-8787-787878787878",
    data_snapshot_sha256: "c".repeat(64),
    strategy_tree_oid: "d".repeat(40),
    parameters_sha256: "e".repeat(64),
    cost_model_sha256: "f".repeat(64),
    environment_lock_sha256: "0".repeat(64),
    price_basis: "raw",
    cutoff: "2026-12-31T23:59:59Z",
    timezone: "UTC",
    sample_start: "2026-01-01T00:00:00Z",
    sample_end: "2026-01-02T00:00:00Z",
  },
  period: { start_at: "2026-01-01T00:00:00Z", end_at: "2026-01-02T00:00:00Z", session_count: 2 },
  summary: {
    starting_equity_atoms: "10000",
    ending_equity_atoms: "10100",
    net_pnl_atoms: "100",
    total_return_rate_atoms: "10000",
    max_drawdown_atoms: "-25",
    max_drawdown_rate_atoms: "-2500",
    gross_exposure_atoms: "500",
    net_exposure_atoms: "500",
    total_fees_atoms: "5",
    total_stamp_duty_atoms: "0",
    total_funding_atoms: "0",
    total_slippage_atoms: "1",
    order_count: 1,
    fill_count: 1,
    closed_trade_count: 0,
    open_position_count: 1,
  },
  reconciliation: { passed: true, checks: [{ field: "ending_equity_atoms", expected: "10100", actual: "10100", passed: true }] },
  definitions: [],
  source: { engine_result_artifact_id: "b".repeat(36), manifest_artifact_id: "c".repeat(36) },
};
const jsonArtifact = {
  artifact_id: JSON_ARTIFACT_ID,
  sha256: "1".repeat(64),
  media_type: "application/json",
  byte_size: JSON_BYTES.byteLength,
  storage_uri: "cas://sha256/" + "1".repeat(64),
};
const htmlArtifact = {
  artifact_id: HTML_ARTIFACT_ID,
  sha256: "2".repeat(64),
  media_type: "application/vnd.open-quant-studio.run-report+html",
  byte_size: HTML_BYTES.byteLength,
  storage_uri: "cas://sha256/" + "2".repeat(64),
};
const FIXTURE = await loadM4FormalRunFixture(resolve(
  import.meta.dirname,
  "../../../fixtures/backtests/m3-a-share-long-short-v1.json",
));

test("browser facade serves the deterministic Run report and downloads", async () => {
  const server = createOqsBrowserServer({
    activeSessionId: SESSION_ID,
    registry: {
      status(sessionId) {
        return sessionId === SESSION_ID
          ? { sessionId, projectId: PROJECT_ID, activityId: ACTIVITY_ID, activeWorkbenchId: "run-detail", isStreaming: false }
          : undefined;
      },
      get() { return undefined; },
    },
    revisionClient: {
      async getRunReport(projectId, runId) {
        assert.equal(projectId, PROJECT_ID);
        assert.equal(runId, RUN_ID);
        return { report, json_artifact: jsonArtifact, html_artifact: htmlArtifact };
      },
      async getArtifact(projectId, artifactId) {
        const pointer = artifactId === JSON_ARTIFACT_ID ? jsonArtifact : htmlArtifact;
        return { ...pointer, project_id: projectId, revision_paths: [] };
      },
      async getArtifactContent(projectId, artifact) {
        assert.equal(projectId, PROJECT_ID);
        return artifact.artifact_id === JSON_ARTIFACT_ID ? JSON_BYTES : HTML_BYTES;
      },
    },
    formalRunFixture: FIXTURE,
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  const baseUrl = `http://127.0.0.1:${address.port}`;
  try {
    const modelResponse = await fetch(`${baseUrl}/api/v1/runs/${RUN_ID}/report`);
    assert.equal(modelResponse.status, 200);
    assert.deepEqual(await modelResponse.json(), { report, json_artifact: jsonArtifact, html_artifact: htmlArtifact });

    const jsonResponse = await fetch(`${baseUrl}/api/v1/runs/${RUN_ID}/report.json`);
    assert.equal(jsonResponse.status, 200);
    assert.equal(jsonResponse.headers.get("content-type"), "application/json");
    assert.equal(jsonResponse.headers.get("content-disposition"), `attachment; filename="${RUN_ID}.report.json"`);
    assert.deepEqual(new Uint8Array(await jsonResponse.arrayBuffer()), JSON_BYTES);

    const htmlResponse = await fetch(`${baseUrl}/api/v1/runs/${RUN_ID}/report.html`);
    assert.equal(htmlResponse.status, 200);
    assert.equal(htmlResponse.headers.get("content-type"), "application/vnd.open-quant-studio.run-report+html");
    assert.equal(htmlResponse.headers.get("content-disposition"), `attachment; filename="${RUN_ID}.report.html"`);
    assert.deepEqual(new Uint8Array(await htmlResponse.arrayBuffer()), HTML_BYTES);
  } finally {
    server.close();
    await once(server, "close");
  }
});
