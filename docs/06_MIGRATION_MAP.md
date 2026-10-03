# Donor migration map

Evidence refreshed: 2026-08-14, Asia/Shanghai. This refresh inspected the
four local donor worktrees named below with `git -C <path> branch --show-current`,
`rev-parse HEAD`, `remote -v`, `status --short --branch`, and the root
`LICENSE`. No network fetch was performed: each `origin/<branch>` relationship
below is the local checkout's tracking metadata, not a claim about the current
remote tip.

## Locked product boundary

Open Quant Studio (OQS) is the sole product, runtime, and UI: one OQS React/Vite
SPA, the OQS TypeScript control plane and Pi adapter, the OQS Python domain/job
service, and the OQS Rust/PyO3 formal engine. A donor may provide an engineering
reference, an offline differential oracle, or a later reviewed source slice; it
may never supply a running application, service, database, UI, AgentLoop,
backtest authority, or order-submission path in OQS.

The donor worktrees remain read-only during this refresh. No donor code was
copied. A source slice is only a candidate until its provenance and acceptance
record below is complete.

## Current migration status

No Qlib, vn.py, LEAN, or QuantDinger file is currently recorded as migrated
into OQS. The current product-source and `third_party/` attribution searches
contain no such migrated-file record, and all-ref literal-history searches for
these donor names returned no product-source migration. This is provenance
evidence, not a similarity audit. Existing LEAN references are behavior-oracle
records only; they are not a source migration.

## Live local donor snapshots

### Qlib

- Local path: `/Users/wzy/Work/01_Projects/Open-Source/G-Finance-Quant-and-Company-Research/qlib`
- Origin: `https://github.com/microsoft/qlib`
- Local Git identity: clean `main` at
  `79633dd9506ea689e5400dea0197717b5b3d74b7`, locally tracking `origin/main`.
- License: root `LICENSE`, MIT.
- Candidate slice: `qlib/backtest/exchange.py` (`Exchange`, tradability,
  suspension, limit, volume clipping, 100-share `trade_unit`, minimum cost,
  open/close cost) and its focused tests.
- Differential-oracle value: fixed A-share-like cases for suspension, price
  limits, 100-share rounding, participation/volume clipping, and minimum
  commission. OQS must retain its own distinction between a real missing-data
  gap and suspension; Qlib's missing close-as-suspension behavior cannot define
  that OQS contract. Qlib also does not establish OQS's dual books, T+1 lots,
  corporate actions, or immutable Run provenance.

### vn.py

- Local path: `/Users/wzy/Work/01_Projects/Open-Source/G-Finance-Quant-and-Company-Research/vnpy`
- Origin: `https://github.com/vnpy/vnpy`
- Local Git identity: clean `master` at
  `fa5206fe63836f3f8cd1ebd7168fbd19a5e2ff09`, locally tracking `origin/master`.
- License: root `LICENSE`, MIT.
- Candidate slice: `vnpy/alpha/strategy/template.py` (explicit buy, sell,
  short, cover intents) and `vnpy/alpha/strategy/backtesting.py` (match
  outstanding orders before `on_bars`, limit-up/down guards, favourable-gap
  limit fill, orders/trades/daily PnL).
- Differential-oracle value: a small pending-order timing and limit-fill suite.
  The local implementation fills missing bars with the previous close, assumes
  whole fills, and hard-codes a 10% limit rule; those are incompatibilities to
  test against rather than behavior OQS may inherit. It does not establish
  OQS's versioned A-share rules, shared participation cap, T+1 lots, or
  `cash_long`/`research_short` accounting.

### LEAN

- Local path: `/Users/wzy/Work/01_Projects/Open-Source/G-Finance-Quant-and-Company-Research/Lean`
- Origin: `https://github.com/QuantConnect/Lean`
- Local Git identity: clean `master` at
  `d2c3659f877bfc2b5d9dc0fc89a9c7566f45e892`, locally tracking `origin/master`.
- License: root `LICENSE`, Apache-2.0.
- Candidate slice: `Common/Orders/Fills/EquityFillModel.cs` for market/limit
  timing and favourable-gap price behavior; `Common/Data/Auxiliary/CorporateFactorRow.cs`
  and `Common/Data/Market/{Dividend,Split,Delisting}.cs` for corporate-action
  event representation.
- Differential-oracle value: favourable market/limit gap, stale-data wait,
  cash-dividend, split, and delisting ledger vectors. LEAN's equity model is
  not an A-share rules engine and explicitly leaves volume-limited partial
  fills as future work; it cannot override OQS's T+1, price-limit, lot,
  participation, or two-book requirements. The existing M3 LEAN oracle pin in
  `third_party/M3_DEPENDENCY_DECISIONS.md` is historical evidence and is not
  silently changed to this newer local snapshot.

### QuantDinger

- Local path: `/Users/wzy/Work/01_Projects/Open-Source/G-Finance-Quant-and-Company-Research/QuantDinger`
- Origin: `https://github.com/OpenByteInc/QuantDinger`
- Local Git identity: clean `main` at
  `e64e1c227bf3174e441a42143620179b286387e1`, locally tracking `origin/main`.
- License: root `LICENSE`, Apache-2.0.
- Candidate slice: `backend_api_python/app/services/strategy_v2/{contract.py,runtime.py,service.py}`
  for typed `OrderIntent`, strategy-contract compilation, next-open scheduling,
  and an independent execution/fee/position reconciliation shape.
- Differential-oracle value: compile a typed strategy into explicit intent,
  prove that a fill never precedes its signal, and reconcile orders, fills,
  fees, positions, cash, and ending equity. The `live_execution.py` order
  gateway, its dispatcher/database, the Python V2 backtest runtime, and every
  QuantDinger UI are explicitly rejected: OQS is research-only and its Rust
  engine remains the sole formal authority.

## Admission record for any later source slice

No candidate above is pre-approved for copying. Before a later source slice is
accepted, create the smallest applicable record under `third_party/` that names:

- donor name, canonical origin URL, exact commit, branch, local snapshot date,
  and clean/dirty status;
- root and file-level license/notice evidence, including required Apache-2.0
  change notices where applicable;
- every original source path, its SHA-256, its OQS destination path, and every
  OQS modification (with post-change hash);
- the allowed OQS boundary and the rejected donor runtime/UI/service/database
  surfaces;
- the semantic mapping and known intentional differences from the frozen OQS
  A-share contract; and
- the executable acceptance oracle, fixture IDs, commands, expected outputs,
  actual results, and reviewer decision.

The acceptance oracle must run the OQS Rust/PyO3 path with the same frozen
DataSnapshot and typed OrderIntents. Where a donor can be run safely offline,
compare mapped outputs at its recorded commit; otherwise use an independently
reviewed golden ledger derived from that donor's documented behavior. A passing
oracle must cover only the donated slice and must additionally prove that OQS
keeps next-bar information timing, unknown-data-gap failure, versioned A-share
rules, shared 10% liquidity, T+1 lots, separate `cash_long` and
`research_short` books, immutable Run provenance, and Run Detail reconciliation.
Any unexplained difference blocks migration. No donor application, backtest
service, UI, database, broker/exchange path, or AgentLoop may be executed as an
OQS runtime dependency.

## Earlier reference-only decisions retained

The following prior map content is retained as historical scope, not refreshed
live donor metadata for this A-share slice:

| Source | Retained decision |
|---|---|
| QuantBT | Named workbench/canvas/Run Detail behavior can be an oracle only. Its source, Claude AgentLoop, workflow executor, and backend remain excluded. |
| quant-assistant | Named domain/report behavior can be an oracle only. Its engine, legacy frontend, scheduler, and source migration remain excluded because earlier lineage/license evidence was unresolved. |
| VibeTrading | Session/chat/streaming/status presentation can be a design oracle only. Its ReAct runtime, swarm, scheduler, broker, and backtest surfaces remain excluded. |
| Pi | The exact approved Pi registry release remains behind the OQS TypeScript adapter as the only AgentLoop; it owns neither durable business state nor formal backtest calculation. |

## Open-source prior art boundary

- `pi-intercom` may be used as an MIT protocol/test oracle for send/ask/reply,
  correlation, receipt, cancel, and supersede behavior. Do not run its broker
  in the unified process.
- PSM and byteowlz session/history extensions had no verifiable root license in
  the reviewed snapshots. Use only public design ideas such as anchored bounded
  recall; copy no source.
- `pi-collaborating-agents` may be an MIT design/test oracle for threads,
  inbox, run registry, and reservations. Do not adopt its subagent spawner or
  second store.
- MCP Agent Mail has a restrictive rider excluding OpenAI/Anthropic and their
  representatives. Do not copy, run, test, or integrate it.
- Graphile Worker remains a future option only if the product's existing
  outbox/job design proves insufficient.

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
`third_party/M3_DEPENDENCY_DECISIONS.md`. The quant-assistant Rust/PyO3 engine
remains excluded: its reviewed local tree was dirty, its configured origin named
an unrelated TencentDB Agent Memory repository, and root/Rust license coverage
and engine lineage remained unresolved. The approved formal path is therefore
an OQS-owned cleanroom Rust/PyO3 implementation with separately reviewed
registry dependencies and oracle tests. No quant-assistant or QuantBT source
may enter that implementation. The current local M3 gate combines this engine
with the checkpointed revision slice, immutable formal artifacts, typed merge
validation, and gated CAS Promote; remote CI remains separate evidence.
