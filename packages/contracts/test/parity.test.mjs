import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

import {
  validateArtifactVerificationEvent,
  validateArtifactRef,
  validateCommandEnvelope,
  validateContextCaptureCommand,
  validateContextCapturedEvent,
  validateDiagnosticLog,
  validateEventEnvelope,
  validateFormalRunCommand,
  validateFormalRunEvent,
  validateRevisionCommand,
  validateRevisionEvent,
  validateSessionCommand,
  validateSessionEvent,
} from "../dist/index.js";

const repoRoot = resolve(import.meta.dirname, "../../..");
const casesPath = join(import.meta.dirname, "../fixtures/v1/cases.json");
const schemaDir = join(import.meta.dirname, "../schemas/v1");
const probePath = join(
  repoRoot,
  "services/quant-domain/src/quant_domain/contract_probe.py",
);
const cases = JSON.parse(readFileSync(casesPath, "utf8")).cases;

test("TypeScript and Python agree on command/event contract vectors", () => {
  const typescriptResults = Object.fromEntries(
    cases.map((contractCase) => {
      const fixturePath = join(dirname(casesPath), contractCase.fixture);
      const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
      const validators = {
        artifact: validateArtifactRef,
        artifact_verification_event: validateArtifactVerificationEvent,
        command: validateCommandEnvelope,
        context_capture_command: validateContextCaptureCommand,
        context_captured_event: validateContextCapturedEvent,
        diagnostic_log: validateDiagnosticLog,
        event: validateEventEnvelope,
        formal_run_command: validateFormalRunCommand,
        formal_run_event: validateFormalRunEvent,
        revision_command: validateRevisionCommand,
        revision_event: validateRevisionEvent,
        session_command: validateSessionCommand,
        session_event: validateSessionEvent,
      };
      const result = validators[contractCase.kind](fixture);

      assert.equal(result.valid, contractCase.valid, contractCase.name);
      return [contractCase.name, result.valid];
    }),
  );

  const python = spawnSync(
    "uv",
    [
      "run",
      "--project",
      join(repoRoot, "services/quant-domain"),
      "--frozen",
      "python",
      probePath,
      casesPath,
      schemaDir,
    ],
    { cwd: repoRoot, encoding: "utf8" },
  );

  assert.equal(python.status, 0, python.stderr);
  assert.deepEqual(JSON.parse(python.stdout), typescriptResults);
});
