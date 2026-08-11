import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  M3_COMMAND_TYPES,
  M3_EVENT_TYPES,
  validateCommandEnvelope,
  validateDomainEvent,
  validateRevisionCommand,
  validateRevisionEvent,
  validateStrategyVariantCreateCommand,
  validateStrategyVariantCreatedEvent,
  validateTypedCommandEnvelope,
  validateTypedEventEnvelope,
  validateWorkspaceRevisionCreateCommand,
  validateWorkspaceRevisionCreatedEvent,
  validateWorkspaceRevisionPromoteCommand,
  validateWorkspaceRevisionPromotedEvent,
} from "../dist/index.js";

const fixturesDir = join(import.meta.dirname, "../fixtures/v1");

function fixture(name) {
  return JSON.parse(readFileSync(join(fixturesDir, name), "utf8"));
}

test("M3 registries expose every revision and variant command/event type", () => {
  assert.deepEqual([...M3_COMMAND_TYPES].sort(), [
    "strategy.variant_create",
    "workspace.revision_create",
    "workspace.revision_promote",
  ]);
  assert.deepEqual([...M3_EVENT_TYPES].sort(), [
    "strategy.variant_created",
    "workspace.revision_created",
    "workspace.revision_promoted",
  ]);
});

test("M3 commands validate root/child revision creation and CAS promotion", () => {
  const root = fixture("command.revision-create-root.valid.json");
  const child = fixture("command.revision-create-child.valid.json");
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
