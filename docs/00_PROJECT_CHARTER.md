# Project charter

Snapshot date: 2026-08-11, Asia/Shanghai.

## Goal

Build one local-first quantitative research product by fusing the useful capabilities of VibeTrading, QuantBT, and quant-assistant around Pi. The product must support rigorous strategy development, reproducible backtests, multi-workbench agent operation, and cross-session collaboration on a resource-limited Mac.

## Product scope

- Research, backtesting, formal comparison, and Forward Test.
- A-share and crypto research are first-class domains, but the platform architecture is asset-agnostic.
- All instruments support actual long and short simulation semantics. This is not a label: orders, signed positions, cover lifecycle, costs, and metrics must agree.
- No real-money order sending, broker connectivity, or exchange execution.
- Medium- and low-frequency strategies, classical machine learning, and LSTM experiments may be supported. The platform does not require general deep-learning infrastructure.

## Frozen architecture decisions

1. A clean independent monorepo is the integration target; donor repositories remain read-only during migration.
2. `earendil-works/pi` is the sole AgentLoop, accessed through a TypeScript adapter.
3. Runtime boundaries are one React/Vite SPA, one TypeScript control plane, one Python domain/job service, and the Rust/PyO3 quant engine.
4. Python is the sole durable writer for business state. TypeScript sends versioned commands and receives SSE events.
5. Pi session JSONL is conversation truth. The product stores indexes and provenance, not a competing transcript truth.
6. The Research Project Graph owns domain relationships. The infinite canvas is its editable projection.
7. Session is provenance, not strategy ownership. Strategies belong to ResearchProject through immutable variants and revisions.
8. Job Runner performs long data, training, backtest, and Forward Test work without holding an LLM call open.
9. Formal Run metrics come only from the formal engine and immutable artifacts.
10. The application is local-first and single-user in v1. A desktop shell may be considered only after the Web POC passes.

## Logging principle

Logs are structured, levelled, prioritised, filterable, exportable, and deletable. Diagnostic log deletion must not silently destroy domain state. Domain objects are deleted through their own Session, Run, or Project lifecycle.

## Success boundary

Success is the automated POC in `07_POC_ACCEPTANCE.md`. Architecture documents, empty packages, mocks, screenshots, or self-reported agent completion are not success.
