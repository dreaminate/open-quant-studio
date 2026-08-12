# Open Quant Studio

Open Quant Studio is a single-user, local-first quantitative research studio. It combines selected product ideas from VibeTrading, QuantBT, and quant-assistant around one Pi AgentLoop without copying donor source or retaining competing runtimes.

Repository: https://github.com/dreaminate/open-quant-studio

## Current state

Checkpoint `c0cbe40` contains the M0 foundation through the M4 unified desktop
vertical. The current branch implements the M5 recovery/lifecycle slice, M6
core POC, M7 local data, M8 six-strategy workbench, M9 deterministic Run
reports, and the M10 local delivery vertical on top of that checkpoint. M2 pins
the official Pi `AgentSession` and connects real Pi sessions through the
Python-owned catalog, inbox, receipt state machine, bounded JSONL recall,
verified source references, and durable wake path. M3 adds Pi-bound
merge/Formal Run/Promote tools, immutable Git and
SQLite WorkspaceRevisions, isolated StrategyVariant heads, ordered two-parent
merge commits, an OQS cleanroom Rust/PyO3 engine, immutable RunSpec/Run and
content-addressed formal artifacts, validation-gated compare-and-set Promote,
and explicit stale conflicts.

M5 adds batch checkpoints and restart, cancel/retry/legal rerun, the full log
lifecycle, local Forward Test replay, deterministic project export/import, and
their Python, control-plane, and SPA surfaces. M6 combines those capabilities
with two real Pi sessions, independent variants, PyO3 Runs, Run Detail, Promote,
and a real-browser local vertical. M7 adds browser and configured-local CSV or
Parquet preview, field mapping and row errors, immutable A-share/crypto
DataSnapshots, direct snapshot-backed Formal Runs, included sample data, and
archive round-trip. M8 adds the six-strategy catalog, authoritative `.py`
editing, deterministic `.ipynb` finalization/download, a shared-cash
multi-symbol A-share portfolio engine, and real engine runs for all six
strategies. M9 adds independently reconciled Run metrics, shared report
contracts, Run Detail report rendering, deterministic JSON/HTML artifacts, and
archive preservation. M10 adds a one-command Docker Compose runtime, a real
six-strategy browser journey, the 250,000-bar performance gate, lock/license/
configuration checks, and Ubuntu/macOS GitHub Actions. The complete local
`pnpm validate:m10` gate passes; remote CI, PR, and merge evidence remain
separate delivery steps. All donor repositories remain read-only and no donor
source was copied. The M0 oracle is not a formal Run. Read [the M0 evidence](docs/09_M0_FOUNDATION_EVIDENCE.md), [the
M1 evidence](docs/10_M1_DURABLE_CORE_EVIDENCE.md), [the M2
evidence](docs/11_M2_SESSION_FABRIC_EVIDENCE.md), [the M3
evidence](docs/12_M3_REVISION_SLICE_EVIDENCE.md), and [the M4
evidence](docs/13_M4_UNIFIED_WORKBENCH_EVIDENCE.md), [the M5
evidence](docs/14_M5_RECOVERY_LIFECYCLE_EVIDENCE.md), [the M6
evidence](docs/15_M6_CORE_POC_EVIDENCE.md), and [the M7
evidence](docs/16_M7_LOCAL_DATA_SNAPSHOT_EVIDENCE.md), [the M8
evidence](docs/17_M8_STRATEGY_WORKBENCH_EVIDENCE.md), [the M9
evidence](docs/18_M9_RUN_REPORT_EVIDENCE.md), and [the M10
evidence](docs/19_M10_DELIVERY_EVIDENCE.md).

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
4. Run `pnpm validate:m10` for the complete local functional gate.
5. Run `docker compose up --build`, then open `http://127.0.0.1:4173`. The
   Compose runtime starts the SPA, Pi/control plane, Python domain and worker,
   and the PyO3 engine. Host files under `var/compose-imports/` are available to
   the Data workbench and project archives are written to
   `var/compose-exports/`.
6. Run `docker compose down` to stop the stack while preserving the named data
   volume.
7. Use [HANDOFF_PROMPT.md](prompts/HANDOFF_PROMPT.md) when transferring the work to another session.

## License

Open Quant Studio is licensed under the [MIT License](LICENSE). Third-party notices and exact dependency/source boundaries live under [`third_party/`](third_party/). The project license does not grant permission to copy donor code whose own rights or provenance are unresolved.
