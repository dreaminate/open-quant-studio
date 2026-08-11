CREATE TABLE workspace_revisions (
    revision_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    variant_id TEXT,
    base_revision_id TEXT,
    git_commit_oid TEXT NOT NULL CHECK (
        length(git_commit_oid) = 40 AND
        git_commit_oid NOT GLOB '*[^0-9a-f]*'
    ),
    git_tree_oid TEXT NOT NULL CHECK (
        length(git_tree_oid) = 40 AND
        git_tree_oid NOT GLOB '*[^0-9a-f]*'
    ),
    message TEXT NOT NULL,
    created_by_session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (revision_id, project_id),
    UNIQUE (revision_id, project_id, activity_id),
    UNIQUE (git_commit_oid, project_id),
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    FOREIGN KEY (created_by_session_id, project_id, activity_id)
        REFERENCES agent_sessions(session_id, project_id, activity_id),
    FOREIGN KEY (base_revision_id, project_id, activity_id)
        REFERENCES workspace_revisions(revision_id, project_id, activity_id),
    FOREIGN KEY (variant_id, project_id, activity_id)
        REFERENCES strategy_variants(variant_id, project_id, activity_id),
    CHECK (
        (variant_id IS NULL AND base_revision_id IS NULL) OR
        (variant_id IS NOT NULL AND base_revision_id IS NOT NULL)
    )
) STRICT;

CREATE TABLE strategy_variants (
    variant_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    base_revision_id TEXT NOT NULL,
    created_by_session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (variant_id, project_id, activity_id),
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    FOREIGN KEY (base_revision_id, project_id, activity_id)
        REFERENCES workspace_revisions(revision_id, project_id, activity_id),
    FOREIGN KEY (created_by_session_id, project_id, activity_id)
        REFERENCES agent_sessions(session_id, project_id, activity_id)
) STRICT;

CREATE TABLE strategy_variant_heads (
    variant_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    head_revision_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 0),
    updated_at TEXT NOT NULL,
    FOREIGN KEY (variant_id, project_id, activity_id)
        REFERENCES strategy_variants(variant_id, project_id, activity_id),
    FOREIGN KEY (head_revision_id, project_id, activity_id)
        REFERENCES workspace_revisions(revision_id, project_id, activity_id)
) STRICT;

CREATE TABLE project_revision_heads (
    project_id TEXT PRIMARY KEY REFERENCES research_projects(project_id),
    head_revision_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 0),
    updated_at TEXT NOT NULL,
    FOREIGN KEY (head_revision_id, project_id)
        REFERENCES workspace_revisions(revision_id, project_id)
) STRICT;

CREATE TABLE project_revision_head_history (
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    head_revision_id TEXT NOT NULL,
    head_version INTEGER NOT NULL CHECK (head_version >= 0),
    command_id TEXT NOT NULL UNIQUE REFERENCES command_receipts(command_id),
    event_id TEXT NOT NULL UNIQUE REFERENCES domain_events(event_id),
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (project_id, head_revision_id),
    UNIQUE (project_id, head_version),
    FOREIGN KEY (head_revision_id, project_id)
        REFERENCES workspace_revisions(revision_id, project_id)
) STRICT;

CREATE TABLE revision_files (
    revision_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    path TEXT NOT NULL,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    git_blob_oid TEXT NOT NULL CHECK (
        length(git_blob_oid) = 40 AND
        git_blob_oid NOT GLOB '*[^0-9a-f]*'
    ),
    PRIMARY KEY (revision_id, path),
    FOREIGN KEY (revision_id, project_id, activity_id)
        REFERENCES workspace_revisions(revision_id, project_id, activity_id)
) STRICT;

CREATE TABLE revision_promotions (
    promotion_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    previous_revision_id TEXT NOT NULL,
    promoted_revision_id TEXT NOT NULL,
    previous_head_version INTEGER NOT NULL CHECK (previous_head_version >= 0),
    resulting_head_version INTEGER NOT NULL CHECK (
        resulting_head_version = previous_head_version + 1
    ),
    command_id TEXT NOT NULL UNIQUE REFERENCES command_receipts(command_id),
    event_id TEXT NOT NULL UNIQUE REFERENCES domain_events(event_id),
    created_at TEXT NOT NULL,
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    FOREIGN KEY (variant_id, project_id, activity_id)
        REFERENCES strategy_variants(variant_id, project_id, activity_id),
    FOREIGN KEY (previous_revision_id, project_id)
        REFERENCES workspace_revisions(revision_id, project_id),
    FOREIGN KEY (promoted_revision_id, project_id)
        REFERENCES workspace_revisions(revision_id, project_id)
) STRICT;

CREATE INDEX revision_files_artifact_idx
ON revision_files(artifact_id, revision_id);

CREATE TRIGGER workspace_revisions_forbid_update
BEFORE UPDATE ON workspace_revisions
BEGIN
    SELECT RAISE(ABORT, 'workspace_revisions are immutable');
END;

CREATE TRIGGER workspace_revisions_forbid_delete
BEFORE DELETE ON workspace_revisions
BEGIN
    SELECT RAISE(ABORT, 'workspace_revisions are immutable');
END;

CREATE TRIGGER strategy_variants_forbid_update
BEFORE UPDATE ON strategy_variants
BEGIN
    SELECT RAISE(ABORT, 'strategy_variants are immutable');
END;

CREATE TRIGGER strategy_variants_forbid_delete
BEFORE DELETE ON strategy_variants
BEGIN
    SELECT RAISE(ABORT, 'strategy_variants are immutable');
END;

CREATE TRIGGER revision_files_forbid_update
BEFORE UPDATE ON revision_files
BEGIN
    SELECT RAISE(ABORT, 'revision_files are immutable');
END;

CREATE TRIGGER revision_files_forbid_delete
BEFORE DELETE ON revision_files
BEGIN
    SELECT RAISE(ABORT, 'revision_files are immutable');
END;

CREATE TRIGGER revision_promotions_forbid_update
BEFORE UPDATE ON revision_promotions
BEGIN
    SELECT RAISE(ABORT, 'revision_promotions are immutable');
END;

CREATE TRIGGER revision_promotions_forbid_delete
BEFORE DELETE ON revision_promotions
BEGIN
    SELECT RAISE(ABORT, 'revision_promotions are immutable');
END;

CREATE TRIGGER project_revision_head_history_forbid_update
BEFORE UPDATE ON project_revision_head_history
BEGIN
    SELECT RAISE(ABORT, 'project revision head history is immutable');
END;

CREATE TRIGGER project_revision_head_history_forbid_delete
BEFORE DELETE ON project_revision_head_history
BEGIN
    SELECT RAISE(ABORT, 'project revision head history is immutable');
END;

CREATE TRIGGER strategy_variant_heads_forbid_delete
BEFORE DELETE ON strategy_variant_heads
BEGIN
    SELECT RAISE(ABORT, 'strategy_variant_heads cannot be deleted');
END;

CREATE TRIGGER project_revision_heads_forbid_delete
BEFORE DELETE ON project_revision_heads
BEGIN
    SELECT RAISE(ABORT, 'project_revision_heads cannot be deleted');
END;
