# M9 Run report evidence

Date: 2026-08-12

## Implemented vertical

- The Python reference derives every displayed period, return, drawdown,
  exposure, cost, and trade-count field from the immutable Rust engine result.
- Reconciliation records compare the independently derived values with Rust
  metrics and costs, including deterministic zero-trade behavior.
- A succeeded Run materializes one canonical JSON report and one standalone
  dependency-free HTML report as immutable Run artifacts.
- Run Detail renders the report values, formula definitions, identities, and
  reconciliation checks without recalculating them in TypeScript.
- JSON and HTML downloads use the same report artifacts, and project export
  includes both artifacts and their hashes.
- The five single-symbol strategies and the multi-symbol A-share rotation all
  produce reconciled reports from real Rust results.

## Functional evidence

The focused M9 gate is `pnpm validate:m9`. Its M9-specific commands are:

```text
pnpm run test:m9-contracts
pnpm run test:m9-domain
pnpm run test:m9-control-plane
pnpm run test:m9-ui
```

Evidence from the cumulative gate:

- `pnpm run validate:m9`: exit 0
- full shared contracts: 37 tests passed; focused M9 report contracts: 6
  tests passed
- Python reference, Run materialization/HTTP/archive, and six-strategy reports:
  9 tests passed
- control-plane report/read/download surface: 1 test passed
- Chromium Run Detail/report/download E2E: 1 test passed
- contracts, control-plane, research-ui, and web builds passed
- the cumulative M0-M8 contracts, Rust v1/v2, PyO3, lifecycle, restart,
  rerun, logs, Forward Test, archive, data import, six-strategy workbench, and
  real-browser gates also passed in the same command

The browser and HTTP tests require permission to bind local loopback ports in
the Codex execution environment. A raw local-test attempt returned
`listen EPERM`; the same tests passed when run with loopback permission.

## Formula boundary

All atom values remain canonical decimal strings. Rate atoms use a scale of
`1_000_000` and truncate toward zero. Funding is reported as cost, defined as
the negative sum of funding-ledger wallet deltas. For v1, final net exposure is
ending equity minus ending cash; for the long-only v2 A-share portfolio, gross
and net exposure equal final market value. Each definition records its name,
unit, formula, inputs, and empty behavior in the report itself.

## Delivery boundary

- Local checkout: implemented in the current uncommitted working tree.
- Local tests: focused M9 commands and cumulative `pnpm run validate:m9`
  passed.
- Remote branch or PR: not pushed and no PR created.
- CI: not queried for this uncommitted tree.
- Production: not deployed.
- User acceptance: not performed.
