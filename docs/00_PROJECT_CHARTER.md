# Project charter

Decision snapshot: 2026-08-12, Asia/Shanghai.

## Goal

Build one small, local-first quantitative research product around Pi. The product must support rigorous strategy development, reproducible A-share and crypto backtests, multi-workbench agent operation, and bounded cross-session collaboration on a normal developer Mac.

## Product scope

- Research, backtesting, formal comparison, and Forward Test.
- A-share daily research and crypto linear-perpetual bar research are first-class domains.
- All instruments support actual long and short simulation semantics. This is not a label: orders, signed positions, cover lifecycle, costs, and metrics must agree.
- No real-money order sending, broker connectivity, or exchange execution.
- Forward Test means local historical walk-forward/replay, not live market data or a paper broker.
- One formal Run may be active at a time; the target ceiling is about 250,000 bars in 60 seconds on a normal development machine.

## Frozen architecture decisions

1. This independent MIT monorepo is the integration target; donor repositories remain read-only and are not copied.
2. `earendil-works/pi` is the sole AgentLoop, accessed through a TypeScript adapter.
3. Runtime boundaries are one OQS-owned React/Vite SPA, one TypeScript control plane, one Python domain/job service, and one OQS-owned cleanroom Rust/PyO3 formal engine.
4. Python is the sole durable writer for business state. TypeScript sends versioned commands and receives SSE events.
5. Pi session JSONL is conversation truth. The product stores indexes and provenance, not a competing transcript truth.
6. The Research Project Graph owns domain relationships. The infinite canvas is its editable projection.
7. Session is provenance, not strategy ownership. Strategies belong to ResearchProject through immutable variants and revisions.
8. Job Runner performs long data, training, backtest, and Forward Test work without holding an LLM call open.
9. Formal Run metrics come only from the formal engine and immutable artifacts.
10. The application is local-first, single-user, and research-only. It does not add accounts, RBAC, cloud HA, real trading, or a second workflow runtime.
11. Immutable DataSnapshot, strategy revision, parameters, costs, engine/environment identity, and artifact hashes bind every Formal Run.
12. M6 is the original ten-scenario POC gate; it does not close the M0-M10 program.

## Logging principle

Logs are structured, levelled, prioritised, filterable, exportable, and deletable. Diagnostic log deletion must not silently destroy domain state. Domain objects are deleted through their own Session, Run, or Project lifecycle.

## Success boundary

M6 succeeds only when the automated POC in `07_POC_ACCEPTANCE.md` passes. The project Goal succeeds only when every M0-M10 exit condition in `08_IMPLEMENTATION_PLAN.md`, local validation, required CI, independent review, PR merge, and post-merge checks have direct evidence. Architecture documents, empty packages, mocks, screenshots, or self-reported agent completion are not success.
