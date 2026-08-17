"""Tests for the adopt-team-charter helper (preview / apply / check)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "team_adopt.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_MIGRATION_MAP = REPO_ROOT / ".agent-team" / "migration-map.md"
ZSH_ENTRY = REPO_ROOT / ".agent-team" / "adopt-team-charter.zsh"

OLD_POINTER = b"""<!-- init-project-agent-team:pointer:begin -->
**Agent Team:** Before starting or repairing the fixed six-seat Team, or creating Tasks, dispatching work, executing, coordinating, reviewing, or accepting Team work, read and follow [`.agent-team/TEAM.md`](.agent-team/TEAM.md) in full.
<!-- init-project-agent-team:pointer:end -->
"""

CANONICAL_POINTER = b"""<!-- init-project-agent-team:pointer:begin -->
**Agent Team:** Before initializing or repairing the `main` or logical `team` bootstrap worktrees; creating or managing Team worktrees or agents; starting, restarting, cleaning, or repairing the fixed six-seat Team; changing `.agent-team/TEAM.md` or its Git-tracked rules; or creating Tasks, dispatching work, executing, coordinating, reviewing, integrating, or accepting Team work, read and follow [`.agent-team/TEAM.md`](.agent-team/TEAM.md) in full.
<!-- init-project-agent-team:pointer:end -->
"""

ASSET_CONTENT = (
    b"# Fixed Six-Seat Agent Team\n"
    b"\n"
    b"## Scope\n\ncanonical scope\n\n"
    b"## Fixed Roster\n\ncanonical roster\n\n"
    b"## Review and Acceptance\n\ncanonical review\n"
)

BOUNDARY_BLOCK = b"""<!-- agent-team-runtime-boundary:begin -->
**Team runtime boundary:** The Orca six-seat Agent Team is a development
collaboration control plane only. It does not enter the OQS product runtime,
does not constitute a second product AgentLoop, and Pi remains the only
AgentLoop inside the product. Team tooling never ships, deploys, or executes
inside product processes. Pre-release check: `team doctor --json` all green
plus the E2E suite passing.
<!-- agent-team-runtime-boundary:end -->
"""

STALE_CHARTER = (
    b"# Fixed Six-Seat Agent Team\n"
    b"\n"
    b"<!-- init-project-agent-team:charter-version=5 -->\n"
    b"\n"
    b"## Scope\n\nold scope\n\n"
    b"## Fixed Roster\n\nold roster\n\n"
    b"## Review and Acceptance\n\nold review\n"
)


def run_helper(project: Path, subcommand: str, asset: Path, *extra: str) -> tuple[str, str, int]:
    proc = subprocess.run(
        [
            sys.executable,
            str(HELPER),
            "--project",
            str(project),
            "--subcommand",
            subcommand,
            "--asset",
            str(asset),
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.stdout, proc.stderr, proc.returncode


def make_project(tmp_path: Path, stale: bool = True) -> Path:
    project = tmp_path / "proj"
    agent_team = project / ".agent-team"
    agent_team.mkdir(parents=True)
    (agent_team / "TEAM.md").write_bytes(STALE_CHARTER if stale else ASSET_CONTENT)
    (agent_team / "migration-map.md").write_bytes(REAL_MIGRATION_MAP.read_bytes())
    if stale:
        (project / "AGENTS.md").write_bytes(
            b"# Project agents\n\nSome local instructions.\n\n" + BOUNDARY_BLOCK + b"\n" + OLD_POINTER
        )
        (project / "CLAUDE.md").write_bytes(OLD_POINTER)
    else:
        (project / "AGENTS.md").write_bytes(
            b"# Project agents\n\nSome local instructions.\n\n" + BOUNDARY_BLOCK + b"\n" + CANONICAL_POINTER
        )
        (project / "CLAUDE.md").write_bytes(CANONICAL_POINTER)
    return project


def parse(stdout: str) -> dict:
    return json.loads(stdout)


def test_preview_detects_stale_charter_and_pointers(tmp_path: Path, asset: Path) -> None:
    project = make_project(tmp_path, stale=True)
    agents_before = (project / "AGENTS.md").read_bytes()
    charter_before = (project / ".agent-team" / "TEAM.md").read_bytes()

    stdout, stderr, code = run_helper(project, "preview", asset)

    assert code == 0, stderr
    result = parse(stdout)
    assert result["ok"] is True
    assert result["code"] == "preview_ready"
    assert result["charter"]["current"] is False
    assert result["charter"]["diffSummary"]["linesRemoved"] > 0
    assert result["charter"]["diffSummary"]["linesAdded"] > 0
    targets = {entry["name"]: entry for entry in result["pointerTargets"]}
    assert targets["AGENTS.md"]["willChange"] is True
    assert targets["AGENTS.md"]["status"] == "update_pointer"
    assert targets["CLAUDE.md"]["willChange"] is True
    assert result["migrationMap"]["coverage"]["complete"] is True
    assert result["migrationMap"]["coverage"]["missingRules"] == []
    assert result["migrationMap"]["coverage"]["expectedRules"] == 24
    assert result["migrationMap"]["coverage"]["coveredRules"] == 24
    assert result["migrationMap"]["coverage"]["duplicatedRules"] == []
    assert result["migrationMap"]["coverage"]["unknownRuleIds"] == []
    assert result["backupPlan"]["required"] is True
    assert len(result["backupPlan"]["files"]) == 3
    assert result["confirmDigest"]
    # Preview is read-only.
    assert (project / "AGENTS.md").read_bytes() == agents_before
    assert (project / ".agent-team" / "TEAM.md").read_bytes() == charter_before
    assert not (project / ".agent-team" / "charter-meta.json").exists()


def test_preview_no_changes_when_current(tmp_path: Path, asset: Path) -> None:
    project = make_project(tmp_path, stale=False)
    stdout, stderr, code = run_helper(project, "preview", asset)
    assert code == 0, stderr
    result = parse(stdout)
    assert result["code"] == "preview_no_changes"
    assert result["charter"]["current"] is True
    assert result["backupPlan"]["required"] is False


def test_apply_roundtrip(tmp_path: Path, asset: Path) -> None:
    project = make_project(tmp_path, stale=True)
    stdout, _, code = run_helper(project, "preview", asset)
    assert code == 0
    confirm = parse(stdout)["confirmDigest"]

    stdout, stderr, code = run_helper(project, "apply", asset, "--confirm-digest", confirm)
    assert code == 0, stderr
    result = parse(stdout)
    assert result["code"] == "adopted"
    assert result["changesApplied"] is True
    assert result["rulesReloadRequired"] is True

    # Charter is byte-identical to the canonical asset.
    assert (project / ".agent-team" / "TEAM.md").read_bytes() == ASSET_CONTENT
    # Pointers replaced; surrounding content preserved.
    agents = (project / "AGENTS.md").read_bytes()
    assert agents.startswith(b"# Project agents\n\nSome local instructions.\n\n")
    assert BOUNDARY_BLOCK in agents
    assert agents.endswith(CANONICAL_POINTER)
    assert (project / "CLAUDE.md").read_bytes() == CANONICAL_POINTER
    # Meta written with the right fields.
    meta = json.loads((project / ".agent-team" / "charter-meta.json").read_text())
    assert meta["contractVersion"] == 6
    assert meta["charterSha256"] == result["meta"]["charterSha256"]
    assert meta["adoptedFrom"]["oldCharterSha256"]
    # Backups exist for all three changed targets.
    backups = list((project / ".agent-team" / "backups").iterdir())
    assert len(backups) == 3

    # Idempotent second apply reports already_adopted (fresh preview digest).
    stdout_preview, _, _ = run_helper(project, "preview", asset)
    new_confirm = parse(stdout_preview)["confirmDigest"]
    stdout2, _, code2 = run_helper(project, "apply", asset, "--confirm-digest", new_confirm)
    assert code2 == 0
    assert parse(stdout2)["code"] == "already_adopted"

    # check now reports charter_current.
    stdout3, _, code3 = run_helper(project, "check", asset)
    assert code3 == 0
    result3 = parse(stdout3)
    assert result3["code"] == "charter_current"
    assert result3["current"]["contractVersion"] == 6


def test_apply_rejects_wrong_digest(tmp_path: Path, asset: Path) -> None:
    project = make_project(tmp_path, stale=True)
    stdout, _, code = run_helper(
        project, "apply", asset, "--confirm-digest", "0" * 64
    )
    assert code == 9
    assert parse(stdout)["code"] == "confirm_digest_mismatch"
    assert (project / ".agent-team" / "TEAM.md").read_bytes() == STALE_CHARTER
    assert not (project / ".agent-team" / "charter-meta.json").exists()


def test_apply_detects_drift_after_preview(tmp_path: Path, asset: Path) -> None:
    project = make_project(tmp_path, stale=True)
    stdout, _, code = run_helper(project, "preview", asset)
    assert code == 0
    confirm = parse(stdout)["confirmDigest"]

    # Drift between preview and apply: pointer file edited by someone else.
    (project / "AGENTS.md").write_bytes(b"# Project agents\n\nedited\n\n" + OLD_POINTER)

    stdout, _, code = run_helper(project, "apply", asset, "--confirm-digest", confirm)
    assert code == 9
    assert parse(stdout)["code"] == "confirm_digest_mismatch"
    assert not (project / ".agent-team" / "backups").exists()


def test_check_reports_mismatch(tmp_path: Path, asset: Path) -> None:
    project = make_project(tmp_path, stale=True)
    stdout, stderr, code = run_helper(project, "check", asset)
    assert code == 5
    result = parse(stdout)
    assert result["code"] == "charter_mismatch"
    assert result["current"]["charterSha256"] != result["expected"]["charterSha256"]
    assert result["diffSummary"]["linesAdded"] > 0
    assert result["nextStep"] == "adopt-team-charter preview"


def test_preview_fails_closed_on_symlink_charter(tmp_path: Path, asset: Path) -> None:
    project = make_project(tmp_path, stale=True)
    charter = project / ".agent-team" / "TEAM.md"
    charter.unlink()
    charter.symlink_to(asset)

    stdout, _, code = run_helper(project, "preview", asset)
    assert code == 9
    assert parse(stdout)["code"] == "invalid_project"


def test_zsh_entry_check_runs(tmp_path: Path, asset: Path) -> None:
    project = make_project(tmp_path, stale=False)
    # A current charter without charter-meta.json is reported as missing meta.
    proc = subprocess.run(
        ["/bin/zsh", "-f", str(ZSH_ENTRY), "check", "--asset", str(asset)],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PATH": os.environ["PATH"]},
    )
    assert proc.returncode == 5, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["code"] == "charter_current_meta_missing"

    # apply on the current charter repairs the missing meta, then check exits 0.
    preview = subprocess.run(
        ["/bin/zsh", "-f", str(ZSH_ENTRY), "preview", "--asset", str(asset)],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PATH": os.environ["PATH"]},
    )
    assert preview.returncode == 0
    confirm = json.loads(preview.stdout)["confirmDigest"]
    applied = subprocess.run(
        ["/bin/zsh", "-f", str(ZSH_ENTRY), "apply", "--confirm-digest", confirm, "--asset", str(asset)],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PATH": os.environ["PATH"]},
    )
    assert applied.returncode == 0, applied.stderr

    proc2 = subprocess.run(
        ["/bin/zsh", "-f", str(ZSH_ENTRY), "check", "--asset", str(asset)],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PATH": os.environ["PATH"]},
    )
    assert proc2.returncode == 0, proc2.stderr
    payload2 = json.loads(proc2.stdout)
    assert payload2["code"] == "charter_current"


def test_zsh_entry_apply_requires_digest(tmp_path: Path, asset: Path) -> None:
    project = make_project(tmp_path, stale=True)
    proc = subprocess.run(
        ["/bin/zsh", "-f", str(ZSH_ENTRY), "apply", "--asset", str(asset)],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PATH": os.environ["PATH"]},
    )
    assert proc.returncode == 2
    assert "confirm-digest" in proc.stderr


def test_fresh_install_creates_charter_and_pointers(tmp_path: Path, asset: Path) -> None:
    project = tmp_path / "fresh"
    project.mkdir()

    # Without the flag: fail closed with a navigable error.
    stdout, _, code = run_helper(project, "preview", asset)
    assert code == 9
    assert "charter_missing_requires_fresh_install" in parse(stdout)["message"]

    # Fresh-install preview plans creation targets.
    stdout, _, code = run_helper(project, "preview", asset, "--fresh-install")
    assert code == 0
    result = parse(stdout)
    assert result["code"] == "preview_fresh_install"
    targets = {entry["name"]: entry for entry in result["pointerTargets"]}
    assert targets["AGENTS.md"]["status"] == "create_pointer"
    assert targets["CLAUDE.md"]["status"] == "create_pointer"

    # Apply creates the charter and both pointer files.
    stdout, stderr, code = run_helper(
        project, "apply", asset, "--fresh-install", "--confirm-digest", result["confirmDigest"]
    )
    assert code == 0, stderr
    applied = parse(stdout)
    assert applied["code"] == "adopted"
    assert (project / ".agent-team" / "TEAM.md").read_bytes() == ASSET_CONTENT
    assert (project / "AGENTS.md").read_bytes() == CANONICAL_POINTER
    assert (project / "CLAUDE.md").read_bytes() == CANONICAL_POINTER

    stdout, _, code = run_helper(project, "check", asset)
    assert code == 0
    assert parse(stdout)["code"] == "charter_current"
