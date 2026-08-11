# Session Fabric

## Purpose

Session Fabric coordinates one Pi session across multiple workbenches and coordinates multiple Pi sessions inside one ResearchProject. It is a product subsystem, not another AgentLoop.

## Same-session, multiple-workbench behavior

- One `AgentSession` remains active while the user moves between canvas, code, model, backtest, Run Detail, and Forward Test workbenches.
- Tool calls carry the current `activity_id` and `workbench_id`, but the session retains access to every project research tool.
- The chat panel binds to the session, not the current route.

## Cross-session operations

- `session_list` and `session_status`
- `session_search` and bounded `session_context`
- `session_send`
- `session_ask` and `session_reply`
- `inbox_pull` and `inbox_ack`
- `session_handoff`
- `task_claim` and `task_release`

Active sessions use an in-process registry and router. Normal delivery uses Pi `followUp`; only an explicitly authorised urgent event uses `steer`. Offline messages remain in the durable inbox and may wake the same session through the event scheduler.

## Retrieval contract

1. Search inside the current ResearchProject by default.
2. Return a bounded top-K list of excerpts with `session_id`, branch/leaf identity, `entry_id`, timestamp, hash, and source URI.
3. Read a bounded window around an explicit entry anchor.
4. Respect the remaining Pi context budget.
5. Render retrieved material as quoted evidence, never as system instructions.

Cross-project lookup requires an explicit project link or handoff.

## Message contract

Messages carry stable message, correlation, sender, recipient, project, activity, source-reference, and timestamp fields. Receipt states are `queued`, `receiver_received`, `injected`, `acknowledged`, `cancelled`, `superseded`, or `expired`. Timeouts do not pretend the underlying message was cancelled.

## Conflict boundary

Sessions exchange revision and artifact references. They never exchange an implicit "latest file" pointer. Writing another session's revision directly is forbidden.
