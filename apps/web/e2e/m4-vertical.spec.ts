import { test, expect } from "@playwright/test";

const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const VARIANT_ID = "20202020-2020-4020-8020-202020202020";
const REVISION_ID = "30303030-3030-4030-8030-303030303030";
const CHILD_REVISION_ID = "40404040-4040-4040-8040-404040404040";
const CANDIDATE_REVISION_ID = "50505050-5050-4050-8050-505050505050";
const RUN_ID = "72727272-7272-4272-8272-727272727272";
const WARN_LOG_ID = "82828282-8282-4282-8282-828282828282";
const INFO_LOG_ID = "83838383-8383-4383-8383-838383838383";
const ERROR_LOG_ID = "84848484-8484-4484-8484-848484848484";
const FORWARD_TEST_ID = "52525252-5252-4252-8252-525252525252";
const ARTIFACT_ID = "75757575-7575-4575-8575-757575757575";
const DATA_SNAPSHOT_ID = "62626262-6262-4262-8262-626262626262";
const DATA_SOURCE_ARTIFACT_ID = "63636363-6363-4363-8363-636363636363";
const STRATEGY_SOURCE = "def on_bar(bar):\n    return []\n";
const PROJECT_ARCHIVE_MEDIA_TYPE = "application/vnd.open-quant-studio.project-archive+zip";

test("M4 desktop vertical uses one SPA from canvas to Run Detail and promote", async ({ page }) => {
  const calls: Array<{ path: string; search: string; method: string; body?: string; contentType?: string }> = [];
  let formalRequested = false;
  let snapshotCreated = false;
  let runDetailAttempts = 0;
  const mapping = { timestamp: "timestamp", symbol: "symbol", open: "open", high: "high", low: "low", close: "close", volume: "volume" };
  const source = { artifact_id: DATA_SOURCE_ARTIFACT_ID, sha256: "a".repeat(64), media_type: "text/csv", byte_size: 256, storage_uri: `cas://sha256/${"a".repeat(64)}`, producing_revision_id: null, producing_run_id: null, provenance: { origin_kind: "user_upload", source_ref: "m7-a-share-daily.csv" } };
  const snapshot = { snapshot_id: DATA_SNAPSHOT_ID, source_artifact_id: DATA_SOURCE_ARTIFACT_ID, normalized_artifact_id: "66666666-6666-4666-8666-666666666666", market_input_artifact_id: "67676767-6767-4767-8767-676767676767", market: "a_share_daily", symbol: "SYNTH.XSHG", timezone: "Asia/Shanghai", price_basis: "raw", cutoff: "2026-12-31T23:59:59Z", schema_version: 1, sample_start: "2026-01-02T07:00:00Z", sample_end: "2026-01-13T07:00:00Z", row_count: 8, sha256: "b".repeat(64), created_at: "2026-08-12T08:00:00Z", project_id: PROJECT_ID, mapping, source_sha256: "a".repeat(64), normalized_sha256: "c".repeat(64), market_input_sha256: "d".repeat(64) };
  let diagnosticLogs = [
    { log_id: WARN_LOG_ID, log_seq: 1, run_id: RUN_ID, level: "warn", priority: "p1", event_code: "m5.delete.witness", message: "deletion witness", timestamp: "2026-08-12T00:00:00Z" },
    { log_id: INFO_LOG_ID, log_seq: 2, run_id: RUN_ID, level: "info", priority: "p3", event_code: "m5.routine", message: "routine record", timestamp: "2026-08-12T00:01:00Z" },
    { log_id: ERROR_LOG_ID, log_seq: 3, run_id: RUN_ID, level: "error", priority: "p2", event_code: "m5.retry", message: "retry record", timestamp: "2026-08-12T00:02:00Z" },
  ];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    calls.push({ path: url.pathname, search: url.search, method: request.method(), body: request.postData() ?? undefined, contentType: request.headers()["content-type"] });
    if (url.pathname === "/api/v1/context") return route.fulfill({ json: { sessionId: "session-a", projectId: PROJECT_ID, activityId: ACTIVITY_ID, activeWorkbenchId: "canvas", isStreaming: false } });
    if (url.pathname === "/api/v1/projects") return route.fulfill({ json: { projects: [{ project_id: PROJECT_ID, name: "M4 Research", created_at: "2026-08-12T00:00:00Z" }] } });
    if (url.pathname === "/api/v1/activities") return route.fulfill({ json: { activities: [{ activity_id: ACTIVITY_ID, project_id: PROJECT_ID, name: "Breakout", created_at: "2026-08-12T00:00:00Z" }] } });
    if (url.pathname === "/api/v1/revision-head") return route.fulfill({ json: { project_id: PROJECT_ID, head_revision_id: REVISION_ID } });
    if (url.pathname === "/api/v1/variants") return route.fulfill({ json: { variants: [{ variant_id: VARIANT_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, head_revision_id: REVISION_ID, version: 1 }] } });
    if (url.pathname === `/api/v1/revisions/${REVISION_ID}` || url.pathname === `/api/v1/revisions/${CHILD_REVISION_ID}`) return route.fulfill({ json: { revision_id: url.pathname.endsWith(CHILD_REVISION_ID) ? CHILD_REVISION_ID : REVISION_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, git_tree_oid: "b".repeat(40), git_commit_oid: "a".repeat(40), files: [{ path: "strategy.py", artifact_id: ARTIFACT_ID, git_blob_oid: "c".repeat(40), sha256: "d".repeat(64), byte_size: STRATEGY_SOURCE.length, media_type: "text/x-python", storage_uri: `cas://sha256/${"d".repeat(64)}` }] } });
    if (url.pathname === `/api/v1/revisions/${REVISION_ID}/files/${ARTIFACT_ID}/content` || url.pathname === `/api/v1/revisions/${CHILD_REVISION_ID}/files/${ARTIFACT_ID}/content`) return route.fulfill({ body: STRATEGY_SOURCE, contentType: "text/plain" });
    if (url.pathname === "/api/v1/revision-comparison") return route.fulfill({ json: { project_id: PROJECT_ID, left_revision_id: REVISION_ID, right_revision_id: CHILD_REVISION_ID, changes: [{ path: "strategy.py", left_sha256: "a".repeat(64), right_sha256: "b".repeat(64), status: "changed" }] } });
    if (request.method() === "GET" && url.pathname === "/api/v1/data-imports/local-files") return route.fulfill({ json: { files: [{ file_name: "m7-a-share-daily.csv", source_format: "csv", byte_size: 256 }] } });
    if (request.method() === "POST" && url.pathname === "/api/v1/data-imports/local-preview") return route.fulfill({ json: { source, source_format: "csv", file_name: "m7-a-share-daily.csv", columns: Object.values(mapping), suggested_mapping: mapping, preview_rows: [{ timestamp: "2026-01-02T07:00:00Z", symbol: "SYNTH.XSHG", open: "0.1000", high: "0.1120", low: "0.0990", close: "0.1100", volume: "1000000" }], total_rows: 8 } });
    if (request.method() === "GET" && url.pathname === "/api/v1/data-snapshots") return route.fulfill({ json: { snapshots: snapshotCreated ? [snapshot] : [] } });
    if (request.method() === "POST" && url.pathname === "/api/v1/data-snapshots") {
      snapshotCreated = true;
      return route.fulfill({ json: { disposition: "accepted", event: { payload: { snapshot_id: DATA_SNAPSHOT_ID } } } });
    }
    if (url.pathname === "/api/v1/runs") return route.fulfill({ json: { runs: formalRequested ? [{ run_id: RUN_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, candidate_revision_id: REVISION_ID, status: "succeeded", finished_at: "2026-08-12T00:00:00Z" }] : [] } });
    if (url.pathname === `/api/v1/runs/${RUN_ID}/report`) return route.fulfill({ json: {
      report: {
        report_version: "m9-v1",
        run: { run_id: RUN_ID, run_spec_id: "75757575-7575-4575-8575-757575757575", project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, candidate_revision_id: REVISION_ID, status: "succeeded", calculation_hash: "a".repeat(64), finished_at: "2026-08-12T00:00:00Z" },
        identities: { engine_result_sha256: "a".repeat(64), engine_version: "oqs-quant-engine/0.1.0", engine_schema_version: 1, account_model: "a_share_cash", data_snapshot_id: DATA_SNAPSHOT_ID, data_snapshot_sha256: "b".repeat(64), strategy_tree_oid: "c".repeat(40), parameters_sha256: "d".repeat(64), cost_model_sha256: "e".repeat(64), environment_lock_sha256: "f".repeat(64), price_basis: "raw", cutoff: "2026-12-31T23:59:59Z", timezone: "Asia/Shanghai", sample_start: "2026-01-01T00:00:00Z", sample_end: "2026-01-31T00:00:00Z" },
        period: { start_at: "2026-01-01T00:00:00Z", end_at: "2026-01-31T00:00:00Z", session_count: 8 },
        summary: { starting_equity_atoms: "10000", ending_equity_atoms: "10100", net_pnl_atoms: "100", total_return_rate_atoms: "10000", max_drawdown_atoms: "0", max_drawdown_rate_atoms: "0", gross_exposure_atoms: "0", net_exposure_atoms: "0", total_fees_atoms: "6", total_stamp_duty_atoms: "0", total_funding_atoms: "0", total_slippage_atoms: "0", order_count: 0, fill_count: 0, closed_trade_count: 0, open_position_count: 0 },
        reconciliation: { passed: true, checks: [{ field: "metrics.ending_equity_atoms", expected: "10100", actual: "10100", passed: true }] },
        definitions: [],
        source: { engine_result_artifact_id: "76767676-7676-4676-8676-767676767676", manifest_artifact_id: "77777777-7777-4777-8777-777777777777" },
      },
      json_artifact: { artifact_id: "78787878-7878-4787-8787-787878787878", sha256: "1".repeat(64), media_type: "application/vnd.open-quant-studio.run-report+json", byte_size: 2, storage_uri: `cas://sha256/${"1".repeat(64)}` },
      html_artifact: { artifact_id: "79797979-7979-4797-8797-797979797979", sha256: "2".repeat(64), media_type: "application/vnd.open-quant-studio.run-report+html", byte_size: 2, storage_uri: `cas://sha256/${"2".repeat(64)}` },
    } });
    if (url.pathname === `/api/v1/runs/${RUN_ID}`) {
      runDetailAttempts += 1;
      if (runDetailAttempts === 1) return route.fulfill({ status: 404, json: { error: "run_not_found" } });
      return route.fulfill({ json: { run: { run_id: RUN_ID, project_id: PROJECT_ID, status: "succeeded", candidate_revision_id: REVISION_ID }, validation: { outcome: "passed" }, manifest: { run_spec: { run_spec_id: "spec" }, gates: { contract: "passed" } }, engine_result: { engine_version: "oqs-quant-engine/0.1.0", metrics: { ending_equity_atoms: "10100", total_fees_atoms: "6" }, orders: [], trades: [], positions: [], cash_ledger: [], funding_ledger: [], equity_curve: [], drawdown_curve: [], costs: {}, assumptions: {} } } });
    }
    if (request.method() === "POST" && url.pathname === `/api/v1/runs/${RUN_ID}/forward-tests`) return route.fulfill({ json: { event: { payload: { forward_test_id: FORWARD_TEST_ID } } } });
    if (url.pathname === `/api/v1/forward-tests/${FORWARD_TEST_ID}`) return route.fulfill({ json: { forward_test_id: FORWARD_TEST_ID, source_run_id: RUN_ID, source_revision_id: REVISION_ID, data_snapshot_id: "23232323-2323-4232-8232-232323232323", protocol_version: "oqs-forward-replay/m5-v1", released_bar_count: 1024, transcript_artifact_id: "54545454-5454-4454-8454-545454545454", transcript_sha256: "a".repeat(64), intent_tape_sha256: "b".repeat(64), status: "passed", error_code: null, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, created_at: "2026-08-12T00:05:00Z" } });
    if (request.method() === "GET" && url.pathname === `/api/v1/projects/${PROJECT_ID}/archive`) return route.fulfill({ body: "project archive fixture", contentType: PROJECT_ARCHIVE_MEDIA_TYPE });
    if (request.method() === "POST" && url.pathname === "/api/v1/project-archives/import") return route.fulfill({ json: { restored_project_id: PROJECT_ID, run_count: 1, artifact_count: 1 } });
    if (request.method() === "GET" && url.pathname === "/api/v1/logs") {
      const logs = diagnosticLogs.filter((log) => (
        (url.searchParams.get("run_id") === null || log.run_id === url.searchParams.get("run_id"))
        && (url.searchParams.get("level") === null || log.level === url.searchParams.get("level"))
        && (url.searchParams.get("priority") === null || log.priority === url.searchParams.get("priority"))
        && (url.searchParams.get("query") === null || `${log.event_code} ${log.message}`.includes(url.searchParams.get("query") ?? ""))
      ));
      return route.fulfill({ json: { logs, next_after_log_seq: null } });
    }
    if (request.method() === "POST" && url.pathname === "/api/v1/logs/delete") {
      const body = JSON.parse(request.postData() ?? "{}") as { log_ids: string[] };
      diagnosticLogs = diagnosticLogs.filter((log) => !body.log_ids.includes(log.log_id));
      return route.fulfill({ json: { disposition: "accepted", event: { payload: { deleted_count: body.log_ids.length } } } });
    }
    if (url.pathname === `/api/v1/runs/${RUN_ID}/promote`) return route.fulfill({ json: { disposition: "accepted" } });
    if (request.method() === "POST" && url.pathname === `/api/v1/variants/${VARIANT_ID}/revisions`) return route.fulfill({ json: { disposition: "accepted", revision_id: CHILD_REVISION_ID } });
    if (request.method() === "POST" && url.pathname === `/api/v1/variants/${VARIANT_ID}/merge-candidates`) return route.fulfill({ json: { disposition: "accepted", candidate_revision_id: CANDIDATE_REVISION_ID } });
    if (request.method() === "POST" && url.pathname === `/api/v1/revisions/${CANDIDATE_REVISION_ID}/runs`) {
      formalRequested = true;
      return route.fulfill({ json: { disposition: "accepted", run_id: RUN_ID } });
    }
    if (request.method() === "POST") return route.fulfill({ json: { disposition: "accepted", revision_id: REVISION_ID, run_id: RUN_ID } });
    return route.fulfill({ json: {} });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Canvas" })).toBeVisible();
  await expect(page.getByText("Strategy Variant")).toBeVisible();
  await expect(page.locator(".react-flow__edge")).toHaveCount(3);
  await page.getByRole("button", { name: /^Data/ }).click();
  await page.getByLabel("Local imports file").selectOption("m7-a-share-daily.csv");
  await page.getByRole("button", { name: "Preview local file" }).click();
  await expect(page.getByRole("heading", { name: "Preview rows" })).toBeVisible();
  await page.getByRole("button", { name: "Create immutable snapshot" }).click();
  const snapshotCard = page.getByTestId(`snapshot-${DATA_SNAPSHOT_ID}`);
  await expect(snapshotCard).toContainText("SYNTH.XSHG");
  await snapshotCard.getByRole("button", { name: "Use for Formal Run" }).click();
  await page.getByRole("button", { name: "Code" }).click();
  await expect(page.getByRole("heading", { name: "strategy.py" })).toBeVisible();
  await page.getByRole("button", { name: "Save child revision" }).click();
  await expect(page.getByText(/Child revision/)).toBeVisible();
  const childCall = calls.find((call) => call.path === `/api/v1/variants/${VARIANT_ID}/revisions` && call.method === "POST");
  expect(JSON.parse(childCall?.body ?? "null")).toEqual({
    message: "Edit strategy.py from OQS Code workbench",
    files: [{ path: "strategy.py", body: STRATEGY_SOURCE }],
  });
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.locator("main h1", { hasText: "Compare" })).toBeVisible();
  await page.getByRole("button", { name: "Create merge candidate" }).click();
  await expect(page.getByText(/Merge candidate/)).toBeVisible();
  const mergeCall = calls.find((call) => call.path === `/api/v1/variants/${VARIANT_ID}/merge-candidates` && call.method === "POST");
  expect(JSON.parse(mergeCall?.body ?? "null")).toEqual({
    message: "Merge candidate from Compare workbench",
    files: [{ path: "strategy.py", body: STRATEGY_SOURCE }],
  });
  await page.getByRole("button", { name: "Run formal" }).click();
  const formalCall = calls.find((call) => call.path === `/api/v1/revisions/${CANDIDATE_REVISION_ID}/runs` && call.method === "POST");
  expect(formalCall?.body).toBe(JSON.stringify({ data_snapshot_id: DATA_SNAPSHOT_ID }));
  await expect(page.locator("main h1", { hasText: "Backtest" })).toBeVisible();
  await page.locator(".oqs-nav-item", { hasText: "Run Detail" }).click();
  await expect(page.locator("main h1", { hasText: "Run Detail" })).toBeVisible();
  await expect(page.getByTestId("run-report-ending-equity")).toContainText("10100");
  expect(runDetailAttempts).toBeGreaterThan(1);
  await page.getByRole("button", { name: "Promote" }).click();
  expect(calls.some((call) => call.path === `/api/v1/runs/${RUN_ID}/promote` && call.method === "POST" && call.body === "{}")).toBeTruthy();
  await page.getByRole("button", { name: "Forward Test" }).click();
  await expect(page.locator("main h1", { hasText: "Forward Test" })).toBeVisible();
  await page.getByRole("button", { name: "Run historical replay" }).click();
  await expect(page.getByTestId("forward-test-result")).toBeVisible();
  await expect(page.getByText("1024", { exact: true })).toBeVisible();
  expect(calls.some((call) => call.path === `/api/v1/runs/${RUN_ID}/forward-tests` && call.method === "POST" && call.body === "{}")).toBeTruthy();
  expect(calls.some((call) => call.path === `/api/v1/forward-tests/${FORWARD_TEST_ID}` && call.method === "GET")).toBeTruthy();
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByLabel("Archive log selection").selectOption("full");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download project archive" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`${PROJECT_ID}.oqs.zip`);
  expect(calls.some((call) => call.path === `/api/v1/projects/${PROJECT_ID}/archive` && call.search === "?selected_logs=full" && call.method === "GET")).toBeTruthy();
  await page.getByRole("button", { name: "Data" }).click();
  await page.getByLabel("Project archive ZIP").setInputFiles({ name: "replay.oqs.zip", mimeType: PROJECT_ARCHIVE_MEDIA_TYPE, buffer: Buffer.from("project archive fixture") });
  await page.getByRole("button", { name: "Import project archive" }).click();
  await expect(page.getByRole("status")).toContainText("Project archive replay.oqs.zip imported");
  const importCall = calls.find((call) => call.path === "/api/v1/project-archives/import" && call.method === "POST");
  expect(importCall?.body).toBe("project archive fixture");
  expect(importCall?.contentType).toBe(PROJECT_ARCHIVE_MEDIA_TYPE);
  await page.getByRole("button", { name: "Logs" }).click();
  await expect(page.locator("main h1", { hasText: "Logs" })).toBeVisible();
  await page.getByLabel("Log level").selectOption("warn");
  await page.getByLabel("Log priority").selectOption("p1");
  await page.getByLabel("Search logs").fill("deletion witness");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByText("deletion witness", { exact: true })).toBeVisible();
  const filteredLogCall = [...calls].reverse().find((call) => call.path === "/api/v1/logs" && call.method === "GET" && new URLSearchParams(call.search).get("query") === "deletion witness");
  const filteredLogQuery = new URLSearchParams(filteredLogCall?.search ?? "");
  expect(filteredLogQuery.get("run_id")).toBe(RUN_ID);
  expect(filteredLogQuery.get("level")).toBe("warn");
  expect(filteredLogQuery.get("priority")).toBe("p1");
  expect(filteredLogQuery.get("query")).toBe("deletion witness");
  expect(filteredLogQuery.get("limit")).toBe("100");
  await page.getByRole("button", { name: `Delete log ${WARN_LOG_ID}` }).click();
  await expect(page.getByRole("alertdialog", { name: "Confirm log deletion" })).toContainText("Delete 1 selected log?");
  await page.getByRole("button", { name: "Confirm deletion" }).click();
  await expect(page.getByText("No logs match current filters")).toBeVisible();
  const singleDeleteCall = calls.find((call) => call.path === "/api/v1/logs/delete" && call.method === "POST");
  expect(singleDeleteCall?.body).toBe(JSON.stringify({ log_ids: [WARN_LOG_ID] }));
  await page.getByLabel("Log level").selectOption("");
  await page.getByLabel("Log priority").selectOption("");
  await page.getByLabel("Search logs").fill("");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByText("routine record", { exact: true })).toBeVisible();
  await page.getByLabel(`Select log ${INFO_LOG_ID}`).check();
  await page.getByLabel(`Select log ${ERROR_LOG_ID}`).check();
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect(page.getByRole("alertdialog", { name: "Confirm log deletion" })).toContainText("Delete 2 selected logs?");
  await page.getByRole("button", { name: "Confirm deletion" }).click();
  await expect(page.getByText("No logs match current filters")).toBeVisible();
  const batchDeleteCall = [...calls].reverse().find((call) => call.path === "/api/v1/logs/delete" && call.method === "POST");
  expect(batchDeleteCall?.body).toBe(JSON.stringify({ log_ids: [INFO_LOG_ID, ERROR_LOG_ID] }));
  expect(calls.some((call) => call.path === "/api/v1/runs")).toBeTruthy();
});
