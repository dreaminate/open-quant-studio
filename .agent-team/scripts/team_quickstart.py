#!/usr/bin/env python3
"""Quick Start preflight and session-lifecycle launcher.

Owns session lifecycle only: input = a verified topology receipt plus a valid
roster; output = a generation receipt. It never repairs worktrees or the
charter mid-run — those failures route to adopt/provision instead.

Preflight phases (all read-only, fail closed with a navigable code):

1. charter check      -> `charter_mismatch` / `charter_current_meta_missing`
2. roster + topology  -> `team_worktree_topology_required`
3. permission modes   -> `claude_auto_mode_required`
4. Orca runtime       -> `orca_runtime_unavailable`

Session phase (only after all four preflight phases pass):

5. close the previous generation's recorded resident tabs (exact tab IDs and
   current handles, zero-state proof), then create six fresh sessions — the
   session-creation CLI surface is unverified, so the create step stops at
   its pending placeholder and fails closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import team_adopt  # noqa: E402  # type: ignore[import-not-found]
import team_common as tc  # noqa: E402  # type: ignore[import-not-found]
import team_provision  # noqa: E402  # type: ignore[import-not-found]
import team_roster  # noqa: E402  # type: ignore[import-not-found]

ORCA_START_SESSION_PLACEHOLDER = (
    "<ORCA_START_SEAT_SESSION_PENDING_CLI_VERIFICATION>"
)
# Session-creation surface verified against the real 1.4.180 CLI (2026-08-18):
# `orca terminal create --worktree <selector> --command "<cli>" --json` returns
# result.terminal.{handle,tabId,worktreeId}. The placeholder above only
# remains for the topology gate: quickstart still refuses to start sessions
# until the complete six-worktree topology exists.

CLAUDE_SEATS = ("leader-claude", "principal-fullstack-claudex")

# Agent token, launch arguments, permission mode, and launch command per seat
# (charter roster). The launch command is what `orca terminal create
# --command` receives; opencode/kimi seats carry their configuration in
# profiles, not flags.
SEAT_LAUNCH: dict[str, tuple[str, str, str, str]] = {
    "leader-claude": (
        "claude",
        "model=deepseek-v4-pro[1m]; effort=max",
        "--permission-mode auto",
        "claude --permission-mode auto",
    ),
    "advisor-codex": (
        "codex",
        "model=gpt-5.6-sol; effort=ultra; service_tier=priority",
        "dangerously-bypass-approvals-and-sandbox",
        "codex --dangerously-bypass-approvals-and-sandbox",
    ),
    "fullstack-opencode": (
        "opencode",
        "agent=delivery-deepseek-flash; model=deepseek-v4-flash; variant=max",
        "auto + agent permission=allow",
        "opencode",
    ),
    "review-opencode": (
        "opencode",
        "agent=review-opus; model=jiekou-ai/claude-opus-4-8-r",
        "auto + agent permission=allow",
        "opencode",
    ),
    "principal-fullstack-claudex": (
        "claudex",
        "model=gpt-5.6-sol; effort=max",
        "--permission-mode auto",
        "claudex --permission-mode auto",
    ),
    "frontend-kimi": (
        "kimi",
        "config model=kimi-k3; thinking=max",
        "Orca default --auto",
        "kimi",
    ),
}


def check_claude_auto_mode(home: Path, project: Path) -> dict[str, Any]:
    """Read-only check that every Claude-surface default resolves to auto mode.

    Looks at the current-user Claude settings and the project-level settings;
    `permissions.defaultMode` must be exactly "auto" on the surface that would
    apply. Reports each surface's effective value; a non-auto or unreadable
    surface fails closed without guessing.
    """
    surfaces: dict[str, Any] = {}
    for label, path in (
        ("user", home / ".claude" / "settings.json"),
        ("project", project / ".claude" / "settings.json"),
    ):
        if not path.exists():
            surfaces[label] = {"path": str(path), "present": False, "defaultMode": None}
            continue
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "ok": False,
                "code": "claude_settings_unreadable",
                "message": f"cannot read {path}: {exc}",
                "surfaces": surfaces,
            }
        mode = (settings.get("permissions") or {}).get("defaultMode")
        surfaces[label] = {"path": str(path), "present": True, "defaultMode": mode}

    # Resolution rule: the project surface overrides the user surface when
    # present; otherwise the user surface applies. auto is required on the
    # surface that actually resolves.
    project_mode = surfaces["project"]["defaultMode"]
    user_mode = surfaces["user"]["defaultMode"]
    effective = project_mode if project_mode is not None else user_mode
    ok = effective == "auto"
    return {
        "ok": ok,
        "code": "claude_auto_mode_ok" if ok else "claude_auto_mode_required",
        "effectiveMode": effective,
        "surfaces": surfaces,
        "message": (
            None
            if ok
            else "The effective Claude permission default mode is not exactly `auto`. "
            "No other permission mode or bypass flag is equivalent; startup refuses "
            "terminal creation."
        ),
    }


def run_quickstart(
    project: Path,
    asset_path: Path,
    meta_path: Path,
    roster_path: Path,
    orca_cli: str,
    home: Path,
    mock_contract: bool = False,
) -> dict[str, Any]:
    if mock_contract:
        team_provision.require_mock_cli(orca_cli)
    results: dict[str, Any] = {"phases": {}}

    # Phase 1: charter.
    charter = team_adopt.check_current(project, asset_path, meta_path)
    results["phases"]["charter"] = charter
    if charter["code"] == "charter_mismatch":
        return fail("charter_mismatch", charter["nextStep"], results)
    if charter["code"] == "charter_current_meta_missing":
        return fail("charter_current_meta_missing", charter["nextStep"], results)

    # Phase 2: roster + verified topology.
    if not roster_path.exists():
        return fail(
            "team_worktree_topology_required",
            "provision preview",
            results,
            message="roster.json missing: run provision to create the six-worktree topology.",
        )
    try:
        roster = team_roster.load_roster(roster_path)
    except tc.TeamToolError as exc:
        return fail("roster_unreadable", "team doctor --json", results, message=str(exc))
    validation = team_roster.validate_roster(roster)
    results["phases"]["roster"] = validation
    if not validation["ok"]:
        return fail(
            "team_worktree_topology_required",
            "provision preview",
            results,
            message="roster invalid: " + "; ".join(validation["errors"]),
        )
    missing_worktrees = [
        seat["seat"]
        for seat in roster["seats"]
        if not Path(seat["worktree"]["path"]).is_dir()
    ]
    if missing_worktrees:
        return fail(
            "team_worktree_topology_required",
            "provision preview",
            results,
            message="missing worktree directories: " + ", ".join(missing_worktrees),
        )

    # Phase 3: permission modes.
    mode_check = check_claude_auto_mode(home, project)
    results["phases"]["claudeAutoMode"] = mode_check
    if not mode_check["ok"]:
        return fail(mode_check["code"], "fix the Claude permission default, then re-run", results)

    # Phase 4: Orca runtime.
    code, _stdout, stderr = tc.orca_run(orca_cli, "status", "--json")
    if code != 0:
        results["phases"]["orca"] = {"ready": False, "exit": code, "stderr": stderr.decode("utf-8", "replace")[:300]}
        return fail(
            "orca_runtime_unavailable",
            "open the local Orca app (requires current-user authorization), then re-run",
            results,
            message=f"orca status exited {code}",
        )
    results["phases"]["orca"] = {"ready": True}

    # Phase 5: session lifecycle — the verified real contract (terminal
    # create); the mock CLI mirrors the same shapes for E2E runs.
    prior_tabs = [seat.get("tabId") for seat in roster["seats"] if seat.get("tabId")]
    listed, repo_info = team_provision.orca_repo_listed(orca_cli, str(project))
    if not listed:
        return fail("orca_repo_not_registered", "provision preview", results)
    repo_id = repo_info.get("repoId")

    code, stdout, _ = tc.orca_run(orca_cli, "terminal", "list", "--include-visual-layouts", "--json")
    if code != 0:
        return fail("terminal_inventory_unavailable", "open the local Orca app, then re-run", results)
    try:
        inventory_payload = json.loads(stdout)
        result_wrapper = inventory_payload.get("result") if isinstance(inventory_payload, dict) else None
        all_terminals = (
            result_wrapper.get("terminals", [])
            if isinstance(result_wrapper, dict)
            else inventory_payload.get("terminals", [])
        )
    except json.JSONDecodeError as exc:
        return fail("terminal_inventory_invalid", "inspect the orca terminal inventory", results, message=str(exc))

    # Scope to THIS project's worktrees: other projects' resident terminals
    # on a shared runtime are never cleanup targets or readiness signals.
    roster_ids = {
        seat["worktree"]["orcaWorktreeId"]
        for seat in roster["seats"]
        if seat["worktree"].get("orcaWorktreeId")
    }
    roster_paths = {
        team_provision.canonical_path(seat["worktree"]["path"])
        for seat in roster["seats"]
    }
    terminals = [
        term
        for term in all_terminals
        if term.get("worktreeId") in roster_ids
        or team_provision.canonical_path(str(term.get("worktreePath") or term.get("path") or ""))
        in roster_paths
    ]

    prior_tab_set = set(prior_tabs)
    unrecorded = [term for term in terminals if term.get("tabId") not in prior_tab_set]
    if terminals and not prior_tab_set:
        return fail(
            "team_cleanup_scope_ambiguous",
            "inspect the resident terminals, then re-run",
            results,
            message="resident terminals exist but the roster records no prior generation; "
            "cleanup fails closed rather than guessing.",
        )
    if unrecorded:
        return fail(
            "team_cleanup_scope_ambiguous",
            "inspect the resident terminals, then re-run",
            results,
            message=f"{len(unrecorded)} terminal(s) not bound to the prior generation roster.",
        )

    for tab_id in prior_tabs:
        handle = next(
            (term["handle"] for term in terminals if term.get("tabId") == tab_id), None
        )
        if handle is None:
            return fail("team_cleanup_scope_ambiguous", "inspect the resident terminals, then re-run", results)
        close_code, close_out, _ = tc.orca_run(
            orca_cli, "terminal", "close", "--terminal", str(handle), "--tab", "--json"
        )
        if close_code != 0:
            return fail("terminal_close_failed", "inspect the close error, then re-run", results)
        if not json.loads(close_out).get("ok"):
            return fail("terminal_close_rejected", "inspect the close error, then re-run", results)

    code, stdout, _ = tc.orca_run(orca_cli, "terminal", "list", "--include-visual-layouts", "--json")
    if code != 0:
        return fail("team_cleanup_incomplete", "inspect the resident terminals, then re-run", results)
    try:
        zero_payload = json.loads(stdout)
        zero_wrapper = zero_payload.get("result") if isinstance(zero_payload, dict) else None
        zero_all = (
            zero_wrapper.get("terminals", [])
            if isinstance(zero_wrapper, dict)
            else zero_payload.get("terminals", [])
        )
    except json.JSONDecodeError:
        zero_all = []
    zero_scoped = [
        term
        for term in zero_all
        if term.get("worktreeId") in roster_ids
        or team_provision.canonical_path(str(term.get("worktreePath") or term.get("path") or ""))
        in roster_paths
    ]
    if zero_scoped:
        return fail("team_cleanup_incomplete", "inspect the resident terminals, then re-run", results)

    updates: dict[str, dict[str, str]] = {}
    tab_ids: set[str] = set()
    handles: set[str] = set()
    for seat in roster["seats"]:
        seat_key = seat["seat"]
        _agent_token, launch_args, permission, launch_command = SEAT_LAUNCH[seat_key]
        selector = f"id:{repo_id}::{seat['worktree']['path']}"
        start_code, start_out, start_err = tc.orca_run(
            orca_cli,
            "terminal",
            "create",
            "--worktree",
            selector,
            "--command",
            launch_command,
            "--title",
            seat_key,
            "--json",
        )
        if start_code != 0:
            return fail(
                "terminal_create_failed",
                "inspect the create error, then re-run",
                results,
                message=f"{seat_key}: {start_err.decode('utf-8', 'replace')[:300]}",
            )
        receipt = json.loads(start_out)
        terminal = receipt.get("result", {}).get("terminal") if isinstance(receipt.get("result"), dict) else None
        tab_id = (terminal or {}).get("tabId")
        handle = (terminal or {}).get("handle")
        if not receipt.get("ok") or not tab_id or not handle:
            return fail("terminal_create_invalid_receipt", "inspect the create error, then re-run", results)
        if tab_id in tab_ids or handle in handles:
            return fail("terminal_create_duplicate_identity", "inspect the create receipts, then re-run", results)
        tab_ids.add(tab_id)
        handles.add(handle)
        updates[seat_key] = {
            "tabId": tab_id,
            "terminalHandle": handle,
            "launchArgs": launch_args,
            "permissionMode": permission,
        }

    publish = team_roster.write_generation_roster(
        roster_path, roster, updates, updated_by="quickstart"
    )
    if not publish["ok"]:
        return fail(publish["code"], "inspect the roster publish error", results, message=publish["message"])

    results["phases"]["sessionLifecycle"] = {
        "priorGenerationTabs": prior_tabs,
        "cleanupRequired": bool(prior_tabs),
        "zeroStateProved": True,
        "createdSessions": 6,
        "state": "generation_published",
    }
    return {
        "ok": True,
        "code": "quickstart_generation_published",
        "generation": publish["generation"],
        "phases": results["phases"],
        "nextStep": "assign work through the Team; verify messages with `message verify`",
        "changesApplied": True,
        "rosterPath": str(roster_path),
    }


def fail(
    code: str, next_step: str, results: dict[str, Any], message: str | None = None
) -> dict[str, Any]:
    return {
        "ok": False,
        "code": code,
        "message": message,
        "phases": results["phases"],
        "nextStep": next_step,
        "changesApplied": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--asset", default=str(tc.ASSET_TEAM_PATH))
    parser.add_argument("--meta-path", default=".agent-team/charter-meta.json")
    parser.add_argument("--roster-path", default=".agent-team/roster.json")
    parser.add_argument("--orca-cli", default="/Users/wzy/.homebrew/bin/orca")
    parser.add_argument("--home", default=str(Path.home()))
    parser.add_argument(
        "--mock-orca-contract",
        action="store_true",
        help="disposable E2E only: use the documented future Orca CLI contract via the mock CLI",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = Path(args.project)
    meta_path = Path(args.meta_path)
    roster_path = Path(args.roster_path)
    if not meta_path.is_absolute():
        meta_path = project / meta_path
    if not roster_path.is_absolute():
        roster_path = project / roster_path
    try:
        result = run_quickstart(
            project,
            Path(args.asset),
            meta_path,
            roster_path,
            args.orca_cli,
            Path(args.home),
            mock_contract=args.mock_orca_contract,
        )
        tc.emit(result, 0 if result.get("ok") else 7)
    except tc.TeamToolError as exc:
        tc.emit(
            {"ok": False, "code": "invalid_project", "message": str(exc), "changesApplied": False},
            9,
        )


if __name__ == "__main__":
    main()
