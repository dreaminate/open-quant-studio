-- Widen the immutable merge-validation tables for the opt-in A-share v3 gate.
-- Database.migrate runs this bounded rebuild with foreign-key enforcement
-- temporarily disabled, then verifies and restores the SQLite invariant.

DROP TRIGGER merge_validations_forbid_update;
DROP TRIGGER merge_validations_forbid_delete;
DROP TRIGGER revision_promotion_validations_forbid_update;
DROP TRIGGER revision_promotion_validations_forbid_delete;

CREATE TABLE merge_validations_v3 (
    validation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    candidate_revision_id TEXT NOT NULL,
    run_id TEXT NOT NULL UNIQUE REFERENCES formal_runs(run_id),
    gate_policy_version TEXT NOT NULL CHECK (
        gate_policy_version IN ('m3-v1', 'm5-v1', 'm8-v1', 'a-share-v3')
    ),
    engine_version TEXT NOT NULL,
    contract_outcome TEXT NOT NULL CHECK (
        contract_outcome IN ('passed', 'failed', 'not_run')
    ),
    strategy_import_outcome TEXT NOT NULL CHECK (
        strategy_import_outcome IN ('passed', 'failed', 'not_run')
    ),
    smoke_run_outcome TEXT NOT NULL CHECK (
        smoke_run_outcome IN ('passed', 'failed', 'not_run')
    ),
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

INSERT INTO merge_validations_v3(
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

CREATE TABLE revision_promotion_validations_v3 (
    promotion_id TEXT PRIMARY KEY REFERENCES revision_promotions(promotion_id),
    validation_id TEXT NOT NULL UNIQUE REFERENCES merge_validations_v3(validation_id),
    created_at TEXT NOT NULL
) STRICT;

INSERT INTO revision_promotion_validations_v3(promotion_id, validation_id, created_at)
SELECT promotion_id, validation_id, created_at
FROM revision_promotion_validations;

DROP TABLE revision_promotion_validations;
DROP TABLE merge_validations;

ALTER TABLE merge_validations_v3 RENAME TO merge_validations;
ALTER TABLE revision_promotion_validations_v3 RENAME TO revision_promotion_validations;

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
