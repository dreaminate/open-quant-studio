import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { readFile, mkdtemp, rm } from "node:fs/promises";
import { createServer as createNetServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";

import {
  createOqsBrowserServer,
  loadM4FormalRunFixture,
} from "../dist/browser-server.js";
import { FetchQuantDomainRevisionClient } from "../dist/domain-revision-client.js";
import { FetchQuantDomainSessionClient } from "../dist/domain-session-client.js";

const REPO_ROOT = resolve(import.meta.dirname, "../../..");
const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const SESSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const ACTOR = {
  projectId: PROJECT_ID,
  activityId: ACTIVITY_ID,
  sessionId: SESSION_ID,
  workbenchId: "canvas",
};

async function freeLoopbackPort() {
  const listener = createNetServer();
  listener.listen(0, "127.0.0.1");
  await once(listener, "listening");
  const address = listener.address();
  listener.close();
  await once(listener, "close");
  return address.port;
}

async function waitForServer(baseUrl, child, stderr) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`quant-domain exited early: ${stderr.value}`);
    }
    try {
      if ((await fetch(`${baseUrl}/health`)).ok) return;
    } catch {
      await delay(25);
    }
  }
  throw new Error(`quant-domain did not become ready: ${stderr.value}`);
}

function pythonLiteral(value) {
  if (value === null) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (Array.isArray(value)) return `[${value.map(pythonLiteral).join(",")}]`;
  if (typeof value === "object") {
    return `{${Object.entries(value)
      .map(([key, item]) => `${JSON.stringify(key)}:${pythonLiteral(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

async function formalStrategySource() {
  const fixture = JSON.parse(await readFile(
    resolve(REPO_ROOT, "fixtures/backtests/m3-a-share-long-short-v1.json"),
    "utf8",
  ));
  const templates = new Map();
  for (const intent of fixture.input.intents) {
    const { known_at, effective_at: _effectiveAt, ...template } = intent;
    const bucket = templates.get(known_at.session_seq) ?? [];
    bucket.push(template);
    templates.set(known_at.session_seq, bucket);
  }
  const literal = `{${[...templates.entries()]
    .map(([sessionSeq, intents]) => `${sessionSeq}:${pythonLiteral(intents)}`)
    .join(",")}}`;
  return [
    `INTENTS = ${literal}`,
    "def on_start():",
    "    return INTENTS.get(0, [])",
    "def on_bar(bar):",
    "    return INTENTS.get(bar['session_seq'], [])",
    "",
  ].join("\n");
}

async function json(response) {
  const body = await response.json();
  assert.equal(response.ok, true, JSON.stringify(body));
  return body;
}

test("real browser facade completes Project to immutable Run Detail and Promote", async (t) => {
  const dataRoot = await mkdtemp(join(tmpdir(), "oqs-m4-real-"));
  const domainPort = await freeLoopbackPort();
  const domainBaseUrl = `http://127.0.0.1:${domainPort}`;
  const stderr = { value: "" };
  const domain = spawn(
    "uv",
    [
      "run",
      "--project",
      join(REPO_ROOT, "services/quant-domain"),
      "--frozen",
      "uvicorn",
      "quant_domain.app:app",
      "--host",
      "127.0.0.1",
      "--port",
      domainPort.toString(),
      "--log-level",
      "warning",
    ],
    {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        OQS_DATA_ROOT: dataRoot,
        PYTHONPATH: join(REPO_ROOT, "services/quant-domain/src"),
      },
      stdio: ["ignore", "ignore", "pipe"],
    },
  );
  domain.stderr.setEncoding("utf8");
  domain.stderr.on("data", (chunk) => {
    stderr.value += chunk;
  });
  t.after(async () => {
    if (domain.exitCode === null) {
      domain.kill("SIGTERM");
      await once(domain, "exit");
    }
    await rm(dataRoot, { recursive: true, force: true });
  });
  await waitForServer(domainBaseUrl, domain, stderr);

  const sessionClient = new FetchQuantDomainSessionClient(domainBaseUrl);
  const revisionClient = new FetchQuantDomainRevisionClient(sessionClient);
  await sessionClient.registerSession({
    ...ACTOR,
    piSessionId: "oqs-m4-real-browser",
  });
  const strategy = await formalStrategySource();
  const rootReceipt = await revisionClient.createRevisionRoot({
    ...ACTOR,
    message: "M4 real browser root",
    files: [{ path: "strategy.py", body: strategy }],
  });
  const rootRevisionId = rootReceipt.event.payload.revision_id;

  const registry = {
    status(sessionId) {
      return sessionId === SESSION_ID
        ? {
            sessionId,
            projectId: PROJECT_ID,
            activityId: ACTIVITY_ID,
            activeWorkbenchId: "canvas",
            isStreaming: false,
          }
        : undefined;
    },
    get() {
      return {
        async prompt() {},
        subscribe() { return () => undefined; },
      };
    },
  };
  const browser = createOqsBrowserServer({
    activeSessionId: SESSION_ID,
    registry,
    revisionClient,
    formalRunFixture: await loadM4FormalRunFixture(
      resolve(REPO_ROOT, "fixtures/backtests/m3-a-share-long-short-v1.json"),
    ),
  });
  browser.listen(0, "127.0.0.1");
  await once(browser, "listening");
  t.after(async () => {
    browser.close();
    await once(browser, "close");
  });
  const browserAddress = browser.address();
  const browserBaseUrl = `http://127.0.0.1:${browserAddress.port}/api/v1`;

  const projects = await json(await fetch(`${browserBaseUrl}/projects`));
  const activities = await json(await fetch(`${browserBaseUrl}/activities`));
  assert.deepEqual(projects.projects.map((item) => item.project_id), [PROJECT_ID]);
  assert.deepEqual(activities.activities.map((item) => item.activity_id), [ACTIVITY_ID]);

  const variantReceipt = await json(await fetch(`${browserBaseUrl}/variants`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  }));
  const variantId = variantReceipt.event.payload.variant_id;
  const childReceipt = await json(await fetch(
    `${browserBaseUrl}/variants/${variantId}/revisions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: "M4 edited strategy",
        files: [{ path: "strategy.py", body: `${strategy}# browser edit\n` }],
      }),
    },
  ));
  const childRevisionId = childReceipt.event.payload.revision_id;

  const comparison = await json(await fetch(
    `${browserBaseUrl}/revision-comparison?leftRevisionId=${rootRevisionId}&rightRevisionId=${childRevisionId}`,
  ));
  assert.deepEqual(comparison.changes.map((change) => change.path), ["strategy.py"]);

  const mergeReceipt = await json(await fetch(
    `${browserBaseUrl}/variants/${variantId}/merge-candidates`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: "M4 resolved candidate",
        files: [{ path: "strategy.py", body: `${strategy}# browser edit\n` }],
      }),
    },
  ));
  const candidateRevisionId = mergeReceipt.event.payload.candidate_revision_id;
  const formalReceipt = await json(await fetch(
    `${browserBaseUrl}/revisions/${candidateRevisionId}/runs`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    },
  ));
  const runId = formalReceipt.event.payload.run_id;

  const workerResponse = await fetch(`${domainBaseUrl}/v1/jobs/run-next`, {
    method: "POST",
  });
  const workerResult = await json(workerResponse);
  assert.equal(workerResult.status, "succeeded");

  const run = await json(await fetch(`${browserBaseUrl}/runs/${runId}`));
  assert.equal(run.run.status, "succeeded");
  assert.equal(run.engine_result.orders.length, 4);
  assert.equal(run.engine_result.trades.length, 4);
  assert.equal(run.validation.outcome, "passed");
  assert.equal(run.run.calculation_hash, run.manifest.engine_result.sha256);
  const marketInputArtifact = await revisionClient.getArtifact(
    PROJECT_ID,
    run.run_spec.market_input_artifact_id,
  );
  assert.equal(marketInputArtifact.project_id, PROJECT_ID);
  assert.equal(marketInputArtifact.origin_kind, "fixture");
  assert.equal(
    marketInputArtifact.source_ref,
    "76767676-7676-4676-8676-767676767676",
  );

  const tamperingClient = new FetchQuantDomainRevisionClient({
    sessionClient,
    fetchImplementation: async (input, init) => {
      const response = await fetch(input, init);
      if (
        response.ok
        && input.toString() === `${domainBaseUrl}/v1/projects/${PROJECT_ID}/runs/${runId}`
      ) {
        const payload = await response.json();
        payload.engine_result.metrics.ending_equity_atoms = "0";
        return Response.json(payload);
      }
      return response;
    },
  });
  await assert.rejects(
    tamperingClient.getRun(PROJECT_ID, runId),
    /embedded engine_result does not match verified artifact bytes/,
  );

  const promoteReceipt = await json(await fetch(
    `${browserBaseUrl}/runs/${runId}/promote`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    },
  ));
  assert.equal(
    promoteReceipt.event.payload.promoted_revision_id,
    candidateRevisionId,
  );
  const head = await json(await fetch(`${browserBaseUrl}/revision-head`));
  assert.equal(head.head_revision_id, candidateRevisionId);

  const forbidden = await fetch(`${browserBaseUrl}/jobs/${formalReceipt.event.payload.job_id}`);
  assert.equal(forbidden.status, 404);
});
