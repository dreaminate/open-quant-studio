import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  M5_COMMAND_TYPES,
  M5_EVENT_TYPES,
  validateDiagnosticCommand,
  validateDiagnosticEvent,
  validateDiagnosticLogListReadModel,
  validateFormalRunCommand,
  validateFormalRunEvent,
  validateFormalRunDetailReadModel,
  validateFormalRunListReadModel,
  validateFormalRunManifestV1,
  validateForwardTestCommand,
  validateForwardTestEvent,
  validateForwardTestReadModel,
  validateProjectArchiveCommand,
  validateProjectArchiveEvent,
  validateProjectArchiveManifestV1,
  validateTypedCommandEnvelope,
  validateTypedEventEnvelope,
} from "../dist/index.js";

const fixturesDir = join(import.meta.dirname, "../fixtures/v1");
const fixture = (name) =>
  JSON.parse(readFileSync(join(fixturesDir, name), "utf8"));

test("M5 registries expose the bounded lifecycle surfaces", () => {
  assert.deepEqual([...M5_COMMAND_TYPES].sort(), [
    "diagnostic.log_delete",
    "diagnostic.log_retention_configure",
    "formal.run_cancel",
    "formal.run_request",
    "formal.run_retry",
    "forward_test.request",
    "project.archive_import",
  ]);
  assert.deepEqual([...M5_EVENT_TYPES].sort(), [
    "diagnostic.logs_deleted",
    "diagnostic.retention_applied",
    "formal.run_cancelled",
    "formal.run_checkpointed",
    "formal.run_completed",
    "formal.run_prepared",
    "formal.run_queued",
    "formal.run_resumed",
    "formal.run_retried",
    "formal.run_started",
    "forward_test.completed",
    "project.archive_imported",
  ]);
});

test("M5 Formal Run request, cancel, retry, lifecycle and cancelled terminal are strict", () => {
  const request = fixture("command.formal-run-request-m5.valid.json");
  const cancel = fixture("command.formal-run-cancel.valid.json");
  const retry = fixture("command.formal-run-retry.valid.json");
  const checkpoint = fixture("event.formal-run-checkpointed.valid.json");
  const cancelled = fixture("event.formal-run-cancelled.valid.json");
  const completed = fixture("event.formal-run-completed-m5.valid.json");

  for (const value of [request, cancel, retry]) {
    assert.equal(validateFormalRunCommand(value).valid, true);
    assert.equal(validateTypedCommandEnvelope(value).valid, true);
  }
  for (const value of [checkpoint, cancelled, completed]) {
    assert.equal(validateFormalRunEvent(value).valid, true);
    assert.equal(validateTypedEventEnvelope(value).valid, true);
  }

  assert.equal(
    validateFormalRunCommand(
      fixture("command.formal-run-request.valid.json"),
    ).valid,
    false,
    "the all-bars M3 request is not an M5 execution path",
  );

  const reused = structuredClone(retry);
  reused.payload.run_id = reused.payload.source_run_id;
  assert.deepEqual(validateFormalRunCommand(reused), {
    valid: false,
    errors: ["/payload/run_id must differ from /payload/source_run_id"],
  });

  const retriedEvent = structuredClone(checkpoint);
  retriedEvent.event_type = "formal.run_retried";
  retriedEvent.payload = {
    lifecycle_version: "m5-v1",
    job_id: checkpoint.payload.job_id,
    run_spec_id: checkpoint.payload.run_spec_id,
    run_id: retry.payload.run_id,
    validation_id: checkpoint.payload.validation_id,
    candidate_revision_id: retry.base_revision_id,
    run_spec_hash:
      "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    execution_version: 0,
    source_run_id: retry.payload.run_id,
  };
  assert.deepEqual(validateFormalRunEvent(retriedEvent), {
    valid: false,
    errors: ["/payload/run_id must differ from /payload/source_run_id"],
  });

  const failedCancellation = structuredClone(cancelled);
  failedCancellation.payload.status = "failed";
  assert.equal(validateFormalRunEvent(failedCancellation).valid, false);
  const resultBearingCancellation = structuredClone(cancelled);
  resultBearingCancellation.payload.engine_result_artifact_id =
    "99999999-9999-4999-8999-999999999999";
  assert.equal(validateFormalRunEvent(resultBearingCancellation).valid, false);
});

test("M5 Formal Run manifest binds streamed market input, frozen intents, checkpoints, and result", () => {
  const manifest = fixture("formal-run-manifest-m5.valid.json");
  assert.equal(validateFormalRunManifestV1(manifest).valid, true);

  const crossedBatch = structuredClone(manifest);
  crossedBatch.checkpoint.checkpoint_batch_size += 1;
  assert.deepEqual(validateFormalRunManifestV1(crossedBatch), {
    valid: false,
    errors: [
      "/checkpoint/checkpoint_batch_size must match /run_spec/checkpoint_batch_size",
    ],
  });

  const unresolvedInput = structuredClone(manifest);
  unresolvedInput.engine_input = structuredClone(manifest.resolved_engine_input);
  assert.equal(validateFormalRunManifestV1(unresolvedInput).valid, false);
});

test("M5 diagnostics expose stable identities and content-free deletion receipts", () => {
  const remove = fixture("command.diagnostic-log-delete.valid.json");
  const configure = fixture("command.diagnostic-retention-configure.valid.json");
  const deleted = fixture("event.diagnostic-logs-deleted.valid.json");

  assert.equal(validateDiagnosticCommand(remove).valid, true);
  assert.equal(validateDiagnosticCommand(configure).valid, true);
  assert.equal(validateDiagnosticEvent(deleted).valid, true);
  assert.equal(validateTypedCommandEnvelope(remove).valid, true);
  assert.equal(validateTypedEventEnvelope(deleted).valid, true);
  assert.equal(
    validateDiagnosticLogListReadModel({
      logs: [fixture("diagnostic-log.valid.json")],
      next_after_log_seq: 42,
    }).valid,
    true,
  );

  for (const leakedField of ["query", "message", "body", "deleted_log_ids"]) {
    const leaked = structuredClone(deleted);
    leaked.payload[leakedField] = leakedField === "deleted_log_ids" ? [] : "secret";
    assert.equal(validateDiagnosticEvent(leaked).valid, false, leakedField);
  }
});

test("M5 archive import is staged-CAS only and preserves project identity", () => {
  const manifest = fixture("project-archive-manifest.valid.json");
  const command = fixture("command.project-archive-import.valid.json");
  const event = fixture("event.project-archive-imported.valid.json");

  assert.equal(validateProjectArchiveManifestV1(manifest).valid, true);
  assert.equal(validateProjectArchiveCommand(command).valid, true);
  assert.equal(validateProjectArchiveEvent(event).valid, true);
  assert.equal(validateTypedCommandEnvelope(command).valid, true);
  assert.equal(validateTypedEventEnvelope(event).valid, true);

  const crossed = structuredClone(command);
  crossed.payload.expected_project_id =
    "99999999-9999-4999-8999-999999999999";
  assert.deepEqual(validateProjectArchiveCommand(crossed), {
    valid: false,
    errors: ["/payload/expected_project_id must match /project_id"],
  });
  const rawPath = structuredClone(command);
  rawPath.payload.archive_path = "/tmp/foreign.oqs.zip";
  assert.equal(validateProjectArchiveCommand(rawPath).valid, false);

  const duplicate = structuredClone(manifest);
  duplicate.cas_objects.push(structuredClone(duplicate.cas_objects[0]));
  assert.equal(validateProjectArchiveManifestV1(duplicate).valid, false);
});

test("M5 Forward Test only references one immutable source Run", () => {
  const command = fixture("command.forward-test-request.valid.json");
  const event = fixture("event.forward-test-completed.valid.json");
  assert.equal(validateForwardTestCommand(command).valid, true);
  assert.equal(validateForwardTestEvent(event).valid, true);
  assert.equal(
    validateForwardTestReadModel(fixture("forward-test-read-model.valid.json"))
      .valid,
    true,
  );
  assert.equal(validateTypedCommandEnvelope(command).valid, true);
  assert.equal(validateTypedEventEnvelope(event).valid, true);

  for (const forbiddenField of [
    "bars",
    "strategy_source",
    "engine_input",
    "host_path",
    "url",
    "lease_token",
    "pi_session_path",
  ]) {
    const unsafe = structuredClone(command);
    unsafe.payload[forbiddenField] = forbiddenField === "bars" ? [] : "unsafe";
    assert.equal(validateForwardTestCommand(unsafe).valid, false, forbiddenField);
  }
});

function m5RunSpec() {
  return {
    run_spec_id: "17171717-1717-4171-8171-171717171717",
    project_id: "22222222-2222-4222-8222-222222222222",
    activity_id: "33333333-3333-4333-8333-333333333333",
    variant_id: "55555555-5555-4555-8555-555555555555",
    candidate_revision_id: "77777777-7777-4777-8777-777777777777",
    market_input_artifact_id: "21212121-2121-4121-8121-212121212121",
    data_snapshot_id: "23232323-2323-4232-8232-232323232323",
    data_snapshot_sha256: "a".repeat(64),
    strategy_tree_oid: "c".repeat(40),
    parameters_sha256: "d".repeat(64),
    cost_model_sha256: "e".repeat(64),
    environment_lock_sha256: "f".repeat(64),
    engine_version: "oqs-quant-engine/0.1.0",
    price_basis: "raw",
    cutoff: "2026-01-01T00:00:00Z",
    timezone: "Asia/Shanghai",
    sample_start: "2026-01-02T00:00:00Z",
    sample_end: "2026-01-07T23:59:59Z",
    random_seed: 0,
    output_schema_version: 1,
    gate_policy_version: "m5-v1",
    strategy_protocol_version: "oqs-strategy-host/m5-stream-v2",
    checkpoint_batch_size: 256,
    engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v1",
    spec_hash: "b".repeat(64),
    created_at: "2026-08-12T02:00:00Z",
  };
}

function activeRun(status) {
  const running = status === "running";
  return {
    run_id: "18181818-1818-4181-8181-181818181818",
    run_spec_id: "17171717-1717-4171-8171-171717171717",
    project_id: "22222222-2222-4222-8222-222222222222",
    activity_id: "33333333-3333-4333-8333-333333333333",
    variant_id: "55555555-5555-4555-8555-555555555555",
    candidate_revision_id: "77777777-7777-4777-8777-777777777777",
    status,
    engine_result_artifact_id: null,
    manifest_artifact_id: null,
    calculation_hash: null,
    error_code: null,
    queued_at: "2026-08-12T02:00:00Z",
    started_at: running ? "2026-08-12T02:01:00Z" : null,
    finished_at: null,
    execution_version: running ? 3 : 0,
    checkpoint_seq: running ? 4 : 0,
    next_bar_index: running ? 1024 : 0,
    retry_of_run_id: null,
    validation_id: "19191919-1919-4191-8191-191919191919",
    validation_outcome: "not_run",
    gates: { contract: "not_run", strategy_import: "not_run", smoke_run: "not_run" },
  };
}

test("M5 Run reads keep pending, running and cancelled states visible", () => {
  const pending = activeRun("pending");
  const running = activeRun("running");
  const cancelled = {
    ...running,
    status: "cancelled",
    finished_at: "2026-08-12T02:02:00Z",
    execution_version: 4,
    cancel_reason: "user_requested",
  };
  assert.equal(validateFormalRunListReadModel({ runs: [pending, running, cancelled] }).valid, true);

  const detail = {
    run: {
      ...cancelled,
      job_id: "25252525-2525-4252-8252-252525252525",
      job_finished_at: "2026-08-12T02:02:00Z",
    },
    run_spec: m5RunSpec(),
    validation: {
      validation_id: cancelled.validation_id,
      gate_policy_version: "m5-v1",
      engine_version: "oqs-quant-engine/0.1.0",
      gates: cancelled.gates,
      outcome: "not_run",
      manifest_artifact_id: null,
      created_at: "2026-08-12T02:02:00Z",
    },
    artifacts: {},
    manifest: null,
    engine_result: null,
    intent_tape: null,
    logs: [],
  };
  const detailValidation = validateFormalRunDetailReadModel(detail);
  assert.equal(detailValidation.valid, true, JSON.stringify(detailValidation));

  const hiddenAsFailure = structuredClone(detail);
  hiddenAsFailure.run.status = "failed";
  assert.equal(validateFormalRunDetailReadModel(hiddenAsFailure).valid, false);
  const resultBearing = structuredClone(detail);
  resultBearing.run.engine_result_artifact_id =
    "99999999-9999-4999-8999-999999999999";
  assert.equal(validateFormalRunDetailReadModel(resultBearing).valid, false);
});
