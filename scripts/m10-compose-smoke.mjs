import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PROJECT_NAME = "oqs-m10-compose-smoke";
const WEB_PORT = Number(process.env.OQS_M10_SMOKE_PORT);
const DATA_VOLUME = "oqs-m10-compose-smoke-data";
const IMPORTS_ROOT = join(REPO_ROOT, "var", "m10-compose-smoke", "imports");
const EXPORTS_ROOT = join(REPO_ROOT, "var", "m10-compose-smoke", "exports");
const BASE_URL = `http://127.0.0.1:${WEB_PORT}`;

function run(command, arguments_, environment = {}) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(command, arguments_, {
      cwd: REPO_ROOT,
      env: { ...process.env, ...environment },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let output = "";
    child.stdout.on("data", (chunk) => {
      output += chunk;
    });
    child.stderr.on("data", (chunk) => {
      output += chunk;
    });
    child.once("error", rejectRun);
    child.once("exit", (code) => {
      if (code === 0) {
        resolveRun(output);
        return;
      }
      rejectRun(new Error(`${command} ${arguments_.join(" ")} exited ${code}\n${output}`));
    });
  });
}

const composeEnvironment = {
  OQS_WEB_PORT: String(WEB_PORT),
  OQS_DATA_VOLUME: DATA_VOLUME,
  OQS_HOST_IMPORTS_DIR: IMPORTS_ROOT,
  OQS_HOST_EXPORTS_DIR: EXPORTS_ROOT,
};

function compose(arguments_) {
  return run(
    "docker",
    [
      "compose",
      "--project-name",
      PROJECT_NAME,
      "--project-directory",
      REPO_ROOT,
      ...arguments_,
    ],
    composeEnvironment,
  );
}

async function fetchJson(path) {
  return (await fetch(`${BASE_URL}${path}`)).json();
}

async function main() {
  await Promise.all([
    mkdir(IMPORTS_ROOT, { recursive: true }),
    mkdir(EXPORTS_ROOT, { recursive: true }),
  ]);
  await compose(["config", "--quiet"]);

  let started = false;
  try {
    await compose(["up", "--build", "--detach"]);
    started = true;

    const contextBefore = await fetchJson("/api/v1/context");
    await compose([
      "exec",
      "--no-TTY",
      "studio",
      "node",
      "-e",
      "fetch('http://127.0.0.1:8765/health').then(async (response) => { const health = await response.json(); if (!response.ok || health.status !== 'ok') process.exitCode = 1; })",
    ]);
    const projectsBefore = await fetchJson("/api/v1/projects");
    const imports = await fetchJson("/api/v1/data-imports/local-files");
    assert.equal(contextBefore.projectId, "22222222-2222-4222-8222-222222222222");
    assert.equal(projectsBefore.projects.length, 1);
    assert.equal(projectsBefore.projects[0].project_id, contextBefore.projectId);
    assert(imports.files.some((file) => file.file_name === "m7-a-share-daily.csv"));
    assert(imports.files.some((file) => file.file_name === "m7-crypto-linear.csv"));
    assert(imports.files.some((file) => file.file_name === "m8-a-share-rotation.csv"));

    const archiveResponse = await fetch(
      `${BASE_URL}/api/v1/projects/${contextBefore.projectId}/archive`,
    );
    assert.equal(archiveResponse.ok, true);
    const archive = new Uint8Array(await archiveResponse.arrayBuffer());
    assert(archive.byteLength > 0);
    await writeFile(join(EXPORTS_ROOT, `${contextBefore.projectId}.oqs.zip`), archive);

    await compose(["restart", "studio"]);
    const contextAfter = await fetchJson("/api/v1/context");
    const projectsAfter = await fetchJson("/api/v1/projects");
    const importsAfter = await fetchJson("/api/v1/data-imports/local-files");
    assert.deepEqual(contextAfter, contextBefore);
    assert.deepEqual(projectsAfter, projectsBefore);
    assert.deepEqual(importsAfter, imports);
  } finally {
    if (started) {
      await compose(["down"]);
      await run("docker", ["volume", "inspect", DATA_VOLUME]);
    }
  }

  process.stdout.write(
    `M10 Compose smoke passed; stack stopped and named volume ${DATA_VOLUME} was retained.\n`,
  );
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
  process.exitCode = 1;
});
