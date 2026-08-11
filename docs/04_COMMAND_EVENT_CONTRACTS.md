# Command and event contracts

## Command envelope

Every durable mutation is submitted to the Python service with:

```json
{
  "command_id": "uuid",
  "schema_version": 1,
  "command_type": "namespace.action",
  "project_id": "uuid",
  "activity_id": "uuid",
  "session_id": "string",
  "workbench_id": "string",
  "correlation_id": "uuid",
  "expected_revision_id": "uuid-or-null",
  "variant_id": "uuid-or-null",
  "base_revision_id": "uuid-or-null",
  "payload": {}
}
```

`command_id` is the idempotency key. The service persists state, an immutable domain event, and an outbox record in one transaction.

M1 implements one concrete mutation, `context.capture`. Its payload contains a
`context_item_id`, title, the fixed `raw_evidence` trust state, and one complete
immutable Artifact reference. The service hashes the canonical full envelope.
Because M3 does not yet own revisions, variants, or formal Runs, M1 requires
`expected_revision_id`, `variant_id`, `base_revision_id`,
`producing_revision_id`, and `producing_run_id` to be explicitly null for this
command and its event.
An exact duplicate returns the original stored event with disposition
`replayed`; the same `command_id` with any changed envelope field returns
`command_id_conflict` and writes nothing.

## Event envelope

```json
{
  "event_id": "uuid",
  "stream_seq": 1,
  "schema_version": 1,
  "event_type": "namespace.past_tense",
  "project_id": "uuid",
  "activity_id": "uuid",
  "session_id": "string-or-null",
  "workbench_id": "string-or-null",
  "correlation_id": "uuid",
  "causation_id": "command-or-event-id",
  "recorded_at": "RFC3339 timestamp",
  "variant_id": "uuid-or-null",
  "base_revision_id": "uuid-or-null",
  "payload": {}
}
```

SSE preserves monotonic `stream_seq` within its product stream. Consumers resume from the last acknowledged sequence and must handle redelivery idempotently.

M1 serves `GET /v1/events?project_id=...` as `text/event-stream`. Each frame has
decimal `stream_seq` as `id`, `domain.event` as `event`, and one JSON event
envelope as `data`. The only resume authority is the `Last-Event-ID` header:
absent means zero, a non-negative decimal returns rows strictly after that
sequence, and malformed values return HTTP 400. The UUID `event_id` remains the
event-application idempotency identity and is not the SSE cursor.

## Artifacts

Commands and events refer to large values by `artifact_id`, lowercase SHA-256,
media type, byte size, `cas://sha256/...` storage URI, provenance, and nullable
producing revision/Run. A blob PUT only stages hash-verified bytes; the typed
command is the authority that registers Artifact metadata. Raw market data,
model files, full logs, equity series, trade ledgers, and reports do not travel
in command or SSE envelopes.

`storage_uri` must equal `cas://sha256/{sha256}` in both runtime validators; a
schema-shaped mismatch is invalid. M1 provenance uses an opaque UUID
`source_ref`, never a user-supplied URL, header, path, or free-text credential.
The referenced source catalog arrives in a later milestone.

The M1 Job Runner emits `artifact.verification_started` in the same transaction
that claims a pending job, then verifies registered artifact bytes and emits
either `artifact.verification_succeeded` with the observed hash/size or
`artifact.verification_failed` with a bounded error code. All three payload
shapes are shared TypeScript/Python contracts. Each event receives a matching
outbox row; M1 does not yet implement an outbox dispatcher.

## Formal RunSpec

A Formal Run freezes at least data snapshot, universe, sample window, timezone, strategy revision, parameters, random seed, fee/slippage model, engine version, environment lock identity, and output schema version. A started Run is never edited; another attempt receives another `run_id`.
