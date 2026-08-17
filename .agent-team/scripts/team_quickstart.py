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
import team_common as tc  # noqa: E402
import team_roster  # noqa: E402  # type: ignore[import-not-found]

ORCA_START_SESSION_PLACEHOLDER = (
    "<ORCA_START_SEAT_SESSION_PENDING_CLI_VERIFICATION>"
)

CLAUDE_SEATS = ("leader-claude", "principal-fullstack-claudex")


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
) -> dict[str, Any]:
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

    # Phase 5: session lifecycle.
    prior_tabs = [
        seat.get("tabId") for seat in roster["seats"] if seat.get("tabId")
    ]
    results["phases"]["sessionLifecycle"] = {
        "priorGenerationTabs": prior_tabs,
        "cleanupRequired": bool(prior_tabs),
        "state": "start_session_cli_pending",
        "placeholder": ORCA_START_SESSION_PLACEHOLDER,
    }
    return {
        "ok": False,
        "code": "start_session_cli_pending",
        "message": (
            "Topology, roster, permission modes, and Orca runtime all verified, but the "
            "Orca CLI surface for starting a seat session in a target worktree is unverified. "
            "Pending placeholder retained; fail closed; no terminal was created."
        ),
        "phases": results["phases"],
        "nextStep": "wait for Orca CLI verification (pending placeholder); do not bypass",
        "changesApplied": False,
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
        )
        tc.emit(result, 0 if result.get("ok") else 7)
    except tc.TeamToolError as exc:
        tc.emit(
            {"ok": False, "code": "invalid_project", "message": str(exc), "changesApplied": False},
            9,
        )


if __name__ == "__main__":
    main()
