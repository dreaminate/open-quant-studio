# services/quant-domain

M1 implements the sole durable business writer as a Starlette application over
SQLite WAL. The `context.capture` command writes project/activity bootstrap
state, immutable artifact metadata, raw context evidence, an immutable domain
event, outbox row, idempotency receipt, pending verification job, and structured
log in one `BEGIN IMMEDIATE` transaction.

Public M1 seams:

- `PUT /v1/artifact-blobs/{sha256}` stages verified bytes in the local
  content-addressed store; staging does not register an official Artifact.
- `POST /v1/commands` accepts the versioned `context.capture` command. Exact
  duplicates replay the original event; divergent reuse returns a conflict.
- `GET /v1/events?project_id=...` emits finite `text/event-stream` batches and
  resumes strictly after the decimal `Last-Event-ID` cursor.
- `POST /v1/jobs/run-next` claims one durable pending job with a typed started
  event/outbox row, then records a compare-and-set success/failure event plus a
  structured log.
- `GET /v1/jobs/{job_id}` and `GET /v1/logs` expose job state and filtered logs.

Run locally with `OQS_DATA_ROOT=var PYTHONPATH=services/quant-domain/src uv run
--project services/quant-domain --frozen uvicorn quant_domain.app:app`. M1 does
not add retries, checkpoints, restart recovery, retention/deletion, import/export,
Pi wake-ups, an outbox dispatcher, or formal Runs; those remain later milestones.
