# Open Quant Studio handoff

Treat this file as a routing index, never as current implementation or delivery proof.

## Goal

Deliver the minimal single-user, local-first, research-only M0-M10 product in
`docs/08_IMPLEMENTATION_PLAN.md`. Pi is the sole AgentLoop, Python is the sole
business-state writer, the formal engine is OQS cleanroom Rust/PyO3, and one
OQS-owned React/Vite SPA owns the UI. No real trading or donor source copying.

## Verified checkpoint at generation

- Local branch: `codex/oqs-m0-m10-minimal`.
- Checkpoint: `146024de37ea228bedc27b29e134b0d80df53e81`.
- `pnpm validate:m3-revisions` passed at that checkpoint: 10 contracts,
  30 control-plane, 37 Python, and focused M3 6/9/16 tests.
- The checkpoint implements M0-M2 and only the revision/variant/CAS portion of M3.
- The M0 golden remains explicitly non-formal.
- Remote branch/PR, CI, production, and user acceptance were not established by
  the checkpoint.

Refresh all of those facts before using them.

## Read first

1. `AGENTS.md`
2. `README.md`
3. `docs/00_PROJECT_CHARTER.md` through `docs/08_IMPLEMENTATION_PLAN.md`
4. `docs/09_M0_FOUNDATION_EVIDENCE.md` through the latest evidence file
5. live Git status, remotes, tests, workflow runs, and any current Goal state

## Current implementation boundary at generation

The next coherent work is the remainder of M0 authority/license synchronization
and M3: cleanroom engine/PyO3, immutable RunSpec/Run, typed merge, formal gates,
and gated CAS Promote. Do not begin M4 until the complete M3 vertical slice and
its tests pass.

## Constraints

- Preserve dirty worktrees and unrelated changes; never reset, clean, or stash implicitly.
- Donor repositories remain read-only and oracle-only.
- Default Pi shell/filesystem/edit/write remain disabled. Trusted Local Mode is
  opt-in and limited to the project workspace plus imports/exports.
- Formal results bind data, code, parameters, costs, engine, environment, and hashes.
- Report local checkout, remote/PR, local tests, CI, production, and user acceptance separately.
- Commit, push, PR, merge, and deployment require authority from the active user
  request and the matching land/workspace gate; this handoff grants none.

## Resume

Run `git status --short --branch`, reopen live evidence, then execute the
earliest incomplete milestone in `docs/08_IMPLEMENTATION_PLAN.md` with its
narrowest reliable validation. Never mark the full Goal complete at M6.
