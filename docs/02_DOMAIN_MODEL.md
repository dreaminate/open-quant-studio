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
| Experiment | Research hypothesis and run family | Versioned |
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

Every write command names `project_id`, `activity_id`, `session_id`, `workbench_id`, `variant_id`, and `base_revision_id`. Concurrent work creates child revisions. Promotion uses compare-and-set against the expected head; conflicts require compare, merge, or an explicit different promotion.
