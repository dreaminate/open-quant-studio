"""Tests for message identity injection and verification (M4).

Positive case: inject -> verify passes. Negative cases must all reject:
tampered seat, forged signature, stale generation, tampered body, worktree
mismatch, unknown recipient, fingerprint mismatch, and agent-supplied
tool fields.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "team_identity.py"

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

AGENT_FIELDS = {
    "messageKind": "worker_done",
    "body": "m4 single-file change complete",
    "outcome": "success",
    "artifactRefs": ["apps/web/src/app.tsx"],
    "commitRefs": [],
    "taskId": "T-1",
    "runId": "R-1",
    "dependencyIds": [],
}


def run_identity(*argv: str, stdin: str | None = None) -> tuple[str, str, int]:
    proc = subprocess.run(
        [sys.executable, str(HELPER), *argv],
        capture_output=True,
        text=True,
        timeout=120,
        input=stdin,
    )
    return proc.stdout, proc.stderr, proc.returncode


def parse(stdout: str) -> dict:
    return json.loads(stdout)


def make_roster(fingerprints: dict[str, str], generation: int = 0) -> dict:
    now = "2026-08-17T00:00:00+08:00"
    leader_path = "/worktrees/leader-claude"
    return {
        "schemaVersion": 1,
        "generation": generation,
        "leaderBootstrapCommit": "a" * 40,
        "acceptedMainCommit": "a" * 40,
        "mainWorktree": {"path": "/worktrees/main", "branch": "main", "commit": "a" * 40},
        "seats": [
            {
                "seat": key,
                "branch": branch,
                "worktree": {
                    "path": leader_path if key == "leader-claude" else f"/worktrees/{key}",
                    "orcaWorktreeId": None,
                },
                "generation": generation,
                "parent_id": None if key == "leader-claude" else leader_path,
                "owner": key,
                "public_key_fingerprint": fingerprints.get(key, ""),
                "updated_by": "provisioner",
                "updated_at": now,
            }
            for key, branch in zip(SEAT_KEYS, SEAT_BRANCHES)
        ],
        "updatedAt": now,
        "updatedBy": "provisioner",
    }


class IdentityFixture:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.keys_dir = tmp_path / "keys"
        self.keys_dir.mkdir()
        self.roster_path = tmp_path / "roster.json"
        self.fingerprints: dict[str, str] = {}

    def generate_key(self, seat: str) -> dict:
        stdout, stderr, code = run_identity(
            "--subcommand", "keys", "--seat", seat, "--keys-dir", str(self.keys_dir)
        )
        assert code == 0, stderr
        result = parse(stdout)
        self.fingerprints[seat] = result["publicKeyFingerprint"]
        return result

    def write_roster(self, generation: int = 0, drop_fingerprint: str | None = None) -> None:
        fingerprints = dict(self.fingerprints)
        if drop_fingerprint:
            fingerprints[drop_fingerprint] = ""
        self.roster_path.write_text(json.dumps(make_roster(fingerprints, generation)))

    def inject(self, seat: str, recipient: str = "leader-claude", fields: dict | None = None) -> dict:
        fields_path = self.tmp / "fields.json"
        fields_path.write_text(json.dumps(AGENT_FIELDS if fields is None else fields))
        stdout, stderr, code = run_identity(
            "--subcommand",
            "inject",
            "--seat",
            seat,
            "--recipient",
            recipient,
            "--project",
            "/worktrees",
            "--private-key",
            str(self.keys_dir / f"{seat}.key"),
            "--roster-path",
            str(self.roster_path),
            "--input",
            str(fields_path),
        )
        assert code == 0, stderr
        result = parse(stdout)
        assert result["ok"] is True
        return result["envelope"]

    def verify(self, envelope: dict) -> dict:
        envelope_path = self.tmp / "envelope.json"
        envelope_path.write_text(json.dumps(envelope))
        stdout, _, _ = run_identity(
            "--subcommand",
            "verify",
            "--roster-path",
            str(self.roster_path),
            "--keys-dir",
            str(self.keys_dir),
            "--envelope",
            str(envelope_path),
        )
        return parse(stdout)


@pytest.fixture()
def fixture(tmp_path: Path) -> IdentityFixture:
    return IdentityFixture(tmp_path)


def test_positive_verify_passes(fixture: IdentityFixture) -> None:
    fixture.generate_key("fullstack-opencode")
    fixture.generate_key("leader-claude")
    fixture.write_roster()
    envelope = fixture.inject("fullstack-opencode")
    result = fixture.verify(envelope)
    assert result["ok"] is True
    assert result["code"] == "identity_verified"


def test_tampered_seat_rejected(fixture: IdentityFixture) -> None:
    fixture.generate_key("fullstack-opencode")
    fixture.generate_key("leader-claude")
    fixture.generate_key("frontend-kimi")
    fixture.write_roster()
    envelope = fixture.inject("fullstack-opencode")
    envelope["sender"]["seat"] = "frontend-kimi"
    result = fixture.verify(envelope)
    assert result["ok"] is False
    assert result["code"] == "identity_rejected"
    assert any(e["code"] in ("sender_worktree_mismatch", "sender_seat_unknown", "fingerprint_mismatch") for e in result["errors"])


def test_forged_signature_rejected(fixture: IdentityFixture) -> None:
    fixture.generate_key("fullstack-opencode")
    fixture.generate_key("leader-claude")
    fixture.write_roster()
    envelope = fixture.inject("fullstack-opencode")
    envelope["signature"]["value"] = "ab" * 64
    result = fixture.verify(envelope)
    assert result["ok"] is False
    assert any(e["code"] == "signature_invalid" for e in result["errors"])


def test_stale_generation_rejected(fixture: IdentityFixture) -> None:
    fixture.generate_key("fullstack-opencode")
    fixture.generate_key("leader-claude")
    fixture.write_roster()
    envelope = fixture.inject("fullstack-opencode")
    # Roster advances one generation; the old envelope must be rejected.
    fixture.write_roster(generation=1)
    result = fixture.verify(envelope)
    assert result["ok"] is False
    assert any(e["code"] == "stale_generation" for e in result["errors"])


def test_tampered_body_rejected(fixture: IdentityFixture) -> None:
    fixture.generate_key("fullstack-opencode")
    fixture.generate_key("leader-claude")
    fixture.write_roster()
    envelope = fixture.inject("fullstack-opencode")
    envelope["body"] = "tampered body"
    result = fixture.verify(envelope)
    assert result["ok"] is False
    assert any(e["code"] == "signature_invalid" for e in result["errors"])


def test_worktree_mismatch_rejected(fixture: IdentityFixture) -> None:
    fixture.generate_key("fullstack-opencode")
    fixture.generate_key("leader-claude")
    fixture.write_roster()
    envelope = fixture.inject("fullstack-opencode")
    envelope["sender"]["worktree"]["path"] = "/worktrees/someone-else"
    result = fixture.verify(envelope)
    assert result["ok"] is False
    assert any(e["code"] == "sender_worktree_mismatch" for e in result["errors"])


def test_unknown_recipient_rejected(fixture: IdentityFixture) -> None:
    fixture.generate_key("fullstack-opencode")
    fixture.generate_key("leader-claude")
    fixture.write_roster()
    envelope = fixture.inject("fullstack-opencode")
    envelope["recipient"]["seat"] = "rogue-seat"
    result = fixture.verify(envelope)
    assert result["ok"] is False
    assert any(e["code"] == "recipient_seat_unknown" for e in result["errors"])


def test_fingerprint_mismatch_rejected(fixture: IdentityFixture) -> None:
    fixture.generate_key("fullstack-opencode")
    fixture.generate_key("leader-claude")
    fixture.write_roster()
    envelope = fixture.inject("fullstack-opencode")
    envelope["signature"]["publicKeyFingerprint"] = "cd" * 32
    result = fixture.verify(envelope)
    assert result["ok"] is False
    assert any(e["code"] == "fingerprint_mismatch" for e in result["errors"])


def test_missing_roster_fingerprint_rejected(fixture: IdentityFixture) -> None:
    fixture.generate_key("fullstack-opencode")
    fixture.generate_key("leader-claude")
    fixture.write_roster(drop_fingerprint="fullstack-opencode")
    envelope = fixture.inject("fullstack-opencode")
    result = fixture.verify(envelope)
    assert result["ok"] is False
    assert any(e["code"] == "fingerprint_missing" for e in result["errors"])


def test_agent_cannot_supply_tool_fields(fixture: IdentityFixture) -> None:
    fixture.generate_key("fullstack-opencode")
    fixture.generate_key("leader-claude")
    fixture.write_roster()
    fields = {**AGENT_FIELDS, "sender": {"seat": "leader-claude"}}
    fields_path = fixture.tmp / "fields.json"
    fields_path.write_text(json.dumps(fields))
    stdout, _, code = run_identity(
        "--subcommand",
        "inject",
        "--seat",
        "fullstack-opencode",
        "--recipient",
        "leader-claude",
        "--project",
        "/worktrees",
        "--private-key",
        str(fixture.keys_dir / "fullstack-opencode.key"),
        "--roster-path",
        str(fixture.roster_path),
        "--input",
        str(fields_path),
    )
    assert code == 9
    assert parse(stdout)["code"] == "identity_error"


def test_keys_generate_creates_0600_and_refuses_overwrite(fixture: IdentityFixture) -> None:
    result = fixture.generate_key("advisor-codex")
    private_path = fixture.keys_dir / "advisor-codex.key"
    assert private_path.stat().st_mode & 0o777 == 0o600
    assert (fixture.keys_dir / "advisor-codex.pub").exists()
    assert len(result["publicKeyFingerprint"]) == 64

    stdout, _, code = run_identity(
        "--subcommand", "keys", "--seat", "advisor-codex", "--keys-dir", str(fixture.keys_dir)
    )
    assert code == 9
    assert "already exist" in parse(stdout)["message"]


def test_roster_update_empty_to_nonempty_then_refuses_rotation(fixture: IdentityFixture) -> None:
    fixture.write_roster()
    new_fingerprint = fixture.generate_key("frontend-kimi")["publicKeyFingerprint"]

    stdout, _, code = run_identity(
        "--subcommand",
        "roster-update",
        "--seat",
        "frontend-kimi",
        "--fingerprint",
        new_fingerprint,
        "--roster-path",
        str(fixture.roster_path),
    )
    assert code == 0, stdout
    roster = json.loads(fixture.roster_path.read_text())
    entry = next(seat for seat in roster["seats"] if seat["seat"] == "frontend-kimi")
    assert entry["public_key_fingerprint"] == new_fingerprint
    assert entry["updated_by"] == "provisioner"

    # Changing a nonempty fingerprint is rotation -> refused (generation rule).
    other = fixture.generate_key("review-opencode")["publicKeyFingerprint"]
    stdout, _, code = run_identity(
        "--subcommand",
        "roster-update",
        "--seat",
        "frontend-kimi",
        "--fingerprint",
        other,
        "--roster-path",
        str(fixture.roster_path),
    )
    assert code == 9
    assert "fingerprint_rotation_requires_generation_increment" in parse(stdout)["message"]


def test_keys_rejects_unknown_seat(fixture: IdentityFixture) -> None:
    stdout, _, code = run_identity(
        "--subcommand", "keys", "--seat", "rogue-seat", "--keys-dir", str(fixture.keys_dir)
    )
    assert code == 9
    assert "unknown seat key" in parse(stdout)["message"]
