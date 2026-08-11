# Implementation plan

## M0: Foundation and evidence

- Verify the new repository, instructions, toolchain, and local data root.
- Refresh donor Git status, origins, licenses, and exact source boundaries.
- Resolve clean snapshot strategy for dirty QuantBT and quant-assistant worktrees.
- Freeze a small local dataset and a deterministic long/short golden backtest.
- Define package manifests and the first executable contract test.

Stop condition: do not copy donor source while its provenance or license is unresolved.

## M1: Contracts and durable domain core

- Implement shared command/event/artifact schemas.
- Implement the Python domain model, SQLite WAL migrations, transactional event/outbox writes, Job Runner skeleton, and structured logging.
- Prove idempotent command handling and SSE resume.

## M2: Pi and Session Fabric

- Add the pinned Pi adapter and typed tools.
- Implement one session across multiple workbenches.
- Implement session registry, bounded recall, send/ask/reply, durable inbox, and wake-up behavior.

## M3: Revisions and formal engine

- Implement Git-backed WorkspaceRevision and StrategyVariant isolation.
- Integrate the formal Rust/PyO3 engine through the Python service.
- Implement immutable RunSpec/Run, formal gates, compare, merge, and CAS Promote.

## M4: Unified product UI

- Build one React/Vite shell.
- Migrate QuantBT workbench, infinite canvas, Run Detail, comparison, and gate surfaces.
- Adapt VibeTrading interaction patterns for Pi sessions and streaming state.
- Add Activity timeline and session/task/inbox views.

## M5: Recovery and lifecycle

- Prove restart recovery, job checkpoints, cancellation, and explicit retry.
- Implement log retention/deletion, quotas, project export/import, and dependency-aware deletion.

## M6: POC closure

- Run every test in `07_POC_ACCEPTANCE.md`.
- Perform an adversarial architecture and delivery-truth review.
- Record local, remote, CI, production, and user-acceptance states separately.

## Sequencing rule

Each milestone must end with a real runnable vertical slice and automated evidence. Later milestones do not excuse a missing predecessor.
