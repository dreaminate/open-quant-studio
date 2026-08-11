import {
  mkdirSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "..");
const dataRoot = resolve(repoRoot, process.env.OQS_DATA_ROOT ?? "var");
const probePath = join(dataRoot, `.m0-write-probe-${process.pid}`);
const probeBody = "open-quant-studio-m0\n";

mkdirSync(dataRoot, { recursive: true });
writeFileSync(probePath, probeBody, { flag: "wx" });

if (readFileSync(probePath, "utf8") !== probeBody) {
  throw new Error(`Local data root probe mismatch: ${probePath}`);
}

unlinkSync(probePath);
process.stdout.write(`Local data root writable: ${dataRoot}\n`);
