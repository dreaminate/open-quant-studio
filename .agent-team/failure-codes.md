# Team tooling failure code table

Every code emitted by the repo-local team tools, its exit status, meaning, and
the next command. The contract: any missing precondition fails closed with one
of these codes — a failure with a next step is part of the success path, not a
dead end.

## adopt-team-charter

| Code | Exit | Meaning | Next command |
|---|---|---|---|
| `preview_ready` | 0 | Diff summary, write targets, backup plan, and confirm digest produced; adoption awaits user confirmation | `adopt-team-charter apply --confirm-digest <hex>` |
| `preview_no_changes` | 0 | Charter and pointers already canonical | `adopt-team-charter check` |
| `preview_missing_charter` | 0 | No charter exists; adoption does not create charters | `init-project-agent-team` (fresh-project install) |
| `adopted` | 0 | Charter and pointers replaced; backups and meta written | End this session; new session: `adopt-team-charter check` |
| `already_adopted` | 0 | Re-run found nothing to change | `adopt-team-charter check` |
| `charter_current` | 0 | Charter bytes, meta, and launcher minimum all consistent | `team doctor --json` |
| `charter_current_meta_missing` | 5 | Charter bytes canonical but charter-meta.json missing | `adopt-team-charter preview`, then `apply` |
| `charter_mismatch` | 5 | Installed charter differs from the canonical asset | `adopt-team-charter preview` |
| `charter_missing` | 5 | Charter missing or a symlink | `adopt-team-charter preview` |
| `confirm_digest_mismatch` | 9 | State changed between preview and apply | Re-run `preview`, obtain fresh user confirmation |
| `confirm_digest_required` | 2 | apply invoked without a preview digest | `adopt-team-charter preview` |
| `charter_missing_apply_conflict` | 9 | apply refused: no existing charter to adopt | `init-project-agent-team` (fresh-project install) |
| `postcondition_failed` | 9 | Replacement result failed byte verification | Inspect the reported path, then re-run `preview` |
| `invalid_project` | 9 | Project, target, or boundary check failed | Read the reported reason, fix, re-run |

## provision / deprovision

| Code | Exit | Meaning | Next command |
|---|---|---|---|
| `preview_ready` | 0 | Topology plan + paths digest produced; creation awaits user confirmation | `provision run --confirm-paths-digest <hex>` |
| `path_conflict` | 9 | A planned path already exists or is occupied | Resolve the listed conflict, re-run `preview` |
| `topology_provisioned` | 0 | All six worktrees verified; roster published; no agent started | `quickstart` |
| `main_attach_pending` | 7 | `main` branch exists with no attached worktree; atomic attach primitive absent (pending placeholder) | Wait for the placeholder to resolve; or a separately authorized Git workflow |
| `leader_branch_baseline_unverified` | 7 | Leader branch exists without bound creation provenance | Re-run with `--leader-bootstrap-commit <sha>` from a prior receipt |
| `team_create_cli_pending` | 7 | Orca CLI cannot safely check out the exact existing Leader branch (pending placeholder) | Wait for CLI support; do not bypass |
| `employee_parent_create_cli_pending` | 7 | Employee parent creation through Orca CLI unverified (pending placeholder) | Wait for CLI verification; do not bypass |
| `orca_runtime_unavailable` | 7 | Orca runtime not ready or status failed | Open the local Orca app (current-user authorization), then re-run |
| `orca_repo_not_registered` | 7 | Project not registered in the local Orca runtime | `init-project-agent-team` for this project first |
| `rules_object_not_accepted` | 7 | Creation requires an accepted commit plus governance evidence | Supply `--accepted-commit` and the governance record |
| `main_worktree_create_failed` / `leader_branch_create_failed` | 7 | A git creation command failed | Inspect the raw error, reconcile, re-run `preview` |
| `git_ref_drift` | 7 | A ref moved before mutation | Reconcile the moved ref before retrying |
| `git_ref_changed_after_mutation` | 7 | A ref moved during mutation | Inventory-only reconciliation before any retry |
| `confirm_digest_mismatch` | 7 | Topology plan changed since preview | Re-run `preview` |
| `confirm_digest_required` | 2 | run invoked without a preview digest | `provision preview` |
| `deprovisioned` | 0 | Roster-listed clean worktrees removed; branches kept | `git branch -d` only under separate authorization |
| `deprovisioned_branches_kept` | 0 | Worktrees removed; branch removal left to an authorized git command | As above |
| `deprovision_requires_confirm` | 8 | Removal requires `--confirm` after reviewing targets | Re-run with `--confirm` |
| `dirty_worktree_refused` | 8 | One or more target worktrees have uncommitted changes; removal refused | Commit/stash in that worktree, then re-run |
| `roster_missing` / `roster_unreadable` / `roster_empty` | 8 | No roster to derive removal targets from | `provision preview` or repair roster.json |
| `git_status_failed` / `worktree_remove_failed` | 8 | A git status/remove command failed | Inspect the raw error, reconcile |
| `invalid_project` | 9 | Boundary or identity check failed (includes `git_inspection_failed`, `git_config_drift`, `git_read_side_effect_authorization_required`, `checkout_side_effect_authorization_required`) | Read the reported reason; the helper must not be bypassed |

## roster validator (`team_roster.py validate`)

| Code | Exit | Meaning | Next command |
|---|---|---|---|
| `roster_valid` | 0 | Schema, six seats, generations, parents, fingerprints all valid | `quickstart` |
| `roster_invalid` | 5 | One or more schema violations (listed) | Fix roster.json through the provisioner or an explicitly confirmed human edit |
| `roster_unreadable` | 9 | File missing or not valid JSON | `provision preview` |

## quickstart

| Code | Exit | Meaning | Next command |
|---|---|---|---|
| `start_session_cli_pending` | 7 | All preflights passed; session-creation CLI surface unverified (pending placeholder) | Wait for CLI verification; do not bypass |
| `charter_mismatch` | 7 | Charter not canonical | `adopt-team-charter preview` |
| `charter_current_meta_missing` | 7 | Charter canonical but meta missing | `adopt-team-charter preview`, then `apply` |
| `team_worktree_topology_required` | 7 | Roster missing/invalid or worktree directories missing | `provision preview` |
| `roster_unreadable` | 7 | roster.json unreadable | `provision preview` |
| `claude_auto_mode_required` | 7 | Effective Claude permission default is not exactly `auto` | Fix `permissions.defaultMode` to `auto`, re-run |
| `claude_settings_unreadable` | 7 | Claude settings file unreadable | Repair the settings file, re-run |
| `orca_runtime_unavailable` | 7 | Orca runtime not ready | Open the local Orca app, re-run |
| `invalid_project` | 9 | Boundary or identity check failed | Read the reported reason |

## Pending placeholder registry

Placeholders retained from the canonical initializer contract; each requires a
separately reviewed implementation plus a disposable-repository test against
the current public CLI before it may be replaced:

| Placeholder | Blocking code | Resolution criteria |
|---|---|---|
| `<GIT_ATTACH_EXISTING_MAIN_BRANCH_TO_WORKTREE_AT_EXPECTED_OID_PENDING_ATOMIC_SUPPORT>` | `main_attach_pending` | A real Git ref transaction or repository-wide writer lease across expected-OID assertion and worktree attachment |
| `<ORCA_CREATE_TEAM_ON_EXACT_EXISTING_LEADER_BRANCH_PENDING_CLI_SUPPORT>` | `team_create_cli_pending` | Confirmed from `orca worktree create --help` and a disposable-repo test: exact repo ID, exact `refs/heads/leader-claude-integration` checkout, no Orca parent, disclosed checkout side effects, full creation receipt, no silent branch prefix/suffix |
| `<ORCA_CREATE_EMPLOYEE_PARENT_PENDING_CLI_VERIFICATION>` | `employee_parent_create_cli_pending` | Same evidence bar for employee parent creation with Leader-parent lineage binding |
| `<ORCA_START_SEAT_SESSION_PENDING_CLI_VERIFICATION>` | `start_session_cli_pending` | Confirmed CLI surface that starts one seat session in a recorded target worktree and returns distinct tab IDs and terminal handles |
