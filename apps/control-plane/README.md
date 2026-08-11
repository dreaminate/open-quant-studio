# apps/control-plane

M1 provides `FetchDomainEventStreamClient`, a typed reader for the Python event
ledger's SSE response. It sends the application's last acknowledged
`stream_seq` as `Last-Event-ID`, validates each shared event envelope, applies
events in order, and advances the returned cursor only after the callback
resolves. A failed callback leaves the caller's prior cursor available for
deliberate redelivery.

The Pi adapter, active SessionRegistry, Session Fabric routing, typed tool
adapters, and UI projection begin in later milestones. No AgentLoop dependency
is installed in M1.
