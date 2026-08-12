import { expect, test } from "@playwright/test";

const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const RUN_ID = "72727272-7272-4272-8272-727272727272";
const REVISION_ID = "77777777-7777-4777-8777-777777777777";
const VARIANT_ID = "76767676-7676-4676-8676-767676767676";
const REPORT = {
  report_version: "m9-v1",
  run: {
    run_id: RUN_ID,
    run_spec_id: "75757575-7575-4575-8575-757575757575",
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    variant_id: VARIANT_ID,
    candidate_revision_id: REVISION_ID,
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
  definitions: [{ field: "ending_equity_atoms", name: "Ending equity", unit: "atoms", formula: "last equity", inputs: ["equity_curve"], empty_behavior: "starting equity" }],
  source: { engine_result_artifact_id: "b".repeat(36), manifest_artifact_id: "c".repeat(36) },
};

test("M9 Run Detail renders the exact report and downloads JSON/HTML", async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/context") return route.fulfill({ json: { sessionId: "session-a", projectId: PROJECT_ID, activityId: ACTIVITY_ID, activeWorkbenchId: "run-detail", isStreaming: false } });
    if (url.pathname === "/api/v1/projects") return route.fulfill({ json: { projects: [{ project_id: PROJECT_ID, name: "M9 Research", created_at: "2026-08-12T00:00:00Z" }] } });
    if (url.pathname === "/api/v1/activities") return route.fulfill({ json: { activities: [{ activity_id: ACTIVITY_ID, project_id: PROJECT_ID, name: "Report activity", created_at: "2026-08-12T00:00:00Z" }] } });
    if (url.pathname === "/api/v1/strategies") return route.fulfill({ json: { strategies: [] } });
    if (url.pathname === "/api/v1/revision-head") return route.fulfill({ json: { project_id: PROJECT_ID, head_revision_id: REVISION_ID } });
    if (url.pathname === "/api/v1/variants") return route.fulfill({ json: { variants: [{ variant_id: VARIANT_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, head_revision_id: REVISION_ID, version: 1 }] } });
    if (url.pathname === `/api/v1/revisions/${REVISION_ID}`) return route.fulfill({ json: { revision_id: REVISION_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, files: [{ path: "strategy.py", body: "def on_bar(bar):\n    return []\n" }] } });
    if (url.pathname === "/api/v1/runs") return route.fulfill({ json: { runs: [{ run_id: RUN_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, candidate_revision_id: REVISION_ID, status: "succeeded", finished_at: REPORT.run.finished_at }] } });
    if (url.pathname === `/api/v1/runs/${RUN_ID}`) return route.fulfill({ json: { run: REPORT.run, validation: { outcome: "passed" }, manifest: { run_spec: { data_snapshot_id: REPORT.identities.data_snapshot_id }, gates: { contract: "passed" } }, engine_result: { engine_version: REPORT.identities.engine_version, metrics: { ending_equity_atoms: REPORT.summary.ending_equity_atoms }, orders: [], trades: [], positions: [], cash_ledger: [], funding_ledger: [], equity_curve: [], drawdown_curve: [], costs: {}, assumptions: {} } } });
    if (url.pathname === `/api/v1/runs/${RUN_ID}/report`) return route.fulfill({ json: { report: REPORT, json_artifact: { artifact_id: "1".repeat(36), sha256: "1".repeat(64), media_type: "application/json", byte_size: 2, storage_uri: "cas://sha256/" + "1".repeat(64) }, html_artifact: { artifact_id: "2".repeat(36), sha256: "2".repeat(64), media_type: "application/vnd.open-quant-studio.run-report+html", byte_size: 2, storage_uri: "cas://sha256/" + "2".repeat(64) } } });
    if (url.pathname === `/api/v1/runs/${RUN_ID}/report.json`) return route.fulfill({ status: 200, contentType: "application/json", headers: { "Content-Disposition": `attachment; filename="${RUN_ID}.report.json"` }, body: "{}" });
    if (url.pathname === `/api/v1/runs/${RUN_ID}/report.html`) return route.fulfill({ status: 200, contentType: "application/vnd.open-quant-studio.run-report+html", headers: { "Content-Disposition": `attachment; filename="${RUN_ID}.report.html"` }, body: "<html>report</html>" });
    return route.fulfill({ status: 404, json: { error: "not_found" } });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Run Detail" }).click();
  await expect(page.getByTestId("run-report")).toBeVisible();
  await expect(page.getByTestId("run-report-ending-equity")).toContainText("10100");
  await expect(page.getByTestId("run-report-net-p&l")).toContainText("100");
  await expect(page.getByTestId("run-report-reconciliation")).toContainText("passed");
  await expect(page.getByTestId("run-report").getByText("Ending equity", { exact: true }).first()).toBeVisible();

  const jsonDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download JSON" }).click();
  const jsonDownload = await jsonDownloadPromise;
  expect(jsonDownload.suggestedFilename()).toBe(`${RUN_ID}.report.json`);
  expect((await (await jsonDownload.createReadStream()).toArray()).toString()).toBe("{}");

  const htmlDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download HTML" }).click();
  const htmlDownload = await htmlDownloadPromise;
  expect(htmlDownload.suggestedFilename()).toBe(`${RUN_ID}.report.html`);
  expect((await (await htmlDownload.createReadStream()).toArray()).toString()).toBe("<html>report</html>");
});
