#!/usr/bin/env python3
"""Provision or deprovision the six-seat Agent Team worktree topology.

Subcommands:

- `preview`: read-only topology plan. Classifies `main`, the six integration
  branches, and every pre-existing worktree; shows every absolute path that
  would be created; emits a `pathsDigest` binding the plan. Zero mutation.
- `run`: executes the plan bound to a user-approved `pathsDigest`. Phases run
  in order and each stops the pipeline on its own failure code. Known gaps
  fail closed with pending placeholders (never bypassed):
  - existing `main` branch with no attached worktree -> `main_attach_pending`;
  - `team` / Leader parent creation -> `team_create_cli_pending`;
  - employee parent creation -> `employee_parent_create_cli_pending`.
- `deprovision`: removes only worktrees listed in `roster.json`. Refuses any
  worktree with uncommitted changes (`dirty_worktree_refused`) and requires
  `--confirm`; branches are never removed by default.

Normative rules live in `.agent-team/TEAM.md`; this helper implements only
the creation/verification mechanics and the receipt output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import team_common as tc  # noqa: E402

SEATS: tuple[dict[str, str], ...] = (
    {"key": "leader-claude", "branch": "leader-claude-integration"},
    {"key": "advisor-codex", "branch": "advisor-codex-integration"},
    {"key": "fullstack-opencode", "branch": "fullstack-opencode-integration"},
    {"key": "review-opencode", "branch": "review-opencode-integration"},
    {"key": "principal-fullstack-claudex", "branch": "principal-fullstack-claudex-integration"},
    {"key": "frontend-kimi", "branch": "frontend-kimi-integration"},
)
SEAT_KEYS = tuple(seat["key"] for seat in SEATS)
SEAT_BRANCHES = tuple(seat["branch"] for seat in SEATS)

# Documented pending placeholders. Replacing either requires a separately
# reviewed implementation plus a disposable-repository test against the
# current public CLI; until then these stop the pipeline, fail closed.
GIT_ATTACH_MAIN_PLACEHOLDER = (
    "<GIT_ATTACH_EXISTING_MAIN_BRANCH_TO_WORKTREE_AT_EXPECTED_OID_PENDING_ATOMIC_SUPPORT>"
)
ORCA_CREATE_TEAM_PLACEHOLDER = (
    "<ORCA_CREATE_TEAM_ON_EXACT_EXISTING_LEADER_BRANCH_PENDING_CLI_SUPPORT>"
)
ORCA_CREATE_EMPLOYEE_PLACEHOLDER = (
    "<ORCA_CREATE_EMPLOYEE_PARENT_PENDING_CLI_VERIFICATION>"
)


def parse_worktree_inventory(git: tc.SafeGit) -> dict[str, dict[str, Any]]:
    """Parse `git worktree list --porcelain -z` into a path-keyed inventory."""
    code, stdout, stderr = git.run("worktree", "list", "--porcelain", "-z")
    if code != 0:
        raise tc.TeamToolError(
            f"git_worktree_list_failed: exited {code}: {stderr.decode('utf-8', 'replace').strip()}"
        )
    if stdout.endswith(b"\0\0"):
        stdout = stdout[:-1]
    inventory: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    for record in stdout.split(b"\0"):
        if record.startswith(b"worktree "):
            path = record[len(b"worktree ") :].decode("utf-8", "replace")
            current = {"path": path, "head": None, "branch": None}
            inventory[path] = current
        elif record.startswith(b"HEAD "):
            if current is not None:
                current["head"] = record[len(b"HEAD ") :].decode("ascii")
        elif record.startswith(b"branch "):
            if current is not None:
                current["branch"] = record[len(b"branch ") :].decode("ascii")
        elif record == b"":
            current = None
        elif current is not None:
            raise tc.TeamToolError("git_worktree_list_unparsable: unknown porcelain record")
    if any(entry["path"] == "" for entry in inventory.values()):
        raise tc.TeamToolError("git_worktree_list_unparsable: truncated inventory")
    return inventory


def ref_exists(git: tc.SafeGit, ref: str) -> bool:
    code, _, stderr = git.run("show-ref", "--verify", "--quiet", ref)
    if code == 0:
        return True
    if code == 1:
        return False
    raise tc.TeamToolError(
        f"git_ref_probe_failed: show-ref {ref} exited {code}: "
        f"{stderr.decode('utf-8', 'replace').strip()}"
    )


def resolve_ref(git: tc.SafeGit, ref: str) -> str:
    code, stdout, stderr = git.run("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
    if code != 0:
        raise tc.TeamToolError(
            f"git_rev_parse_failed: {ref} exited {code}: {stderr.decode('utf-8', 'replace').strip()}"
        )
    resolved = stdout.decode("ascii").strip()
    if not resolved or "\n" in resolved:
        raise tc.TeamToolError(f"git_rev_parse_failed: {ref} did not resolve to one full commit")
    return resolved


def orca_status(orca_cli: str) -> dict[str, Any]:
    code, stdout, stderr = tc.orca_run(orca_cli, "status", "--json")
    if code != 0:
        return {
            "ready": False,
            "code": "orca_status_failed",
            "exit": code,
            "stderr": stderr.decode("utf-8", "replace").strip()[:500],
        }
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {"ready": False, "code": "orca_status_invalid_json", "error": str(exc)}
    return {"ready": True, "code": "orca_ready", "payload": payload}


def orca_repo_listed(orca_cli: str, project_path: str) -> tuple[bool, Any]:
    code, stdout, _ = tc.orca_run(orca_cli, "repo", "list", "--json")
    if code != 0:
        return False, {"code": "orca_repo_list_failed", "exit": code}
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return False, {"code": "orca_repo_list_invalid_json", "error": str(exc)}
    repos = payload if isinstance(payload, list) else payload.get("repos", [])
    for repo in repos:
        if repo.get("path") == project_path or repo.get("canonicalPath") == project_path:
            return True, {"repoId": repo.get("id"), "worktreeId": repo.get("worktreeId")}
    return False, {"code": "orca_repo_not_found", "reposListed": len(repos)}


def classify_main(git: tc.SafeGit) -> dict[str, Any]:
    inventory = parse_worktree_inventory(git)
    main_worktrees = [entry for entry in inventory.values() if entry["branch"] == "refs/heads/main"]
    branch_exists = ref_exists(git, "refs/heads/main")
    if len(main_worktrees) > 1:
        raise tc.TeamToolError("duplicate main worktrees detected")
    if main_worktrees:
        return {"state": "existing_worktree", "worktree": main_worktrees[0]}
    if branch_exists:
        return {"state": "existing_unattached_branch", "worktree": None}
    return {"state": "absent_branch", "worktree": None}


def classify_seat_branches(git: tc.SafeGit) -> dict[str, dict[str, Any]]:
    result = {}
    inventory = parse_worktree_inventory(git)
    for seat in SEATS:
        branch = seat["branch"]
        worktrees = [
            entry for entry in inventory.values() if entry["branch"] == f"refs/heads/{branch}"
        ]
        if len(worktrees) > 1:
            raise tc.TeamToolError(f"duplicate worktrees on branch {branch}")
        result[seat["key"]] = {
            "branch": branch,
            "branchExists": ref_exists(git, f"refs/heads/{branch}"),
            "worktree": worktrees[0] if worktrees else None,
        }
    return result


def build_plan(
    git: tc.SafeGit, base_dir: Path, accepted_commit: str | None, leader_bootstrap_commit: str | None
) -> dict[str, Any]:
    main_class = classify_main(git)
    seats = classify_seat_branches(git)
    main_commit = None
    if main_class["state"] == "existing_worktree":
        main_commit = main_class["worktree"]["head"]
    elif ref_exists(git, "refs/heads/main"):
        main_commit = resolve_ref(git, "refs/heads/main")
    if accepted_commit is not None and main_commit is not None and main_commit != accepted_commit:
        raise tc.TeamToolError(
            f"accepted commit {accepted_commit} does not match current main {main_commit}"
        )

    planned_paths: dict[str, str] = {"main": str(base_dir / "main")}
    for seat in SEATS:
        planned_paths[seat["key"]] = str(base_dir / seat["key"])

    existing_paths = set(parse_worktree_inventory(git).keys())
    conflicts = [key for key, path in planned_paths.items() if Path(path).exists() or path in existing_paths]
    path_conflicts = [
        key for key, path in planned_paths.items() if Path(path).exists() and path not in existing_paths
    ]

    employee_keys = [seat["key"] for seat in SEATS[1:]]
    plan: dict[str, Any] = {
        "ok": True,
        "code": "preview_ready",
        "project": tc.directory_identity(git.repo),
        "baseDir": str(base_dir),
        "main": {
            "state": main_class["state"],
            "branch": "main",
            "commit": main_commit,
            "existingWorktreePath": (
                main_class["worktree"]["path"] if main_class["worktree"] else None
            ),
            "plannedPath": planned_paths["main"],
            "action": (
                "reuse_existing"
                if main_class["state"] == "existing_worktree"
                else ("attach_pending" if main_class["state"] == "existing_unattached_branch" else "create_branch_and_worktree")
            ),
            "placeholder": GIT_ATTACH_MAIN_PLACEHOLDER
            if main_class["state"] == "existing_unattached_branch"
            else None,
        },
        "seats": {
            key: {
                "branch": seats[key]["branch"],
                "branchExists": seats[key]["branchExists"],
                "plannedPath": planned_paths[key],
                "worktree": seats[key]["worktree"],
                "existingWorktreePath": (
                    seats[key]["worktree"]["path"] if seats[key]["worktree"] else None
                ),
                "isLeader": key == SEATS[0]["key"],
            }
            for key in SEAT_KEYS
        },
        "plannedCreates": {
            "main": main_class["state"] == "absent_branch",
            "leaderBranch": not seats[SEATS[0]["key"]]["branchExists"],
            "teamWorktree": seats[SEATS[0]["key"]]["worktree"] is None,
            "employeeWorktrees": [
                key for key in employee_keys if seats[key]["worktree"] is None
            ],
        },
        "conflicts": sorted(conflicts),
        "pathConflicts": sorted(path_conflicts),
        "unrelatedWorktreesPreserved": sorted(
            path for path in existing_paths if path not in planned_paths.values()
        ),
        "acceptedCommit": accepted_commit,
        "leaderBootstrapCommit": leader_bootstrap_commit,
        "firstBlockingCode": expected_first_blocking_code(main_class, seats),
        "nextStep": "review the plan, confirm the paths, then run: provision run --confirm-paths-digest <pathsDigest>",
    }
    if plan["conflicts"]:
        plan["ok"] = False
        plan["code"] = "path_conflict"
        return plan
    digest_payload = {key: value for key, value in plan.items() if key != "pathsDigest"}
    plan["pathsDigest"] = tc.bytes_sha256(
        json.dumps(digest_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    return plan


def expected_first_blocking_code(
    main_class: dict[str, Any], seats: dict[str, dict[str, Any]]
) -> str | None:
    """The first failure code a `run` will hit, for preview navigation."""
    if main_class["state"] == "existing_unattached_branch":
        return "main_attach_pending"
    leader = seats[SEATS[0]["key"]]
    if leader["branchExists"] and leader["worktree"] is None:
        return "leader_branch_baseline_unverified"
    if leader["worktree"] is None:
        return "team_create_cli_pending"
    employee_keys = [seat["key"] for seat in SEATS[1:]]
    if any(seats[key]["worktree"] is None for key in employee_keys):
        return "employee_parent_create_cli_pending"
    return None


def run_provision(
    project: Path,
    base_dir: Path,
    git_cli: str,
    orca_cli: str,
    accepted_commit: str | None,
    leader_bootstrap_commit: str | None,
    confirm_paths_digest: str,
    roster_path: Path,
) -> dict[str, Any]:
    """Bind the user-approved preview, then walk the phase pipeline.

    The confirm digest is checked against the initial plan only; after a
    mid-run mutation the pipeline re-classifies from live inventory and the
    same fail-closed phases continue.
    """
    git = tc.SafeGit(git_cli, project)
    git.inspect_config()
    git.require_clean_read()
    initial_plan = build_plan(git, base_dir, accepted_commit, leader_bootstrap_commit)
    if initial_plan.get("pathsDigest") != confirm_paths_digest:
        return {
            "ok": False,
            "code": "confirm_digest_mismatch",
            "message": "The topology plan changed since it was confirmed. Re-run preview.",
            "expectedPathsDigest": confirm_paths_digest,
            "observedPathsDigest": initial_plan.get("pathsDigest"),
            "changesApplied": False,
        }
    return run_phases(
        git,
        base_dir,
        orca_cli,
        accepted_commit,
        leader_bootstrap_commit,
        roster_path,
        mutations=[],
        unrelated_before=initial_plan["unrelatedWorktreesPreserved"],
    )


def run_phases(
    git: tc.SafeGit,
    base_dir: Path,
    orca_cli: str,
    accepted_commit: str | None,
    leader_bootstrap_commit: str | None,
    roster_path: Path,
    mutations: list[dict[str, Any]],
    unrelated_before: list[str],
) -> dict[str, Any]:
    """One walk of the phase pipeline against fresh live inventory."""

    def stop(code: str, message: str) -> dict[str, Any]:
        return stop_plan(git, base_dir, mutations, unrelated_before, code, message)

    plan = build_plan(git, base_dir, accepted_commit, leader_bootstrap_commit)

    # Phase 1: main release worktree.
    if plan["main"]["state"] == "existing_unattached_branch":
        return stop(
            "main_attach_pending",
            "The main branch exists but no worktree checks it out. Attaching it requires an "
            "atomic expected-OID primitive that git does not provide; retained pending "
            "placeholder, zero mutation.",
        )
    if plan["main"]["state"] == "absent_branch":
        if accepted_commit is None:
            return stop(
                "rules_object_not_accepted",
                "Creating the main branch requires an accepted bootstrap commit "
                "(--accepted-commit) with its governance evidence.",
            )
        git.require_clean_checkout()
        git.check_config_snapshot()
        main_path = plan["main"]["plannedPath"]
        code, _, stderr = git.run("worktree", "add", "-b", "main", main_path, accepted_commit)
        if code != 0:
            return stop(
                "main_worktree_create_failed",
                f"git worktree add exited {code}: {stderr.decode('utf-8', 'replace').strip()}",
            )
        if resolve_ref(git, "refs/heads/main") != accepted_commit:
            return stop(
                "git_ref_changed_after_mutation",
                "main moved during worktree creation; reconcile before retrying.",
            )
        mutations.append(
            {
                "kind": "main_branch_and_worktree_created",
                "path": main_path,
                "baseCommit": accepted_commit,
                "commandSucceeded": True,
            }
        )
        return run_phases(
            git, base_dir, orca_cli, accepted_commit, leader_bootstrap_commit, roster_path,
            mutations, unrelated_before,
        )

    # Phase 2: Leader integration branch.
    leader_key = SEATS[0]["key"]
    leader_branch = SEATS[0]["branch"]
    leader_seat = plan["seats"][leader_key]
    if not leader_seat["branchExists"]:
        if accepted_commit is None:
            return stop(
                "rules_object_not_accepted",
                "Creating the Leader branch requires an accepted main commit (--accepted-commit).",
            )
        git.require_clean_read()
        git.check_config_snapshot()
        main_commit_now = resolve_ref(git, "refs/heads/main")
        if accepted_commit != main_commit_now:
            return stop("git_ref_drift", f"main moved before Leader branch creation: {main_commit_now}")
        code, _, stderr = git.run("branch", leader_branch, accepted_commit)
        if code != 0:
            return stop(
                "leader_branch_create_failed",
                f"git branch exited {code}: {stderr.decode('utf-8', 'replace').strip()}",
            )
        if resolve_ref(git, f"refs/heads/{leader_branch}") != accepted_commit:
            return stop(
                "git_ref_changed_after_mutation",
                "Leader branch moved during creation; reconcile before retrying.",
            )
        mutations.append(
            {
                "kind": "leader_branch_created",
                "branch": leader_branch,
                "leaderBootstrapCommit": accepted_commit,
                "commandSucceeded": True,
            }
        )
        return run_phases(
            git, base_dir, orca_cli, accepted_commit, accepted_commit, roster_path,
            mutations, unrelated_before,
        )
    if leader_seat["worktree"] is None:
        if leader_bootstrap_commit is None:
            return stop(
                "leader_branch_baseline_unverified",
                "The Leader branch exists but no bootstrap receipt or roster binds its creation "
                "provenance. Pass --leader-bootstrap-commit from a prior provision receipt.",
            )
        if resolve_ref(git, f"refs/heads/{leader_branch}") != leader_bootstrap_commit:
            return stop(
                "leader_branch_baseline_unverified",
                "The supplied leaderBootstrapCommit does not match the current Leader branch tip.",
            )

    # Phase 3: Orca runtime and repo registration.
    status = orca_status(orca_cli)
    if not status["ready"]:
        return stop(
            "orca_runtime_unavailable",
            f"Orca runtime not ready: {status.get('code')} "
            f"(exit {status.get('exit')}): {status.get('stderr', '')}",
        )
    listed, _ = orca_repo_listed(orca_cli, str(git.repo))
    if not listed:
        return stop(
            "orca_repo_not_registered",
            "The project is not registered in the local Orca runtime. Run init-project-agent-team "
            "for this project first (its section 4 registers the root worktree).",
        )

    # Phase 4: logical team / Leader parent worktree — documented CLI gap.
    if leader_seat["worktree"] is None:
        return stop(
            "team_create_cli_pending",
            "Orca CLI 1.4.180 exposes no command that safely checks out the exact existing "
            "leader-claude-integration branch. Pending placeholder retained; fail closed; "
            "employee parent creation is unreachable until this resolves.",
        )

    # Phase 5: five employee secondary parents — unverified CLI surface.
    missing_employees = [
        key for key in SEAT_KEYS[1:] if plan["seats"][key]["worktree"] is None
    ]
    if missing_employees:
        return stop(
            "employee_parent_create_cli_pending",
            "Employee parent creation through the Orca CLI (with Leader-parent lineage binding) "
            "is not verified against the current CLI. Pending placeholder retained; fail closed.",
        )

    # Phase 6: full topology verified — publish the roster atomically.
    import team_roster  # noqa: PLC0415  # type: ignore[import-not-found]

    roster_result = team_roster.write_initial_roster(
        project=git.repo,
        roster_path=roster_path,
        plan=plan,
        mutations=mutations,
        git=git,
    )
    if not roster_result.get("ok"):
        return stop(roster_result.get("code", "roster_write_failed"), roster_result.get("message", ""))

    return {
        "ok": True,
        "code": "topology_provisioned",
        "changesApplied": True,
        "mutations": mutations,
        "main": plan["main"],
        "seats": plan["seats"],
        "roster": roster_result["roster"],
        "rosterPath": str(roster_path),
        "unrelatedWorktreesPreserved": True,
        "agentsStarted": False,
        "nextStep": "team quickstart",
    }


def stop_plan(
    git: tc.SafeGit,
    base_dir: Path,
    mutations: list[dict[str, Any]],
    unrelated_before: list[str],
    code: str,
    message: str,
) -> dict[str, Any]:
    """Build the unified topology receipt for a stop result."""
    unrelated_after: list[str] | None = None
    try:
        inventory = parse_worktree_inventory(git)
        planned_paths = {
            str(Path(path)).rstrip("/") for path in _all_planned_paths(base_dir)
        }
        unrelated_after = sorted(
            path
            for path in inventory.keys()
            if str(Path(path)).rstrip("/") not in planned_paths
        )
    except tc.TeamToolError:
        unrelated_after = None
    return {
        "ok": False,
        "code": code,
        "message": message,
        "changesApplied": bool(mutations),
        "mutations": mutations,
        "unrelatedWorktreesBefore": unrelated_before,
        "unrelatedWorktreesAfter": unrelated_after,
        "unrelatedWorktreesPreserved": (
            unrelated_after == unrelated_before if unrelated_after is not None else "unverified"
        ),
        "rosterPublished": False,
        "agentsStarted": False,
        "nextStep": {
            "main_attach_pending": "no safe in-repo next step; wait for the atomic attach primitive "
            "(pending placeholder) or attach main through a separately authorized Git workflow",
            "leader_branch_baseline_unverified": "re-run with --leader-bootstrap-commit from a prior receipt",
            "team_create_cli_pending": "wait for Orca CLI support (pending placeholder); do not bypass",
            "employee_parent_create_cli_pending": "wait for Orca CLI verification (pending placeholder); do not bypass",
            "orca_runtime_unavailable": "open the local Orca app (requires current-user authorization), then re-run",
            "orca_repo_not_registered": "run init-project-agent-team for this project first",
            "rules_object_not_accepted": "supply the accepted commit and governance evidence, then re-run",
            "main_worktree_create_failed": "inspect the raw git error, reconcile, then re-run preview",
            "leader_branch_create_failed": "inspect the raw git error, reconcile, then re-run preview",
            "git_ref_drift": "reconcile the moved ref before retrying",
            "git_ref_changed_after_mutation": "inventory-only reconciliation before any retry",
        }.get(code, "run team doctor --json for a full diagnosis"),
    }


def _all_planned_paths(base_dir: Path) -> list[str]:
    return [str(base_dir / "main")] + [str(base_dir / seat["key"]) for seat in SEATS]


def deprovision(
    project: Path,
    git_cli: str,
    roster_path: Path,
    confirm: bool,
    remove_branches: bool,
) -> dict[str, Any]:
    if not confirm:
        return {
            "ok": False,
            "code": "deprovision_requires_confirm",
            "message": "deprovision removes worktrees; pass --confirm after reviewing the target list.",
            "changesApplied": False,
            "targets": [],
        }
    if not roster_path.exists():
        return {
            "ok": False,
            "code": "roster_missing",
            "message": "roster.json missing; deprovision only removes worktrees recorded in the roster.",
            "changesApplied": False,
            "targets": [],
        }
    try:
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "code": "roster_unreadable",
            "message": f"roster.json unreadable: {exc}",
            "changesApplied": False,
            "targets": [],
        }
    targets = []
    for seat in roster.get("seats", []):
        worktree = seat.get("worktree", {}) if isinstance(seat.get("worktree"), dict) else {}
        path = worktree.get("path") or seat.get("worktree")
        if path:
            targets.append(path)
    main = roster.get("mainWorktree", {})
    main_path = main.get("path") if isinstance(main, dict) else None
    if main_path:
        targets.append(main_path)
    if not targets:
        return {
            "ok": False,
            "code": "roster_empty",
            "message": "roster.json records no worktrees; nothing to remove.",
            "changesApplied": False,
            "targets": [],
        }

    git = tc.SafeGit(git_cli, project)
    git.inspect_config()
    git.require_clean_read()

    dirty = []
    inventory = parse_worktree_inventory(git)
    existing_targets = [path for path in targets if path in inventory]
    for path in existing_targets:
        code, stdout, _ = git.run("-C", path, "status", "--porcelain")
        if code != 0:
            return {
                "ok": False,
                "code": "git_status_failed",
                "message": f"git status failed for {path}: exit {code}",
                "changesApplied": False,
                "targets": targets,
            }
        if stdout.strip():
            dirty.append(path)
    if dirty:
        return {
            "ok": False,
            "code": "dirty_worktree_refused",
            "message": "Refusing removal: the following worktrees have uncommitted changes.",
            "dirtyWorktrees": dirty,
            "changesApplied": False,
            "targets": targets,
        }

    removed = []
    for path in existing_targets:
        git.check_config_snapshot()
        code, stdout, stderr = git.run("worktree", "remove", path)
        if code != 0:
            return {
                "ok": False,
                "code": "worktree_remove_failed",
                "message": f"git worktree remove {path} exited {code}: "
                f"{stderr.decode('utf-8', 'replace').strip()}",
                "changesApplied": bool(removed),
                "removed": removed,
                "targets": targets,
            }
        removed.append(path)
    if remove_branches:
        return {
            "ok": True,
            "code": "deprovisioned_branches_kept",
            "message": "Worktrees removed; branch removal requires a separately authorized git command.",
            "changesApplied": True,
            "removed": removed,
            "targets": targets,
        }
    return {
        "ok": True,
        "code": "deprovisioned",
        "changesApplied": True,
        "removed": removed,
        "targets": targets,
        "branchesKept": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--subcommand", required=True, choices=("preview", "run", "deprovision"))
    parser.add_argument("--base-dir", help="worktrees base directory (default: <project-parent>/<project-name>-worktrees)")
    parser.add_argument("--git-cli", default="/usr/bin/git")
    parser.add_argument("--orca-cli", default="/Users/wzy/.homebrew/bin/orca")
    parser.add_argument("--accepted-commit")
    parser.add_argument("--leader-bootstrap-commit")
    parser.add_argument("--confirm-paths-digest")
    parser.add_argument("--confirm", action="store_true", help="deprovision: confirm removal of listed worktrees")
    parser.add_argument("--remove-branches", action="store_true", help="deprovision: also remove branches (requires separate authorization at run time)")
    parser.add_argument("--roster-path", default=".agent-team/roster.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = Path(args.project)
    base_dir = Path(args.base_dir) if args.base_dir else project.parent / f"{project.name}-worktrees"
    roster_path = Path(args.roster_path)
    if not roster_path.is_absolute():
        roster_path = project / roster_path

    try:
        if args.subcommand == "preview":
            git = tc.SafeGit(args.git_cli, project)
            git.inspect_config()
            git.require_clean_read()
            plan = build_plan(git, base_dir, args.accepted_commit, args.leader_bootstrap_commit)
            exit_code = 0 if plan.get("ok", True) else 9
            tc.emit(plan, exit_code)
        elif args.subcommand == "run":
            if not args.confirm_paths_digest:
                tc.emit(
                    {
                        "ok": False,
                        "code": "confirm_digest_required",
                        "message": "run requires --confirm-paths-digest from a user-approved preview",
                        "changesApplied": False,
                    },
                    2,
                )
            result = run_provision(
                project,
                base_dir,
                args.git_cli,
                args.orca_cli,
                args.accepted_commit,
                args.leader_bootstrap_commit,
                args.confirm_paths_digest,
                roster_path,
            )
            tc.emit(result, 0 if result.get("ok") else 7)
        elif args.subcommand == "deprovision":
            result = deprovision(project, args.git_cli, roster_path, args.confirm, args.remove_branches)
            tc.emit(result, 0 if result.get("ok") else 8)
    except tc.TeamToolError as exc:
        tc.emit(
            {
                "ok": False,
                "code": "invalid_project",
                "message": str(exc),
                "changesApplied": False,
            },
            9,
        )


if __name__ == "__main__":
    main()
