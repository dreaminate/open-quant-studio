# M7 local data and snapshot evidence

Evidence date: 2026-08-12, Asia/Shanghai.

This document records local-checkout implementation and validation evidence for
the M7 functional slice. It does not claim M8-M10 completion, remote CI,
production deployment, or user acceptance.

## Implemented functional slice

1. The Data workbench accepts local CSV or Parquet uploads and lists configured
   files from the runtime instance's `imports/` directory. Both paths return the
   same typed preview with source identity, columns, suggested mapping, preview
   rows, and total row count.
2. PyArrow 25.0.0 owns CSV/Parquet decoding. OQS-owned code applies the shared
   timestamp, symbol, OHLCV mapping and returns row-numbered field errors for an
   invalid import. The exact dependency, license, wheel hashes, and upstream
   APIs are recorded in `third_party/M7_DEPENDENCY_DECISIONS.md`.
3. A typed `data.snapshot_create` command materializes canonical normalized bars
   and a Rust-engine market input, registers their CAS artifacts, and persists
   immutable metadata: market, symbol, timezone, price basis, cutoff, schema,
   range, row count, mapping, and SHA-256 identities.
4. Snapshot create is command-idempotent. Its list/detail/market-input reads are
   available through Python HTTP, the typed TypeScript client, the browser
   facade, and the SPA.
5. Formal Run creation requires an explicitly selected DataSnapshot. The facade
   resolves the snapshot metadata and market-input bytes, while Python reuses
   the existing market-input artifact. Running the same legal strategy and
   snapshot again creates a distinct immutable Run with the same calculation
   identity.
6. DataSnapshot rows and referenced CAS objects are included in project archive
   export/import and retain their read model and identities after restoration.
7. The launcher installs the included A-share daily and crypto linear-perpetual
   sample CSVs into a new runtime instance's `imports/` directory without
   replacing an existing local file.

## Included sample data

- `fixtures/market/m7-a-share-daily.csv`: 8 synthetic daily bars for
  `SYNTH.XSHG`; its first four OHLC bars remain compatible with the frozen M3
  strategy fixture.
- `fixtures/market/m7-crypto-linear.csv`: 8 synthetic hourly bars for
  `BTCUSDT.PERP`.

Both samples pass the same preview, mapping, validation, normalization, and
snapshot path used by browser uploads and configured local imports.

## Local validation record

`pnpm run validate:m7` exited `0` in the current checkout. It reran the complete
M6 gate and added:

- 4 M7 contract, strict read-model, and TypeScript/Python parity tests;
- 38 Python tests spanning CSV/Parquet parity, row-numbered validation,
  idempotent snapshot commands, HTTP reads, configured imports, archive
  round-trip, real PyO3 Formal Run, and legal rerun;
- 2 control-plane tests for upload/local preview, snapshot creation/read, and
  selected-snapshot Formal Run mapping;
- 1 mocked Playwright flow for browser CSV upload through Run Detail;
- 1 cumulative real Playwright flow that starts the local Python domain, worker,
  PyO3 extension, Pi session, browser facade, and SPA, then performs local
  import preview, snapshot creation/selection, strategy edit, merge, Formal Run,
  Run Detail, and Promote.

The cumulative gate also passed all existing contract, Rust, PyO3, M5 lifecycle,
M6 session/restart, control-plane, and browser checks. Vite emitted one
non-blocking warning for an approximately 888 kB minified application chunk.

## Explicit residuals and non-claims

- M8 must add the six built-in strategies, real multi-symbol rotation support,
  and `.py`-to-`.ipynb` finalization.
- M9 must complete the formal field definitions, Python reconciliation, and
  shared HTML/JSON report export.
- M10 must add Docker Compose, six-strategy total E2E, required Ubuntu/macOS CI,
  the final local gate, ready PR, land gate, and squash merge.
- The 250,000-bar release benchmark remains a named final M10 gate; its latest
  development-Mac evidence is 12.66 seconds.

## Delivery state

- local checkout: M7 is implemented and `validate:m7` passed on branch
  `codex/oqs-m0-m10-minimal`;
- remote branch or PR: the current working tree has not been pushed and is not
  in a PR;
- local tests: the named M7 gate passed;
- CI: no CI result exists for this unpushed state;
- production: no deployment was performed;
- user acceptance: not performed; the full Goal remains active through M10.
