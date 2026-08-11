# M6 core POC acceptance

M6 passes only when automated evidence demonstrates all ten scenarios. Passing M6 does not close the M0-M10 Goal.

1. One real Pi session operates the canvas, code, and Run Detail workbenches under one Activity without losing context.
2. Session A asks Session B a question; B retrieves a bounded, anchored source window and replies with provenance.
3. B forks an independent StrategyVariant from A's base; concurrent edits never overwrite each other.
4. Both variants run through the OQS cleanroom Rust/PyO3 formal engine with working long/short orders, signed positions, covering, and a per-side fee of `0.0006` included in trades and metrics.
5. The OQS-owned Run Detail renders the same immutable Run artifact: RunSpec, orders, trades, positions, cash, equity/drawdown, metrics, fees, logs, provenance, and gate outcomes.
6. Promote uses compare-and-set. After one candidate advances the head, the other stale candidate receives an explicit conflict.
7. A long job lets the Pi session sleep, persists progress, survives an application restart, and wakes the same session on a durable event without continuous model polling.
8. Debug/Info/Warn/Error and P1-P4 filters work. Deleting selected logs makes their bodies and full-text hits unavailable.
9. Exporting and importing the ResearchProject preserves Git tree identity, Run identity, and artifact hashes.
10. The complete path runs through automated integration/E2E tests. Manual narration or screenshots alone do not pass.

## Required test classes

- unit tests for pure state transitions and cost/accounting calculations
- TypeScript/Python contract tests from shared fixtures
- restart and redelivery integration tests
- differential tests against approved open-source protocol oracles
- browser E2E for the unified workbench
- deterministic golden backtest fixture

CI and local execution are separate evidence. A local pass does not imply CI passed.
