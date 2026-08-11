# Open Quant Studio

Open Quant Studio is a local-first, agent-native quantitative research studio. It is intended to fuse the useful product capabilities of VibeTrading, QuantBT, and quant-assistant around one Pi AgentLoop without retaining three competing runtimes.

Repository: https://github.com/dreaminate/open-quant-studio

## Current state

This repository is an architecture and development bootstrap. The product application, runtime integration, backtest integration, and POC are **not implemented yet**.

The first development session must begin at milestone M0 in [the implementation plan](docs/08_IMPLEMENTATION_PLAN.md). Do not interpret the presence of directories or documents as a working application.

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
docs/                      frozen architecture and POC gates
prompts/                   fresh-session development and handoff prompts
third_party/               provenance and attribution policy
```

## Start here

1. Read [AGENTS.md](AGENTS.md).
2. Read [the project charter](docs/00_PROJECT_CHARTER.md) through [the implementation plan](docs/08_IMPLEMENTATION_PLAN.md).
3. Paste [START_DEVELOPMENT_PROMPT.md](prompts/START_DEVELOPMENT_PROMPT.md) into the new development session.
4. Use [HANDOFF_PROMPT.md](prompts/HANDOFF_PROMPT.md) when transferring the work to another session.

## License status

No project license has been selected. Public visibility does not grant permission to reuse this repository's code. Do not import donor code until its exact license, commit, attribution, and modification boundary have been recorded.
