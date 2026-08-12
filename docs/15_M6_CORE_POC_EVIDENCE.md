# M6 core POC evidence

Evidence date: 2026-08-12, Asia/Shanghai.

This document records local-checkout evidence for the ten M6 scenarios in
`docs/07_POC_ACCEPTANCE.md`. M6 is a core POC gate, not completion of the
M0-M10 Goal.

## Scenario evidence

1. `m2-real-session-fabric.test.mjs` runs two official Pi AgentSessions against
   real Python HTTP. One Activity keeps the same session identity across
   workbench context, recall, reply, SSE, and durable receipts.
2. The same test has Session A ask Session B about the `0.0006` fee model. B
   retrieves a bounded JSONL source window and sends a provenance-bearing reply.
3. `test_two_variants_keep_independent_child_revisions_and_compare` creates two
   child StrategyVariants from one base, retains independent heads, and compares
   their immutable Git trees without moving the project head.
4. The Rust suite proves long, short, cover, signed positions, A-share T+1,
   crypto T+0, trades, fees, cash, funding, equity, and metrics. The two-candidate
   domain scenario runs both candidates through the real PyO3 engine.
5. The mocked and real browser verticals render the formal Run Detail from the
   returned immutable Run: RunSpec, engine identity, orders, trades, positions,
   ledgers, equity/drawdown, metrics, costs, provenance, gates, and logs.
6. `test_two_validated_candidates_race_and_only_one_cas_promote_wins` completes
   two validated candidates and proves exactly one project-head Promote while
   the stale candidate receives the product conflict outcome.
7. `test_reopen_resumes_from_the_last_persisted_checkpoint` proves formal job
   progress resumes after reopening. `m6-session-restart.test.mjs` independently
   restarts the real domain service, reopens the same Pi session and JSONL,
   delivers an offline durable message with wake enabled, and injects it once.
8. The M5 diagnostics suite proves level/priority filters, UTF-8 quota,
   retention, deletion, and removal from full-text results. The browser/client
   tests prove the user-facing filter and deletion routes.
9. The archive suite exports and imports one project and compares Git tree, Run,
   and Artifact identities. The HTTP and browser tests exercise the same normal
   flow.
10. `m4-live.spec.ts` starts the current local runtime on isolated loopback
    ports and drives Canvas, Pi Chat, Code edit, child revision, comparison,
    merge, Formal Run, worker/PyO3 completion, Run Detail, and Promote in a real
    Chromium browser.

## Local validation record

`pnpm run validate:m6` exited `0` in the current checkout. It ran the complete
M5 gate followed by:

- 2 Python domain tests for independent variants and two-candidate Promote;
- 2 real-session integration tests for ask/reply and application restart/wake;
- all TypeScript production builds and the PyO3 development build;
- 1 real Playwright browser vertical.

The cumulative results were 25 contract tests, 16 automatic Rust tests plus one
ignored manual benchmark, 3 PyO3/reference tests, 32 focused M5 domain tests, 4
M5 control-plane tests, 1 mocked browser test, 2 M6 domain tests, 2 M6 session
tests, and 1 real browser test, all passed. The Vite build emitted the same
non-blocking application-chunk warning recorded in the M5 evidence.

## Explicit residuals and non-claims

- M6 closes the core POC gate only. M7 local data import, M8 six strategies, M9
  complete formulas/reports, and M10 Docker/CI/PR/merge remain open.
- The current development Mac passed the named 250,000-bar release benchmark
  in 12.66 seconds; the M10 gate must repeat it alongside the remaining
  delivery checks.
- No remote CI, production deployment, or user acceptance is claimed.

## Delivery state

- local checkout: the M6 gate is implemented and passed locally on branch
  `codex/oqs-m0-m10-minimal`;
- remote branch or PR: this working tree has not been pushed and is not in a PR;
- local tests: `pnpm run validate:m6` passed;
- CI: unqueried for the current unpushed state;
- production: no deployment was performed;
- user acceptance: not performed; the full Goal remains active through M10.
