# Open Quant Studio

Open Quant Studio is a single-user, local-first quantitative research studio. It combines selected product ideas from VibeTrading, QuantBT, and quant-assistant around one Pi AgentLoop without copying donor source or retaining competing runtimes.

Repository: https://github.com/dreaminate/open-quant-studio

## Current state

Checkpoint `ae5fd02` contains the M0 foundation, M1 durable-domain slice, M2 Pi
Session Fabric, and the provenance-safe M3 formal Run slice. The current local
working tree implements the M4 unified desktop vertical on top of that checkpoint.
M2 pins the
official Pi `AgentSession`, keeps built-in filesystem and shell tools disabled,
and connects real Pi sessions through the Python-owned catalog, inbox, receipt
state machine, bounded JSONL recall, verified source references, and durable
wake path. M3 adds Pi-bound merge/Formal Run/Promote tools, immutable Git and
SQLite WorkspaceRevisions, isolated StrategyVariant heads, ordered two-parent
merge commits, an OQS cleanroom Rust/PyO3 engine, immutable RunSpec/Run and
content-addressed formal artifacts, validation-gated compare-and-set Promote,
and explicit stale conflicts.

The M4 working tree adds strict project/activity/artifact/Run read models, a
continuous Python worker, a sealed same-origin browser facade, the single
React/Vite SPA, and both mocked and real browser vertical tests. The M4 formal
path uses a pinned synthetic fixture and does not establish market performance.
Restart recovery, full log lifecycle, local data import, the six-strategy
library, reports, Docker/CI, and the complete POC remain not implemented. All donor
repositories remain read-only and no donor source was copied. The M0 oracle is
not a formal Run. Read [the M0 evidence](docs/09_M0_FOUNDATION_EVIDENCE.md), [the
M1 evidence](docs/10_M1_DURABLE_CORE_EVIDENCE.md), [the M2
evidence](docs/11_M2_SESSION_FABRIC_EVIDENCE.md), [the M3
evidence](docs/12_M3_REVISION_SLICE_EVIDENCE.md), and [the M4
evidence](docs/13_M4_UNIFIED_WORKBENCH_EVIDENCE.md).

## Non-negotiable product boundaries

- Research only. No broker or exchange order submission.
- All supported assets use real long/short research semantics; formal simulations use structured orders, signed positions, covering, and configurable costs.
- Pi is the sole AgentLoop and model/provider entrypoint.
- OQS-owned cleanroom Rust/PyO3 code is the only formal backtest authority.
- One OQS-owned React/Vite SPA supplies the workbench, React Flow canvas, Run Detail, comparison, and research gates.
- Donors may supply named behavior or test oracles only; they are never runtime dependencies or source-copy shortcuts.
- Python owns durable domain writes; TypeScript uses versioned HTTP commands and SSE events.
- Concurrent sessions create independent WorkspaceRevision/StrategyVariant histories. Last-write-wins is forbidden.
- Logs are structured, levelled, prioritised, and user-deletable.

## Repository map

```text
apps/web/                  React/Vite unified frontend
apps/control-plane/        Pi adapter and Session Fabric
services/quant-domain/     Python domain service and Job Runner
crates/quant-engine/       OQS cleanroom Rust/PyO3 formal engine
packages/contracts/        command, event, artifact, and tool contracts
packages/research-ui/      OQS-owned workbench components
fixtures/                  synthetic M0 market data and golden accounting oracle
docs/                      frozen architecture and POC gates
prompts/                   fresh-session development and handoff prompts
third_party/               provenance and attribution policy
```

## Start here

1. Read [AGENTS.md](AGENTS.md).
2. Read [the project charter](docs/00_PROJECT_CHARTER.md) through [the implementation plan](docs/08_IMPLEMENTATION_PLAN.md).
3. Run `pnpm install --frozen-lockfile` and `uv sync --project services/quant-domain --frozen`.
4. Run `pnpm validate:m4` before relying on the current local M4 evidence.
5. Run `pnpm start:m4`, then open `http://127.0.0.1:4173`. The launcher builds
   the SPA and PyO3 extension and starts the local domain, worker, Pi session,
   and browser facade against `var/m4-local` by default.
6. Use [HANDOFF_PROMPT.md](prompts/HANDOFF_PROMPT.md) when transferring the work to another session.

## License

Open Quant Studio is licensed under the [MIT License](LICENSE). Third-party notices and exact dependency/source boundaries live under [`third_party/`](third_party/). The project license does not grant permission to copy donor code whose own rights or provenance are unresolved.
