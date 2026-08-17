# Charter Migration Map: v5 → v6

Generated for the `adopt-team-charter` adoption. One row per existing v5 rule;
every row names a unique destination in the canonical charter (the current
global `init-project-agent-team/assets/TEAM.md`), in `charter-meta.json`, or in
the managed pointers. Coverage is machine-checked: the adoption preview
requires every rule id below to appear in exactly one row and every row to
name a real destination.

## Rule mapping

| Rule id | v5 rule | Unique destination |
|---|---|---|
| V5-R1 | Title `# Fixed Six-Seat Agent Team` | Canonical charter line 1 — identical title. |
| V5-R2 | `<!-- init-project-agent-team:charter-version=5 -->` version marker | Removed from the charter body. The semantic version moves to `.agent-team/charter-meta.json` (`contractVersion: 6`); the authoritative revision record is the charter digest plus the Git object tuple (charter section "Git-Tracked TEAM Writing and Collaboration"). |
| V5-R3 | Scope: charter applies to starting/repairing the Team and creating/dispatching/executing/coordinating/reviewing/accepting Team work; other instructions stay in force; charter defines seat identity and the collaboration contract | Canonical charter line 5 — expanded trigger list (initialize/create/start/restart/clean/repair/manage, worktrees, and any change to this file or its Git-tracked rules) and expanded definitions (seat identity, worktree ownership, writing discipline, collaboration contract). |
| V5-R4 | Scope: charter initialization writes project instructions only; Team startup separately creates Orca runtime state | Canonical charter line 7 — "Charter installation and root-worktree bootstrap are separate phases. Initialization may ensure only the `main` and logical `team` bootstrap worktrees. Team startup separately creates resident Orca runtime state and requires explicit authorization plus the complete topology gate below." |
| V5-R5 | Fixed Roster table: six positions, agents + LLMs, startup parameters, permission parameters | Canonical charter lines 13–18 — same six seats; two permission cells change: `leader-claude` and `principal-fullstack-claudex` become `auto mode on (--permission-mode auto)`; position column uses the fixed display labels. |
| V5-R6 | Roster identity paragraph: six rows jointly define seat identities; the instruction chain and current user authorization govern; permission values record launch mode only; the startup workflow owns launch commands | Canonical charter line 20 (identity paragraph) plus line 22 (new fail-closed sentence: verify each selected CLI profile or Agent definition preserves the canonical seat identity and role before startup). |
| V5-R7 | Authority definitions: Leader = Claude Code seat on `deepseek-v4-pro[1m]` at max effort; top-level employee = the five non-Leader seats through Orca; Codex CLI seat is Deputy | Canonical charter line 143 — identical text. |
| V5-R8 | Leader is the sole final decision-maker: objective, decomposition, priorities, dependencies, scope and acceptance changes, Task-to-Dispatch binding, seat assignment, integration decisions, conflict resolution, final acceptance | Canonical charter line 145 — identical text. |
| V5-R9 | Deputy advises Leader on architecture, plans, alternatives, tradeoffs, risks, integration quality; may challenge a proposal and recommend a decision | Canonical charter line 146 — identical text. |
| V5-R10 | Deputy recommendations are advisory; Deputy does not bind or reassign a Dispatch, change priority/dependency/scope/acceptance, accept Team work, or override Leader | Canonical charter line 147 — identical text. |
| V5-R11 | Within an assigned Dispatch, Deputy may decide reversible technical details inside its objective/scope/constraints/dependencies/acceptance criteria | Canonical charter line 148 — identical text. |
| V5-R12 | Deputy as accountable employee for implementation or review Dispatches retains advisory authority; may delegate only within the Dispatch through native subagents | Canonical charter line 149 — identical text. |
| V5-R13 | Each assignment states objective, scope, constraints, dependencies, and checkable acceptance criteria, and binds the work to one Dispatch and one top-level seat | Canonical charter line 150 — identical text. |
| V5-R14 | Top-level employees may use native subagents when instructions and user authorization permit; the parent limits scope, validates results, remains accountable | Canonical charter line 151 — identical text with "top-level member" wording. |
| V5-R15 | Top-level employees coordinate technical details directly; owner/priority/dependencies/scope/acceptance changes return to Leader | Canonical charter line 152 — identical text. |
| V5-R16 | Communication Topology table (5 routes: Leader↔employee, employee↔employee, employee↔own subagent, subagent→Leader, subagent→other employee) | Canonical charter lines 156–162 — same five routes; rows update to "top-level member ↔ own subagent", "subagent → Leader: relayed by its parent member; a Leader-owned subagent reports directly to Leader", and "subagent → another top-level member: relayed by the parent member". |
| V5-R17 | Subagent reports only to its parent employee; parent relays through Orca; a subagent is not an Orca top-level member, acquires no identity, and does not complete the parent's Dispatch | Canonical charter line 164 — same rule with "top-level member" wording. |
| V5-R18 | Lifecycle 1: every Quick Start fully replaces this project's Orca seat sessions (closes old terminals, creates one fresh session per seat) | Canonical charter lines 181–182 — expanded: the future launcher verifies the complete six-worktree topology first, may close only the prior-generation recorded resident tabs under an exact generation lease or compare-and-stop contract, proves the zero-state barrier, and leaves `main`, task worktrees, subagent sessions, setup terminals, and unrelated terminals unchanged. |
| V5-R19 | Lifecycle 2: each top-level seat owns one resident native CLI session during the startup cycle; sequential work reuses the same session | Canonical charter line 183 — expanded: the launcher records one new generation with, for every seat, seat key, Agent token, branch, worktree ID, canonical path, parent worktree ID, tab ID, terminal handle, effective permission mode, and launch arguments; the Leader record binds `leaderBootstrapCommit`, `acceptedMainCommit`, current head, and full tree; all IDs distinct. |
| V5-R20 | Lifecycle 3: Leader assigns a Dispatch to the selected seat; that seat executes and communicates from its own session | Canonical charter line 184 — identical rule, plus "and worktree". |
| V5-R21 | Lifecycle 4: the assigned top-level employee sends exactly one `worker_done` from its own resident session with a nonempty summary and explicit outcome | Canonical charter line 185 — identical rule with "top-level member" wording. |
| V5-R22 | Lifecycle 5: Leader evaluates the evidence, resolves independent review findings, settles the Dispatch; sessions remain for later work | Canonical charter line 186 — identical rule. |
| V5-R23 | Quick Start receipt scope: the receipt proves only the launcher cleanup barrier and six terminal-creation receipts, not TUI/auth/model readiness, routes, or lifecycle | Canonical charter line 188 — expanded: a future receipt proves the verified worktree mapping and six resident-terminal creation receipts only; it does not prove TUI, authentication, provider or model readiness, message delivery, task lifecycle, hard security isolation, or user acceptance. |
| V5-R24 | Review and Acceptance bullets: Independent Reviewer performs functional review (expand to security audit only when the task requires it); base claims on current files/output/tests/receipts; report the six delivery layers separately with `Unqueried:`/`Unverified:`; Leader declares complete only after the lifecycle and evidence — `worker_done` alone is not acceptance | Canonical charter lines 192–195, one bullet each, in order — all four identical in text. |

## Content with no v5 counterpart (added by the canonical charter, not migrated)

- "Canonical Identities and Branch Names" (lines 24–41): six seat keys, position tokens, Agent tokens, six persistent integration branches, task-branch syntax, and the two-OpenCode-seat routing rule.
- "Worktree Hierarchy" (lines 43–66): the two lineage roots, the logical `team` alias, the tree diagram, and the recorded-facts rule (worktree ID, path, branch, parent ID, seat key, generation).
- "Creation and Worktree Authority" (lines 68–83): the bootstrap controller is not a seventh member; the managed bootstrap set; the six-step create/validate procedure; per-seat worktree ownership boundaries.
- "Branch Flow and Dependencies" (lines 85–96): the standard merge flow and cross-employee dependency rules.
- "Git-Tracked TEAM Writing and Collaboration" (lines 98–127): sole charter body, byte-identical install rule, Git-object revision records, the `safe-git` no-exec boundary, the seven-step rule-change contract, and the forbidden list.
- "Top-level Collaboration Rules" (lines 129–139): the seven handoff contracts with trigger/responsible/collaborators/input/output/forbidden per rule.
- Message envelope and fail-closed routing rules (lines 166–175): mandatory envelope fields, dispatch addressing, sender/recipient verification, rejection behavior, acknowledgment scope, broadcast limits, and context minimization.
- Topology safety hold (line 179): the current launcher is under a topology safety hold and creates no resident session.

## Managed pointer update (part of adoption, outside the charter body)

| File | Change |
|---|---|
| `AGENTS.md` | Replace the old managed pointer block (328 bytes) with the canonical pointer block (545 bytes). All other instructions preserved byte-for-byte. |
| `CLAUDE.md` | Replace the old managed pointer block with the canonical pointer block. The file consists solely of the pointer. |

## Deduplication boundary

- `TEAM.md` keeps roles, topology, permissions, and lifecycle principles — the normative body.
- The two global skills keep only input/output, commands, and failure codes; they are global assets and are not modified by this adoption.
- The repo-local tools under `.agent-team/` implement only I/O mechanics and reference the charter for every normative rule.
- Orca command semantics are not copied into the charter; the charter references the public Orca CLI by capability, and unresolved capabilities stay pending placeholders that fail closed.
