import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "..");

function readRepoFile(path) {
  const absolutePath = resolve(repoRoot, path);
  if (!existsSync(absolutePath)) {
    throw new Error(`Required lock/config file is missing: ${path}`);
  }
  return readFileSync(absolutePath, "utf8");
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const rootPackage = JSON.parse(readRepoFile("package.json"));
assert(
  rootPackage.packageManager === "pnpm@11.21.0",
  `package.json must pin pnpm@11.21.0 (found ${rootPackage.packageManager ?? "missing"})`,
);
assert(
  rootPackage.engines?.node === ">=24.0.0",
  "package.json must require Node >=24.0.0",
);

const pnpmLock = readRepoFile("pnpm-lock.yaml");
assert(/^lockfileVersion:\s*['"]9\.0['"]?$/m.test(pnpmLock), "pnpm-lock.yaml must use lockfileVersion 9.0");
assert(/^importers:\s*$/m.test(pnpmLock), "pnpm-lock.yaml must contain importer records");
assert(/^snapshots:\s*$/m.test(pnpmLock), "pnpm-lock.yaml must contain snapshots");

function importerBlock(importer) {
  const startMarker = `  ${importer}:`;
  const start = pnpmLock.indexOf(startMarker);
  assert(start >= 0, `pnpm-lock.yaml is missing importer ${importer}`);
  const rest = pnpmLock.slice(start + startMarker.length);
  const next = rest.search(/\n  [^ \n][^\n]*:/);
  return rest.slice(0, next < 0 ? rest.length : next);
}

function yamlScalar(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function assertImporterDependencies(importer, packagePath) {
  const packageJson = JSON.parse(readRepoFile(`${packagePath}/package.json`));
  const block = importerBlock(importer);
  const dependencyGroups = [
    packageJson.dependencies ?? {},
    packageJson.devDependencies ?? {},
    packageJson.optionalDependencies ?? {},
  ];
  for (const dependencies of dependencyGroups) {
    for (const [name, specifier] of Object.entries(dependencies)) {
      const namePattern = yamlScalar(name);
      const specifierPattern = yamlScalar(specifier);
      const recordPattern = new RegExp(
        `(?:^|\\n)\\s{6}(?:'${namePattern}'|${namePattern}):\\n\\s{8}specifier:\\s*${specifierPattern}(?:\\n|$)`,
      );
      assert(
        recordPattern.test(block),
        `pnpm-lock.yaml importer ${importer} is out of sync for ${name}@${specifier}`,
      );
    }
  }
}

assertImporterDependencies(".", ".");
assertImporterDependencies("apps/control-plane", "apps/control-plane");
assertImporterDependencies("apps/web", "apps/web");
assertImporterDependencies("packages/contracts", "packages/contracts");
assertImporterDependencies("packages/research-ui", "packages/research-ui");

const pyproject = readRepoFile("services/quant-domain/pyproject.toml");
const uvLock = readRepoFile("services/quant-domain/uv.lock");
assert(/^requires-python\s*=\s*">=3\.13"$/m.test(uvLock), "uv.lock must retain Python >=3.13");
for (const match of pyproject.matchAll(/^\s*["']([a-z0-9-]+)==([^"']+)["'],?\s*$/gim)) {
  const [, name, version] = match;
  const packagePattern = new RegExp(
    `\\[\\[package\\]\\]\\nname = "${yamlScalar(name)}"\\nversion = "${yamlScalar(version)}"`,
  );
  assert(packagePattern.test(uvLock), `uv.lock is out of sync for ${name}==${version}`);
}

const cargoManifest = readRepoFile("crates/quant-engine/Cargo.toml");
const cargoLock = readRepoFile("crates/quant-engine/Cargo.lock");
assert(/^version\s*=\s*4\s*$/m.test(cargoLock), "Cargo.lock must use lockfile format version 4");
const cargoDependencies = [
  ...cargoManifest.matchAll(/^\s*([a-z0-9_-]+)\s*=\s*\{\s*version\s*=\s*"=([^\"]+)"/gim),
  ...cargoManifest.matchAll(/^\s*([a-z0-9_-]+)\s*=\s*"=([^\"]+)"\s*$/gim),
];
for (const [, name, version] of cargoDependencies) {
  const packagePattern = new RegExp(
    `\\[\\[package\\]\\]\\nname = "${yamlScalar(name)}"\\nversion = "${yamlScalar(version)}"`,
  );
  assert(packagePattern.test(cargoLock), `Cargo.lock is out of sync for ${name}=${version}`);
}

process.stdout.write(
  "M10 lockfile check passed: pnpm, uv, and Cargo manifests have matching frozen lock records.\n",
);
