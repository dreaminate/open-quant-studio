# Start development

Open this repository and read `AGENTS.md`, `README.md`, and
`docs/00_PROJECT_CHARTER.md` through `docs/08_IMPLEMENTATION_PLAN.md`.
Refresh live Git, files, tests, remotes, CI, donor states, and current Goal
state; saved evidence and this prompt are indexes, not proof.

Implement the earliest incomplete M0-M10 milestone as one runnable vertical
slice. Preserve these invariants:

- research-only; no broker/exchange order submission or online market provider
- Pi is the only AgentLoop
- TypeScript owns active Pi sessions; Python owns durable business writes
- OQS cleanroom Rust/PyO3 is the formal backtest authority
- one OQS-owned React/Vite SPA; no iframe, microfrontend, or donor source
- immutable Run and DataSnapshot identities; child revisions/variants instead
  of last-write-wins
- shell output requires a typed domain command before becoming official state
- local checkout, remote/PR, local tests, CI, production, and user acceptance
  are separate delivery states

Before writing, inspect `git status --short --branch`, declare the bounded
write scope and validation, and preserve every unrelated change. Do not add a
dependency until its package boundary, upstream implementation, version,
license, and validation oracle have been checked. Do not commit, push, create a
PR, merge, or deploy unless the active user request explicitly authorizes it.
