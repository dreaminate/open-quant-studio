CREATE TABLE data_snapshots (
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
    schema_version INTEGER NOT NULL CHECK (schema_version IN (1, 2)),
    mapping_json TEXT NOT NULL CHECK (json_valid(mapping_json)),
    sample_start TEXT NOT NULL,
    sample_end TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count BETWEEN 1 AND 250000),
    session_count INTEGER NOT NULL CHECK (session_count BETWEEN 1 AND 250000),
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (project_id, snapshot_id)
    CHECK (
        (schema_version = 1 AND symbol IS NOT NULL AND json_array_length(symbols_json) = 1) OR
        (schema_version = 2 AND symbol IS NULL AND json_array_length(symbols_json) >= 2)
    )
) STRICT;

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
