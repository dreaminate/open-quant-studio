-- A-share v3 review evidence is an immutable, content-addressed input to a
-- Formal Run.  Legacy RunSpecs remain nullable and unchanged.

CREATE TABLE review_attestations (
    attestation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(project_id),
    activity_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    candidate_revision_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status = 'approved'),
    strategy_tree_oid TEXT NOT NULL CHECK (
        length(strategy_tree_oid) = 40 AND
        strategy_tree_oid NOT GLOB '*[^0-9a-f]*'
    ),
    data_snapshot_sha256 TEXT NOT NULL CHECK (
        length(data_snapshot_sha256) = 64 AND
        data_snapshot_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    parameters_sha256 TEXT NOT NULL CHECK (
        length(parameters_sha256) = 64 AND
        parameters_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    cost_model_sha256 TEXT NOT NULL CHECK (
        length(cost_model_sha256) = 64 AND
        cost_model_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    reviewer_id TEXT NOT NULL CHECK (length(reviewer_id) BETWEEN 1 AND 256),
    reviewed_at TEXT NOT NULL,
    attestation_sha256 TEXT NOT NULL CHECK (
        length(attestation_sha256) = 64 AND
        attestation_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    attestation_json TEXT NOT NULL CHECK (json_valid(attestation_json)),
    created_at TEXT NOT NULL,
    UNIQUE (attestation_sha256),
    FOREIGN KEY (activity_id, project_id)
        REFERENCES activities(activity_id, project_id),
    FOREIGN KEY (variant_id, project_id, activity_id)
        REFERENCES strategy_variants(variant_id, project_id, activity_id),
    FOREIGN KEY (candidate_revision_id, project_id, activity_id)
        REFERENCES workspace_revisions(revision_id, project_id, activity_id)
) STRICT;

CREATE TRIGGER review_attestations_forbid_update
BEFORE UPDATE ON review_attestations
BEGIN
    SELECT RAISE(ABORT, 'review_attestations are immutable');
END;

CREATE TRIGGER review_attestations_forbid_delete
BEFORE DELETE ON review_attestations
BEGIN
    SELECT RAISE(ABORT, 'review_attestations are immutable');
END;

ALTER TABLE run_specs
    ADD COLUMN review_attestation_id TEXT
    REFERENCES review_attestations(attestation_id);
ALTER TABLE run_specs
    ADD COLUMN review_attestation_sha256 TEXT;
ALTER TABLE run_specs
    ADD COLUMN review_attestation_json TEXT
    CHECK (review_attestation_json IS NULL OR json_valid(review_attestation_json));

CREATE TRIGGER run_specs_v3_review_attestation_required
BEFORE INSERT ON run_specs
WHEN NEW.gate_policy_version = 'a-share-v3'
 AND (NEW.review_attestation_id IS NULL
      OR NEW.review_attestation_sha256 IS NULL
      OR NEW.review_attestation_json IS NULL)
BEGIN
    SELECT RAISE(ABORT, 'a-share-v3 RunSpecs require an approved review attestation');
END;
