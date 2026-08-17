"""Tests for the quickstart preflight pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_team_adopt import make_project, run_helper as adopt_run

QUICKSTART_HELPER = Path(__file__).resolve().parents[1] / "scripts" / "team_quickstart.py"

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


def adopt_project(project: Path, asset: Path) -> None:
    stdout, _, code = adopt_run(project, "preview", asset)
    assert code == 0
    confirm = json.loads(stdout)["confirmDigest"]
    stdout, stderr, code = adopt_run(project, "apply", asset, "--confirm-digest", confirm)
    assert code == 0, stderr


def make_roster(base_dir: Path, generation: int = 0) -> dict:
    now = "2026-08-17T00:00:00+08:00"
    leader_path = str(base_dir / "leader-claude")
    return {
        "schemaVersion": 1,
        "generation": generation,
        "leaderBootstrapCommit": "a" * 40,
        "acceptedMainCommit": "a" * 40,
        "mainWorktree": {"path": str(base_dir / "main"), "branch": "main", "commit": "a" * 40},
        "seats": [
            {
                "seat": key,
                "branch": branch,
                "worktree": {"path": leader_path if key == "leader-claude" else str(base_dir / key), "orcaWorktreeId": None},
                "generation": generation,
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


def write_orca_ready_stub(base_dir: Path) -> Path:
    stub = base_dir / "orca-stub.sh"
    stub.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  status)\n"
        "    printf '%s\\n' '{\"ok\":true,\"runtimeId\":\"test-runtime\",\"state\":\"ready\"}'\n"
        "    ;;\n"
        "esac\n"
    )
    stub.chmod(0o755)
    return stub


def run_quickstart(project: Path, asset: Path, base_dir: Path, home: Path) -> tuple[str, str, int]:
    proc = subprocess.run(
        [
            sys.executable,
            str(QUICKSTART_HELPER),
            "--project",
            str(project),
            "--asset",
            str(asset),
            "--roster-path",
            str(project / ".agent-team" / "roster.json"),
            "--meta-path",
            str(project / ".agent-team" / "charter-meta.json"),
            "--orca-cli",
            str(base_dir / "orca-stub.sh"),
            "--home",
            str(home),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.stdout, proc.stderr, proc.returncode


def setup_ready_project(tmp_path: Path, asset: Path) -> tuple[Path, Path, Path]:
    project = make_project(tmp_path / "proj", stale=True)
    adopt_project(project, asset)
    base_dir = tmp_path / "worktrees"
    base_dir.mkdir()
    write_orca_ready_stub(base_dir)
    roster = make_roster(base_dir)
    for seat in roster["seats"]:
        Path(seat["worktree"]["path"]).mkdir(parents=True, exist_ok=True)
    Path(roster["mainWorktree"]["path"]).mkdir(parents=True, exist_ok=True)
    (project / ".agent-team" / "roster.json").write_text(json.dumps(roster))
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "auto"}})
    )
    return project, base_dir, home


def test_quickstart_all_preflights_pass_stops_at_session_placeholder(
    tmp_path: Path, asset: Path
) -> None:
    project, base_dir, home = setup_ready_project(tmp_path, asset)
    stdout, stderr, code = run_quickstart(project, asset, base_dir, home)
    assert code == 7
    result = json.loads(stdout)
    assert result["code"] == "start_session_cli_pending"
    assert result["phases"]["charter"]["code"] == "charter_current"
    assert result["phases"]["roster"]["code"] == "roster_valid"
    assert result["phases"]["claudeAutoMode"]["code"] == "claude_auto_mode_ok"
    assert result["phases"]["orca"]["ready"] is True
    assert result["changesApplied"] is False
    assert "PENDING" in result["phases"]["sessionLifecycle"]["placeholder"]


def test_quickstart_fails_on_stale_charter(tmp_path: Path, asset: Path) -> None:
    project = make_project(tmp_path / "proj", stale=True)
    base_dir = tmp_path / "worktrees"
    base_dir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    stdout, _, code = run_quickstart(project, asset, base_dir, home)
    assert code == 7
    result = json.loads(stdout)
    assert result["code"] == "charter_mismatch"
    assert result["nextStep"] == "adopt-team-charter preview"


def test_quickstart_fails_on_missing_topology(tmp_path: Path, asset: Path) -> None:
    project, _, _ = setup_ready_project(tmp_path, asset)
    (project / ".agent-team" / "roster.json").unlink()
    home = tmp_path / "home2"
    home.mkdir()
    base_dir = tmp_path / "worktrees2"
    base_dir.mkdir()
    write_orca_ready_stub(base_dir)
    stdout, _, code = run_quickstart(project, asset, base_dir, home)
    assert code == 7
    result = json.loads(stdout)
    assert result["code"] == "team_worktree_topology_required"
    assert result["nextStep"] == "provision preview"


def test_quickstart_fails_on_missing_worktree_dirs(tmp_path: Path, asset: Path) -> None:
    project, base_dir, home = setup_ready_project(tmp_path, asset)
    roster = json.loads((project / ".agent-team" / "roster.json").read_text())
    missing = base_dir / "advisor-codex"
    missing.mkdir(parents=True, exist_ok=True)
    missing.rmdir()
    roster["seats"][1]["worktree"]["path"] = str(missing)
    (project / ".agent-team" / "roster.json").write_text(json.dumps(roster))
    stdout, _, code = run_quickstart(project, asset, base_dir, home)
    assert code == 7
    assert json.loads(stdout)["code"] == "team_worktree_topology_required"


def test_quickstart_fails_on_non_auto_permission(tmp_path: Path, asset: Path) -> None:
    project, base_dir, home = setup_ready_project(tmp_path, asset)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "bypassPermissions"}})
    )
    stdout, _, code = run_quickstart(project, asset, base_dir, home)
    assert code == 7
    result = json.loads(stdout)
    assert result["code"] == "claude_auto_mode_required"
    assert result["phases"]["claudeAutoMode"]["effectiveMode"] == "bypassPermissions"


def test_quickstart_fails_on_orca_unavailable(tmp_path: Path, asset: Path) -> None:
    project, base_dir, home = setup_ready_project(tmp_path, asset)
    stub = base_dir / "orca-stub.sh"
    stub.write_text("#!/bin/sh\nexit 3\n")
    stub.chmod(0o755)
    stdout, _, code = run_quickstart(project, asset, base_dir, home)
    assert code == 7
    result = json.loads(stdout)
    assert result["code"] == "orca_runtime_unavailable"
    assert result["nextStep"].startswith("open the local Orca app")


def test_claude_auto_mode_resolution_project_overrides_user(tmp_path: Path, asset: Path) -> None:
    project, base_dir, home = setup_ready_project(tmp_path, asset)
    # User surface bypass, project surface auto -> project wins -> ok.
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "bypassPermissions"}})
    )
    (project / ".claude").mkdir()
    (project / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "auto"}})
    )
    stdout, _, code = run_quickstart(project, asset, base_dir, home)
    assert code == 7
    result = json.loads(stdout)
    assert result["code"] == "start_session_cli_pending"
    assert result["phases"]["claudeAutoMode"]["effectiveMode"] == "auto"
