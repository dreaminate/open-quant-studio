CREATE TABLE forward_tests (
    forward_test_id TEXT PRIMARY KEY,
    source_run_id TEXT NOT NULL REFERENCES formal_runs(run_id),
    source_revision_id TEXT NOT NULL,
    data_snapshot_id TEXT NOT NULL,
    protocol_version TEXT NOT NULL CHECK (
        protocol_version = 'oqs-forward-replay/m5-v1'
    ),
    released_bar_count INTEGER NOT NULL CHECK (
        released_bar_count BETWEEN 0 AND 250000
    ),
    transcript_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    transcript_sha256 TEXT NOT NULL,
    intent_tape_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('passed', 'failed')),
    error_code TEXT CHECK (
        error_code IS NULL OR error_code IN (
            'source_run_not_succeeded',
            'strategy_protocol_failed',
            'transcript_integrity_mismatch'
        )
    ),
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    FOREIGN KEY (variant_id, project_id, activity_id)
        REFERENCES strategy_variants(variant_id, project_id, activity_id),
    FOREIGN KEY (source_revision_id, project_id, activity_id)
        REFERENCES workspace_revisions(revision_id, project_id, activity_id),
    CHECK (
        (status = 'passed' AND error_code IS NULL) OR
        (status = 'failed' AND error_code IS NOT NULL)
    )
) STRICT;

CREATE INDEX forward_tests_project_idx
ON forward_tests(project_id, activity_id, created_at, forward_test_id);

CREATE TRIGGER forward_tests_forbid_update
BEFORE UPDATE ON forward_tests
BEGIN
    SELECT RAISE(ABORT, 'forward_tests are immutable');
END;

CREATE TRIGGER forward_tests_forbid_delete
BEFORE DELETE ON forward_tests
BEGIN
    SELECT RAISE(ABORT, 'forward_tests are immutable');
END;
