import assert from "node:assert/strict";
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
const RUN_ID = "18181818-1818-4181-8181-181818181818";
const LOG_ID = "91919191-9191-4191-8191-919191919191";
const COMMAND_ID = "51515151-5151-4151-8151-515151515151";
const CORRELATION_ID = "44444444-4444-4444-8444-444444444444";
const FIXTURE_PATH = resolve(
  import.meta.dirname,
  "../../../fixtures/backtests/m3-a-share-long-short-v1.json",
);
const FIXTURE = await loadM4FormalRunFixture(FIXTURE_PATH);

function logPage() {
  return {
    logs: [{
      log_id: LOG_ID,
      log_seq: 42,
      timestamp: "2026-08-12T02:00:00Z",
      level: "warn",
      priority: "p2",
      component: "quant_domain",
      event_code: "diagnostic.log.viewed",
      project_id: PROJECT_ID,
      activity_id: ACTIVITY_ID,
      session_id: SESSION_ID,
      task_id: null,
      job_id: null,
      run_id: RUN_ID,
      correlation_id: CORRELATION_ID,
      message: "Normal diagnostic log",
    }],
    next_after_log_seq: null,
  };
}

function deletionReceipt(commandId = COMMAND_ID) {
  return {
    command_id: commandId,
    disposition: "accepted",
    event: {
      event_type: "diagnostic.logs_deleted",
      payload: { deleted_count: 1 },
    },
  };
}

function browserHarness() {
  const calls = [];
  const registry = {
    status(sessionId) {
      return sessionId === SESSION_ID
        ? {
            sessionId,
            projectId: PROJECT_ID,
            activityId: ACTIVITY_ID,
            activeWorkbenchId: "logs",
            isStreaming: false,
          }
        : undefined;
    },
  };
  const revisionClient = {
    async listLogs(projectId, filters) {
      calls.push(["list", projectId, filters]);
      return logPage();
    },
    async deleteLogs(request) {
      calls.push(["delete", request]);
      return deletionReceipt();
    },
  };
  return {
    calls,
    server: createOqsBrowserServer({
      activeSessionId: SESSION_ID,
      registry,
      revisionClient,
      formalRunFixture: FIXTURE,
    }),
  };
}

async function withServer(setup, run) {
  setup.server.listen(0, "127.0.0.1");
  await once(setup.server, "listening");
  const address = setup.server.address();
  const baseUrl = `http://127.0.0.1:${address.port}`;
  try {
    await run(baseUrl);
  } finally {
    setup.server.close();
    await once(setup.server, "close");
  }
}

test("browser facade maps normal log filters and returns the deletion receipt", async () => {
  const setup = browserHarness();
  await withServer(setup, async (baseUrl) => {
    const listed = await fetch(
      `${baseUrl}/api/v1/logs?run_id=${RUN_ID}&activity_id=${ACTIVITY_ID}&session_id=${SESSION_ID}&level=warn&priority=p2&query=Normal%20diagnostic&after_log_seq=41&limit=25`,
    );
    assert.equal(listed.status, 200);
    assert.deepEqual(await listed.json(), logPage());
    assert.deepEqual(setup.calls[0], ["list", PROJECT_ID, {
      runId: RUN_ID,
      activityId: ACTIVITY_ID,
      sessionId: SESSION_ID,
      level: "warn",
      priority: "p2",
      query: "Normal diagnostic",
      afterLogSeq: 41,
      limit: 25,
    }]);

    const deleted = await fetch(`${baseUrl}/api/v1/logs/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ log_ids: [LOG_ID] }),
    });
    assert.equal(deleted.status, 200);
    assert.deepEqual(await deleted.json(), deletionReceipt());
    assert.deepEqual(setup.calls[1], ["delete", {
      projectId: PROJECT_ID,
      activityId: ACTIVITY_ID,
      sessionId: SESSION_ID,
      workbenchId: "logs",
      logIds: [LOG_ID],
    }]);
  });
});

test("typed log client maps the domain query and emits a diagnostic delete command", async () => {
  const requests = [];
  const commands = [];
  const sessionClient = {
    baseUrl: "http://quant-domain.test",
    async stageText() { throw new Error("not used"); },
    async stageJson() { throw new Error("not used"); },
    async postCommand(command) {
      commands.push(command);
      return deletionReceipt(command.command_id);
    },
  };
  const client = new FetchQuantDomainRevisionClient(sessionClient, async (input, init = {}) => {
    requests.push({ url: String(input), init });
    return Response.json(logPage());
  });

  assert.deepEqual(
    await client.listLogs(PROJECT_ID, {
      runId: RUN_ID,
      activityId: ACTIVITY_ID,
      sessionId: SESSION_ID,
      level: "warn",
      priority: "p2",
      query: "Normal diagnostic",
      afterLogSeq: 41,
      limit: 25,
    }),
    logPage(),
  );
  await client.deleteLogs({
    projectId: PROJECT_ID,
    activityId: ACTIVITY_ID,
    sessionId: SESSION_ID,
    workbenchId: "logs",
    logIds: [LOG_ID],
    commandId: COMMAND_ID,
    correlationId: CORRELATION_ID,
  });

  const requestUrl = new URL(requests[0].url);
  assert.equal(requestUrl.pathname, "/v1/logs");
  assert.deepEqual(Object.fromEntries(requestUrl.searchParams), {
    project_id: PROJECT_ID,
    run_id: RUN_ID,
    activity_id: ACTIVITY_ID,
    session_id: SESSION_ID,
    level: "warn",
    priority: "p2",
    query: "Normal diagnostic",
    after_log_seq: "41",
    limit: "25",
  });
  assert.equal(requests[0].init.headers.Accept, "application/json");
  assert.deepEqual(commands, [{
    command_id: COMMAND_ID,
    schema_version: 1,
    command_type: "diagnostic.log_delete",
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    session_id: SESSION_ID,
    workbench_id: "logs",
    correlation_id: CORRELATION_ID,
    expected_revision_id: null,
    variant_id: null,
    base_revision_id: null,
    payload: { selection: { log_ids: [LOG_ID] } },
  }]);
});
