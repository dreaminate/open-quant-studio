# M10 local delivery evidence

Evidence date: 2026-08-12, Asia/Shanghai.

This document records the local functional completion boundary for M0-M10.
Remote branch, pull request, GitHub Actions, and merge evidence are evaluated
separately after this checkout is committed and pushed.

## Implemented vertical

1. `docker compose up --build` starts one local `studio` service containing the
   React/Vite SPA, Pi/control plane, Python domain and worker, and Rust/PyO3
   engine. The service has an HTTP healthcheck, a named persistent data volume,
   and host-mounted import and export directories.
2. The launcher seeds the A-share, crypto, and three-symbol rotation sample
   files without overwriting existing imports. A normal stop closes active
   browser event connections and exits the composed processes cleanly.
3. The real Chromium journey creates three immutable DataSnapshots, then runs
   all six catalog strategies: A-share trend breakout, research short, and
   three-symbol rotation; crypto trend, mean reversion, and breakout.
4. Every strategy journey saves and finalizes source/notebook revisions,
   compares and merges the candidate, completes a real Rust/PyO3 Formal Run,
   renders and reconciles its report, promotes the successful revision, and
   preserves Run identity.
5. The same browser journey downloads a project archive and imports it through
   the Data workbench. A separate fresh Python domain imports that archive and
   verifies all six Run and report identities.
6. GitHub Actions defines the same portable functional gate on macOS and the
   complete gate, including Compose, on Ubuntu. Node, pnpm, Python, uv, Rust,
   Playwright, frozen dependency installs, locks, licenses, and delivery
   configuration are explicit in the workflow.

## Complete local gate

`pnpm validate:m10` exited `0` in the current checkout. The command includes
all earlier milestone gates and finished with this evidence:

- shared contracts: 37 tests passed;
- Rust v1 engine: 16 automatic tests passed and the separately invoked release
  benchmark passed; Rust portfolio v2: 4 tests passed; PyO3: 4 tests passed;
- M5 domain/lifecycle/log/Forward Test/archive: 34 tests passed; M5 typed
  control-plane surfaces: 5 tests passed;
- M6 domain concurrency: 2 tests passed; real session restart: 2 tests passed;
  real local browser vertical: 1 test passed;
- M7 contracts/parity: 4 tests passed; cumulative domain/data tests: 42 tests
  passed; control plane: 2 tests passed; browser data journey: 1 test passed;
- M8 contracts/parity: 3 tests passed; strategy/domain tests: 10 tests passed;
  cumulative control plane: 4 tests passed; browser workbench: 1 test passed;
- M9 report contracts: 6 tests passed; reference/domain/six-strategy reports: 9
  tests passed; control plane: 1 test passed; browser report journey: 1 test
  passed;
- the 250,000-bar mixed trade/funding release benchmark completed in
  `11.462799875s`, below its 60-second ceiling;
- lockfile, dependency-license evidence, Compose configuration, builds, and
  `git diff --check` passed;
- the real M10 six-strategy/report/promote/archive browser journey passed in
  `14.4s`;
- the Compose smoke passed internal domain health, browser context, three
  imports, archive export, restart identity, and retained its named volume
  after stopping the stack.

Vite reported a non-blocking warning for the approximately 896 kB minified
application chunk.

## Local runtime commands

```text
pnpm validate:m10
docker compose up --build
docker compose down
```

The browser is available at `http://127.0.0.1:4173`. The default host import
and export directories are `var/compose-imports/` and
`var/compose-exports/`. `docker compose down` does not delete the named
`oqs-m10-data` volume.

## Delivery state at this evidence point

- local checkout: M0-M10 functionality is implemented on branch
  `codex/oqs-m0-m10-minimal`;
- local tests: `pnpm validate:m10` passed;
- remote branch or PR: not yet pushed and no PR exists for this working tree;
- CI: the Ubuntu/macOS workflow is implemented but has not yet run for this
  working tree;
- production: no deployment was performed;
- user acceptance: not performed.
