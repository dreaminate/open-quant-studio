#!/Users/wzy/miniforge3/bin/python3
"""Mock Orca CLI for the disposable-repository E2E suite.

Implements the *documented future CLI contract* the pipeline expects — NOT a
claim about the real Orca 1.4.180 CLI, whose gaps remain pending placeholders
and keep real runs failing closed. The mock is stateful (state file passed
via MOCK_ORCA_STATE) and performs real `git worktree add` for worktree
creation on exact branches, so the E2E pipeline verifies receipts against
real Git state.

Commands:
  status --json
  repo list --json
  worktree create --repo <id> --branch <branch> --path <path>
      [--parent <id>] [--display-name <name>] [--no-parent] --json
  worktree list --repo <id> --json
  terminal list [--worktree <selector>] --include-visual-layouts --json
  terminal close --terminal <handle> --tab --json
  terminal start --worktree <selector> --agent <agent> [--args <text>] --json
  message send --envelope <file> --json
  message receive [--seat <key>] --json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

STATE_ENV = "MOCK_ORCA_STATE"


def load_state() -> dict[str, Any]:
    path = Path(os.environ[STATE_ENV])
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "runtime": {"id": "mock-runtime", "ready": True},
        "repos": [],
        "worktrees": [],
        "terminals": [],
        "messages": [],
        "counter": 0,
    }


def save_state(state: dict[str, Any]) -> None:
    path = Path(os.environ[STATE_ENV])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


def emit(payload: dict[str, Any], code: int) -> None:
    print(json.dumps(payload, sort_keys=True))
    raise SystemExit(code)


def next_id(state: dict[str, Any], prefix: str) -> str:
    state["counter"] += 1
    return f"{prefix}-{state['counter']:04d}"


def git(*argv: str, cwd: Path) -> tuple[int, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    proc = subprocess.run(
        ["/usr/bin/git", "--no-pager", "--no-optional-locks", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout + proc.stderr


def cmd_status(state: dict[str, Any], _args: list[str]) -> None:
    emit(
        {
            "ok": True,
            "id": "local-status",
            "result": {
                "app": {"running": True, "pid": 4242},
                "runtime": {
                    "state": "ready",
                    "reachable": True,
                    "runtimeId": state["runtime"]["id"],
                },
            },
        },
        0,
    )


def cmd_repo_list(state: dict[str, Any], _args: list[str]) -> None:
    emit({"repos": state["repos"]}, 0)


def find_repo(state: dict[str, Any], repo_id: str) -> dict[str, Any]:
    for repo in state["repos"]:
        if repo["id"] == repo_id:
            return repo
    emit({"ok": False, "error": f"repo not found: {repo_id}"}, 1)
    raise SystemExit(1)  # unreachable; keeps the type checker honest


def worktree_selector_to_path(state: dict[str, Any], selector: str) -> str:
    # selector: id:<repoId>::<path>; canonicalize for symlink-safe comparison
    if not selector.startswith("id:") or "::" not in selector:
        emit({"ok": False, "error": f"unparseable worktree selector: {selector}"}, 1)
    _, rest = selector.split("::", 1)
    return os.path.realpath(rest)


def cmd_worktree_create(state: dict[str, Any], args: list[str]) -> None:
    repo_id = args[args.index("--repo") + 1]
    branch = args[args.index("--branch") + 1]
    path = args[args.index("--path") + 1]
    parent = None
    if "--parent" in args:
        parent = args[args.index("--parent") + 1]
    repo = find_repo(state, repo_id)
    repo_path = Path(repo["path"])
    target = Path(path)

    # Exact-branch contract: the branch must exist and the name must match
    # byte-for-byte; any prefix/suffix derivation is refused.
    code, out = git("show-ref", "--verify", "--quiet", f"refs/heads/{branch}", cwd=repo_path)
    if code != 0:
        emit({"ok": False, "error": f"branch {branch} does not exist exactly"}, 1)
    if target.exists():
        emit({"ok": False, "error": f"path already exists: {path}"}, 1)
    if parent is not None and not any(wt["id"] == parent for wt in state["worktrees"]):
        emit({"ok": False, "error": f"parent worktree not found: {parent}"}, 1)

    code, out = git("worktree", "add", str(target), branch, cwd=repo_path)
    if code != 0:
        emit({"ok": False, "error": f"git worktree add failed: {out}"}, 1)

    worktree_id = next_id(state, "wt")
    canonical_target = os.path.realpath(str(target))
    state["worktrees"].append(
        {
            "id": worktree_id,
            "repoId": repo_id,
            "path": canonical_target,
            "branch": branch,
            "parentId": parent,
            "displayName": None,
        }
    )
    # Worktree creation creates a first saved terminal (as the real Orca does).
    tab_id = next_id(state, "tab")
    handle = next_id(state, "term")
    state["terminals"].append(
        {"id": handle, "tabId": tab_id, "handle": handle, "worktreeId": worktree_id}
    )
    emit(
        {
            "ok": True,
            "worktree": {
                "id": worktree_id,
                "path": canonical_target,
                "branch": branch,
                "parentId": parent,
            },
            "firstTerminal": {"tabId": tab_id, "handle": handle},
        },
        0,
    )


def cmd_worktree_list(state: dict[str, Any], args: list[str]) -> None:
    repo_id = args[args.index("--repo") + 1]
    emit(
        {
            "worktrees": [
                wt for wt in state["worktrees"] if wt["repoId"] == repo_id
            ]
        },
        0,
    )


def cmd_terminal_list(state: dict[str, Any], args: list[str]) -> None:
    worktree_id = None
    if "--worktree" in args:
        path = worktree_selector_to_path(state, args[args.index("--worktree") + 1])
        worktree_id = next(
            (wt["id"] for wt in state["worktrees"] if wt["path"] == path), None
        )
    terminals = [
        term for term in state["terminals"]
        if worktree_id is None or term["worktreeId"] == worktree_id
    ]
    emit(
        {
            "ok": True,
            "totalCount": len(terminals),
            "terminals": terminals,
            "visualLayouts": [],
        },
        0,
    )


def cmd_terminal_close(state: dict[str, Any], args: list[str]) -> None:
    handle = args[args.index("--terminal") + 1]
    target = next((term for term in state["terminals"] if term["handle"] == handle), None)
    if target is None:
        emit({"ok": False, "error": f"terminal not found: {handle}"}, 1)
        raise SystemExit(1)  # unreachable
    state["terminals"] = [
        term for term in state["terminals"] if term["tabId"] != target["tabId"]
    ]
    emit({"ok": True, "closedTab": target["tabId"]}, 0)


def cmd_terminal_create(state: dict[str, Any], args: list[str]) -> None:
    # Mirrors the verified real CLI shape: orca terminal create --worktree
    # <selector> --command <text> --json -> result.terminal.{handle,tabId,
    # worktreeId}.
    path = worktree_selector_to_path(state, args[args.index("--worktree") + 1])
    command = args[args.index("--command") + 1] if "--command" in args else ""
    worktree = next((wt for wt in state["worktrees"] if wt["path"] == path), None)
    if worktree is None:
        emit({"ok": False, "error": f"worktree not managed: {path}"}, 1)
        raise SystemExit(1)  # unreachable
    tab_id = next_id(state, "tab")
    handle = next_id(state, "term")
    state["terminals"].append(
        {
            "id": handle,
            "tabId": tab_id,
            "handle": handle,
            "worktreeId": worktree["id"],
            "command": command,
        }
    )
    emit(
        {
            "ok": True,
            "result": {
                "terminal": {
                    "handle": handle,
                    "tabId": tab_id,
                    "worktreeId": worktree["id"],
                }
            },
        },
        0,
    )


def cmd_message_send(state: dict[str, Any], args: list[str]) -> None:
    envelope_file = Path(args[args.index("--envelope") + 1])
    envelope = json.loads(envelope_file.read_text(encoding="utf-8"))
    state["messages"].append(envelope)
    emit({"ok": True, "messageId": envelope.get("messageId")}, 0)


def cmd_message_receive(state: dict[str, Any], args: list[str]) -> None:
    seat = None
    if "--seat" in args:
        seat = args[args.index("--seat") + 1]
    drained = []
    remaining = []
    for message in state["messages"]:
        if seat is None or message.get("recipient", {}).get("seat") == seat:
            drained.append(message)
        else:
            remaining.append(message)
    state["messages"] = remaining
    emit({"ok": True, "messages": drained}, 0)


def main() -> None:
    if STATE_ENV not in os.environ:
        emit({"ok": False, "error": f"{STATE_ENV} not set"}, 2)
    state = load_state()
    args = sys.argv[1:]
    command = args[0] if args else ""
    try:
        if command == "status":
            cmd_status(state, args[1:])
        elif command == "repo" and args[1] == "list":
            cmd_repo_list(state, args[2:])
        elif command == "worktree" and args[1] == "create":
            cmd_worktree_create(state, args[2:])
        elif command == "worktree" and args[1] == "list":
            cmd_worktree_list(state, args[2:])
        elif command == "terminal" and args[1] == "list":
            cmd_terminal_list(state, args[2:])
        elif command == "terminal" and args[1] == "close":
            cmd_terminal_close(state, args[2:])
        elif command == "terminal" and args[1] == "create":
            cmd_terminal_create(state, args[2:])
        elif command == "message" and args[1] == "send":
            cmd_message_send(state, args[2:])
        elif command == "message" and args[1] == "receive":
            cmd_message_receive(state, args[2:])
        else:
            emit({"ok": False, "error": f"unknown command: {' '.join(args)}"}, 2)
    finally:
        save_state(state)


if __name__ == "__main__":
    main()
