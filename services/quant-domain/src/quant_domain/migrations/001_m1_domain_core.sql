CREATE TABLE IF NOT EXISTS research_projects (
    project_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS activities (
    activity_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    created_at TEXT NOT NULL,
    UNIQUE (activity_id, project_id)
) STRICT;

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    media_type TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    storage_uri TEXT NOT NULL,
    producing_revision_id TEXT,
    producing_run_id TEXT,
    origin_kind TEXT NOT NULL CHECK (
        origin_kind IN ('fixture', 'user_upload', 'service_generated')
    ),
    source_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (sha256, storage_uri)
) STRICT;

CREATE TABLE IF NOT EXISTS context_items (
    context_item_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    title TEXT NOT NULL,
    trust_state TEXT NOT NULL CHECK (trust_state = 'raw_evidence'),
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    created_at TEXT NOT NULL,
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id)
) STRICT;

CREATE TABLE IF NOT EXISTS domain_events (
    stream_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    event_type TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    session_id TEXT,
    workbench_id TEXT,
    correlation_id TEXT NOT NULL,
    causation_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    variant_id TEXT,
    base_revision_id TEXT,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id)
) STRICT;

CREATE TRIGGER IF NOT EXISTS domain_events_forbid_update
BEFORE UPDATE ON domain_events
BEGIN
    SELECT RAISE(ABORT, 'domain_events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS domain_events_forbid_delete
BEFORE DELETE ON domain_events
BEGIN
    SELECT RAISE(ABORT, 'domain_events are immutable');
END;

CREATE TABLE IF NOT EXISTS outbox (
    outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE REFERENCES domain_events(event_id),
    stream_seq INTEGER NOT NULL UNIQUE REFERENCES domain_events(stream_seq),
    recorded_at TEXT NOT NULL,
    delivered_at TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS command_receipts (
    command_id TEXT PRIMARY KEY,
    command_hash TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE REFERENCES domain_events(event_id),
    receipt_json TEXT NOT NULL CHECK (json_valid(receipt_json)),
    recorded_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    command_id TEXT NOT NULL UNIQUE REFERENCES command_receipts(command_id),
    job_type TEXT NOT NULL CHECK (job_type = 'artifact.verify_sha256'),
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    session_id TEXT,
    workbench_id TEXT,
    correlation_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
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
        REFERENCES activities(activity_id, project_id)
) STRICT;

CREATE INDEX IF NOT EXISTS jobs_pending_idx
ON jobs(status, created_at, job_id);

CREATE TABLE IF NOT EXISTS diagnostic_logs (
    log_id TEXT PRIMARY KEY,
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

CREATE INDEX IF NOT EXISTS diagnostic_logs_filter_idx
ON diagnostic_logs(project_id, level, priority, timestamp);
