import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "..");

function readRepoFile(path) {
  const absolutePath = resolve(repoRoot, path);
  if (!existsSync(absolutePath)) {
    throw new Error(`Required delivery configuration is missing: ${path}`);
  }
  return readFileSync(absolutePath, "utf8");
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const envExample = readRepoFile(".env.example");
for (const key of ["OQS_DATA_ROOT", "OQS_PORT", "OQS_DOMAIN_PORT"]) {
  assert(new RegExp(`^${key}=.+$`, "m").test(envExample), `.env.example must define ${key}`);
}
assert(/^OQS_DATA_ROOT=(?!\/)[^\n]+$/m.test(envExample), "OQS_DATA_ROOT must be a relative persistent path");
assert(/^OQS_PORT=\d+$/m.test(envExample), "OQS_PORT must be numeric");
assert(/^OQS_DOMAIN_PORT=\d+$/m.test(envExample), "OQS_DOMAIN_PORT must be numeric");

const composePath = ["compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"].find(
  (path) => existsSync(resolve(repoRoot, path)),
);
assert(composePath, "M10 requires a Compose file at the repository root");
const compose = readRepoFile(composePath);
const dockerfile = existsSync(resolve(repoRoot, "Dockerfile")) ? readRepoFile("Dockerfile") : "";
const deliveryConfig = `${compose}\n${dockerfile}`;
assert(/^services:\s*$/m.test(compose), `${composePath} must declare services`);
assert(/^volumes:\s*$/m.test(compose), `${composePath} must declare named volumes`);
assert(/\bports:\s*\n(?:\s+-[^\n]*\n)+/m.test(compose), `${composePath} must expose service ports`);
assert(/\b(?:build|image):\s*/m.test(compose), `${composePath} must define build or image sources`);
assert(compose.includes("4173"), `${composePath} must expose the SPA port 4173`);
assert(/imports/i.test(compose), `${composePath} must mount the host imports path`);
assert(/exports/i.test(compose), `${composePath} must mount the host exports path`);
assert(/^\s+healthcheck:\s*$/m.test(compose), `${composePath} must define a service healthcheck`);
assert(/run-m4-local\.mjs|start:m[0-9]/i.test(deliveryConfig), `${composePath} must invoke the project launcher`);
assert(/maturin|pyo3|quant-engine/i.test(deliveryConfig), `${composePath} must include the PyO3 runtime build`);

const servicesStart = compose.indexOf("services:");
const servicesBlock = compose.slice(servicesStart, compose.search(/^volumes:\s*$/m));
const serviceNames = [...servicesBlock.matchAll(/^  ([a-zA-Z0-9][a-zA-Z0-9_-]*):\s*$/gm)].map(
  ([, name]) => name.toLowerCase(),
);
assert(serviceNames.length >= 1, `${composePath} must define at least one service`);

process.stdout.write(
  `M10 delivery configuration check passed: ${composePath} has ${serviceNames.length} service(s), healthcheck, ports, volumes, and host import/export paths.\n`,
);
