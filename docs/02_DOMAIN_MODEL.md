# Domain model

## Core identities

| Entity | Meaning | Mutability |
|---|---|---|
| ResearchProject | Context, authorization, lineage, and tool boundary | Versioned metadata |
| AgentSession | One Pi conversation tree and its provenance | Append/branch through Pi |
| Activity | One user objective spanning workbenches and sessions | State machine |
| Task | Durable unit of work with dependencies and a claim | State machine |
| WorkbenchBinding | Session-to-workbench projection within an Activity | Replaceable projection |
| StrategyVariant | Independent strategy exploration lineage | Append-only lineage |
| WorkspaceRevision | Immutable code/config snapshot | Immutable |
| DataSnapshot | Immutable validated market-data identity and metadata | Immutable |
| Experiment | Research hypothesis and run family | Versioned |
| RunSpec | Frozen strategy/data/parameters/cost/environment request | Immutable |
| Run | One execution of a frozen RunSpec | Immutable |
| Artifact | Content-addressed data, code package, model, report, or output | Immutable |
| ProjectContextItem | Shared evidence or conclusion with provenance and trust state | Superseded, never overwritten |

## Context trust states

- `raw_evidence`: immutable source messages, tool results, code, and artifacts.
- `candidate`: agent-proposed conclusion with source references and validation state.
- `canonical`: passed an applicable test/research gate or received explicit approval.
- `superseded`: preserved historical item replaced by a newer item.

Canonical items are retrieved by default. Candidate items are retrieved only when relevant or explicitly selected. Full transcripts are never automatically injected into every session.

## Task coordination

- A Task is completed by evidence such as a revision, artifact, Run, or validation record, not by an agent saying "done".
- A session claims a Task for a bounded lease and may hand it off with exact context and revision references.
- Expired claims return to a claimable state.
- A deterministic coordinator enforces transitions. It does not ask an LLM to decide routine scheduling state.

## Concurrent changes

Every write command carries `project_id`, `activity_id`, `session_id`,
`workbench_id`, `variant_id`, and `base_revision_id`. Project-scoped commands
that precede the M3 revision/variant subsystem, such as M1 `context.capture`,
set the last two fields explicitly to null. Commands that mutate variant-backed
research must name both identities. Concurrent work creates child revisions.
Promotion uses compare-and-set against the expected head; conflicts require
compare, merge, or an explicit different promotion.

## Formal research model

- A strategy emits structured `OrderIntent` values with direction, quantity, order type, `known_at`, `effective_at`, and optional limit/stop price. It never supplies a fill price or accounting result.
- The Rust engine is authoritative for fills, signed positions, cash, fees, funding, equity, drawdown, and metrics. Python durably records one immutable engine result and the SPA reads that same artifact.
- A-share daily runs use 100-share lots, T+1 sell eligibility, snapshot-provided tradable/suspension/price-limit flags, long positions, and an explicitly labelled hypothetical `research_short` mode.
- Crypto runs use T+0 linear-perpetual research semantics at 1x notional with long/short, maker/taker fees, fixed slippage, and optional constant funding. They do not model leverage, margin, liquidation, ADL, or an order book.
- Re-running creates a new `run_id`. Concurrent strategy work creates child revisions or variants; no Run or revision is overwritten.
