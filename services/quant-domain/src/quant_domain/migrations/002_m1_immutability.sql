CREATE TRIGGER artifacts_forbid_update
BEFORE UPDATE ON artifacts
BEGIN
    SELECT RAISE(ABORT, 'artifacts are immutable');
END;

CREATE TRIGGER context_items_forbid_update
BEFORE UPDATE ON context_items
BEGIN
    SELECT RAISE(ABORT, 'context_items are immutable');
END;
