-- The v3 contract widens two immutable tables.  Database.migrate runs this
-- bounded rebuild with foreign-key enforcement temporarily disabled, then
-- verifies and restores the SQLite invariant before returning.

DROP TRIGGER run_specs_forbid_update;
DROP TRIGGER run_specs_forbid_delete;

CREATE TABLE run_specs_v3 (
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
    output_schema_version INTEGER NOT NULL CHECK (output_schema_version IN (1, 2, 3)),
    gate_policy_version TEXT NOT NULL CHECK (
        gate_policy_version IN ('m3-v1', 'm5-v1', 'm8-v1', 'a-share-v3')
    ),
    strategy_protocol_version TEXT,
    checkpoint_batch_size INTEGER CHECK (
        checkpoint_batch_size IS NULL OR checkpoint_batch_size BETWEEN 1 AND 250000
    ),
    engine_checkpoint_abi TEXT,
    execution_profile TEXT NOT NULL DEFAULT 'legacy' CHECK (
        execution_profile IN ('legacy', 'a-share-v3')
    ),
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
         execution_profile = 'legacy' AND
         engine_input_artifact_id IS NOT NULL AND market_input_artifact_id IS NULL AND
         strategy_protocol_version IS NULL AND checkpoint_batch_size IS NULL AND
         engine_checkpoint_abi IS NULL) OR
        (gate_policy_version = 'm5-v1' AND
         execution_profile = 'legacy' AND
         engine_input_artifact_id IS NULL AND market_input_artifact_id IS NOT NULL AND
         strategy_protocol_version = 'oqs-strategy-host/m5-stream-v2' AND
         checkpoint_batch_size IS NOT NULL AND
         engine_checkpoint_abi = 'oqs-quant-engine/checkpoint-v1') OR
        (gate_policy_version = 'm8-v1' AND
         execution_profile = 'legacy' AND
         engine_input_artifact_id IS NULL AND market_input_artifact_id IS NOT NULL AND
         engine_version = 'oqs-quant-engine/0.2.0' AND output_schema_version = 2 AND
         strategy_protocol_version = 'oqs-strategy-host/m8-portfolio-v1' AND
         checkpoint_batch_size IS NOT NULL AND
         engine_checkpoint_abi = 'oqs-quant-engine/checkpoint-v2') OR
        (gate_policy_version = 'a-share-v3' AND
         execution_profile = 'a-share-v3' AND
         engine_input_artifact_id IS NULL AND market_input_artifact_id IS NOT NULL AND
         engine_version = 'oqs-quant-engine/0.3.0' AND output_schema_version = 3 AND
         strategy_protocol_version = 'oqs-strategy-host/a-share-v3' AND
         checkpoint_batch_size IS NOT NULL AND
         engine_checkpoint_abi = 'oqs-quant-engine/checkpoint-v3')
    )
) STRICT;

INSERT INTO run_specs_v3(
    run_spec_id, project_id, activity_id, variant_id, candidate_revision_id,
    engine_input_artifact_id, market_input_artifact_id, data_snapshot_id,
    data_snapshot_sha256, strategy_tree_oid, parameters_sha256,
    cost_model_sha256, environment_lock_sha256, engine_version, price_basis,
    cutoff, timezone, sample_start, sample_end, random_seed,
    output_schema_version, gate_policy_version, strategy_protocol_version,
    checkpoint_batch_size, engine_checkpoint_abi, execution_profile,
    spec_hash, created_at
)
SELECT
    run_spec_id, project_id, activity_id, variant_id, candidate_revision_id,
    engine_input_artifact_id, market_input_artifact_id, data_snapshot_id,
    data_snapshot_sha256, strategy_tree_oid, parameters_sha256,
    cost_model_sha256, environment_lock_sha256, engine_version, price_basis,
    cutoff, timezone, sample_start, sample_end, random_seed,
    output_schema_version, gate_policy_version, strategy_protocol_version,
    checkpoint_batch_size, engine_checkpoint_abi, 'legacy', spec_hash, created_at
FROM run_specs;

DROP TABLE run_specs;
ALTER TABLE run_specs_v3 RENAME TO run_specs;

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

DROP TRIGGER data_snapshots_forbid_update;
DROP TRIGGER data_snapshots_forbid_delete;

CREATE TABLE data_snapshots_v3 (
    snapshot_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    source_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    normalized_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    market_input_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    market TEXT NOT NULL CHECK (market IN ('a_share_daily', 'crypto_linear_perp')),
    symbol TEXT,
    symbols_json TEXT NOT NULL CHECK (json_valid(symbols_json)),
    timezone TEXT NOT NULL,
    price_basis TEXT NOT NULL CHECK (price_basis IN ('raw', 'qfq', 'hfq')),
    cutoff TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version IN (1, 2, 3)),
    mapping_json TEXT NOT NULL CHECK (json_valid(mapping_json)),
    sample_start TEXT NOT NULL,
    sample_end TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count BETWEEN 1 AND 250000),
    session_count INTEGER NOT NULL CHECK (session_count BETWEEN 1 AND 250000),
    sha256 TEXT NOT NULL,
    execution_profile TEXT NOT NULL DEFAULT 'legacy' CHECK (
        execution_profile IN ('legacy', 'a-share-v3')
    ),
    created_at TEXT NOT NULL,
    UNIQUE (project_id, snapshot_id),
    CHECK (
        (schema_version = 1 AND execution_profile = 'legacy' AND
         symbol IS NOT NULL AND json_array_length(symbols_json) = 1) OR
        (schema_version = 2 AND execution_profile = 'legacy' AND
         symbol IS NULL AND json_array_length(symbols_json) >= 2) OR
        (schema_version = 3 AND execution_profile = 'a-share-v3' AND
         ((symbol IS NOT NULL AND json_array_length(symbols_json) = 1 AND
           json_extract(symbols_json, '$[0]') = symbol) OR
          (symbol IS NULL AND json_array_length(symbols_json) >= 2)))
    )
) STRICT;

INSERT INTO data_snapshots_v3(
    snapshot_id, project_id, source_artifact_id, normalized_artifact_id,
    market_input_artifact_id, market, symbol, symbols_json, timezone,
    price_basis, cutoff, schema_version, mapping_json, sample_start,
    sample_end, row_count, session_count, sha256, execution_profile, created_at
)
SELECT
    snapshot_id, project_id, source_artifact_id, normalized_artifact_id,
    market_input_artifact_id, market, symbol, symbols_json, timezone,
    price_basis, cutoff, schema_version, mapping_json, sample_start,
    sample_end, row_count, session_count, sha256, 'legacy', created_at
FROM data_snapshots;

DROP TABLE data_snapshots;
ALTER TABLE data_snapshots_v3 RENAME TO data_snapshots;

CREATE INDEX data_snapshots_project_idx
ON data_snapshots(project_id, created_at, snapshot_id);

CREATE TRIGGER data_snapshots_forbid_update
BEFORE UPDATE ON data_snapshots
BEGIN
    SELECT RAISE(ABORT, 'data_snapshots are immutable');
END;

CREATE TRIGGER data_snapshots_forbid_delete
BEFORE DELETE ON data_snapshots
BEGIN
    SELECT RAISE(ABORT, 'data_snapshots are immutable');
END;
