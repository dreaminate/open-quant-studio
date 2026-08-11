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
