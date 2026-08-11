# Start-development prompt

Copy the text below into a fresh Codex task opened at this repository.

---

You are developing Open Quant Studio in the current repository. It is a local-first, research-only quantitative strategy studio that fuses selected capabilities from VibeTrading, QuantBT, and quant-assistant around Pi as the sole AgentLoop.

Start by reading `AGENTS.md`, then `docs/00_PROJECT_CHARTER.md` through `docs/08_IMPLEMENTATION_PLAN.md`. Reopen the live Git state of this repository and every donor path named in `docs/06_MIGRATION_MAP.md`; the document is an index, not current proof. Preserve all donor changes and do not copy a dirty worktree implicitly.

Your immediate objective is M0 only:

1. verify local and remote repository state;
2. refresh source commits, dirty state, licenses, and provenance boundaries;
3. propose and implement the smallest buildable monorepo foundation consistent with the frozen architecture;
4. create the first shared command/event contract and an executable cross-language contract test;
5. create a tiny frozen local market fixture and deterministic long/short golden-backtest specification, without pretending the formal engine is integrated;
6. validate the bootstrap and report exact evidence.

Constraints:

- Pi is the only AgentLoop; no Claude-specific loop, supervisor LLM, or second orchestration runtime.
- One React/Vite SPA; no iframe or microfrontend.
- TypeScript owns active sessions; Python is the sole durable business writer; Rust/PyO3 is the intended formal backtest authority.
- No real trading or broker/exchange order submission.
- All official artifacts require provenance; shell output cannot self-register as a formal Run.
- Concurrent strategy work uses independent variants/revisions and explicit CAS promotion.
- Logs follow `docs/05_LOGGING_AND_RETENTION.md` and remain deletable.
- Do not install large optional dependencies, datasets, browsers, models, containers, or global packages without a separate current authorization.
- Do not commit or push unless the user explicitly authorizes it in the current task.

Before writing, give a short evidence-backed plan with write scope and validation. Do not begin M1 until M0's stop conditions and tests pass. At the end, separate local checkout, remote branch/PR, local tests, CI, production, and user acceptance.

Done when M0 has a buildable, tested foundation and every donor/import decision is provenance-safe. A scaffold, mock-only path, or document-only claim is not M0 completion.

---
