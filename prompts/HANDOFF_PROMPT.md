# Cleanroom handoff prompt

Paste this entire handoff into a fresh Codex task opened at `/Users/wzy/Work/01_Projects/My-Projects/Original/open-quant-studio`.

Goal

Continue development of Open Quant Studio from its verified repository state. Deliver the real POC defined in `docs/07_POC_ACCEPTANCE.md` through milestones M0-M6, beginning with the next incomplete milestone. Pi must remain the sole AgentLoop; the product remains research-only.

Audience

A fresh Codex development session with filesystem and terminal access to the local repository and read-only access to the named donor repositories.

Generated at

2026-08-11, Asia/Shanghai.

Authoritative sources

- Current repository Git/files/tests: `/Users/wzy/Work/01_Projects/My-Projects/Original/open-quant-studio`
- Project rules: `AGENTS.md`
- Frozen product decisions: `docs/00_PROJECT_CHARTER.md` through `docs/05_LOGGING_AND_RETENTION.md`
- Donor evidence index: `docs/06_MIGRATION_MAP.md`; refresh it before relying on it
- POC gates: `docs/07_POC_ACCEPTANCE.md`
- Milestones: `docs/08_IMPLEMENTATION_PLAN.md`
- QuantBT donor: `/Users/wzy/Work/01_Projects/My-Projects/Original/QuantBT`
- quant-assistant donor: `/Users/wzy/Work/01_Projects/My-Projects/Derived/quant-assistant`
- VibeTrading donor: `/Users/wzy/Work/01_Projects/Open-Source/G-Finance-Quant-and-Company-Research/Vibe-Trading`
- Pi upstream: `https://github.com/earendil-works/pi`

Verified state

- The integration repository was initialized as a separate public-project bootstrap with architecture, rules, prompts, and milestone documents.
- At handoff generation time, QuantBT and quant-assistant had extensive uncommitted changes; VibeTrading was clean.
- quant-assistant's current local origin pointed to `TencentCloud/TencentDB-Agent-Memory.git`, so that remote is not evidence of the desired quant-assistant product lineage.
- No donor source, runtime dependency, application implementation, formal engine integration, POC result, CI result, or deployment was created by this bootstrap.

Constraints

- Refresh all Git, file, test, remote, and license evidence; do not trust this handoff as current proof.
- Preserve dirty donor worktrees. Do not stash, clean, reset, commit, or copy their uncommitted contents without an explicit reviewed boundary.
- Use the architecture and ownership rules in `AGENTS.md`.
- No real trading, credentials, private data, secret logging, global installs, or unapproved large downloads.
- One Pi AgentLoop, one unified SPA, Python durable writer, Rust/PyO3 formal backtest authority.
- Keep logs structured, prioritised, filterable, and deletable.
- Keep local checkout, remote/PR, tests, CI, production, and user acceptance separate.

Done when

The next incomplete milestone has direct code/test evidence and its stop conditions pass. The full project is done only after every automated POC gate in `docs/07_POC_ACCEPTANCE.md` passes and the user explicitly accepts it.

Next actions

1. Run `git status --short --branch`, inspect remotes, and read all project rules/docs.
2. Refresh the donor states and record contradictions against `docs/06_MIGRATION_MAP.md`.
3. Determine the first incomplete milestone; initially this should be M0.
4. Present a bounded plan, write scope, validation commands, and stop conditions.
5. Implement and validate only the next coherent vertical slice.

Raw failures

- None are assumed current. Re-run relevant commands and preserve any new raw failure text.

Delivery state

  local checkout

  Bootstrap documents and repository structure exist. Product implementation is unverified until refreshed in the new task.

  remote branch or PR

  Query the GitHub remote and branch again. Do not infer it from this file.

  local tests

  Only the bootstrap validator was intended at generation time. Product tests were not run.

  CI

  Unqueried.

  production

  Not deployed; production is outside the POC bootstrap.

  user acceptance

  Bootstrap decisions were approved during architecture discussion; product behavior has not been accepted.

Unverified

- Current repository HEAD and cleanliness
- Current remote branch contents and CI
- Donor states after 2026-08-11
- Pi package compatibility
- Formal backtest integration
- Any runtime, UI, restart recovery, logging deletion, import/export, or POC acceptance behavior

Fresh-start instructions

Treat the handoff as a routing index. Reopen every authoritative source, refresh evidence, and let live Git/files/tests override it. Do not ask the user to repeat settled architecture decisions unless current evidence creates a real conflict. Begin with the next evidence-backed milestone and report progress without unsupported completion language.

```yaml
workflow_id: "open-quant-studio-bootstrap"
topology_revision: 1
progress_update: 0
open_nodes:
  - M0
  - M1
  - M2
  - M3
  - M4
  - M5
  - M6
blocked_nodes: []
next_ready_nodes:
  - M0
```
