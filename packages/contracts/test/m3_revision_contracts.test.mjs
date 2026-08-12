import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  M3_COMMAND_TYPES,
  M3_EVENT_TYPES,
  validateCommandEnvelope,
  validateDomainEvent,
  validateFormalRunCommand,
  validateFormalRunEvent,
  validateRevisionCommand,
  validateRevisionEvent,
  validateStrategyVariantCreateCommand,
  validateStrategyVariantCreatedEvent,
  validateTypedCommandEnvelope,
  validateTypedEventEnvelope,
  validateWorkspaceRevisionCreateCommand,
  validateWorkspaceRevisionCreatedEvent,
  validateWorkspaceMergeCreateCommand,
  validateWorkspaceMergeCandidateCreatedEvent,
  validateWorkspaceRevisionPromoteCommand,
  validateWorkspaceRevisionPromotedEvent,
} from "../dist/index.js";

const fixturesDir = join(import.meta.dirname, "../fixtures/v1");

function fixture(name) {
  return JSON.parse(readFileSync(join(fixturesDir, name), "utf8"));
}

test("M3 registries expose every revision and variant command/event type", () => {
  assert.deepEqual([...M3_COMMAND_TYPES].sort(), [
    "formal.run_request",
    "strategy.variant_create",
    "workspace.merge_create",
    "workspace.revision_create",
    "workspace.revision_promote",
  ]);
  assert.deepEqual([...M3_EVENT_TYPES].sort(), [
    "formal.run_completed",
    "formal.run_queued",
    "formal.run_started",
    "strategy.variant_created",
    "workspace.merge_candidate_created",
    "workspace.revision_created",
    "workspace.revision_promoted",
  ]);
});

test("M3 validates typed merge candidates and Formal Run lifecycle envelopes", () => {
  const merge = fixture("command.merge-create.valid.json");
  const mergeCreated = fixture("event.merge-candidate-created.valid.json");
  const run = fixture("command.formal-run-request-m5.valid.json");
  const runQueued = fixture("event.formal-run-queued.valid.json");
  const runStarted = fixture("event.formal-run-started.valid.json");
  const runSucceeded = fixture("event.formal-run-completed-succeeded.valid.json");
  const runFailed = fixture("event.formal-run-completed-failed.valid.json");

  assert.equal(validateWorkspaceMergeCreateCommand(merge).valid, true);
  assert.equal(validateWorkspaceMergeCandidateCreatedEvent(mergeCreated).valid, true);
  assert.equal(validateFormalRunCommand(run).valid, true);
  assert.equal(validateFormalRunEvent(runQueued).valid, true);
  assert.equal(validateFormalRunEvent(runStarted).valid, true);
  assert.equal(validateFormalRunEvent(runSucceeded).valid, true);
  assert.equal(validateFormalRunEvent(runFailed).valid, true);
  assert.equal(validateTypedCommandEnvelope(run).valid, true);
  assert.equal(validateTypedEventEnvelope(runQueued).valid, true);
  assert.equal(validateTypedEventEnvelope(runSucceeded).valid, true);
  assert.equal(
    validateFormalRunCommand(fixture("command.formal-run-request.valid.json")).valid,
    false,
    "the historical all-bars command is not an executable M5 request",
  );
});

test("M3 rejects a Formal Run calculation hash that is not the engine result identity", () => {
  const invalid = fixture(
    "event.formal-run-completed.invalid-calculation-hash.json",
  );

  assert.deepEqual(validateFormalRunEvent(invalid), {
    valid: false,
    errors: [
      "/payload/calculation_hash must match /payload/engine_result_sha256",
    ],
  });
});

test("M3 commands validate root/child revision creation and CAS promotion", () => {
  const root = fixture("command.revision-create-root.valid.json");
  const child = fixture("command.revision-create-child.valid.json");
  child.payload.removed_paths = ["strategy.ipynb"];
  const variant = fixture("command.valid.json");
  const promote = fixture("command.revision-promote.valid.json");

  assert.equal(validateWorkspaceRevisionCreateCommand(root).valid, true);
  assert.equal(validateWorkspaceRevisionCreateCommand(child).valid, true);
  assert.equal(validateStrategyVariantCreateCommand(variant).valid, true);
  assert.equal(validateWorkspaceRevisionPromoteCommand(promote).valid, true);
  assert.equal(validateRevisionCommand(root).valid, true);
  assert.equal(validateTypedCommandEnvelope(promote).valid, true);
  assert.equal(validateCommandEnvelope(variant).valid, true);
});

test("M3 child revisions can remove inherited files without overlapping replacements", () => {
  const root = fixture("command.revision-create-root.valid.json");
  root.payload.removed_paths = ["strategy.ipynb"];
  assert.equal(validateWorkspaceRevisionCreateCommand(root).valid, false);

  const child = fixture("command.revision-create-child.valid.json");
  child.payload.removed_paths = [child.payload.files[0].path];
  assert.equal(validateWorkspaceRevisionCreateCommand(child).valid, false);
});

test("M3 command validators reject invalid paths, duplicate paths, artifact bounds, and CAS identities", () => {
  for (const name of [
    "command.revision-create.invalid-path.json",
    "command.revision-create.invalid-git-path.json",
    "command.revision-create.invalid-path-collision.json",
    "command.revision-create.invalid-duplicate-path.json",
    "command.revision-create.invalid-artifact.json",
    "command.revision-create.invalid-child-cas.json",
    "command.variant-create.invalid-payload.json",
    "command.revision-promote.invalid-cas.json",
  ]) {
    assert.equal(validateRevisionCommand(fixture(name)).valid, false, name);
  }

  const unsafe = fixture("command.revision-create-root.valid.json");
  for (const path of [
    "strategy.py\n100644 blob aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\tinjected.py",
    ".GIT/config",
  ]) {
    unsafe.payload.files[0].path = path;
    assert.equal(validateRevisionCommand(unsafe).valid, false, path);
  }

  const colliding = fixture("command.revision-create-root.valid.json");
  colliding.payload.files[1].path = `${colliding.payload.files[0].path}/child.py`;
  assert.equal(validateRevisionCommand(colliding).valid, false, "path prefix collision");

  assert.deepEqual(
    validateRevisionCommand(fixture("command.revision-promote.invalid-cas.json")),
    {
      valid: false,
      errors: ["/expected_revision_id must match /base_revision_id"],
    },
  );
});

test("M3 events validate root/child creation, variant creation, and promotion", () => {
  const root = fixture("event.revision-created-root.valid.json");
  const child = fixture("event.revision-created-child.valid.json");
  const variant = fixture("event.valid.json");
  const promoted = fixture("event.revision-promoted.valid.json");

  assert.equal(validateWorkspaceRevisionCreatedEvent(root).valid, true);
  assert.equal(validateWorkspaceRevisionCreatedEvent(child).valid, true);
  assert.equal(validateStrategyVariantCreatedEvent(variant).valid, true);
  assert.equal(validateWorkspaceRevisionPromotedEvent(promoted).valid, true);
  assert.equal(validateRevisionEvent(root).valid, true);
  assert.equal(validateTypedEventEnvelope(promoted).valid, true);
  assert.equal(validateDomainEvent(variant).valid, true);
});

test("M3 event validators reject lineage and payload identity mismatches", () => {
  for (const name of [
    "event.revision-created.invalid-parent.json",
    "event.variant-created.invalid-payload.json",
    "event.revision-promoted.invalid-previous.json",
  ]) {
    assert.equal(validateRevisionEvent(fixture(name)).valid, false, name);
  }

  const variant = fixture("event.valid.json");
  variant.payload.revision_id = "99999999-9999-4999-8999-999999999999";
  assert.equal(validateRevisionEvent(variant).valid, false, "variant base revision");

  assert.deepEqual(
    validateRevisionEvent(fixture("event.revision-promoted.invalid-previous.json")),
    {
      valid: false,
      errors: ["/payload/previous_revision_id must match /base_revision_id"],
    },
  );
});

test("generic envelopes remain forward-compatible while typed dispatch is strict", () => {
  const command = fixture("command.valid.json");
  const event = fixture("event.valid.json");
  command.command_type = "future.revision_command";
  event.event_type = "future.revision_event";
  assert.equal(validateCommandEnvelope(command).valid, true);
  assert.equal(validateTypedCommandEnvelope(command).valid, false);
  assert.equal(validateRevisionCommand(command).valid, false);
  assert.equal(validateDomainEvent(event).valid, false);
  assert.equal(validateTypedEventEnvelope(event).valid, false);
  assert.equal(validateRevisionEvent(event).valid, false);
});
