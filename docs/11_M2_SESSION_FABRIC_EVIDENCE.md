# M2 Pi and Session Fabric evidence

Evidence date: 2026-08-11, Asia/Shanghai.

This document records local-checkout evidence for M2. It is not remote, CI,
production, complete POC, or user-acceptance evidence.

## Implemented vertical slice

M2 implements one bounded, runnable path with Pi as the sole AgentLoop:

1. The control plane creates an official pinned Pi `AgentSession` with a
   controlled session directory, a static OQS resource loader, no ambient
   extensions/context, and no built-in filesystem or shell tools.
2. Python registers the durable OQS-to-Pi session identity and owns the
   replaceable active WorkbenchBinding projection. One live Pi adapter remains
   registered while canvas, code, and Run Detail bindings change.
3. Typed OQS tools use the TypeScript HTTP client; they never write SQLite.
   Python atomically owns message, event, outbox, receipt, and Artifact writes.
4. Offline messages remain `queued`. Delivery advances by compare-and-set
   through `receiver_received` and `injected` only after the structured message
   marker exists in Pi JSONL; application acknowledgement is explicit.
5. Bounded same-project recall returns an anchored branch/leaf, entry hash, and
   Pi source URI. Replies stage the canonical entry as a hash-addressed witness,
   and Python validates the witness before recording provenance.
6. A bounded `wait=1` event request lets an already-waiting control-plane reader
   receive a later queued event and wake the recipient without continuous model
   polling.

The real integration test starts the Python service, creates two official Pi
sessions with the official faux provider, asks from A to B, lets B's Pi call
`session_search` and then `session_reply`, and delivers the provenance-bearing
reply to A. The same test switches A across all three durable workbenches,
proves duplicate injection is idempotent, proves repeated message bodies reuse
one immutable Artifact, and exercises a live event wake.

## Contract and safety boundary

- Shared TypeScript/Python validators own registration, active-workbench bind,
  send/ask/reply, four receipt transitions, and their concrete event payloads.
- Session and Pi identities, media type, UTF-8 byte length, source count, Pi
  URI, event identity, receipt state, and receipt version are bounded before a
  durable write.
- Message bodies are stored only in the local CAS and are absent from events,
  inbox rows, receipts, SSE frames, and diagnostic logs.
- Recall is project-scoped and branch-aware. Retrieved content is rendered as
  quoted data, not system instructions. An omitted inactive-branch leaf
  deterministically selects a descendant head; an explicit historical Pi
  branch head remains valid after later children are appended.
- The adapter accepts a delivery only after a structured OQS custom-message
  entry is durable in Pi JSONL. Plain body text that resembles a marker does not
  satisfy dedupe.
- Pi is pinned to `0.84.1`; source identity, package integrities, license text,
  transitive license groups, and the no-copy donor boundary are recorded in
  `../third_party/M2_DEPENDENCY_DECISIONS.md`.

## Test-first failure evidence

Representative observed red states include:

- control-plane exit `1`: `ERR_MODULE_NOT_FOUND` for the not-yet-implemented
  `dist/session-fabric.js`;
- contracts exit `1`: the requested
  `validateSessionWorkbenchBindCommand` export did not exist;
- four focused adapter/recall regressions: streaming delivery settled before
  JSONL persistence, marker-shaped body text spoofed dedupe, an abandoned
  branch used the wrong leaf, and cross-project status leaked active metadata;
- a direct repeated-body probe returned
  `domain_conflict UNIQUE constraint failed: artifacts.sha256, artifacts.storage_uri`;
- the first hardened real integration run failed because the Pi search query
  matched the new inbox message instead of A's earlier fact;
- final review probes found an omitted inactive leaf truncating its `after`
  window and a foreign-Activity queued event blocking the current Activity's
  wake cursor.

Each red state was followed by a focused implementation and regression test.

## Local validation record

- `pnpm --filter @open-quant-studio/contracts test`: exit `0`; four contract
  and TypeScript/Python parity tests passed.
- `pnpm install --frozen-lockfile`: exit `0`; five workspace projects were
  already locked and up to date.
- `uv sync --project services/quant-domain --frozen`: exit `0`; thirteen locked
  packages were checked.
- `uv lock --project services/quant-domain --check`: exit `0`; fifteen lock
  records resolved without changing the lockfile.
- `pnpm validate:m2`: exit `0`; forty required repository files were present,
  the local data root probe passed, four shared contract/parity tests passed,
  the non-formal M0 golden oracle passed, twenty-one control-plane tests passed,
  and twenty-one independent Python tests passed.
- The control-plane count includes the real Uvicorn/two-Pi vertical slice,
  streaming JSONL durability, concurrent marker dedupe, abandoned-branch
  inference, exact-message wake after 100 historical inbox rows, and
  foreign-Activity cursor progress.
- `PYTHONPATH=services/quant-domain/src uv run --project services/quant-domain
  --frozen python -m compileall -q services/quant-domain/src
  services/quant-domain/test scripts/verify-golden-backtest.py`: exit `0`.
- `pnpm run build`: exit `0` for contracts and control-plane TypeScript.
- `pnpm licenses list --json`: exit `0`; 136 records were grouped as MIT 60,
  Apache-2.0 48, BSD-3-Clause 14, BlueOak-1.0.0 5, ISC 8, and 0BSD 1.
- `git diff --check`: exit `0` with no output.

The final independent adversarial review first reproduced two P1 defects:
inactive-leaf inference and cross-Activity event delivery. Both received red
regressions and fixes. A bounded second review checked Pi 0.84.1 branch-head
semantics and the Activity cursor path, reran all twenty-one control-plane
tests, and reported no remaining blocker. No reviewer edited the worktree.

## M2 non-claims

- Receipt cancellation, supersession, expiry, retry policy, checkpoints, and
  restart recovery remain M5 lifecycle work. The four-state M2 spine is not the
  complete frozen Session Fabric contract.
- `session_handoff`, task claim/release, cross-project lookup, authentication,
  quotas, and a persistent outbox dispatcher are not implemented.
- Recall has bounded top-K/window/result sizes but does not yet calculate an
  exact remaining Pi context-token budget.
- The Python witness check proves hash, canonical JSON, entry identity, session,
  and source URI consistency. The loopback POC has no signed caller identity, so
  this is not an authenticated external provenance service.
- No Git-backed WorkspaceRevision or StrategyVariant, Rust/PyO3 formal engine,
  formal Run, unified SPA, restart proof, or complete POC is implemented.
- The quant-assistant engine donor remains unsafe to copy because root/Rust
  license coverage and product lineage are unresolved.

## Delivery state

- local checkout: M2 implementation and evidence are present as uncommitted
  changes on local `main` at HEAD
  `95446dc248f4a7bd14831ebe03d5b2b0c67a67c3`.
- remote branch or PR: local HEAD is one commit ahead of local and queried
  remote `origin/main` at
  `c5d321e10483f76a6f6987d1ae66b620244f0ea0`; M2 is not committed, pushed, or
  represented by a PR.
- local tests: the named M2 gate and supplemental commands above passed.
- CI: `gh run list --repo dreaminate/open-quant-studio` returned `[]`; no CI pass
  exists for M2.
- production: no deployment was performed or queried.
- user acceptance: pending explicit review.
