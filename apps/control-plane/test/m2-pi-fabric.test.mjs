import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";

import {
  fauxAssistantMessage,
  fauxToolCall,
  registerFauxProvider,
  streamSimple,
} from "@earendil-works/pi-ai/compat";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

import {
  formatMessageMarker,
  PiSessionAdapter,
  StaticResourceLoader,
  validatePiSessionId,
} from "../dist/pi-session-adapter.js";
import { SessionRegistry } from "../dist/session-registry.js";
import { PiJsonlRecall } from "../dist/pi-jsonl-recall.js";


async function tempDir(prefix) {
  return mkdtemp(join(tmpdir(), `oqs-${prefix}-`));
}

test("Pi session ids use the upstream-compatible alphabet and reject colon fixtures", () => {
  assert.equal(validatePiSessionId("oqs-m2-session_01"), true);
  assert.equal(validatePiSessionId("A"), true);
  assert.equal(validatePiSessionId("pi:session:m2"), false);
  assert.equal(validatePiSessionId("-leading"), false);
  assert.equal(validatePiSessionId("trailing-"), false);
  const v7 = "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa";
  const v8 = "bbbbbbbb-bbbb-8bbb-8bbb-bbbbbbbbbbbb";
  assert.equal(formatMessageMarker(v7), `[oqs-message:${v7}]`);
  assert.equal(formatMessageMarker(v8), `[oqs-message:${v8}]`);
});

test("static resource loader has only the versioned OQS system prompt", async () => {
  const loader = new StaticResourceLoader({
    cwd: "/controlled/cwd",
    agentDir: "/controlled/agent",
    settingsPath: "/controlled/settings.json",
  });
  assert.deepEqual(loader.getExtensions().extensions, []);
  assert.deepEqual(loader.getSkills().skills, []);
  assert.deepEqual(loader.getPrompts().prompts, []);
  assert.deepEqual(loader.getThemes().themes, []);
  assert.deepEqual(loader.getAgentsFiles().agentsFiles, []);
  assert.match(loader.getSystemPrompt(), /Open Quant Studio/);
  assert.match(loader.getSystemPrompt(), /research-only/i);
  assert.equal(loader.cwd, "/controlled/cwd");
  assert.equal(loader.agentDir, "/controlled/agent");
  assert.equal(loader.settingsPath, "/controlled/settings.json");
});

test("registry routes one adapter across workbenches and rejects remapping", async () => {
  const root = await tempDir("registry");
  const sessionDir = join(root, "sessions");
  const adapter = await PiSessionAdapter.create({
    sessionId: "domain-session-m2",
    projectId: "project-m2",
    activityId: "activity-m2",
    controlledCwd: root,
    controlledSessionDir: sessionDir,
  });
  const registry = new SessionRegistry();

  registry.register({
    adapter,
    projectId: "project-m2",
    activityId: "activity-m2",
    workbenchId: "canvas",
  });
  registry.bindWorkbench("domain-session-m2", "code");
  registry.bindWorkbench("domain-session-m2", "run-detail");

  assert.equal(registry.get("domain-session-m2"), adapter);
  assert.deepEqual(registry.status("domain-session-m2"), {
    sessionId: "domain-session-m2",
    piSessionId: adapter.piSessionId,
    projectId: "project-m2",
    activityId: "activity-m2",
    workbenchIds: ["canvas", "code", "run-detail"],
    activeWorkbenchId: "canvas",
    isStreaming: false,
  });
  assert.throws(
    () =>
      registry.register({
        adapter,
        projectId: "other-project",
        activityId: "activity-m2",
        workbenchId: "canvas",
      }),
    /project/i,
  );

  registry.unregister("domain-session-m2");
  assert.equal(registry.get("domain-session-m2"), undefined);
  await rm(root, { recursive: true, force: true });
});

async function fauxSessionOptions(root, sessionDir, piSessionId, withTool = false, responses) {
  const faux = registerFauxProvider({
    provider: "oqs-faux",
    models: [{ id: "m2-faux", name: "M2 faux", reasoning: false, input: ["text"] }],
  });
  faux.setResponses(
    responses ?? (withTool
      ? [
          fauxAssistantMessage(fauxToolCall("oqs_test_tool", {})),
          fauxAssistantMessage("faux response"),
        ]
      : [fauxAssistantMessage("faux response")]),
  );
  const modelRuntime = await ModelRuntime.create({
    authPath: join(root, "auth.json"),
    modelsPath: null,
    allowModelNetwork: false,
    refreshOnCreate: false,
  });
  const model = faux.getModel();
  modelRuntime.registerProvider("oqs-faux", {
    baseUrl: "http://localhost:0",
    api: faux.api,
    apiKey: "faux-test",
    models: [
      {
        id: model.id,
        name: model.name,
        api: model.api,
        reasoning: model.reasoning,
        input: model.input,
        cost: model.cost,
        contextWindow: model.contextWindow,
        maxTokens: model.maxTokens,
      },
    ],
    streamSimple,
  });
  return { modelRuntime, model, unregister: faux.unregister };
}

test("adapter creates one Pi JSONL session with an explicit message marker", async () => {
  const root = await tempDir("adapter");
  const sessionDir = join(root, "sessions");
  const faux = await fauxSessionOptions(root, sessionDir, "pi-session-m2-follow-up", true);
  let customToolCalls = 0;
  const customTool = {
    name: "oqs_test_tool",
    label: "OQS test tool",
    description: "A no-op OQS fixture tool.",
    parameters: Type.Object({}),
    execute: async () => {
      customToolCalls += 1;
      return { content: [{ type: "text", text: "ok" }] };
    },
  };
  const adapter = await PiSessionAdapter.create({
    sessionId: "domain-session-m2-follow-up",
    projectId: "project-m2",
    activityId: "activity-m2",
    controlledCwd: root,
    controlledSessionDir: sessionDir,
    piSessionId: "pi-session-m2-follow-up",
    modelRuntime: faux.modelRuntime,
    model: faux.model,
    customTools: [customTool],
  });

  assert.equal(adapter.sessionId, "domain-session-m2-follow-up");
  assert.match(adapter.piSessionId, /^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$/);
  assert.equal(adapter.isStreaming, false);
  assert.deepEqual(adapter.activeToolNames, ["oqs_test_tool"]);
  const messageId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const response = await adapter.followUp({
    messageId,
    quotedBody: "hello Pi",
  }, { wake: true });
  assert.equal(response.marker, `[oqs-message:${messageId}]`);
  assert.equal(response.accepted, true);
  assert.equal(adapter.isStreaming, false);
  assert.equal(customToolCalls, 1);
  assert.ok(adapter.sessionFile.endsWith(".jsonl"));
  const jsonl = await readFile(adapter.sessionFile, "utf8");
  assert.match(jsonl, new RegExp(response.marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.equal(
    jsonl
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line))
      .some((entry) => entry.details?.messageId === messageId),
    true,
  );

  await adapter.dispose();
  const reopened = await PiSessionAdapter.open({
    sessionId: "domain-session-m2-follow-up",
    projectId: "project-m2",
    activityId: "activity-m2",
    controlledCwd: root,
    controlledSessionDir: sessionDir,
    piSessionId: adapter.piSessionId,
    modelRuntime: faux.modelRuntime,
    model: faux.model,
  });
  assert.equal(await reopened.hasMessageMarker(messageId), true);
  const retry = await reopened.followUp({ messageId, quotedBody: "hello Pi" });
  assert.equal(retry.duplicate, true);
  await reopened.dispose();
  faux.unregister();
  await rm(root, { recursive: true, force: true });
});

test("adapter reserves a marker before concurrent Pi writes", async () => {
  const root = await tempDir("adapter-concurrent");
  const sessionDir = join(root, "sessions");
  const faux = await fauxSessionOptions(root, sessionDir, "pi-session-m2-concurrent");
  const adapter = await PiSessionAdapter.create({
    sessionId: "domain-session-m2-concurrent",
    projectId: "project-m2",
    activityId: "activity-m2",
    controlledCwd: root,
    controlledSessionDir: sessionDir,
    piSessionId: "pi-session-m2-concurrent",
    modelRuntime: faux.modelRuntime,
    model: faux.model,
  });
  const messageId = "cccccccc-cccc-7ccc-8ccc-cccccccccccc";
  const results = await Promise.all([
    adapter.followUp({ messageId, quotedBody: "concurrent" }),
    adapter.followUp({ messageId, quotedBody: "concurrent" }),
  ]);
  assert.equal(results.filter((result) => result.accepted).length, 1);
  assert.equal(results.filter((result) => result.duplicate).length, 1);
  const entries = adapter.entries.filter(
    (entry) => entry.type === "custom_message" && entry.details?.messageId === messageId,
  );
  assert.equal(entries.length, 1);
  adapter.dispose();
  faux.unregister();
  await rm(root, { recursive: true, force: true });
});

test("adapter records streaming follow-ups in Pi JSONL before reporting acceptance", async () => {
  const root = await tempDir("adapter-streaming");
  const sessionDir = join(root, "sessions");
  const faux = await fauxSessionOptions(
    root,
    sessionDir,
    "pi-session-m2-streaming",
    false,
    [async () => {
      await delay(250);
      return fauxAssistantMessage("slow response");
    }, fauxAssistantMessage("follow-up handled")],
  );
  const adapter = await PiSessionAdapter.create({
    sessionId: "domain-session-m2-streaming",
    projectId: "project-m2",
    activityId: "activity-m2",
    controlledCwd: root,
    controlledSessionDir: sessionDir,
    piSessionId: "pi-session-m2-streaming",
    modelRuntime: faux.modelRuntime,
    model: faux.model,
  });
  const first = adapter.followUp({
    messageId: "dddddddd-dddd-7ddd-8ddd-dddddddddddd",
    quotedBody: "start a slow turn",
  }, { wake: true });
  for (let attempt = 0; attempt < 100 && !adapter.isStreaming; attempt += 1) {
    await delay(5);
  }
  assert.equal(adapter.isStreaming, true);
  let settled = false;
  const queuedMessageId = "eeeeeeee-eeee-7eee-8eee-eeeeeeeeeeee";
  const second = adapter.followUp({
    messageId: queuedMessageId,
    quotedBody: "persist me before acknowledging injection",
  }).then((result) => {
    settled = true;
    return result;
  });
  await delay(25);
  assert.equal(settled, false);
  await first;
  const result = await second;
  assert.equal(result.accepted, true);
  assert.equal(
    adapter.entries.some(
      (entry) => entry.type === "custom_message" && entry.details?.messageId === queuedMessageId,
    ),
    true,
  );
  adapter.dispose();
  faux.unregister();
  await rm(root, { recursive: true, force: true });
});

test("marker dedupe trusts structured OQS details, not marker-shaped body text", async () => {
  const root = await tempDir("adapter-marker-spoof");
  const sessionDir = join(root, "sessions");
  const adapter = await PiSessionAdapter.create({
    sessionId: "domain-session-m2-marker-spoof",
    projectId: "project-m2",
    activityId: "activity-m2",
    controlledCwd: root,
    controlledSessionDir: sessionDir,
    piSessionId: "pi-session-m2-marker-spoof",
  });
  const spoofed = "ffffffff-ffff-7fff-8fff-ffffffffffff";
  await adapter.followUp({
    messageId: "99999999-9999-7999-8999-999999999999",
    quotedBody: `ordinary evidence contains ${formatMessageMarker(spoofed)}`,
  });
  assert.equal(await adapter.hasMessageMarker(spoofed), false);
  adapter.dispose();
  await rm(root, { recursive: true, force: true });
});

test("recall anchors abandoned intermediate matches to their descendant leaf", async () => {
  const entries = [
    { id: "root", parentId: null, type: "custom_message", customType: "fixture", content: "root", timestamp: "2026-08-11T00:00:00Z" },
    { id: "abandoned-mid", parentId: "root", type: "custom_message", customType: "fixture", content: "abandoned research fact", timestamp: "2026-08-11T00:00:01Z" },
    { id: "abandoned-tail", parentId: "abandoned-mid", type: "custom_message", customType: "fixture", content: "abandoned successor", timestamp: "2026-08-11T00:00:02Z" },
    { id: "active-tail", parentId: "root", type: "custom_message", customType: "fixture", content: "active sibling", timestamp: "2026-08-11T00:00:03Z" },
  ];
  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  const adapter = {
    sessionId: "domain-session-branch",
    piSessionId: "pi-session-branch",
    projectId: "project-m2",
    currentLeafId: "active-tail",
    entries,
    branch(leafId = "active-tail") {
      const branch = [];
      let current = byId.get(leafId);
      while (current !== undefined) {
        branch.push(current);
        current = current.parentId === null ? undefined : byId.get(current.parentId);
      }
      return branch.reverse();
    },
  };
  const registry = {
    list: () => [{ sessionId: adapter.sessionId, projectId: adapter.projectId }],
    get: (sessionId) => sessionId === adapter.sessionId ? adapter : undefined,
  };
  const recall = new PiJsonlRecall(registry);
  const [result] = await recall.search({
    projectId: "project-m2",
    query: "abandoned research fact",
    topK: 1,
  });
  assert.equal(result.leafId, "abandoned-tail");
  const context = await recall.context({
    projectId: "project-m2",
    sessionId: adapter.sessionId,
    entryId: result.entryId,
    leafId: result.leafId,
    after: 1,
  });
  assert.deepEqual(context.after.map((entry) => entry.entryId), ["abandoned-tail"]);
  const inferred = await recall.context({
    projectId: "project-m2",
    sessionId: adapter.sessionId,
    entryId: result.entryId,
    after: 1,
  });
  assert.equal(inferred.entry.leafId, "abandoned-tail");
  assert.deepEqual(inferred.after.map((entry) => entry.entryId), ["abandoned-tail"]);
});

test("recall searches only a registered project session and returns anchored evidence", async () => {
  const root = await tempDir("recall");
  const sessionDir = join(root, "sessions");
  const faux = await fauxSessionOptions(root, sessionDir, "pi-session-m2-recall");
  const adapter = await PiSessionAdapter.create({
    sessionId: "domain-session-m2-recall",
    projectId: "project-m2",
    activityId: "activity-m2",
    controlledCwd: root,
    controlledSessionDir: sessionDir,
    piSessionId: "pi-session-m2-recall",
    modelRuntime: faux.modelRuntime,
    model: faux.model,
  });
  const registry = new SessionRegistry();
  registry.register({
    adapter,
    projectId: "project-m2",
    activityId: "activity-m2",
    workbenchId: "canvas",
  });
  const response = await adapter.followUp({
    messageId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    quotedBody: "remember this bounded research fact",
  });

  const recall = new PiJsonlRecall(registry);
  const results = await recall.search({
    projectId: "project-m2",
    query: "bounded research fact",
    topK: 5,
  });
  assert.equal(results.length > 0, true);
  assert.equal(results[0].sessionId, "domain-session-m2-recall");
  assert.match(results[0].uri, /^pi-jsonl:\/\/session\/.+#entry=.+$/);
  assert.match(results[0].sha256, /^[a-f0-9]{64}$/);
  assert.deepEqual(results[0].source_ref, {
    session_id: results[0].sessionId,
    entry_id: results[0].entryId,
    leaf_id: results[0].leafId,
    sha256: results[0].sha256,
    source_uri: results[0].uri,
  });
  assert.ok(results[0].excerpt.length <= 1000);
  assert.match(results[0].rendered, /data, not instructions/i);
  const targetEntry = adapter.entries.find(
    (entry) => entry.type === "custom_message" && entry.details?.messageId === "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  );
  assert.ok(targetEntry);
  const anchored = await recall.context({
    projectId: "project-m2",
    sessionId: "domain-session-m2-recall",
    entryId: targetEntry.id,
    before: 10,
    after: 10,
  });
  assert.equal(anchored.entry.entryId, targetEntry.id);
  assert.match(anchored.rendered, /data, not instructions/i);

  await assert.rejects(
    recall.search({ projectId: "other-project", query: "fact", topK: 5 }),
    /registered same-project session/i,
  );
  await assert.rejects(
    recall.context({
      projectId: "project-m2",
      sessionId: "domain-session-m2-recall",
      entryId: "missing",
      before: 0,
      after: 0,
    }),
    /entry/i,
  );

  await adapter.dispose();
  faux.unregister();
  await rm(root, { recursive: true, force: true });
});
