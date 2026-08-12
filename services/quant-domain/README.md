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

M2 adds the durable Session Fabric catalog and inbox. `session.register` writes
an OQS session to Pi identity mapping plus its initial workbench binding without
claiming active in-memory state or storing a transcript path.
`session.workbench_bind` replaces the durable active projection while retaining
the session's known workbench set. Message send/reply
commands register a pre-staged, bounded UTF-8 text Artifact and atomically write
an immutable message, queued event/outbox row, and idempotency receipt. Receipt
commands advance only `queued -> receiver_received -> injected -> acknowledged`
with expected state/version compare-and-set checks. `GET /v1/sessions`,
`GET /v1/inbox`, and identity-checked `GET /v1/messages/{message_id}` expose
catalog metadata, body-free inbox rows, and verified bounded UTF-8 body access.
Source references require a hash-addressed canonical Pi entry witness in the
local CAS. `GET /v1/events?wait=1` performs one bounded asynchronous wait for a
new event; the default remains a finite resumable batch.

The provenance-safe M3 revision slice adds `workspace.revision_create`,
`strategy.variant_create`, and `workspace.revision_promote`. Python remains the
sole durable writer: it registers bounded CAS text artifacts, writes immutable
revision/file/variant/event/outbox/receipt rows in SQLite, and creates the
matching Git blobs, trees, and zero/one-parent commits in a project-local bare
repository. Accepted commits receive immutable per-revision refs and survive
Git garbage collection. Variant and project heads are explicit mutable
projections guarded by compare-and-set; an immutable head history prevents ABA
by requiring a revert to use a new revision identity. Each project is bounded
to 64 variants so the durable writer and bounded control-plane catalog agree. `GET
/v1/revisions/{revision_id}`, `GET /v1/variants`,
`GET /v1/revisions/compare`, and `GET /v1/projects/{project_id}/revision-head`
return identity and hash metadata without source bodies.

M3/M4 add merge validation, immutable Formal Runs and artifacts, project-scoped
read models, and a continuous `python -m quant_domain.worker` process. A global
database gate permits only one running Formal Run, and attempt-bound completion
prevents a reclaimed job from accepting a stale current-worker completion.

Run the complete M4 local composition with `pnpm start:m4`. To operate the
Python processes separately, point both Uvicorn and the worker at the same
absolute `OQS_DATA_ROOT`; the repository launcher is the executable reference.
Checkpoint/resume, cancel/retry, retention/deletion, import/export, and durable
outbox dispatch remain later milestone work.
