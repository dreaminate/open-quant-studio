# Open Quant Studio

Open Quant Studio is a local-first, agent-native quantitative research studio. It is intended to fuse the useful product capabilities of VibeTrading, QuantBT, and quant-assistant around one Pi AgentLoop without retaining three competing runtimes.

Repository: https://github.com/dreaminate/open-quant-studio

## Current state

The local checkout contains the M0 foundation, M1 durable-domain slice, M2 Pi
Session Fabric, and a provenance-safe partial M3 revision slice. M2 pins the
official Pi `AgentSession`, keeps built-in filesystem and shell tools disabled,
and connects real Pi sessions through the Python-owned catalog, inbox, receipt
state machine, bounded JSONL recall, verified source references, and durable
wake path. The partial M3 slice adds Pi-bound revision tools, immutable Git and
SQLite WorkspaceRevisions, isolated StrategyVariant heads, metadata compare,
and compare-and-set Promote with explicit stale conflicts.

M3 is **not complete**. Rust/PyO3 formal engine integration, immutable
RunSpec/Run records, formal gates, merge, the unified SPA, restart recovery,
full log lifecycle, and the complete POC remain not implemented. The
quant-assistant engine donor is still blocked by unresolved root/Rust license
coverage and product lineage; no donor source was copied. The M0 oracle is not
a formal Run. Read [the M0 evidence](docs/09_M0_FOUNDATION_EVIDENCE.md), [the
M1 evidence](docs/10_M1_DURABLE_CORE_EVIDENCE.md), [the M2
evidence](docs/11_M2_SESSION_FABRIC_EVIDENCE.md), and [the partial M3 revision
evidence](docs/12_M3_REVISION_SLICE_EVIDENCE.md).

## Non-negotiable product boundaries

- Research only. No broker or exchange order submission.
- All supported assets use real long/short research semantics; formal simulations use structured orders, signed positions, covering, and configurable costs.
- Pi is the sole AgentLoop and model/provider entrypoint.
- quant-assistant's Rust/PyO3 engine is the intended formal backtest authority after a provenance-safe migration.
- QuantBT supplies the unified workbench, infinite canvas, Run Detail, comparison, and research gates.
- VibeTrading supplies interaction patterns such as session/chat/streaming and run-state presentation, not a second runtime.
- Python owns durable domain writes; TypeScript uses versioned HTTP commands and SSE events.
- Concurrent sessions create independent WorkspaceRevision/StrategyVariant histories. Last-write-wins is forbidden.
- Logs are structured, levelled, prioritised, and user-deletable.

## Repository map

```text
apps/web/                  React/Vite unified frontend
apps/control-plane/        Pi adapter and Session Fabric
services/quant-domain/     Python domain service and Job Runner
crates/quant-engine/       quant-assistant Rust/PyO3 backtest core
packages/contracts/        command, event, artifact, and tool contracts
packages/research-ui/      QuantBT-derived workbench components
fixtures/                  synthetic M0 market data and golden accounting oracle
docs/                      frozen architecture and POC gates
prompts/                   fresh-session development and handoff prompts
third_party/               provenance and attribution policy
```

## Start here

1. Read [AGENTS.md](AGENTS.md).
2. Read [the project charter](docs/00_PROJECT_CHARTER.md) through [the implementation plan](docs/08_IMPLEMENTATION_PLAN.md).
3. Run `pnpm install --frozen-lockfile` and `uv sync --project services/quant-domain --frozen`.
4. Run `pnpm validate:m3-revisions` before relying on the local partial-M3
   revision evidence.
5. Use [HANDOFF_PROMPT.md](prompts/HANDOFF_PROMPT.md) when transferring the work to another session.

## License status

No project license has been selected. Public visibility does not grant permission to reuse this repository's code. Do not import donor code until its exact license, commit, attribution, and modification boundary have been recorded.
