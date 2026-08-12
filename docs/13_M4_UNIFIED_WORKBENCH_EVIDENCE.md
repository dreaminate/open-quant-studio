# M4 unified workbench evidence

Evidence date: 2026-08-12, Asia/Shanghai.

This document records local-checkout implementation and validation evidence for
M4. It is not evidence of remote CI, production deployment, M5-M10 completion,
or user acceptance.

## Implemented vertical slice

1. Shared contracts define strict Project, Activity, Artifact metadata, formal
   engine result, formal Run manifest, terminal Run list, and succeeded/failed
   Run detail read models. TypeScript and Python validate the same semantic
   identities, including project, Activity, Run, job, Artifact, manifest, and
   engine-result hash bindings.
2. Python remains the durable business writer. It exposes project-scoped read
   models, verifies CAS bytes before returning Artifact content or succeeded Run
   detail, preserves immutable failed Run details without result Artifacts, and
   runs a continuous worker process. Migration `006` permits only one globally
   running Formal Run and terminalizes legacy running claims before an old
   binary can complete them.
3. The TypeScript browser facade seals one active project, Activity, session,
   and Workbench context. Browser requests cannot supply actor identities,
   command identities, Formal Run hashes, validation identities, raw jobs,
   arbitrary blob staging, or Pi internal state. Child revision, merge,
   Formal Run, and Promote requests derive fresh server-side heads and bounded
   typed commands.
4. Revision file content requires both exact revision membership and verified
   project-scoped Artifact metadata and bytes. A foreign-project Artifact cannot
   enter the content path through the public client method.
5. The single React/Vite SPA provides Project and Activity selection, a React
   Flow Canvas, Pi Chat, CodeMirror strategy editing, revision comparison,
   merge, Backtest, immutable Run Detail, Run-scoped Logs, and explicit
   Forward Test, Data, and Settings milestone boundaries. Canvas Session,
   Strategy, Run, and Artifact nodes support pan, zoom, selection, drag, edges,
   and project/Activity-scoped persisted positions.
6. Run Detail renders the returned RunSpec, engine orders, trades, positions,
   cash ledger, funding ledger, equity, drawdown, metrics, costs, assumptions,
   manifest, provenance, gates, and logs. The SPA does not recalculate a second
   metric set.
7. `scripts/run-m4-local.mjs` composes one loopback-only local runtime: built
   SPA, Uvicorn domain service, continuous Python worker, one official Pi
   `AgentSession`, session registry, and browser facade. All processes share one
   named data root strictly inside repository `var/`; shutdown disposes the Pi
   session/model and stops both Python processes. A random per-launch instance
   token must round-trip through the domain health response before bootstrap, so
   an incumbent service on the configured port cannot silently attach the
   facade to a different data root.
8. The launcher validates and freezes the pinned synthetic formal fixture
   before it creates a directory, starts a process, or performs a durable
   command. Strategy source is derived only from the validated canonical input.
   A tampered fixture fails without leaving data-root state.
9. The local M4 launcher uses the official Pi faux provider as an offline,
   deterministic demo model. It remains the model stream for the one Pi
   AgentSession, not a second AgentLoop. The SPA waits for the Pi EventSource to
   report an open connection before enabling Send, so the 204 prompt response
   cannot race and lose an ephemeral assistant event.

## Real browser evidence

The real Playwright vertical starts the current local launcher with isolated
loopback ports and an exact temporary data root. It then performs:

```text
Project / Activity -> Canvas -> Pi prompt / SSE reply
-> edit strategy.py -> child revision -> compare -> merge candidate
-> Formal Run -> continuous worker -> Rust/PyO3 result -> Run Detail
-> compare-and-set Promote
```

The test verifies three React Flow edges, an HTTP 200 `text/event-stream` Pi
subscription and visible assistant message, exact strategy edit persistence,
comparison output, the formal engine identity, four orders, four trades, a
promoted project head equal to the Run candidate, and a 404 for the forbidden
raw browser jobs route. The mock browser vertical separately verifies exact
sanitized child/merge request bodies and Run-detail polling after an initial
404.

## Test-first and adversarial evidence

Representative failures found and fixed while closing M4 include:

- terminal Run reads were initially absent, and succeeded-only Artifact
  assumptions made failed immutable Runs return 409;
- two workers could initially claim two Formal Runs, while a naive migration
  requeue still allowed a pre-migration binary to win a stale completion;
- the browser facade initially existed only as a library with no runnable SPA,
  worker, or same-origin composition root;
- revision metadata preserved by a GET was initially posted back into the
  strict child/merge write body and returned 422;
- the first Canvas refresh dropped measured React Flow state and produced no
  visible edges;
- the local launcher initially accepted an escaping `OQS_DATA_ROOT`, validated
  the formal fixture after durable bootstrap writes, and created Pi without a
  usable model;
- a healthy but unrelated quant-domain process on the configured port was
  initially accepted as launcher readiness, splitting durable browser writes
  from the launcher's worker and Pi data root;
- the first real Pi Chat could race its EventSource subscription and lose the
  assistant message because the prompt endpoint returns an empty 204;
- the cumulative M1 migration-ledger test initially expected only migrations
  `001` through `005` after M4 added migration `006`.

Each blocking failure received a focused regression or real-browser assertion.

## Local validation record

After the final instance-token and Pi EventSource readiness changes,
`pnpm run validate:m4` exited `0` in the current checkout. The cumulative gate
included:

- bootstrap manifest: 57 required files present, and the repository data-root
  probe passed;
- shared contracts: 18 tests passed, including TypeScript/Python parity and
  strict M4 read-model semantics;
- control plane: 50 tests passed, including real Uvicorn, two official Pi
  sessions, browser facade, Artifact scope, and SSE behavior;
- M1-M2 Python regression: 22 tests passed;
- Rust: 11 engine tests passed; formatting and Clippy with `-D warnings`
  passed;
- PyO3: 2 differential/reference tests passed;
- complete Python domain discovery: 63 tests passed with `ResourceWarning`
  treated as an error;
- focused M3: 8 contract, 10 control-plane, and 31 Python tests passed;
- focused M4: 18 contract, 50 control-plane, 10 Python, and 2 Playwright tests
  passed;
- SPA and component TypeScript builds passed. Vite reported one non-blocking
  865.70 kB minified chunk-size warning.

React Doctor was run against both frontend packages after the final UI change.
It scanned 12 files, exited `0`, and reported only the non-blocking large
`ResearchWorkbench` component warning. Its remote scoring API was unreachable
in the restricted environment, so no post-change numeric score is claimed.
`git diff --check` also exited `0` with no output.

Two independent post-implementation reviews reported no unresolved P0 or P1 in
their final current-snapshot verdicts. One independently ran the frontend
builds, real Playwright vertical, and cumulative M4 gate. The other reproduced
the former two-data-root port collision after the instance-token fix: the
launcher exited `1`, never exposed the browser as ready, and created no project
in the incumbent data root. Its focused control-plane build and 11-test browser
suite passed. Their remaining P2 observations are missing drag-then-reload and
empty-catalog browser assertions, no forced first-404 in the real vertical, and
the intentionally out-of-scope external-model/reconnect path.

## Explicit residuals and non-claims

- The pinned synthetic fixture proves the M4 product path, not market
  performance or a user-supplied data workflow.
- The deterministic local demo model proves Pi Chat/SSE composition without an
  API key. It is not a claim that a cloud model/provider is configured.
- Forward-test replay, checkpoint/restart/cancel/retry, log deletion/retention,
  project export/import, and the complete POC are M5-M6 work.
- CSV/Parquet DataSnapshot import, six built-in strategies and generated
  notebooks, complete formula reconciliation, HTML/JSON reports, Docker
  Compose, multi-platform CI, and final end-to-end delivery remain M7-M10 work.
- No remote CI, production deployment, or user acceptance is claimed.

## Delivery state

- local checkout: M4 is implemented in the local checkout on branch
  `codex/oqs-m0-m10-minimal`, based on M3 checkpoint
  `ae5fd022dfc347523bdb1ed89e368b36083c2fef`;
- remote branch or PR: this M4 working-tree state is not yet pushed and is not
  represented by a PR;
- local tests: the named cumulative and focused commands above passed;
- CI: no CI result exists for this unpushed M4 state;
- production: no deployment was performed;
- user acceptance: pending explicit user review and completion of M5-M10.
