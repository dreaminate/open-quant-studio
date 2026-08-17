#!/usr/bin/env python3
"""Generation roster: schema validator and initial writer.

`roster.json` lives at the repository root (`.agent-team/roster.json`).
Writing rules (normative, from the charter):

- only the provisioner (generation increments) and explicit human edits with
  current-user confirmation may write it; models and seats may not;
- every roster change is its own commit (authorized separately);
- a seat's `generation` increments when that seat's identity changes; stale
  generations are rejected at message verification time (M4).

This helper implements only the schema check and the atomic write mechanics.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import team_common as tc  # noqa: E402

ROSTER_SCHEMA_VERSION = 1
HEX_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}([+-]\d{2}:?\d{2}|Z)?$"
)

SEAT_KEYS = (
    "leader-claude",
    "advisor-codex",
    "fullstack-opencode",
    "review-opencode",
    "principal-fullstack-claudex",
    "frontend-kimi",
)
SEAT_BRANCHES = (
    "leader-claude-integration",
    "advisor-codex-integration",
    "fullstack-opencode-integration",
    "review-opencode-integration",
    "principal-fullstack-claudex-integration",
    "frontend-kimi-integration",
)


def validate_roster(roster: dict[str, Any]) -> dict[str, Any]:
    """Validate one parsed roster object; returns ok/errors, never mutates."""
    errors: list[str] = []

    def fail(message: str) -> None:
        errors.append(message)

    if roster.get("schemaVersion") != ROSTER_SCHEMA_VERSION:
        fail(f"schemaVersion must be {ROSTER_SCHEMA_VERSION}")
    generation = roster.get("generation")
    if not isinstance(generation, int) or generation < 0:
        fail("generation must be a non-negative integer")
    if "updatedAt" not in roster or not ISO8601_RE.match(str(roster.get("updatedAt", ""))):
        fail("updatedAt must be an ISO-8601 timestamp")
    if "updatedBy" not in roster or not str(roster.get("updatedBy", "")).strip():
        fail("updatedBy must be a nonempty string")

    for field in ("leaderBootstrapCommit", "acceptedMainCommit"):
        value = roster.get(field)
        if value is not None and not HEX_COMMIT_RE.match(str(value)):
            fail(f"{field} must be a full commit hash or null")

    main = roster.get("mainWorktree")
    if main is None or not isinstance(main, dict):
        fail("mainWorktree must be an object")
    elif main.get("branch") != "main":
        fail("mainWorktree.branch must be 'main'")
    elif not HEX_COMMIT_RE.match(str(main.get("commit", ""))):
        fail("mainWorktree.commit must be a full commit hash")
    elif not str(main.get("path", "")).strip():
        fail("mainWorktree.path must be a nonempty path")

    seats = roster.get("seats")
    if not isinstance(seats, list) or len(seats) != 6:
        fail("seats must contain exactly six entries")
        seats = []
    else:
        keys = [seat.get("seat") for seat in seats]
        if keys != list(SEAT_KEYS):
            fail(f"seats must use the canonical keys in order: {', '.join(SEAT_KEYS)}")

    seat_generations = [seat.get("generation") for seat in seats if isinstance(seat, dict)]
    if isinstance(generation, int) and seat_generations and any(
        value != generation for value in seat_generations
    ):
        fail("every seat generation must equal the roster generation")

    branches = []
    worktree_paths = []
    leader_worktree_id = None
    for index, seat in enumerate(seats):
        if not isinstance(seat, dict):
            fail(f"seats[{index}] must be an object")
            continue
        label = seat.get("seat", f"seats[{index}]")
        expected_branch = SEAT_BRANCHES[index]
        if seat.get("branch") != expected_branch:
            fail(f"{label}: branch must be {expected_branch}")
        branches.append(seat.get("branch"))

        worktree = seat.get("worktree")
        if not isinstance(worktree, dict) or not str(worktree.get("path", "")).strip():
            fail(f"{label}: worktree.path must be a nonempty path")
            continue
        worktree_paths.append(worktree["path"])
        orca_id = worktree.get("orcaWorktreeId")
        if orca_id is not None and not str(orca_id).strip():
            fail(f"{label}: worktree.orcaWorktreeId must be null or a nonempty id")

        if seat.get("owner") != label:
            fail(f"{label}: owner must equal the seat key")
        fingerprint = seat.get("public_key_fingerprint", "")
        if fingerprint != "" and not HEX_SHA256_RE.match(str(fingerprint)):
            fail(f"{label}: public_key_fingerprint must be empty or a 64-hex sha256")

        parent_id = seat.get("parent_id")
        if label == "leader-claude":
            if parent_id is not None:
                fail("leader-claude: parent_id must be null (second lineage root)")
            leader_worktree_id = worktree.get("orcaWorktreeId") or worktree.get("path")
        else:
            if parent_id is None:
                fail(f"{label}: parent_id must reference the Leader parent worktree")
            elif leader_worktree_id is not None and parent_id not in (
                leader_worktree_id,
                worktree.get("orcaWorktreeId"),
            ):
                fail(f"{label}: parent_id {parent_id!r} does not match the Leader worktree identity")

        if not str(seat.get("updated_by", "")).strip():
            fail(f"{label}: updated_by must be a nonempty string")
        if not ISO8601_RE.match(str(seat.get("updated_at", ""))):
            fail(f"{label}: updated_at must be an ISO-8601 timestamp")

    if len(set(branches)) != len(branches):
        fail("seat branches must be unique")
    if len(set(worktree_paths)) != len(worktree_paths):
        fail("seat worktree paths must be unique")

    return {
        "ok": not errors,
        "code": "roster_valid" if not errors else "roster_invalid",
        "errors": errors,
    }


def write_initial_roster(
    _project: Path,
    roster_path: Path,
    plan: dict[str, Any],
    mutations: list[dict[str, Any]],
    _git: Any = None,  # reserved: main-commit resolution source for future callers
) -> dict[str, Any]:
    """Build and atomically publish the initial generation-0 roster."""
    leader_mutation = next(
        (m for m in mutations if m.get("kind") == "leader_branch_created"), None
    )
    leader_bootstrap = (
        leader_mutation.get("leaderBootstrapCommit")
        if leader_mutation
        else plan.get("leaderBootstrapCommit")
    )
    accepted_main = plan["main"]["commit"]

    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    leader_worktree_path = (
        plan["seats"]["leader-claude"].get("existingWorktreePath")
        or plan["seats"]["leader-claude"]["plannedPath"]
    )
    seats = []
    for key, branch in zip(SEAT_KEYS, SEAT_BRANCHES):
        seat_plan = plan["seats"][key]
        worktree_path = seat_plan.get("existingWorktreePath") or seat_plan["plannedPath"]
        seats.append(
            {
                "seat": key,
                "branch": branch,
                "worktree": {"path": worktree_path, "orcaWorktreeId": None},
                "generation": 0,
                "parent_id": None if key == "leader-claude" else leader_worktree_path,
                "owner": key,
                "public_key_fingerprint": "",
                "updated_by": "provisioner",
                "updated_at": now,
            }
        )

    main_path = plan["main"].get("existingWorktreePath") or plan["main"]["plannedPath"]
    roster: dict[str, Any] = {
        "schemaVersion": ROSTER_SCHEMA_VERSION,
        "generation": 0,
        "leaderBootstrapCommit": leader_bootstrap,
        "acceptedMainCommit": accepted_main,
        "mainWorktree": {"path": main_path, "branch": "main", "commit": accepted_main},
        "seats": seats,
        "updatedAt": now,
        "updatedBy": "provisioner",
    }

    validation = validate_roster(roster)
    if not validation["ok"]:
        return {
            "ok": False,
            "code": "roster_validation_failed",
            "message": "; ".join(validation["errors"]),
        }

    roster_bytes = json.dumps(roster, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if roster_path.exists():
        return {
            "ok": False,
            "code": "roster_already_exists",
            "message": "roster.json already exists; generation increments belong to the quickstart "
            "publisher, not to initial provisioning.",
        }
    tc.write_new_file(roster_path, roster_bytes, 0o644)
    return {"ok": True, "code": "roster_published", "roster": roster}


def load_roster(roster_path: Path) -> dict[str, Any]:
    try:
        return json.loads(roster_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise tc.TeamToolError(f"roster_unreadable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise tc.TeamToolError(f"roster_invalid_json: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster-path", required=True)
    args = parser.parse_args()
    roster_path = Path(args.roster_path)
    try:
        roster = load_roster(roster_path)
    except tc.TeamToolError as exc:
        tc.emit(
            {"ok": False, "code": "roster_unreadable", "message": str(exc), "errors": [str(exc)]},
            9,
        )
        raise  # unreachable: emit raises SystemExit; keeps the type checker honest
    result = validate_roster(roster)
    result["path"] = str(roster_path)
    tc.emit(result, 0 if result["ok"] else 5)


if __name__ == "__main__":
    main()
