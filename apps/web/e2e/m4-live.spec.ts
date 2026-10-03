import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { createServer as createNetServer } from "node:net";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

import { expect, test } from "@playwright/test";
import { validateFormalRunDetailReadModel } from "@open-quant-studio/contracts";

const REPO_ROOT = resolve(import.meta.dirname, "../../..");
const PROJECT_ID = "22222222-2222-4222-8222-222222222222";

async function freeLoopbackPort(): Promise<number> {
  const listener = createNetServer();
  listener.listen(0, "127.0.0.1");
  await once(listener, "listening");
  const address = listener.address();
  listener.close();
  await once(listener, "close");
  if (typeof address === "string" || address === null) throw new Error("loopback listener has no TCP port");
  return address.port;
}

async function waitForRuntime(
  baseUrl: string,
  runtime: ReturnType<typeof spawn>,
  output: { value: string },
): Promise<void> {
  for (let attempt = 0; attempt < 300; attempt += 1) {
    if (runtime.exitCode !== null) {
      throw new Error(`M4 runtime exited before readiness: ${output.value}`);
    }
    try {
      const response = await fetch(`${baseUrl}/api/v1/context`);
      if (response.ok && response.headers.get("content-type")?.startsWith("application/json")) return;
    } catch {
      await delay(50);
    }
  }
  throw new Error(`M4 runtime did not become ready: ${output.value}`);
}

test("real local runtime completes the browser edit to Formal Run and Promote vertical", async ({ page }) => {
  test.setTimeout(60_000);
  const varRoot = join(REPO_ROOT, "var");
  await mkdir(varRoot, { recursive: true });
  const dataRoot = await mkdtemp(join(varRoot, "m4-live-"));
  const port = await freeLoopbackPort();
  const domainPort = await freeLoopbackPort();
  const baseUrl = `http://127.0.0.1:${port}`;
  const output = { value: "" };
  const runtime = spawn("node", ["scripts/run-m4-local.mjs"], {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      OQS_DATA_ROOT: dataRoot,
      OQS_PORT: String(port),
      OQS_DOMAIN_PORT: String(domainPort),
      OQS_PI_MODE: "fixture",
      OQS_PI_TOOL_TRACER: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  runtime.stdout?.setEncoding("utf8");
  runtime.stderr?.setEncoding("utf8");
  runtime.stdout?.on("data", (chunk) => { output.value += chunk; });
  runtime.stderr?.on("data", (chunk) => { output.value += chunk; });

  try {
    await waitForRuntime(baseUrl, runtime, output);
    await page.goto(baseUrl);
    await expect(page.getByRole("heading", { name: "Canvas" })).toBeVisible();
    await expect(page.getByText("Strategy Variant")).toBeVisible();
    await expect(page.locator(".react-flow__edge")).toHaveCount(3);

    const chatEventsReady = page.waitForResponse((response) =>
      response.url().endsWith("/api/v1/chat/events")
      && response.request().method() === "GET");
    await page.getByRole("button", { name: "Pi Chat" }).click();
    const chatEventsResponse = await chatEventsReady;
    expect(chatEventsResponse.status()).toBe(200);
    expect(chatEventsResponse.headers()["content-type"]).toContain("text/event-stream");
    await expect(page.getByText("Pi connected", { exact: true })).toBeVisible();
    await page.getByRole("textbox", { name: "Chat prompt" }).fill("Confirm the local research context");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.locator(".oqs-chat-message.pi p").last()).toHaveText("Pi local demo is connected to the current research Activity.");
    await page.getByRole("textbox", { name: "Chat prompt" }).fill("OQS_TOOL_TRACER: create a new strategy variant and child revision");
    await page.getByRole("button", { name: "Send" }).click();
    for (let attempt = 0; attempt < 100; attempt += 1) {
      const variants = await (await fetch(`${baseUrl}/api/v1/variants`)).json();
      const traced = variants.variants?.find((variant: { variant_id?: string }) =>
        variant.variant_id === "40404040-4040-4040-8040-404040404040");
      if (traced) break;
      await delay(100);
    }
    const tracedVariants = await (await fetch(`${baseUrl}/api/v1/variants`)).json();
    expect(tracedVariants.variants.some((variant: { variant_id?: string }) =>
      variant.variant_id === "40404040-4040-4040-8040-404040404040")).toBe(true);
    for (let attempt = 0; attempt < 100; attempt += 1) {
      const revisionResponse = await fetch(`${baseUrl}/api/v1/revisions/30303030-3030-4030-8030-303030303030`);
      if (revisionResponse.ok) {
        const tracedRevision = await revisionResponse.json();
        const strategyFile = tracedRevision.files.find((file: { path?: string }) =>
          file.path === "strategy.py");
        expect(strategyFile?.artifact_id).toBeTruthy();
        const sourceResponse = await fetch(
          `${baseUrl}/api/v1/revisions/30303030-3030-4030-8030-303030303030/files/${strategyFile.artifact_id}/content`,
        );
        expect(sourceResponse.ok).toBe(true);
        expect(await sourceResponse.text()).toContain("# pi-tool-tracer");
        break;
      }
      await delay(100);
    }
    expect((await fetch(`${baseUrl}/api/v1/revisions/30303030-3030-4030-8030-303030303030`)).ok).toBe(true);

    await page.getByRole("button", { name: /^Data/ }).click();
    await expect(page.locator("main h1", { hasText: "Data" })).toBeVisible();
    const localImport = page.getByLabel("Local imports file");
    await expect(localImport.locator('option[value="m7-a-share-daily.csv"]')).toHaveCount(1);
    await localImport.selectOption("m7-a-share-daily.csv");
    await page.getByRole("button", { name: "Preview local file" }).click();
    await expect(page.getByRole("heading", { name: "Preview rows" })).toBeVisible();
    await expect(page.getByText("SYNTH.XSHG", { exact: true }).first()).toBeVisible();
    await page.getByLabel("Snapshot execution profile").selectOption("a-share-v3");
    await page.getByRole("button", { name: "Create immutable snapshot" }).click();
    const snapshot = page.locator('[data-testid^="snapshot-"]', { hasText: "SYNTH.XSHG" });
    await expect(snapshot).toBeVisible();
    await snapshot.getByRole("button", { name: "Use for Formal Run" }).click();
    await expect(snapshot.getByRole("button", { name: "Selected for Formal Run" })).toBeVisible();

    await page.getByRole("button", { name: "Code" }).click();
    await expect(page.getByRole("heading", { name: "strategy.py" })).toBeVisible();
    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.press(process.platform === "darwin" ? "Meta+End" : "Control+End");
    await page.keyboard.insertText("\n# live browser edit\n");
    await page.getByRole("button", { name: "Save child revision" }).click();
    await expect(page.getByText(/Child revision/)).toBeVisible();

    await page.getByRole("button", { name: "Compare", exact: true }).click();
    await expect(page.locator("main h1", { hasText: "Compare" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "strategy.py" })).toBeVisible();
    await page.getByRole("button", { name: "Create merge candidate" }).click();
    await expect(page.getByText(/Merge candidate/)).toBeVisible();

    await page.getByRole("button", { name: "Review formal Run" }).click();
    await expect(page.locator("main h1", { hasText: "Backtest" })).toBeVisible();
    await page.getByLabel("I reviewed strategy, parameters and costs").check();
    await page.getByRole("button", { name: "Request formal Run" }).click();
    let queuedRuns: { runs: Array<{ run_id: string }> } = { runs: [] };
    for (let attempt = 0; attempt < 100; attempt += 1) {
      queuedRuns = await (await fetch(`${baseUrl}/api/v1/runs`)).json();
      if (queuedRuns.runs.length > 0) break;
      await delay(100);
    }
    expect(queuedRuns.runs).toHaveLength(1);
    const queuedRunId = queuedRuns.runs[0].run_id;
    let rawRunDetail: { run?: { status?: string; error_code?: string | null } } | undefined;
    for (let attempt = 0; attempt < 100; attempt += 1) {
      const response = await fetch(
        `http://127.0.0.1:${domainPort}/v1/projects/${PROJECT_ID}/runs/${queuedRunId}`,
      );
      if (response.ok) {
        rawRunDetail = await response.json();
        if (["succeeded", "failed", "cancelled"].includes(rawRunDetail.run?.status ?? "")) break;
      }
      await delay(100);
    }
    expect(rawRunDetail?.run?.status, JSON.stringify(rawRunDetail)).toBe("succeeded");
    const detailContract = validateFormalRunDetailReadModel(rawRunDetail);
    expect(detailContract.valid, JSON.stringify(detailContract)).toBe(true);
    await page.locator(".oqs-nav-item", { hasText: "Run Detail" }).click();
    await expect(page.locator("main h1", { hasText: "Run Detail" })).toBeVisible();
    await expect(page.locator(".oqs-chip", { hasText: "oqs-quant-engine/0.3.0" })).toBeVisible({ timeout: 20_000 });
    await expect(
      page.getByTestId("engine-record-fills").getByRole("heading", { name: "fills", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("research_short", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("bound", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Promote" }).click();
    await expect(page.getByText(/promoted with compare-and-set/)).toBeVisible();

    const runList = await (await fetch(`${baseUrl}/api/v1/runs`)).json();
    expect(runList.runs).toHaveLength(1);
    expect(runList.runs[0].status).toBe("succeeded");
    const runDetail = await (await fetch(`${baseUrl}/api/v1/runs/${runList.runs[0].run_id}`)).json();
    const head = await (await fetch(`${baseUrl}/api/v1/revision-head`)).json();
    expect(runDetail.run_spec.execution_profile).toBe("a-share-v3");
    expect(runDetail.manifest.manifest_version).toBe("a-share-v3");
    expect(runDetail.engine_result.engine_version).toBe("oqs-quant-engine/0.3.0");
    expect(runDetail.engine_result.orders).toHaveLength(4);
    expect(runDetail.engine_result.fills).toHaveLength(4);
    expect(new Set(runDetail.engine_result.positions.map((position: { book: string }) => position.book))).toEqual(
      new Set(["cash_long", "research_short"]),
    );
    expect(runDetail.engine_result.cash_ledger).toHaveLength(4);
    expect(runDetail.engine_result.equity_curve).toHaveLength(8);
    expect(runDetail.artifacts.engine_result.sha256).toBe(runDetail.run.calculation_hash);
    expect(head.head_revision_id).toBe(runDetail.run.candidate_revision_id);
    expect((await fetch(`${baseUrl}/api/v1/jobs`)).status).toBe(404);
  } finally {
    if (runtime.exitCode === null) {
      runtime.kill("SIGTERM");
      await once(runtime, "exit");
    }
    await rm(dataRoot, { recursive: true, force: true });
  }
});
