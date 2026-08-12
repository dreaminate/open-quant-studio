import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { createServer as createNetServer } from "node:net";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

import { expect, test } from "@playwright/test";

const REPO_ROOT = resolve(import.meta.dirname, "../../..");

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

    await page.getByRole("button", { name: /^Data/ }).click();
    await expect(page.locator("main h1", { hasText: "Data" })).toBeVisible();
    const localImport = page.getByLabel("Local imports file");
    await expect(localImport.locator('option[value="m7-a-share-daily.csv"]')).toHaveCount(1);
    await localImport.selectOption("m7-a-share-daily.csv");
    await page.getByRole("button", { name: "Preview local file" }).click();
    await expect(page.getByRole("heading", { name: "Preview rows" })).toBeVisible();
    await expect(page.getByText("SYNTH.XSHG", { exact: true }).first()).toBeVisible();
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

    await page.getByRole("button", { name: "Run formal" }).click();
    await expect(page.locator("main h1", { hasText: "Backtest" })).toBeVisible();
    await page.locator(".oqs-nav-item", { hasText: "Run Detail" }).click();
    await expect(page.locator("main h1", { hasText: "Run Detail" })).toBeVisible();
    await expect(page.locator(".oqs-chip", { hasText: "oqs-quant-engine/0.1.0" })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("bound", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Promote" }).click();
    await expect(page.getByText(/promoted with compare-and-set/)).toBeVisible();

    const runList = await (await fetch(`${baseUrl}/api/v1/runs`)).json();
    expect(runList.runs).toHaveLength(1);
    expect(runList.runs[0].status).toBe("succeeded");
    const runDetail = await (await fetch(`${baseUrl}/api/v1/runs/${runList.runs[0].run_id}`)).json();
    const head = await (await fetch(`${baseUrl}/api/v1/revision-head`)).json();
    expect(runDetail.engine_result.orders).toHaveLength(4);
    expect(runDetail.engine_result.trades).toHaveLength(4);
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
