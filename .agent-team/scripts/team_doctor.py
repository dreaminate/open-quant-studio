#!/usr/bin/env python3
"""Read-only Team self-check: `team doctor --json`.

Checks, in severity order: charter version, pointer consistency, approval
matrix coverage, roster validity, main/team worktree state, six parent
worktrees, CLI profile seat identity, Orca runtime, terminal readiness, and
embedded M4 identity positive/negative cases. Every failure carries a
machine-readable code and the next safe recovery command. Zero mutation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import team_adopt  # noqa: E402  # type: ignore[import-not-found]
import team_common as tc  # noqa: E402  # type: ignore[import-not-found]
import team_identity  # noqa: E402  # type: ignore[import-not-found]
import team_provision  # noqa: E402  # type: ignore[import-not-found]
import team_quickstart  # noqa: E402  # type: ignore[import-not-found]
import team_roster  # noqa: E402  # type: ignore[import-not-found]

APPROVAL_ROW_IDS = tuple(f"AP-{index:02d}" for index in range(1, 23))


def check_charter(project: Path, asset_path: Path, meta_path: Path) -> dict[str, Any]:
    result = team_adopt.check_current(project, asset_path, meta_path)
    return {
        "id": "charter",
        "label": "charter version",
        "ok": result["ok"],
        "code": result["code"],
        "detail": {
            "currentContractVersion": result["current"]["contractVersion"],
            "currentCharterSha256": result["current"]["charterSha256"],
        },
        "nextStep": result["nextStep"],
    }


def check_pointers(project: Path) -> dict[str, Any]:
    problems = []
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = project / name
        if not path.exists() or path.is_symlink():
            problems.append(f"{name} missing or a symlink")
            continue
        try:
            _, changed = tc.replace_pointer_block(path.read_bytes(), name)
        except tc.TeamToolError as exc:
            problems.append(str(exc))
            continue
        if changed:
            problems.append(f"{name} pointer is not canonical")
    return {
        "id": "pointers",
        "label": "pointer consistency",
        "ok": not problems,
        "code": "pointers_canonical" if not problems else "pointer_mismatch",
        "detail": problems,
        "nextStep": "adopt-team-charter preview" if problems else None,
    }


BOUNDARY_BEGIN = "<!-- agent-team-runtime-boundary:begin -->"
BOUNDARY_END = "<!-- agent-team-runtime-boundary:end -->"
# Generic clauses every project's boundary block must contain; project-specific
# wording (OQS, Pi, the game, ...) is free beyond these.
BOUNDARY_CLAUSES = (
    "development collaboration control plane",
    "does not enter the",
    "not constitute a second",
    "team doctor --json",
)


def check_runtime_boundary(project: Path) -> dict[str, Any]:
    """Verify the M8 runtime-boundary clause is installed in AGENTS.md."""
    path = project / "AGENTS.md"
    if not path.exists() or path.is_symlink():
        return {
            "id": "runtime_boundary",
            "label": "runtime boundary clause",
            "ok": False,
            "code": "runtime_boundary_missing",
            "detail": ["AGENTS.md missing or a symlink"],
            "nextStep": "restore the boundary section in AGENTS.md from the repository",
        }
    text = path.read_text(encoding="utf-8")
    if BOUNDARY_BEGIN not in text or BOUNDARY_END not in text:
        return {
            "id": "runtime_boundary",
            "label": "runtime boundary clause",
            "ok": False,
            "code": "runtime_boundary_missing",
            "detail": ["boundary markers missing from AGENTS.md"],
            "nextStep": "restore the boundary section in AGENTS.md from the repository",
        }
    block = text[text.index(BOUNDARY_BEGIN) + len(BOUNDARY_BEGIN) : text.index(BOUNDARY_END)]
    normalized_block = re.sub(r"\s+", " ", block)
    missing_clauses = [clause for clause in BOUNDARY_CLAUSES if clause not in normalized_block]
    return {
        "id": "runtime_boundary",
        "label": "runtime boundary clause",
        "ok": not missing_clauses,
        "code": "runtime_boundary_present" if not missing_clauses else "runtime_boundary_incomplete",
        "detail": {"missingClauses": missing_clauses},
        "nextStep": (
            None
            if not missing_clauses
            else "restore the boundary section in AGENTS.md from the repository"
        ),
    }


def check_approval_matrix(approval_path: Path) -> dict[str, Any]:
    if not approval_path.exists():
        return {
            "id": "approval",
            "label": "approval matrix",
            "ok": False,
            "code": "approval_missing",
            "detail": [f"{approval_path} missing"],
            "nextStep": "restore .agent-team/APPROVAL.md from the repository",
        }
    text = approval_path.read_text(encoding="utf-8")
    missing = [row for row in APPROVAL_ROW_IDS if re.search(rf"^\| {row} \|", text, re.M) is None]
    return {
        "id": "approval",
        "label": "approval matrix",
        "ok": not missing,
        "code": "approval_complete" if not missing else "approval_incomplete",
        "detail": {"missingRows": missing, "expectedRows": len(APPROVAL_ROW_IDS)},
        "nextStep": "repair .agent-team/APPROVAL.md (matrix changes require user confirmation)",
    }


def check_roster(roster_path: Path) -> dict[str, Any]:
    if not roster_path.exists():
        return {
            "id": "roster",
            "label": "roster and generation",
            "ok": False,
            "code": "roster_missing",
            "detail": [f"{roster_path} missing"],
            "nextStep": "provision preview",
        }
    try:
        roster = team_roster.load_roster(roster_path)
    except tc.TeamToolError as exc:
        return {
            "id": "roster",
            "label": "roster and generation",
            "ok": False,
            "code": "roster_unreadable",
            "detail": [str(exc)],
            "nextStep": "provision preview",
        }
    validation = team_roster.validate_roster(roster)
    return {
        "id": "roster",
        "label": "roster and generation",
        "ok": validation["ok"],
        "code": validation["code"],
        "detail": {
            "generation": roster.get("generation"),
            "errors": validation["errors"],
        },
        "nextStep": "repair roster.json (roster changes require user confirmation)",
    }


def check_topology(project: Path, git_cli: str, roster_path: Path) -> dict[str, Any]:
    """main attach state + six parent worktrees from live Git inventory."""
    try:
        git = tc.SafeGit(git_cli, project)
        git.inspect_config()
        git.require_clean_read()
        inventory = team_provision.parse_worktree_inventory(git)
    except tc.TeamToolError as exc:
        return {
            "id": "topology",
            "label": "main and six parent worktrees",
            "ok": False,
            "code": "git_inventory_failed",
            "detail": [str(exc)],
            "nextStep": "inspect the git boundary error",
        }

    main_state = "attached"
    main_detail = next(
        (entry for entry in inventory.values() if entry["branch"] == "refs/heads/main"), None
    )
    if main_detail is None:
        main_state = "unattached_pending"
        main_detail = {"path": None, "branch": "refs/heads/main", "head": None}

    roster_worktrees: dict[str, str] = {}
    roster_ok = False
    if roster_path.exists():
        try:
            roster = team_roster.load_roster(roster_path)
            roster_ok = team_roster.validate_roster(roster)["ok"]
            if roster_ok:
                for seat in roster["seats"]:
                    roster_worktrees[seat["seat"]] = seat["worktree"]["path"]
        except tc.TeamToolError:
            pass

    seat_states = {}
    if roster_worktrees:
        canonical_inventory = {
            team_provision.canonical_path(path): entry
            for path, entry in inventory.items()
        }
        for seat, path in roster_worktrees.items():
            entry = canonical_inventory.get(team_provision.canonical_path(path))
            seat_states[seat] = {
                "path": path,
                "exists": entry is not None,
                "branch": entry["branch"] if entry else None,
                "head": entry["head"] if entry else None,
            }
    problems = []
    if main_state != "attached":
        problems.append(
            "main branch has no attached worktree (pending atomic attach primitive)"
        )
    if roster_worktrees:
        missing = [seat for seat, state in seat_states.items() if not state["exists"]]
        if missing:
            problems.append(f"missing parent worktrees: {', '.join(missing)}")

    return {
        "id": "topology",
        "label": "main and six parent worktrees",
        "ok": not problems,
        "code": "topology_ready" if not problems else "topology_incomplete",
        "detail": {"mainState": main_state, "seats": seat_states},
        "nextStep": "provision preview",
    }


def check_cli_profiles(
    cli_paths: dict[str, str | None], home: Path, project: Path
) -> dict[str, Any]:
    problems = []
    found: dict[str, str | None] = {}
    for label, raw in cli_paths.items():
        if not raw:
            problems.append(f"cli {label} not found on PATH")
            found[label] = None
            continue
        path = Path(raw)
        if not path.exists() or not path.is_file():
            problems.append(f"cli {label} missing at {raw}")
            found[label] = None
            continue
        found[label] = str(path.resolve())
    mode_check = team_quickstart.check_claude_auto_mode(home, project)
    if not mode_check["ok"]:
        problems.append(mode_check["code"])
    seat_binding = "not_implemented"
    return {
        "id": "cli_profiles",
        "label": "CLI profiles and seat identity",
        "ok": not problems,
        "code": "cli_profiles_ready" if not problems else "cli_profile_issue",
        "detail": {
            "clis": found,
            "claudeAutoMode": mode_check,
            "seatProfileBinding": seat_binding,
        },
        "nextStep": "repair the listed CLI profile, then re-run",
    }


def check_orca(orca_cli: str) -> dict[str, Any]:
    status = team_provision.orca_status(orca_cli)
    ok = status["ready"]
    return {
        "id": "orca",
        "label": "Orca runtime",
        "ok": ok,
        "code": "orca_ready" if ok else status.get("code", "orca_runtime_unavailable"),
        "detail": status.get("payload"),
        "nextStep": (
            None if ok else "open the local Orca app (requires current-user authorization), then re-run"
        ),
    }


def check_identity_self_test(project: str) -> dict[str, Any]:
    """Embedded M4 positive/negative cases against the real verifier code."""
    cases = []
    try:
        with tempfile.TemporaryDirectory(prefix="team-doctor-identity-") as tmp:
            keys_dir = Path(tmp) / "keys"
            roster_path = Path(tmp) / "roster.json"
            generated = team_identity.generate_keys(keys_dir, "fullstack-opencode")
            team_identity.generate_keys(keys_dir, "leader-claude")
            roster = {
                "schemaVersion": 1,
                "generation": 0,
                "leaderBootstrapCommit": "a" * 40,
                "acceptedMainCommit": "a" * 40,
                "mainWorktree": {"path": "/wt/main", "branch": "main", "commit": "a" * 40},
                "seats": [
                    {
                        "seat": "leader-claude",
                        "branch": "leader-claude-integration",
                        "worktree": {"path": "/wt/leader-claude", "orcaWorktreeId": None},
                        "generation": 0,
                        "parent_id": None,
                        "owner": "leader-claude",
                        "public_key_fingerprint": team_identity.public_key_fingerprint(
                            team_identity.serialization.load_pem_public_key(
                                (keys_dir / "leader-claude.pub").read_bytes()
                            )
                        ),
                        "updated_by": "provisioner",
                        "updated_at": "2026-08-17T00:00:00+08:00",
                    },
                    {
                        "seat": "fullstack-opencode",
                        "branch": "fullstack-opencode-integration",
                        "worktree": {"path": "/wt/fullstack-opencode", "orcaWorktreeId": None},
                        "generation": 0,
                        "parent_id": "/wt/leader-claude",
                        "owner": "fullstack-opencode",
                        "public_key_fingerprint": generated["publicKeyFingerprint"],
                        "updated_by": "provisioner",
                        "updated_at": "2026-08-17T00:00:00+08:00",
                    },
                ],
                "updatedAt": "2026-08-17T00:00:00+08:00",
                "updatedBy": "provisioner",
            }
            roster_path.write_text(json.dumps(roster))
            fields = {
                "messageKind": "worker_done",
                "body": "doctor self-test",
                "outcome": "success",
                "artifactRefs": [],
                "commitRefs": [],
            }
            envelope = team_identity.build_envelope(
                fields, "fullstack-opencode", "leader-claude", project, roster, keys_dir / "fullstack-opencode.key"
            )
            positive = team_identity.verify_envelope(envelope, roster, keys_dir)
            cases.append({"case": "positive", "expected": "verify", "result": positive["code"]})

            tampered = json.loads(json.dumps(envelope))
            tampered["sender"]["seat"] = "leader-claude"
            cases.append(
                {
                    "case": "tampered_seat",
                    "expected": "reject",
                    "result": team_identity.verify_envelope(tampered, roster, keys_dir)["code"],
                }
            )
            forged = json.loads(json.dumps(envelope))
            forged["signature"]["value"] = "ab" * 64
            cases.append(
                {
                    "case": "forged_signature",
                    "expected": "reject",
                    "result": team_identity.verify_envelope(forged, roster, keys_dir)["code"],
                }
            )
            stale_roster = json.loads(json.dumps(roster))
            stale_roster["generation"] = 1
            for seat in stale_roster["seats"]:
                seat["generation"] = 1
            cases.append(
                {
                    "case": "stale_generation",
                    "expected": "reject",
                    "result": team_identity.verify_envelope(envelope, stale_roster, keys_dir)["code"],
                }
            )
    except Exception as exc:  # pragma: no cover - environment guard
        return {
            "id": "identity",
            "label": "M4 identity self-test",
            "ok": False,
            "code": "identity_self_test_error",
            "detail": [str(exc)],
            "nextStep": "inspect the identity self-test error",
        }
    failed = [
        case for case in cases
        if (case["case"] == "positive" and case["result"] != "identity_verified")
        or (case["case"] != "positive" and case["result"] != "identity_rejected")
    ]
    return {
        "id": "identity",
        "label": "M4 identity self-test",
        "ok": not failed,
        "code": "identity_cases_pass" if not failed else "identity_cases_fail",
        "detail": cases,
        "nextStep": None if not failed else "inspect the failing identity case",
    }


def check_terminal_readiness(orca_cli: str, roster: dict[str, Any] | None) -> dict[str, Any]:
    code, stdout, _ = tc.orca_run(orca_cli, "terminal", "list", "--json")
    if code != 0:
        return {
            "id": "terminals",
            "label": "terminal readiness",
            "ok": False,
            "code": "terminal_inventory_unavailable",
            "detail": [f"orca terminal list exited {code}"],
            "nextStep": "open the local Orca app, then re-run",
        }
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {
            "id": "terminals",
            "label": "terminal readiness",
            "ok": False,
            "code": "terminal_inventory_invalid",
            "detail": [str(exc)],
            "nextStep": "inspect the orca terminal inventory",
        }
    result_wrapper = payload.get("result") if isinstance(payload, dict) else None
    terminals = (
        result_wrapper.get("terminals", [])
        if isinstance(result_wrapper, dict)
        else (payload.get("terminals", []) if isinstance(payload, dict) else [])
    )
    # Scope to this project's worktrees when a roster exists: other
    # projects' terminals on a shared runtime are not a readiness signal.
    # Terminals bound to the current generation's recorded tab IDs are the
    # EXPECTED live seats; only unrecorded in-scope terminals are a problem.
    recorded_tabs: set[str] = set()
    if roster is not None:
        ids = {
            seat["worktree"]["orcaWorktreeId"]
            for seat in roster.get("seats", [])
            if (seat.get("worktree") or {}).get("orcaWorktreeId")
        }
        paths = {
            team_provision.canonical_path((seat.get("worktree") or {}).get("path", ""))
            for seat in roster.get("seats", [])
            if (seat.get("worktree") or {}).get("path")
        }
        recorded_tabs = {
            seat.get("tabId")
            for seat in roster.get("seats", [])
            if seat.get("tabId")
        }
        terminals = [
            term
            for term in terminals
            if term.get("worktreeId") in ids
            or team_provision.canonical_path(
                str(term.get("worktreePath") or term.get("path") or "")
            )
            in paths
        ]
    unrecorded = [
        term for term in terminals if term.get("tabId") not in recorded_tabs
    ]
    total = len(unrecorded)
    return {
        "id": "terminals",
        "label": "terminal readiness",
        "ok": total == 0,
        "code": "terminals_clean" if total == 0 else "resident_terminals_present",
        "detail": {
            "scopedToProject": roster is not None,
            "recordedSeatTerminals": len(terminals) - total,
            "unrecordedTerminals": total,
        },
        "nextStep": (
            None
            if total == 0
            else "quickstart (generation-bound cleanup) requires user authorization"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--asset", default=str(tc.ASSET_TEAM_PATH))
    parser.add_argument("--meta-path", default=".agent-team/charter-meta.json")
    parser.add_argument("--roster-path", default=".agent-team/roster.json")
    parser.add_argument("--approval-path", default=".agent-team/APPROVAL.md")
    parser.add_argument("--orca-cli", default="/Users/wzy/.homebrew/bin/orca")
    parser.add_argument("--git-cli", default="/usr/bin/git")
    parser.add_argument("--home", default=str(Path.home()))
    for label in ("claude", "codex", "opencode", "claudex", "kimi"):
        parser.add_argument(f"--cli-{label}", default=None)
    args = parser.parse_args()

    project = Path(args.project)
    meta_path = Path(args.meta_path)
    roster_path = Path(args.roster_path)
    approval_path = Path(args.approval_path)
    if not meta_path.is_absolute():
        meta_path = project / meta_path
    if not roster_path.is_absolute():
        roster_path = project / roster_path
    if not approval_path.is_absolute():
        approval_path = project / approval_path

    try:
        roster_for_terminals: dict[str, Any] | None = None
        if roster_path.exists():
            try:
                loaded_roster = team_roster.load_roster(roster_path)
                if team_roster.validate_roster(loaded_roster)["ok"]:
                    roster_for_terminals = loaded_roster
            except tc.TeamToolError:
                pass
        checks = [
            check_charter(project, Path(args.asset), meta_path),
            check_pointers(project),
            check_approval_matrix(approval_path),
            check_runtime_boundary(project),
            check_roster(roster_path),
            check_topology(project, args.git_cli, roster_path),
            check_cli_profiles(
                {
                    "claude": args.cli_claude,
                    "codex": args.cli_codex,
                    "opencode": args.cli_opencode,
                    "claudex": args.cli_claudex,
                    "kimi": args.cli_kimi,
                },
                Path(args.home),
                project,
            ),
            check_orca(args.orca_cli),
            check_terminal_readiness(args.orca_cli, roster_for_terminals),
            check_identity_self_test(str(project)),
        ]
    except tc.TeamToolError as exc:
        tc.emit(
            {"ok": False, "code": "invalid_project", "message": str(exc), "checks": []}, 9
        )
        raise  # unreachable: emit raises SystemExit; keeps the type checker honest
    failing = [check for check in checks if not check["ok"]]
    first_failing = failing[0] if failing else None
    tc.emit(
        {
            "ok": not failing,
            "code": "doctor_all_green" if not failing else "doctor_failed",
            "checks": checks,
            "failingCount": len(failing),
            "nextStep": first_failing["nextStep"] if first_failing else "team quickstart",
        },
        0 if not failing else 3,
    )


if __name__ == "__main__":
    main()
