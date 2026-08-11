import assert from "node:assert/strict";
import { createServer } from "node:net";
import { once } from "node:events";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";

import {
  fauxAssistantMessage,
  fauxToolCall,
  registerFauxProvider,
  streamSimple,
} from "@earendil-works/pi-ai/compat";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";

import { validateTypedCommandEnvelope } from "@open-quant-studio/contracts";
import { FetchQuantDomainSessionClient } from "../dist/domain-session-client.js";
import { FetchQuantDomainRevisionClient } from "../dist/domain-revision-client.js";
import { PiSessionAdapter } from "../dist/pi-session-adapter.js";
import { createRevisionTools } from "../dist/revision-tools.js";

const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const SESSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const ROOT_REVISION_ID = "10101010-1010-4010-8010-101010101010";
const VARIANT_A_ID = "20202020-2020-4020-8020-202020202020";
const VARIANT_B_ID = "30303030-3030-4030-8030-303030303030";
const REVISION_A_ID = "40404040-4040-4040-8040-404040404040";
const REVISION_B_ID = "50505050-5050-4050-8050-505050505050";
const REPO_ROOT = resolve(import.meta.dirname, "../../..");

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

function receipt(command, eventType = "workspace.revision_created") {
  return {
    command_id: command.command_id,
    disposition: "accepted",
    event: {
      event_id: command.command_id,
      stream_seq: 1,
      schema_version: 1,
      event_type: eventType,
      project_id: command.project_id,
      activity_id: command.activity_id,
      session_id: command.session_id,
      workbench_id: command.workbench_id,
      correlation_id: command.correlation_id,
      causation_id: command.command_id,
      recorded_at: "2026-08-11T00:00:00Z",
      variant_id: command.variant_id,
      base_revision_id: command.base_revision_id,
      payload: eventType === "strategy.variant_created"
        ? { variant_id: command.variant_id, revision_id: command.base_revision_id }
        : eventType === "workspace.revision_promoted"
          ? {
              variant_id: command.variant_id,
              previous_revision_id: command.expected_revision_id,
              promoted_revision_id: command.payload.candidate_revision_id,
              git_commit_oid: "a".repeat(40),
              git_tree_oid: "b".repeat(40),
            }
          : {
              revision_id: command.payload.revision_id,
              parent_revision_id: command.base_revision_id,
              git_commit_oid: "a".repeat(40),
              git_tree_oid: "b".repeat(40),
              file_count: command.payload.files.length,
            },
    },
  };
}

function fakeClient() {
  const commands = [];
  const staged = [];
  const client = {
    baseUrl: "http://quant-domain.test",
    async stageText(body) {
      const bytes = new TextEncoder().encode(body);
      const hash = (await import("node:crypto")).createHash("sha256").update(bytes).digest("hex");
      staged.push(body);
      return { sha256: hash, byte_size: bytes.byteLength, storage_uri: `cas://sha256/${hash}` };
    },
    async postCommand(command) {
      commands.push(structuredClone(command));
      return receipt(command, command.command_type === "strategy.variant_create"
        ? "strategy.variant_created"
        : command.command_type === "workspace.revision_promote"
          ? "workspace.revision_promoted"
          : "workspace.revision_created");
    },
  };
  return { client, commands, staged };
}

const actor = {
  projectId: PROJECT_ID,
  activityId: ACTIVITY_ID,
  sessionId: SESSION_ID,
  workbenchId: "code",
};

test("revision tools expose exactly five actor-bound bounded tools", () => {
  const { client } = fakeClient();
  const revisionClient = new FetchQuantDomainRevisionClient(client, async () => {
    throw new Error("reads are not used");
  });
  const tools = createRevisionTools(revisionClient, { ...actor, workbenchId: () => "code" });
  assert.deepEqual(tools.map((tool) => tool.name), [
    "revision_create_root",
    "strategy_variant_create",
    "revision_create_child",
    "revision_compare",
    "revision_promote",
  ]);
  for (const tool of tools) {
    assert.equal("project_id" in tool.parameters.properties, false);
    assert.equal("activity_id" in tool.parameters.properties, false);
    assert.equal("session_id" in tool.parameters.properties, false);
    assert.equal("workbench_id" in tool.parameters.properties, false);
  }
});

test("Pi tool retries derive one deterministic command identity from the tool call", async () => {
  const { client, commands } = fakeClient();
  const revisionClient = new FetchQuantDomainRevisionClient(client, async () => {
    throw new Error("reads are not used");
  });
  const tool = createRevisionTools(revisionClient, actor).find(
    (candidate) => candidate.name === "strategy_variant_create",
  );
  const params = { base_revision_id: ROOT_REVISION_ID };
  await tool.execute("pi-tool-call-stable-1", params);
  await tool.execute("pi-tool-call-stable-1", params);
  assert.deepEqual(commands[1], commands[0]);
});

test("root and child commands are contract-valid, bounded, staged after validation, and preserve CAS lineage", async () => {
  const { client, commands, staged } = fakeClient();
  const revisionClient = new FetchQuantDomainRevisionClient(client, async () => {
    throw new Error("reads are not used");
  });
  const root = await revisionClient.createRevisionRoot({
    ...actor,
    commandId: "61616161-6161-4161-8161-616161616161",
    revisionId: ROOT_REVISION_ID,
    message: "Create root",
    files: [{ path: "strategy.py", body: "signal = close > open\n" }],
  });
  assert.equal(validateTypedCommandEnvelope(commands[0]).valid, true);
  assert.equal(root.command_id, commands[0].command_id);
  const childA = await revisionClient.createRevisionChild({
    ...actor,
    commandId: "62626262-6262-4262-8262-626262626262",
    revisionId: REVISION_A_ID,
    variantId: VARIANT_A_ID,
    baseRevisionId: ROOT_REVISION_ID,
    message: "A child",
    files: [{ path: "strategy.py", body: "signal = close > moving_average\n" }],
  });
  const childB = await revisionClient.createRevisionChild({
    ...actor,
    commandId: "63636363-6363-4363-8363-636363636363",
    revisionId: REVISION_B_ID,
    variantId: VARIANT_B_ID,
    baseRevisionId: ROOT_REVISION_ID,
    message: "B child",
    files: [{ path: "strategy.py", body: "signal = momentum > 0\n" }],
  });
  assert.equal(validateTypedCommandEnvelope(commands[1]).valid, true);
  assert.equal(validateTypedCommandEnvelope(commands[2]).valid, true);
  assert.equal(commands[1].base_revision_id, ROOT_REVISION_ID);
  assert.equal(commands[2].base_revision_id, ROOT_REVISION_ID);
  assert.notEqual(commands[1].variant_id, commands[2].variant_id);
  assert.notEqual(commands[1].payload.revision_id, commands[2].payload.revision_id);
  assert.equal(childA.command_id, commands[1].command_id);
  assert.equal(childB.command_id, commands[2].command_id);
  assert.deepEqual(staged, [
    "signal = close > open\n",
    "signal = close > moving_average\n",
    "signal = momentum > 0\n",
  ]);
});

test("same command retry preserves deterministic revision/artifact/provenance identity", async () => {
  const { client, commands } = fakeClient();
  const revisionClient = new FetchQuantDomainRevisionClient(client, async () => {
    throw new Error("reads are not used");
  });
  const request = {
    ...actor,
    commandId: "64646464-6464-4464-8464-646464646464",
    message: "retry identity",
    files: [{ path: "strategy.py", body: "same bytes\n" }],
  };
  await revisionClient.createRevisionRoot(request);
  await revisionClient.createRevisionRoot(request);
  assert.deepEqual(commands[1], commands[0]);
});

test("stale promotion HTTP conflict is surfaced", async () => {
  const { client } = fakeClient();
  client.postCommand = async () => {
    const { QuantDomainHttpError } = await import("../dist/domain-session-client.js");
    throw new QuantDomainHttpError({ status: 409, code: "promotion_conflict" });
  };
  const revisionClient = new FetchQuantDomainRevisionClient(client, async () => {
    throw new Error("reads are not used");
  });
  await assert.rejects(
    revisionClient.promoteRevision({
      ...actor,
      commandId: "65656565-6565-4565-8565-656565656565",
      expectedRevisionId: ROOT_REVISION_ID,
      variantId: VARIANT_A_ID,
      candidateRevisionId: REVISION_A_ID,
    }),
    (error) => error?.status === 409 && error?.code === "promotion_conflict",
  );
});

test("HTTP command receipts bind the top-level command id", async () => {
  const sessionClient = new FetchQuantDomainSessionClient(
    "http://quant-domain.test",
    async (_input, init) => {
      const command = JSON.parse(init.body);
      const response = receipt(command, "strategy.variant_created");
      response.command_id = "99999999-9999-4999-8999-999999999999";
      return new Response(JSON.stringify(response), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    },
  );
  const revisionClient = new FetchQuantDomainRevisionClient(sessionClient);
  await assert.rejects(
    revisionClient.createStrategyVariant({
      ...actor,
      commandId: "85858585-8585-4585-8585-858585858585",
      variantId: VARIANT_A_ID,
      baseRevisionId: ROOT_REVISION_ID,
    }),
    /preserve command identity/,
  );
});

test("HTTP error parsing bounds oversized server codes before exposing them", async () => {
  const { client } = fakeClient();
  const revisionClient = new FetchQuantDomainRevisionClient(
    client,
    async () => new Response(
      JSON.stringify({ error: "x".repeat(256 * 1024) }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    ),
  );
  await assert.rejects(
    revisionClient.getProjectRevisionHead(PROJECT_ID),
    (error) => error?.status === 409 && error?.code === null && error.message.length < 128,
  );
});

test("real Python HTTP reuses canonical text artifact identity from an M2 message in an M3 revision", async (t) => {
  const dataRoot = await mkdtemp(join(tmpdir(), "oqs-m3-http-data-"));
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
  t.after(async () => {
    if (child.exitCode === null) {
      child.kill("SIGTERM");
      await once(child, "exit");
    }
    await rm(dataRoot, { recursive: true, force: true });
  });
  await waitForServer(baseUrl, child, stderr);

  const sessionClient = new FetchQuantDomainSessionClient(baseUrl);
  await sessionClient.registerSession({
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    sessionId: SESSION_ID,
    workbenchId: "code",
    piSessionId: "pi-session-m3-message-a",
    commandId: "68686868-6868-4868-8868-686868686868",
    correlationId: "69696969-6969-4969-8969-696969696969",
  });
  await sessionClient.registerSession({
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    sessionId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    workbenchId: "code",
    piSessionId: "pi-session-m3-message-b",
    commandId: "70707070-7070-4070-8070-707070707070",
    correlationId: "71717171-7171-4171-8171-717171717171",
  });
  const body = "canonical M2-to-M3 artifact text\n";
  await sessionClient.sendMessage({
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    sessionId: SESSION_ID,
    workbenchId: "code",
    recipientSessionId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    messageKind: "send",
    body,
    messageId: "72727272-7272-4272-8272-727272727272",
    commandId: "73737373-7373-4373-8373-737373737373",
    correlationId: "74747474-7474-4474-8474-747474747474",
  });

  const revisionClient = new FetchQuantDomainRevisionClient(sessionClient);
  const receipt = await revisionClient.createRevisionRoot({
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    sessionId: SESSION_ID,
    workbenchId: "code",
    commandId: "75757575-7575-4575-8575-757575757575",
    correlationId: "76767676-7676-4676-8676-767676767676",
    revisionId: ROOT_REVISION_ID,
    message: "M3 root reuses M2 text identity",
    files: [{ path: "strategy.py", body }],
  });
  assert.equal(receipt.disposition, "accepted");
  assert.equal(receipt.event.event_type, "workspace.revision_created");
  assert.equal(receipt.event.variant_id, null);
  assert.equal(receipt.event.base_revision_id, null);
});

test("an official faux Pi AgentSession invokes strategy_variant_create", async () => {
  const root = await mkdtemp(join(tmpdir(), "oqs-m3-pi-"));
  const faux = registerFauxProvider({
    provider: "oqs-m3-faux",
    models: [{ id: "m3-faux", name: "M3 faux", reasoning: false, input: ["text"] }],
  });
  faux.setResponses([
    fauxAssistantMessage(fauxToolCall("strategy_variant_create", {
      base_revision_id: ROOT_REVISION_ID,
      variant_id: VARIANT_A_ID,
      command_id: "66666666-6666-4666-8666-666666666666",
    })),
    fauxAssistantMessage("variant created"),
  ]);
  const modelRuntime = await ModelRuntime.create({
    authPath: join(root, "auth.json"),
    modelsPath: null,
    allowModelNetwork: false,
    refreshOnCreate: false,
  });
  const model = faux.getModel();
  modelRuntime.registerProvider("oqs-m3-faux", {
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
  const { client, commands } = fakeClient();
  const revisionClient = new FetchQuantDomainRevisionClient(client, async () => {
    throw new Error("reads are not used");
  });
  const adapter = await PiSessionAdapter.create({
    sessionId: SESSION_ID,
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    controlledCwd: root,
    controlledSessionDir: join(root, "sessions"),
    piSessionId: "pi-session-m3-faux",
    modelRuntime,
    model,
    customTools: createRevisionTools(revisionClient, {
      ...actor,
      workbenchId: "code",
    }),
  });
  try {
    await adapter.followUp({
      messageId: "67676767-6767-4767-8767-676767676767",
      quotedBody: "create a strategy variant",
    }, { wake: true });
    assert.equal(commands.length, 1);
    assert.equal(commands[0].command_type, "strategy.variant_create");
    assert.equal(validateTypedCommandEnvelope(commands[0]).valid, true);
  } finally {
    adapter.dispose();
    faux.unregister();
    await rm(root, { recursive: true, force: true });
  }
});
