"""Tests for the provisioner and the roster validator."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "team_provision.py"
ROSTER_HELPER = Path(__file__).resolve().parents[1] / "scripts" / "team_roster.py"

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


def init_repo(path: Path, branch: str = "main") -> tuple[Path, str]:
    path.mkdir(parents=True, exist_ok=True)
    assert git("init", "-b", branch, str(path), cwd=path.parent).returncode == 0
    assert git("config", "user.email", "test@example.invalid", cwd=path).returncode == 0
    assert git("config", "user.name", "Test User", cwd=path).returncode == 0
    (path / "file.txt").write_text("content\n")
    assert git("add", "file.txt", cwd=path).returncode == 0
    assert git("commit", "-m", "base", cwd=path).returncode == 0
    head = git("rev-parse", "HEAD", cwd=path).stdout.strip()
    return path, head


def run_helper(project: Path, subcommand: str, base_dir: Path, *extra: str) -> tuple[str, str, int]:
    proc = subprocess.run(
        [
            sys.executable,
            str(HELPER),
            "--project",
            str(project),
            "--subcommand",
            subcommand,
            "--base-dir",
            str(base_dir),
            "--git-cli",
            "/usr/bin/git",
            "--orca-cli",
            str(base_dir / "orca-stub.sh"),
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.stdout, proc.stderr, proc.returncode


def parse(stdout: str) -> dict:
    return json.loads(stdout)


def write_orca_stub(base_dir: Path, *, ready: bool, repo_path: str | None = None) -> Path:
    stub = base_dir / "orca-stub.sh"
    lines = ["#!/bin/sh"]
    if ready:
        lines.append('case "$1" in')
        lines.append("  status)")
        lines.append('    printf \'%s\\n\' \'{"ok":true,"runtimeId":"test-runtime","state":"ready"}\'')
        lines.append("    ;;")
        lines.append("  repo)")
        lines.append(f'    printf \'%s\\n\' \'{{"repos":[{{"id":"repo-1","worktreeId":"wt-1","path":"{repo_path}"}}]}}\'')
        lines.append("    ;;")
        lines.append("esac")
    else:
        lines.append('printf \'%s\\n\' \'{"ok":false,"runtimeId":null,"state":"not_running"}\'')
        lines.append("exit 1")
    stub.write_text("\n".join(lines) + "\n")
    stub.chmod(0o755)
    return stub


def test_preview_main_attached_no_seat_branches(tmp_path: Path) -> None:
    project, head = init_repo(tmp_path / "repo")
    base_dir = tmp_path / "worktrees"
    base_dir.mkdir()
    write_orca_stub(base_dir, ready=False)

    stdout, _, code = run_helper(project, "preview", base_dir)
    assert code == 0
    result = parse(stdout)
    assert result["code"] == "preview_ready"
    assert result["main"]["state"] == "existing_worktree"
    assert result["main"]["existingWorktreePath"] == str(project)
    assert result["main"]["commit"] == head
    leader = result["seats"]["leader-claude"]
    assert leader["branchExists"] is False
    assert result["plannedCreates"] == {
        "main": False,
        "leaderBranch": True,
        "teamWorktree": True,
        "employeeWorktrees": list(SEAT_KEYS[1:]),
    }
    assert result["firstBlockingCode"] == "team_create_cli_pending"
    assert result["pathsDigest"]


def test_preview_main_unattached_stops_at_attach_placeholder(tmp_path: Path) -> None:
    project, head = init_repo(tmp_path / "repo", branch="master")
    # main branch exists, no worktree checks it out.
    assert git("branch", "main", head, cwd=project).returncode == 0
    base_dir = tmp_path / "worktrees"
    base_dir.mkdir()
    write_orca_stub(base_dir, ready=False)

    stdout, _, code = run_helper(project, "preview", base_dir)
    assert code == 0
    result = parse(stdout)
    assert result["main"]["state"] == "existing_unattached_branch"
    assert result["main"]["action"] == "attach_pending"
    assert result["firstBlockingCode"] == "main_attach_pending"
    assert result["main"]["placeholder"]


def test_run_creates_leader_branch_then_stops_at_orca(tmp_path: Path) -> None:
    project, head = init_repo(tmp_path / "repo")
    base_dir = tmp_path / "worktrees"
    base_dir.mkdir()
    write_orca_stub(base_dir, ready=False)

    stdout, _, code = run_helper(project, "preview", base_dir, "--accepted-commit", head)
    assert code == 0
    digest = parse(stdout)["pathsDigest"]

    stdout, stderr, code = run_helper(
        project, "run", base_dir, "--confirm-paths-digest", digest, "--accepted-commit", head
    )
    assert code == 7
    result = parse(stdout)
    assert result["code"] == "orca_runtime_unavailable"
    assert result["changesApplied"] is True
    assert any(m["kind"] == "leader_branch_created" for m in result["mutations"])
    # The Leader branch was created at the accepted commit; no worktree created.
    assert git("rev-parse", "leader-claude-integration", cwd=project).stdout.strip() == head
    worktrees = git("worktree", "list", "--porcelain", cwd=project).stdout
    assert worktrees.count("worktree ") == 1
    assert result["agentsStarted"] is False


def test_run_existing_leader_branch_requires_provenance(tmp_path: Path) -> None:
    project, head = init_repo(tmp_path / "repo")
    assert git("branch", "leader-claude-integration", head, cwd=project).returncode == 0
    base_dir = tmp_path / "worktrees"
    base_dir.mkdir()
    write_orca_stub(base_dir, ready=False)

    # Preview without provenance, then run without provenance: the digest binds
    # exactly what was shown, and the run fails closed at the missing receipt.
    stdout, _, code = run_helper(project, "preview", base_dir, "--accepted-commit", head)
    digest = parse(stdout)["pathsDigest"]
    stdout, _, code = run_helper(
        project, "run", base_dir, "--confirm-paths-digest", digest, "--accepted-commit", head
    )
    assert code == 7
    assert parse(stdout)["code"] == "leader_branch_baseline_unverified"

    # With provenance in the plan: a fresh preview binds it, then the run
    # proceeds past the provenance gate to the Orca phase.
    stdout, _, code = run_helper(
        project,
        "preview",
        base_dir,
        "--accepted-commit",
        head,
        "--leader-bootstrap-commit",
        head,
    )
    digest2 = parse(stdout)["pathsDigest"]
    stdout, _, code = run_helper(
        project,
        "run",
        base_dir,
        "--confirm-paths-digest",
        digest2,
        "--accepted-commit",
        head,
        "--leader-bootstrap-commit",
        head,
    )
    assert code == 7
    assert parse(stdout)["code"] == "orca_runtime_unavailable"


def test_run_stops_at_team_placeholder_when_orca_ready(tmp_path: Path) -> None:
    project, head = init_repo(tmp_path / "repo")
    base_dir = tmp_path / "worktrees"
    base_dir.mkdir()
    write_orca_stub(base_dir, ready=True, repo_path=str(project))

    stdout, _, code = run_helper(project, "preview", base_dir, "--accepted-commit", head)
    digest = parse(stdout)["pathsDigest"]

    stdout, _, code = run_helper(
        project,
        "run",
        base_dir,
        "--confirm-paths-digest",
        digest,
        "--accepted-commit",
        head,
    )
    assert code == 7
    result = parse(stdout)
    assert result["code"] == "team_create_cli_pending"
    # Leader branch was created in phase 2, then the documented CLI gap stopped phase 4.
    assert any(m["kind"] == "leader_branch_created" for m in result["mutations"])
    assert result["rosterPublished"] is False


def test_run_rejects_wrong_digest(tmp_path: Path) -> None:
    project, head = init_repo(tmp_path / "repo")
    base_dir = tmp_path / "worktrees"
    base_dir.mkdir()
    write_orca_stub(base_dir, ready=False)

    stdout, _, code = run_helper(
        project, "run", base_dir, "--confirm-paths-digest", "0" * 64, "--accepted-commit", head
    )
    assert code == 7
    assert parse(stdout)["code"] == "confirm_digest_mismatch"
    # Zero mutation.
    assert git("show-ref", "--verify", "--quiet", "refs/heads/leader-claude-integration", cwd=project).returncode == 1


def test_run_requires_accepted_commit_for_creation(tmp_path: Path) -> None:
    project, _ = init_repo(tmp_path / "repo")
    base_dir = tmp_path / "worktrees"
    base_dir.mkdir()
    write_orca_stub(base_dir, ready=False)

    stdout, _, code = run_helper(project, "preview", base_dir)
    digest = parse(stdout)["pathsDigest"]
    stdout, _, code = run_helper(project, "run", base_dir, "--confirm-paths-digest", digest)
    assert code == 7
    assert parse(stdout)["code"] == "rules_object_not_accepted"


def test_deprovision_refuses_dirty_then_removes_clean(tmp_path: Path) -> None:
    project, head = init_repo(tmp_path / "repo", branch="master")
    assert git("branch", "main", head, cwd=project).returncode == 0
    assert git("branch", "leader-claude-integration", head, cwd=project).returncode == 0
    base_dir = tmp_path / "worktrees"
    base_dir.mkdir()
    main_wt = base_dir / "main"
    leader_wt = base_dir / "leader-claude"
    assert git("worktree", "add", str(main_wt), "main", cwd=project).returncode == 0
    assert git("worktree", "add", str(leader_wt), "leader-claude-integration", cwd=project).returncode == 0

    roster = {
        "schemaVersion": 1,
        "generation": 0,
        "leaderBootstrapCommit": head,
        "acceptedMainCommit": head,
        "mainWorktree": {"path": str(main_wt), "branch": "main", "commit": head},
        "seats": [
            {
                "seat": key,
                "branch": branch,
                "worktree": {"path": str(leader_wt if key == "leader-claude" else base_dir / key), "orcaWorktreeId": None},
                "generation": 0,
                "parent_id": None if key == "leader-claude" else str(leader_wt),
                "owner": key,
                "public_key_fingerprint": "",
                "updated_by": "provisioner",
                "updated_at": "2026-08-17T00:00:00+08:00",
            }
            for key, branch in zip(SEAT_KEYS, SEAT_BRANCHES)
        ],
        "updatedAt": "2026-08-17T00:00:00+08:00",
        "updatedBy": "provisioner",
    }
    (project / ".agent-team").mkdir(exist_ok=True)
    (project / ".agent-team" / "roster.json").write_text(json.dumps(roster))

    # Without --confirm: refused.
    stdout, _, code = run_helper(project, "deprovision", base_dir)
    assert code == 8
    assert parse(stdout)["code"] == "deprovision_requires_confirm"

    # Dirty worktree: refused even with --confirm.
    (leader_wt / "dirty.txt").write_text("uncommitted\n")
    stdout, _, code = run_helper(project, "deprovision", base_dir, "--confirm")
    assert code == 8
    result = parse(stdout)
    assert result["code"] == "dirty_worktree_refused"
    assert result["dirtyWorktrees"] == [str(leader_wt)]

    # Clean: removed.
    (leader_wt / "dirty.txt").unlink()
    stdout, stderr, code = run_helper(project, "deprovision", base_dir, "--confirm")
    assert code == 0, stderr
    result = parse(stdout)
    assert result["code"] == "deprovisioned"
    assert sorted(result["removed"]) == sorted([str(main_wt), str(leader_wt)])
    worktrees = git("worktree", "list", "--porcelain", cwd=project).stdout
    assert worktrees.count("worktree ") == 1
    assert str(main_wt) not in worktrees and str(leader_wt) not in worktrees
    # Branches kept.
    assert git("show-ref", "--verify", "--quiet", "refs/heads/main", cwd=project).returncode == 0


# ---------------------------------------------------------------------------
# Roster validator
# ---------------------------------------------------------------------------


def roster_helper(roster: dict, tmp_path: Path) -> dict:
    path = tmp_path / "roster.json"
    path.write_text(json.dumps(roster))
    proc = subprocess.run(
        [sys.executable, str(ROSTER_HELPER), "--roster-path", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return {"returncode": proc.returncode, **json.loads(proc.stdout)}


def make_roster(leader_path: str = "/tmp/wt/leader-claude") -> dict:
    now = "2026-08-17T00:00:00+08:00"
    return {
        "schemaVersion": 1,
        "generation": 0,
        "leaderBootstrapCommit": "a" * 40,
        "acceptedMainCommit": "a" * 40,
        "mainWorktree": {"path": "/tmp/wt/main", "branch": "main", "commit": "a" * 40},
        "seats": [
            {
                "seat": key,
                "branch": branch,
                "worktree": {"path": leader_path if key == "leader-claude" else f"/tmp/wt/{key}", "orcaWorktreeId": None},
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


def test_roster_validator_accepts_valid(tmp_path: Path) -> None:
    result = roster_helper(make_roster(), tmp_path)
    assert result["returncode"] == 0
    assert result["code"] == "roster_valid"


def test_roster_validator_rejects_mismatched_generation(tmp_path: Path) -> None:
    roster = make_roster()
    roster["seats"][2]["generation"] = 1
    result = roster_helper(roster, tmp_path)
    assert result["returncode"] == 5
    assert result["code"] == "roster_invalid"
    assert any("generation" in error for error in result["errors"])


def test_roster_validator_rejects_wrong_branch(tmp_path: Path) -> None:
    roster = make_roster()
    roster["seats"][0]["branch"] = "leader-claude-integration-other"
    result = roster_helper(roster, tmp_path)
    assert result["returncode"] == 5
    assert any("branch" in error for error in result["errors"])


def test_roster_validator_rejects_bad_parent(tmp_path: Path) -> None:
    roster = make_roster()
    roster["seats"][1]["parent_id"] = None
    result = roster_helper(roster, tmp_path)
    assert result["returncode"] == 5
    assert any("parent_id" in error for error in result["errors"])


def test_roster_validator_rejects_missing_seat(tmp_path: Path) -> None:
    roster = make_roster()
    roster["seats"] = roster["seats"][:5]
    result = roster_helper(roster, tmp_path)
    assert result["returncode"] == 5


def test_roster_validator_rejects_bad_fingerprint(tmp_path: Path) -> None:
    roster = make_roster()
    roster["seats"][0]["public_key_fingerprint"] = "not-hex"
    result = roster_helper(roster, tmp_path)
    assert result["returncode"] == 5
    assert any("fingerprint" in error for error in result["errors"])


def test_write_initial_roster_generation_zero(tmp_path: Path) -> None:
    sys.path.insert(0, str(HELPER.parent))
    import team_roster  # noqa: PLC0415

    project, head = init_repo(tmp_path / "repo")
    base_dir = tmp_path / "worktrees"
    plan = {
        "main": {"commit": head, "existingWorktreePath": str(project), "plannedPath": str(base_dir / "main")},
        "seats": {
            key: {
                "existingWorktreePath": str(base_dir / key) if key == "leader-claude" else None,
                "plannedPath": str(base_dir / key),
            }
            for key in SEAT_KEYS
        },
        "leaderBootstrapCommit": head,
    }
    mutations = [{"kind": "leader_branch_created", "leaderBootstrapCommit": head}]
    roster_path = project / ".agent-team" / "roster.json"
    (project / ".agent-team").mkdir(exist_ok=True)
    result = team_roster.write_initial_roster(project, roster_path, plan, mutations)
    assert result["ok"] is True
    assert result["code"] == "roster_published"
    roster = result["roster"]
    assert roster["generation"] == 0
    assert len(roster["seats"]) == 6
    assert all(seat["generation"] == 0 for seat in roster["seats"])
    assert roster["leaderBootstrapCommit"] == head
    assert roster["seats"][0]["parent_id"] is None
    leader_path = str(base_dir / "leader-claude")
    assert roster["seats"][0]["worktree"]["path"] == leader_path
    assert all(seat["parent_id"] == leader_path for seat in roster["seats"][1:])
    assert all(seat["public_key_fingerprint"] == "" for seat in roster["seats"])

    # The persisted file passes the standalone validator.
    validation = team_roster.validate_roster(
        json.loads(roster_path.read_text(encoding="utf-8"))
    )
    assert validation["ok"] is True

    # A second initial write is refused: generation increments are not
    # initial provisioning.
    second = team_roster.write_initial_roster(project, roster_path, plan, mutations)
    assert second["ok"] is False
    assert second["code"] == "roster_already_exists"
