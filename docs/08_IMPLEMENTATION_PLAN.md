# M0-M10 implementation plan

This plan is the authority for the minimal single-user product. Each milestone
must end in a runnable vertical slice with automated evidence. A directory,
schema, mock, empty page, or type check alone does not satisfy a milestone.

## M0: Foundation, decisions, and entrypoints

- Refresh live Git, remote, license, donor, dependency, and toolchain evidence.
- Keep every donor read-only; build the formal engine and SPA as OQS cleanroom code.
- Select the MIT project license and retain required third-party notices.
- Freeze synthetic fixtures and the deterministic non-formal golden oracle.
- Provide root frozen-install, build, test, and data-root commands.

Exit: a fresh checkout can install frozen dependencies, check the local data
root, and run the contract/golden foundation gate without donor source.

## M1: Contracts and durable domain core

- Version command, event, Artifact, and log contracts.
- Run the Python HTTP service over SQLite WAL, Git/CAS paths, migrations, jobs,
  outbox, events, and structured logs.
- Prove typed HTTP command -> atomic durable writes -> resumable SSE,
  idempotent command handling, CAS transitions, and large-body CAS storage.

Exit: the real HTTP/SQLite/SSE vertical test passes.

## M2: Pi and Session Fabric

- Use the pinned official Pi `AgentSession` as the only AgentLoop.
- Keep one session across workbenches and prove two-session ask/retrieve/reply,
  provenance, offline delivery, receipt CAS, wake, and reopen.
- Present Pi's own provider/model/config settings through the OQS adapter.

Exit: the official faux provider passes the two-session local integration gate
without an external API key.

## M3: Revisions, formal engine, Run, merge, and promote

Local status on 2026-08-12: implemented and passed by `pnpm validate:m3` in the
working tree; remote CI is not yet available. See
`docs/12_M3_REVISION_SLICE_EVIDENCE.md` for the exact proof boundary.

- Keep immutable Git-backed WorkspaceRevisions, protected refs, independent
  StrategyVariant heads, compare, typed merge revisions, and CAS Promote.
- Implement an OQS cleanroom Rust/PyO3 engine. Strategies emit structured
  OrderIntents; Rust owns fills, signed positions, cash, fees, equity,
  drawdown, and metrics using deterministic fixed-point accounting.
- Support Market, Limit, and Stop; conservative same-bar `stop-first`; gap
  execution; A-share daily 100-share lots/T+1/tradability/long plus labelled
  `research_short`; crypto T+0 1x linear-perpetual long/short.
- Apply A-share commission/sell stamp duty/slippage and crypto maker/taker
  fee/slippage/optional constant funding to every formal ledger surface.
- Freeze immutable RunSpec/Run identity, data/code/parameter/cost/engine/
  environment provenance, formal outputs, logs, artifacts, and gate outcomes.
- A Pi-generated merge candidate must pass contract import and smoke-Run gates
  before a typed CAS Promote; failure preserves the candidate without moving a head.

Exit: two variants run through real PyO3 with reproducible long/short/cover,
orders/trades/cash/equity/metrics/costs and explicit stale Promote conflict.

## M4: Unified desktop SPA

- Build one desktop-first React/Vite SPA with Projects, Activity, React Flow
  Canvas, Pi Chat, Code, Backtest, Forward Test, Run Detail, Data, Logs, and Settings.
- Limit Canvas to pan/zoom, Session/Strategy/Run/Artifact nodes, edges, drag,
  persisted layout, and detail selection.
- Run Detail renders the same formal Run artifact; the UI does not recalculate
  a competing metric set.

Exit: a browser user can move from Project/Activity through strategy edit and
Run to Run Detail, compare, and Promote.

## M5: Recovery and lifecycle

- Checkpoint a formal Run at fixed bar batches and resume after restart; support
  cancel and explicit retry without a distributed scheduler.
- Implement log filters, single/bulk deletion, startup retention cleanup, and
  removal of deleted bodies/search hits.
- Export/import one project as `.oqs.zip` with Git bundle/refs, Run artifacts,
  reports, strategies, CAS objects, manifest, and identity hashes.
- Implement Forward Test as local historical walk-forward/replay with no future access.

Exit: restart resumes a long Run, deleted logs are unavailable, and an exported
then imported project preserves Git tree, Run, and Artifact identity.

## M6: Core POC gate

Run all ten automated scenarios in `07_POC_ACCEPTANCE.md`, including browser
E2E. M6 is only the original core POC closure; M7-M10 remain open.

## M7: Local data import and immutable snapshots

Local status on 2026-08-12: implemented and passed by `pnpm validate:m7` in the
working tree; remote CI is not yet available. See
`docs/16_M7_LOCAL_DATA_SNAPSHOT_EVIDENCE.md` for the exact proof boundary.

- Import CSV and Parquet from the SPA or local `imports/` directory.
- Preview field mapping; validate symbol/date/OHLCV with row-numbered errors.
- Create immutable DataSnapshot metadata and SHA-256 for A-share daily and
  crypto bars, including timezone, price basis, cutoff, schema, range, and count.
- Ship directly runnable A-share and crypto sample datasets.

Exit: a UI import creates a snapshot that immediately runs through the engine.

## M8: Strategy workbench and six strategies

Local status on 2026-08-12: implemented and passed by `pnpm validate:m8` in the
working tree; remote CI is not yet available. See
`docs/17_M8_STRATEGY_WORKBENCH_EVIDENCE.md` for the exact proof boundary.

- Treat `.py` as the only authoritative source. Generate a companion `.ipynb`
  only when finalizing; do not run Jupyter Server or implement notebook sync.
- Ship A-share trend/breakout, labelled research-short, and rotation plus
  crypto trend, mean-reversion, and breakout strategies.
- Give every strategy real parameters, entry/exit/risk logic, revision,
  formal Run, Run Detail, report, and browser E2E coverage.

Exit: all six strategies run and their finalized notebooks can be exported.

## M9: Run Detail formulas and reports

Local status on 2026-08-12: implemented in the working tree. The focused
contracts, Python reference/materialization/archive, control-plane, and browser
tests pass, and the cumulative `pnpm run validate:m9` milestone gate exits 0.
See `docs/18_M9_RUN_REPORT_EVIDENCE.md` for the exact proof boundary.

- Define name, unit, formula, inputs, and empty behavior for every formal field.
- Independently recompute displayed fields in a Python reference from formal
  orders/trades/equity and differential-test it against Rust.
- Reconcile fees, trade count, date bounds, open positions, and ending equity;
  cover long/short/cover, T+1/T+0, stop-first, costs, and zero trades.
- Export SPA Run Detail, standalone HTML, and JSON manifest from one Run artifact.

Exit: all six reports pass formulas/reconciliation and survive project archive.

## M10: Docker, total E2E, CI, PR, and merge

Local status on 2026-08-12: the Docker runtime, total browser journey,
250,000-bar release benchmark, delivery checks, and Ubuntu/macOS workflow are
implemented, and `pnpm validate:m10` exits 0 in the working tree. Remote CI,
the ready PR, and squash merge remain pending. See
`docs/19_M10_DELIVERY_EVIDENCE.md` for the exact local proof boundary.

- `docker compose up --build` starts web, control plane/Pi, Python domain, and
  the PyO3 runtime with named persistent state volumes and host imports/exports.
- Run all six strategies through import -> snapshot -> source/notebook ->
  revision/variant -> Run -> detail/report -> compare/merge/promote -> archive identity.
- Provide `validate:m0` through `validate:m10`; `validate:m10` covers contracts,
  TypeScript, Python, Rust, differential formulas, Chromium E2E, Compose,
  locks, licenses, and `git diff --check`.
- Required GitHub Actions run on Ubuntu and macOS; Windows, Kubernetes, cloud
  databases, ingress, and HA are excluded.
- After local gates, a functional review and land gate confirm no blocker on
  normal user paths with required CI green; create the ready PR, squash merge,
  and verify the merged commit checks. Never bypass failed CI.

Exit: Compose and `validate:m10` pass, required CI is green, the PR is squash
merged, and the merge commit has passing required-check evidence.

## Sequencing and delivery truth

Work milestone by milestone and implement the smallest user-visible vertical
slice before abstraction or hardening. Later work cannot excuse a missing
predecessor. Report local checkout, remote branch/PR, local tests, CI,
production, and user acceptance separately. Production deployment is outside
this plan, and CI/merge never imply user acceptance.
