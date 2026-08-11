# Donor migration map

Evidence refreshed again: 2026-08-11, Asia/Shanghai. Local donors and named
remotes were inspected read-only immediately before M0 implementation. No donor
file was copied.

## Live donor state

| Donor | Local evidence | Migration rule |
|---|---|---|
| QuantBT | `/Users/wzy/Work/01_Projects/My-Projects/Original/QuantBT`; clean commit object `e13b322ea00e6dc80cfe003ba44d126df8676230`; origin and remote `main` match that SHA; live worktree has 52 modified tracked paths and 20 untracked entries; no root/subtree license for the candidate UI | Unsafe to copy. Git-object addressing can isolate the committed tree from WIP, but no file may migrate until rights, attribution, paths, and an oracle are approved. |
| quant-assistant | `/Users/wzy/Work/01_Projects/My-Projects/Derived/quant-assistant`; branch `codex/quant-memory-mcp`; commit object `985f4502485f1b2978d72dca89e769a3a61525b8`; 77 modified, 35 deleted, and 102 untracked paths; no upstream; origin is `TencentCloud/TencentDB-Agent-Memory.git` | Unsafe to copy. The commit contains a Rust/PyO3 engine and crate metadata says MIT, but no root/Rust license or reliable product lineage proves per-file reuse rights. |
| VibeTrading | `/Users/wzy/Work/01_Projects/Open-Source/G-Finance-Quant-and-Company-Research/Vibe-Trading`; MIT; clean local `main` at `bec189f2eea3926262d6b692da9acdf1a19a6eeb`; remote `main` advanced to `1bf1d8b4c9b212ee73d5d1e46a00c498738d2cfd` | Local SHA is reproducible but not current remote tip. Use selected streaming/status behavior only as a named design/test oracle; M0 imports no source. Reject its AgentLoop, swarm, scheduler, broker, and backtest surfaces. |
| Pi | MIT upstream `earendil-works/pi`; final M0 remote refresh found `main` at `2a95ef70db83a19cf5500f31dc4ff8247e04043e`; reviewed SHA `24047f5dfb222ef7d26b554a0e576e5efa844024` still exists; that reviewed package reports version `0.84.1` and Node `>=22.19.0` | Do not install in M0. Pin a reviewed SHA, not mutable `main` or the version label, and verify runtime imports behind `pi-adapter` in M2. Pi remains the only permitted AgentLoop. |

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

## M0 cleanroom decision

M0 imports no donor or Pi source and vendors no prior-art implementation. The
only installed third-party code is declared package-manager dependencies for
TypeScript compilation and JSON Schema validation. Exact donor decisions and
dependency licenses are recorded in `third_party/M0_IMPORT_DECISIONS.md`.

## M1 cleanroom decision

M1 imports no donor or Pi source. SQLite behavior was implemented against the
Python standard library and upstream SQLite transaction/WAL semantics; HTTP/SSE
uses declared registry packages rather than copied framework source. Exact new
direct/transitive dependency versions and licenses are recorded in
`third_party/M1_DEPENDENCY_DECISIONS.md`.
