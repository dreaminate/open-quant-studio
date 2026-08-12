# M5 recovery and lifecycle evidence

Evidence date: 2026-08-12, Asia/Shanghai.

This document records local-checkout implementation and validation evidence for
the M5 functional slice. It is not evidence of remote CI, production
deployment, M7-M10 completion, or user acceptance.

## Implemented functional slice

1. The Rust/PyO3 engine exposes deterministic checkpoint start, step, and
   finalize operations. A step advances by the RunSpec batch size and preserves
   orders, trades, positions, lots, cash and funding ledgers, equity, drawdown,
   metrics, and execution counters required to resume the same legal input.
2. Python persists every completed batch as a CAS Artifact and
   `formal_run_checkpoints` row. A reopened worker loads the latest checkpoint,
   resumes from its next bar, persists subsequent checkpoints, and finalizes the
   same formal engine result. Run reads expose pending, running, cancelled,
   failed, and succeeded lifecycle states.
3. Formal Runs support explicit cancel and retry. Retry reserves a new immutable
   Run while retaining the original RunSpec identity. Re-running the same legal
   strategy and market input succeeds with a distinct Run identity and the same
   calculation identity.
4. A persistent strategy context receives start followed by released bars in
   order. Module state survives across callbacks, and a normal strategy is not
   given unreleased future bars, the complete engine input, or an expected
   intent tape. The same path runs on the current macOS checkout without a
   platform-specific launcher dependency.
5. Structured diagnostics support Debug/Info/Warn/Error, P1-P4, scoped filters,
   full-text query, single or batch deletion, documented default retention, and
   a 2 GiB project quota measured in UTF-8 bytes. Startup cleanup removes the
   oldest eligible Debug, Info, then Warn entries; Error and P1 remain until the
   user deletes them.
6. Forward Test replays a succeeded immutable source Run bar by bar, stores a
   canonical transcript Artifact, binds the source Run/revision/snapshot and
   strategy protocol, and exposes the persisted result through Python HTTP,
   the TypeScript facade, and the SPA.
7. Project export produces a deterministic `.oqs.zip` containing a manifest,
   project SQLite rows, Git bundle and refs, and referenced CAS objects. Import
   restores a new local project and verifies Git tree, Run, and Artifact
   identities. Python HTTP, the browser facade, and the SPA expose the normal
   export/import flow.
8. The SPA Logs view queries the real filter surface and deletes selected rows.
   Forward Test and archive controls use the same typed browser facade as the
   rest of the workbench.

## Local validation record

`pnpm run validate:m5` exited `0` in the current checkout. The gate included:

- repository bootstrap and local data-root checks;
- 25 shared-contract and TypeScript/Python parity tests;
- 16 Rust tests passed, with one manual benchmark ignored by the automatic
  gate; Rust formatting and Clippy with `-D warnings` passed;
- 3 PyO3/reference tests;
- 32 focused Python domain tests for immutable Runs, workers, streamed bars,
  checkpoint/restart, cancel, retry, legal rerun, diagnostics, Forward Test,
  and archive round-trip;
- 4 control-plane tests for Forward Test, archive, log filters, and deletion;
- the research UI and web builds plus one mocked Playwright workbench vertical.

The Vite build emitted one non-blocking warning for an approximately 877 kB
minified application chunk.

## Explicit residuals and non-claims

- The named manual release gate completed 250,000 legal crypto bars with a
  fixed checkpoint batch size of 16,384 in 12.66 seconds on the current
  development Mac, below the 60-second target. It produced a 71,171,529-byte
  final checkpoint and exact finalized output equality with `run_engine_v1`.
  The command is `pnpm run test:engine:250k`; it remains separate from the fast
  automatic test loop and must run again in the final M10 functional gate.
- Data import and immutable user-created snapshots are M7 work.
- The six built-in strategies and generated notebooks are M8 work.
- Complete formula reconciliation and HTML/JSON reports are M9 work.
- Docker Compose, multi-platform CI, the ready PR, and merge are M10 work.

## Delivery state

- local checkout: M5 is implemented and the named local gate passed on branch
  `codex/oqs-m0-m10-minimal`;
- remote branch or PR: the M5 working tree has not been pushed and is not in a
  PR;
- local tests: the named `validate:m5` gate passed;
- CI: no CI result exists for this unpushed state;
- production: no deployment was performed;
- user acceptance: pending explicit user review and completion of M7-M10.
