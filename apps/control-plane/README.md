# apps/control-plane

M1 provides `FetchDomainEventStreamClient`, a typed reader for the Python event
ledger's SSE response. It sends the application's last acknowledged
`stream_seq` as `Last-Event-ID`, validates each shared event envelope, applies
events in order, and advances the returned cursor only after the callback
resolves. A failed callback leaves the caller's prior cursor available for
deliberate redelivery.

M2 adds a pinned `@earendil-works/pi-coding-agent` 0.84.1 adapter. Every adapter
creates exactly one official `AgentSession` with a controlled
`SessionManager.create(cwd, sessionDir, { id })`; the domain session id and Pi
session id remain separate. `StaticResourceLoader` supplies only the versioned
OQS system prompt, with no ambient extensions, skills, prompts, themes,
`AGENTS.md`, context files, or built-in read/bash/edit/write tools.

`SessionRegistry` is an in-memory active router. It binds one adapter to the
canvas, code, and Run Detail workbenches and rejects project/activity/Pi-id
remapping. `PiJsonlRecall` reads registered sessions through the official Pi
session manager, bounds search/context windows, hashes canonical entries, and
renders recalled text as data rather than instructions. Follow-up and urgent
steer messages carry a caller-supplied `[oqs-message:<UUID>]` marker and the
same UUID in Pi custom-message details for redelivery dedupe.

`FetchQuantDomainSessionClient` is the typed boundary to the Python-owned
catalog, CAS, inbox, and receipt transitions. `SessionFabric` exposes the nine
bounded OQS tools, stages canonical Pi entry witnesses for source references,
delivers offline messages through `followUp`, and advances durable receipt
state only after the structured marker is present in Pi JSONL. Its event reader
can hold one bounded `wait=1` request open so a queued event wakes an active
session without model polling.

The real M2 integration test starts Uvicorn, creates two official Pi sessions
with the official faux provider, runs a Pi-owned `session_search ->
session_reply` turn with anchored provenance, switches one durable session
across canvas/code/Run Detail, and proves redelivery dedupe and event wake-up.
Restart recovery, terminal cancellation/expiry, authentication, task handoff,
and exact remaining-context-budget accounting remain later work.

The partial M3 revision slice adds `FetchQuantDomainRevisionClient` and five
actor-bound Pi tools for root revision creation, variant fork, child revision
creation, metadata compare, and CAS Promote. File bytes are validated locally,
staged through the existing Python CAS seam, and represented by the same
canonical text Artifact identity used by M2 messages. All durable mutations
still pass through the typed Python command endpoint; read responses are
identity-checked and body-free. The M3 tests include an official faux Pi tool
call and a real Uvicorn regression. No second AgentLoop, formal backtest engine,
or formal Run path is introduced here.
