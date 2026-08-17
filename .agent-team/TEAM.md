# Fixed Six-Seat Agent Team

## Scope

This charter applies whenever this project's fixed six-seat Agent Team or its worktrees are initialized, created, started, restarted, cleaned, repaired, managed, dispatched, executed, coordinated, reviewed, integrated, or accepted, and whenever this file or its Git-tracked rules change. Read and follow all other applicable project instructions first. Those instructions and existing build, test, safety, delivery, and user-authorization requirements remain in force. This charter defines seat identity, worktree ownership, writing discipline, and the collaboration contract.

Charter installation and root-worktree bootstrap are separate phases. Initialization may ensure only the `main` and logical `team` bootstrap worktrees. Team startup separately creates resident Orca runtime state and requires explicit authorization plus the complete topology gate below.

## Fixed Roster

| Position (fixed display label) | Agent + LLM | Startup parameters | Permission parameters |
|---|---|---|---|
| 一把手 / 最终决策者 | Claude Code + DeepSeek V4 Pro 1M Max | `model=deepseek-v4-pro[1m]; effort=max` | `auto mode on (--permission-mode auto)` |
| 二把手 / 方案顾问 | Codex CLI + GPT-5.6 Sol Ultra Fast | `model=gpt-5.6-sol; effort=ultra; service_tier=priority` | `dangerously-bypass-approvals-and-sandbox` |
| 高性价比全栈工程师 | OpenCode + DeepSeek V4 Flash | `agent=delivery-deepseek-flash; model=deepseek-v4-flash; variant=max` | `auto + agent permission=allow` |
| 独立审查员 | OpenCode + Opus 4.8 | `agent=review-opus; model=jiekou-ai/claude-opus-4-8-r` | `auto + agent permission=allow` |
| 首席全栈工程师 | Claudex + GPT-5.6 Sol | `model=gpt-5.6-sol; effort=max` | `auto mode on (--permission-mode auto)` |
| 前端工程师 | Kimi Code + Kimi K3 | `config model=kimi-k3; thinking=max` | `Orca default --auto` |

The six rows and their parameter and permission values jointly define the fixed seat identities. The active instruction chain and current user authorization govern every action. Permission values record only how each seat's CLI is launched; they do not expand task scope, tool access, sandbox or approval authority, or user authorization. The startup workflow owns the terminal launch commands. Before startup is enabled, verify that each selected CLI profile or Agent definition preserves the canonical seat identity and role; a conflicting profile fails closed.

For `leader-claude` and `principal-fullstack-claudex`, **auto mode on** means the exact Claude Code permission mode `auto`, passed as `--permission-mode auto`. Every start and restart must verify that the current-user Claude default, Orca's canonical `claude` Agent default arguments, and the effective per-seat launch arguments all resolve to that exact mode. No other permission mode or permission-bypass flag is equivalent. A missing, implicit, conflicting, bypass, or non-`auto` value fails closed before terminal creation. Record the effective permission mode and launch arguments in the generation receipt; a settings value or terminal-creation receipt alone does not prove the running session used the required mode.

## Canonical Identities and Branch Names

“Top-level member” means the six roster seats together: one Leader and five non-Leader top-level employees. “Top-level employee” never includes Leader. Fullstack seats are employees under Leader; technical dependency does not grant them authority over Leader or another employee.

Use the Quick Start CLI type as the canonical Agent token. Keep the model and profile names only as launch configuration; do not use them as Agent identity.

| Seat key | Position token | Agent token | Persistent integration branch |
|---|---|---|---|
| `leader-claude` | `leader` | `claude` | `leader-claude-integration` |
| `advisor-codex` | `advisor` | `codex` | `advisor-codex-integration` |
| `fullstack-opencode` | `fullstack` | `opencode` | `fullstack-opencode-integration` |
| `review-opencode` | `review` | `opencode` | `review-opencode-integration` |
| `principal-fullstack-claudex` | `principal-fullstack` | `claudex` | `principal-fullstack-claudex-integration` |
| `frontend-kimi` | `frontend` | `kimi` | `frontend-kimi-integration` |

Every Team branch follows `<position>-<agent>-<feature>`. A task branch uses the owning seat's position and Agent tokens plus a nonempty feature slug that is unique within that seat, normally by ending in a stable Task ID. Reserve the feature `integration` for the six persistent parent branches; a task worktree may not use it. Use lowercase ASCII letters, digits, and single hyphens; keep the full name at or below 100 bytes. Exclude whitespace, slash or backslash, `:`, `~`, `^`, `?`, `*`, `[`, control characters, consecutive dots, leading or trailing dots or hyphens, and the suffix `.lock`. The seat registry is authoritative because position and feature tokens may contain hyphens; never infer ownership by splitting an arbitrary branch name.

The two OpenCode seats are distinct. Route and authorize them by their complete seat key and current worktree identity, never by `opencode` alone.

## Worktree Hierarchy

The initializer-managed topology has exactly two top-level Orca lineage roots: the `main` release worktree and the Leader top-level parent worktree. Unrelated pre-existing roots may coexist unchanged outside that managed topology. The Leader parent has the logical Orca display name `team` and exact Git branch `leader-claude-integration`; `team` is an alias for that existing role-owned parent, not a third managed root, seventh persistent Team worktree, or seventh Team seat. `main` remains the default release worktree and is not part of Leader's managed subtree. The Leader branch starts from the accepted `main` baseline.

```text
repository
|-- main                                      release worktree
`-- leader-claude-integration                 Leader top-level parent
    |-- leader-claude-<feature>               Leader subagent task worktree
    |-- advisor-codex-integration             employee secondary parent
    |   `-- advisor-codex-<feature>           employee subagent task worktree
    |-- fullstack-opencode-integration         employee secondary parent
    |   `-- fullstack-opencode-<feature>       employee subagent task worktree
    |-- review-opencode-integration            employee secondary parent
    |   `-- review-opencode-<feature>          employee subagent task worktree
    |-- principal-fullstack-claudex-integration employee secondary parent
    |   `-- principal-fullstack-claudex-<feature> employee subagent task worktree
    `-- frontend-kimi-integration              employee secondary parent
        `-- frontend-kimi-<feature>            employee subagent task worktree
```

The Leader work-content tree is the logical set of Leader-owned task worktrees directly under the Leader parent; it is not a seventh persistent parent seat. Each employee secondary parent is both that employee's resident workspace and the parent of that employee's task worktrees. Each task worktree belongs to exactly one subagent and has no child worktree unless the current user explicitly changes this rule.

Orca lineage, Git base, filesystem path, and authority are separate facts. Record and verify the exact `worktreeId`, canonical path, branch, parent worktree ID, seat key, and current generation for every parent and task worktree. Persist and verify the Leader branch's immutable creation provenance as `leaderBootstrapCommit`; record the current generation's accepted `main` object separately as `acceptedMainCommit` together with the current Leader head and tree. An existing worktree or branch name alone proves neither provenance nor current synchronization. A visual nesting label or matching branch prefix alone does not prove ownership.

## Creation and Worktree Authority

A user-authorized bootstrap controller provisions or validates the fixed topology. It is a workflow capability, not a seventh Team member, and it does not inherit any seat's task authority.

The initializer-managed bootstrap set is exactly `{main, team}`. Before creating either worktree or branch, bind an accepted Git commit, tree, and TEAM blob that contain the exact current charter plus both managed pointer entries; acceptance also requires a Rule-Change-ID, Independent Reviewer record, Leader decision, and current-user confirmation bound to that exact object. A branch tip or commit hash alone is only a candidate, and the initializer never creates a commit or acceptance record implicitly. It creates or validates `main`, then creates or validates the logical `team` / Leader parent from that accepted baseline.

Team worktrees use the **Orca-first creation contract** (verified against Orca CLI 1.4.180, 2026-08-18): the CLI creates the exact integration branch together with its worktree, so the branch must NOT pre-exist. A pre-existing branch makes the CLI auto-suffix the name (`-2`), which must be rejected — the provisioner fails closed with `leader_branch_collision_cleanup_required` / `employee_branch_collision_cleanup_required`, and the stale branch is removed only through a separately authorized Git command. Creation must be attempted by the public Orca CLI directly in a terminal against the verified local runtime; every Orca subprocess removes all inherited `ORCA_*` and `GIT_*` keys so selectors, paired-runtime state, repository overrides, config injection, filters, or external diff cannot leak into Orca or a cold-started app. Visual inspection, interactive confirmation, a Git-only worktree command, filesystem copying, remote or paired runtime selection, and non-CLI APIs are not substitutes. Worktree paths are Orca-chosen (`<orca-workspaces>/<repo>/<name>`); they are recorded from creation receipts and Git inventory, never assumed from local paths. Preserve every pre-existing worktree outside the bootstrap set without deleting, moving, renaming, reparenting, cleaning, resetting, starting, or otherwise changing it. The complete physical inventory is exactly two only when no unrelated worktree existed before initialization.

1. Confirm the exact `main` release worktree and repository identity.
2. Create the logical `team` / Leader top-level parent with `orca worktree create --repo id:<repo-id> --name leader-claude-integration --base-branch main --no-parent --json`; verify the receipt shows exactly `refs/heads/leader-claude-integration`, a null parent, and a creation receipt; set `--display-name team` via `orca worktree set`; close the receipt-bound first terminal and prove the zero-state barrier.
3. Create or validate all five employee secondary parent worktrees with the same create shape (`--name <seat>-integration --base-branch leader-claude-integration --no-parent`), then bind lineage with `orca worktree set --worktree id:<id> --parent-worktree id:<team-id>` and verify the receipt's `parentWorktreeId`; close each receipt-bound first terminal.
4. Verify all six member worktree IDs, paths, branches, owners, and parent relationships. Fullstack is one of the five employee children and is never Leader's parent.
5. Only after the complete topology passes, start exactly one top-level member in each corresponding parent worktree with `orca terminal create --worktree id:<repo-id>::<path> --command "<cli> ..." --json`; record the receipt's `handle` and `tabId`. Never start the six top-level members in one worktree and never fall back to `active` when a target mapping is missing or ambiguous.
6. For delegated work, the owning top-level member first creates one task worktree under its own parent, verifies its identity and branch, and then starts one subagent inside it.

Leader manages the Leader top-level parent and Leader-owned task worktrees. The five employee subtrees are structurally below the Leader parent but remain outside Leader's worktree-management authority; Leader coordinates them through Tasks, Dispatches, messages, and integration decisions. Each employee manages only its own secondary parent and direct task worktrees. No employee may create, move, remove, retarget, or manage a worktree owned by Leader or another employee. A subagent operates only in its assigned task worktree and may not create worktrees, rewrite a parent branch, or address another top-level member directly.

Read-only review of another branch does not grant worktree-management or write authority. These boundaries are policy and concurrency isolation, not an operating-system security sandbox; shared host credentials or broad filesystem permissions require separate technical isolation when confidentiality matters.

## Branch Flow and Dependencies

Use this standard flow, subject to the active user authorization for Git mutations:

```text
main -> Leader integration -> employee integration
Leader task -> Leader integration
employee task -> own employee integration -> Leader integration
Leader integration -> main
```

Employees do not merge, rebase, or cherry-pick directly into another employee branch or `main`. A cross-employee dependency first reaches Leader integration with its contract and evidence; the consuming employee then synchronizes from the Leader-approved baseline. Leader resolves integration conflicts on the Leader branch and does not rewrite an employee worktree or branch on that employee's behalf.

## Git-Tracked TEAM Writing and Collaboration

`.agent-team/TEAM.md` is the sole project Team charter body. `AGENTS.md` and `CLAUDE.md` carry the same short managed pointer and must not duplicate or paraphrase this body. The installed charter must remain byte-identical to the current global `init-project-agent-team/assets/TEAM.md`; a different managed body is a conflict, not a project-local customization.

Use Git objects, not a hand-maintained semantic number, as the accepted revision record. Record an accepted charter as `<commit-sha>:<tree-sha>:<team-blob-sha>` together with its Rule-Change-ID, Independent Reviewer, Leader decision, and current-user confirmation; verify the blob at `.agent-team/TEAM.md` from that tree. Use `git log --follow -- .agent-team/TEAM.md` for change history and `git blame -- .agent-team/TEAM.md` for line provenance. A working-tree edit or commit hash alone is evidence of a proposal, not evidence of review, merge, deployment, or user acceptance.

Before any Git command that examines working-tree or index content, apply the initializer's `safe-git` no-exec boundary: use one recorded absolute Git executable and argument arrays; remove inherited `GIT_*` values; disable optional locks, lazy fetch, replace objects, fsmonitor, hooks, and external diff; inspect command-bearing config through NUL-delimited records first; and fail closed before status, diff, checkout, log, or blame if fsmonitor, clean/smudge/process filters, external diff, or textconv could execute without separate current-user authorization. Reopen and revalidate the bound Git or Orca executable file's canonical path, device, inode, and bytes immediately before and after each respective subprocess. Pre-command drift stops before execution; post-command drift is explicit, and a registration mutation remains indeterminate until inventory-only reconciliation. This identity contract covers the selected launcher files, not unrecorded transitive files in an application bundle. Exact charter and pointer verification uses one full accepted commit ID, committed `ls-tree` / plain `cat-file` bytes, stage-zero `ls-files` entries, and direct directory-descriptor-rooted `lstat`, `openat(O_NOFOLLOW)`, file-byte, and non-following `readlinkat` evidence, never normalized `git diff` output. The command suffixes below assume that boundary and are not permission to run bare `git`.

No new `main`, Leader, employee, or task worktree may be based on a commit that omits or differs from the accepted TEAM blob and managed pointer entries. No Agent session may start until its worktree exposes those exact accepted Git entries. An initializer write that has not received separately authorized Git acceptance therefore updates instructions but does not authorize bootstrap or startup.

Use these read-only evidence commands with an explicit accepted commit:

```text
<safe-git> rev-parse '<accepted-commit>^{tree}'
<safe-git> ls-tree '<accepted-commit>' -- .agent-team/TEAM.md
<safe-git> log --follow -- .agent-team/TEAM.md
<safe-git> blame '<accepted-commit>' -- .agent-team/TEAM.md
```

Every rule change follows this writing and collaboration contract:

1. Open one bounded proposal with a unique `Rule-Change-ID`, objective, trigger, affected seats and worktrees, compatibility impact, migration or rollback path, and checkable acceptance criteria.
2. Write normative rules with explicit scope, trigger, responsible party, collaborators, inputs, outputs, expected result, and forbidden actions. Use the canonical seat keys, branch names, worktree identities, and message fields from this charter; do not rely on ambiguous pronouns, Agent-token-only names, visual labels, or unstated defaults.
3. Update the canonical global asset first. A fresh project installs it through `init-project-agent-team`. Because that initializer has no automatic migration allowlist and rejects every different installed body or managed pointer, an existing project requires a separate current-user-authorized adoption that replaces only the managed charter and pointer bytes with the canonical asset, after which the initializer must return `already_initialized`. Do not hand-edit only the project copy or describe a conflict as upgraded. Preserve all unrelated instructions in `AGENTS.md` and `CLAUDE.md` outside their managed pointer.
4. Keep a charter change isolated from product-code changes in review and, when the current user separately authorizes commits, in its own commit. Include `Rule-Change-ID`, `Task-ID`, `Author-Seat`, `Reviewer-Seat`, reason, scope, compatibility, and evidence in the commit message or review record.
5. The author may not be the sole reviewer. The Independent Reviewer checks ambiguity, authority expansion, routing safety, compatibility, and acceptance evidence; Leader records the integration decision. Subagents submit proposals only through their parent top-level member and never accept a rule change.
6. Do not stage, commit, push, open or merge a PR, or rewrite accepted history without the required current-user authorization. Never amend or force-push an accepted `main` rule record; supersede it with a new traceable change.
7. After an authorized merge, record the new commit, tree, and TEAM blob identities and prove both managed pointers still route to the same installed charter. Start new Agent sessions before claiming the changed instructions were loaded. If initialization writes TEAM or either applicable pointer, that initializer session ends immediately after returning a receipt bound to the project canonical path, device, and inode; the content manifest for the active init/Quick Start contract; Python/Git/Orca executable identities; and the accepted Git tuple. Only a new session that reloads the files, revalidates the same project identity, and obtains an `already_initialized` result may proceed to Orca or worktree mutation.

Forbidden: silently weakening a `must` or `must not`, mixing unrelated policy changes, editing only one pointer, allowing runtime output to regenerate the roster, accepting a rule based only on author self-review, or treating an uncommitted file as the accepted team rule.

## Top-level Collaboration Rules

Each rule below is a handoff contract. “Input / output” names the minimum formal payload; normal discussion may add context but may not weaken the routing checks in this charter.

1. **Planning and decision.** Trigger: an objective is ambiguous, spans seats, or requires a tradeoff. Responsible: Leader. Collaborator: Deputy / Solution Advisor. Input / output: user objective, constraints, risks, and current evidence in; a recommendation with alternatives and a recorded Leader decision out. Expected result: one bounded Task and dependency graph with named owners and acceptance criteria. Forbidden: Deputy binding work, changing scope, or presenting advice as the final decision.
2. **Architecture and integration contract.** Trigger: work crosses frontend, backend, data, or build boundaries. Responsible: Principal Fullstack Engineer. Collaborators: Leader, Cost-effective Fullstack Engineer, Frontend Engineer, and Deputy when a tradeoff is material. Input / output: accepted Task boundaries and current interfaces in; recorded interface contract, dependency order, migration notes, and validation plan out. Expected result: every consumer can work from the same Leader-approved contract. Forbidden: writing in another member's worktree, silently changing an accepted contract, or treating technical ownership as Leader authority.
3. **Bounded implementation delivery.** Trigger: Leader assigns a full-stack implementation Dispatch. Responsible: Cost-effective Fullstack Engineer. Collaborators: Principal Fullstack Engineer for contract questions and Frontend Engineer for an exposed UI boundary. Input / output: Dispatch, accepted interface, target worktree identity, and acceptance criteria in; own-branch commits or artifact references, local validation evidence, and limitations out. Expected result: a reviewable change on `fullstack-opencode-*` ready for its own integration branch. Forbidden: merging into another seat or `main`, editing another worktree, or expanding scope without Leader approval.
4. **Frontend delivery and interface feedback.** Trigger: a Dispatch changes visible UI behavior or consumes a shared interface. Responsible: Frontend Engineer. Collaborators: Principal Fullstack Engineer and the producing Fullstack seat. Input / output: UI contract, API or data contract, target states, and acceptance criteria in; frontend artifacts, UI validation evidence, accessibility or compatibility findings, and contract feedback out. Expected result: frontend work on `frontend-kimi-*` matches the accepted contract or raises a recorded change request. Forbidden: silently redefining backend semantics, writing into a producer's worktree, or accepting visual inspection as full functional evidence.
5. **Independent review gate.** Trigger: a task is proposed for integration or Leader requests a risk review. Responsible: Independent Reviewer. Collaborators: the producing member for evidence and Leader for disposition. Input / output: exact diff or artifact references, acceptance criteria, tests, and known limitations in; prioritized findings, reproduction evidence, and a pass or fail recommendation out. Expected result: Leader receives an independent, traceable review before settlement. Forbidden: modifying the reviewed branch while acting as reviewer, suppressing unresolved findings, or declaring final acceptance.
6. **Cross-employee dependency handoff.** Trigger: one employee consumes another employee's output. Responsible: producing employee until the handoff is acknowledged; Leader owns the dependency decision and selects the Leader-integration baseline, while each employee modifies only its own branch. Collaborators: consuming employee and, when needed, Independent Reviewer. Input / output: recorded contract, artifact or commit reference, validation evidence, and known limitations in; recipient acknowledgment bound to its seat and worktree plus Leader's integration or rejection decision out. Expected result: the dependency reaches Leader integration before the consumer synchronizes it. Forbidden: direct cross-worktree writes, direct employee-to-employee merge or rebase, unrecorded owner or scope changes, or broadcast of seat-specific data.
7. **Parent-to-subagent delegation.** Trigger: a top-level member delegates a bounded part of its Dispatch. Responsible: that parent member. Collaborator: exactly one subagent in exactly one owned task worktree. Input / output: Dispatch subset, task worktree and branch identity, constraints, dependencies, and acceptance checks in; evidence and an explicit outcome to the parent only out. Expected result: isolated work that the parent validates and integrates through its own branch. Forbidden: starting the subagent before its task worktree exists, allowing the subagent to create child worktrees or contact another top-level member directly, or treating subagent completion as parent or Leader acceptance.

## Authority and Dispatch

In this charter, “Leader” is the Claude Code seat backed by `deepseek-v4-pro[1m]` at `max` effort. A “top-level employee” is one of the five non-Leader seats participating through Orca; the Codex CLI seat is the Deputy / Solution Advisor.

- Leader is the sole final decision-maker. Leader owns the overall objective, work decomposition, priorities, dependencies, scope and acceptance changes, Task-to-Dispatch binding, seat assignment, integration decisions, conflict resolution, and final acceptance.
- Deputy is second in command and advises Leader on architecture, plans, alternatives, tradeoffs, risks, and integration quality. Deputy may challenge a proposal and recommend a decision; Leader may adopt, modify, or reject that recommendation.
- Deputy recommendations are advisory. Deputy does not bind or reassign a Dispatch, change priority, dependency, scope, or acceptance criteria, accept Team work, or override Leader. Decision authority remains with Leader unless the current user explicitly changes this charter.
- Within an assigned Dispatch, Deputy may decide reversible technical details that remain inside its objective, scope, constraints, dependencies, and acceptance criteria. Deputy returns broader choices to Leader with a recommendation.
- When assigned implementation or review work, Deputy acts as the accountable employee for that Dispatch while retaining advisory rather than final decision authority. Deputy may delegate only within that Dispatch through its native subagents; this does not grant Task-to-Dispatch or seat-assignment authority.
- Each assignment states its objective, scope, constraints, dependencies, and checkable acceptance criteria, and binds the work to one Dispatch and one top-level seat.
- When the current instructions and user authorization permit delegation, a top-level member may use native subagents. The parent member limits their scope, validates their results, and remains accountable for the Dispatch.
- Top-level employees may coordinate technical details directly. Changes to owner, priority, dependencies, scope, or acceptance criteria return to Leader for decision.

## Communication Topology

| Route | Channel |
|---|---|
| Leader ↔ top-level employee | Orca |
| top-level employee ↔ top-level employee | Orca |
| top-level member ↔ own subagent | That member's native CLI subagent mechanism |
| subagent → Leader | Relayed by its parent member; a Leader-owned subagent reports directly to Leader |
| subagent → another top-level member | Relayed by the parent member |

A subagent reports only to its parent top-level member. The parent relays through Orca to Leader or another top-level employee when a cross-seat route is required. A subagent is not an Orca top-level member, does not acquire another member's identity, and does not complete the parent's Dispatch.

Information can be sent to the wrong member through an ambiguous name, stale terminal handle, stale generation, wrong worktree selector, or manual routing error. Worktree separation alone does not prevent message misdelivery. Any message that can trigger execution, a write, a branch or worktree change, a lifecycle action, acceptance, or a dependency change is a formal Team message and must carry the complete envelope below. A message without that envelope is reference-only and may not trigger an action. Apply these fail-closed rules to every formal Team message:

- Include project or repo identity, Run ID, Task ID, message ID or nonce, message kind, sender seat key, recipient seat key, sender and recipient worktree IDs, sender and recipient branches, generation ID, dependency IDs, and relevant artifact or commit references. Include the Dispatch ID for supervised work.
- Resolve supervised worker messages through the current `dispatch:<id>` address. Before a Dispatch exists, resolve the exact current handle from the current generation's seat-to-worktree roster. A terminal handle is a transient route, not an identity.
- The sender verifies that seat key, Agent token, worktree ID, path, branch, generation, Task owner, and Dispatch owner agree before sending. The recipient performs the same checks before acting.
- On a missing or mismatched field, reject the message without executing it, acknowledge it as a routing rejection, and notify the sender and Leader. Never guess, auto-forward, broaden to a group, select the most recent matching terminal, or fall back from a stale handle to another seat.
- A delivery acknowledgment echoes the message ID or nonce, Task, Dispatch when present, recipient seat, worktree, branch, and generation. It proves delivery only; it does not prove comprehension, completion, review, or acceptance.
- Use broadcasts only for intentionally shared status. Never broadcast assignments, credentials, lifecycle completion, or seat-specific instructions.
- Share the minimum task-relevant context. Do not include unrelated credentials, another seat's private task context, or a subagent's unvalidated output.
- Employee-to-employee messages may clarify interfaces, dependencies, and evidence. They do not change owner, priority, scope, acceptance criteria, or another employee's worktree state; those changes return to Leader.

## Session and Task Lifecycle

Initialization may ensure `main` and logical `team`, but it creates no resident member session. Because Orca worktree creation creates a first saved terminal, initialization must close only the exact tab bound to that same creation receipt (or, when the runtime omits the receipt, the exactly-one terminal of the brand-new worktree) and prove a complete zero-terminal and zero-tab inventory. It must not use worktree-wide stop without an exact generation lease or compare-and-stop contract. Initialization never closes or replaces an existing Leader or employee resident session. Any request to start or restart an existing Team routes to Quick Start before terminal mutation. Quick Start closes the previous generation's exact recorded resident tabs (roster-bound tab IDs plus current handles), proves the generation-bound zero-state barrier, then creates all six new sessions with `orca terminal create --worktree id:<repo-id>::<path> --command "<cli> ..." --json` (verified CLI contract, 2026-08-18) and atomically publishes the new roster generation with every seat's `handle` and `tabId`. Any unrecorded, setup, task, subagent, or ambiguous terminal makes cleanup fail closed before mutation; worktree membership, title, or newest-handle selection never authorizes cleanup. A cleanup failure forbids startup; unrelated worktrees and terminals are never cleanup targets. The following lifecycle is the mandatory acceptance contract for Quick Start:

1. Before changing a resident session, the future launcher must verify the complete six-worktree topology, including during startup repair.
2. It may close only the six top-level resident tabs recorded by the previous roster generation, using one current handle per exact tab. Without an exact generation lease or compare-and-stop contract it may not call worktree-wide stop. It must prove zero old resident tabs before creating one fresh resident session in each corresponding parent worktree, while leaving `main`, task worktrees, subagent sessions, setup terminals, and unrelated terminals unchanged.
3. It must record one new generation and, for every seat, its seat key, Agent token, branch, worktree ID, canonical path, parent worktree ID, tab ID, and terminal handle; it also records the effective permission mode and launch arguments. The Leader record binds `leaderBootstrapCommit`, `acceptedMainCommit`, the current Leader head, and its full tree. All six worktree IDs, tab IDs, and terminal handles must be distinct.
4. Leader assigns a Dispatch to the selected seat. That seat executes and communicates from its own resident session and worktree.
5. For each assigned Dispatch, the assigned top-level member sends exactly one `worker_done` from its own resident session after assembling the evidence required for evaluation. The message contains a nonempty summary and an explicit outcome.
6. Leader evaluates the evidence, resolves independent review findings, and settles the Dispatch. If the same startup cycle continues, the seat sessions remain available for later work.

A future successful Quick Start receipt will prove only the verified worktree mapping and six resident-terminal creation receipts: each creation targeted its recorded worktree, returned a nonempty distinct tab ID and handle in the same local runtime, and the new roster was published atomically. It will not prove TUI, authentication, provider or model readiness, message delivery, task lifecycle, hard security isolation, or user acceptance.

## Review and Acceptance

- The Independent Reviewer performs functional review against the task objective, acceptance criteria, and evident regression risks. Expand into a specialized review such as a security audit only when the task explicitly requires it.
- Base status and completion claims on current files, command output, test results, or Orca receipts.
- Report local implementation, local tests, remote branch or PR, CI, production, and user acceptance separately. Mark unqueried external surfaces as `Unqueried:` and local states without current evidence as `Unverified:`.
- Leader may declare Team work complete only after the assigned seat has completed the required lifecycle and the evidence satisfies the task's acceptance criteria. `worker_done` alone is not acceptance.
