import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { setTimeout } from "node:timers/promises";
import test from "node:test";

import { FetchDomainEventStreamClient } from "../dist/domain-event-stream-client.js";


const REPO_ROOT = resolve(import.meta.dirname, "../../..");
const PROJECT_ID = "22222222-2222-4222-8222-222222222222";

async function freeLoopbackPort() {
  const listener = createServer();
  listener.listen(0, "127.0.0.1");
  await once(listener, "listening");
  const address = listener.address();
  const port = address.port;
  listener.close();
  await once(listener, "close");
  return port;
}

async function waitForServer(baseUrl, child, stderr) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`quant-domain exited early: ${stderr.value}`);
    }
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) {
        return;
      }
    } catch {
      await setTimeout(25);
    }
  }
  throw new Error("quant-domain did not become ready");
}

test("fetch client resumes and redelivers against the real Uvicorn SSE bytes", async (t) => {
  const dataRoot = await mkdtemp(join(tmpdir(), "oqs-m1-node-"));
  const port = await freeLoopbackPort();
  const baseUrl = `http://127.0.0.1:${port}`;
  const stderr = { value: "" };
  const child = spawn(
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
      port.toString(),
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
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => {
    stderr.value += chunk;
  });
  t.after(async () => {
    if (child.exitCode === null) {
      child.kill("SIGTERM");
      await once(child, "exit");
    }
    await rm(dataRoot, { recursive: true, force: true });
  });
  await waitForServer(baseUrl, child, stderr);

  const blob = new TextEncoder().encode("real TypeScript to Uvicorn stream\n");
  const sha256 = createHash("sha256").update(blob).digest("hex");
  const blobResponse = await fetch(`${baseUrl}/v1/artifact-blobs/${sha256}`, {
    method: "PUT",
    body: blob,
  });
  assert.equal(blobResponse.status, 201);

  const command = {
    command_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    schema_version: 1,
    command_type: "context.capture",
    project_id: PROJECT_ID,
    activity_id: "33333333-3333-4333-8333-333333333333",
    session_id: "pi:session:m1-real-wire",
    workbench_id: "canvas",
    correlation_id: "44444444-4444-4444-8444-444444444444",
    expected_revision_id: null,
    variant_id: null,
    base_revision_id: null,
    payload: {
      context_item_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      title: "Real wire evidence",
      trust_state: "raw_evidence",
      artifact: {
        artifact_id: "99999999-9999-4999-8999-999999999999",
        sha256,
        media_type: "text/plain",
        byte_size: blob.byteLength,
        storage_uri: `cas://sha256/${sha256}`,
        producing_revision_id: null,
        producing_run_id: null,
        provenance: {
          origin_kind: "fixture",
          source_ref: "15151515-1515-4515-8515-151515151515",
        },
      },
    },
  };
  const commandResponse = await fetch(`${baseUrl}/v1/commands`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(command),
  });
  assert.equal(commandResponse.status, 201);

  const client = new FetchDomainEventStreamClient(baseUrl);
  const initial = [];
  const initialCursor = await client.read({
    projectId: PROJECT_ID,
    lastAcknowledgedStreamSeq: 0,
    signal: AbortSignal.timeout(5_000),
    onEvent: async (event) => initial.push(event.event_type),
  });
  assert.equal(initialCursor, 1);
  assert.deepEqual(initial, ["context.captured"]);

  const jobResponse = await fetch(`${baseUrl}/v1/jobs/run-next`, {
    method: "POST",
  });
  assert.equal(jobResponse.status, 200);
  assert.equal((await jobResponse.json()).status, "succeeded");

  await assert.rejects(
    client.read({
      projectId: PROJECT_ID,
      lastAcknowledgedStreamSeq: 1,
      signal: AbortSignal.timeout(5_000),
      onEvent: async () => {
        throw new Error("projection failed on real wire");
      },
    }),
    /projection failed on real wire/,
  );
  const redelivered = [];
  const resumedCursor = await client.read({
    projectId: PROJECT_ID,
    lastAcknowledgedStreamSeq: 1,
    signal: AbortSignal.timeout(5_000),
    onEvent: async (event) => redelivered.push(event.event_type),
  });
  assert.equal(resumedCursor, 3);
  assert.deepEqual(redelivered, [
    "artifact.verification_started",
    "artifact.verification_succeeded",
  ]);
});
