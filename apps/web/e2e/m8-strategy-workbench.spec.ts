import { expect, test } from "@playwright/test";
import { runReportFixture } from "./run-report-fixture";


const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const VARIANT_ID = "20202020-2020-4020-8020-202020202020";
const ROOT_REVISION_ID = "30303030-3030-4030-8030-303030303030";
const SAVED_REVISION_ID = "31313131-3131-4131-8131-313131313131";
const FINAL_REVISION_ID = "32323232-3232-4232-8232-323232323232";
const EDITED_REVISION_ID = "34343434-3434-4434-8434-343434343434";
const MERGE_REVISION_ID = "33333333-3333-4333-8333-333333333334";
const SNAPSHOT_ID = "23232323-2323-4232-8232-232323232323";
const RUN_ID = "72727272-7272-4272-8272-727272727272";
const STRATEGY_IDS = [
  "a_share_trend_breakout",
  "a_share_research_short",
  "a_share_rotation",
  "crypto_trend",
  "crypto_mean_reversion",
  "crypto_breakout",
];
const SELECTED_STRATEGY_ID = "crypto_mean_reversion";
const STRATEGY_SOURCE = [
  "# Crypto mean reversion built-in strategy",
  "def on_start():",
  "    return []",
  "",
  "def on_bar(bar):",
  "    return []",
  "",
].join("\n");
const NOTEBOOK_BODY = `${JSON.stringify({
  cells: [{
    cell_type: "code",
    execution_count: null,
    metadata: { oqs: { role: "authoritative_source" } },
    outputs: [],
    source: STRATEGY_SOURCE,
  }],
  metadata: { oqs: { strategy_id: SELECTED_STRATEGY_ID } },
  nbformat: 4,
  nbformat_minor: 5,
}, null, 2)}\n`;
const EDITED_STRATEGY_SOURCE = `${STRATEGY_SOURCE}# Edited after notebook finalization.\n`;
const STRATEGIES = STRATEGY_IDS.map((strategyId, index) => ({
  strategy_id: strategyId,
  title: strategyId === SELECTED_STRATEGY_ID ? "Crypto mean reversion" : `Strategy ${index + 1}`,
  market: index < 3 ? "a_share_daily" : "crypto_linear_perp",
  source: `strategies/${strategyId}/strategy.py`,
  notebook: `strategies/${strategyId}/notebook.ipynb`,
  summary: `Built-in strategy ${index + 1}`,
  assumptions: ["Bars arrive in order."],
  parameters: [{ name: "WINDOW", value: 3, meaning: "completed bars" }],
  tags: ["built_in"],
  source_body: strategyId === SELECTED_STRATEGY_ID
    ? STRATEGY_SOURCE
    : `# ${strategyId}\ndef on_start():\n    return []\ndef on_bar(bar):\n    return []\n`,
  source_sha256: "a".repeat(64),
}));
const SNAPSHOT = {
  snapshot_id: SNAPSHOT_ID,
  source_artifact_id: "24242424-2424-4242-8242-242424242424",
  normalized_artifact_id: "25252525-2525-4252-8252-252525252525",
  market_input_artifact_id: "26262626-2626-4262-8262-262626262626",
  market: "crypto_linear_perp",
  symbol: "BTCUSDT.PERP",
  symbols: ["BTCUSDT.PERP"],
  timezone: "UTC",
  price_basis: "raw",
  cutoff: "2026-12-31T23:59:59Z",
  schema_version: 1,
  sample_start: "2026-01-01T00:00:00Z",
  sample_end: "2026-01-02T00:00:00Z",
  row_count: 8,
  session_count: 8,
  sha256: "b".repeat(64),
  created_at: "2026-08-12T00:00:00Z",
  project_id: PROJECT_ID,
  mapping: { timestamp: "date", symbol: "symbol", open: "open", high: "high", low: "low", close: "close", volume: "volume" },
  source_sha256: "c".repeat(64),
  normalized_sha256: "d".repeat(64),
  market_input_sha256: "e".repeat(64),
};


test("M8 selects, saves, finalizes, downloads, merges, and runs a built-in strategy", async ({ page }) => {
  const writes: Array<{ path: string; body: unknown }> = [];
  let currentRevisionId = ROOT_REVISION_ID;
  let formalRequested = false;
  let childRevisionCount = 0;

  const revision = (revisionId: string) => ({
    revision_id: revisionId,
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    variant_id: VARIANT_ID,
    git_tree_oid: revisionId === ROOT_REVISION_ID ? "a".repeat(40) : "b".repeat(40),
    git_commit_oid: "c".repeat(40),
    files: revisionId === FINAL_REVISION_ID
      ? [
          { path: "strategy.py", body: STRATEGY_SOURCE },
          { path: "strategy.ipynb", body: NOTEBOOK_BODY },
        ]
      : [{
          path: "strategy.py",
          body: revisionId === ROOT_REVISION_ID
            ? "def on_start():\n    return []\ndef on_bar(bar):\n    return []\n"
            : revisionId === EDITED_REVISION_ID ? EDITED_STRATEGY_SOURCE : STRATEGY_SOURCE,
        }],
  });

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const body = request.postData() ? JSON.parse(request.postData() ?? "null") : undefined;
    if (url.pathname === "/api/v1/context") return route.fulfill({ json: { sessionId: "session-a", projectId: PROJECT_ID, activityId: ACTIVITY_ID, activeWorkbenchId: "canvas", isStreaming: false } });
    if (url.pathname === "/api/v1/projects") return route.fulfill({ json: { projects: [{ project_id: PROJECT_ID, name: "M8 Research", created_at: "2026-08-12T00:00:00Z" }] } });
    if (url.pathname === "/api/v1/activities") return route.fulfill({ json: { activities: [{ activity_id: ACTIVITY_ID, project_id: PROJECT_ID, name: "Strategy workbench", created_at: "2026-08-12T00:00:00Z" }] } });
    if (url.pathname === "/api/v1/strategies" && request.method() === "GET") return route.fulfill({ json: { strategies: STRATEGIES } });
    if (url.pathname === "/api/v1/revision-head") return route.fulfill({ json: { project_id: PROJECT_ID, head_revision_id: ROOT_REVISION_ID } });
    if (url.pathname === "/api/v1/variants") return route.fulfill({ json: { variants: [{ variant_id: VARIANT_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, head_revision_id: currentRevisionId, version: 1 }] } });
    if (url.pathname.startsWith("/api/v1/revisions/") && request.method() === "GET" && !url.pathname.includes("/files/") && !url.pathname.endsWith("/runs")) {
      return route.fulfill({ json: revision(url.pathname.split("/").at(-1) ?? ROOT_REVISION_ID) });
    }
    if (url.pathname === `/api/v1/strategies/${SELECTED_STRATEGY_ID}/notebook` && request.method() === "POST") {
      expect(body).toEqual({ source: STRATEGY_SOURCE });
      return route.fulfill({ json: { strategy_id: SELECTED_STRATEGY_ID, file_name: "strategy.ipynb", body: NOTEBOOK_BODY, sha256: "f".repeat(64) } });
    }
    if (url.pathname === `/api/v1/variants/${VARIANT_ID}/revisions` && request.method() === "POST") {
      writes.push({ path: url.pathname, body });
      childRevisionCount += 1;
      currentRevisionId = childRevisionCount === 1
        ? SAVED_REVISION_ID
        : childRevisionCount === 2 ? FINAL_REVISION_ID : EDITED_REVISION_ID;
      return route.fulfill({ json: { disposition: "accepted", event: { payload: { revision_id: currentRevisionId } } } });
    }
    if (url.pathname === "/api/v1/revision-comparison") return route.fulfill({ json: { project_id: PROJECT_ID, left_revision_id: ROOT_REVISION_ID, right_revision_id: FINAL_REVISION_ID, changes: [{ path: "strategy.py", status: "changed", left_sha256: "1".repeat(64), right_sha256: "2".repeat(64) }, { path: "strategy.ipynb", status: "added", left_sha256: null, right_sha256: "3".repeat(64) }] } });
    if (url.pathname === `/api/v1/variants/${VARIANT_ID}/merge-candidates` && request.method() === "POST") {
      writes.push({ path: url.pathname, body });
      return route.fulfill({ json: { disposition: "accepted", event: { payload: { candidate_revision_id: MERGE_REVISION_ID } } } });
    }
    if (url.pathname === "/api/v1/data-imports/local-files") return route.fulfill({ json: { files: [] } });
    if (url.pathname === "/api/v1/data-snapshots") return route.fulfill({ json: { snapshots: [SNAPSHOT] } });
    if (url.pathname === "/api/v1/runs") return route.fulfill({ json: { runs: formalRequested ? [{ run_id: RUN_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, candidate_revision_id: MERGE_REVISION_ID, status: "succeeded", finished_at: "2026-08-12T00:05:00Z" }] : [] } });
    if (url.pathname === `/api/v1/revisions/${MERGE_REVISION_ID}/runs` && request.method() === "POST") {
      formalRequested = true;
      writes.push({ path: url.pathname, body });
      return route.fulfill({ json: { disposition: "accepted", event: { payload: { run_id: RUN_ID } } } });
    }
    if (url.pathname === `/api/v1/runs/${RUN_ID}`) return route.fulfill({ json: { run: { run_id: RUN_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, candidate_revision_id: MERGE_REVISION_ID, status: "succeeded" }, validation: { outcome: "passed" }, manifest: { run_spec: { data_snapshot_id: SNAPSHOT_ID }, gates: { contract: "passed" } }, engine_result: { engine_version: "oqs-quant-engine/0.1.0", metrics: { ending_equity_atoms: "10100" }, orders: [], trades: [], positions: [], cash_ledger: [], funding_ledger: [], equity_curve: [], drawdown_curve: [], costs: {}, assumptions: {} } } });
    if (url.pathname === `/api/v1/runs/${RUN_ID}/report`) return route.fulfill({ json: runReportFixture({ projectId: PROJECT_ID, activityId: ACTIVITY_ID, variantId: VARIANT_ID, revisionId: MERGE_REVISION_ID, snapshotId: SNAPSHOT_ID, runId: RUN_ID }) });
    return route.fulfill({ status: 404, json: { error: "not_found" } });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Code" }).click();
  await expect(page.getByLabel("Built-in strategy")).toHaveCount(1);
  await expect(page.getByLabel("Built-in strategy").locator("option")).toHaveCount(7);
  for (const strategy of STRATEGIES) {
    await page.getByLabel("Built-in strategy").selectOption(strategy.strategy_id);
    await expect(page.locator(".cm-content")).toContainText(
      strategy.source_body.split("\n")[0],
    );
  }
  await page.getByLabel("Built-in strategy").selectOption(SELECTED_STRATEGY_ID);
  await expect(page.locator(".cm-content")).toContainText("Crypto mean reversion built-in strategy");

  await page.getByRole("button", { name: "Save child revision" }).click();
  await expect(page.getByText("Child revision 31313131 created")).toBeVisible();
  expect(writes[0].body).toEqual({
    message: "Edit strategy.py from OQS Code workbench",
    files: [{ path: "strategy.py", body: STRATEGY_SOURCE }],
  });

  await page.getByRole("button", { name: "Finalize notebook" }).click();
  await expect(page.getByText("Finalized notebook in revision 32323232")).toBeVisible();
  expect(writes[1].body).toEqual({
    message: "Finalize Crypto mean reversion notebook from strategy.py",
    files: [
      { path: "strategy.py", body: STRATEGY_SOURCE },
      { path: "strategy.ipynb", body: NOTEBOOK_BODY },
    ],
  });

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download notebook" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`${SELECTED_STRATEGY_ID}.ipynb`);
  expect(await (await download.createReadStream()).toArray()).toEqual([Buffer.from(NOTEBOOK_BODY)]);

  await page.reload();
  await page.getByRole("button", { name: "Code" }).click();
  await expect(page.getByLabel("Built-in strategy")).toHaveValue("");
  const reopenedDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download notebook" }).click();
  const reopenedDownload = await reopenedDownloadPromise;
  expect(reopenedDownload.suggestedFilename()).toBe(`${SELECTED_STRATEGY_ID}.ipynb`);
  expect(await (await reopenedDownload.createReadStream()).toArray()).toEqual([Buffer.from(NOTEBOOK_BODY)]);

  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await page.getByRole("button", { name: "Create merge candidate" }).click();
  await expect(page.getByText("Merge candidate 33333333 created")).toBeVisible();
  expect(writes[2].body).toEqual({
    message: "Merge candidate from Compare workbench",
    files: [
      { path: "strategy.py", body: STRATEGY_SOURCE },
      { path: "strategy.ipynb", body: NOTEBOOK_BODY },
    ],
  });

  await page.getByRole("button", { name: "Data" }).click();
  await page.getByRole("button", { name: "Use for Formal Run" }).click();
  await page.getByRole("button", { name: "Run formal" }).click();
  expect(writes[3]).toEqual({
    path: `/api/v1/revisions/${MERGE_REVISION_ID}/runs`,
    body: { data_snapshot_id: SNAPSHOT_ID },
  });
  await page.getByRole("button", { name: "View Run Detail", exact: true }).click();
  await expect(page.locator("main h1", { hasText: "Run Detail" })).toBeVisible();
  await expect(page.getByTestId("run-report-ending-equity")).toContainText("10100");

  await page.getByRole("button", { name: "Code" }).click();
  const editor = page.locator(".cm-content");
  await editor.click();
  await page.keyboard.press(process.platform === "darwin" ? "Meta+End" : "Control+End");
  await page.keyboard.insertText("\n# Edited after notebook finalization.\n");
  await page.getByRole("button", { name: "Save child revision" }).click();
  await expect(page.getByText("Child revision 34343434 created")).toBeVisible();
  expect(writes[4].body).toEqual({
    message: "Edit strategy.py from OQS Code workbench",
    files: [{ path: "strategy.py", body: EDITED_STRATEGY_SOURCE }],
    removed_paths: ["strategy.ipynb"],
  });
  await expect(page.getByRole("button", { name: "Download notebook" })).toBeDisabled();
});
