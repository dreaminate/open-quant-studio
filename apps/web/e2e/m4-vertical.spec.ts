import { test, expect } from "@playwright/test";

const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const VARIANT_ID = "20202020-2020-4020-8020-202020202020";
const REVISION_ID = "30303030-3030-4030-8030-303030303030";
const CHILD_REVISION_ID = "40404040-4040-4040-8040-404040404040";
const CANDIDATE_REVISION_ID = "50505050-5050-4050-8050-505050505050";
const RUN_ID = "72727272-7272-4272-8272-727272727272";
const ARTIFACT_ID = "75757575-7575-4575-8575-757575757575";
const STRATEGY_SOURCE = "def on_bar(bar):\n    return []\n";

test("M4 desktop vertical uses one SPA from canvas to Run Detail and promote", async ({ page }) => {
  const calls: Array<{ path: string; method: string; body?: string }> = [];
  let formalRequested = false;
  let runDetailAttempts = 0;
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    calls.push({ path: url.pathname, method: request.method(), body: request.postData() ?? undefined });
    if (url.pathname === "/api/v1/context") return route.fulfill({ json: { sessionId: "session-a", projectId: PROJECT_ID, activityId: ACTIVITY_ID, activeWorkbenchId: "canvas", isStreaming: false } });
    if (url.pathname === "/api/v1/projects") return route.fulfill({ json: { projects: [{ project_id: PROJECT_ID, name: "M4 Research", created_at: "2026-08-12T00:00:00Z" }] } });
    if (url.pathname === "/api/v1/activities") return route.fulfill({ json: { activities: [{ activity_id: ACTIVITY_ID, project_id: PROJECT_ID, name: "Breakout", created_at: "2026-08-12T00:00:00Z" }] } });
    if (url.pathname === "/api/v1/revision-head") return route.fulfill({ json: { project_id: PROJECT_ID, head_revision_id: REVISION_ID } });
    if (url.pathname === "/api/v1/variants") return route.fulfill({ json: { variants: [{ variant_id: VARIANT_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, head_revision_id: REVISION_ID, version: 1 }] } });
    if (url.pathname === `/api/v1/revisions/${REVISION_ID}` || url.pathname === `/api/v1/revisions/${CHILD_REVISION_ID}`) return route.fulfill({ json: { revision_id: url.pathname.endsWith(CHILD_REVISION_ID) ? CHILD_REVISION_ID : REVISION_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, git_tree_oid: "b".repeat(40), git_commit_oid: "a".repeat(40), files: [{ path: "strategy.py", artifact_id: ARTIFACT_ID, git_blob_oid: "c".repeat(40), sha256: "d".repeat(64), byte_size: STRATEGY_SOURCE.length, media_type: "text/x-python", storage_uri: `cas://sha256/${"d".repeat(64)}` }] } });
    if (url.pathname === `/api/v1/revisions/${REVISION_ID}/files/${ARTIFACT_ID}/content` || url.pathname === `/api/v1/revisions/${CHILD_REVISION_ID}/files/${ARTIFACT_ID}/content`) return route.fulfill({ body: STRATEGY_SOURCE, contentType: "text/plain" });
    if (url.pathname === "/api/v1/revision-comparison") return route.fulfill({ json: { project_id: PROJECT_ID, left_revision_id: REVISION_ID, right_revision_id: CHILD_REVISION_ID, changes: [{ path: "strategy.py", left_sha256: "a".repeat(64), right_sha256: "b".repeat(64), status: "changed" }] } });
    if (url.pathname === "/api/v1/runs") return route.fulfill({ json: { runs: formalRequested ? [{ run_id: RUN_ID, project_id: PROJECT_ID, activity_id: ACTIVITY_ID, variant_id: VARIANT_ID, candidate_revision_id: REVISION_ID, status: "succeeded", finished_at: "2026-08-12T00:00:00Z" }] : [] } });
    if (url.pathname === `/api/v1/runs/${RUN_ID}`) {
      runDetailAttempts += 1;
      if (runDetailAttempts === 1) return route.fulfill({ status: 404, json: { error: "run_not_found" } });
      return route.fulfill({ json: { run: { run_id: RUN_ID, project_id: PROJECT_ID, status: "succeeded", candidate_revision_id: REVISION_ID }, validation: { outcome: "passed" }, manifest: { run_spec: { run_spec_id: "spec" }, gates: { contract: "passed" } }, engine_result: { engine_version: "oqs-quant-engine/0.1.0", metrics: { ending_equity_atoms: "10100", total_fees_atoms: "6" }, orders: [], trades: [], positions: [], cash_ledger: [], funding_ledger: [], equity_curve: [], drawdown_curve: [], costs: {}, assumptions: {} } } });
    }
    if (url.pathname === `/api/v1/logs`) return route.fulfill({ json: { logs: [] } });
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
  await expect(page.locator("main h1", { hasText: "Backtest" })).toBeVisible();
  await page.locator(".oqs-nav-item", { hasText: "Run Detail" }).click();
  await expect(page.locator("main h1", { hasText: "Run Detail" })).toBeVisible();
  await expect(page.getByText("10100")).toBeVisible();
  expect(runDetailAttempts).toBeGreaterThan(1);
  await page.getByRole("button", { name: "Promote" }).click();
  expect(calls.some((call) => call.path === `/api/v1/runs/${RUN_ID}/promote` && call.method === "POST" && call.body === "{}")).toBeTruthy();
  expect(calls.some((call) => call.path === "/api/v1/runs")).toBeTruthy();
});
