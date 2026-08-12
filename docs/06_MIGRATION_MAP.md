# Donor migration map

Evidence refreshed: 2026-08-12, Asia/Shanghai. Local donors and named remotes
were inspected read-only for the M0-M10 Goal. No donor file was copied.

## Live donor state

| Donor | Local evidence | Migration rule |
|---|---|---|
| QuantBT | `/Users/wzy/Work/01_Projects/My-Projects/Original/QuantBT`; clean commit object `e13b322ea00e6dc80cfe003ba44d126df8676230`; origin and remote `main` match that SHA; live worktree has 52 modified tracked paths and 20 untracked entries; no root/subtree license for the candidate UI | Unsafe to copy. Git-object addressing can isolate the committed tree from WIP, but no file may migrate until rights, attribution, paths, and an oracle are approved. |
| quant-assistant | `/Users/wzy/Work/01_Projects/My-Projects/Derived/quant-assistant`; branch `codex/quant-memory-mcp`; commit object `985f4502485f1b2978d72dca89e769a3a61525b8`; 77 modified, 35 deleted, and 37 untracked status entries; no upstream; origin is `TencentCloud/TencentDB-Agent-Memory.git`, whose default branch is `feat/server_team` at `4dca55c41bf11cb19b49728dbe495c8e05d25abb` and `main` is `98d687819e9feef2c6137a8f6be18551810f6ce7` | Unsafe to copy. The local commit contains Rust/PyO3 files, but no root/Rust license or reliable product lineage proves per-file reuse rights; its configured origin is a different product. |
| VibeTrading | `/Users/wzy/Work/01_Projects/Open-Source/G-Finance-Quant-and-Company-Research/Vibe-Trading`; MIT; clean local `main` at `bec189f2eea3926262d6b692da9acdf1a19a6eeb`; remote `main` advanced to `1bf1d8b4c9b212ee73d5d1e46a00c498738d2cfd` | Local SHA is reproducible but not current remote tip. Use selected streaming/status behavior only as a named design/test oracle; M0 imports no source. Reject its AgentLoop, swarm, scheduler, broker, and backtest surfaces. |
| Pi | MIT upstream `earendil-works/pi`; exact release `v0.84.1` tag remains `53fa77ccd8a279eb87e92294ef3687b03ff80112`; installed registry metadata reports `0.84.1`, MIT, Node `>=22.19.0`; mutable `main` is now `2a9b4ebc680053c64e31f635b0b22d5e22564001`; lock integrity is recorded in `third_party/M2_DEPENDENCY_DECISIONS.md` | M2 uses exact registry version `0.84.1` plus the frozen lock, never mutable `main`. Pi stays behind the OQS adapter as the only permitted AgentLoop; built-in filesystem/shell tools and ambient resources remain disabled. |

## Capability ownership

| Source | Keep | Remove or reject |
|---|---|---|
| VibeTrading | session/chat/streaming interaction, status presentation, logging controls | ReAct runtime, swarm, in-memory scheduler, strategy/backtest authority |
| QuantBT | named workbench/canvas/Run Detail behavior as an oracle only | all source copying, Claude AgentLoop, duplicate workflow executor, duplicate backend |
| quant-assistant | named quant-domain/report behavior as an oracle only | all source copying, engine migration, legacy frontend, duplicate scheduler |
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

## M2 cleanroom decision

M2 imports no donor or Session Fabric prior-art source. It consumes Pi's exact
MIT-licensed `v0.84.1` registry release and implements OQS-specific typed tools,
HTTP routing, durable inbox delivery, and bounded recall as cleanroom product
code. Exact integrities, the retained upstream license, transitive license
groups, native/optional dependency caveats, and the point-in-time upstream
identity are recorded in `third_party/M2_DEPENDENCY_DECISIONS.md`.

## M3 cleanroom decision

The revision/variant/CAS slice is OQS-owned cleanroom code implemented against
the frozen command/domain rules, Python's standard library, SQLite, and the
locally available `/usr/bin/git` plumbing interface. It copies no donor source
and adds no package dependency. The formal engine is a separate OQS-owned
cleanroom Rust/PyO3 package whose exact dependencies, licenses, locks, external
rules sources, and no-copy behavior oracles are recorded in
`third_party/M3_DEPENDENCY_DECISIONS.md`. The quant-assistant Rust/PyO3 engine remains
excluded: its current local tree is dirty, its configured origin names an
unrelated TencentDB Agent Memory repository, and root/Rust license coverage and
engine lineage remain unresolved. The approved formal path is therefore an
OQS-owned cleanroom Rust/PyO3 implementation with separately reviewed registry
dependencies and oracle tests. No quant-assistant or QuantBT source may enter
that implementation. The current local M3 gate combines this engine with the
checkpointed revision slice, immutable formal artifacts, typed merge
validation, and gated CAS Promote; remote CI remains separate evidence.
