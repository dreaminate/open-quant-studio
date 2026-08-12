import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  validateArtifactMetadataReadModel,
  validateRunReportReadModel,
} from "../dist/index.js";

const fixturesDir = join(import.meta.dirname, "../fixtures/v1");
const fixture = () =>
  JSON.parse(
    readFileSync(join(fixturesDir, "run-report-read-model.valid.json"), "utf8"),
  );

test("M9 Run report envelope validates with strict artifacts and definitions", () => {
  assert.equal(validateRunReportReadModel(fixture()).valid, true);
});

test("M9 report artifact storage URI must bind to its SHA-256", () => {
  const invalid = fixture();
  invalid.json_artifact.storage_uri = "cas://sha256/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
  const result = validateRunReportReadModel(invalid);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((error) => error.includes("/json_artifact/storage_uri")));
});

test("M9 report calculation identity binds to the engine result", () => {
  const invalid = fixture();
  invalid.report.identities.engine_result_sha256 = "b".repeat(64);
  const result = validateRunReportReadModel(invalid);
  assert.equal(result.valid, false);
  assert.ok(
    result.errors.some((error) =>
      error.includes("engine_result_sha256 must match /report/run/calculation_hash")
    ),
  );
});

test("M9 report definitions must cover period and summary exactly", () => {
  const invalid = fixture();
  invalid.report.definitions.pop();
  const result = validateRunReportReadModel(invalid);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((error) => error.includes("definitions/field set")));
});

test("M9 reconciliation passed flag must match every check", () => {
  const falseFlag = fixture();
  falseFlag.report.reconciliation.passed = false;
  assert.equal(validateRunReportReadModel(falseFlag).valid, false);

  const falseCheck = fixture();
  falseCheck.report.reconciliation.checks[0].passed = false;
  assert.equal(validateRunReportReadModel(falseCheck).valid, false);
});

test("M9 report JSON and HTML artifacts are valid run artifact kinds", () => {
  const reportArtifact = {
    artifact_id: "29292929-2929-4292-8292-292929292929",
    project_id: "20202020-2020-4202-8202-202020202020",
    sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    media_type: "application/vnd.open-quant-studio.run-report+json",
    byte_size: 10,
    storage_uri:
      "cas://sha256/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    producing_revision_id: null,
    producing_run_id: "18181818-1818-4181-8181-181818181818",
    origin_kind: "service_generated",
    source_ref: "m9-report",
    created_at: "2026-08-12T08:00:00Z",
    revision_paths: [],
    run_kinds: [
      {
        run_id: "18181818-1818-4181-8181-181818181818",
        kind: "report_json",
      },
      {
        run_id: "18181818-1818-4181-8181-181818181818",
        kind: "report_html",
      },
    ],
  };
  assert.equal(validateArtifactMetadataReadModel(reportArtifact).valid, true);
});
