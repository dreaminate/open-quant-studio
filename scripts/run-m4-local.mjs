import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { once } from "node:events";
import { constants } from "node:fs";
import { access, copyFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

import {
  createOqsBrowserServer,
  loadM4FormalRunFixture,
} from "../apps/control-plane/dist/browser-server.js";
import { FetchQuantDomainRevisionClient } from "../apps/control-plane/dist/domain-revision-client.js";
import { FetchQuantDomainSessionClient } from "../apps/control-plane/dist/domain-session-client.js";
import { createLocalPiModel } from "../apps/control-plane/dist/local-pi-model.js";
import { PiSessionAdapter } from "../apps/control-plane/dist/pi-session-adapter.js";
import { createRevisionTools } from "../apps/control-plane/dist/revision-tools.js";
import { SessionRegistry } from "../apps/control-plane/dist/session-registry.js";
import { ModelRuntime } from "../apps/control-plane/node_modules/@earendil-works/pi-coding-agent/dist/index.js";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const SESSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const ROOT_REVISION_ID = "10101010-1010-4010-8010-101010101010";
const VARIANT_ID = "20202020-2020-4020-8020-202020202020";
const PI_SESSION_ID = "oqs-m4-local";
const ACTOR = {
  projectId: PROJECT_ID,
  activityId: ACTIVITY_ID,
  sessionId: SESSION_ID,
  workbenchId: "canvas",
};

export function resolveM4DataRoot(value = "var/m4-local") {
  const varRoot = join(REPO_ROOT, "var");
  const dataRoot = resolve(REPO_ROOT, value);
  const instancePath = relative(varRoot, dataRoot);
  if (
    instancePath === ""
    || instancePath === ".."
    || instancePath.startsWith(`..${sep}`)
    || isAbsolute(instancePath)
  ) {
    throw new Error("OQS_DATA_ROOT must stay inside the repository var directory");
  }
  return dataRoot;
}

function configuredStrategySource() {
  return [
    "STATE = {'intent_seq': 0, 'symbol': None}",
    "def on_start():",
    "    return []",
    "def _order(symbol, book, side, position_effect):",
    "    STATE['intent_seq'] += 1",
    "    return {'intent_kind': 'order', 'intent_id': f'oqs-local:{STATE[\"intent_seq\"]}', 'intent_seq': STATE['intent_seq'], 'symbol': symbol, 'book': book, 'side': side, 'position_effect': position_effect, 'quantity': '100', 'order_type': 'market', 'limit_price_atoms': None, 'time_in_force': 'day'}",
    "def on_bar(bar):",
    "    STATE['symbol'] = STATE['symbol'] or bar['symbol']",
    "    if bar['symbol'] != STATE['symbol']:",
    "        return []",
    "    if bar['session_seq'] == 1: return [_order(bar['symbol'], 'cash_long', 'buy', 'open'), _order(bar['symbol'], 'research_short', 'sell', 'open')]",
    "    if bar['session_seq'] == 2: return [_order(bar['symbol'], 'cash_long', 'sell', 'close'), _order(bar['symbol'], 'research_short', 'buy', 'close')]",
    "    return []",
    "",
  ].join("\n");
}

function startPython(arguments_, dataRoot, extraEnvironment = {}) {
  return spawn("uv", arguments_, {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      OQS_DATA_ROOT: dataRoot,
      PYTHONPATH: join(REPO_ROOT, "services/quant-domain/src"),
      ...extraEnvironment,
    },
    stdio: ["ignore", "inherit", "inherit"],
  });
}

async function createConfiguredPiModel(dataRoot) {
  const providerId = process.env.OQS_PI_PROVIDER;
  const modelId = process.env.OQS_PI_MODEL;
  if (!providerId || !modelId) {
    throw new Error(
      "OQS_PI_PROVIDER and OQS_PI_MODEL are required; set OQS_PI_MODE=fixture only for deterministic local tests",
    );
  }
  const modelRuntime = await ModelRuntime.create({
    authPath: process.env.OQS_PI_AUTH_PATH ?? join(dataRoot, "pi-auth.json"),
    modelsPath: process.env.OQS_PI_MODELS_PATH ?? null,
    allowModelNetwork: process.env.OQS_PI_ALLOW_NETWORK === "1",
    refreshOnCreate: false,
  });
  const model = modelRuntime.getModel(providerId, modelId);
  if (model === undefined) {
    throw new Error(`configured Pi model is unavailable: ${providerId}/${modelId}`);
  }
  return { model, modelRuntime, dispose: () => {} };
}

export async function waitForDomain(baseUrl, domain, instanceToken) {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    if (domain.exitCode !== null) {
      throw new Error(`quant-domain exited before readiness with code ${domain.exitCode}`);
    }
    let response;
    try {
      response = await fetch(`${baseUrl}/health`);
    } catch {
      await delay(50);
      continue;
    }
    if (!response.ok) {
      await delay(50);
      continue;
    }
    const health = await response.json();
    if (health.instance_token !== instanceToken) {
      throw new Error("quant-domain port is owned by a different instance");
    }
    return;
  }
  throw new Error("quant-domain did not become ready within 10 seconds");
}

async function listen(server, host, port) {
  await new Promise((resolveListen, rejectListen) => {
    const onError = (error) => rejectListen(error);
    server.once("error", onError);
    server.listen(port, host, () => {
      server.off("error", onError);
      resolveListen();
    });
  });
}

async function stopChild(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  child.kill("SIGTERM");
  await once(child, "exit");
}

async function installSampleImport(importsRoot, fileName) {
  try {
    await copyFile(
      join(REPO_ROOT, "fixtures/market", fileName),
      join(importsRoot, fileName),
      constants.COPYFILE_EXCL,
    );
  } catch (error) {
    if (error.code !== "EEXIST") throw error;
  }
}

async function main() {
  const host = process.env.OQS_HOST ?? "127.0.0.1";
  const port = Number(process.env.OQS_PORT ?? "4173");
  const domainPort = Number(process.env.OQS_DOMAIN_PORT ?? "8765");
  const dataRoot = resolveM4DataRoot(process.env.OQS_DATA_ROOT);
  const domainBaseUrl = `http://127.0.0.1:${domainPort}`;
  const domainInstanceToken = randomUUID();
  const webRoot = join(REPO_ROOT, "apps/web/dist");
  const fixturePath = join(REPO_ROOT, "fixtures/backtests/m3-a-share-long-short-v1.json");
  const controlledCwd = join(dataRoot, "pi-workspace");
  const controlledSessionDir = join(dataRoot, "pi-sessions");
  const importsRoot = join(dataRoot, "imports");
  const exportsRoot = join(dataRoot, "exports");
  const fixtureMode = process.env.OQS_PI_MODE === "fixture";
  const formalRunFixture = fixtureMode
    ? await loadM4FormalRunFixture(fixturePath)
    : undefined;
  const strategy = configuredStrategySource();

  await access(join(webRoot, "index.html"));
  await mkdir(controlledCwd, { recursive: true });
  await mkdir(controlledSessionDir, { recursive: true });
  await mkdir(importsRoot, { recursive: true });
  await mkdir(exportsRoot, { recursive: true });
  await Promise.all([
    installSampleImport(importsRoot, "m7-a-share-daily.csv"),
    installSampleImport(importsRoot, "m7-crypto-linear.csv"),
    installSampleImport(importsRoot, "m8-a-share-rotation.csv"),
  ]);

  const domain = startPython([
    "run",
    "--project",
    join(REPO_ROOT, "services/quant-domain"),
    "--frozen",
    "uvicorn",
    "quant_domain.app:app",
    "--host",
    "127.0.0.1",
    "--port",
    String(domainPort),
    "--log-level",
    "warning",
  ], dataRoot, { OQS_DOMAIN_INSTANCE_TOKEN: domainInstanceToken });
  let worker;
  let browserServer;
  let registry;
  let localPiModel;
  try {
    await waitForDomain(domainBaseUrl, domain, domainInstanceToken);
    worker = startPython([
      "run",
      "--project",
      join(REPO_ROOT, "services/quant-domain"),
      "--frozen",
      "python",
      "-m",
      "quant_domain.worker",
      "--data-root",
      dataRoot,
      "--poll-interval",
      "0.1",
    ], dataRoot);

    const sessionClient = new FetchQuantDomainSessionClient(domainBaseUrl);
    const revisionClient = new FetchQuantDomainRevisionClient(sessionClient);
    await sessionClient.registerSession({
      ...ACTOR,
      piSessionId: PI_SESSION_ID,
      commandId: "81818181-8181-4818-8181-818181818181",
      correlationId: "91919191-9191-4919-8191-919191919191",
    });
    await revisionClient.createRevisionRoot({
      ...ACTOR,
      commandId: "82828282-8282-4828-8282-828282828282",
      correlationId: "92929292-9292-4929-8292-929292929292",
      revisionId: ROOT_REVISION_ID,
      message: "M4 local formal strategy root",
      files: [{ path: "strategy.py", body: strategy }],
    });
    await revisionClient.createStrategyVariant({
      ...ACTOR,
      commandId: "83838383-8383-4838-8383-838383838383",
      correlationId: "93939393-9393-4939-8393-939393939393",
      variantId: VARIANT_ID,
      baseRevisionId: ROOT_REVISION_ID,
    });

    localPiModel = process.env.OQS_PI_MODE === "fixture"
      ? await createLocalPiModel(join(dataRoot, "pi-model-auth.json"), {
        toolTracer: process.env.OQS_PI_TOOL_TRACER === "1",
      })
      : await createConfiguredPiModel(dataRoot);
    registry = new SessionRegistry();
    const revisionTools = createRevisionTools(revisionClient, {
      ...ACTOR,
      workbenchId: () => registry.status(SESSION_ID)?.activeWorkbenchId ?? "canvas",
    });
    const adapter = await PiSessionAdapter.create({
      ...ACTOR,
      controlledCwd,
      controlledSessionDir,
      piSessionId: PI_SESSION_ID,
      model: localPiModel.model,
      modelRuntime: localPiModel.modelRuntime,
      customTools: revisionTools,
    });
    registry.register({ adapter, ...ACTOR });
    registry.bindWorkbench(SESSION_ID, "code");
    registry.bindWorkbench(SESSION_ID, "run-detail");

    browserServer = createOqsBrowserServer({
      activeSessionId: SESSION_ID,
      registry,
      revisionClient,
      ...(formalRunFixture === undefined ? {} : { formalRunFixture }),
      webRoot,
    });
    await listen(browserServer, host, port);
    process.stdout.write(`Open Quant Studio M4 local runtime: http://${host}:${port}\n`);

    const stop = new Promise((resolveStop) => {
      process.once("SIGINT", resolveStop);
      process.once("SIGTERM", resolveStop);
    });
    const unexpectedDomainExit = once(domain, "exit").then(([code, signal]) => {
      throw new Error(`quant-domain exited unexpectedly (${code ?? signal})`);
    });
    const unexpectedWorkerExit = once(worker, "exit").then(([code, signal]) => {
      throw new Error(`quant-domain worker exited unexpectedly (${code ?? signal})`);
    });
    await Promise.race([stop, unexpectedDomainExit, unexpectedWorkerExit]);
  } finally {
    if (browserServer?.listening) {
      const browserClosed = once(browserServer, "close");
      browserServer.close();
      browserServer.closeAllConnections();
      await browserClosed;
    }
    registry?.dispose();
    localPiModel?.dispose();
    if (worker !== undefined) await stopChild(worker);
    await stopChild(domain);
  }
}

if (resolve(process.argv[1] ?? "") === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
