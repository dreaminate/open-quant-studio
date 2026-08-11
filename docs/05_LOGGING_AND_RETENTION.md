# Logging and retention

## Two independent dimensions

- `level`: `debug`, `info`, `warn`, or `error`.
- `priority`: `p1`, `p2`, `p3`, or `p4`.

`silent` is a collection/display threshold, not an emitted event level. It stops diagnostic logs for its configured scope but does not stop domain events required to maintain project state.

## Required fields

`timestamp`, `level`, `priority`, `component`, `event_code`, `project_id`, `activity_id`, `session_id`, `task_id`, `job_id`, `run_id`, `correlation_id`, and `message` are the shared schema. Fields that do not apply are null, not guessed.

Large tool output, model output, and backtest details are stored as artifacts; the log contains a reference and hash. Credentials, cookies, authorization headers, tokens, secret environment values, and raw secret-bearing configuration are never logged.

## Defaults

- Collection threshold: Info.
- Debug retention: 7 days.
- Info retention: 30 days.
- Warn retention: 90 days.
- Error/P1 retention: until user deletion.
- Diagnostic log quota: 2 GiB, user-configurable.

When the quota is reached, the cleaner removes the oldest Debug, then Info, then Warn records. Error/P1 records are never automatically removed. Artifacts use a separate quota.

## Deletion

Users can delete one record or select by project, session, Activity, Run, time, level, and priority. Deletion removes log bodies, full-text indexes, and caches. A content-free deletion receipt may record time, scope, count, and actor.

Clearing diagnostic logs does not delete domain state. Session, Run, Artifact, and Project deletion use their own dependency-aware operations. Export offers full logs, Warn/Error only, or no logs.
