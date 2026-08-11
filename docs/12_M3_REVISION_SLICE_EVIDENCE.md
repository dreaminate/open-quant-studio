# Partial M3 revision/variant/CAS evidence

Evidence date: 2026-08-11, Asia/Shanghai.

This document records local-checkout evidence for the provenance-safe part of
M3. It is deliberately **not** an M3 completion record: the required formal
Rust/PyO3 engine, immutable RunSpec/Run path, and formal gates are blocked and
not implemented.

## Implemented vertical slice

1. Five actor-bound Pi tools create a root revision, fork a StrategyVariant,
   create a child revision, compare two revisions, and attempt CAS Promote.
   Project, Activity, session, and active workbench identities come from the
   control-plane binding rather than model-supplied tool parameters. When the
   model omits `command_id`, the adapter derives it from the Pi tool-call and
   actor identity, so the same tool retry reaches Python with the same command,
   revision/variant, and correlation identities.
2. TypeScript validates the complete shared command before staging bytes. It
   uses the same content-derived Artifact/provenance identity as M2 messages,
   stages bounded UTF-8 text through the Python CAS endpoint, and submits the
   mutation through the typed Python command boundary.
3. Python owns every durable write. One `BEGIN IMMEDIATE` transaction records
   immutable revision/variant/file state, the event, outbox row, command
   receipt, structured log, and promotion audit. Project and variant heads are
   explicit projections; stale head updates return typed conflicts and write no
   receipt.
4. Each WorkspaceRevision points to a real project-local bare-Git commit, tree,
   and blobs. Root revisions have no parent; variant children have the exact
   prior variant-head commit as their sole parent. File paths reject control
   characters, `.git` case variants, traversal, and file/directory collisions.
   Accepted commits receive immutable `refs/oqs/revisions/<uuid>` refs and
   survive `git gc --prune=now`.
5. Two variants created from one root retain different child heads and Git
   trees. Compare returns bounded Artifact IDs and hashes without source bodies.
   A project may register at most 64 variants, matching the bounded read
   contract enforced by the TypeScript client.
   A two-thread Promote race records exactly one winner; the stale candidate
   receives `promotion_conflict` and has no command receipt. Immutable project
   head history also forbids re-entering an old head revision, closing CAS ABA;
   an intentional revert must use a new revision identity.
6. Read-only HTTP endpoints expose revision detail, variant heads, metadata
   comparison, and the current project revision head. The real HTTP test stages
   blobs, creates the complete root/two-variant/two-child graph, promotes one
   candidate, and observes the stale conflict for the other.

## Cleanroom and authority boundary

- No QuantBT, quant-assistant, VibeTrading, or other donor source was copied.
- The Git object writer is OQS-owned code using `/usr/bin/git` plumbing with
  argv invocation, a controlled `GIT_DIR`, no shell, and SHA-1 Git object IDs.
  Artifact content identity remains SHA-256.
- Pi remains the sole AgentLoop. The new tools use the already pinned official
  Pi `AgentSession`; there is no supervisor, ReAct loop, or second runtime.
- The quant-assistant engine donor remains excluded because current source
  lineage and root/Rust reuse rights are unresolved. Crate metadata alone is
  not sufficient evidence to copy or integrate the engine.

## Test-first failure evidence

Representative observed red states before implementation or hardening:

- contracts: the M3 test failed because `dist/index.js` had no
  `M3_COMMAND_TYPES` export;
- Python domain: the first M3 test failed importing the absent
  `PromotionConflict` symbol;
- control plane: twenty-one existing tests passed while the new M3 test failed
  with `ERR_MODULE_NOT_FOUND` for `dist/domain-revision-client.js`;
- HTTP: focused M3 tests initially raised `AttributeError` for absent
  `revision`, `variants`, `compare_revisions`, and `project_head` APIs;
- Git-path hardening: the shared validator accepted an embedded-newline
  `mktree` path, `.GIT/config` was accepted, and a file/directory prefix
  collision raised raw `TypeError` instead of a bounded domain error;
- adversarial control-plane tests showed that an omitted model `command_id`
  generated different variants on retry, a mismatched top-level receipt
  `command_id` was accepted, and a 256 KiB server error code was copied into an
  exception;
- a Python regression created a 65th variant even though the control-plane read
  contract rejects catalogs larger than 64.

Each red state received a focused implementation and regression test before
the full local gate was rerun.

## Local validation record

- `pnpm --filter @open-quant-studio/contracts test`: exit `0`; ten tests passed,
  including shared TypeScript/Python M3 parity and negative path/lineage cases.
- `pnpm --filter @open-quant-studio/control-plane test`: exit `0`; thirty
  tests passed. The nine M3 tests include deterministic Pi tool-call retries,
  receipt identity binding, bounded HTTP error parsing, an official faux Pi
  `strategy_variant_create` call and a real Uvicorn regression proving that the
  same text can be registered first by an M2 message and then reused by an M3
  revision without Artifact identity conflict.
- the Python discovery run executed by `pnpm validate:m2`: exit `0`;
  thirty-seven M1-M3 tests passed, including real Git object inspection and GC
  survival, unsafe path rejection, immutable rows, the 64-variant bound,
  independent variant heads, HTTP reads, duplicate-write side-effect checks,
  ABA rejection, and a concurrent two-candidate Promote race.
- the non-formal M0 golden fixture still reports
  `formal_engine_integrated=false`; this is a guard against mislabelling it as
  the required M3 engine.

- `pnpm validate:m3-revisions`: exit `0`; it reran the 44-file bootstrap
  manifest, ten contract tests, the non-formal golden fixture, thirty
  control-plane tests, thirty-seven Python tests, and the focused M3 suites
  (six contract, nine control-plane, and sixteen Python tests).
- `git diff --check`: exit `0`.
- Independent domain review reran the accepted-ref GC, forced SQLite rollback,
  ABA, and duplicate-revision probes and closed all three findings. Independent
  control-plane review reran real HTTP tool-call replay, 64/65 variant writes,
  forged receipt identity, and bounded error parsing probes and closed all four
  findings without discovering a new P0-P2 blocker in those axes.

## Explicit non-claims and residual work

- The formal Rust/PyO3 engine is not integrated or built. There is no Formal
  RunSpec, immutable Run, order/trade/equity output, fee accounting result, or
  formal gate record. POC acceptance scenarios 4 and 5 do not pass.
- Compare is implemented; a typed merge operation is not. A merge-capable Git
  commit and conflict-resolution workflow remain future M3 work.
- Accepted Git commits are retained by immutable revision refs and the GC
  survival path is tested. A process crash in the narrow ref-before-SQLite-
  commit window can still require ref/database reconciliation; restart repair,
  export/import, and recovery proof belong to M5.
- There is no unified SPA surface for revision comparison or promotion. That is
  M4, not evidence from this service/control-plane slice.
- Restart recovery, project export/import, log lifecycle, CI, deployment, and
  full POC closure remain unverified or later work.

## Delivery state

- local checkout: the partial M3 revision implementation is present as
  uncommitted changes on local `main` at HEAD
  `95446dc248f4a7bd14831ebe03d5b2b0c67a67c3`.
- remote branch or PR: queried local and remote `origin/main` both point to
  `c5d321e10483f76a6f6987d1ae66b620244f0ea0`; this partial M3 work is not
  committed, pushed, or represented by a PR.
- local tests: the named focused suites and `pnpm validate:m3-revisions` passed
  in the current uncommitted checkout.
- CI: `gh run list --repo dreaminate/open-quant-studio` returned `[]`; no CI
  pass exists for this slice.
- production: no deployment was performed or queried.
- user acceptance: pending explicit review; the full POC cannot be accepted
  while M3 formal-engine requirements and M4-M6 gates remain open.
