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
  "payload": {}
}
```

`command_id` is the idempotency key. The service persists state, an immutable domain event, and an outbox record in one transaction.

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
  "payload": {}
}
```

SSE preserves monotonic `stream_seq` within its product stream. Consumers resume from the last acknowledged sequence and must handle redelivery idempotently.

## Artifacts

Commands and events refer to large values by `artifact_id`, content hash, media type, byte size, and producing revision/Run. Raw market data, model files, full logs, equity series, trade ledgers, and reports do not travel in command or SSE envelopes.

## Formal RunSpec

A Formal Run freezes at least data snapshot, universe, sample window, timezone, strategy revision, parameters, random seed, fee/slippage model, engine version, environment lock identity, and output schema version. A started Run is never edited; another attempt receives another `run_id`.
