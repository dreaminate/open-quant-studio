import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { once } from "node:events";
import { resolve } from "node:path";
import test from "node:test";

import {
  createOqsBrowserServer,
  loadM4FormalRunFixture,
} from "../dist/browser-server.js";
import { FetchQuantDomainRevisionClient } from "../dist/domain-revision-client.js";


const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const SESSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const VARIANT_ID = "20202020-2020-4020-8020-202020202020";
const REVISION_ID = "30303030-3030-4030-8030-303030303030";
const STRATEGY_IDS = [
  "a_share_trend_breakout",
  "a_share_research_short",
  "a_share_rotation",
  "crypto_trend",
  "crypto_mean_reversion",
  "crypto_breakout",
];
const STRATEGIES = STRATEGY_IDS.map((strategyId, index) => {
  const sourceBody = `def on_start():\n    return []\n\ndef on_bar(bar):\n    return []\n# ${strategyId}\n`;
  return {
    strategy_id: strategyId,
    title: `Strategy ${index + 1}`,
    market: index < 3 ? "a_share_daily" : "crypto_linear_perp",
    source: `strategies/${strategyId}/strategy.py`,
    notebook: `strategies/${strategyId}/notebook.ipynb`,
    summary: `Built-in strategy ${index + 1}`,
    assumptions: ["Bars arrive in order."],
    parameters: [{ name: "WINDOW", value: 3, meaning: "completed bars" }],
    tags: ["built_in"],
    source_body: sourceBody,
    source_sha256: createHash("sha256").update(sourceBody).digest("hex"),
  };
});
const NOTEBOOK_BODY = `${JSON.stringify({ cells: [], nbformat: 4, nbformat_minor: 5 })}\n`;
const NOTEBOOK = {
  strategy_id: STRATEGY_IDS[0],
  file_name: "strategy.ipynb",
  body: NOTEBOOK_BODY,
  sha256: createHash("sha256").update(NOTEBOOK_BODY).digest("hex"),
};
const FIXTURE = await loadM4FormalRunFixture(resolve(
  import.meta.dirname,
  "../../../fixtures/backtests/m3-a-share-long-short-v1.json",
));


test("typed client maps the M8 catalog and deterministic notebook routes", async () => {
  const requests = [];
  const client = new FetchQuantDomainRevisionClient({
    baseUrl: "http://quant-domain.test",
    async stageText() { throw new Error("not used"); },
    async stageJson() { throw new Error("not used"); },
    async postCommand() { throw new Error("not used"); },
  }, async (input, init = {}) => {
    requests.push({ url: String(input), init });
    if (String(input).endsWith("/v1/strategies")) {
      return Response.json({ schema_version: 1, strategies: STRATEGIES });
    }
    if (String(input).endsWith(`/v1/strategies/${STRATEGY_IDS[0]}/notebook`)) {
      return Response.json(NOTEBOOK);
    }
    throw new Error(`unexpected request ${String(input)}`);
  });

  assert.deepEqual(await client.listBuiltInStrategies(), STRATEGIES);
  assert.deepEqual(
    await client.renderStrategyNotebook(STRATEGY_IDS[0], STRATEGIES[0].source_body),
    NOTEBOOK,
  );
  assert.equal(requests[0].init.headers.Accept, "application/json");
  assert.equal(requests[1].init.method, "POST");
  assert.equal(requests[1].init.headers["Content-Type"], "application/json");
  assert.equal(
    requests[1].init.body,
    JSON.stringify({ source: STRATEGIES[0].source_body }),
  );
});


test("browser facade exposes the M8 catalog and notebook render to the SPA", async () => {
  const calls = [];
  const server = createOqsBrowserServer({
    activeSessionId: SESSION_ID,
    registry: {
      status(sessionId) {
        return sessionId === SESSION_ID
          ? {
              sessionId,
              projectId: PROJECT_ID,
              activityId: ACTIVITY_ID,
              activeWorkbenchId: "code",
              isStreaming: false,
            }
          : undefined;
      },
      get() { return undefined; },
    },
    revisionClient: {
      async listBuiltInStrategies() {
        calls.push(["catalog"]);
        return STRATEGIES;
      },
      async renderStrategyNotebook(strategyId, source) {
        calls.push(["notebook", strategyId, source]);
        return NOTEBOOK;
      },
      async listVariants() {
        return [{
          variant_id: VARIANT_ID,
          project_id: PROJECT_ID,
          activity_id: ACTIVITY_ID,
          head_revision_id: REVISION_ID,
          version: 1,
        }];
      },
      async createRevisionChild(request) {
        calls.push(["child", request]);
        return {
          disposition: "accepted",
          event: { payload: { revision_id: REVISION_ID } },
        };
      },
    },
    formalRunFixture: FIXTURE,
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  const baseUrl = `http://127.0.0.1:${address.port}`;
  try {
    const catalog = await fetch(`${baseUrl}/api/v1/strategies`);
    assert.equal(catalog.status, 200);
    assert.deepEqual(await catalog.json(), { strategies: STRATEGIES });

    const rendered = await fetch(
      `${baseUrl}/api/v1/strategies/${STRATEGY_IDS[0]}/notebook`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: STRATEGIES[0].source_body }),
      },
    );
    assert.equal(rendered.status, 200);
    assert.deepEqual(await rendered.json(), NOTEBOOK);

    const child = await fetch(
      `${baseUrl}/api/v1/variants/${VARIANT_ID}/revisions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "Edit strategy.py",
          files: [{ path: "strategy.py", body: STRATEGIES[0].source_body }],
          removed_paths: ["strategy.ipynb"],
        }),
      },
    );
    assert.equal(child.status, 200);
    await child.json();
    assert.deepEqual(calls, [
      ["catalog"],
      ["notebook", STRATEGY_IDS[0], STRATEGIES[0].source_body],
      ["child", {
        projectId: PROJECT_ID,
        activityId: ACTIVITY_ID,
        sessionId: SESSION_ID,
        workbenchId: "code",
        variantId: VARIANT_ID,
        baseRevisionId: REVISION_ID,
        expectedRevisionId: REVISION_ID,
        message: "Edit strategy.py",
        files: [{ path: "strategy.py", body: STRATEGIES[0].source_body }],
        removedPaths: ["strategy.ipynb"],
      }],
    ]);
  } finally {
    server.close();
    await once(server, "close");
  }
});
