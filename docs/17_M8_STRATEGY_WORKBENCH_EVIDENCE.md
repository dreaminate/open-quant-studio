# M8 strategy workbench evidence

Evidence date: 2026-08-12, Asia/Shanghai.

This document records local-checkout implementation and validation evidence for
the M8 functional slice. It does not claim M9-M10 completion, remote CI,
production deployment, or user acceptance.

## Implemented functional slice

1. The built-in catalog contains exactly six OQS-owned strategies: A-share
   trend/breakout, labelled research-short, real multi-symbol rotation, crypto
   trend, mean-reversion, and breakout. Each has parameters, entry/exit logic,
   a Python source file, and a deterministic generated notebook.
2. `strategy.py` is the authoritative source. The Code workbench loads any of
   the six sources, saves an immutable child revision, and only creates
   `strategy.ipynb` through the explicit Finalize action. A later source save
   removes the inherited stale notebook; finalizing again recreates it.
3. Finalized notebook metadata binds the strategy identity and source SHA-256.
   A notebook reopened from an immutable revision downloads with the correct
   strategy filename without relying on transient selector state.
4. Five single-symbol strategies execute their emitted intents through the
   OQS Rust v1 engine. The A-share rotation strategy runs through a real
   multi-symbol DataSnapshot, streamed strategy host, PyO3 checkpoint-v2 path,
   and formal Run detail.
5. The separate portfolio v2 ABI uses one sorted symbol universe, session
   panels, shared cash, per-symbol T+1 eligibility, close-before-open execution,
   and one portfolio equity point per session. The frozen v1 ABI remains
   unchanged.
6. The six-strategy catalog and notebook render are available through Python
   HTTP, the typed control-plane client, the browser facade, and the SPA.
   Finalized `.py` and `.ipynb` files survive project archive export/import with
   the same revision and artifact identities.

## Local validation record

`pnpm run validate:m8` exited `0` in the current checkout. It reran the complete
M7 gate and added:

- 3 M8 contract and TypeScript/Python parity tests, including the strict
  portfolio engine-result schema;
- 9 Python tests covering the exact six-entry catalog, deterministic notebook
  generation, five real v1 engine runs, the real portfolio-v2 Formal Run, HTTP
  rendering, and archive round-trip;
- 4 cumulative M7/M8 control-plane tests for data-backed Formal Run, catalog,
  notebook render, and child-revision notebook removal mapping;
- 1 Playwright strategy-workbench vertical that visits all six catalog entries,
  saves and finalizes one strategy, downloads it before and after page reopen,
  compares, merges, runs, opens Run Detail, then edits the finalized source and
  verifies that the stale notebook is removed.

The cumulative gate also passed 31 contract tests, 20 automatic Rust tests plus
one ignored final release benchmark, 4 PyO3/reference tests, M5 lifecycle and
archive tests, M6 real-session restart and browser tests, and M7 data-import
tests. Vite emitted one non-blocking warning for an approximately 890 kB
minified application chunk.

## Explicit residuals and non-claims

- M9 must define and independently reconcile every formal Run Detail field,
  then export shared JSON and standalone HTML reports for all six strategies.
- M10 must run the six complete real-browser report/archive chains, add Docker
  Compose, repeat the 250,000-bar release benchmark, add required Ubuntu/macOS
  CI, and complete the ready-PR and squash-merge gates.
- No remote CI, production deployment, or user acceptance is claimed.

## Delivery state

- local checkout: M8 is implemented and `validate:m8` passed on branch
  `codex/oqs-m0-m10-minimal`;
- remote branch or PR: the current working tree has not been pushed and is not
  in a PR;
- local tests: the named M8 gate passed;
- CI: no CI result exists for this unpushed state;
- production: no deployment was performed;
- user acceptance: not performed; the full Goal remains active through M10.
