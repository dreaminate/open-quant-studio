# contracts

M1 extends the v1 command/event envelopes with explicit nullable revision and
variant provenance, then adds concrete JSON Schema 2020-12 contracts for
immutable artifact references, `context.capture`, `context.captured`, artifact
verification outcomes, and structured diagnostic logs. Ajv and Python
jsonschema execute the same positive and negative fixtures in
`test/parity.test.mjs`.

The runtime validators additionally bind `storage_uri` to the Artifact SHA-256;
the shared fixtures prove TypeScript/Python agreement on that cross-field rule.
M1 source provenance is an opaque UUID, not free text or a credential-bearing
URL.

This package remains transport-only. Python owns persistence and emits the
validated envelope shape; TypeScript consumes it without becoming a second
durable writer.

M2 adds an explicit Session Fabric command/event registry. `session.register`
maps a durable OQS session identity to a bounded Pi identity and URI. Message
commands carry only a staged CAS Artifact reference, typed bounded Pi JSONL
source references, and receipt state/version fields; message events never carry
body bytes. `validateTypedCommandEnvelope` and
`validateTypedEventEnvelope` reject command/event types not owned by the
current milestone, while the original envelope validators remain generic
transport checks for forward-compatible fixtures.

`session.workbench_bind`/`session.workbench_bound` replace the active durable
WorkbenchBinding projection without creating another session. The M2 receipt
schema deliberately owns the delivery spine only: `queued`,
`receiver_received`, `injected`, and `acknowledged`. Cancellation,
supersession, expiry, retry, and recovery remain the M5 lifecycle slice named in
the implementation plan.

M3 adds strict `workspace.revision_create`, `strategy.variant_create`, and
`workspace.revision_promote` commands plus their corresponding revision and
variant events. Revision creation accepts only bounded `text/plain` CAS
artifacts, relative POSIX file paths, and unique paths; child creation and
promotion bind their compare-and-set identities explicitly. Revision-created
events distinguish root lineage from child `variant_id`/`base_revision_id`
lineage, while promotion events bind the previous head and candidate metadata.
The generic envelope validators still accept well-formed unknown types for
forward compatibility; typed dispatch only accepts the registered M1/M2/M3
contracts.

This package defines transport contracts only. Runtime Git/SQLite evidence is
recorded separately by the Python and control-plane integration tests. Passing
these validators alone is not evidence of runtime persistence, formal backtest
engine integration, immutable formal `Run` records, or complete M3/POC
acceptance.
