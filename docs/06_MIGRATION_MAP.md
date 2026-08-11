# Donor migration map

Evidence refreshed: 2026-08-11, Asia/Shanghai. Donor repositories were inspected read-only.

## Live donor state

| Donor | Local evidence | Migration rule |
|---|---|---|
| QuantBT | `/Users/wzy/Work/01_Projects/My-Projects/Original/QuantBT`; origin `dreaminate/QuantBT`; HEAD `e13b322ea00e6dc80cfe003ba44d126df8676230`; worktree has many modified and untracked files | Do not assume HEAD contains the desired current UI. Establish and approve a clean source snapshot before copying any slice. |
| quant-assistant | `/Users/wzy/Work/01_Projects/My-Projects/Derived/quant-assistant`; HEAD `985f4502485f1b2978d72dca89e769a3a61525b8`; branch `codex/quant-memory-mcp`; worktree has many modified, deleted, and untracked files; current origin points to `TencentCloud/TencentDB-Agent-Memory.git` | Treat the local checkout, not its remote, as the candidate source. Resolve exact snapshot and ownership before migration. Never copy its dirty state implicitly. |
| VibeTrading | `/Users/wzy/Work/01_Projects/Open-Source/G-Finance-Quant-and-Company-Research/Vibe-Trading`; origin `HKUDS/Vibe-Trading`; clean main at `bec189f2eea3926262d6b692da9acdf1a19a6eeb` | Inspect license and migrate bounded interaction patterns only. Do not retain its AgentLoop, swarm, scheduler, or backtest authority. |
| Pi | Primary upstream `earendil-works/pi`; reviewed research snapshot `24047f5dfb222ef7d26b554a0e576e5efa844024` | Pin a reviewed package/SHA and wrap it behind `pi-adapter`. It is the only direct AgentLoop dependency. Refresh upstream state before implementation. |

## Capability ownership

| Source | Keep | Remove or reject |
|---|---|---|
| VibeTrading | session/chat/streaming interaction, status presentation, logging controls | ReAct runtime, swarm, in-memory scheduler, strategy/backtest authority |
| QuantBT | unified workbench, infinite canvas, Run Detail, comparison, gates, research governance | Claude AgentLoop, duplicate workflow executor, duplicate backend |
| quant-assistant | quant domain behavior, Rust/PyO3 formal backtest, reproducible report artifacts | legacy frontend entrypoint and duplicate scheduling surface |
| Pi | session, branch, compaction, tool loop, model/provider adapter | business persistence, backtest calculation, task authority |

## Open-source prior art boundary

- `pi-intercom` may be used as an MIT protocol/test oracle for send/ask/reply, correlation, receipt, cancel, and supersede behavior. Do not run its broker in the unified process.
- PSM and byteowlz session/history extensions had no verifiable root license in the reviewed snapshots. Use only public design ideas such as anchored bounded recall; copy no source.
- `pi-collaborating-agents` may be an MIT design/test oracle for threads, inbox, run registry, and reservations. Do not adopt its subagent spawner or second store.
- MCP Agent Mail has a restrictive rider excluding OpenAI/Anthropic and their representatives. Do not copy, run, test, or integrate it.
- Graphile Worker remains a future option only if the product's existing outbox/job design proves insufficient.

Every migrated file requires a provenance record under `third_party/` before it lands.
