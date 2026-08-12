# M3 immutable Formal Run and gated Promote evidence

Evidence date: 2026-08-12, Asia/Shanghai.

This document records local-checkout evidence for M3. It is an implementation
and local-validation record, not evidence of remote CI, production deployment,
or user acceptance. M4-M10 remain separate milestones.

## Implemented vertical slice

1. Seven actor-bound Pi tools create a root revision, fork a
   StrategyVariant, create a child revision, compare revisions, create a merge
   candidate, request a Formal Run, and attempt gated Promote. Project,
   Activity, session, and active-workbench identities come from the
   control-plane binding rather than model-supplied parameters.
2. TypeScript validates complete shared commands before staging bytes. Python
   remains the only durable business writer: it owns immutable revision,
   variant, job, RunSpec, Run, artifact-link, validation, event, receipt,
   outbox, log, and promotion records.
3. WorkspaceRevisions point to real project-local bare-Git commits. A merge
   candidate is an immutable ordered two-parent commit whose resolved tree must
   be the complete union of both parent path sets. Creating a candidate moves
   neither the project head nor the StrategyVariant head.
4. A `formal.run_request` reserves its `validation_id`, freezes a RunSpec, and
   creates a new immutable Run identity. Re-running the same RunSpec creates a
   new Run and manifest while retaining the same deterministic intent-tape and
   engine-result calculation identities.
5. The strategy subprocess receives ordered bars but cannot observe the caller's
   expected intent tape. It returns raw callback batches. The trusted parent
   stamps `known_at`, defaults `effective_at` to the next bar open or validates
   its exact three-field shape for a strategy-requested later future open, and
   persists the ordered intent tape as a content-addressed artifact.
6. Rust/PyO3 consumes the exact canonical input bytes that contain the persisted
   tape. Rust is the sole authority for fills, orders, trades, signed positions,
   cash, fees, tax, slippage, funding, equity, drawdown, metrics, and calculation
   output. Python records the returned bytes and hashes without recomputing any
   formal result.
7. A succeeded Run binds the immutable intent-tape, engine-result, and per-Run
   manifest artifacts. Contract validation requires
   `calculation_hash == engine_result_sha256`. A failed Run remains immutable,
   has no result artifacts, retains its merge candidate, and cannot authorize
   Promote.
8. `workspace.revision_promote` requires the exact passed validation and
   compare-and-set identities for both the project and StrategyVariant heads.
   Both heads move atomically. When two independently validated candidates race,
   exactly one wins; the stale candidate writes no promotion receipt or event.
9. The official Pi adapter executes the merge -> Formal Run -> Promote lineage
   through the typed HTTP client. The SSE client validates and acknowledges the
   queued -> started -> completed -> promoted lifecycle in order.

## Cleanroom engine and market contracts

- The engine in `crates/quant-engine` is OQS-owned cleanroom Rust. No QuantBT,
  quant-assistant, VibeTrading, or other donor source was copied.
- A-share tests cover 100-share lots, T+1, long and explicit research-short
  accounting, Market/Limit/Stop, GTC/DAY behavior, stop-first OCO ordering,
  gap execution, commission, stamp duty, and slippage.
- Crypto tests cover T+0 linear perpetual long/short/cover accounting, maker and
  taker fees, slippage, funding, wallet reconciliation, and stop-first OCO.
- Fixed-point integers and checked arithmetic are used for formal calculations.
  Malformed market and cost inputs fail closed.
- The generic PyO3 seam is byte-deterministic. The frozen A-share fixture also
  reconciles against an independent Python `Decimal` reference.

## Strategy execution boundary

The candidate is imported and called in a child interpreter with ordered bars.
It returns raw callback batches. The parent stamps `known_at`, defaults
`effective_at` to the next bar open or validates its exact three-field shape
for a strategy-requested later future open, and persists the ordered intent tape
as a content-addressed artifact.

## Test-first correctness evidence

Representative failures found and fixed while closing M3 include:

- a shared content-addressed engine result initially conflicted with per-Run
  artifact metadata on deterministic rerun;
- intent-tape comparison initially used caller-provided data instead of the
  callback output;
- duplicate `validation_id` allocation could initially leave a running job after
  a late uniqueness failure;
- a merge candidate initially accepted only payload files and could drop
  inherited parent files;
- contract fixtures initially accepted a completed Formal Run whose calculation
  hash did not equal its engine-result content identity;
- the parent and Rust initially accepted an `effective_at` with unknown fields,
  allowing ignored child-controlled data to alter a successful immutable tape;
- control-plane tests initially listed the new tools without executing the
  merge/Formal Run/Promote chain through Pi.

Each failure has a focused regression. Engine and domain-integrity correctness
checks were rerun against the stabilized source and reported no remaining P0 or
P1 correctness blocker in their reviewed M3 boundaries.

## Local validation record

`git diff --check && pnpm run validate:m3` exited `0` on this working tree. The
gate included:

- bootstrap manifest: 46 required files present;
- shared contracts: 12 tests passed, including TypeScript/Python parity and
  calculation-hash rejection;
- control plane: 32 tests passed, including typed Pi execution and ordered SSE;
- M1-M2 Python base regression: 22 tests passed;
- Rust: 11 engine tests passed; `cargo fmt --check` and Clippy with
  `-D warnings` passed;
- PyO3: 2 tests passed;
- complete Python domain discovery: 53 tests passed with `ResourceWarning`
  treated as an error;
- focused M3 suites: 8 contract, 10 control-plane, and 31 Python tests passed.

The legacy M0 golden fixture still reports
`formal_engine_integrated=false`. It remains a non-formal bootstrap fixture and
is not relabelled as M3 evidence.

## Explicit residuals and non-claims

- The formal throughput target and the full M10 multi-platform gate have not yet
  been recorded.
- M4-M9 UI, job/projection, data, strategy-library, Run Detail, and report work
  are not implied by this engine/domain/control-plane slice.
- Restart recovery, export/import, log lifecycle, and the full POC acceptance
  matrix are later milestone evidence.
- No remote CI, production deployment, or user acceptance is claimed here.

## Delivery state

- local checkout: M3 is implemented as uncommitted changes on branch
  `codex/oqs-m0-m10-minimal`, based on checkpoint
  `146024de37ea228bedc27b29e134b0d80df53e81`;
- remote branch or PR: this M3 working-tree state has not been pushed and is not
  represented by a PR;
- local tests: the commands and counts above passed in the current checkout;
- CI: no CI result exists for this unpushed state;
- production: no deployment was performed;
- user acceptance: pending explicit review and completion of M4-M10.
