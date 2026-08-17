#!/usr/bin/env python3
"""Message identity injection and verification for the six-seat Team.

Subcommands:

- `keys generate`  — create one seat Ed25519 key pair in the user key
  directory (private key mode 0600, never overwrites); prints the public key
  fingerprint (sha256 over the raw 32-byte public key).
- `inject`         — take agent-provided message fields (kind, recipient,
  body, outcome, refs) and build a signed envelope. Sender identity is never
  taken from the message content: it comes from `--seat` plus the roster
  entry (worktree, branch, generation). The model may not self-report.
- `verify`         — check an envelope against the roster: signature valid,
  fingerprint matches the roster, sender generation equals the current
  roster generation, sender worktree/branch match, recipient exists and
  matches. Any mismatch rejects the message without execution.
- `roster-update`  — set one seat's public_key_fingerprint in roster.json
  (empty -> nonempty only; changing a nonempty fingerprint requires a
  generation increment and is refused here).

Signature scheme: Ed25519 over the canonical JSON of the envelope without the
signature field (sorted keys, compact separators). Depends on the `cryptography`
package (present in the runtime environment, v48.0.0).

Normative rules live in `.agent-team/TEAM.md`; this helper implements only
the injection/verification mechanics.
"""

from __future__ import annotations

import argparse
import datetime
import json
import secrets
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import team_common as tc  # noqa: E402
from cryptography.exceptions import InvalidSignature  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

ENVELOPE_VERSION = 1
SIGNATURE_SCHEME = "ed25519"
SEAT_KEYS = (
    "leader-claude",
    "advisor-codex",
    "fullstack-opencode",
    "review-opencode",
    "principal-fullstack-claudex",
    "frontend-kimi",
)

# Fields the tool injects; the agent must never supply these.
TOOL_INJECTED_FIELDS = (
    "envelopeVersion",
    "project",
    "messageId",
    "sender",
    "recipient",
    "injectedAt",
    "signature",
)

# Fields the agent supplies.
AGENT_FIELDS = (
    "messageKind",
    "body",
    "outcome",
    "artifactRefs",
    "commitRefs",
    "taskId",
    "dispatchId",
    "runId",
    "dependencyIds",
)


class IdentityError(Exception):
    pass


def canonical_bytes(envelope: dict[str, Any]) -> bytes:
    """Canonical form of an envelope without its signature field."""
    payload = {key: value for key, value in envelope.items() if key != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def public_key_fingerprint(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return tc.bytes_sha256(raw)


def load_roster(roster_path: Path) -> dict[str, Any]:
    try:
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise IdentityError(f"roster unreadable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise IdentityError(f"roster invalid json: {exc}") from exc
    seats = roster.get("seats")
    if not isinstance(seats, list):
        raise IdentityError("roster has no seats list")
    return roster


def seat_entry(roster: dict[str, Any], seat_key: str) -> dict[str, Any]:
    for seat in roster["seats"]:
        if seat.get("seat") == seat_key:
            return seat
    raise IdentityError(f"seat unknown in roster: {seat_key}")


def generate_keys(keys_dir: Path, seat_key: str) -> dict[str, Any]:
    if seat_key not in SEAT_KEYS:
        raise IdentityError(f"unknown seat key: {seat_key} (canonical keys: {', '.join(SEAT_KEYS)})")
    keys_dir.mkdir(parents=True, exist_ok=True)
    if keys_dir.is_symlink() or not keys_dir.is_dir():
        raise IdentityError(f"keys directory is not a real directory: {keys_dir}")

    private_path = keys_dir / f"{seat_key}.key"
    public_path = keys_dir / f"{seat_key}.pub"
    if private_path.exists() or public_path.exists():
        raise IdentityError(f"key files already exist for {seat_key}; generation is manual and refused")

    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    tc.write_new_file(private_path, private_pem, 0o600)
    tc.write_new_file(public_path, public_pem, 0o644)
    return {
        "seat": seat_key,
        "privateKeyPath": str(private_path),
        "publicKeyPath": str(public_path),
        "publicKeyFingerprint": public_key_fingerprint(key.public_key()),
    }


def build_envelope(
    agent_fields: dict[str, Any],
    seat_key: str,
    recipient_seat: str,
    project_path: str,
    roster: dict[str, Any],
    private_key_path: Path,
) -> dict[str, Any]:
    if seat_key not in SEAT_KEYS or recipient_seat not in SEAT_KEYS:
        raise IdentityError("sender and recipient must be canonical seat keys")
    sender = seat_entry(roster, seat_key)
    recipient = seat_entry(roster, recipient_seat)

    unknown = set(agent_fields) - set(AGENT_FIELDS)
    if unknown:
        raise IdentityError(f"agent supplied tool-injected fields: {sorted(unknown)}")
    if not agent_fields.get("messageKind") or not str(agent_fields.get("body", "")).strip():
        raise IdentityError("messageKind and a nonempty body are required")

    for ref_field in ("artifactRefs", "commitRefs", "dependencyIds"):
        if ref_field in agent_fields and not isinstance(agent_fields[ref_field], list):
            raise IdentityError(f"{ref_field} must be a list")

    envelope: dict[str, Any] = {
        "envelopeVersion": ENVELOPE_VERSION,
        "project": project_path,
        "messageId": secrets.token_hex(16),
        "messageKind": agent_fields["messageKind"],
        "sender": {
            "seat": seat_key,
            "worktree": sender["worktree"],
            "branch": sender["branch"],
            "generation": sender["generation"],
        },
        "recipient": {
            "seat": recipient_seat,
            "worktree": recipient["worktree"],
            "branch": recipient["branch"],
        },
        "injectedAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "body": agent_fields["body"],
        "outcome": agent_fields.get("outcome"),
    }
    for optional in ("artifactRefs", "commitRefs", "taskId", "dispatchId", "runId", "dependencyIds"):
        if agent_fields.get(optional):
            envelope[optional] = agent_fields[optional]

    try:
        loaded_key = serialization.load_pem_private_key(
            private_key_path.read_bytes(), password=None
        )
    except (OSError, ValueError) as exc:
        raise IdentityError(f"private key unreadable: {exc}") from exc
    if not isinstance(loaded_key, Ed25519PrivateKey):
        raise IdentityError("private key must be an Ed25519 key")
    private_key: Ed25519PrivateKey = loaded_key
    signature = private_key.sign(canonical_bytes(envelope))
    fingerprint = public_key_fingerprint(private_key.public_key())
    envelope["signature"] = {
        "scheme": SIGNATURE_SCHEME,
        "publicKeyFingerprint": fingerprint,
        "value": signature.hex(),
    }
    return envelope


def verify_envelope(
    envelope: dict[str, Any],
    roster: dict[str, Any],
    keys_dir: Path,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    def fail(code: str, detail: str) -> None:
        errors.append({"code": code, "detail": detail})

    if envelope.get("envelopeVersion") != ENVELOPE_VERSION:
        fail("envelope_version", "envelopeVersion must be 1")
    sender = envelope.get("sender")
    if not isinstance(sender, dict):
        fail("sender_missing", "sender missing")
        sender = {}
    recipient = envelope.get("recipient")
    if not isinstance(recipient, dict):
        fail("recipient_missing", "recipient missing")
        recipient = {}

    sender_seat = sender.get("seat")
    try:
        roster_sender = seat_entry(roster, str(sender_seat))
    except IdentityError as exc:
        roster_sender = None
        fail("sender_seat_unknown", str(exc))

    if roster_sender is not None:
        roster_generation = roster["generation"]
        if sender.get("generation") != roster_generation:
            fail(
                "stale_generation",
                f"envelope {sender.get('generation')!r} vs roster {roster_generation!r}",
            )
        if (sender.get("worktree") or {}).get("path") != (roster_sender.get("worktree") or {}).get(
            "path"
        ):
            fail(
                "sender_worktree_mismatch",
                f"envelope {(sender.get('worktree') or {}).get('path')!r} vs roster "
                f"{(roster_sender.get('worktree') or {}).get('path')!r}",
            )
        if sender.get("branch") != roster_sender.get("branch"):
            fail(
                "sender_branch_mismatch",
                f"envelope {sender.get('branch')!r} vs roster {roster_sender.get('branch')!r}",
            )

        fingerprint = roster_sender.get("public_key_fingerprint", "")
        signature = envelope.get("signature")
        if not fingerprint:
            fail("fingerprint_missing", "roster has no fingerprint for this seat")
        elif not isinstance(signature, dict) or signature.get("publicKeyFingerprint") != fingerprint:
            fail("fingerprint_mismatch", "signature fingerprint does not match the roster")
        else:
            public_path = keys_dir / f"{sender_seat}.pub"
            if not public_path.exists():
                fail("public_key_missing", f"no public key at {public_path}")
            else:
                try:
                    loaded_public = serialization.load_pem_public_key(public_path.read_bytes())
                    if not isinstance(loaded_public, Ed25519PublicKey):
                        raise IdentityError(f"{public_path} is not an Ed25519 public key")
                    loaded_public.verify(
                        bytes.fromhex(signature["value"]), canonical_bytes(envelope)
                    )
                except (ValueError, InvalidSignature, TypeError, IdentityError):
                    fail("signature_invalid", "signature verification failed")

    recipient_seat = recipient.get("seat")
    try:
        roster_recipient = seat_entry(roster, str(recipient_seat))
    except IdentityError:
        roster_recipient = None
        fail("recipient_seat_unknown", f"recipient seat unknown: {recipient_seat!r}")
    if roster_recipient is not None:
        recipient_worktree = recipient.get("worktree")
        if recipient_worktree is not None and recipient_worktree.get("path") != (
            roster_recipient.get("worktree") or {}
        ).get("path"):
            fail("recipient_worktree_mismatch", "recipient worktree does not match the roster")
        if recipient.get("branch") not in (None, roster_recipient.get("branch")):
            fail("recipient_branch_mismatch", "recipient branch does not match the roster")

    if not envelope.get("messageId") or not str(envelope.get("body", "")).strip():
        fail("envelope_incomplete", "messageId and a nonempty body are required")

    return {
        "ok": not errors,
        "code": "identity_verified" if not errors else "identity_rejected",
        "errors": errors,
    }


def roster_update_fingerprint(
    roster_path: Path, seat_key: str, fingerprint: str
) -> dict[str, Any]:
    roster = load_roster(roster_path)
    entry = seat_entry(roster, seat_key)
    current = entry.get("public_key_fingerprint", "")
    if fingerprint and not (len(fingerprint) == 64 and all(c in "0123456789abcdef" for c in fingerprint)):
        raise IdentityError("fingerprint must be a 64-hex sha256 or empty")
    if current and current != fingerprint:
        raise IdentityError(
            "fingerprint_rotation_requires_generation_increment: rotating a key means a new "
            "seat generation; initial provisioning (empty -> nonempty) only"
        )
    entry["public_key_fingerprint"] = fingerprint
    entry["updated_by"] = "provisioner"
    entry["updated_at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    roster["updatedBy"] = "provisioner"
    roster["updatedAt"] = entry["updated_at"]
    roster_bytes = (
        json.dumps(roster, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    tc.atomic_replace_file(roster_path, roster_bytes)
    return {"ok": True, "code": "roster_fingerprint_updated", "seat": seat_key, "fingerprint": fingerprint}


def load_envelope(path: Path | None) -> dict[str, Any]:
    try:
        data = sys.stdin.read() if path is None else path.read_text(encoding="utf-8")
        envelope = json.loads(data)
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityError(f"envelope unreadable: {exc}") from exc
    if not isinstance(envelope, dict):
        raise IdentityError("envelope must be a JSON object")
    return envelope


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subcommand", required=True, choices=("keys", "inject", "verify", "roster-update"))
    parser.add_argument("--seat")
    parser.add_argument("--roster-path", default=".agent-team/roster.json")
    parser.add_argument("--keys-dir")
    parser.add_argument("--project")
    parser.add_argument("--private-key")
    parser.add_argument("--recipient")
    parser.add_argument("--input", help="agent-fields JSON file for inject (stdin if omitted)")
    parser.add_argument("--envelope", help="envelope JSON file for verify (stdin if omitted)")
    parser.add_argument("--fingerprint")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.subcommand == "keys":
            if not args.seat or not args.keys_dir:
                raise IdentityError("keys requires --seat and --keys-dir")
            result = generate_keys(Path(args.keys_dir), args.seat)
            result["nextStep"] = "record the fingerprint in roster.json (roster-update) and commit roster separately"
            tc.emit({**result, "ok": True, "code": "keys_generated"}, 0)
        elif args.subcommand == "inject":
            if not args.seat or not args.recipient or not args.project or not args.private_key:
                raise IdentityError("inject requires --seat --recipient --project --private-key")
            roster_path = Path(args.roster_path)
            if not roster_path.is_absolute():
                roster_path = Path(args.project) / roster_path
            roster = load_roster(roster_path)
            agent_fields = load_envelope(Path(args.input) if args.input else None)
            envelope = build_envelope(
                agent_fields,
                args.seat,
                args.recipient,
                args.project,
                roster,
                Path(args.private_key),
            )
            tc.emit({"ok": True, "code": "envelope_signed", "envelope": envelope}, 0)
        elif args.subcommand == "verify":
            if not args.roster_path or not args.keys_dir:
                raise IdentityError("verify requires --roster-path and --keys-dir")
            roster = load_roster(Path(args.roster_path))
            envelope = load_envelope(Path(args.envelope) if args.envelope else None)
            result = verify_envelope(envelope, roster, Path(args.keys_dir))
            tc.emit(result, 0 if result["ok"] else 6)
        elif args.subcommand == "roster-update":
            if not args.roster_path or not args.seat or not args.fingerprint:
                raise IdentityError("roster-update requires --roster-path --seat --fingerprint")
            result = roster_update_fingerprint(Path(args.roster_path), args.seat, args.fingerprint)
            tc.emit(result, 0)
    except IdentityError as exc:
        tc.emit(
            {"ok": False, "code": "identity_error", "message": str(exc), "changesApplied": False},
            9,
        )


if __name__ == "__main__":
    try:
        main()
    except ImportError as exc:  # pragma: no cover - environment dependency guard
        tc.emit(
            {
                "ok": False,
                "code": "identity_error",
                "message": f"cryptography package unavailable; message identity requires Ed25519 support: {exc}",
                "changesApplied": False,
            },
            9,
        )
