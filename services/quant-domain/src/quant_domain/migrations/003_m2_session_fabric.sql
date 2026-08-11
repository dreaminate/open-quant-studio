CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    pi_session_id TEXT NOT NULL,
    session_uri TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (project_id, pi_session_id),
    UNIQUE (session_id, project_id, activity_id),
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id)
) STRICT;

CREATE TABLE IF NOT EXISTS workbench_bindings (
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    workbench_id TEXT NOT NULL,
    is_active INTEGER NOT NULL CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, activity_id, session_id, workbench_id),
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    FOREIGN KEY (session_id, project_id, activity_id)
        REFERENCES agent_sessions(session_id, project_id, activity_id)
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS workbench_bindings_one_active_idx
ON workbench_bindings(project_id, activity_id, session_id)
WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS session_messages (
    message_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    sender_session_id TEXT NOT NULL,
    recipient_session_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    message_kind TEXT NOT NULL CHECK (message_kind IN ('send', 'ask', 'reply')),
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    reply_to TEXT,
    source_refs_json TEXT NOT NULL CHECK (json_valid(source_refs_json)),
    created_at TEXT NOT NULL,
    UNIQUE (message_id, project_id, activity_id),
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    FOREIGN KEY (sender_session_id, project_id, activity_id)
        REFERENCES agent_sessions(session_id, project_id, activity_id),
    FOREIGN KEY (recipient_session_id, project_id, activity_id)
        REFERENCES agent_sessions(session_id, project_id, activity_id),
    FOREIGN KEY (reply_to, project_id, activity_id)
        REFERENCES session_messages(message_id, project_id, activity_id)
) STRICT;

CREATE INDEX IF NOT EXISTS session_messages_inbox_idx
ON session_messages(project_id, activity_id, recipient_session_id, created_at, message_id);

CREATE TABLE IF NOT EXISTS message_receipts (
    message_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('queued', 'receiver_received', 'injected', 'acknowledged')),
    version INTEGER NOT NULL CHECK (version >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    FOREIGN KEY (message_id, project_id, activity_id)
        REFERENCES session_messages(message_id, project_id, activity_id)
) STRICT;

CREATE TABLE IF NOT EXISTS message_receipt_transitions (
    transition_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    from_state TEXT NOT NULL CHECK (from_state IN ('queued', 'receiver_received', 'injected')),
    to_state TEXT NOT NULL CHECK (to_state IN ('receiver_received', 'injected', 'acknowledged')),
    expected_version INTEGER NOT NULL CHECK (expected_version >= 0),
    resulting_version INTEGER NOT NULL CHECK (resulting_version = expected_version + 1),
    command_id TEXT NOT NULL UNIQUE REFERENCES command_receipts(command_id),
    event_id TEXT NOT NULL UNIQUE REFERENCES domain_events(event_id),
    created_at TEXT NOT NULL,
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    FOREIGN KEY (message_id, project_id, activity_id)
        REFERENCES session_messages(message_id, project_id, activity_id),
    CHECK (
        (from_state = 'queued' AND to_state = 'receiver_received') OR
        (from_state = 'receiver_received' AND to_state = 'injected') OR
        (from_state = 'injected' AND to_state = 'acknowledged')
    )
) STRICT;

CREATE INDEX IF NOT EXISTS message_receipts_inbox_idx
ON message_receipts(project_id, activity_id, state, updated_at, message_id);

CREATE TRIGGER agent_sessions_forbid_update
BEFORE UPDATE ON agent_sessions
BEGIN
    SELECT RAISE(ABORT, 'agent_sessions are immutable');
END;

CREATE TRIGGER agent_sessions_forbid_delete
BEFORE DELETE ON agent_sessions
BEGIN
    SELECT RAISE(ABORT, 'agent_sessions are immutable');
END;

CREATE TRIGGER session_messages_forbid_update
BEFORE UPDATE ON session_messages
BEGIN
    SELECT RAISE(ABORT, 'session_messages are immutable');
END;

CREATE TRIGGER session_messages_forbid_delete
BEFORE DELETE ON session_messages
BEGIN
    SELECT RAISE(ABORT, 'session_messages are immutable');
END;

CREATE TRIGGER message_receipt_transitions_forbid_update
BEFORE UPDATE ON message_receipt_transitions
BEGIN
    SELECT RAISE(ABORT, 'message_receipt_transitions are immutable');
END;

CREATE TRIGGER message_receipt_transitions_forbid_delete
BEFORE DELETE ON message_receipt_transitions
BEGIN
    SELECT RAISE(ABORT, 'message_receipt_transitions are immutable');
END;

CREATE TRIGGER artifacts_forbid_delete
BEFORE DELETE ON artifacts
BEGIN
    SELECT RAISE(ABORT, 'artifacts are immutable');
END;
