DROP TRIGGER run_specs_forbid_update;
DROP TRIGGER run_specs_forbid_delete;
DROP TRIGGER formal_runs_forbid_update;
DROP TRIGGER formal_runs_forbid_delete;
DROP TRIGGER run_artifacts_forbid_update;
DROP TRIGGER run_artifacts_forbid_delete;
DROP TRIGGER merge_validations_forbid_update;
DROP TRIGGER merge_validations_forbid_delete;
DROP TRIGGER revision_promotion_validations_forbid_update;
DROP TRIGGER revision_promotion_validations_forbid_delete;

INSERT INTO formal_runs(
    run_id, run_spec_id, project_id, activity_id, variant_id,
    candidate_revision_id, status, engine_result_artifact_id,
    manifest_artifact_id, calculation_hash, error_code, finished_at
)
SELECT
    j.run_id, j.run_spec_id, j.project_id, j.activity_id, rs.variant_id,
    j.candidate_revision_id, 'failed', NULL, NULL, NULL,
    'worker_interrupted_by_m5_upgrade',
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
FROM jobs AS j
JOIN run_specs AS rs ON rs.run_spec_id = j.run_spec_id
WHERE j.job_type = 'formal.run'
  AND (
      j.status = 'running' OR
      (j.status = 'failed' AND j.error_code = 'worker_interrupted_by_upgrade')
  )
  AND NOT EXISTS (
      SELECT 1 FROM formal_runs AS existing WHERE existing.run_id = j.run_id
  );

INSERT INTO merge_validations(
    validation_id, project_id, activity_id, variant_id,
    candidate_revision_id, run_id, gate_policy_version, engine_version,
    contract_outcome, strategy_import_outcome, smoke_run_outcome, outcome,
    manifest_artifact_id, created_at
)
SELECT
    j.validation_id, j.project_id, j.activity_id, rs.variant_id,
    j.candidate_revision_id, j.run_id, rs.gate_policy_version,
    rs.engine_version, 'failed', 'failed', 'failed', 'failed', NULL,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
FROM jobs AS j
JOIN run_specs AS rs ON rs.run_spec_id = j.run_spec_id
WHERE j.job_type = 'formal.run'
  AND (
      j.status = 'running' OR
      (j.status = 'failed' AND j.error_code = 'worker_interrupted_by_upgrade')
  )
  AND NOT EXISTS (
      SELECT 1
      FROM merge_validations AS existing
      WHERE existing.validation_id = j.validation_id
         OR existing.run_id = j.run_id
  );

UPDATE jobs
SET status = 'failed',
    error_code = 'worker_interrupted_by_m5_upgrade',
    error_message = 'Formal Run interrupted by M5 worker upgrade',
    finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE job_type = 'formal.run'
  AND (
      status = 'running' OR
      (status = 'failed' AND error_code = 'worker_interrupted_by_upgrade')
  );

CREATE TABLE run_specs_m5 (
    run_spec_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    candidate_revision_id TEXT NOT NULL,
    engine_input_artifact_id TEXT REFERENCES artifacts(artifact_id),
    market_input_artifact_id TEXT REFERENCES artifacts(artifact_id),
    data_snapshot_id TEXT NOT NULL,
    data_snapshot_sha256 TEXT NOT NULL,
    strategy_tree_oid TEXT NOT NULL,
    parameters_sha256 TEXT NOT NULL,
    cost_model_sha256 TEXT NOT NULL,
    environment_lock_sha256 TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    price_basis TEXT NOT NULL CHECK (price_basis IN ('raw', 'qfq', 'hfq')),
    cutoff TEXT NOT NULL,
    timezone TEXT NOT NULL,
    sample_start TEXT NOT NULL,
    sample_end TEXT NOT NULL,
    random_seed INTEGER NOT NULL CHECK (random_seed >= 0),
    output_schema_version INTEGER NOT NULL CHECK (output_schema_version IN (1, 2)),
    gate_policy_version TEXT NOT NULL CHECK (gate_policy_version IN ('m3-v1', 'm5-v1', 'm8-v1')),
    strategy_protocol_version TEXT,
    checkpoint_batch_size INTEGER CHECK (
        checkpoint_batch_size IS NULL OR checkpoint_batch_size BETWEEN 1 AND 250000
    ),
    engine_checkpoint_abi TEXT,
    spec_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    FOREIGN KEY (variant_id, project_id, activity_id)
        REFERENCES strategy_variants(variant_id, project_id, activity_id),
    FOREIGN KEY (candidate_revision_id, project_id, activity_id)
        REFERENCES workspace_revisions(revision_id, project_id, activity_id),
    CHECK (
        (gate_policy_version = 'm3-v1' AND
         engine_input_artifact_id IS NOT NULL AND market_input_artifact_id IS NULL AND
         strategy_protocol_version IS NULL AND checkpoint_batch_size IS NULL AND
         engine_checkpoint_abi IS NULL) OR
        (gate_policy_version = 'm5-v1' AND
         engine_input_artifact_id IS NULL AND market_input_artifact_id IS NOT NULL AND
         strategy_protocol_version = 'oqs-strategy-host/m5-stream-v2' AND
         checkpoint_batch_size IS NOT NULL AND
         engine_checkpoint_abi = 'oqs-quant-engine/checkpoint-v1') OR
        (gate_policy_version = 'm8-v1' AND
         engine_input_artifact_id IS NULL AND market_input_artifact_id IS NOT NULL AND
         engine_version = 'oqs-quant-engine/0.2.0' AND output_schema_version = 2 AND
         strategy_protocol_version = 'oqs-strategy-host/m8-portfolio-v1' AND
         checkpoint_batch_size IS NOT NULL AND
         engine_checkpoint_abi = 'oqs-quant-engine/checkpoint-v2')
    )
) STRICT;

INSERT INTO run_specs_m5(
    run_spec_id, project_id, activity_id, variant_id, candidate_revision_id,
    engine_input_artifact_id, market_input_artifact_id, data_snapshot_id,
    data_snapshot_sha256, strategy_tree_oid, parameters_sha256,
    cost_model_sha256, environment_lock_sha256, engine_version, price_basis,
    cutoff, timezone, sample_start, sample_end, random_seed,
    output_schema_version, gate_policy_version, strategy_protocol_version,
    checkpoint_batch_size, engine_checkpoint_abi, spec_hash, created_at
)
SELECT
    run_spec_id, project_id, activity_id, variant_id, candidate_revision_id,
    engine_input_artifact_id, NULL, data_snapshot_id, data_snapshot_sha256,
    strategy_tree_oid, parameters_sha256, cost_model_sha256,
    environment_lock_sha256, engine_version, price_basis, cutoff, timezone,
    sample_start, sample_end, random_seed, output_schema_version,
    gate_policy_version, NULL, NULL, NULL, spec_hash, created_at
FROM run_specs;

CREATE TABLE jobs_m5 (
    job_id TEXT PRIMARY KEY,
    command_id TEXT NOT NULL UNIQUE REFERENCES command_receipts(command_id),
    job_type TEXT NOT NULL CHECK (
        job_type IN ('artifact.verify_sha256', 'formal.run')
    ),
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    session_id TEXT,
    workbench_id TEXT,
    correlation_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    run_spec_id TEXT,
    run_id TEXT,
    validation_id TEXT,
    candidate_revision_id TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')
    ),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    execution_version INTEGER NOT NULL DEFAULT 0 CHECK (execution_version >= 0),
    claim_epoch INTEGER NOT NULL DEFAULT 0 CHECK (claim_epoch >= 0),
    claim_token TEXT UNIQUE,
    lease_expires_at TEXT,
    checkpoint_seq INTEGER NOT NULL DEFAULT 0 CHECK (checkpoint_seq >= 0),
    next_bar_index INTEGER NOT NULL DEFAULT 0 CHECK (next_bar_index >= 0),
    checkpoint_artifact_id TEXT REFERENCES artifacts(artifact_id),
    calculation_context_sha256 TEXT,
    retry_of_run_id TEXT,
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    CHECK (
        (job_type = 'artifact.verify_sha256' AND
         run_spec_id IS NULL AND run_id IS NULL AND validation_id IS NULL AND
         candidate_revision_id IS NULL AND execution_version = 0 AND
         claim_epoch = 0 AND claim_token IS NULL AND lease_expires_at IS NULL AND
         checkpoint_seq = 0 AND next_bar_index = 0 AND
         checkpoint_artifact_id IS NULL AND calculation_context_sha256 IS NULL AND
         retry_of_run_id IS NULL) OR
        (job_type = 'formal.run' AND
         run_spec_id IS NOT NULL AND run_id IS NOT NULL AND
         validation_id IS NOT NULL AND candidate_revision_id IS NOT NULL)
    ),
    CHECK (
        job_type != 'formal.run' OR
        (status = 'running' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR
        (status != 'running' AND claim_token IS NULL AND lease_expires_at IS NULL)
    ),
    CHECK (
        job_type != 'formal.run' OR
        (checkpoint_seq = 0 AND next_bar_index = 0 AND
         checkpoint_artifact_id IS NULL AND calculation_context_sha256 IS NULL) OR
        (checkpoint_seq > 0 AND next_bar_index > 0 AND
         checkpoint_artifact_id IS NOT NULL AND calculation_context_sha256 IS NOT NULL)
    )
) STRICT;

INSERT INTO jobs_m5(
    job_id, command_id, job_type, project_id, activity_id, session_id,
    workbench_id, correlation_id, artifact_id, run_spec_id, run_id,
    validation_id, candidate_revision_id, status, attempts, execution_version,
    claim_epoch, claim_token, lease_expires_at, checkpoint_seq, next_bar_index,
    checkpoint_artifact_id, calculation_context_sha256, retry_of_run_id,
    result_json, error_code, error_message, created_at, started_at, finished_at
)
SELECT
    job_id, command_id, job_type, project_id, activity_id, session_id,
    workbench_id, correlation_id, artifact_id, run_spec_id, run_id,
    validation_id, candidate_revision_id, status, attempts,
    CASE WHEN job_type = 'formal.run' THEN attempts ELSE 0 END,
    CASE WHEN job_type = 'formal.run' THEN attempts ELSE 0 END,
    NULL, NULL, 0, 0, NULL, NULL, NULL, result_json, error_code,
    error_message, created_at, started_at, finished_at
FROM jobs;

CREATE TABLE formal_runs_m5 (
    run_id TEXT PRIMARY KEY,
    run_spec_id TEXT NOT NULL REFERENCES run_specs_m5(run_spec_id),
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    candidate_revision_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed', 'cancelled')),
    execution_version INTEGER NOT NULL CHECK (execution_version >= 1),
    retry_of_run_id TEXT REFERENCES formal_runs_m5(run_id),
    engine_result_artifact_id TEXT REFERENCES artifacts(artifact_id),
    manifest_artifact_id TEXT REFERENCES artifacts(artifact_id),
    calculation_hash TEXT,
    error_code TEXT,
    cancel_reason TEXT,
    finished_at TEXT NOT NULL,
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    FOREIGN KEY (variant_id, project_id, activity_id)
        REFERENCES strategy_variants(variant_id, project_id, activity_id),
    FOREIGN KEY (candidate_revision_id, project_id, activity_id)
        REFERENCES workspace_revisions(revision_id, project_id, activity_id),
    CHECK (
        (status = 'succeeded' AND engine_result_artifact_id IS NOT NULL AND
         manifest_artifact_id IS NOT NULL AND calculation_hash IS NOT NULL AND
         error_code IS NULL AND cancel_reason IS NULL) OR
        (status = 'failed' AND engine_result_artifact_id IS NULL AND
         manifest_artifact_id IS NULL AND calculation_hash IS NULL AND
         error_code IS NOT NULL AND cancel_reason IS NULL) OR
        (status = 'cancelled' AND engine_result_artifact_id IS NULL AND
         manifest_artifact_id IS NULL AND calculation_hash IS NULL AND
         error_code IS NULL AND cancel_reason = 'user_requested')
    )
) STRICT;

INSERT INTO formal_runs_m5(
    run_id, run_spec_id, project_id, activity_id, variant_id,
    candidate_revision_id, status, execution_version, retry_of_run_id,
    engine_result_artifact_id, manifest_artifact_id, calculation_hash,
    error_code, cancel_reason, finished_at
)
SELECT
    r.run_id, r.run_spec_id, r.project_id, r.activity_id, r.variant_id,
    r.candidate_revision_id, r.status, MAX(1, j.attempts), NULL,
    r.engine_result_artifact_id, r.manifest_artifact_id, r.calculation_hash,
    r.error_code, NULL, r.finished_at
FROM formal_runs AS r
JOIN jobs AS j ON j.run_id = r.run_id;

CREATE TABLE run_artifacts_m5 (
    run_id TEXT NOT NULL REFERENCES formal_runs_m5(run_id),
    kind TEXT NOT NULL CHECK (kind IN ('intent_tape', 'engine_result', 'manifest')),
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    PRIMARY KEY (run_id, kind),
    UNIQUE (run_id, artifact_id)
) STRICT;

INSERT INTO run_artifacts_m5(run_id, kind, artifact_id)
SELECT run_id, kind, artifact_id FROM run_artifacts;

CREATE TABLE merge_validations_m5 (
    validation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    candidate_revision_id TEXT NOT NULL,
    run_id TEXT NOT NULL UNIQUE REFERENCES formal_runs_m5(run_id),
    gate_policy_version TEXT NOT NULL CHECK (gate_policy_version IN ('m3-v1', 'm5-v1', 'm8-v1')),
    engine_version TEXT NOT NULL,
    contract_outcome TEXT NOT NULL CHECK (contract_outcome IN ('passed', 'failed', 'not_run')),
    strategy_import_outcome TEXT NOT NULL CHECK (strategy_import_outcome IN ('passed', 'failed', 'not_run')),
    smoke_run_outcome TEXT NOT NULL CHECK (smoke_run_outcome IN ('passed', 'failed', 'not_run')),
    outcome TEXT NOT NULL CHECK (outcome IN ('passed', 'failed', 'not_run')),
    manifest_artifact_id TEXT REFERENCES artifacts(artifact_id),
    created_at TEXT NOT NULL,
    FOREIGN KEY (candidate_revision_id, project_id, activity_id)
        REFERENCES workspace_merge_candidates(candidate_revision_id, project_id, activity_id),
    FOREIGN KEY (variant_id, project_id, activity_id)
        REFERENCES strategy_variants(variant_id, project_id, activity_id),
    CHECK (
        (outcome = 'passed' AND contract_outcome = 'passed' AND
         strategy_import_outcome = 'passed' AND smoke_run_outcome = 'passed' AND
         manifest_artifact_id IS NOT NULL) OR
        (outcome = 'failed' AND manifest_artifact_id IS NULL) OR
        (outcome = 'not_run' AND contract_outcome = 'not_run' AND
         strategy_import_outcome = 'not_run' AND smoke_run_outcome = 'not_run' AND
         manifest_artifact_id IS NULL)
    )
) STRICT;

INSERT INTO merge_validations_m5(
    validation_id, project_id, activity_id, variant_id,
    candidate_revision_id, run_id, gate_policy_version, engine_version,
    contract_outcome, strategy_import_outcome, smoke_run_outcome, outcome,
    manifest_artifact_id, created_at
)
SELECT
    validation_id, project_id, activity_id, variant_id,
    candidate_revision_id, run_id, gate_policy_version, engine_version,
    contract_outcome, strategy_import_outcome, smoke_run_outcome, outcome,
    manifest_artifact_id, created_at
FROM merge_validations;

CREATE TABLE revision_promotion_validations_m5 (
    promotion_id TEXT PRIMARY KEY REFERENCES revision_promotions(promotion_id),
    validation_id TEXT NOT NULL UNIQUE REFERENCES merge_validations_m5(validation_id),
    created_at TEXT NOT NULL
) STRICT;

INSERT INTO revision_promotion_validations_m5(promotion_id, validation_id, created_at)
SELECT promotion_id, validation_id, created_at
FROM revision_promotion_validations;

DROP TABLE revision_promotion_validations;
DROP TABLE merge_validations;
DROP TABLE run_artifacts;
DROP TABLE formal_runs;
DROP INDEX jobs_pending_idx;
DROP INDEX formal_run_job_run_idx;
DROP INDEX formal_run_job_validation_idx;
DROP INDEX formal_run_job_active_candidate_idx;
DROP INDEX jobs_single_running_formal_idx;
DROP TABLE jobs;
DROP TABLE run_specs;

ALTER TABLE run_specs_m5 RENAME TO run_specs;
ALTER TABLE jobs_m5 RENAME TO jobs;
ALTER TABLE formal_runs_m5 RENAME TO formal_runs;
ALTER TABLE run_artifacts_m5 RENAME TO run_artifacts;
ALTER TABLE merge_validations_m5 RENAME TO merge_validations;
ALTER TABLE revision_promotion_validations_m5 RENAME TO revision_promotion_validations;

CREATE INDEX jobs_pending_idx
ON jobs(status, created_at, job_id);

CREATE UNIQUE INDEX formal_run_job_run_idx
ON jobs(run_id)
WHERE run_id IS NOT NULL;

CREATE UNIQUE INDEX formal_run_job_validation_idx
ON jobs(validation_id)
WHERE validation_id IS NOT NULL;

CREATE UNIQUE INDEX formal_run_job_active_candidate_idx
ON jobs(candidate_revision_id)
WHERE job_type = 'formal.run' AND status IN ('pending', 'running');

CREATE UNIQUE INDEX jobs_single_running_formal_idx
ON jobs((1))
WHERE job_type = 'formal.run' AND status = 'running';

CREATE TABLE formal_run_preparations (
    job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),
    intent_tape_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    resolved_engine_input_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    calculation_context_sha256 TEXT NOT NULL,
    total_bar_count INTEGER NOT NULL CHECK (total_bar_count BETWEEN 1 AND 250000),
    prepared_at TEXT NOT NULL
) STRICT;

CREATE TABLE formal_run_checkpoints (
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    checkpoint_seq INTEGER NOT NULL CHECK (checkpoint_seq >= 1),
    next_bar_index INTEGER NOT NULL CHECK (next_bar_index >= 1),
    execution_version INTEGER NOT NULL CHECK (execution_version >= 1),
    claim_epoch INTEGER NOT NULL CHECK (claim_epoch >= 1),
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    calculation_context_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (job_id, checkpoint_seq),
    UNIQUE (job_id, artifact_id)
) STRICT;

CREATE TRIGGER formal_run_preparations_forbid_update
BEFORE UPDATE ON formal_run_preparations
BEGIN
    SELECT RAISE(ABORT, 'formal_run_preparations are immutable');
END;

CREATE TRIGGER formal_run_preparations_forbid_delete
BEFORE DELETE ON formal_run_preparations
BEGIN
    SELECT RAISE(ABORT, 'formal_run_preparations are immutable');
END;

CREATE TRIGGER formal_run_checkpoints_forbid_update
BEFORE UPDATE ON formal_run_checkpoints
BEGIN
    SELECT RAISE(ABORT, 'formal_run_checkpoints are immutable');
END;

CREATE TRIGGER formal_run_checkpoints_forbid_delete
BEFORE DELETE ON formal_run_checkpoints
BEGIN
    SELECT RAISE(ABORT, 'formal_run_checkpoints are immutable');
END;

CREATE TRIGGER run_specs_forbid_update
BEFORE UPDATE ON run_specs
BEGIN
    SELECT RAISE(ABORT, 'run_specs are immutable');
END;

CREATE TRIGGER run_specs_forbid_delete
BEFORE DELETE ON run_specs
BEGIN
    SELECT RAISE(ABORT, 'run_specs are immutable');
END;

CREATE TRIGGER formal_runs_forbid_update
BEFORE UPDATE ON formal_runs
BEGIN
    SELECT RAISE(ABORT, 'formal_runs are immutable');
END;

CREATE TRIGGER formal_runs_forbid_delete
BEFORE DELETE ON formal_runs
BEGIN
    SELECT RAISE(ABORT, 'formal_runs are immutable');
END;

CREATE TRIGGER run_artifacts_forbid_update
BEFORE UPDATE ON run_artifacts
BEGIN
    SELECT RAISE(ABORT, 'run_artifacts are immutable');
END;

CREATE TRIGGER run_artifacts_forbid_delete
BEFORE DELETE ON run_artifacts
BEGIN
    SELECT RAISE(ABORT, 'run_artifacts are immutable');
END;

CREATE TRIGGER merge_validations_forbid_update
BEFORE UPDATE ON merge_validations
BEGIN
    SELECT RAISE(ABORT, 'merge_validations are immutable');
END;

CREATE TRIGGER merge_validations_forbid_delete
BEFORE DELETE ON merge_validations
BEGIN
    SELECT RAISE(ABORT, 'merge_validations are immutable');
END;

CREATE TRIGGER revision_promotion_validations_forbid_update
BEFORE UPDATE ON revision_promotion_validations
BEGIN
    SELECT RAISE(ABORT, 'revision_promotion_validations are immutable');
END;

CREATE TRIGGER revision_promotion_validations_forbid_delete
BEFORE DELETE ON revision_promotion_validations
BEGIN
    SELECT RAISE(ABORT, 'revision_promotion_validations are immutable');
END;

ALTER TABLE diagnostic_logs RENAME TO diagnostic_logs_m4;

CREATE TABLE diagnostic_logs (
    log_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('debug', 'info', 'warn', 'error')),
    priority TEXT NOT NULL CHECK (priority IN ('p1', 'p2', 'p3', 'p4')),
    component TEXT NOT NULL,
    event_code TEXT NOT NULL,
    project_id TEXT,
    activity_id TEXT,
    session_id TEXT,
    task_id TEXT,
    job_id TEXT,
    run_id TEXT,
    correlation_id TEXT,
    message TEXT NOT NULL
) STRICT;

INSERT INTO diagnostic_logs(
    log_id, timestamp, level, priority, component, event_code, project_id,
    activity_id, session_id, task_id, job_id, run_id, correlation_id, message
)
SELECT
    log_id, timestamp, level, priority, component, event_code, project_id,
    activity_id, session_id, task_id, job_id, run_id, correlation_id, message
FROM diagnostic_logs_m4
ORDER BY timestamp, log_id;

DROP TABLE diagnostic_logs_m4;

CREATE INDEX diagnostic_logs_filter_idx
ON diagnostic_logs(project_id, level, priority, timestamp, log_seq);

CREATE VIRTUAL TABLE diagnostic_logs_fts USING fts5(
    message,
    content='diagnostic_logs',
    content_rowid='log_seq',
    tokenize='unicode61'
);

INSERT INTO diagnostic_logs_fts(rowid, message)
SELECT log_seq, message FROM diagnostic_logs;

CREATE TRIGGER diagnostic_logs_fts_insert
AFTER INSERT ON diagnostic_logs
BEGIN
    INSERT INTO diagnostic_logs_fts(rowid, message)
    VALUES (new.log_seq, new.message);
END;

CREATE TRIGGER diagnostic_logs_fts_delete
AFTER DELETE ON diagnostic_logs
BEGIN
    INSERT INTO diagnostic_logs_fts(diagnostic_logs_fts, rowid, message)
    VALUES ('delete', old.log_seq, old.message);
END;

CREATE TABLE diagnostic_log_retention (
    project_id TEXT PRIMARY KEY REFERENCES research_projects(project_id),
    debug_days INTEGER NOT NULL CHECK (debug_days >= 0),
    info_days INTEGER NOT NULL CHECK (info_days >= 0),
    warn_days INTEGER NOT NULL CHECK (warn_days >= 0),
    quota_bytes INTEGER NOT NULL CHECK (quota_bytes >= 0),
    configured_at TEXT NOT NULL
) STRICT;

CREATE TABLE diagnostic_log_delete_receipts (
    receipt_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    reason TEXT NOT NULL CHECK (reason IN ('user', 'retention', 'quota')),
    selection_sha256 TEXT NOT NULL,
    deleted_count INTEGER NOT NULL CHECK (deleted_count >= 0),
    deleted_at TEXT NOT NULL
) STRICT;
