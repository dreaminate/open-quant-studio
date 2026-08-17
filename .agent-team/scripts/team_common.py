#!/usr/bin/env python3
"""Shared helpers for the repo-local Agent Team tooling.

This module implements only input/output mechanics. All normative Team rules
live in `.agent-team/TEAM.md`; this file must not duplicate or paraphrase them.

The atomic-write and digest conventions follow the canonical global
`init-project-agent-team` helpers, so adopt/provision results stay comparable
with the initializer's receipts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

INIT_SKILL_ROOT = Path("/Users/wzy/.codex/skills/init-project-agent-team")
QUICK_START_ROOT = Path("/Users/wzy/.codex/skills/quick-team-agent-start")
ASSET_TEAM_PATH = INIT_SKILL_ROOT / "assets" / "TEAM.md"

POINTER_BEGIN = b"<!-- init-project-agent-team:pointer:begin -->"
POINTER_END = b"<!-- init-project-agent-team:pointer:end -->"
POINTER_BLOCK = b"""<!-- init-project-agent-team:pointer:begin -->
**Agent Team:** Before initializing or repairing the `main` or logical `team` bootstrap worktrees; creating or managing Team worktrees or agents; starting, restarting, cleaning, or repairing the fixed six-seat Team; changing `.agent-team/TEAM.md` or its Git-tracked rules; or creating Tasks, dispatching work, executing, coordinating, reviewing, integrating, or accepting Team work, read and follow [`.agent-team/TEAM.md`](.agent-team/TEAM.md) in full.
<!-- init-project-agent-team:pointer:end -->
"""

# Machine-readable charter fields. The authoritative revision record is the
# content digest plus the Git object tuple; the semantic numbers are pointers.
CONTRACT_VERSION = 6
MIN_LAUNCHER_VERSION = 1

# Labels for the launcher contract manifest. The file set mirrors the
# initializer's "quick/*" manifest entries so digests stay comparable.
LAUNCHER_MANIFEST_ENTRIES = (
    ("quick/SKILL.md", QUICK_START_ROOT / "SKILL.md"),
    ("quick/start-team.zsh", QUICK_START_ROOT / "scripts" / "start-team.zsh"),
    ("quick/recovery.md", QUICK_START_ROOT / "references" / "recovery.md"),
    ("quick/team-runtime.md", QUICK_START_ROOT / "references" / "team-runtime.md"),
)

# xattr names that carry ACL semantics; their presence fails the write closed.
ACL_XATTR_NAMES = (b"com.apple.acl", b"system.posix_acl_access", b"system.posix_acl_default")


class TeamToolError(Exception):
    """A managed target or boundary check failed; the caller fails closed."""


def emit(payload: dict[str, Any], exit_code: int) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(exit_code)


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_sha256(entries: list[tuple[str, Path]]) -> str:
    """Content-addressed manifest over (label, path) pairs.

    Same framing as the initializer's skill contract digest: label length +
    label + content length + content, per entry, in order.
    """
    digest = hashlib.sha256()
    for label, path in entries:
        content = path.read_bytes()
        label_bytes = label.encode("utf-8")
        digest.update(len(label_bytes).to_bytes(4, "big"))
        digest.update(label_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def launcher_contract_sha256() -> str:
    return manifest_sha256(list(LAUNCHER_MANIFEST_ENTRIES))


def directory_identity(path: Path) -> dict[str, Any]:
    """Canonical identity of an existing directory, for drift detection."""
    supplied = Path(path)
    if not supplied.is_absolute():
        raise TeamToolError(f"project path must be absolute: {supplied}")
    try:
        canonical = supplied.resolve(strict=True)
        status = canonical.stat()
    except OSError as exc:
        raise TeamToolError(f"directory unavailable: {exc}") from exc
    if not stat.S_ISDIR(status.st_mode):
        raise TeamToolError(f"not a directory: {canonical}")
    return {
        "path": str(canonical),
        "device": status.st_dev,
        "inode": status.st_ino,
    }


def executable_identity(raw_path: str, label: str) -> dict[str, Any]:
    supplied = Path(raw_path)
    if not supplied.is_absolute():
        raise TeamToolError(f"{label} executable path must be absolute")
    try:
        canonical = supplied.resolve(strict=True)
        executable_status = canonical.stat()
    except OSError as exc:
        raise TeamToolError(f"{label} executable is unavailable: {exc}") from exc
    if not stat.S_ISREG(executable_status.st_mode) or not os.access(canonical, os.X_OK):
        raise TeamToolError(f"{label} executable must resolve to an executable regular file")
    return {
        "requestedPath": str(supplied),
        "canonicalPath": str(canonical),
        "device": executable_status.st_dev,
        "inode": executable_status.st_ino,
        "sha256": file_sha256(canonical),
    }


def file_identity(path: Path) -> dict[str, Any]:
    """Canonical identity of an existing regular file (no symlink follow)."""
    try:
        status = path.lstat()
    except OSError as exc:
        raise TeamToolError(f"file unavailable: {exc}") from exc
    if not stat.S_ISREG(status.st_mode):
        raise TeamToolError(f"not a regular file: {path}")
    return {
        "path": str(path),
        "device": status.st_dev,
        "inode": status.st_ino,
        "size": status.st_size,
        "mode": stat.S_IMODE(status.st_mode),
        "links": status.st_nlink,
        "flags": getattr(status, "st_flags", 0),
        "sha256": file_sha256(path),
    }


def read_xattrs(path: Path) -> dict[bytes, bytes]:
    """Read xattrs without following symlinks; fail closed on ACL xattrs."""
    listxattr = getattr(os, "listxattr", None)
    getxattr = getattr(os, "getxattr", None)
    if listxattr is None or getxattr is None:
        return {}
    try:
        names = listxattr(path, follow_symlinks=False)
    except OSError:
        return {}
    values: dict[bytes, bytes] = {}
    for name in names:
        if name in ACL_XATTR_NAMES:
            raise TeamToolError(
                f"{path} carries an ACL xattr ({name!r}); replace requires explicit authorization"
            )
        values[name] = getxattr(path, name, follow_symlinks=False)
    return values


def write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        offset += os.write(fd, data[offset:])


def _fsync_directory(path: Path) -> None:
    try:
        dir_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def atomic_replace_file(path: Path, content: bytes) -> dict[str, Any]:
    """Replace one regular file atomically, preserving mode and xattrs.

    Fails closed on: symlink/special file, hard links, file flags, ACL
    xattrs, or concurrent change of the target before the rename.
    """
    parent = path.parent
    expected_parent_real = _assert_real_parent(parent)
    baseline = file_identity(path)
    if baseline["links"] != 1:
        raise TeamToolError(f"{path} is hard-linked and cannot be replaced safely")
    if baseline["flags"] != 0:
        raise TeamToolError(f"{path} has file flags and cannot be replaced safely")
    xattrs = read_xattrs(path)

    temp_name = f".{path.name}.adopt-team.{os.getpid()}.{secrets.token_hex(8)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(parent / temp_name, flags, 0o600)
    try:
        try:
            write_all(fd, content)
            os.fchmod(fd, baseline["mode"])
            fsetxattr = getattr(os, "fsetxattr", None)
            if fsetxattr is not None:
                for name, value in xattrs.items():
                    fsetxattr(fd, name, value)
            os.fsync(fd)
        finally:
            os.close(fd)

        current = file_identity(path)
        if current["sha256"] != baseline["sha256"] or current["inode"] != baseline["inode"]:
            raise TeamToolError(f"{path} changed before replacement")
        _assert_real_parent(parent)
        os.replace(parent / temp_name, path)
    except BaseException:
        try:
            os.unlink(parent / temp_name)
        except FileNotFoundError:
            pass
        raise

    try:
        _assert_contained(path, expected_parent_real)
        _assert_real_parent(parent)
    except TeamToolError:
        raise
    _fsync_directory(parent)
    written = file_identity(path)
    if written["sha256"] != bytes_sha256(content):
        raise TeamToolError(f"{path} changed during atomic replacement")
    return written


def _assert_real_parent(parent: Path) -> str:
    """Require the parent to be a real (non-symlink) directory; return its realpath."""
    if parent.is_symlink() or not parent.is_dir():
        raise TeamToolError(f"parent is not a real directory: {parent}")
    return os.path.realpath(str(parent))


def _assert_contained(path: Path, expected_parent_real: str) -> None:
    """Fail closed if the file resolved outside the expected parent (TOCTOU)."""
    resolved = os.path.realpath(str(path))
    expected = os.path.join(expected_parent_real, path.name)
    if resolved != expected:
        raise TeamToolError(
            f"{path} resolved to {resolved}; expected containment under {expected_parent_real}"
        )


def write_new_file(path: Path, content: bytes, mode: int) -> dict[str, Any]:
    """Create a new regular file atomically; fail closed if it appeared first.

    The parent directory is verified real before and after the rename, and
    the written file must resolve inside it — a parent swapped for a symlink
    mid-write is detected and the stray file removed.
    """
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    expected_parent_real = _assert_real_parent(parent)
    temp_name = f".{path.name}.adopt-team.{os.getpid()}.{secrets.token_hex(8)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(parent / temp_name, flags, 0o600)
    try:
        try:
            write_all(fd, content)
            os.fchmod(fd, mode)
            os.fsync(fd)
        finally:
            os.close(fd)
        if path.exists() or path.is_symlink():
            raise TeamToolError(f"{path} appeared before commit")
        _assert_real_parent(parent)
        os.replace(parent / temp_name, path)
    except BaseException:
        try:
            os.unlink(parent / temp_name)
        except FileNotFoundError:
            pass
        raise
    try:
        _assert_contained(path, expected_parent_real)
        _assert_real_parent(parent)
    except TeamToolError:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        raise
    _fsync_directory(parent)
    return file_identity(path)


def write_backup(source: Path, backup_dir: Path, tag: str) -> dict[str, Any]:
    """Byte-copy one file into the backup directory; never overwrites.

    Content-addressed names: an existing backup with the same digest is
    treated as already backed up; a colliding name with different bytes is
    an error.
    """
    identity = file_identity(source)
    backup_dir.mkdir(parents=True, exist_ok=True)
    if not backup_dir.is_dir() or backup_dir.is_symlink():
        raise TeamToolError(f"backup directory is not a real directory: {backup_dir}")
    name = f"{source.name}.{tag}.{identity['sha256'][:8]}.bak"
    target = backup_dir / name
    if target.exists():
        existing_sha = file_sha256(target)
        if existing_sha == identity["sha256"]:
            return {
                "source": str(source),
                "sourceSha256": identity["sha256"],
                "backupPath": str(target),
                "backupSha256": existing_sha,
                "preExisting": True,
            }
        raise TeamToolError(f"backup name collision with different content: {target}")
    content = source.read_bytes()
    written = write_new_file(target, content, identity["mode"])
    return {
        "source": str(source),
        "sourceSha256": identity["sha256"],
        "backupPath": str(target),
        "backupSha256": written["sha256"],
        "preExisting": False,
    }


def replace_pointer_block(existing: bytes, path_label: str) -> tuple[bytes, bool]:
    """Normalize a file to the canonical managed pointer layout.

    Returns `(canonical_bytes, changed)`. The canonical layout matches what
    the initializer accepts: the file is exactly `POINTER_BLOCK`, or it ends
    with `b"\n\n" + POINTER_BLOCK`. Surrounding content is preserved except
    for the separator immediately before the block, which is normalized to
    exactly two newlines. A missing marker pair, multiple blocks, or content
    after the block is a conflict, not a silent skip.
    """
    begin_idx = existing.find(POINTER_BEGIN)
    end_idx = existing.find(POINTER_END)
    if begin_idx == -1 or end_idx == -1:
        raise TeamToolError(f"{path_label}: managed pointer markers missing")
    if end_idx < begin_idx:
        raise TeamToolError(f"{path_label}: managed pointer markers out of order")
    if existing.count(POINTER_BEGIN) != 1 or existing.count(POINTER_END) != 1:
        raise TeamToolError(f"{path_label}: multiple managed pointer blocks present")
    suffix = existing[end_idx + len(POINTER_END) :]
    if suffix.strip(b"\r\n") != b"":
        raise TeamToolError(f"{path_label}: content after the managed pointer block")
    prefix = existing[:begin_idx]
    if prefix.strip(b"\r\n") == b"":
        canonical = POINTER_BLOCK
    else:
        canonical = prefix.rstrip(b"\r\n") + b"\n\n" + POINTER_BLOCK
    return canonical, canonical != existing


def section_headers(data: bytes) -> list[str]:
    return [line for line in data.decode("utf-8", "replace").splitlines() if line.startswith("## ")]


def line_diff_summary(old: bytes, new: bytes, old_label: str, new_label: str) -> dict[str, Any]:
    import difflib

    old_lines = old.decode("utf-8", "replace").splitlines()
    new_lines = new.decode("utf-8", "replace").splitlines()
    differ = difflib.unified_diff(
        old_lines, new_lines, fromfile=old_label, tofile=new_label, lineterm="", n=0
    )
    added = 0
    removed = 0
    hunks = 0
    for line in differ:
        if line.startswith("@@ "):
            hunks += 1
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    old_sections = section_headers(old)
    new_sections = section_headers(new)
    return {
        "linesRemoved": removed,
        "linesAdded": added,
        "hunks": hunks,
        "unchangedLines": len(old_lines) - removed,
        "sectionsRemoved": [s for s in old_sections if s not in new_sections],
        "sectionsAdded": [s for s in new_sections if s not in old_sections],
    }


# ---------------------------------------------------------------------------
# safe-git no-exec inspection boundary
#
# Mirrors the canonical initializer boundary: one recorded absolute Git
# executable, argument arrays (never a shell), inherited GIT_* keys removed,
# optional locks / lazy fetch / replace objects / fsmonitor / hooks / external
# diff disabled, and command-bearing config inspected through NUL-delimited
# records before any working-tree or index scan.
# ---------------------------------------------------------------------------

GIT_COMMAND_BEARING_CONFIG_RE = re.compile(
    rb"^(core\.fsmonitor|core\.hooksPath|diff\.external|"
    rb"diff\..*\.(command|textconv|trustExitCode)|"
    rb"filter\..*\.(clean|smudge|process|required))$"
)

SAFE_GIT_BASE_FLAGS = (
    "--no-pager",
    "--no-optional-locks",
    "--no-lazy-fetch",
    "--no-replace-objects",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "diff.external=",
    "-c",
    "diff.trustExitCode=false",
)


def stripped_env() -> dict[str, str]:
    """Environment with all inherited GIT_* and ORCA_* keys removed."""
    env = {
        "HOME": os.environ.get("HOME", ""),
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    }
    for key, value in os.environ.items():
        if key.startswith("GIT_") or key.startswith("ORCA_"):
            continue
        if key in ("HOME", "PATH", "LC_ALL", "TMPDIR"):
            continue
        env[key] = value
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_PAGER"] = "/bin/cat"
    return env


def run_process(argv: list[str], timeout: int = 60) -> tuple[int, bytes, bytes]:
    proc = subprocess.run(argv, capture_output=True, timeout=timeout, env=stripped_env())
    return proc.returncode, proc.stdout, proc.stderr


class SafeGit:
    """One repository-bound Git boundary: config inspection plus guarded runs."""

    def __init__(self, git_cli: str, repo: Path) -> None:
        self.git = executable_identity(git_cli, "git")
        self.repo = Path(repo)
        self._config_snapshot: dict[str, Any] | None = None

    def inspect_config(self) -> dict[str, Any]:
        """Inspect command-bearing config read-only; fail closed on executors.

        The `-z` output is a flat NUL-delimited stream of three-part records:
        `<scope>\0<origin>\0<key>\n<value>`. Values are redacted from reports;
        classification decisions use them internally.
        """
        argv = [
            self.git["canonicalPath"],
            "-C",
            str(self.repo),
            "config",
            "-z",
            "--show-origin",
            "--show-scope",
            "--get-regexp",
            rb"^(core\.fsmonitor|core\.hooksPath|diff\.external|diff\..*\.(command|textconv|trustExitCode)|filter\..*\.(clean|smudge|process|required))$".decode("ascii"),
        ]
        code, stdout, stderr = run_process(argv)
        if code != 0:
            if code == 1 and stdout == b"":
                records: list[dict[str, Any]] = []
            else:
                raise TeamToolError(
                    f"git_inspection_failed: config probe exited {code}: "
                    f"{stderr.decode('utf-8', 'replace').strip()}"
                )
        else:
            parts = stdout.split(b"\0")
            records = []
            for index in range(0, len(parts) - 1, 3):
                scope = parts[index].decode("utf-8", "replace")
                origin = parts[index + 1].decode("utf-8", "replace")
                key_value = parts[index + 2].split(b"\n", 1)
                key = key_value[0].decode("utf-8", "replace")
                value = key_value[1].decode("utf-8", "replace") if len(key_value) > 1 else ""
                records.append(
                    {
                        "key": key,
                        "value": value,
                        "scope": scope,
                        "origin": origin,
                    }
                )
        read_side_effects: list[str] = []
        checkout_side_effects: list[str] = []
        for record in records:
            key = record["key"]
            value = record["value"]
            if key == "core.fsmonitor" and value not in ("", "false"):
                read_side_effects.append(key)
            elif key == "diff.external" and value:
                read_side_effects.append(key)
            elif re.fullmatch(r"diff\..*\.(command|textconv)", key) and value:
                read_side_effects.append(key)
            elif re.fullmatch(r"filter\..*\.(clean|process)", key) and value:
                read_side_effects.append(key)
            elif re.fullmatch(r"filter\..*\.smudge", key) and value:
                checkout_side_effects.append(key)
            elif re.fullmatch(r"filter\..*\.required", key) and value == "true":
                read_side_effects.append(key)
        snapshot: dict[str, Any] = {
            "records": [
                {**record, "valueRedacted": "<redacted>", "value": None} for record in records
            ],
            "readSideEffects": sorted(set(read_side_effects)),
            "checkoutSideEffects": sorted(set(checkout_side_effects)),
            "configDigest": bytes_sha256(stdout),
            "executable": self.git,
        }
        self._config_snapshot = snapshot
        return snapshot

    def require_clean_read(self) -> None:
        snapshot = self.inspect_config()
        if snapshot["readSideEffects"]:
            raise TeamToolError(
                "git_read_side_effect_authorization_required: "
                + ", ".join(snapshot["readSideEffects"])
            )

    def require_clean_checkout(self) -> None:
        self.require_clean_read()
        snapshot = self._config_snapshot
        if snapshot is not None and snapshot["checkoutSideEffects"]:
            raise TeamToolError(
                "checkout_side_effect_authorization_required: "
                + ", ".join(snapshot["checkoutSideEffects"])
            )

    def check_config_snapshot(self) -> dict[str, Any]:
        """Re-inspect and compare against the bound snapshot; fail on drift."""
        if self._config_snapshot is None:
            raise TeamToolError("git_config_drift: no bound config snapshot")
        current = self.inspect_config()
        if current["configDigest"] != self._config_snapshot["configDigest"]:
            raise TeamToolError("git_config_drift: config changed since the bound snapshot")
        return current

    def run(self, *argv: str) -> tuple[int, bytes, bytes]:
        """Run one git command through the guarded boundary.

        `-C <repo>` is always prepended, so callers never depend on the
        process cwd. An explicit `-C <path>` in argv still overrides for
        per-worktree commands (last `-C` wins).
        """
        return run_process([self.git["canonicalPath"], *SAFE_GIT_BASE_FLAGS, "-C", str(self.repo), *argv])


def orca_run(orca_cli: str, *argv: str, timeout: int = 60) -> tuple[int, bytes, bytes]:
    """Run one Orca CLI command in the stripped environment."""
    identity = executable_identity(orca_cli, "orca")
    return run_process([identity["canonicalPath"], *argv], timeout=timeout)


def main() -> None:  # pragma: no cover - module has no CLI of its own
    print("team_common.py is a library; invoke a team command instead.", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover
    main()
