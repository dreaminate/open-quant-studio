import { existsSync, readFileSync } from "node:fs";

const requiredFiles = [
  "README.md",
  "AGENTS.md",
  "docs/00_PROJECT_CHARTER.md",
  "docs/01_ARCHITECTURE.md",
  "docs/02_DOMAIN_MODEL.md",
  "docs/03_SESSION_FABRIC.md",
  "docs/04_COMMAND_EVENT_CONTRACTS.md",
  "docs/05_LOGGING_AND_RETENTION.md",
  "docs/06_MIGRATION_MAP.md",
  "docs/07_POC_ACCEPTANCE.md",
  "docs/08_IMPLEMENTATION_PLAN.md",
  "prompts/START_DEVELOPMENT_PROMPT.md",
  "prompts/HANDOFF_PROMPT.md",
];

const missing = requiredFiles.filter((path) => !existsSync(path));
if (missing.length > 0) {
  process.stderr.write(`Missing bootstrap files:\n${missing.join("\n")}\n`);
  process.exit(1);
}

JSON.parse(readFileSync("package.json", "utf8"));
process.stdout.write(`Bootstrap manifest valid: ${requiredFiles.length} required files present.\n`);
