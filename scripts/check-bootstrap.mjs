import { existsSync, readFileSync } from "node:fs";

const requiredFiles = [
  ".env.example",
  "README.md",
  "AGENTS.md",
  "apps/control-plane/package.json",
  "apps/web/package.json",
  "docs/00_PROJECT_CHARTER.md",
  "docs/01_ARCHITECTURE.md",
  "docs/02_DOMAIN_MODEL.md",
  "docs/03_SESSION_FABRIC.md",
  "docs/04_COMMAND_EVENT_CONTRACTS.md",
  "docs/05_LOGGING_AND_RETENTION.md",
  "docs/06_MIGRATION_MAP.md",
  "docs/07_POC_ACCEPTANCE.md",
  "docs/08_IMPLEMENTATION_PLAN.md",
  "docs/09_M0_FOUNDATION_EVIDENCE.md",
  "fixtures/backtests/m0-long-short-v1.json",
  "fixtures/market/m0-long-short-v1.csv",
  "packages/contracts/fixtures/v1/cases.json",
  "packages/contracts/fixtures/v1/event.invalid-recorded-at.json",
  "packages/contracts/package.json",
  "packages/contracts/schemas/v1/command-envelope.schema.json",
  "packages/contracts/schemas/v1/event-envelope.schema.json",
  "packages/contracts/src/index.ts",
  "packages/research-ui/package.json",
  "prompts/START_DEVELOPMENT_PROMPT.md",
  "prompts/HANDOFF_PROMPT.md",
  "scripts/check-data-root.mjs",
  "scripts/verify-golden-backtest.py",
  "services/quant-domain/pyproject.toml",
  "services/quant-domain/src/quant_domain/contract_probe.py",
  "services/quant-domain/uv.lock",
  "third_party/M0_IMPORT_DECISIONS.md",
  "tsconfig.base.json",
];

const missing = requiredFiles.filter((path) => !existsSync(path));
if (missing.length > 0) {
  process.stderr.write(`Missing bootstrap files:\n${missing.join("\n")}\n`);
  process.exit(1);
}

const jsonFiles = [
  "package.json",
  "apps/control-plane/package.json",
  "apps/web/package.json",
  "fixtures/backtests/m0-long-short-v1.json",
  "packages/contracts/fixtures/v1/cases.json",
  "packages/contracts/package.json",
  "packages/contracts/schemas/v1/command-envelope.schema.json",
  "packages/contracts/schemas/v1/event-envelope.schema.json",
  "packages/research-ui/package.json",
  "tsconfig.base.json",
];

for (const path of jsonFiles) {
  JSON.parse(readFileSync(path, "utf8"));
}

const goldenSpec = JSON.parse(
  readFileSync("fixtures/backtests/m0-long-short-v1.json", "utf8"),
);
if (
  goldenSpec.status !== "test_oracle_only" ||
  goldenSpec.formal_engine_integrated !== false
) {
  throw new Error("M0 golden fixture must remain a non-formal test oracle.");
}

process.stdout.write(
  `M0 bootstrap manifest valid: ${requiredFiles.length} required files present.\n`,
);
