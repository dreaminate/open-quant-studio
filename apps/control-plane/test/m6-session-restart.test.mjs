import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, realpath, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";

import {
  fauxAssistantMessage,
  registerFauxProvider,
  streamSimple,
} from "@earendil-works/pi-ai/compat";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";

import { FetchQuantDomainSessionClient } from "../dist/domain-session-client.js";
import { PiJsonlRecall } from "../dist/pi-jsonl-recall.js";
import { PiSessionAdapter } from "../dist/pi-session-adapter.js";
import { SessionFabric } from "../dist/session-fabric.js";
import { SessionRegistry } from "../dist/session-registry.js";

const REPO_ROOT = resolve(import.meta.dirname, "../../..");
const PROJECT_ID = "77777777-7777-4777-8777-777777777777";
const ACTIVITY_ID = "88888888-8888-4888-8888-888888888888";
const SESSION_ID = "session-m6-restart";
const SENDER_SESSION_ID = "session-m6-sender";
const PI_SESSION_ID = "pi-session-m6-restart";
const SEED_MESSAGE_ID = "60000000-0000-4000-8000-000000000001";
const QUEUED_MESSAGE_ID = "60000000-0000-4000-8000-000000000002";
const INITIAL_REPLY = "Pi session persisted before application restart";
const WAKE_REPLY = "Reopened Pi session handled the durable queued message";

async function freePort() {
  const server = createServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const port = server.address().port;
  server.close();
  await once(server, "close");
  return port;
}

function startQuantDomain(dataRoot, port) {
  const baseUrl = `http://127.0.0.1:${port}`;
  const stderr = { value: "" };
  const child = spawn(
    "uv",
    [
      "run", "--project", join(REPO_ROOT, "services/quant-domain"), "--frozen",
      "uvicorn", "quant_domain.app:app", "--host", "127.0.0.1", "--port", String(port),
      "--log-level", "warning",
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
  child.stderr.on("data", (chunk) => { stderr.value += chunk; });
  return { baseUrl, child, stderr };
}

async function waitForServer(runtime) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (runtime.child.exitCode !== null) {
      throw new Error(`quant-domain exited early: ${runtime.stderr.value}`);
    }
    try {
      if ((await fetch(`${runtime.baseUrl}/health`)).ok) return;
    } catch {
      await delay(25);
    }
  }
  throw new Error("quant-domain did not become ready");
}

async function stopQuantDomain(child) {
  if (child.exitCode === null && child.signalCode === null) {
    child.kill("SIGTERM");
    await once(child, "exit");
  }
}

async function fauxModel(root) {
  const faux = registerFauxProvider({
    provider: "oqs-faux-m6-session-restart",
    models: [{
      id: "m6-session-restart",
      name: "M6 session restart faux",
      reasoning: false,
      input: ["text"],
    }],
  });
  faux.setResponses([
    fauxAssistantMessage(INITIAL_REPLY),
    fauxAssistantMessage(WAKE_REPLY),
  ]);
  const modelRuntime = await ModelRuntime.create({
    authPath: join(root, "auth.json"),
    modelsPath: null,
    allowModelNetwork: false,
    refreshOnCreate: false,
  });
  const model = faux.getModel();
  modelRuntime.registerProvider("oqs-faux-m6-session-restart", {
    baseUrl: "http://localhost:0",
    api: faux.api,
    apiKey: "faux-test",
    models: [{
      id: model.id,
      name: model.name,
      api: model.api,
      reasoning: model.reasoning,
      input: model.input,
      cost: model.cost,
      contextWindow: model.contextWindow,
      maxTokens: model.maxTokens,
    }],
    streamSimple,
  });
  return { modelRuntime, model, unregister: faux.unregister };
}

function customMessageEntries(adapter, messageId) {
  return adapter.entries.filter(
    (entry) => entry.type === "custom_message" && entry.details?.messageId === messageId,
  );
}

function wakeReplyEntries(adapter) {
  return adapter.entries.filter((entry) => JSON.stringify(entry).includes(WAKE_REPLY));
}

test("normal application restart reopens one durable Pi session and wakes one offline message exactly once", async (t) => {
  const dataRoot = await mkdtemp(join(tmpdir(), "oqs-m6-restart-domain-"));
  const root = await mkdtemp(join(tmpdir(), "oqs-m6-restart-pi-"));
  let runtime = startQuantDomain(dataRoot, await freePort());
  t.after(async () => {
    if (runtime !== null) {
      await stopQuantDomain(runtime.child);
    }
    await rm(dataRoot, { recursive: true, force: true });
    await rm(root, { recursive: true, force: true });
  });
  await waitForServer(runtime);

  const faux = await fauxModel(root);
  t.after(() => { faux.unregister(); });
  const sessionsDir = join(root, "sessions");
  const clientBeforeRestart = new FetchQuantDomainSessionClient(runtime.baseUrl);
  const registryBeforeRestart = new SessionRegistry();
  t.after(() => { registryBeforeRestart.dispose(); });
  const fabricBeforeRestart = new SessionFabric({
    client: clientBeforeRestart,
    registry: registryBeforeRestart,
    recall: new PiJsonlRecall(registryBeforeRestart),
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    workbenchId: "canvas",
  });
  const adapterBeforeRestart = await PiSessionAdapter.create({
    sessionId: SESSION_ID,
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    controlledCwd: root,
    controlledSessionDir: sessionsDir,
    piSessionId: PI_SESSION_ID,
    modelRuntime: faux.modelRuntime,
    model: faux.model,
  });
  registryBeforeRestart.register({
    adapter: adapterBeforeRestart,
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    workbenchId: "canvas",
  });
  await clientBeforeRestart.registerSession({
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    sessionId: SESSION_ID,
    workbenchId: "canvas",
    piSessionId: PI_SESSION_ID,
  });
  await clientBeforeRestart.registerSession({
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    sessionId: SENDER_SESSION_ID,
    workbenchId: "canvas",
    piSessionId: "pi-session-m6-sender",
  });
  assert.equal((await fabricBeforeRestart.status(SESSION_ID)).piSessionId, PI_SESSION_ID);

  await adapterBeforeRestart.prompt("Establish this Pi session before the application restarts");
  assert.equal(
    adapterBeforeRestart.entries.filter((entry) => JSON.stringify(entry).includes(INITIAL_REPLY)).length,
    1,
  );
  await adapterBeforeRestart.followUp({
    messageId: SEED_MESSAGE_ID,
    quotedBody: "Pi JSONL continuity anchor before application restart",
  });
  const sessionFile = adapterBeforeRestart.sessionFile;
  const seedEntryBeforeRestart = customMessageEntries(adapterBeforeRestart, SEED_MESSAGE_ID)[0];
  assert.ok(seedEntryBeforeRestart);

  registryBeforeRestart.dispose();
  assert.equal(registryBeforeRestart.get(SESSION_ID), undefined);
  const queuedReceipt = await clientBeforeRestart.sendMessage({
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    sessionId: SENDER_SESSION_ID,
    workbenchId: "canvas",
    recipientSessionId: SESSION_ID,
    messageKind: "send",
    body: "A normal durable event arrived while the Pi session was offline",
    messageId: QUEUED_MESSAGE_ID,
  });
  assert.equal(queuedReceipt.event.payload.message_id, QUEUED_MESSAGE_ID);
  const queuedBeforeRestart = (await clientBeforeRestart.inbox({
    projectId: PROJECT_ID,
    sessionId: SESSION_ID,
  }))[0];
  assert.equal(queuedBeforeRestart.state, "queued");

  await stopQuantDomain(runtime.child);
  runtime = null;
  runtime = startQuantDomain(dataRoot, await freePort());
  await waitForServer(runtime);

  const clientAfterRestart = new FetchQuantDomainSessionClient(runtime.baseUrl);
  const registryAfterRestart = new SessionRegistry();
  t.after(() => { registryAfterRestart.dispose(); });
  const fabricAfterRestart = new SessionFabric({
    client: clientAfterRestart,
    registry: registryAfterRestart,
    recall: new PiJsonlRecall(registryAfterRestart),
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    workbenchId: "canvas",
  });
  const reopened = await PiSessionAdapter.open({
    sessionId: SESSION_ID,
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    controlledCwd: root,
    controlledSessionDir: sessionsDir,
    piSessionId: PI_SESSION_ID,
    sessionFile,
    modelRuntime: faux.modelRuntime,
    model: faux.model,
  });
  registryAfterRestart.register({
    adapter: reopened,
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    workbenchId: "canvas",
  });

  assert.equal(reopened.sessionId, SESSION_ID);
  assert.equal(reopened.piSessionId, PI_SESSION_ID);
  assert.equal(await realpath(reopened.sessionFile), await realpath(sessionFile));
  assert.deepEqual(customMessageEntries(reopened, SEED_MESSAGE_ID), [seedEntryBeforeRestart]);
  const durableSession = (await clientAfterRestart.listSessions(PROJECT_ID)).find(
    (session) => session.session_id === SESSION_ID,
  );
  assert.ok(durableSession);
  assert.equal(durableSession.activity_id, ACTIVITY_ID);
  assert.equal(durableSession.pi_session_id, PI_SESSION_ID);
  assert.equal(durableSession.session_uri, `pi-jsonl://session/${PI_SESSION_ID}`);
  assert.equal((await fabricAfterRestart.status(SESSION_ID)).piSessionId, PI_SESSION_ID);
  assert.equal(customMessageEntries(reopened, QUEUED_MESSAGE_ID).length, 0);
  assert.equal(wakeReplyEntries(reopened).length, 0);

  const delivery = await fabricAfterRestart.deliver(SESSION_ID, { wake: true });
  assert.equal(delivery.length, 1);
  assert.equal(delivery[0].message.message_id, QUEUED_MESSAGE_ID);
  assert.equal(delivery[0].message.state, "injected");
  assert.equal(delivery[0].delivered, true);
  assert.equal(delivery[0].duplicate, false);
  assert.equal(delivery[0].injected, true);
  assert.equal(customMessageEntries(reopened, QUEUED_MESSAGE_ID).length, 1);
  assert.equal(wakeReplyEntries(reopened).length, 1);

  const redelivery = await fabricAfterRestart.deliver(SESSION_ID, { wake: true });
  assert.equal(redelivery.length, 1);
  assert.equal(redelivery[0].message.state, "injected");
  assert.equal(customMessageEntries(reopened, QUEUED_MESSAGE_ID).length, 1);
  assert.equal(wakeReplyEntries(reopened).length, 1);
  const durableMessage = await clientAfterRestart.getMessage({
    projectId: PROJECT_ID,
    recipientSessionId: SESSION_ID,
    messageId: QUEUED_MESSAGE_ID,
  });
  assert.equal(durableMessage.state, "injected");
  assert.equal(durableMessage.receipt_version, 2);
});
