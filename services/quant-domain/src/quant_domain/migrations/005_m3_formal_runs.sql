DROP INDEX jobs_pending_idx;

ALTER TABLE jobs RENAME TO jobs_m1;

CREATE TABLE jobs (
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
        status IN ('pending', 'running', 'succeeded', 'failed')
    ),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
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
         candidate_revision_id IS NULL) OR
        (job_type = 'formal.run' AND
         run_spec_id IS NOT NULL AND run_id IS NOT NULL AND
         validation_id IS NOT NULL AND candidate_revision_id IS NOT NULL)
    )
) STRICT;

INSERT INTO jobs(
    job_id, command_id, job_type, project_id, activity_id, session_id,
    workbench_id, correlation_id, artifact_id, status, attempts,
    result_json, error_code, error_message, created_at, started_at, finished_at
)
SELECT
    job_id, command_id, job_type, project_id, activity_id, session_id,
    workbench_id, correlation_id, artifact_id, status, attempts,
    result_json, error_code, error_message, created_at, started_at, finished_at
FROM jobs_m1;

DROP TABLE jobs_m1;

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

CREATE TABLE run_specs (
    run_spec_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    candidate_revision_id TEXT NOT NULL,
    engine_input_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
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
    output_schema_version INTEGER NOT NULL CHECK (output_schema_version = 1),
    gate_policy_version TEXT NOT NULL CHECK (gate_policy_version = 'm3-v1'),
    spec_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    FOREIGN KEY (variant_id, project_id, activity_id)
        REFERENCES strategy_variants(variant_id, project_id, activity_id),
    FOREIGN KEY (candidate_revision_id, project_id, activity_id)
        REFERENCES workspace_revisions(revision_id, project_id, activity_id)
) STRICT;

CREATE TABLE workspace_merge_candidates (
    candidate_revision_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    project_parent_revision_id TEXT NOT NULL,
    variant_parent_revision_id TEXT NOT NULL,
    expected_project_head_version INTEGER NOT NULL CHECK (
        expected_project_head_version >= 0
    ),
    expected_variant_head_version INTEGER NOT NULL CHECK (
        expected_variant_head_version >= 0
    ),
    created_by_command_id TEXT NOT NULL UNIQUE REFERENCES command_receipts(command_id),
    created_at TEXT NOT NULL,
    UNIQUE (candidate_revision_id, project_id, activity_id),
    FOREIGN KEY (candidate_revision_id, project_id, activity_id)
        REFERENCES workspace_revisions(revision_id, project_id, activity_id),
    FOREIGN KEY (variant_id, project_id, activity_id)
        REFERENCES strategy_variants(variant_id, project_id, activity_id),
    FOREIGN KEY (project_parent_revision_id, project_id)
        REFERENCES workspace_revisions(revision_id, project_id),
    FOREIGN KEY (variant_parent_revision_id, project_id, activity_id)
        REFERENCES workspace_revisions(revision_id, project_id, activity_id),
    CHECK (project_parent_revision_id != variant_parent_revision_id)
) STRICT;

CREATE TABLE formal_runs (
    run_id TEXT PRIMARY KEY,
    run_spec_id TEXT NOT NULL REFERENCES run_specs(run_spec_id),
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    candidate_revision_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed')),
    engine_result_artifact_id TEXT REFERENCES artifacts(artifact_id),
    manifest_artifact_id TEXT REFERENCES artifacts(artifact_id),
    calculation_hash TEXT,
    error_code TEXT,
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
         error_code IS NULL) OR
        (status = 'failed' AND engine_result_artifact_id IS NULL AND
         manifest_artifact_id IS NULL AND calculation_hash IS NULL AND
         error_code IS NOT NULL)
    )
) STRICT;

CREATE TABLE run_artifacts (
    run_id TEXT NOT NULL REFERENCES formal_runs(run_id),
    kind TEXT NOT NULL CHECK (kind IN ('intent_tape', 'engine_result', 'manifest')),
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    PRIMARY KEY (run_id, kind),
    UNIQUE (run_id, artifact_id)
) STRICT;

CREATE TABLE merge_validations (
    validation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    candidate_revision_id TEXT NOT NULL,
    run_id TEXT NOT NULL UNIQUE REFERENCES formal_runs(run_id),
    gate_policy_version TEXT NOT NULL CHECK (gate_policy_version = 'm3-v1'),
    engine_version TEXT NOT NULL,
    contract_outcome TEXT NOT NULL CHECK (contract_outcome IN ('passed', 'failed')),
    strategy_import_outcome TEXT NOT NULL CHECK (
        strategy_import_outcome IN ('passed', 'failed')
    ),
    smoke_run_outcome TEXT NOT NULL CHECK (smoke_run_outcome IN ('passed', 'failed')),
    outcome TEXT NOT NULL CHECK (outcome IN ('passed', 'failed')),
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
        outcome = 'failed'
    )
) STRICT;

CREATE TABLE revision_promotion_validations (
    promotion_id TEXT PRIMARY KEY REFERENCES revision_promotions(promotion_id),
    validation_id TEXT NOT NULL UNIQUE REFERENCES merge_validations(validation_id),
    created_at TEXT NOT NULL
) STRICT;

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

CREATE TRIGGER workspace_merge_candidates_forbid_update
BEFORE UPDATE ON workspace_merge_candidates
BEGIN
    SELECT RAISE(ABORT, 'workspace_merge_candidates are immutable');
END;

CREATE TRIGGER workspace_merge_candidates_forbid_delete
BEFORE DELETE ON workspace_merge_candidates
BEGIN
    SELECT RAISE(ABORT, 'workspace_merge_candidates are immutable');
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
