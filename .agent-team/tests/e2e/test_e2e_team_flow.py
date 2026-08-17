"""Disposable-repository end-to-end suite for the six-seat Team pipeline.

Covers the plan's M7 scenarios: six parent worktrees created, six seats
started, idempotent restart, wrong-generation terminals never cleaned,
no-write handshake, worker_done + acknowledgment full chain, the three M4
negative identity cases, and the approval-refusal path.

The Orca CLI is the stateful mock (mock_orca.py) implementing the documented
future CLI contract; the real 1.4.180 CLI keeps its pending placeholders and
the real-repo pipeline still fails closed. The mock performs real
`git worktree add` on exact branches, so every receipt is verified against
real Git state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from test_team_adopt import make_project, run_helper as adopt_run  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
PROVISION = SCRIPTS / "team_provision.py"
QUICKSTART = SCRIPTS / "team_quickstart.py"
IDENTITY = SCRIPTS / "team_identity.py"
MOCK_ORCA = Path(__file__).resolve().parent / "mock_orca.py"
E2E = Path(__file__).resolve().parent

SEAT_KEYS = (
    "leader-claude",
    "advisor-codex",
    "fullstack-opencode",
    "review-opencode",
    "principal-fullstack-claudex",
    "frontend-kimi",
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


def run_py(script: Path, *argv: str, env: dict[str, str] | None = None) -> tuple[str, str, int]:
    proc = subprocess.run(
        [sys.executable, str(script), *argv],
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, **(env or {})},
    )
    return proc.stdout, proc.stderr, proc.returncode


def mock_state(state_path: Path) -> dict:
    return json.loads(state_path.read_text())


def make_e2e_project(tmp_path: Path, asset: Path) -> tuple[Path, Path, Path, dict]:
    """Adopted disposable project + mock Orca state."""
    project = make_project(tmp_path / "repo", stale=True)
    stdout, _, code = adopt_run(project, "preview", asset)
    assert code == 0
    adopt_run(project, "apply", asset, "--confirm-digest", json.loads(stdout)["confirmDigest"])

    # The approval matrix ships with the repo; the E2E fixture installs it.
    real_approval = Path(__file__).resolve().parents[2] / "APPROVAL.md"
    (project / ".agent-team" / "APPROVAL.md").write_text(real_approval.read_text())

    # Make the disposable project a real git repository with main attached.
    assert git("init", "-q", "-b", "main", str(project), cwd=project.parent).returncode == 0
    assert git("config", "user.email", "e2e@example.invalid", cwd=project).returncode == 0
    assert git("config", "user.name", "E2E Test", cwd=project).returncode == 0
    assert git("add", ".agent-team", "AGENTS.md", "CLAUDE.md", cwd=project).returncode == 0
    assert git("commit", "-qm", "adopt charter", cwd=project).returncode == 0

    base_dir = tmp_path / "worktrees"
    base_dir.mkdir()
    state_path = tmp_path / "orca-state.json"
    state_path.write_text(
        json.dumps(
            {
                "runtime": {"id": "mock-runtime", "ready": True},
                "repos": [{"id": "repo-1", "path": str(project), "worktreeId": "wt-0000"}],
                "worktrees": [
                    {
                        "id": "wt-0000",
                        "repoId": "repo-1",
                        "path": str(project),
                        "branch": "main",
                        "parentId": None,
                        "displayName": None,
                    }
                ],
                "terminals": [],
                "messages": [],
                "counter": 0,
            }
        )
    )

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "auto"}})
    )
    mock_env = {"MOCK_ORCA_STATE": str(state_path)}
    return project, base_dir, home, mock_env


def provision_run(project: Path, base_dir: Path, mock_env: dict, head: str) -> dict:
    stdout, _, code = run_py(
        PROVISION,
        "--project", str(project),
        "--subcommand", "preview",
        "--base-dir", str(base_dir),
        "--git-cli", "/usr/bin/git",
        "--orca-cli", str(MOCK_ORCA),
        "--accepted-commit", head,
        env=mock_env,
    )
    assert code == 0, stdout
    digest = json.loads(stdout)["pathsDigest"]
    stdout, stderr, code = run_py(
        PROVISION,
        "--project", str(project),
        "--subcommand", "run",
        "--base-dir", str(base_dir),
        "--git-cli", "/usr/bin/git",
        "--orca-cli", str(MOCK_ORCA),
        "--accepted-commit", head,
        "--confirm-paths-digest", digest,
        "--mock-orca-contract",
        env=mock_env,
    )
    assert code == 0, stderr
    return json.loads(stdout)


def quickstart_run(project: Path, home: Path, asset: Path, mock_env: dict) -> dict:
    stdout, stderr, code = run_py(
        QUICKSTART,
        "--project", str(project),
        "--asset", str(asset),
        "--roster-path", str(project / ".agent-team" / "roster.json"),
        "--meta-path", str(project / ".agent-team" / "charter-meta.json"),
        "--orca-cli", str(MOCK_ORCA),
        "--home", str(home),
        "--mock-orca-contract",
        env=mock_env,
    )
    assert code == 0, stderr
    return json.loads(stdout)


@pytest.fixture()
def e2e(tmp_path, asset) -> dict:
    tmp = tmp_path
    project, base_dir, home, mock_env = make_e2e_project(tmp, asset)
    head = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    return {
        "tmp": tmp,
        "project": project,
        "base_dir": base_dir,
        "home": home,
        "mock_env": mock_env,
        "asset": asset,
        "head": head,
    }


def test_scenario_a_six_parent_worktrees_created(e2e: dict) -> None:
    result = provision_run(e2e["project"], e2e["base_dir"], e2e["mock_env"], e2e["head"])
    assert result["code"] == "topology_provisioned"
    assert result["rosterPublished"] is True
    assert result["agentsStarted"] is False

    worktrees = git("worktree", "list", "--porcelain", cwd=e2e["project"]).stdout
    assert worktrees.count("worktree ") == 7  # main + six seat parents

    roster = json.loads((e2e["project"] / ".agent-team" / "roster.json").read_text())
    assert roster["generation"] == 0
    assert len(roster["seats"]) == 6
    assert all(seat["worktree"]["orcaWorktreeId"] for seat in roster["seats"])
    leader_orca_id = roster["seats"][0]["worktree"]["orcaWorktreeId"]
    assert roster["seats"][0]["parent_id"] is None
    assert all(seat["parent_id"] == leader_orca_id for seat in roster["seats"][1:])
    # First terminals from worktree creation were all cleaned.
    state = mock_state(e2e["tmp"] / "orca-state.json")
    assert state["terminals"] == []


def test_scenario_b_six_seats_started(e2e: dict) -> None:
    provision_run(e2e["project"], e2e["base_dir"], e2e["mock_env"], e2e["head"])
    result = quickstart_run(e2e["project"], e2e["home"], e2e["asset"], e2e["mock_env"])
    assert result["code"] == "quickstart_generation_published"
    assert result["generation"] == 1

    roster = json.loads((e2e["project"] / ".agent-team" / "roster.json").read_text())
    assert roster["generation"] == 1
    tab_ids = [seat["tabId"] for seat in roster["seats"]]
    handles = [seat["terminalHandle"] for seat in roster["seats"]]
    assert len(set(tab_ids)) == 6 and len(set(handles)) == 6
    claude_seats = {
        seat["seat"]: seat
        for seat in roster["seats"]
        if seat["seat"] in ("leader-claude", "principal-fullstack-claudex")
    }
    assert all(seat["permissionMode"] == "--permission-mode auto" for seat in claude_seats.values())

    state = mock_state(e2e["tmp"] / "orca-state.json")
    assert len(state["terminals"]) == 6
    bound_paths = {
        term["worktreeId"]: term["handle"]
        for term in state["terminals"]
    }
    assert len(bound_paths) == 6


def test_scenario_c_idempotent_restart(e2e: dict) -> None:
    provision_run(e2e["project"], e2e["base_dir"], e2e["mock_env"], e2e["head"])
    quickstart_run(e2e["project"], e2e["home"], e2e["asset"], e2e["mock_env"])
    before = json.loads((e2e["project"] / ".agent-team" / "roster.json").read_text())
    old_tab_ids = {seat["tabId"] for seat in before["seats"]}

    result = quickstart_run(e2e["project"], e2e["home"], e2e["asset"], e2e["mock_env"])
    assert result["code"] == "quickstart_generation_published"
    assert result["generation"] == 2

    after = json.loads((e2e["project"] / ".agent-team" / "roster.json").read_text())
    new_tab_ids = {seat["tabId"] for seat in after["seats"]}
    assert after["generation"] == 2
    assert old_tab_ids.isdisjoint(new_tab_ids)
    state = mock_state(e2e["tmp"] / "orca-state.json")
    assert len(state["terminals"]) == 6
    live_tab_ids = {term["tabId"] for term in state["terminals"]}
    assert live_tab_ids == new_tab_ids


def test_scenario_d_unrecorded_terminal_blocks_cleanup(e2e: dict) -> None:
    provision_run(e2e["project"], e2e["base_dir"], e2e["mock_env"], e2e["head"])
    quickstart_run(e2e["project"], e2e["home"], e2e["asset"], e2e["mock_env"])
    # Inject an unrelated resident terminal: cleanup must fail closed and
    # close nothing.
    state_path = e2e["tmp"] / "orca-state.json"
    state = mock_state(state_path)
    state["terminals"].append(
        {"id": "term-9999", "tabId": "tab-9999", "handle": "term-9999", "worktreeId": "wt-0000"}
    )
    state_path.write_text(json.dumps(state))

    stdout, _, code = run_py(
        QUICKSTART,
        "--project", str(e2e["project"]),
        "--asset", str(e2e["asset"]),
        "--roster-path", str(e2e["project"] / ".agent-team" / "roster.json"),
        "--meta-path", str(e2e["project"] / ".agent-team" / "charter-meta.json"),
        "--orca-cli", str(MOCK_ORCA),
        "--home", str(e2e["home"]),
        "--mock-orca-contract",
        env=e2e["mock_env"],
    )
    assert code == 7
    result = json.loads(stdout)
    assert result["code"] == "team_cleanup_scope_ambiguous"
    # Nothing was closed: 6 resident + 1 injected remain.
    state = mock_state(state_path)
    assert len(state["terminals"]) == 7


def test_scenario_e_no_write_handshake(e2e: dict) -> None:
    provision_run(e2e["project"], e2e["base_dir"], e2e["mock_env"], e2e["head"])
    quickstart_run(e2e["project"], e2e["home"], e2e["asset"], e2e["mock_env"])
    # After the full pipeline, every worktree is clean: the pipeline
    # performed no writes in any seat worktree.
    base = e2e["base_dir"]
    for path in sorted(base.iterdir()):
        if path.is_dir():
            status = git("-C", str(path), "status", "--porcelain", cwd=base)
            assert status.stdout == "", f"unexpected changes in {path}"
    # The roster records receipts only; nothing beyond terminals + roster.
    state = mock_state(e2e["tmp"] / "orca-state.json")
    assert all(
        any(
            term.get("command", "").startswith(cli)
            for cli in ("claude", "codex", "opencode", "claudex", "kimi")
        )
        for term in state["terminals"]
    )


def test_scenario_f_worker_done_and_ack_full_chain(e2e: dict) -> None:
    provision_run(e2e["project"], e2e["base_dir"], e2e["mock_env"], e2e["head"])
    quickstart_run(e2e["project"], e2e["home"], e2e["asset"], e2e["mock_env"])
    quickstart_run(e2e["project"], e2e["home"], e2e["asset"], e2e["mock_env"])
    project = e2e["project"]
    keys_dir = e2e["tmp"] / "keys"
    roster_path = project / ".agent-team" / "roster.json"
    env = dict(e2e["mock_env"])

    # Generate keys for the two seats and record fingerprints (empty -> nonempty).
    fingerprints = {}
    for seat in ("fullstack-opencode", "leader-claude"):
        stdout, _, code = run_py(
            IDENTITY, "--subcommand", "keys", "--seat", seat, "--keys-dir", str(keys_dir)
        )
        assert code == 0
        fingerprints[seat] = json.loads(stdout)["publicKeyFingerprint"]
        stdout, _, code = run_py(
            IDENTITY,
            "--subcommand", "roster-update",
            "--seat", seat,
            "--fingerprint", fingerprints[seat],
            "--roster-path", str(roster_path),
        )
        assert code == 0

    def inject_and_send(sender: str, recipient: str, kind: str, body: str) -> dict:
        fields = e2e["tmp"] / f"fields-{sender}-{kind}.json"
        fields.write_text(json.dumps(
            {"messageKind": kind, "body": body, "outcome": "success", "artifactRefs": [], "commitRefs": []}
        ))
        stdout, stderr, code = run_py(
            IDENTITY,
            "--subcommand", "inject",
            "--seat", sender,
            "--recipient", recipient,
            "--project", str(project),
            "--private-key", str(keys_dir / f"{sender}.key"),
            "--roster-path", str(roster_path),
            "--input", str(fields),
        )
        assert code == 0, stderr
        envelope = json.loads(stdout)["envelope"]
        envelope_file = e2e["tmp"] / f"envelope-{sender}-{kind}.json"
        envelope_file.write_text(json.dumps(envelope))
        _, _, send_code = run_py(
            MOCK_ORCA, "message", "send", "--envelope", str(envelope_file), "--json", env=env
        )
        assert send_code == 0
        return envelope

    def receive_and_verify(seat: str) -> dict:
        recv_out, _, recv_code = run_py(
            MOCK_ORCA, "message", "receive", "--seat", seat, "--json", env=env
        )
        assert recv_code == 0
        messages = json.loads(recv_out)["messages"]
        assert messages
        envelope_file = e2e["tmp"] / f"received-{seat}.json"
        envelope_file.write_text(json.dumps(messages[-1]))
        stdout, _, code = run_py(
            IDENTITY,
            "--subcommand", "verify",
            "--roster-path", str(roster_path),
            "--keys-dir", str(keys_dir),
            "--envelope", str(envelope_file),
        )
        assert code == 0, stdout
        return json.loads(stdout)

    # worker_done: fullstack -> leader.
    worker_done = inject_and_send(
        "fullstack-opencode", "leader-claude", "worker_done", "m7 single-file change complete"
    )
    verified = receive_and_verify("leader-claude")
    assert verified["code"] == "identity_verified"
    assert worker_done["sender"]["generation"] == 2
    assert worker_done["sender"]["seat"] == "fullstack-opencode"

    # acknowledgment: leader -> fullstack, echoing the message id.
    ack = inject_and_send(
        "leader-claude", "fullstack-opencode", "acknowledgment",
        f"ack for {worker_done['messageId']}: delivery verified",
    )
    verified_ack = receive_and_verify("fullstack-opencode")
    assert verified_ack["code"] == "identity_verified"
    assert ack["sender"]["seat"] == "leader-claude"


def test_scenario_g_negative_identity_cases_in_flow(e2e: dict) -> None:
    provision_run(e2e["project"], e2e["base_dir"], e2e["mock_env"], e2e["head"])
    quickstart_run(e2e["project"], e2e["home"], e2e["asset"], e2e["mock_env"])
    project = e2e["project"]
    keys_dir = e2e["tmp"] / "keys"
    roster_path = project / ".agent-team" / "roster.json"

    # Generate the sender key and record its fingerprint (empty -> nonempty).
    stdout, _, code = run_py(
        IDENTITY, "--subcommand", "keys", "--seat", "fullstack-opencode", "--keys-dir", str(keys_dir)
    )
    assert code == 0
    fingerprint = json.loads(stdout)["publicKeyFingerprint"]
    _, _, code = run_py(
        IDENTITY,
        "--subcommand", "roster-update",
        "--seat", "fullstack-opencode",
        "--fingerprint", fingerprint,
        "--roster-path", str(roster_path),
    )
    assert code == 0

    fields = e2e["tmp"] / "fields-neg.json"
    fields.write_text(json.dumps(
        {"messageKind": "worker_done", "body": "negative case", "outcome": "success"}
    ))
    stdout, _, code = run_py(
        IDENTITY,
        "--subcommand", "inject",
        "--seat", "fullstack-opencode",
        "--recipient", "leader-claude",
        "--project", str(project),
        "--private-key", str(keys_dir / "fullstack-opencode.key"),
        "--roster-path", str(roster_path),
        "--input", str(fields),
    )
    assert code == 0
    envelope = json.loads(stdout)["envelope"]

    def verify_envelope(envelope: dict) -> dict:
        envelope_file = e2e["tmp"] / "envelope-neg.json"
        envelope_file.write_text(json.dumps(envelope))
        stdout, _, _ = run_py(
            IDENTITY,
            "--subcommand", "verify",
            "--roster-path", str(roster_path),
            "--keys-dir", str(keys_dir),
            "--envelope", str(envelope_file),
        )
        return json.loads(stdout)

    # Tampered seat.
    tampered = json.loads(json.dumps(envelope))
    tampered["sender"]["seat"] = "frontend-kimi"
    assert verify_envelope(tampered)["code"] == "identity_rejected"

    # Forged signature.
    forged = json.loads(json.dumps(envelope))
    forged["signature"]["value"] = "ab" * 64
    assert verify_envelope(forged)["code"] == "identity_rejected"

    # Stale generation: envelope signed at generation 2 verified against a
    # roster advanced to generation 3.
    stale_roster = json.loads(roster_path.read_text())
    stale_roster["generation"] = 3
    for seat in stale_roster["seats"]:
        seat["generation"] = 3
    stale_path = e2e["tmp"] / "stale-roster.json"
    stale_path.write_text(json.dumps(stale_roster))
    envelope_file = e2e["tmp"] / "envelope-stale.json"
    envelope_file.write_text(json.dumps(envelope))
    stdout, _, _ = run_py(
        IDENTITY,
        "--subcommand", "verify",
        "--roster-path", str(stale_path),
        "--keys-dir", str(keys_dir),
        "--envelope", str(envelope_file),
    )
    result = json.loads(stdout)
    assert result["code"] == "identity_rejected"
    assert any(error["code"] == "stale_generation" for error in result["errors"])


def test_scenario_h_approval_refusal_path(e2e: dict) -> None:
    provision_run(e2e["project"], e2e["base_dir"], e2e["mock_env"], e2e["head"])
    project = e2e["project"]
    base_dir = e2e["base_dir"]
    roster = json.loads((project / ".agent-team" / "roster.json").read_text())

    # Make one seat worktree dirty, then attempt deprovision: refused (AP-21).
    dirty_path = Path(roster["seats"][1]["worktree"]["path"])
    (dirty_path / "uncommitted.txt").write_text("dirty\n")
    stdout, _, code = run_py(
        PROVISION,
        "--project", str(project),
        "--subcommand", "deprovision",
        "--base-dir", str(base_dir),
        "--git-cli", "/usr/bin/git",
        "--orca-cli", str(MOCK_ORCA),
        "--confirm",
        env=e2e["mock_env"],
    )
    assert code == 8
    result = json.loads(stdout)
    assert result["code"] == "dirty_worktree_refused"
    assert str(dirty_path) in result["dirtyWorktrees"]

    # Matrix row coverage is checked by doctor (already covered in unit tests);
    # here assert the AP-21 rule text is present in the matrix.
    approval = (project / ".agent-team" / "APPROVAL.md").read_text()
    assert "AP-21" in approval


def test_scenario_i_rollback_drill(e2e: dict) -> None:
    """M8 rollback drill: charter restore + re-adopt, then deprovision."""
    project = e2e["project"]
    base_dir = e2e["base_dir"]
    provision_run(project, base_dir, e2e["mock_env"], e2e["head"])
    quickstart_run(project, e2e["home"], e2e["asset"], e2e["mock_env"])

    # Charter rollback: restore the v5 backup, observe the mismatch, re-adopt.
    backups = sorted((project / ".agent-team" / "backups").glob("TEAM.md.v5.*.bak"))
    assert backups, "v5 backup must exist after adoption"
    (project / ".agent-team" / "TEAM.md").write_bytes(backups[0].read_bytes())
    check_out, _, check_code = run_py(
        SCRIPTS / "team_adopt.py",
        "--project", str(project),
        "--subcommand", "check",
        "--asset", str(e2e["asset"]),
    )
    assert check_code == 5
    assert json.loads(check_out)["code"] == "charter_mismatch"

    preview_out, _, code = run_py(
        SCRIPTS / "team_adopt.py",
        "--project", str(project),
        "--subcommand", "preview",
        "--asset", str(e2e["asset"]),
    )
    assert code == 0
    apply_out, apply_err, code = run_py(
        SCRIPTS / "team_adopt.py",
        "--project", str(project),
        "--subcommand", "apply",
        "--asset", str(e2e["asset"]),
        "--confirm-digest", json.loads(preview_out)["confirmDigest"],
    )
    assert code == 0, apply_err
    assert json.loads(apply_out)["code"] == "adopted"
    check_out2, _, check_code2 = run_py(
        SCRIPTS / "team_adopt.py",
        "--project", str(project),
        "--subcommand", "check",
        "--asset", str(e2e["asset"]),
    )
    assert check_code2 == 0
    assert json.loads(check_out2)["code"] == "charter_current"

    # Deprovision drill: clean seat worktrees removed, primary main kept,
    # branches kept.
    dep_out, dep_err, dep_code = run_py(
        PROVISION,
        "--project", str(project),
        "--subcommand", "deprovision",
        "--base-dir", str(base_dir),
        "--git-cli", "/usr/bin/git",
        "--orca-cli", str(MOCK_ORCA),
        "--confirm",
        env=e2e["mock_env"],
    )
    assert dep_code == 0, dep_err
    dep_result = json.loads(dep_out)
    assert dep_result["code"] == "deprovisioned"
    assert len(dep_result["removed"]) == 6
    assert dep_result["branchesKept"] is True
    remaining = git("worktree", "list", "--porcelain", cwd=project).stdout
    assert remaining.count("worktree ") == 1
    assert git("show-ref", "--verify", "--quiet", "refs/heads/leader-claude-integration", cwd=project).returncode == 0
