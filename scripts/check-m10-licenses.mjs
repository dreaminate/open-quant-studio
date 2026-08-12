import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "..");

function readRepoFile(path) {
  const absolutePath = resolve(repoRoot, path);
  if (!existsSync(absolutePath)) {
    throw new Error(`Required licensing evidence is missing: ${path}`);
  }
  return readFileSync(absolutePath, "utf8");
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const rootLicense = readRepoFile("LICENSE");
assert(rootLicense.includes("MIT License"), "LICENSE must retain the MIT project license");

const thirdPartyRoot = resolve(repoRoot, "third_party");
const evidenceFiles = readdirSync(thirdPartyRoot)
  .filter((name) => name.endsWith(".md"))
  .map((name) => resolve(thirdPartyRoot, name));
const evidenceText = evidenceFiles
  .map((path) => readFileSync(path, "utf8"))
  .join("\n");
assert(evidenceFiles.length >= 1, "third_party must contain dependency evidence documents");
assert(
  evidenceText.toLowerCase().includes("license"),
  "third_party dependency evidence must declare applicable licenses",
);
assert(
  existsSync(resolve(thirdPartyRoot, "README.md")),
  "third_party/README.md must document the notice boundary",
);
assert(
  existsSync(resolve(thirdPartyRoot, "licenses/PI_MIT.txt")),
  "the retained Pi MIT notice must be present",
);

const workspacePackages = [
  "apps/control-plane",
  "apps/web",
  "packages/contracts",
  "packages/research-ui",
];
for (const packagePath of workspacePackages) {
  const packageJson = JSON.parse(readRepoFile(`${packagePath}/package.json`));
  assert(
    packageJson.license === "MIT",
    `${packagePath}/package.json must declare the MIT project license`,
  );
}

const npmPackages = new Set();
for (const packagePath of ["package.json", ...workspacePackages.map((path) => `${path}/package.json`)]) {
  const packageJson = JSON.parse(readRepoFile(packagePath));
  for (const group of ["dependencies", "devDependencies", "optionalDependencies"]) {
    for (const name of Object.keys(packageJson[group] ?? {})) {
      if (!name.startsWith("@open-quant-studio/")) {
        npmPackages.add(name);
      }
    }
  }
}
const missingNpmEvidence = [...npmPackages].filter((name) => !evidenceText.includes(name));
assert(
  missingNpmEvidence.length === 0,
  `third_party evidence is missing npm dependency entries: ${missingNpmEvidence.join(", ")}`,
);

const pythonManifest = readRepoFile("services/quant-domain/pyproject.toml");
const pythonPackages = [...pythonManifest.matchAll(/^\s*["']([a-z0-9-]+)==[^"']+["'],?\s*$/gim)].map(
  ([, name]) => name,
);
const missingPythonEvidence = pythonPackages.filter((name) => !evidenceText.includes(name));
assert(
  missingPythonEvidence.length === 0,
  `third_party evidence is missing Python dependency entries: ${missingPythonEvidence.join(", ")}`,
);

const rustEvidence = readRepoFile("third_party/M3_DEPENDENCY_DECISIONS.md");
assert(
  /\| `pyo3` \| `0\.28\.3` \| MIT OR Apache-2\.0 \|/i.test(rustEvidence),
  "M3 Rust dependency evidence must state the Rust/PyO3 boundary and applicable licenses",
);

for (const requiredDocument of [
  "M0_IMPORT_DECISIONS.md",
  "M1_DEPENDENCY_DECISIONS.md",
  "M2_DEPENDENCY_DECISIONS.md",
  "M3_DEPENDENCY_DECISIONS.md",
  "M4_DEPENDENCY_DECISIONS.md",
  "M7_DEPENDENCY_DECISIONS.md",
]) {
  const text = readRepoFile(`third_party/${requiredDocument}`);
  assert(/license/i.test(text), `${requiredDocument} must retain license evidence`);
}

process.stdout.write(
  `M10 license evidence check passed: ${npmPackages.size} declared npm dependencies and third-party notices are documented.\n`,
);
