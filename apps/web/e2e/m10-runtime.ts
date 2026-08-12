import { execFile, spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { createServer as createNetServer } from "node:net";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export const M10_REPO_ROOT = resolve(import.meta.dirname, "../../..");

export interface M10Runtime {
  readonly baseUrl: string;
  readonly dataRoot: string;
  readonly runtime: ReturnType<typeof spawn>;
  readonly output: { value: string };
}

export interface ImportedArchiveIdentity {
  readonly restored_project_id: string;
  readonly run_ids: string[];
  readonly report_run_ids: string[];
}

async function freeLoopbackPort(): Promise<number> {
  const listener = createNetServer();
  listener.listen(0, "127.0.0.1");
  await once(listener, "listening");
  const address = listener.address();
  listener.close();
  await once(listener, "close");
  if (typeof address === "string" || address === null) {
    throw new Error("loopback listener has no TCP port");
  }
  return address.port;
}

async function waitForRuntime(instance: M10Runtime): Promise<void> {
  for (let attempt = 0; attempt < 600; attempt += 1) {
    if (instance.runtime.exitCode !== null) {
      throw new Error(`M10 runtime exited before readiness: ${instance.output.value}`);
    }
    try {
      const response = await fetch(`${instance.baseUrl}/api/v1/context`);
      if (response.ok && response.headers.get("content-type")?.startsWith("application/json")) {
        return;
      }
    } catch {
      await delay(50);
    }
  }
  throw new Error(`M10 runtime did not become ready: ${instance.output.value}`);
}

export async function startM10Runtime(): Promise<M10Runtime> {
  const varRoot = join(M10_REPO_ROOT, "var");
  await mkdir(varRoot, { recursive: true });
  const dataRoot = await mkdtemp(join(varRoot, "m10-total-"));
  const port = await freeLoopbackPort();
  const domainPort = await freeLoopbackPort();
  const output = { value: "" };
  const runtime = spawn("node", ["scripts/run-m4-local.mjs"], {
    cwd: M10_REPO_ROOT,
    env: {
      ...process.env,
      OQS_DATA_ROOT: dataRoot,
      OQS_PORT: String(port),
      OQS_DOMAIN_PORT: String(domainPort),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  runtime.stdout?.setEncoding("utf8");
  runtime.stderr?.setEncoding("utf8");
  runtime.stdout?.on("data", (chunk) => { output.value += chunk; });
  runtime.stderr?.on("data", (chunk) => { output.value += chunk; });
  const instance: M10Runtime = {
    baseUrl: `http://127.0.0.1:${port}`,
    dataRoot,
    runtime,
    output,
  };
  await waitForRuntime(instance);
  return instance;
}

export async function stopM10Runtime(instance: M10Runtime): Promise<void> {
  if (instance.runtime.exitCode === null) {
    instance.runtime.kill("SIGTERM");
    await once(instance.runtime, "exit");
  }
  await rm(instance.dataRoot, { recursive: true, force: true });
}

export async function verifyImportedArchiveIdentity(
  archivePath: string,
  projectId: string,
  expectedRunIds: string[],
): Promise<ImportedArchiveIdentity> {
  const varRoot = join(M10_REPO_ROOT, "var");
  await mkdir(varRoot, { recursive: true });
  const targetRoot = await mkdtemp(join(varRoot, "m10-archive-import-"));
  const verifier = [
    "import json",
    "import sys",
    "from pathlib import Path",
    "from quant_domain.domain import QuantDomain",
    "from quant_domain.project_archive import import_project_archive",
    "archive_path = Path(sys.argv[1])",
    "target_root = Path(sys.argv[2])",
    "project_id = sys.argv[3]",
    "expected_run_ids = json.loads(sys.argv[4])",
    "domain = QuantDomain(target_root)",
    "imported = import_project_archive(domain, archive_path, expected_project_id=project_id)",
    "runs = domain.runs(project_id)",
    "run_ids = sorted(run['run_id'] for run in runs)",
    "if run_ids != sorted(expected_run_ids):",
    "    raise RuntimeError(f'archive run identities did not match: {run_ids!r}')",
    "report_run_ids = []",
    "for run_id in expected_run_ids:",
    "    detail = domain.run(project_id, run_id)",
    "    if detail is None or detail['run']['status'] != 'succeeded':",
    "        raise RuntimeError(f'archive Run {run_id} was not restored as succeeded')",
    "    report = domain.run_report(project_id, run_id)",
    "    if report['report']['run']['run_id'] != run_id:",
    "        raise RuntimeError(f'archive report identity did not match {run_id}')",
    "    report_run_ids.append(run_id)",
    "print(json.dumps({'restored_project_id': imported.restored_project_id, 'run_ids': run_ids, 'report_run_ids': sorted(report_run_ids)}, sort_keys=True))",
  ].join("\n");
  try {
    const { stdout } = await execFileAsync(
      "uv",
      [
        "run",
        "--project",
        "services/quant-domain",
        "--frozen",
        "python",
        "-c",
        verifier,
        archivePath,
        targetRoot,
        projectId,
        JSON.stringify(expectedRunIds),
      ],
      {
        cwd: M10_REPO_ROOT,
        env: {
          ...process.env,
          PYTHONPATH: join(M10_REPO_ROOT, "services/quant-domain/src"),
        },
        maxBuffer: 1024 * 1024,
      },
    );
    return JSON.parse(stdout) as ImportedArchiveIdentity;
  } finally {
    await rm(targetRoot, { recursive: true, force: true });
  }
}
