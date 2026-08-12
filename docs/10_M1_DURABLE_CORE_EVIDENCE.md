# M1 durable core evidence

Evidence date: 2026-08-11, Asia/Shanghai.

This document records local-checkout evidence for M1. It is not remote, CI,
production, complete POC, or user-acceptance evidence.

## Implemented vertical slice

M1 implements one real bounded path:

1. `PUT /v1/artifact-blobs/{sha256}` verifies and stages bytes in the local CAS.
2. `POST /v1/commands` validates a concrete `context.capture` envelope.
3. Python opens `BEGIN IMMEDIATE` and writes project/activity bootstrap state,
   immutable Artifact metadata, immutable raw context evidence, an immutable
   event, outbox row, command receipt, pending verification job, and structured
   log atomically.
4. Exact command replay returns the original event without another write;
   divergent reuse of the command ID returns an explicit conflict.
5. `GET /v1/events` emits ordered SSE frames and resumes strictly after the
   acknowledged decimal `Last-Event-ID`.
6. The durable runner claims one job with a started event/outbox row, verifies
   the real CAS bytes, and records a compare-and-set terminal event/outbox/log.
7. The TypeScript fetch client consumes the real Uvicorn bytes, validates the
   concrete event payload, and advances its cursor only after the callback
   resolves; callback failure deliberately redelivers from the prior cursor.

## Contract and data boundary

- Twenty-two shared positive/negative fixture vectors cover generic envelopes,
  Artifact references, `context.capture`, `context.captured`, three job event
  states, and diagnostic logs through both Ajv and Python jsonschema.
- Artifact `storage_uri` must bind the same SHA-256 in both runtime validators.
- M1 rejects non-null revision, variant, and formal-Run provenance that M3 does
  not yet own.
- Artifact provenance accepts only an opaque UUID `source_ref` before any
  database write.
- No donor or Pi source is present. New HTTP runtime dependencies and licenses
  are recorded in `../third_party/M1_DEPENDENCY_DECISIONS.md`.

## Persistence evidence

- SQLite startup requires and verifies WAL mode plus foreign-key enforcement.
- The migration ledger executes only pending files, records each migration only
  after success, and skips a deliberately non-repeatable migration on reopen.
- Command tests cover invalid pre-write rejection, a late constraint failure
  after an Artifact insert, full rollback, exact replay, divergent command-ID
  conflict, and two simultaneously blocked callers producing one outcome.
- Database triggers reject updates to domain events, Artifacts, and context
  items. Future dependency-aware deletion is not part of M1.
- Job tests cover deterministic hash success, explicit missing-blob failure,
  pending/running/terminal events, and rejection of a stale duplicate finish
  without an extra terminal event or outbox row.
- Diagnostic logs contain every required field, keep level and priority
  independent, support project/level/priority filters, and never store command
  payloads. Retention and user deletion remain M5 work.

## Test-first failure evidence

The implementation was driven through observed red states rather than only a
final green run. Representative raw failures were:

- contract test exit `1`: requested `validateArtifactRef` export did not exist;
- Python suite exit `1`: `No module named 'quant_domain.domain'`;
- real server test exit `1`: `No module named uvicorn`;
- control-plane test exit `1`: SSE client module did not exist;
- concrete event negative test exit `1`: `Missing expected rejection`;
- a focused regression initially exposed a rerun-only migration ledger and a
  stale duplicate job terminal event.

Each failure was followed by a focused implementation and passing regression.

## Local validation record

- `pnpm install --frozen-lockfile`: exit `0`; five workspace projects already
  up to date.
- `uv sync --project services/quant-domain --frozen`: exit `0`; thirteen locked
  packages checked.
- `pnpm validate:m1`: exit `0`; the M0 33-file/data-root/golden gates regressed
  cleanly, TypeScript/Python agreed on all 22 fixture vectors, five
  control-plane tests passed including a real Uvicorn wire test, and nine Python
  disk/HTTP tests passed with `ResourceWarning` promoted to an error.
- `PYTHONPATH=services/quant-domain/src uv run --project services/quant-domain
  --frozen python -m compileall -q services/quant-domain/src
  services/quant-domain/test scripts/verify-golden-backtest.py`: exit `0`.
- `uv lock --project services/quant-domain --check`: exit `0`; fifteen lock
  records resolved without a lockfile change.
- `pnpm run build`: exit `0` in the independent SSE/contracts re-review.
- `git diff --check`: exit `0` with no output.

Three independent read-only re-reviews then reran the full or focused gates.
The acceptance/contracts reviewer, SQLite/domain reviewer, and HTTP/SSE reviewer
all reported no remaining P0-P2 finding. The bounded SSE parser's support for
this producer's LF/CRLF `id/event/data` frames is a documented P3 limitation,
not a general-purpose EventSource claim.

## M1 non-claims

- No Pi dependency, Pi session, Session Fabric, second AgentLoop, or M2 behavior
  is implemented.
- No Rust/PyO3 formal engine, immutable formal Run, revision/variant/CAS Promote,
  unified SPA, restart recovery, retry/cancellation/checkpointing, Pi wake-up,
  outbox delivery, log deletion/retention, project import/export, or POC E2E is
  implemented.
- The M0 accounting fixture remains a non-formal oracle.
- GitHub Actions currently has no run records, so CI has not passed. Production
  was not deployed by this work; user acceptance is pending.

## Delivery state

- local checkout: M1 implementation and evidence are present in the dirty local
  checkout on `main` at base HEAD
  `c5d321e10483f76a6f6987d1ae66b620244f0ea0`; the pre-existing uncommitted M0
  work is preserved.
- remote branch or PR: local HEAD, local `origin/main`, and queried remote
  `main` match the base SHA with ahead/behind `0/0`, but all M0/M1 work remains
  uncommitted and no branch, push, or PR was created.
- local tests: the commands above passed.
- CI: `gh run list --repo dreaminate/open-quant-studio` returned `[]`; no CI pass
  exists for the uncommitted M1 tree.
- production: no deployment was performed; external production is unqueried.
- user acceptance: pending explicit user review.
