"""Tests for team doctor --json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from test_team_adopt import make_project, run_helper as adopt_run

DOCTOR_HELPER = Path(__file__).resolve().parents[1] / "scripts" / "team_doctor.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_APPROVAL = REPO_ROOT / ".agent-team" / "APPROVAL.md"

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


def git(*argv: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/usr/bin/git", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "HOME": os.environ["HOME"]},
    )


def run_doctor(project: Path, base_dir: Path, home: Path, asset: Path, *extra: str) -> tuple[str, str, int]:
    argv = [
        sys.executable,
        str(DOCTOR_HELPER),
        "--project",
        str(project),
        "--asset",
        str(asset),
        "--roster-path",
        str(project / ".agent-team" / "roster.json"),
        "--meta-path",
        str(project / ".agent-team" / "charter-meta.json"),
        "--approval-path",
        str(project / ".agent-team" / "APPROVAL.md"),
        "--orca-cli",
        str(base_dir / "orca-stub.sh"),
        "--git-cli",
        "/usr/bin/git",
        "--home",
        str(home),
        *extra,
    ]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    return proc.stdout, proc.stderr, proc.returncode


def write_orca_stub(base_dir: Path) -> None:
    stub = base_dir / "orca-stub.sh"
    stub.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  status)\n"
        "    printf '%s\\n' '{\"ok\":true,\"result\":{\"app\":{\"running\":true},\"runtime\":{\"state\":\"ready\",\"reachable\":true,\"runtimeId\":\"test-runtime\"}}}'\n"
        "    ;;\n"
        "  terminal)\n"
        "    printf '%s\\n' '{\"ok\":true,\"totalCount\":0,\"terminals\":[]}'\n"
        "    ;;\n"
        "esac\n"
    )
    stub.chmod(0o755)


def make_roster(base_dir: Path) -> dict:
    now = "2026-08-17T00:00:00+08:00"
    leader_path = str(base_dir / "leader-claude")
    return {
        "schemaVersion": 1,
        "generation": 0,
        "leaderBootstrapCommit": "a" * 40,
        "acceptedMainCommit": "a" * 40,
        "mainWorktree": {"path": str(base_dir / "main"), "branch": "main", "commit": "a" * 40},
        "seats": [
            {
                "seat": key,
                "branch": branch,
                "worktree": {
                    "path": leader_path if key == "leader-claude" else str(base_dir / key),
                    "orcaWorktreeId": None,
                },
                "generation": 0,
                "parent_id": None if key == "leader-claude" else leader_path,
                "owner": key,
                "public_key_fingerprint": "",
                "updated_by": "provisioner",
                "updated_at": now,
            }
            for key, branch in zip(SEAT_KEYS, SEAT_BRANCHES)
        ],
        "updatedAt": now,
        "updatedBy": "provisioner",
    }


def build_full_fixture(tmp_path: Path, asset: Path) -> tuple[Path, Path, Path]:
    """Adopted charter + real git topology with all seven worktrees + green CLI/orca."""
    project = make_project(tmp_path / "proj", stale=True)
    adopt_run(project, "preview", asset)
    stdout, _, code = adopt_run(project, "preview", asset)
    assert code == 0
    confirm = json.loads(stdout)["confirmDigest"]
    _, stderr, code = adopt_run(project, "apply", asset, "--confirm-digest", confirm)
    assert code == 0, stderr

    base_dir = tmp_path / "worktrees"
    base_dir.mkdir()
    write_orca_stub(base_dir)

    # Real git topology: repo primary on master; main + six seat worktrees.
    git("init", "-q", "-b", "master", str(project), cwd=project.parent)
    git("config", "user.email", "t@e.invalid", cwd=project)
    git("config", "user.name", "T", cwd=project)
    head_file = project / "probe.txt"
    head_file.write_text("x\n")
    git("add", "probe.txt", cwd=project)
    git("commit", "-qm", "fixture", cwd=project)
    head = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    git("branch", "main", head, cwd=project)
    for branch in SEAT_BRANCHES:
        git("branch", branch, head, cwd=project)
    git("worktree", "add", str(base_dir / "main"), "main", cwd=project)
    for key, branch in zip(SEAT_KEYS, SEAT_BRANCHES):
        git("worktree", "add", str(base_dir / key), branch, cwd=project)

    roster = make_roster(base_dir)
    roster["leaderBootstrapCommit"] = head
    roster["acceptedMainCommit"] = head
    roster["mainWorktree"]["commit"] = head
    (project / ".agent-team" / "roster.json").write_text(json.dumps(roster))
    (project / ".agent-team" / "APPROVAL.md").write_text(REAL_APPROVAL.read_text())

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "auto"}})
    )
    return project, base_dir, home


GREEN_CLI_ARGS = (
    "--cli-claude", "/bin/ls", "--cli-codex", "/bin/ls",
    "--cli-opencode", "/bin/ls", "--cli-claudex", "/bin/ls", "--cli-kimi", "/bin/ls",
)


def test_doctor_all_green_on_full_fixture(tmp_path: Path, asset: Path) -> None:
    project, base_dir, home = build_full_fixture(tmp_path, asset)
    stdout, stderr, code = run_doctor(project, base_dir, home, asset, *GREEN_CLI_ARGS)
    assert code == 0, stderr
    result = json.loads(stdout)
    assert result["code"] == "doctor_all_green"
    assert result["failingCount"] == 0
    codes = {check["id"]: check["code"] for check in result["checks"]}
    assert codes["charter"] == "charter_current"
    assert codes["pointers"] == "pointers_canonical"
    assert codes["approval"] == "approval_complete"
    assert codes["roster"] == "roster_valid"
    assert codes["topology"] == "topology_ready"
    assert codes["cli_profiles"] == "cli_profiles_ready"
    assert codes["orca"] == "orca_ready"
    assert codes["terminals"] == "terminals_clean"
    assert codes["identity"] == "identity_cases_pass"
    assert result["nextStep"] == "team quickstart"


def test_doctor_fails_with_navigable_codes_when_roster_missing(tmp_path: Path, asset: Path) -> None:
    project, base_dir, home = build_full_fixture(tmp_path, asset)
    (project / ".agent-team" / "roster.json").unlink()
    stdout, _, code = run_doctor(project, base_dir, home, asset)
    assert code == 3
    result = json.loads(stdout)
    assert result["code"] == "doctor_failed"
    codes = {check["id"]: check["code"] for check in result["checks"]}
    assert codes["roster"] == "roster_missing"
    assert result["nextStep"] == "provision preview"
    # Charter/pointers/approval/identity still green even when topology fails.
    assert codes["charter"] == "charter_current"
    assert codes["pointers"] == "pointers_canonical"
    assert codes["approval"] == "approval_complete"
    assert codes["identity"] == "identity_cases_pass"


def test_doctor_identity_cases_reject_tampering(tmp_path: Path, asset: Path) -> None:
    project, base_dir, home = build_full_fixture(tmp_path, asset)
    stdout, _, code = run_doctor(project, base_dir, home, asset, *GREEN_CLI_ARGS)
    assert code == 0
    result = json.loads(stdout)
    identity = next(check for check in result["checks"] if check["id"] == "identity")
    cases = {case["case"]: case["result"] for case in identity["detail"]}
    assert cases["positive"] == "identity_verified"
    assert cases["tampered_seat"] == "identity_rejected"
    assert cases["forged_signature"] == "identity_rejected"
    assert cases["stale_generation"] == "identity_rejected"


def test_doctor_rejects_non_auto_claude_mode(tmp_path: Path, asset: Path) -> None:
    project, base_dir, home = build_full_fixture(tmp_path, asset)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "acceptEdits"}})
    )
    stdout, _, code = run_doctor(project, base_dir, home, asset, *GREEN_CLI_ARGS)
    assert code == 3
    result = json.loads(stdout)
    cli = next(check for check in result["checks"] if check["id"] == "cli_profiles")
    assert cli["ok"] is False
