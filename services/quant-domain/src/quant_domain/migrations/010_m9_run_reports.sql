DROP TRIGGER run_artifacts_forbid_update;
DROP TRIGGER run_artifacts_forbid_delete;

CREATE TABLE run_artifacts_m9 (
    run_id TEXT NOT NULL REFERENCES formal_runs(run_id),
    kind TEXT NOT NULL CHECK (
        kind IN (
            'intent_tape',
            'engine_result',
            'manifest',
            'report_json',
            'report_html'
        )
    ),
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    PRIMARY KEY (run_id, kind),
    UNIQUE (run_id, artifact_id)
) STRICT;

INSERT INTO run_artifacts_m9(run_id, kind, artifact_id)
SELECT run_id, kind, artifact_id FROM run_artifacts;

DROP TABLE run_artifacts;
ALTER TABLE run_artifacts_m9 RENAME TO run_artifacts;

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
