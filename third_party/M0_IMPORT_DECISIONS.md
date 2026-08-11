# M0 import decisions

Evidence date: 2026-08-11, Asia/Shanghai.

## Donor and upstream boundary

| Source | Reviewed identity | License evidence | M0 decision |
|---|---|---|---|
| QuantBT | `dreaminate/QuantBT` commit `e13b322ea00e6dc80cfe003ba44d126df8676230` | No committed root or candidate-UI license found | No source copied; unsafe until explicit rights and per-file provenance are resolved |
| quant-assistant | local commit `985f4502485f1b2978d72dca89e769a3a61525b8`; configured origin names TencentDB Agent Memory | Crate metadata says MIT; no root/Rust license or reliable engine lineage found | No source copied; clean Git object may be inspected only as a future oracle |
| VibeTrading | `HKUDS/Vibe-Trading` local commit `bec189f2eea3926262d6b692da9acdf1a19a6eeb` | Root MIT license | No source copied; SSE/status patterns are named design/test oracles only |
| Pi | `earendil-works/pi` reviewed commit `24047f5dfb222ef7d26b554a0e576e5efa844024` | Root MIT license; reviewed SHA still exists | Not installed in M0; runtime compatibility and exact SHA pin belong to M2 |

The M0 schemas, validators, tests, synthetic market data, and accounting oracle
were written cleanroom in this repository. They do not contain donor code.

## Registry dependencies

| Package | Version | Registry | License | Purpose |
|---|---:|---|---|---|
| `typescript` | `7.0.2` | `https://www.npmjs.com/package/typescript` | Apache-2.0 | Compile the shared TypeScript contract package |
| `ajv` | `8.20.0` | `https://www.npmjs.com/package/ajv` | MIT | JSON Schema 2020-12 validation in TypeScript |
| `ajv-formats` | `3.0.1` | `https://www.npmjs.com/package/ajv-formats` | MIT | RFC3339 `date-time` validation through Ajv |
| `jsonschema` | `4.26.0` | `https://pypi.org/project/jsonschema/` | MIT | JSON Schema 2020-12 validation in Python |
| `rfc3339-validator` | `0.1.4` | `https://pypi.org/project/rfc3339-validator/` | MIT | RFC3339 `date-time` validation through jsonschema |

`pnpm-lock.yaml` and `services/quant-domain/uv.lock` freeze the full transitive
dependency sets. No package source is vendored under `third_party/`.

## 2026-08-12 project-license and cleanroom refresh

- Open Quant Studio's own source uses the root MIT `LICENSE`.
- The project license does not license donor code. The live donor/remote refresh
  in `docs/06_MIGRATION_MAP.md` preserves every no-copy decision above.
- The approved formal engine and SPA paths are OQS-owned cleanroom
  implementations. No QuantBT or quant-assistant source migration is planned.
- The M0 dependency graph is unchanged; the frozen install and license-group
  audit passed on the refreshed authority tree.
