# M0 foundation evidence

Evidence date: 2026-08-11, Asia/Shanghai.

This document records local M0 evidence. It is not remote, CI, production, POC,
or user-acceptance evidence.

## Repository and toolchain baseline

- The integration checkout was clean before M0 writes on `main` at
  `c5d321e10483f76a6f6987d1ae66b620244f0ea0`.
- Local `HEAD`, local `origin/main`, and read-only remote `main` all matched;
  ahead/behind was `0/0`.
- GitHub reported public repository `dreaminate/open-quant-studio`, default
  branch `main`, and no Actions run records.
- Verified tools: Node `24.14.1`, npm `11.16.0`, pnpm `11.16.0`, Python
  `3.13.13`, uv `0.11.23`, rustc/cargo `1.95.0`.
- The configured package-manager pin remains pnpm `11.21.0`; local validation
  uses compatible pnpm `11.16.0`. No global tool was installed or changed.
- Development data defaults to ignored repository path `var/`; the M0 probe
  creates, reads, and removes one exact probe file to prove writability.

## Provenance boundary

The refreshed donor matrix is in `06_MIGRATION_MAP.md`; exact M0 decisions are
in `../third_party/M0_IMPORT_DECISIONS.md`.

- QuantBT: exact committed SHA is reproducible, but its live UI tree is dirty
  and no applicable committed UI license was found. No copy is permitted.
- quant-assistant: exact commit contains Rust/PyO3 code, but the live engine is
  dirty, its configured origin names a different product, and root/Rust license
  coverage is unresolved. No copy is permitted.
- VibeTrading: clean local MIT snapshot is behind remote `main`; selected SSE
  and status behavior is oracle-only. No source was copied.
- Pi: reviewed MIT SHA still exists and local Node meets the static requirement;
  Pi was not installed, and runtime compatibility remains an M2 check. A final
  read-only refresh found mutable upstream `main` at
  `2a95ef70db83a19cf5500f31dc4ff8247e04043e`, reinforcing the SHA-pin rule.

## Executable foundation

- `packages/contracts/schemas/v1/` is the canonical command/event envelope v1.
- `packages/contracts/src/index.ts` supplies typed Ajv runtime validation.
- `services/quant-domain/src/quant_domain/contract_probe.py` validates the same
  schemas through Python jsonschema.
- `packages/contracts/test/parity.test.mjs` executes both implementations over
  the same valid and invalid vectors and requires identical results, including
  rejection of an impossible RFC3339 calendar date through standard format
  validators rather than a handwritten timestamp parser.
- `fixtures/market/m0-long-short-v1.csv` is synthetic local data with SHA-256
  `5106492190b928ce9c92f7d0e78571f0da8b3800651b9c1cc9983025ba9e1dc2`.
- `fixtures/backtests/m0-long-short-v1.json` freezes one long and one short
  round trip, signed positions, four fee-bearing sides at `0.0006`, cash,
  equity, total return, and max drawdown.
- `scripts/verify-golden-backtest.py` independently replays the fixture. The
  spec has `formal_engine_integrated: false` and cannot register a formal Run.

## Validation record

- `pnpm install --frozen-lockfile`: exit `0`; five workspace projects were
  already locked and up to date.
- `uv sync --project services/quant-domain --frozen`: exit `0`; seven locked
  Python packages were checked.
- `uv lock --project services/quant-domain --check`: exit `0`; eight lock
  records resolved without a lockfile change.
- `pnpm validate:m0`: exit `0`; 33 required files were present, the local data
  root was writable, TypeScript compiled, one Node test passed with zero
  failures, TypeScript/Python agreed on all five shared contract vectors, and
  the golden replay matched the frozen SHA and expectations.
- `uv run --project services/quant-domain --frozen python -m compileall -q
  services/quant-domain/src scripts/verify-golden-backtest.py`: exit `0`.
- `git diff --check`: exit `0` with no output.

Two intermediate failures were found and corrected. The first `pnpm run build`
exited `2` with `TS2351`, `TS7031`, and `TS2322` because the Ajv CommonJS/ESM
declaration was imported as a non-constructable default and validation results
did not narrow from `unknown`. Reading the installed `dist/2020.d.ts` led to the
named `Ajv2020` import and explicit branches. After RFC3339 format validation
was added, the first `pnpm run test:contracts` exited `2` with `TS2349` because
the CommonJS `ajv-formats` default was treated as a module namespace; calling
its typed `.default` export resolved it. The final full gate above passed.

## M0 non-claims

- No Pi session or AgentLoop runtime is present.
- No Python durable writer, SQLite ledger, event/outbox transaction, or SSE
  stream is present.
- No Rust/PyO3 formal engine is present.
- No React/Vite application or donor UI is present.
- No formal Run, CI success, deployment, production state, or user acceptance
  is claimed.

## 2026-08-12 M0-M10 decision refresh

This refresh updates the authority and licensing surface without rewriting the
historical validation above.

- The user selected an OQS-owned cleanroom Rust/PyO3 formal engine, an
  OQS-owned React/Vite SPA, the MIT project license, and the M0-M10 milestone
  plan. Donor repositories remain read-only and no donor file was copied.
- Root `LICENSE` is MIT with SHA-256
  `875271587863cc1d7a4d8542d129f9014edd26e5252fa982885ca53653a53b8d`.
- Live donor/remotes were refreshed in `06_MIGRATION_MAP.md`. QuantBT remains
  dirty without a candidate UI license; quant-assistant remains dirty without
  root/Rust rights or reliable product lineage; VibeTrading is clean but local
  `main` is behind remote; Pi remains pinned to `0.84.1` while mutable upstream
  `main` has advanced.
- `pnpm install --frozen-lockfile`: exit `0`; five workspace projects were up
  to date. `uv lock --project services/quant-domain --check`: exit `0`.
- `pnpm validate:m0`: exit `0`; 46 required files, writable data root, ten
  contracts/parity tests, and the non-formal golden oracle passed.
- `pnpm licenses list --json`: exit `0`; groups were MIT 60, Apache-2.0 48,
  BSD-3-Clause 14, BlueOak-1.0.0 5, ISC 8, and 0BSD 1.
- `git diff --check`: exit `0` after removing two prompt EOF whitespace errors.

Delivery state for this refresh: local checkout implemented on
`codex/oqs-m0-m10-minimal` after checkpoint `146024d`; local M0 tests passed;
the authority refresh is not yet pushed or represented by a PR; GitHub CI has
no workflow/run evidence; production was not deployed; user acceptance remains
pending.
