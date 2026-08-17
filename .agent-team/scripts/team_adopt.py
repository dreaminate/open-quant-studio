#!/usr/bin/env python3
"""Adopt the canonical Agent Team charter into one confirmed project.

Subcommands:

- `preview`: read-only. Shows the current vs canonical charter diff summary,
  the pointer diff, the migration-map coverage check, the proposed
  machine-readable meta, the exact write targets, and the backup plan.
  Emits a `confirmDigest` binding the preview payload; zero writes.
- `apply`: requires `--confirm-digest` from a preview the current user
  confirmed. Backs up every changed target, replaces the charter and pointer
  bytes atomically, writes `charter-meta.json`, and validates the result.
  Reports `rules_reload_required` — the adopting session must end and a new
  session must re-verify.
- `check`: read-only version check. Returns current vs expected contract
  version, charter digest, and a diff summary plus the next-step command.

Normative rules live in the charter itself; this helper implements only I/O.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

# The launcher invokes this helper with `python -I` (isolated mode), which does
# not add the script directory to sys.path. Insert it explicitly so the sibling
# module import works identically under -I and normal invocation.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import team_common as tc  # noqa: E402  # type: ignore[import-not-found]

V5_RULE_IDS = tuple(f"V5-R{i}" for i in range(1, 25))


def v5_rule_coverage(mapping_text: str) -> dict[str, Any]:
    """Mechanically verify the migration map covers every v5 rule exactly once."""
    rows = [
        line.split("|")[1].strip()
        for line in mapping_text.splitlines()
        if line.startswith("| V5-R") and "|" in line[4:]
    ]
    row_counts = {rule: rows.count(rule) for rule in set(rows)}
    missing = [rule for rule in V5_RULE_IDS if row_counts.get(rule, 0) == 0]
    duplicated = sorted(rule for rule, count in row_counts.items() if count > 1)
    unknown = sorted(set(rows) - set(V5_RULE_IDS))
    return {
        "expectedRules": len(V5_RULE_IDS),
        "coveredRules": len([r for r in V5_RULE_IDS if row_counts.get(r, 0) > 0]),
        "missingRules": missing,
        "duplicatedRules": duplicated,
        "unknownRuleIds": unknown,
        "complete": not missing and not duplicated and not unknown,
    }


def build_meta(
    charter_sha256: str,
    asset: dict[str, Any],
    migration_map: dict[str, Any],
    old_charter_sha256: str | None,
    backups: list[dict[str, Any]],
    adopted_at: str,
    adopted_by: str,
    min_launcher_contract_sha256: str,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "schemaVersion": 1,
        "contractVersion": tc.CONTRACT_VERSION,
        "charterPath": ".agent-team/TEAM.md",
        "charterSha256": charter_sha256,
        "assetSource": asset["path"],
        "assetSha256": asset["sha256"],
        "pointerSha256": tc.bytes_sha256(tc.POINTER_BLOCK),
        "pointerTargets": ["AGENTS.md", "CLAUDE.md"],
        "migrationMapPath": ".agent-team/migration-map.md",
        "migrationMapSha256": migration_map["sha256"],
        "minLauncherVersion": tc.MIN_LAUNCHER_VERSION,
        "minLauncherContractSha256": min_launcher_contract_sha256,
        "adoptedAt": adopted_at,
        "adoptedBy": adopted_by,
    }
    if old_charter_sha256 is not None:
        meta["adoptedFrom"] = {
            "oldCharterSha256": old_charter_sha256,
            "backup": [item["backupPath"] for item in backups],
        }
    return meta


def build_preview(
    project: Path, asset_path: Path, migration_map_path: Path, fresh_install: bool = False
) -> dict[str, Any]:
    project_identity = tc.directory_identity(project)
    asset_identity = tc.file_identity(asset_path)
    asset_bytes = asset_path.read_bytes()
    asset_sha = asset_identity["sha256"]

    charter_path = project / ".agent-team" / "TEAM.md"
    charter = None
    charter_current = None
    if charter_path.exists() and not charter_path.is_symlink():
        charter = tc.file_identity(charter_path)
        charter_current = charter["sha256"] == asset_sha
    elif charter_path.is_symlink():
        raise tc.TeamToolError(f"{charter_path} is a symlink and cannot be adopted safely")
    if charter is None and not fresh_install:
        raise tc.TeamToolError(
            "charter_missing_requires_fresh_install: no existing charter to adopt; pass "
            "--fresh-install to create the canonical charter and pointer files from scratch"
        )

    charter_old_bytes = charter_path.read_bytes() if charter is not None else b""
    charter_diff = (
        tc.line_diff_summary(charter_old_bytes, asset_bytes, "TEAM.md (installed)", "TEAM.md (canonical)")
        if charter is not None and not charter_current
        else None
    )

    pointer_targets = []
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = project / name
        entry: dict[str, Any] = {"name": name, "path": str(path)}
        if not path.exists():
            if fresh_install:
                entry["status"] = "create_pointer"
                entry["willChange"] = True
                entry["reason"] = "pointer file missing; fresh install creates it with the canonical pointer"
                entry["plannedSha256"] = tc.bytes_sha256(tc.POINTER_BLOCK)
            else:
                entry["status"] = "missing"
                entry["willChange"] = False
                entry["reason"] = "pointer file missing; adopt does not create instruction files"
        elif path.is_symlink():
            entry["status"] = "symlink"
            entry["willChange"] = False
            entry["reason"] = "symlink pointer preserved; verify the regular target carries the canonical pointer"
        else:
            existing = path.read_bytes()
            entry["currentSha256"] = tc.bytes_sha256(existing)
            try:
                replaced, changed = tc.replace_pointer_block(existing, name)
            except tc.TeamToolError as exc:
                entry["status"] = "conflict"
                entry["willChange"] = False
                entry["reason"] = str(exc)
            else:
                entry["matchesCanonical"] = not changed
                entry["status"] = "unchanged" if not changed else "update_pointer"
                entry["willChange"] = changed
                entry["preservesSurroundingContent"] = True
                if changed:
                    entry["plannedSha256"] = tc.bytes_sha256(replaced)
        pointer_targets.append(entry)

    migration_map_path = migration_map_path if migration_map_path.is_absolute() else project / migration_map_path
    mapping_text = migration_map_path.read_text(encoding="utf-8") if migration_map_path.exists() else ""
    migration_map = {
        "path": str(migration_map_path),
        "sha256": tc.bytes_sha256(migration_map_path.read_bytes()) if migration_map_path.exists() else None,
        "coverage": v5_rule_coverage(mapping_text) if mapping_text else None,
    }

    backups_dir = project / ".agent-team" / "backups"
    backup_plan = []
    if charter is not None and not charter_current:
        backup_plan.append(
            {"name": "TEAM.md", "path": str(charter_path), "sha256": charter["sha256"]}
        )
    for entry in pointer_targets:
        if entry.get("willChange") and entry.get("status") != "create_pointer":
            backup_plan.append(
                {
                    "name": entry["name"],
                    "path": entry["path"],
                    "sha256": entry["currentSha256"],
                }
            )

    if charter is None:
        preview_code = "preview_fresh_install"
    elif not charter_current or backup_plan:
        preview_code = "preview_ready"
    else:
        preview_code = "preview_no_changes"
    preview: dict[str, Any] = {
        "ok": True,
        "code": preview_code,
        "project": project_identity,
        "charter": {
            "installed": charter is not None,
            "installedSha256": charter["sha256"] if charter else None,
            "installedLines": charter_old_bytes.decode("utf-8", "replace").count("\n") if charter else None,
            "canonicalSha256": asset_sha,
            "canonicalLines": asset_bytes.decode("utf-8", "replace").count("\n"),
            "current": charter_current,
            "diffSummary": charter_diff,
        },
        "asset": asset_identity,
        "pointerTargets": pointer_targets,
        "migrationMap": migration_map,
        "proposedMeta": {
            "contractVersion": tc.CONTRACT_VERSION,
            "charterSha256": asset_sha,
            "minLauncherVersion": tc.MIN_LAUNCHER_VERSION,
            "minLauncherContractSha256": tc.launcher_contract_sha256(),
        },
        "backupPlan": {
            "backupDir": str(backups_dir),
            "files": backup_plan,
            "required": bool(backup_plan),
        },
        "writeTargets": [
            str(project / ".agent-team" / "TEAM.md"),
            str(project / "AGENTS.md"),
            str(project / "CLAUDE.md"),
            str(project / ".agent-team" / "charter-meta.json"),
        ],
        "nextStep": "review this preview, confirm adoption, then run: adopt-team-charter apply --confirm-digest <confirmDigest>",
    }
    confirm_payload = {key: value for key, value in preview.items() if key != "confirmDigest"}
    preview["confirmDigest"] = tc.bytes_sha256(
        json.dumps(confirm_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    return preview


def apply_adoption(
    project: Path,
    asset_path: Path,
    migration_map_path: Path,
    confirm_digest: str,
    meta_path: Path,
    fresh_install: bool = False,
) -> dict[str, Any]:
    preview = build_preview(project, asset_path, migration_map_path, fresh_install)
    if preview["confirmDigest"] != confirm_digest:
        return {
            "ok": False,
            "code": "confirm_digest_mismatch",
            "message": "The preview changed since it was confirmed. Re-run preview and obtain a fresh user confirmation.",
            "expectedConfirmDigest": confirm_digest,
            "observedConfirmDigest": preview["confirmDigest"],
            "changesApplied": False,
        }

    asset_bytes = asset_path.read_bytes()
    backups: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    backups_dir = project / ".agent-team" / "backups"

    charter_path = project / ".agent-team" / "TEAM.md"
    if not preview["charter"]["installed"]:
        if not fresh_install:
            return {
                "ok": False,
                "code": "charter_missing_apply_conflict",
                "message": (
                    "No existing charter to adopt. Creating a charter from scratch is a project-local "
                    "decision outside adopt-team-charter; install the canonical asset through "
                    "init-project-agent-team for a fresh project instead."
                ),
                "changesApplied": False,
            }
        agent_team_dir = project / ".agent-team"
        agent_team_dir.mkdir(parents=True, exist_ok=True)
        if agent_team_dir.is_symlink() or not agent_team_dir.is_dir():
            return {
                "ok": False,
                "code": "postcondition_failed",
                "message": ".agent-team is not a real directory",
                "changesApplied": False,
            }
        tc.write_new_file(charter_path, asset_bytes, 0o644)
        changes.append({"path": str(charter_path), "kind": "charter_created"})
    elif preview["charter"]["installed"] and not preview["charter"]["current"]:
        backups.append(tc.write_backup(charter_path, backups_dir, "v5"))
        tc.atomic_replace_file(charter_path, asset_bytes)
        changes.append({"path": str(charter_path), "kind": "charter_replaced"})

    for entry in preview["pointerTargets"]:
        if not entry.get("willChange"):
            continue
        path = project / entry["name"]
        if entry.get("status") == "create_pointer":
            tc.write_new_file(path, tc.POINTER_BLOCK, 0o644)
            changes.append({"path": str(path), "kind": "pointer_created"})
        else:
            backups.append(tc.write_backup(path, backups_dir, "pointer"))
            existing = path.read_bytes()
            replaced, _ = tc.replace_pointer_block(existing, entry["name"])
            tc.atomic_replace_file(path, replaced)
            changes.append({"path": str(path), "kind": "pointer_updated"})

    if not changes and meta_path.exists():
        # Idempotent re-apply: nothing to change; verify the existing meta agrees.
        try:
            parsed_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "ok": False,
                "code": "postcondition_failed",
                "message": f"charter-meta.json unreadable while no adoption change was required: {exc}",
                "changesApplied": False,
                "changes": [],
            }
        if parsed_meta.get("charterSha256") != tc.bytes_sha256(asset_bytes):
            return {
                "ok": False,
                "code": "postcondition_failed",
                "message": "charter-meta.json disagrees with the installed charter; re-run preview to plan a repair.",
                "changesApplied": False,
                "changes": [],
            }
        return {
            "ok": True,
            "code": "already_adopted",
            "changesApplied": False,
            "changes": [],
            "backups": [],
            "meta": parsed_meta,
            "rulesReloadRequired": False,
            "message": "Project charter and pointers already match the canonical asset.",
            "nextStep": "adopt-team-charter check",
        }

    old_charter_sha256 = preview["charter"]["installedSha256"]
    adopted_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    meta = build_meta(
        charter_sha256=tc.bytes_sha256(asset_bytes),
        asset=preview["asset"],
        migration_map=preview["migrationMap"],
        old_charter_sha256=old_charter_sha256 if changes else None,
        backups=backups,
        adopted_at=adopted_at,
        adopted_by="adopt-team-charter",
        min_launcher_contract_sha256=preview["proposedMeta"]["minLauncherContractSha256"],
    )
    meta_bytes = json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if meta_path.exists():
        tc.atomic_replace_file(meta_path, meta_bytes)
    else:
        tc.write_new_file(meta_path, meta_bytes, 0o644)
    changes.append({"path": str(meta_path), "kind": "meta_written"})

    # Postcondition validation: charter byte-identical, pointers canonical, meta consistent.
    installed = charter_path.read_bytes()
    if installed != asset_bytes:
        return {
            "ok": False,
            "code": "postcondition_failed",
            "message": "Installed charter is not byte-identical to the canonical asset after replacement.",
            "changesApplied": True,
            "changes": changes,
        }
    for entry in preview["pointerTargets"]:
        if entry["name"] in ("AGENTS.md", "CLAUDE.md"):
            path = project / entry["name"]
            if path.exists() and not path.is_symlink():
                try:
                    _, changed = tc.replace_pointer_block(path.read_bytes(), entry["name"])
                except tc.TeamToolError as exc:
                    return {
                        "ok": False,
                        "code": "postcondition_failed",
                        "message": f"{entry['name']} pointer not canonical after replacement: {exc}",
                        "changesApplied": True,
                        "changes": changes,
                    }
                if changed:
                    return {
                        "ok": False,
                        "code": "postcondition_failed",
                        "message": f"{entry['name']} pointer not canonical after replacement.",
                        "changesApplied": True,
                        "changes": changes,
                    }
    parsed_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if parsed_meta.get("charterSha256") != tc.bytes_sha256(asset_bytes):
        return {
            "ok": False,
            "code": "postcondition_failed",
            "message": "charter-meta.json digest does not match the installed charter.",
            "changesApplied": True,
            "changes": changes,
        }

    return {
        "ok": True,
        "code": "adopted" if changes else "already_adopted",
        "changesApplied": bool(changes),
        "changes": changes,
        "backups": backups,
        "meta": parsed_meta,
        "rulesReloadRequired": True if any(c["kind"] != "meta_written" for c in changes) else False,
        "message": (
            "Charter adopted. This session must end after reporting the receipt; "
            "a new session must reload the rules and run: adopt-team-charter check"
        ),
        "nextStep": "adopt-team-charter check",
    }


def check_current(project: Path, asset_path: Path, meta_path: Path) -> dict[str, Any]:
    charter_path = project / ".agent-team" / "TEAM.md"
    asset_bytes = asset_path.read_bytes()
    asset_sha = tc.bytes_sha256(asset_bytes)

    if not charter_path.exists() or charter_path.is_symlink():
        return {
            "ok": False,
            "code": "charter_missing",
            "message": "Project charter missing or a symlink. Run: adopt-team-charter preview",
            "expected": {"contractVersion": tc.CONTRACT_VERSION, "charterSha256": asset_sha},
            "current": None,
            "nextStep": "adopt-team-charter preview",
        }

    installed = charter_path.read_bytes()
    installed_sha = tc.bytes_sha256(installed)
    meta = None
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = None

    diff_summary = (
        None
        if installed_sha == asset_sha
        else tc.line_diff_summary(installed, asset_bytes, "TEAM.md (installed)", "TEAM.md (canonical)")
    )
    current = {
        "contractVersion": meta.get("contractVersion") if meta else None,
        "charterSha256": installed_sha,
        "metaPresent": meta is not None,
    }
    expected = {
        "contractVersion": tc.CONTRACT_VERSION,
        "charterSha256": asset_sha,
        "minLauncherVersion": tc.MIN_LAUNCHER_VERSION,
        "minLauncherContractSha256": tc.launcher_contract_sha256(),
    }
    charter_matches = installed_sha == asset_sha
    meta_matches = meta is not None and meta.get("charterSha256") == asset_sha
    if charter_matches and meta_matches:
        code = "charter_current"
    elif charter_matches:
        code = "charter_current_meta_missing"
    else:
        code = "charter_mismatch"
    next_step = {
        "charter_current": "team doctor --json",
        "charter_current_meta_missing": "adopt-team-charter preview",
        "charter_mismatch": "adopt-team-charter preview",
    }[code]
    return {
        "ok": charter_matches and meta_matches,
        "code": code,
        "current": current,
        "expected": expected,
        "diffSummary": diff_summary,
        "nextStep": next_step,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="absolute path of the project directory")
    parser.add_argument("--subcommand", required=True, choices=("preview", "apply", "check"))
    parser.add_argument("--asset", default=str(tc.ASSET_TEAM_PATH), help="canonical charter asset path")
    parser.add_argument("--confirm-digest", help="preview confirmDigest the user approved (apply only)")
    parser.add_argument("--migration-map", default=".agent-team/migration-map.md")
    parser.add_argument("--meta-path", default=".agent-team/charter-meta.json")
    parser.add_argument(
        "--fresh-install",
        action="store_true",
        help="project has no existing charter: create the canonical charter and pointer files",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = Path(args.project)
    asset_path = Path(args.asset)
    migration_map_path = Path(args.migration_map)
    meta_path = Path(args.meta_path)
    if not meta_path.is_absolute():
        meta_path = project / meta_path

    try:
        if args.subcommand == "preview":
            tc.emit(
                build_preview(project, asset_path, migration_map_path, args.fresh_install), 0
            )
        elif args.subcommand == "apply":
            if not args.confirm_digest:
                tc.emit(
                    {
                        "ok": False,
                        "code": "confirm_digest_required",
                        "message": "apply requires --confirm-digest from a user-approved preview",
                        "changesApplied": False,
                    },
                    2,
                )
            result = apply_adoption(
                project,
                asset_path,
                migration_map_path,
                args.confirm_digest,
                meta_path,
                fresh_install=args.fresh_install,
            )
            tc.emit(result, 0 if result["ok"] else 9)
        elif args.subcommand == "check":
            result = check_current(project, asset_path, meta_path)
            tc.emit(result, 0 if result["ok"] else 5)
    except tc.TeamToolError as exc:
        tc.emit(
            {
                "ok": False,
                "code": "invalid_project",
                "message": str(exc),
                "changesApplied": False,
            },
            9,
        )


if __name__ == "__main__":
    main()
