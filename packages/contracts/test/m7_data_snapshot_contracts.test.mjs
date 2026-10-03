import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  DATA_SNAPSHOT_COMMAND_TYPES,
  DATA_SNAPSHOT_EVENT_TYPES,
  M7_COMMAND_TYPES,
  M7_EVENT_TYPES,
  validateCommandEnvelope,
  validateDataImportPreviewReadModel,
  validateDataSnapshotCommand,
  validateDataSnapshotEvent,
  validateDataSnapshotListReadModel,
  validateDataSnapshotReadModel,
  validateDomainEvent,
  validateTypedCommandEnvelope,
  validateTypedEventEnvelope,
} from "../dist/index.js";

const fixturesDir = join(import.meta.dirname, "../fixtures/v1");
const fixture = (name) =>
  JSON.parse(readFileSync(join(fixturesDir, name), "utf8"));

test("M7 registries expose the data snapshot command and event", () => {
  assert.deepEqual([...DATA_SNAPSHOT_COMMAND_TYPES], ["data.snapshot_create"]);
  assert.deepEqual([...DATA_SNAPSHOT_EVENT_TYPES], ["data.snapshot_created"]);
  assert.equal(M7_COMMAND_TYPES.has("data.snapshot_create"), true);
  assert.equal(M7_EVENT_TYPES.has("data.snapshot_created"), true);
});

test("M7 data snapshot command and event are strict and registered", () => {
  const command = fixture("command.data-snapshot-create.valid.json");
  const event = fixture("event.data-snapshot-created.valid.json");
  const invalidEvent = fixture(
    "event.data-snapshot-created.invalid-row-count.json",
  );

  assert.equal(validateDataSnapshotCommand(command).valid, true);
  assert.equal(validateCommandEnvelope(command).valid, true);
  assert.equal(validateTypedCommandEnvelope(command).valid, true);
  assert.equal(validateDataSnapshotEvent(event).valid, true);
  assert.equal(validateTypedEventEnvelope(event).valid, true);
  assert.equal(validateDomainEvent(event).valid, true);
  assert.equal(validateDataSnapshotEvent(invalidEvent).valid, false);

  const mismatchedMedia = structuredClone(command);
  mismatchedMedia.payload.source_format = "parquet";
  assert.deepEqual(validateDataSnapshotCommand(mismatchedMedia), {
    valid: false,
    errors: ["/payload/source/media_type must match /payload/source_format"],
  });

  const missingMappingField = structuredClone(command);
  delete missingMappingField.payload.mapping.volume;
  assert.equal(validateDataSnapshotCommand(missingMappingField).valid, false);
});

test("M7 import preview, immutable snapshot, and list read models validate", () => {
  const preview = fixture("data-import-preview-read-model.valid.json");
  const snapshot = fixture("data-snapshot-read-model.valid.json");
  const list = fixture("data-snapshot-list-read-model.valid.json");

  assert.equal(validateDataImportPreviewReadModel(preview).valid, true);
  assert.equal(validateDataSnapshotReadModel(snapshot).valid, true);
  assert.equal(validateDataSnapshotListReadModel(list).valid, true);

  const extraPreviewField = structuredClone(preview);
  extraPreviewField.preview_rows[0].close_num = 10;
  assert.equal(validateDataImportPreviewReadModel(extraPreviewField).valid, false);

  const badSnapshot = structuredClone(snapshot);
  badSnapshot.mapping.timestamp = "";
  assert.equal(validateDataSnapshotReadModel(badSnapshot).valid, false);

  const badList = structuredClone(list);
  badList.snapshots[0].row_count = 0;
  assert.equal(validateDataSnapshotListReadModel(badList).valid, false);
});

test("A-share-v3 data snapshots support a fixed basket with explicit symbol shape", () => {
  const event = fixture("event.data-snapshot-created.valid.json");
  const singleEvent = structuredClone(event);
  singleEvent.payload.schema_version = 3;
  singleEvent.payload.execution_profile = "a-share-v3";
  assert.equal(validateDataSnapshotEvent(singleEvent).valid, true);

  const basketEvent = structuredClone(singleEvent);
  basketEvent.payload.symbol = null;
  basketEvent.payload.symbols = ["000001.SZ", "600519.SH"];
  assert.equal(validateDataSnapshotEvent(basketEvent).valid, true);

  const nonNullBasketSymbol = structuredClone(basketEvent);
  nonNullBasketSymbol.payload.symbol = "000001.SZ";
  assert.equal(validateDataSnapshotEvent(nonNullBasketSymbol).valid, false);

  const nullSingleSymbol = structuredClone(singleEvent);
  nullSingleSymbol.payload.symbol = null;
  assert.equal(validateDataSnapshotEvent(nullSingleSymbol).valid, false);

  const mismatchedSingleSymbol = structuredClone(singleEvent);
  mismatchedSingleSymbol.payload.symbol = "600519.SH";
  assert.equal(validateDataSnapshotEvent(mismatchedSingleSymbol).valid, false);

  const snapshot = fixture("data-snapshot-read-model.valid.json");
  const basketSnapshot = structuredClone(snapshot);
  basketSnapshot.schema_version = 3;
  basketSnapshot.execution_profile = "a-share-v3";
  basketSnapshot.symbol = null;
  basketSnapshot.symbols = ["000001.SZ", "600519.SH"];
  assert.equal(validateDataSnapshotReadModel(basketSnapshot).valid, true);

  const invalidBasketSnapshot = structuredClone(basketSnapshot);
  invalidBasketSnapshot.symbol = "000001.SZ";
  assert.equal(validateDataSnapshotReadModel(invalidBasketSnapshot).valid, false);

  const mismatchedSingleSnapshot = structuredClone(snapshot);
  mismatchedSingleSnapshot.schema_version = 3;
  mismatchedSingleSnapshot.execution_profile = "a-share-v3";
  mismatchedSingleSnapshot.symbol = "600519.SH";
  assert.equal(validateDataSnapshotReadModel(mismatchedSingleSnapshot).valid, false);
});
