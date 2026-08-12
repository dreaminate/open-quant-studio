import { expect, test } from "@playwright/test";
import { runReportFixture } from "./run-report-fixture";

const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const VARIANT_ID = "20202020-2020-4020-8020-202020202020";
const REVISION_ID = "30303030-3030-4030-8030-303030303030";
const SNAPSHOT_ID = "23232323-2323-4232-8232-232323232323";
const SOURCE_ARTIFACT_ID = "24242424-2424-4242-8242-242424242424";
const RUN_ID = "72727272-7272-4272-8272-727272727272";
const ARTIFACT_ID = "75757575-7575-4575-8575-757575757575";
const SOURCE_SHA256 = "a".repeat(64);
const CSV_BODY = [
  "date,ticker,open,high,low,close,vol",
  "2026-01-02,600519.SH,1500.1000,1510.2000,1490.0000,1505.5000,1000",
  "2026-01-05,600519.SH,1505.5000,1512.0000,1500.0000,1510.0000,1200",
  "",
].join("\n");
const STRATEGY_SOURCE = "def on_bar(bar):\n    return []\n";
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
  byte_size: Buffer.byteLength(CSV_BODY),
  storage_uri: `cas://sha256/${SOURCE_SHA256}`,
  producing_revision_id: null,
  producing_run_id: null,
  provenance: {
    origin_kind: "user_upload",
    source_ref: "27272727-2727-4272-8272-272727272727",
  },
};
const PREVIEW = {
  source: SOURCE,
  source_format: "csv",
  file_name: "a-share.csv",
  columns: ["date", "ticker", "open", "high", "low", "close", "vol"],
  suggested_mapping: MAPPING,
  preview_rows: [
    { date: "2026-01-02", ticker: "600519.SH", open: "1500.1000", high: "1510.2000", low: "1490.0000", close: "1505.5000", vol: "1000" },
    { date: "2026-01-05", ticker: "600519.SH", open: "1505.5000", high: "1512.0000", low: "1500.0000", close: "1510.0000", vol: "1200" },
  ],
  total_rows: 2,
};
const SNAPSHOT = {
  snapshot_id: SNAPSHOT_ID,
  source_artifact_id: SOURCE_ARTIFACT_ID,
  normalized_artifact_id: "25252525-2525-4252-8252-252525252525",
  market_input_artifact_id: "26262626-2626-4262-8262-262626262626",
  market: "a_share_daily",
  symbol: "600519.SH",
  timezone: "Asia/Shanghai",
  price_basis: "raw",
  cutoff: "2026-12-31T23:59:59Z",
  schema_version: 1,
  sample_start: "2026-01-02T00:00:00Z",
  sample_end: "2026-01-05T23:59:59Z",
  row_count: 2,
  sha256: "b".repeat(64),
  created_at: "2026-08-12T00:00:00Z",
  project_id: PROJECT_ID,
  mapping: MAPPING,
  source_sha256: SOURCE_SHA256,
  normalized_sha256: "c".repeat(64),
  market_input_sha256: "d".repeat(64),
};

test("M7 Data imports CSV, creates and selects a snapshot, then opens its Formal Run", async ({ page }) => {
  const calls: Array<{ path: string; method: string; body?: string; contentType?: string }> = [];
  let snapshotCreated = false;
  let formalRequested = false;

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    calls.push({
      path: url.pathname,
      method: request.method(),
      body: request.postData() ?? undefined,
      contentType: request.headers()["content-type"],
    });
    if (url.pathname === "/api/v1/context") return route.fulfill({ json: { sessionId: "session-a", projectId: PROJECT_ID, activityId: ACTIVITY_ID, activeWorkbenchId: "canvas", isStreaming: false } });
    if (url.pathname === "/api/v1/projects") return route.fulfill({ json: { projects: [{ project_id: PROJECT_ID, name: "M7 Research", created_at: "2026-08-12T00:00:00Z" }] } });
    if (url.pathname === "/api/v1/activities") return route.fulfill({ json: { activities: [{ activity_id: ACTIVITY_ID, project_id: PROJECT_ID, name: "Data import", created_at: "2026-08-12T00:00:00Z" }] } });
    if (url.pathname === "/api/v1/revision-head") return route.fulfill({ json: { project_id: PROJECT_ID, head_revision_id: REVISION_ID } });
    if (url.pathname === "/api/v1/variants") return route.fulfill({ json: { variants: [{ variant_id: VARIANT_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, head_revision_id: REVISION_ID, version: 1 }] } });
    if (url.pathname === `/api/v1/revisions/${REVISION_ID}`) return route.fulfill({ json: { revision_id: REVISION_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, git_tree_oid: "b".repeat(40), git_commit_oid: "a".repeat(40), files: [{ path: "strategy.py", artifact_id: ARTIFACT_ID, git_blob_oid: "c".repeat(40), sha256: "e".repeat(64), byte_size: STRATEGY_SOURCE.length, media_type: "text/plain", storage_uri: `cas://sha256/${"e".repeat(64)}` }] } });
    if (url.pathname === `/api/v1/revisions/${REVISION_ID}/files/${ARTIFACT_ID}/content`) return route.fulfill({ body: STRATEGY_SOURCE, contentType: "text/plain" });
    if (url.pathname === "/api/v1/data-imports/local-files") return route.fulfill({ json: { files: [{ file_name: "sample.parquet", source_format: "parquet", byte_size: 4096 }] } });
    if (url.pathname === "/api/v1/data-snapshots" && request.method() === "GET") return route.fulfill({ json: { snapshots: snapshotCreated ? [SNAPSHOT] : [] } });
    if (url.pathname === "/api/v1/data-imports/preview" && request.method() === "POST") return route.fulfill({ json: PREVIEW });
    if (url.pathname === "/api/v1/data-snapshots" && request.method() === "POST") {
      snapshotCreated = true;
      return route.fulfill({ json: { disposition: "accepted", event: { payload: { snapshot_id: SNAPSHOT_ID } } } });
    }
    if (url.pathname === "/api/v1/runs") return route.fulfill({ json: { runs: formalRequested ? [{ run_id: RUN_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, candidate_revision_id: REVISION_ID, status: "succeeded", finished_at: "2026-08-12T00:05:00Z" }] : [] } });
    if (url.pathname === `/api/v1/revisions/${REVISION_ID}/runs` && request.method() === "POST") {
      formalRequested = true;
      return route.fulfill({ json: { disposition: "accepted", event: { payload: { run_id: RUN_ID } } } });
    }
    if (url.pathname === `/api/v1/runs/${RUN_ID}`) return route.fulfill({ json: { run: { run_id: RUN_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, candidate_revision_id: REVISION_ID, status: "succeeded" }, validation: { outcome: "passed" }, manifest: { run_spec: { data_snapshot_id: SNAPSHOT_ID, data_snapshot_sha256: SNAPSHOT.sha256 }, gates: { contract: "passed" } }, engine_result: { engine_version: "oqs-quant-engine/0.1.0", metrics: { ending_equity_atoms: "10100" }, orders: [], trades: [], positions: [], cash_ledger: [], funding_ledger: [], equity_curve: [], drawdown_curve: [], costs: {}, assumptions: {} } } });
    if (url.pathname === `/api/v1/runs/${RUN_ID}/report`) return route.fulfill({ json: runReportFixture({ projectId: PROJECT_ID, activityId: ACTIVITY_ID, variantId: VARIANT_ID, revisionId: REVISION_ID, snapshotId: SNAPSHOT_ID, runId: RUN_ID }) });
    return route.fulfill({ status: 404, json: { error: "not_found" } });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Data" }).click();
  await expect(page.getByRole("heading", { name: "CSV or Parquet source" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Import project" })).toBeVisible();
  await expect(page.getByLabel("Local imports file")).toHaveValue("sample.parquet");

  await page.getByLabel("Market data file").setInputFiles({
    name: "a-share.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(CSV_BODY),
  });
  await page.getByRole("button", { name: "Preview upload" }).click();
  await expect(page.getByText("600519.SH", { exact: true }).first()).toBeVisible();
  await expect(page.getByLabel("Timestamp column")).toHaveValue("date");
  await expect(page.getByLabel("Symbol column")).toHaveValue("ticker");

  const previewCall = calls.find((call) => call.path === "/api/v1/data-imports/preview" && call.method === "POST");
  expect(previewCall?.body).toBe(CSV_BODY);
  expect(previewCall?.contentType).toBe("text/csv");

  await page.getByRole("button", { name: "Create immutable snapshot" }).click();
  await expect(page.getByTestId(`snapshot-${SNAPSHOT_ID}`)).toBeVisible();
  const createCall = calls.find((call) => call.path === "/api/v1/data-snapshots" && call.method === "POST");
  expect(JSON.parse(createCall?.body ?? "null")).toEqual({
    source: SOURCE,
    source_format: "csv",
    file_name: "a-share.csv",
    mapping: MAPPING,
    market: "a_share_daily",
    timezone: "Asia/Shanghai",
    price_basis: "raw",
    cutoff: "2026-12-31T23:59:59Z",
  });

  await page.getByRole("button", { name: "Use for Formal Run" }).click();
  await expect(page.getByRole("button", { name: "Selected for Formal Run" })).toBeVisible();
  await page.getByRole("button", { name: "Run formal" }).click();
  const formalCall = calls.find((call) => call.path === `/api/v1/revisions/${REVISION_ID}/runs` && call.method === "POST");
  expect(formalCall?.body).toBe(JSON.stringify({ data_snapshot_id: SNAPSHOT_ID }));

  await expect(page.locator("main h1", { hasText: "Backtest" })).toBeVisible();
  await page.getByRole("button", { name: "View Run Detail", exact: true }).click();
  await expect(page.locator("main h1", { hasText: "Run Detail" })).toBeVisible();
  await expect(page.locator("pre", { hasText: SNAPSHOT_ID }).first()).toBeVisible();
  await expect(page.getByTestId("run-report-ending-equity")).toContainText("10100");
});
