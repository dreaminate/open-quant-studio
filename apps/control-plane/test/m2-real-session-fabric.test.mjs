import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { once } from "node:events";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";

import {
  fauxAssistantMessage,
  fauxToolCall,
  registerFauxProvider,
  streamSimple,
} from "@earendil-works/pi-ai/compat";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";

import { FetchQuantDomainSessionClient } from "../dist/domain-session-client.js";
import { PiJsonlRecall } from "../dist/pi-jsonl-recall.js";
import { PiSessionAdapter } from "../dist/pi-session-adapter.js";
import { SessionFabric } from "../dist/session-fabric.js";
import { SessionRegistry } from "../dist/session-registry.js";
import { createSessionFabricTools } from "../dist/session-tools.js";

const REPO_ROOT = resolve(import.meta.dirname, "../../..");
const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const SESSION_A = "session-a-m2";
const SESSION_B = "session-b-m2";

async function freePort() {
  const server = createServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const port = server.address().port;
  server.close();
  await once(server, "close");
  return port;
}

async function waitForServer(baseUrl, child, stderr) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`quant-domain exited early: ${stderr.value}`);
    }
    try {
      if ((await fetch(`${baseUrl}/health`)).ok) return;
    } catch {
      await delay(25);
    }
  }
  throw new Error("quant-domain did not become ready");
}

async function fauxModel(root, id, responses) {
  const faux = registerFauxProvider({
    provider: `oqs-faux-${id}`,
    models: [{ id: `m2-${id}`, name: `M2 ${id} faux`, reasoning: false, input: ["text"] }],
  });
  faux.setResponses(responses);
  const modelRuntime = await ModelRuntime.create({
    authPath: join(root, `${id}-auth.json`),
    modelsPath: null,
    allowModelNetwork: false,
    refreshOnCreate: false,
  });
  const model = faux.getModel();
  modelRuntime.registerProvider(`oqs-faux-${id}`, {
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

test("real Python HTTP + two official Pi sessions deliver, recall, reply, SSE, and dedupe", async (t) => {
  const dataRoot = await mkdtemp(join(tmpdir(), "oqs-m2-real-"));
  const root = await mkdtemp(join(tmpdir(), "oqs-m2-pi-"));
  const port = await freePort();
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
      env: { ...process.env, OQS_DATA_ROOT: dataRoot, PYTHONPATH: join(REPO_ROOT, "services/quant-domain/src") },
      stdio: ["ignore", "ignore", "pipe"],
    },
  );
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => { stderr.value += chunk; });
  t.after(async () => {
    if (child.exitCode === null) {
      child.kill("SIGTERM");
      await once(child, "exit");
    }
    await rm(dataRoot, { recursive: true, force: true });
    await rm(root, { recursive: true, force: true });
  });
  await waitForServer(baseUrl, child, stderr);

  const client = new FetchQuantDomainSessionClient(baseUrl);
  const registry = new SessionRegistry();
  const recall = new PiJsonlRecall(registry);
  let failInjectedMessageId = null;
  const realClient = {
    baseUrl,
    stageText: (...args) => client.stageText(...args),
    stageSourceEntry: (...args) => client.stageSourceEntry(...args),
    postCommand: (...args) => client.postCommand(...args),
    registerSession: (...args) => client.registerSession(...args),
    bindWorkbench: (...args) => client.bindWorkbench(...args),
    sendMessage: (...args) => client.sendMessage(...args),
    listSessions: (...args) => client.listSessions(...args),
    inbox: (...args) => client.inbox(...args),
    getMessage: (...args) => client.getMessage(...args),
    async transitionReceipt(request) {
      if (request.commandType === "session.message_mark_injected" && request.messageId === failInjectedMessageId) {
        failInjectedMessageId = "already-failed";
        throw new Error("injected transition failed once");
      }
      return client.transitionReceipt(request);
    },
  };
  const fabric = new SessionFabric({
    client: realClient,
    registry,
    recall,
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    workbenchId: "canvas",
  });
  const toolsA = createSessionFabricTools(fabric, {
    sessionId: SESSION_A,
    workbenchId: () => registry.status(SESSION_A)?.activeWorkbenchId ?? "canvas",
  });
  const toolsB = createSessionFabricTools(fabric, {
    sessionId: SESSION_B,
    workbenchId: () => registry.status(SESSION_B)?.activeWorkbenchId ?? "canvas",
  });
  let askMessageId;
  let adapterAForReply;
  const fauxA = await fauxModel(root, "a", [fauxAssistantMessage("A handled the reply"), fauxAssistantMessage("A handled retry")]);
  const fauxB = await fauxModel(root, "b", [
    fauxAssistantMessage(fauxToolCall("session_search", { query: "0.0006", top_k: 1 })),
    async (context) => {
      const toolResult = context.messages.findLast(
        (message) => message.role === "toolResult" && message.toolName === "session_search",
      );
      const text = toolResult?.content.find((part) => part.type === "text")?.text;
      if (text === undefined || askMessageId === undefined || adapterAForReply === undefined) {
        throw new Error("session_search result was not available to the Pi reply turn");
      }
      const recalled = JSON.parse(text);
      const fact = recalled.find((result) => result.sessionId === SESSION_A);
      if (fact?.source_ref === undefined) {
        throw new Error("session_search result omitted its composable source_ref");
      }
      await adapterAForReply.followUp({
        messageId: "aaaaaaa8-aaaa-8aaa-8aaa-aaaaaaaaaaaa",
        quotedBody: "A appended after the anchored fact",
      });
      return fauxAssistantMessage(fauxToolCall("session_reply", {
        recipient_session_id: SESSION_A,
        reply_to: askMessageId,
        body: "B confirms the fee model from anchored evidence",
        source_refs: [fact.source_ref],
      }));
    },
    fauxAssistantMessage("B handled the ask"),
    fauxAssistantMessage("B handled retry"),
    fauxAssistantMessage("B handled SSE"),
  ]);
  t.after(() => { fauxA.unregister(); fauxB.unregister(); });
  const adapterA = await PiSessionAdapter.create({
    sessionId: SESSION_A,
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    controlledCwd: root,
    controlledSessionDir: join(root, "sessions-a"),
    piSessionId: "pi-session-a-m2",
    modelRuntime: fauxA.modelRuntime,
    model: fauxA.model,
    customTools: toolsA,
  });
  const adapterB = await PiSessionAdapter.create({
    sessionId: SESSION_B,
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    controlledCwd: root,
    controlledSessionDir: join(root, "sessions-b"),
    piSessionId: "pi-session-b-m2",
    modelRuntime: fauxB.modelRuntime,
    model: fauxB.model,
    customTools: toolsB,
  });
  adapterAForReply = adapterA;
  t.after(() => { adapterA.dispose(); adapterB.dispose(); });
  assert.deepEqual([...adapterA.activeToolNames].sort(), toolsA.map((tool) => tool.name).sort());
  assert.deepEqual([...adapterB.activeToolNames].sort(), toolsB.map((tool) => tool.name).sort());

  await client.registerSession({
    projectId: PROJECT_ID, activityId: ACTIVITY_ID, sessionId: SESSION_A,
    workbenchId: "canvas", piSessionId: adapterA.piSessionId,
  });
  await client.registerSession({
    projectId: PROJECT_ID, activityId: ACTIVITY_ID, sessionId: SESSION_B,
    workbenchId: "canvas", piSessionId: adapterB.piSessionId,
  });
  registry.register({ adapter: adapterA, projectId: PROJECT_ID, activityId: ACTIVITY_ID, workbenchId: "canvas" });
  registry.bindWorkbench(SESSION_A, "code");
  registry.bindWorkbench(SESSION_A, "run-detail");
  assert.deepEqual(registry.status(SESSION_A).workbenchIds, ["canvas", "code", "run-detail"]);

  const factId = "aaaaaaa7-aaaa-7aaa-8aaa-aaaaaaaaaaaa";
  await adapterA.followUp({ messageId: factId, quotedBody: "A alpha-fact: fee model is 0.0006 per side" });
  const askBody = "Please inspect the fee model";
  const ask = await fabric.ask({ sessionId: SESSION_A, recipientSessionId: SESSION_B, body: askBody });
  assert.equal(ask.event.workbench_id, "canvas");
  askMessageId = (await client.inbox({ projectId: PROJECT_ID, sessionId: SESSION_B }))
    .find((message) => message.message_kind === "ask")?.message_id;
  assert.ok(askMessageId);
  const secretEvents = await (await fetch(`${baseUrl}/v1/events?project_id=${PROJECT_ID}`)).text();
  assert.equal(secretEvents.includes(askBody), false);
  const secretInbox = await (await fetch(`${baseUrl}/v1/inbox?project_id=${PROJECT_ID}&session_id=${SESSION_B}`)).text();
  assert.equal(secretInbox.includes(askBody), false);
  const secretLogs = await (await fetch(`${baseUrl}/v1/logs?project_id=${PROJECT_ID}`)).text();
  assert.equal(secretLogs.includes(askBody), false);
  assert.equal((await fabric.deliver(SESSION_B))[0].message.state, "queued");

  registry.register({ adapter: adapterB, projectId: PROJECT_ID, activityId: ACTIVITY_ID, workbenchId: "canvas" });
  const deliveredAsk = await fabric.deliver(SESSION_B, { wake: true });
  assert.equal(deliveredAsk[0].injected, true);
  const bConversation = JSON.stringify(adapterB.entries);
  assert.match(bConversation, /session_search/);
  assert.match(bConversation, /session_reply/);
  assert.match(bConversation, /alpha-fact/);
  const aInbox = await client.inbox({ projectId: PROJECT_ID, sessionId: SESSION_A });
  const replyMessage = aInbox.find((message) => message.message_kind === "reply");
  assert.ok(replyMessage);
  assert.equal((await fabric.deliver(SESSION_A, { wake: true })).some((result) => result.injected), true);

  const retryAsk = await fabric.ask({ sessionId: SESSION_A, recipientSessionId: SESSION_B, body: "Retry this bounded message" });
  const retryInbox = await client.inbox({ projectId: PROJECT_ID, sessionId: SESSION_B });
  const retryMessage = retryInbox.find((message) => message.message_kind === "ask" && message.message_id !== askMessageId);
  assert.ok(retryMessage);
  failInjectedMessageId = retryMessage.message_id;
  await assert.rejects(fabric.deliver(SESSION_B, { wake: true }), /injected transition failed once/);
  const firstEntries = adapterB.entries.filter((entry) => entry.type === "custom_message" && entry.details?.messageId === retryMessage.message_id);
  assert.equal(firstEntries.length, 1);
  const retryDelivery = await fabric.deliver(SESSION_B, { wake: true });
  assert.equal(retryDelivery[0].injected, true);
  const secondEntries = adapterB.entries.filter((entry) => entry.type === "custom_message" && entry.details?.messageId === retryMessage.message_id);
  assert.equal(secondEntries.length, 1);

  await fabric.bindWorkbench(SESSION_A, "code");
  const baseline = await fabric.readEvents({ lastAcknowledgedStreamSeq: 0, signal: AbortSignal.timeout(5_000), wake: false });
  const wake = fabric.readEvents({
    lastAcknowledgedStreamSeq: baseline,
    signal: AbortSignal.timeout(5_000),
    wake: true,
  });
  await delay(50);
  const toolSend = await toolsA.find((tool) => tool.name === "session_send").execute(
    "tool-send-code",
    { recipient_session_id: SESSION_B, body: "SSE wakes B from the code workbench" },
  );
  const toolReceipt = JSON.parse(toolSend.content[0].text);
  assert.equal(toolReceipt.event.workbench_id, "code");
  const sseMessageId = toolReceipt.event.payload.message_id;
  const cursor = await wake;
  assert.ok(cursor > baseline);
  const sseEntries = adapterB.entries.filter((entry) => entry.type === "custom_message" && entry.details?.messageId === sseMessageId);
  assert.equal(sseEntries.length, 1);
  const sseDurable = (await client.inbox({ projectId: PROJECT_ID, sessionId: SESSION_B })).find((message) => message.message_id === sseMessageId);
  assert.equal(sseDurable.state, "injected");
  await fabric.bindWorkbench(SESSION_A, "run-detail");
  assert.equal(registry.status(SESSION_A).activeWorkbenchId, "run-detail");
  const repeatedBody = "same immutable body can back multiple messages";
  const firstRepeated = JSON.parse((await toolsA.find((tool) => tool.name === "session_send").execute(
    "tool-send-repeat-1",
    { recipient_session_id: SESSION_B, body: repeatedBody },
  )).content[0].text);
  const secondRepeated = JSON.parse((await toolsA.find((tool) => tool.name === "session_send").execute(
    "tool-send-repeat-2",
    { recipient_session_id: SESSION_B, body: repeatedBody },
  )).content[0].text);
  assert.equal(firstRepeated.event.workbench_id, "run-detail");
  assert.equal(secondRepeated.event.workbench_id, "run-detail");
  assert.equal(firstRepeated.event.payload.artifact_id, secondRepeated.event.payload.artifact_id);
  const durableA = (await client.listSessions(PROJECT_ID)).find(
    (session) => session.session_id === SESSION_A,
  );
  assert.deepEqual(durableA.workbench_ids, ["canvas", "code", "run-detail"]);
  assert.equal(durableA.active_workbench_id, "run-detail");
  assert.equal((await client.getMessage({ projectId: PROJECT_ID, recipientSessionId: SESSION_B, messageId: retryMessage.message_id })).body, "Retry this bounded message");
});
