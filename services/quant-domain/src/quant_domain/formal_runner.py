from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

GATE_NAMES = ("contract", "strategy_import", "smoke_run")
STRATEGY_IMPORT_PROGRAM = r"""
import importlib.util
import ctypes
import errno
import json
import os
import pathlib
import platform
import resource
import sys

root = pathlib.Path(sys.argv[1]).resolve()
source = root / "strategy.py"
sys.dont_write_bytecode = True

def apply_linux_landlock():
    class RulesetAttr(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    write_access = sum(1 << bit for bit in range(1, 2))
    write_access |= sum(1 << bit for bit in range(4, 15))
    attributes = RulesetAttr(write_access)
    libc = ctypes.CDLL(None, use_errno=True)
    ruleset_fd = libc.syscall(444, ctypes.byref(attributes), ctypes.sizeof(attributes), 0)
    if ruleset_fd < 0:
        raise OSError(ctypes.get_errno(), "Landlock ruleset creation failed")
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "no_new_privs failed")
    if libc.syscall(446, ruleset_fd, 0) != 0:
        raise OSError(ctypes.get_errno(), "Landlock restriction failed")
    os.close(ruleset_fd)

if platform.system() == "Linux":
    apply_linux_landlock()
resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
del ctypes, errno, platform, resource

def audit(event, args):
    if event == "open" and len(args) > 1:
        mode = args[1]
        if isinstance(mode, str) and any(flag in mode for flag in ("w", "a", "x", "+")):
            raise RuntimeError("strategy host cannot mutate files")
        if isinstance(mode, int) and mode != 0:
            raise RuntimeError("strategy host cannot mutate files")
    if event in {
        "os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.link",
        "os.symlink", "os.truncate", "os.chmod", "os.chown", "os.utime",
        "os.system", "os.fork", "os.forkpty", "os.posix_spawn",
        "subprocess.Popen", "socket.connect", "ctypes.dlopen",
        "ctypes.dlsym", "ctypes.call_function",
    }:
        raise RuntimeError(f"strategy import cannot perform {event}")

sys.addaudithook(audit)

def blocked_process_control(*args):
    raise RuntimeError("strategy host cannot exit or write raw protocol bytes")

os._exit = blocked_process_control
os.write = blocked_process_control
sys.exit = blocked_process_control
posix = sys.modules.get("posix")
if posix is not None:
    posix._exit = blocked_process_control
    posix.write = blocked_process_control

try:
    spec = importlib.util.spec_from_file_location("oqs_candidate_strategy", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "on_bar", None)):
        raise RuntimeError("strategy.py must export callable on_bar")
    strategy_input = json.loads(sys.stdin.buffer.read())
    bars = strategy_input["bars"]
    on_start = getattr(module, "on_start", None)
    if on_start is not None and not callable(on_start):
        raise RuntimeError("on_start must be callable")
    start_batch = [] if on_start is None else on_start()
    bar_batches = [module.on_bar(dict(bar)) for bar in bars]
except BaseException as error:
    raise RuntimeError("candidate strategy execution failed") from error

sys.stdout.write(json.dumps(
    {
        "protocol_version": 1,
        "on_start": start_batch,
        "on_bars": bar_batches,
    },
    sort_keys=True,
    separators=(",", ":"),
))
"""


@dataclass(frozen=True)
class FormalExecution:
    engine_result: bytes | None
    gates: dict[str, str]
    error_code: str | None
    intent_tape: bytes | None = None


def execute_formal_run(
    *,
    strategy_source: bytes,
    engine_input: bytes,
    expected_engine_version: str,
    expected_output_schema_version: int,
) -> FormalExecution:
    failed_gates = {gate: "failed" for gate in GATE_NAMES}
    try:
        parsed_input = json.loads(engine_input)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return FormalExecution(None, failed_gates, "contract_gate_failed")
    if not isinstance(parsed_input, dict):
        return FormalExecution(None, failed_gates, "contract_gate_failed")

    gates = {"contract": "passed", "strategy_import": "failed", "smoke_run": "failed"}
    strategy_intents = run_strategy_host(strategy_source, engine_input)
    if strategy_intents is None or strategy_intents != parsed_input.get("intents"):
        return FormalExecution(None, gates, "strategy_import_failed")

    gates["strategy_import"] = "passed"
    from oqs_quant_engine import run_engine_v1

    try:
        engine_result = run_engine_v1(engine_input)
    except ValueError:
        return FormalExecution(None, gates, "smoke_run_failed")
    gates["smoke_run"] = "passed"

    try:
        parsed_result = json.loads(engine_result)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return FormalExecution(None, gates, "engine_result_contract_failed")
    if (
        not isinstance(parsed_result, dict)
        or parsed_result.get("schema_version") != expected_output_schema_version
        or parsed_result.get("engine_version") != expected_engine_version
    ):
        return FormalExecution(None, gates, "engine_result_contract_failed")
    intent_tape = json.dumps(
        strategy_intents, sort_keys=True, separators=(",", ":")
    ).encode()
    return FormalExecution(engine_result, gates, None, intent_tape)


def run_strategy_host(strategy_source: bytes, engine_input: bytes) -> list[object] | None:
    try:
        parsed_input = json.loads(engine_input)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed_input, dict):
        return None
    bars = parsed_input.get("bars")
    if (
        not isinstance(bars, list)
        or not bars
        or any(
            not isinstance(bar, dict)
            or not isinstance(bar.get("session_seq"), int)
            for bar in bars
        )
    ):
        return None
    strategy_input = json.dumps(
        {"bars": bars}, sort_keys=True, separators=(",", ":")
    ).encode()
    with tempfile.TemporaryDirectory(prefix="oqs-strategy-import-") as temporary:
        root = Path(temporary)
        (root / "strategy.py").write_bytes(strategy_source)
        try:
            command = [
                sys.executable,
                "-I",
                "-c",
                STRATEGY_IMPORT_PROGRAM,
                str(root),
            ]
            if sys.platform == "darwin":
                command = [
                    "/usr/bin/sandbox-exec",
                    "-p",
                    "(version 1) (allow default) (deny file-write*) (deny network*)",
                    *command,
                ]
            completed = subprocess.run(
                command,
                cwd=root,
                env={},
                input=strategy_input,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None
    if completed.returncode != 0:
        return None
    try:
        output = json.loads(completed.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(output, dict)
        or set(output) != {"protocol_version", "on_start", "on_bars"}
        or output["protocol_version"] != 1
        or not isinstance(output["on_bars"], list)
        or len(output["on_bars"]) != len(bars)
    ):
        return None

    emitted: list[object] = []

    def append_intents(
        intents: object,
        known_session_seq: int,
        effective_session_seq: int,
    ) -> bool:
        if not isinstance(intents, list) or any(
            not isinstance(intent, dict) or not isinstance(intent.get("intent_seq"), int)
            for intent in intents
        ):
            return False
        for intent in intents:
            stamped = dict(intent)
            stable_seq = stamped["intent_seq"]
            requested_effective_at = stamped.get("effective_at")
            if requested_effective_at is None:
                effective_at = {
                    "session_seq": effective_session_seq,
                    "phase": "open",
                    "stable_seq": stable_seq,
                }
            elif (
                not isinstance(requested_effective_at, dict)
                or set(requested_effective_at)
                != {"session_seq", "phase", "stable_seq"}
                or not isinstance(requested_effective_at.get("session_seq"), int)
                or requested_effective_at["session_seq"] < effective_session_seq
                or requested_effective_at.get("phase") != "open"
                or not isinstance(requested_effective_at.get("stable_seq"), int)
            ):
                return False
            else:
                effective_at = dict(requested_effective_at)
            stamped["known_at"] = {
                "session_seq": known_session_seq,
                "phase": "close",
                "stable_seq": stable_seq,
            }
            stamped["effective_at"] = effective_at
            emitted.append(stamped)
        return True

    if not append_intents(output["on_start"], 0, bars[0]["session_seq"]):
        return None
    for index, bar in enumerate(bars[:-1]):
        if not append_intents(
            output["on_bars"][index],
            bar["session_seq"],
            bars[index + 1]["session_seq"],
        ):
            return None
    if output["on_bars"][-1] != []:
        return None
    return emitted
