import assert from "node:assert/strict";
import test from "node:test";

import {
  validateActivityListReadModel,
  validateArtifactMetadataReadModel,
  validateFormalEngineResultV1,
  validateFormalRunDetailReadModel,
  validateFormalRunListReadModel,
  validateFormalRunManifestV1,
  validateProjectListReadModel,
} from "../dist/index.js";


const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const ACTIVITY_ID = "33333333-3333-4333-8333-333333333333";
const VARIANT_ID = "20202020-2020-4020-8020-202020202020";
const REVISION_ID = "40404040-4040-4040-8040-404040404040";
const RUN_SPEC_ID = "71717171-7171-4171-8171-717171717171";
const RUN_ID = "72727272-7272-4272-8272-727272727272";
const VALIDATION_ID = "73737373-7373-4373-8373-737373737373";
const JOB_ID = "74747474-7474-4474-8474-747474747474";
const INPUT_ARTIFACT_ID = "75757575-7575-4575-8575-757575757575";
const INTENT_ARTIFACT_ID = "76767676-7676-4676-8676-767676767676";
const RESULT_ARTIFACT_ID = "77777777-7777-4777-8777-777777777777";
const MANIFEST_ARTIFACT_ID = "78787878-7878-4878-8878-787878787878";
const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const HASH_C = "c".repeat(64);
const CREATED_AT = "2026-08-12T00:00:00Z";

function artifact({ artifactId, sha256, kind, mediaType = "application/json" }) {
  return {
    artifact_id: artifactId,
    project_id: PROJECT_ID,
    sha256,
    media_type: mediaType,
    byte_size: 128,
    storage_uri: `cas://sha256/${sha256}`,
    producing_revision_id: null,
    producing_run_id: null,
    origin_kind: "service_generated",
    source_ref: VALIDATION_ID,
    created_at: CREATED_AT,
    revision_paths: [],
    run_kinds: kind === undefined ? [] : [{ run_id: RUN_ID, kind }],
  };
}

function diagnosticLog(overrides = {}) {
  return {
    timestamp: CREATED_AT,
    level: "info",
    priority: "p2",
    component: "quant-domain",
    event_code: "formal.run.completed",
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    session_id: null,
    task_id: null,
    job_id: JOB_ID,
    run_id: RUN_ID,
    correlation_id: "81818181-8181-4181-8181-818181818181",
    message: "Formal Run completed",
    ...overrides,
  };
}

function engineResult() {
  return {
    schema_version: 1,
    engine_version: "oqs-quant-engine/0.1.0",
    account_model: "a_share_cash",
    orders: [],
    trades: [],
    positions: [],
    cash_ledger: [],
    funding_ledger: [],
    equity_curve: [],
    drawdown_curve: [],
    metrics: {
      starting_equity_atoms: "1000000",
      ending_equity_atoms: "1025534",
      net_pnl_atoms: "25534",
      total_return_rate_atoms: "25534",
      max_drawdown_atoms: "0",
      max_drawdown_rate_atoms: "0",
      total_fees_atoms: "248",
      total_stamp_duty_atoms: "218",
      total_funding_atoms: "0",
      total_slippage_atoms: "4000",
      fill_count: 4,
      closed_trade_count: 2,
      open_position_count: 0,
    },
    costs: {
      commission_atoms: "248",
      stamp_duty_atoms: "218",
      funding_atoms: "0",
      slippage_atoms: "4000",
    },
    assumptions: {
      fill_model: "ohlc_full_fill_v1",
      partial_fills: false,
      liquidate_on_end: false,
      research_short: true,
      research_short_notice: "research-only synthetic short accounting",
      one_x_notional: true,
    },
  };
}

function manifest() {
  return {
    schema_version: 1,
    manifest_version: "m3-v1",
    run_id: RUN_ID,
    validation_id: VALIDATION_ID,
    run_spec: {
      run_spec_id: RUN_SPEC_ID,
      spec_hash: HASH_C,
      project_id: PROJECT_ID,
      activity_id: ACTIVITY_ID,
      variant_id: VARIANT_ID,
      candidate_revision_id: REVISION_ID,
      data_snapshot_id: "79797979-7979-4979-8979-797979797979",
      data_snapshot_sha256: HASH_A,
      strategy_tree_oid: "a".repeat(40),
      parameters_sha256: HASH_B,
      cost_model_sha256: HASH_C,
      environment_lock_sha256: HASH_A,
      engine_version: "oqs-quant-engine/0.1.0",
      price_basis: "raw",
      cutoff: CREATED_AT,
      timezone: "Asia/Shanghai",
      sample_start: "2026-01-02T00:00:00Z",
      sample_end: "2026-01-07T23:59:59Z",
      random_seed: 0,
      output_schema_version: 1,
      gate_policy_version: "m3-v1",
    },
    revision: {
      candidate_revision_id: REVISION_ID,
      git_commit_oid: "b".repeat(40),
      git_tree_oid: "a".repeat(40),
      strategy_path: "strategy.py",
      strategy_artifact_id: "80808080-8080-4080-8080-808080808080",
      strategy_sha256: HASH_B,
      strategy_git_blob_oid: "c".repeat(40),
      project_parent_revision_id: "10101010-1010-4010-8010-101010101010",
      variant_parent_revision_id: "30303030-3030-4030-8030-303030303030",
      expected_project_head_version: 0,
      expected_variant_head_version: 1,
    },
    engine_input: {
      artifact_id: INPUT_ARTIFACT_ID,
      sha256: HASH_A,
      media_type: "application/json",
      byte_size: 1024,
      storage_uri: `cas://sha256/${HASH_A}`,
    },
    strategy_execution: {
      intent_tape_artifact_id: INTENT_ARTIFACT_ID,
      intent_tape_sha256: HASH_B,
      intent_tape_byte_size: 512,
      intent_tape_storage_uri: `cas://sha256/${HASH_B}`,
      timing_authority: "oqs-strategy-host/m3-v1",
    },
    engine_result: {
      artifact_id: RESULT_ARTIFACT_ID,
      sha256: HASH_C,
      media_type: "application/json",
      byte_size: 2048,
      storage_uri: `cas://sha256/${HASH_C}`,
      schema_version: 1,
      engine_version: "oqs-quant-engine/0.1.0",
    },
    gates: {
      contract: "passed",
      strategy_import: "passed",
      smoke_run: "passed",
    },
    logs: {
      run_id: RUN_ID,
      deletable: true,
      included_in_calculation_hash: false,
    },
  };
}

function runSpec() {
  return {
    run_spec_id: RUN_SPEC_ID,
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    variant_id: VARIANT_ID,
    candidate_revision_id: REVISION_ID,
    engine_input_artifact_id: INPUT_ARTIFACT_ID,
    data_snapshot_id: "79797979-7979-4979-8979-797979797979",
    data_snapshot_sha256: HASH_A,
    strategy_tree_oid: "a".repeat(40),
    parameters_sha256: HASH_B,
    cost_model_sha256: HASH_C,
    environment_lock_sha256: HASH_A,
    engine_version: "oqs-quant-engine/0.1.0",
    price_basis: "raw",
    cutoff: CREATED_AT,
    timezone: "Asia/Shanghai",
    sample_start: "2026-01-02T00:00:00Z",
    sample_end: "2026-01-07T23:59:59Z",
    random_seed: 0,
    output_schema_version: 1,
    gate_policy_version: "m3-v1",
    spec_hash: HASH_C,
    created_at: CREATED_AT,
  };
}

function runRecord(status = "succeeded") {
  const succeeded = status === "succeeded";
  return {
    run_id: RUN_ID,
    run_spec_id: RUN_SPEC_ID,
    project_id: PROJECT_ID,
    activity_id: ACTIVITY_ID,
    variant_id: VARIANT_ID,
    candidate_revision_id: REVISION_ID,
    status,
    engine_result_artifact_id: succeeded ? RESULT_ARTIFACT_ID : null,
    manifest_artifact_id: succeeded ? MANIFEST_ARTIFACT_ID : null,
    calculation_hash: succeeded ? HASH_C : null,
    error_code: succeeded ? null : "strategy_import_failed",
    finished_at: CREATED_AT,
    job_id: JOB_ID,
    queued_at: CREATED_AT,
    started_at: CREATED_AT,
    job_finished_at: CREATED_AT,
  };
}

function validation(status = "succeeded") {
  const succeeded = status === "succeeded";
  return {
    validation_id: VALIDATION_ID,
    gate_policy_version: "m3-v1",
    engine_version: "oqs-quant-engine/0.1.0",
    gates: {
      contract: "passed",
      strategy_import: succeeded ? "passed" : "failed",
      smoke_run: succeeded ? "passed" : "failed",
    },
    outcome: succeeded ? "passed" : "failed",
    manifest_artifact_id: succeeded ? MANIFEST_ARTIFACT_ID : null,
    created_at: CREATED_AT,
  };
}

function succeededDetail() {
  return {
    run: runRecord(),
    run_spec: runSpec(),
    validation: validation(),
    artifacts: {
      intent_tape: artifact({
        artifactId: INTENT_ARTIFACT_ID,
        sha256: HASH_B,
        kind: "intent_tape",
        mediaType: "application/vnd.open-quant-studio.order-intents+json",
      }),
      engine_result: artifact({
        artifactId: RESULT_ARTIFACT_ID,
        sha256: HASH_C,
        kind: "engine_result",
      }),
      manifest: artifact({
        artifactId: MANIFEST_ARTIFACT_ID,
        sha256: HASH_A,
        kind: "manifest",
        mediaType: "application/vnd.open-quant-studio.formal-run-manifest+json",
      }),
    },
    manifest: manifest(),
    engine_result: engineResult(),
    intent_tape: [],
    logs: [],
  };
}

test("M4 validates current Project, Activity, artifact, engine, manifest, and Run reads", () => {
  assert.equal(validateProjectListReadModel({
    projects: [{ project_id: PROJECT_ID, created_at: CREATED_AT }],
  }).valid, true);
  assert.equal(validateActivityListReadModel({
    activities: [{
      activity_id: ACTIVITY_ID,
      project_id: PROJECT_ID,
      created_at: CREATED_AT,
    }],
  }).valid, true);
  assert.equal(validateArtifactMetadataReadModel(artifact({
    artifactId: RESULT_ARTIFACT_ID,
    sha256: HASH_C,
    kind: "engine_result",
  })).valid, true);
  assert.equal(validateFormalEngineResultV1(engineResult()).valid, true);
  assert.equal(validateFormalRunManifestV1(manifest()).valid, true);

  const detail = succeededDetail();
  assert.equal(validateFormalRunDetailReadModel(detail).valid, true);
  const listedRun = runRecord();
  delete listedRun.job_id;
  delete listedRun.queued_at;
  delete listedRun.started_at;
  delete listedRun.job_finished_at;
  assert.equal(validateFormalRunListReadModel({
    runs: [{
      ...listedRun,
      validation_id: VALIDATION_ID,
      validation_outcome: "passed",
      gates: validation().gates,
    }],
  }).valid, true);

  const failed = {
    run: runRecord("failed"),
    run_spec: runSpec(),
    validation: validation("failed"),
    artifacts: {},
    manifest: null,
    engine_result: null,
    intent_tape: null,
    logs: [],
  };
  assert.equal(validateFormalRunDetailReadModel(failed).valid, true);
});

test("M4 read artifact metadata never accepts command ArtifactRef provenance", () => {
  const invalid = artifact({
    artifactId: RESULT_ARTIFACT_ID,
    sha256: HASH_C,
    kind: "engine_result",
  });
  delete invalid.origin_kind;
  delete invalid.source_ref;
  invalid.provenance = {
    origin_kind: "service_generated",
    source_ref: VALIDATION_ID,
  };
  assert.equal(validateArtifactMetadataReadModel(invalid).valid, false);
});

test("M4 Run unions reject succeeded-null and failed-result states", () => {
  const invalidList = {
    runs: [{
      ...runRecord(),
      engine_result_artifact_id: null,
      validation_id: VALIDATION_ID,
      validation_outcome: "passed",
      gates: validation().gates,
    }],
  };
  assert.equal(validateFormalRunListReadModel(invalidList).valid, false);

  const invalidDetail = succeededDetail();
  invalidDetail.run = runRecord("failed");
  invalidDetail.validation = validation("failed");
  assert.equal(validateFormalRunDetailReadModel(invalidDetail).valid, false);
});

test("M4 Run details reject crossed log project, Activity, Run, and job identity", () => {
  const crossedId = "99999999-9999-4999-8999-999999999999";
  const succeeded = succeededDetail();
  succeeded.logs = [diagnosticLog({ activity_id: crossedId })];
  assert.equal(validateFormalRunDetailReadModel(succeeded).valid, false);

  const failed = {
    run: runRecord("failed"),
    run_spec: runSpec(),
    validation: validation("failed"),
    artifacts: {},
    manifest: null,
    engine_result: null,
    intent_tape: null,
    logs: [diagnosticLog({
      project_id: crossedId,
      activity_id: crossedId,
      run_id: crossedId,
      job_id: crossedId,
    })],
  };
  assert.equal(validateFormalRunDetailReadModel(failed).valid, false);
});

test("M4 formal engine Atom values remain canonical decimal strings", () => {
  const invalid = engineResult();
  invalid.metrics.ending_equity_atoms = 1025534;
  assert.equal(validateFormalEngineResultV1(invalid).valid, false);
});

test("M4 Run detail rejects a manifest engine identity mismatch", () => {
  const invalid = succeededDetail();
  invalid.manifest.engine_result.sha256 = HASH_B;
  assert.deepEqual(validateFormalRunDetailReadModel(invalid), {
    valid: false,
    errors: [
      "/manifest/engine_result/sha256 must match /run/calculation_hash",
    ],
  });
});
