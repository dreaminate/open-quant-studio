# Open Quant Studio agent rules

## Read order

Before non-trivial work, read:

1. `README.md`
2. `docs/00_PROJECT_CHARTER.md`
3. the document that owns the subsystem being changed
4. `docs/07_POC_ACCEPTANCE.md`
5. `docs/08_IMPLEMENTATION_PLAN.md`

Git, current files, tests, CI, and queried external state are the sources of truth. Planning documents and handoffs are indexes, not implementation proof.

## Product invariants

- Research only; never add real broker/exchange order submission.
- Pi is the only AgentLoop. Do not add another ReAct loop, supervisor LLM, or agent runtime.
- TypeScript owns active Pi sessions and orchestration. Python owns durable business writes and jobs. Rust/PyO3 owns formal backtest calculations.
- One React/Vite SPA owns the UI. Do not add iframes, microfrontends, or donor applications as runtime dependencies.
- The Research Project Graph owns relationships and lineage. The infinite canvas is an editable projection, not a second workflow engine.
- A Run is immutable. Re-running creates a new Run.
- Concurrent writers create child WorkspaceRevisions/StrategyVariants. Never implement last-write-wins.
- Shell output cannot become an official Run, metric, or Canonical Context without a typed domain command.
- Formal results must bind data snapshot, code revision, parameters, cost model, engine version, environment, and artifact hashes.
- Logs use the contract in `docs/05_LOGGING_AND_RETENTION.md` and remain user-deletable.

## Donor boundaries

Treat all donor repositories as read-only until `docs/06_MIGRATION_MAP.md` has been refreshed from live Git state. Never copy uncommitted donor changes implicitly. Every migrated slice requires a source URL, exact commit or reviewed local snapshot, license, attribution, changed-file list, and validation oracle.

## Work discipline

- Work milestone by milestone. M0 must pass before M1 begins.
- Before edits, run `git status --short --branch` and preserve unrelated changes.
- Use a bounded plan for any task spanning more than one subsystem.
- Add tests with behavior. A directory, schema, prompt, mock, or passing type check is not an end-to-end integration.
- Do not add dependencies until the responsible package exists, the upstream implementation has been checked, and the dependency boundary is documented.
- Do not log credentials, cookies, authorization headers, private environment values, or raw secret-bearing configuration.
- Commit, push, PR, deployment, and public release remain separate delivery states.

## Completion reporting

Every handoff and completion report must separate:

- local checkout
- remote branch or PR
- local tests
- CI
- production
- user acceptance
