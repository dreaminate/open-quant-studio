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
import os
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
    try:
        result = payload.get("result") if isinstance(payload, dict) else None
        app_running = bool(result.get("app", {}).get("running")) if isinstance(result, dict) else False
        runtime_state = (
            result.get("runtime", {}).get("state") if isinstance(result, dict) else None
        )
        runtime_reachable = bool(
            result.get("runtime", {}).get("reachable") if isinstance(result, dict) else False
        )
    except (AttributeError, KeyError):
        app_running, runtime_state, runtime_reachable = False, "unknown", False
    ready = app_running and runtime_reachable and runtime_state not in (
        None,
        "not_running",
        "none",
        "",
    )
    if ready:
        return {"ready": True, "code": "orca_ready", "payload": payload}
    return {
        "ready": False,
        "code": "orca_runtime_unavailable",
        "payload": payload,
        "appRunning": app_running,
        "runtimeState": runtime_state,
        "runtimeReachable": runtime_reachable,
    }


def orca_repo_listed(orca_cli: str, project_path: str) -> tuple[bool, Any]:
    code, stdout, _ = tc.orca_run(orca_cli, "repo", "list", "--json")
    if code != 0:
        return False, {"code": "orca_repo_list_failed", "exit": code}
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return False, {"code": "orca_repo_list_invalid_json", "error": str(exc)}
    result_wrapper = payload.get("result") if isinstance(payload, dict) else None
    repos = (
        result_wrapper.get("repos", [])
        if isinstance(result_wrapper, dict)
        else (payload if isinstance(payload, list) else payload.get("repos", []))
    )
    canonical_project = canonical_path(project_path)
    for repo in repos:
        repo_path = repo.get("path") or repo.get("canonicalPath")
        if repo_path and canonical_path(str(repo_path)) == canonical_project:
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
            # Orca-first: branch and worktree are created together by the CLI;
            # there is no separate branch-creation step.
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
        "firstBlockingCode": expected_first_blocking_code(
            main_class, seats, leader_bootstrap_commit
        ),
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
    main_class: dict[str, Any],
    seats: dict[str, dict[str, Any]],
    leader_bootstrap_commit: str | None = None,
) -> str | None:
    """The first deterministic failure code a `run` will hit, if any.

    Environmental gates (Orca runtime, repo registration) are not
    deterministic, so a creatable topology returns None.
    """
    if main_class["state"] == "existing_unattached_branch":
        return "main_attach_pending"
    leader = seats[SEATS[0]["key"]]
    if leader["branchExists"] and leader["worktree"] is None:
        return "leader_branch_collision_cleanup_required"
    if leader["worktree"] is not None and leader_bootstrap_commit is None:
        return "leader_branch_baseline_unverified"
    employee_keys = [seat["key"] for seat in SEATS[1:]]
    for key in employee_keys:
        if seats[key]["branchExists"] and seats[key]["worktree"] is None:
            return "employee_branch_collision_cleanup_required"
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
    mock_contract: bool = False,
) -> dict[str, Any]:
    """Bind the user-approved preview, then walk the phase pipeline.

    The confirm digest is checked against the initial plan only; after a
    mid-run mutation the pipeline re-classifies from live inventory and the
    same fail-closed phases continue.
    """
    if mock_contract:
        require_mock_cli(orca_cli)
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
        mock_contract=mock_contract,
        repo_id=None,
    )


def canonical_path(raw: str) -> str:
    return os.path.realpath(str(Path(raw).expanduser()))


def require_mock_cli(orca_cli: str) -> None:
    """Contract-mode may only target the in-repo mock CLI.

    The real Orca CLI keeps its pending placeholders; the mock-contract flag
    must never reach it, or unverified command shapes would execute real
    terminal/worktree mutations.
    """
    identity = tc.executable_identity(orca_cli, "orca")
    resolved = Path(identity["canonicalPath"])
    is_in_repo_mock = (
        resolved.name == "mock_orca.py"
        and resolved.parent.name == "e2e"
        and resolved.parent.parent.name == "tests"
        and resolved.parent.parent.parent.name == ".agent-team"
    )
    if not is_in_repo_mock:
        raise tc.TeamToolError(
            "mock_contract_requires_mock_cli: --mock-orca-contract may only target the "
            "in-repo .agent-team/tests/e2e/mock_orca.py; the real Orca CLI keeps its "
            "pending placeholders and fails closed."
        )


def orca_worktree_ids(orca_cli: str, repo_id: str) -> dict[str, str]:
    """Map canonical worktree path -> orca worktree id from the CLI inventory."""
    code, stdout, _ = tc.orca_run(orca_cli, "worktree", "list", "--repo", repo_id, "--json")
    if code != 0:
        raise tc.TeamToolError(f"orca_worktree_list_failed: exit {code}")
    payload = json.loads(stdout)
    result_wrapper = payload.get("result") if isinstance(payload, dict) else None
    worktrees = (
        result_wrapper.get("worktrees", [])
        if isinstance(result_wrapper, dict)
        else payload.get("worktrees", [])
    )
    return {
        canonical_path(wt["path"]): wt["id"]
        for wt in worktrees
        if wt.get("path") and wt.get("id")
    }


def orca_worktree_inventory(
    orca_cli: str, repo_id: str
) -> dict[str, dict[str, Any]]:
    """Full Orca worktree inventory keyed by canonical path (real payload shape)."""
    code, stdout, _ = tc.orca_run(orca_cli, "worktree", "list", "--repo", repo_id, "--json")
    if code != 0:
        raise tc.TeamToolError(f"orca_worktree_list_failed: exit {code}")
    payload = json.loads(stdout)
    result_wrapper = payload.get("result") if isinstance(payload, dict) else None
    worktrees = (
        result_wrapper.get("worktrees", [])
        if isinstance(result_wrapper, dict)
        else payload.get("worktrees", [])
    )
    return {canonical_path(wt["path"]): wt for wt in worktrees if wt.get("path")}


def orca_create_named_worktree(
    orca_cli: str, repo_id: str, name: str, base_branch: str
) -> dict[str, Any]:
    """Create one worktree through the verified real CLI contract.

    Verified against 1.4.180 (2026-08-18): `worktree create --repo id:<id>
    --name <name> --base-branch <base> --no-parent --json` creates the exact
    branch `refs/heads/<name>` from <base> together with the worktree and a
    first terminal — provided the branch does not pre-exist (a collision
    makes the CLI auto-suffix the name, which this helper rejects).
    """
    argv = [
        "worktree",
        "create",
        "--repo",
        f"id:{repo_id}",
        "--name",
        name,
        "--base-branch",
        base_branch,
        "--no-parent",
        "--json",
    ]
    code, stdout, stderr = tc.orca_run(orca_cli, *argv)
    if code != 0:
        return {
            "ok": False,
            "code": "orca_worktree_create_failed",
            "exit": code,
            "stderr": stderr.decode("utf-8", "replace").strip()[:500],
        }
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "code": "orca_worktree_create_invalid_json", "error": str(exc)}
    result_wrapper = payload.get("result") if isinstance(payload, dict) else None
    created = result_wrapper.get("worktree") if isinstance(result_wrapper, dict) else None
    if not payload.get("ok") or not isinstance(created, dict):
        return {"ok": False, "code": "orca_worktree_create_rejected", "payload": payload}
    if created.get("branch") != f"refs/heads/{name}":
        return {
            "ok": False,
            "code": "orca_worktree_create_mismatched_branch",
            "payload": created,
        }
    if not created.get("head"):
        return {"ok": False, "code": "orca_worktree_create_missing_head", "payload": created}
    first_terminal = result_wrapper.get("firstTerminal") if isinstance(result_wrapper, dict) else None
    return {
        "ok": True,
        "worktree": created,
        "firstTerminal": first_terminal,
    }


def orca_set_worktree(
    orca_cli: str,
    worktree_selector: str,
    display_name: str | None = None,
    parent_worktree: str | None = None,
    no_parent: bool = False,
) -> dict[str, Any]:
    """Update Orca metadata: display name and/or parent lineage (verified CLI).

    `worktree_selector` and `parent_worktree` are raw Orca worktree ids
    (`<repo-id>::<path>`); the CLI selector form `id:<id>` is composed here.
    """
    argv = ["worktree", "set", "--worktree", f"id:{worktree_selector}", "--json"]
    if display_name is not None:
        argv += ["--display-name", display_name]
    if parent_worktree is not None:
        argv += ["--parent-worktree", f"id:{parent_worktree}"]
    if no_parent:
        argv.append("--no-parent")
    code, stdout, stderr = tc.orca_run(orca_cli, *argv)
    if code != 0:
        return {
            "ok": False,
            "code": "orca_worktree_set_failed",
            "exit": code,
            "stderr": stderr.decode("utf-8", "replace").strip()[:500],
        }
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "code": "orca_worktree_set_invalid_json", "error": str(exc)}
    if not payload.get("ok"):
        return {"ok": False, "code": "orca_worktree_set_rejected", "payload": payload}
    result_wrapper = payload.get("result") if isinstance(payload, dict) else None
    updated = result_wrapper.get("worktree") if isinstance(result_wrapper, dict) else None
    if parent_worktree is not None and isinstance(updated, dict):
        if updated.get("parentWorktreeId") != parent_worktree:
            return {
                "ok": False,
                "code": "orca_worktree_set_parent_mismatch",
                "payload": updated,
            }
    return {"ok": True, "worktree": updated}


def orca_clean_first_terminal(
    orca_cli: str,
    repo_id: str,
    worktree_path: str,
    first_terminal: dict[str, Any] | None,
) -> dict[str, Any]:
    """Close exactly the first terminal bound to a worktree-creation receipt.

    With a receipt: every terminal in the new worktree's inventory must
    belong to the receipt's tab. Without one (older runtimes omit it): the
    brand-new worktree must show exactly one terminal — the just-created
    first terminal — or cleanup fails closed as scope-ambiguous.
    """
    if not first_terminal:
        first_terminal = {}
    code, stdout, _ = tc.orca_run(
        orca_cli,
        "terminal",
        "list",
        "--worktree",
        f"id:{repo_id}::{worktree_path}",
        "--include-visual-layouts",
        "--json",
    )
    if code != 0:
        return {"ok": False, "code": "terminal_list_failed", "exit": code}
    try:
        payload = json.loads(stdout)
        wrapper = payload.get("result") if isinstance(payload, dict) else None
        terminals = (
            wrapper.get("terminals", [])
            if isinstance(wrapper, dict)
            else payload.get("terminals", [])
        )
    except json.JSONDecodeError as exc:
        return {"ok": False, "code": "terminal_list_invalid_json", "error": str(exc)}
    handle = first_terminal.get("handle")
    if handle:
        # Receipt-bound path: every terminal must belong to the receipt tab.
        if any(term.get("tabId") != first_terminal.get("tabId") for term in terminals):
            return {"ok": False, "code": "team_cleanup_scope_ambiguous"}
    else:
        # Receipt-less (older runtime): the brand-new worktree must show
        # exactly one terminal — the just-created first terminal.
        if len(terminals) != 1 or not terminals[0].get("handle"):
            return {"ok": False, "code": "team_cleanup_scope_ambiguous"}
        handle = terminals[0]["handle"]
    close_code, close_out, _ = tc.orca_run(
        orca_cli, "terminal", "close", "--terminal", str(handle), "--tab", "--json"
    )
    if close_code != 0:
        return {"ok": False, "code": "terminal_close_failed", "exit": close_code}
    try:
        close_payload = json.loads(close_out)
    except json.JSONDecodeError as exc:
        return {"ok": False, "code": "terminal_close_invalid_json", "error": str(exc)}
    if not close_payload.get("ok"):
        return {"ok": False, "code": "terminal_close_rejected", "payload": close_payload}
    # Zero-state proof: re-list and require no terminals for this worktree.
    code, stdout, _ = tc.orca_run(
        orca_cli,
        "terminal",
        "list",
        "--worktree",
        f"id:{repo_id}::{worktree_path}",
        "--include-visual-layouts",
        "--json",
    )
    if code != 0:
        return {"ok": False, "code": "terminal_list_failed_after_close", "exit": code}
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "code": "terminal_list_invalid_json_after_close", "error": str(exc)}
    wrapper = payload.get("result") if isinstance(payload, dict) else None
    total = wrapper.get("totalCount") if isinstance(wrapper, dict) else payload.get("totalCount", -1)
    terminals = wrapper.get("terminals", []) if isinstance(wrapper, dict) else payload.get("terminals", [])
    if total != 0 or terminals:
        return {"ok": False, "code": "team_cleanup_incomplete"}
    return {"ok": True, "code": "first_terminal_cleaned"}


def run_phases(
    git: tc.SafeGit,
    base_dir: Path,
    orca_cli: str,
    accepted_commit: str | None,
    leader_bootstrap_commit: str | None,
    roster_path: Path,
    mutations: list[dict[str, Any]],
    unrelated_before: list[str],
    mock_contract: bool = False,
    repo_id: str | None = None,
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
            mutations, unrelated_before, mock_contract, repo_id,
        )

    # Phase 2: Leader branch state. The verified Orca-first contract creates
    # the exact integration branch together with its worktree; a pre-existing
    # branch collides (the CLI auto-suffixes the name), so that state fails
    # closed with a cleanup route.
    leader_key = SEATS[0]["key"]
    leader_branch = SEATS[0]["branch"]
    leader_seat = plan["seats"][leader_key]
    if leader_seat["branchExists"] and leader_seat["worktree"] is None:
        return stop(
            "leader_branch_collision_cleanup_required",
            f"The {leader_branch} branch already exists without an Orca worktree. "
            "Orca-first creation requires the branch to be absent (a pre-existing branch "
            "makes the CLI auto-suffix the name). Delete the branch through a separately "
            "authorized git command, then re-run.",
        )
    if leader_seat["worktree"] is not None and leader_bootstrap_commit is None:
        return stop(
            "leader_branch_baseline_unverified",
            "The Leader worktree exists but no bootstrap receipt or roster binds its creation "
            "provenance. Pass --leader-bootstrap-commit from a prior provision receipt.",
        )

    # Phase 3: Orca runtime and repo registration.
    status = orca_status(orca_cli)
    if not status["ready"]:
        return stop(
            "orca_runtime_unavailable",
            f"Orca runtime not ready: {status.get('code')} "
            f"(exit {status.get('exit')}): {status.get('stderr', '')}",
        )
    listed, repo_info = orca_repo_listed(orca_cli, str(git.repo))
    if not listed:
        return stop(
            "orca_repo_not_registered",
            "The project is not registered in the local Orca runtime. Run init-project-agent-team "
            "for this project first (its section 4 registers the root worktree).",
        )
    repo_id = repo_info.get("repoId") or repo_id
    if not repo_id:
        return stop(
            "orca_repo_registration_incomplete",
            "The Orca repo inventory did not expose a repo id for this project.",
        )

    # Phase 4: logical team / Leader parent worktree — the verified real
    # Orca-first contract (identical shape in mock mode, which mirrors it).
    if leader_seat["worktree"] is None:
        created = orca_create_named_worktree(orca_cli, repo_id, leader_branch, "main")
        if not created["ok"]:
            return stop(created["code"], f"team worktree creation failed: {created}")
        team_path = created["worktree"]["path"]
        set_result = orca_set_worktree(
            orca_cli, created["worktree"]["id"], display_name="team", no_parent=True
        )
        if not set_result["ok"]:
            return stop(set_result["code"], f"team display-name set failed: {set_result}")
        cleaned = orca_clean_first_terminal(
            orca_cli, repo_id, team_path, created.get("firstTerminal")
        )
        if not cleaned["ok"]:
            return stop(cleaned["code"], f"team first-terminal cleanup failed: {cleaned}")
        bootstrap_commit = created["worktree"]["head"]
        mutations.append(
            {
                "kind": "team_worktree_created",
                "path": team_path,
                "branch": leader_branch,
                "orcaWorktreeId": created["worktree"]["id"],
                "leaderBootstrapCommit": bootstrap_commit,
                "commandSucceeded": True,
                "firstTerminalCleaned": True,
            }
        )
        return run_phases(
            git, base_dir, orca_cli, accepted_commit, bootstrap_commit, roster_path,
            mutations, unrelated_before, mock_contract, repo_id,
        )

    # Phase 5: five employee secondary parents — the verified real contract.
    missing_employees = [
        key for key in SEAT_KEYS[1:] if plan["seats"][key]["worktree"] is None
    ]
    if missing_employees:
        team_inventory = orca_worktree_inventory(orca_cli, repo_id)
        team_entry = team_inventory.get(
            canonical_path(plan["seats"][leader_key]["existingWorktreePath"])
        )
        if team_entry is None:
            return stop(
                "orca_worktree_inventory_missing_team",
                "team worktree not found in the Orca inventory",
            )
        team_selector = team_entry["id"]
        for key in missing_employees:
            seat_plan = plan["seats"][key]
            if seat_plan["branchExists"]:
                return stop(
                    "employee_branch_collision_cleanup_required",
                    f"Branch {seat_plan['branch']} exists without an Orca worktree; delete it "
                    "through a separately authorized git command and re-run.",
                )
            created = orca_create_named_worktree(
                orca_cli, repo_id, seat_plan["branch"], leader_branch
            )
            if not created["ok"]:
                return stop(
                    created["code"], f"employee worktree creation failed for {key}: {created}"
                )
            employee_path = created["worktree"]["path"]
            parent_result = orca_set_worktree(
                orca_cli, created["worktree"]["id"], parent_worktree=team_selector
            )
            if not parent_result["ok"]:
                return stop(
                    parent_result["code"],
                    f"employee parent set failed for {key}: {parent_result}",
                )
            cleaned = orca_clean_first_terminal(
                orca_cli, repo_id, employee_path, created.get("firstTerminal")
            )
            if not cleaned["ok"]:
                return stop(
                    cleaned["code"], f"employee first-terminal cleanup failed for {key}: {cleaned}"
                )
            mutations.append(
                {
                    "kind": "employee_worktree_created",
                    "seat": key,
                    "path": employee_path,
                    "branch": seat_plan["branch"],
                    "orcaWorktreeId": created["worktree"]["id"],
                    "parentOrcaWorktreeId": team_selector,
                    "commandSucceeded": True,
                    "firstTerminalCleaned": True,
                }
            )
        return run_phases(
            git, base_dir, orca_cli, accepted_commit, leader_bootstrap_commit, roster_path,
            mutations, unrelated_before, mock_contract, repo_id,
        )

    # Phase 6: full topology verified — publish the roster atomically.
    import team_roster  # noqa: PLC0415  # type: ignore[import-not-found]

    orca_ids = orca_worktree_ids(orca_cli, repo_id)
    roster_result = team_roster.write_initial_roster(
        _project=git.repo,
        roster_path=roster_path,
        plan=plan,
        mutations=mutations,
        _git=git,
        orca_worktree_ids=orca_ids,
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
        "rosterPublished": True,
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
        planned_paths = {canonical_path(path) for path in _all_planned_paths(base_dir)}
        # Worktrees created by Orca-first land at Orca-chosen paths; those
        # are managed, not unrelated.
        for mutation in mutations:
            if mutation.get("path"):
                planned_paths.add(canonical_path(mutation["path"]))
        unrelated_after = sorted(
            path for path in inventory.keys() if canonical_path(path) not in planned_paths
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
    primary_code, primary_out, _ = git.run("rev-parse", "--show-toplevel")
    primary = primary_out.decode("utf-8", "replace").strip() if primary_code == 0 else None
    existing_targets = [path for path in targets if path in inventory]
    removable_targets = [
        path
        for path in existing_targets
        if primary is None or canonical_path(path) != canonical_path(primary)
    ]
    for path in removable_targets:
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
    primary_kept = []
    for path in existing_targets:
        if primary and canonical_path(path) == canonical_path(primary):
            # The primary worktree is never a deprovision target.
            primary_kept.append(path)
            continue
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
                "primaryWorktreeKept": primary_kept,
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
            "primaryWorktreeKept": primary_kept,
            "targets": targets,
        }
    return {
        "ok": True,
        "code": "deprovisioned",
        "changesApplied": True,
        "removed": removed,
        "primaryWorktreeKept": primary_kept,
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
    parser.add_argument(
        "--mock-orca-contract",
        action="store_true",
        help="disposable E2E only: use the documented future Orca CLI contract via the mock CLI "
        "instead of the pending placeholders",
    )
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
                mock_contract=args.mock_orca_contract,
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
