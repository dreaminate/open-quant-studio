import { mkdir } from "node:fs/promises";
import { join } from "node:path";

import { expect, test, type Locator, type Page } from "@playwright/test";

import {
  M10_REPO_ROOT,
  startM10Runtime,
  stopM10Runtime,
  verifyImportedArchiveIdentity,
} from "./m10-runtime";

const PROJECT_ID = "22222222-2222-4222-8222-222222222222";

const STRATEGIES = [
  {
    id: "a_share_trend_breakout",
    snapshot: "aShare",
    engineVersion: "oqs-quant-engine/0.1.0",
  },
  {
    id: "a_share_research_short",
    snapshot: "aShare",
    engineVersion: "oqs-quant-engine/0.1.0",
  },
  {
    id: "a_share_rotation",
    snapshot: "rotation",
    engineVersion: "oqs-quant-engine/0.2.0",
  },
  {
    id: "crypto_trend",
    snapshot: "crypto",
    engineVersion: "oqs-quant-engine/0.1.0",
  },
  {
    id: "crypto_mean_reversion",
    snapshot: "crypto",
    engineVersion: "oqs-quant-engine/0.1.0",
  },
  {
    id: "crypto_breakout",
    snapshot: "crypto",
    engineVersion: "oqs-quant-engine/0.1.0",
  },
] as const;

type SnapshotKind = (typeof STRATEGIES)[number]["snapshot"];

async function snapshotId(card: Locator): Promise<string> {
  const testId = await card.getAttribute("data-testid");
  expect(testId).toMatch(/^snapshot-[0-9a-f-]+$/);
  return testId!.slice("snapshot-".length);
}

async function selectSnapshot(page: Page, snapshot: string): Promise<void> {
  await page.getByRole("button", { name: /^Data/ }).click();
  const card = page.getByTestId(`snapshot-${snapshot}`);
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Use for Formal Run" }).click();
  await expect(card.getByRole("button", { name: "Selected for Formal Run" })).toBeVisible();
}

async function saveAndReadNotebook(page: Page, strategyId: string): Promise<void> {
  await page.getByRole("button", { name: /^Code/ }).click();
  const picker = page.getByLabel("Built-in strategy");
  await expect(picker.locator("option")).toHaveCount(7);
  await picker.selectOption(strategyId);
  await expect(page.locator(".cm-content")).toContainText(`STRATEGY_ID = "${strategyId}"`);

  const save = page.getByRole("button", { name: "Save child revision" });
  await save.click();
  await expect(page.getByRole("status")).toContainText("Child revision");
  await expect(save).toBeEnabled();

  const finalize = page.getByRole("button", { name: "Finalize notebook" });
  await finalize.click();
  await expect(page.getByRole("status")).toContainText("Finalized notebook");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download notebook" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`${strategyId}.ipynb`);
  const stream = await download.createReadStream();
  expect(stream).not.toBeNull();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(chunk);
  const notebook = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  expect(notebook.metadata.oqs.strategy_id).toBe(strategyId);
  expect(notebook.metadata.oqs.source).toBe(`strategies/${strategyId}/strategy.py`);
}

async function readRuns(baseUrl: string): Promise<Array<Record<string, unknown>>> {
  const response = await fetch(`${baseUrl}/api/v1/runs`);
  expect(response.ok).toBe(true);
  const body = await response.json() as { runs: Array<Record<string, unknown>> };
  return body.runs;
}

async function runStrategy(
  page: Page,
  baseUrl: string,
  strategy: (typeof STRATEGIES)[number],
  snapshotIdByKind: Record<SnapshotKind, string>,
  previousRunIds: Set<string>,
): Promise<string> {
  await page.reload();
  await expect(page.getByRole("heading", { name: "Canvas" })).toBeVisible();
  await selectSnapshot(page, snapshotIdByKind[strategy.snapshot]);
  await saveAndReadNotebook(page, strategy.id);

  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.locator("main h1", { hasText: "Compare" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "strategy.py" })).toBeVisible();
  await page.getByRole("button", { name: "Create merge candidate" }).click();
  await expect(page.getByRole("status")).toContainText("Merge candidate");

  await page.getByRole("button", { name: "Run formal", exact: true }).click();
  await expect(page.locator("main h1", { hasText: "Backtest" })).toBeVisible();
  await page.getByRole("button", { name: "View Run Detail", exact: true }).click();
  await expect(page.locator("main h1", { hasText: "Run Detail" })).toBeVisible();
  await expect.poll(async () => {
    const runs = await readRuns(baseUrl);
    return runs.some((run) =>
      !previousRunIds.has(run.run_id as string)
      && ["succeeded", "failed", "cancelled"].includes(run.status as string),
    );
  }, { timeout: 30_000 }).toBe(true);
  const allRuns = await readRuns(baseUrl);
  const current = allRuns.filter((run) => !previousRunIds.has(run.run_id as string));
  expect(current).toHaveLength(1);
  const run = current[0];
  expect(run, `Formal Run for ${strategy.id}`).toMatchObject({
    status: "succeeded",
    error_code: null,
    gates: { contract: "passed", strategy_import: "passed", smoke_run: "passed" },
  });
  const runId = run.run_id as string;

  await expect(page.getByTestId("run-report-reconciliation")).toContainText("passed", { timeout: 30_000 });
  await expect(page.locator(".oqs-chip", { hasText: strategy.engineVersion })).toBeVisible();

  const reportResponse = await fetch(`${baseUrl}/api/v1/runs/${runId}/report`);
  expect(reportResponse.ok).toBe(true);
  const reportBody = await reportResponse.json() as { report: { run: { run_id: string }; reconciliation: { passed: boolean } } };
  expect(reportBody.report.run.run_id).toBe(runId);
  expect(reportBody.report.reconciliation.passed).toBe(true);

  await page.getByRole("button", { name: "Promote" }).click();
  await expect(page.getByRole("status")).toContainText("promoted with compare-and-set");
  const [runDetailResponse, headResponse] = await Promise.all([
    fetch(`${baseUrl}/api/v1/runs/${runId}`),
    fetch(`${baseUrl}/api/v1/revision-head`),
  ]);
  expect(runDetailResponse.ok).toBe(true);
  expect(headResponse.ok).toBe(true);
  const runDetail = await runDetailResponse.json() as { run: { candidate_revision_id: string } };
  const head = await headResponse.json() as { head_revision_id: string };
  expect(head.head_revision_id).toBe(runDetail.run.candidate_revision_id);
  return runId;
}

test("M10 real runtime completes all six strategy, report, promote, and archive identity paths", async ({ page }) => {
  test.setTimeout(300_000);
  const runtime = await startM10Runtime();
  try {
    await page.goto(runtime.baseUrl);
    await expect(page.getByRole("heading", { name: "Canvas" })).toBeVisible();
    await page.getByRole("button", { name: /^Data/ }).click();

    const localImport = page.getByLabel("Local imports file");
    await expect(localImport.locator('option[value="m7-a-share-daily.csv"]')).toHaveCount(1);
    await localImport.selectOption("m7-a-share-daily.csv");
    await page.getByRole("button", { name: "Preview local file" }).click();
    await expect(page.getByRole("heading", { name: "Preview rows" })).toBeVisible();
    await page.getByRole("button", { name: "Create immutable snapshot" }).click();
    const aShare = await snapshotId(page.locator('[data-testid^="snapshot-"]', { hasText: "SYNTH.XSHG" }));

    await localImport.selectOption("m7-crypto-linear.csv");
    await page.getByRole("button", { name: "Preview local file" }).click();
    await page.getByLabel("Snapshot market").selectOption("crypto_linear_perp");
    await page.getByLabel("Snapshot timezone").fill("UTC");
    await page.getByRole("button", { name: "Create immutable snapshot" }).click();
    const crypto = await snapshotId(page.locator('[data-testid^="snapshot-"]', { hasText: "BTCUSDT.PERP" }));

    await page.getByLabel("Market data file").setInputFiles(
      join(M10_REPO_ROOT, "fixtures/market/m8-a-share-rotation.csv"),
    );
    await page.getByRole("button", { name: "Preview upload" }).click();
    await page.getByLabel("Snapshot market").selectOption("a_share_daily");
    await page.getByLabel("Snapshot timezone").fill("Asia/Shanghai");
    await page.getByRole("button", { name: "Create immutable snapshot" }).click();
    const rotation = await snapshotId(page.locator('[data-testid^="snapshot-"]', { hasText: "3-symbol portfolio" }));

    const snapshotIdByKind = { aShare, crypto, rotation };
    const runIds = new Set<string>();
    for (const strategy of STRATEGIES) {
      const runId = await runStrategy(page, runtime.baseUrl, strategy, snapshotIdByKind, runIds);
      runIds.add(runId);
    }
    expect(runIds.size).toBe(STRATEGIES.length);

    await page.getByRole("button", { name: /^Settings/ }).click();
    await page.getByLabel("Archive log selection").selectOption("full");
    const archiveDownloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download project archive" }).click();
    const archiveDownload = await archiveDownloadPromise;
    expect(archiveDownload.suggestedFilename()).toBe(`${PROJECT_ID}.oqs.zip`);
    const archiveDirectory = join(runtime.dataRoot, "m10-archive-downloads");
    await mkdir(archiveDirectory, { recursive: true });
    const archivePath = join(archiveDirectory, archiveDownload.suggestedFilename());
    await archiveDownload.saveAs(archivePath);

    await page.getByRole("button", { name: /^Data/ }).click();
    await page.getByLabel("Project archive ZIP").setInputFiles(archivePath);
    await expect(page.getByText(`Ready: ${archiveDownload.suggestedFilename()}`)).toBeVisible();
    await page.getByRole("button", { name: "Import project archive" }).click();
    const importReceipt = page.locator(".oqs-detail-block").filter({ hasText: "Import receipt" });
    await expect(importReceipt).toContainText("accepted");
    await expect(importReceipt).toContainText(PROJECT_ID);

    const imported = await verifyImportedArchiveIdentity(
      archivePath,
      PROJECT_ID,
      [...runIds],
    );
    expect(imported.restored_project_id).toBe(PROJECT_ID);
    expect(imported.run_ids).toEqual([...runIds].sort());
    expect(imported.report_run_ids).toEqual([...runIds].sort());
  } finally {
    await stopM10Runtime(runtime);
  }
});
