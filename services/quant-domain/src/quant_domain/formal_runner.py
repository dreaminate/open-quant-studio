from __future__ import annotations

import json
import os
import secrets
import selectors
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

GATE_NAMES = ("contract", "strategy_import", "smoke_run")
STRATEGY_PROTOCOL_VERSION = 2
STRATEGY_RESPONSE_TIMEOUT_SECONDS = 5.0
STRATEGY_PROCESS_EXIT_TIMEOUT_SECONDS = 1.0
MAX_STRATEGY_FRAME_BYTES = 1_048_576

STRATEGY_CALLBACK_PROGRAM = r"""
import importlib.util
import json
import pathlib
import queue
import sys
import threading

sys.dont_write_bytecode = True

def load_candidate(root):
    source = root / "strategy.py"
    spec = importlib.util.spec_from_file_location("oqs_candidate_strategy", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "on_bar", None)):
        raise RuntimeError("strategy.py must export callable on_bar")
    on_start = getattr(module, "on_start", None)
    if on_start is not None and not callable(on_start):
        raise RuntimeError("on_start must be callable")
    return module, on_start

def run_candidate(root, requests, results):
    try:
        module, on_start = load_candidate(root)
    except BaseException:
        results.put({"kind": "ready", "ok": False})
        return
    results.put({"kind": "ready", "ok": True})
    while True:
        request = requests.get()
        if request is None:
            return
        try:
            if request["frame_type"] == "start":
                intents = [] if on_start is None else on_start()
            else:
                intents = module.on_bar(dict(request["bar"]))
        except BaseException:
            results.put(
                {"kind": "response", "request_id": request["request_id"], "ok": False}
            )
            return
        results.put(
            {
                "kind": "response",
                "request_id": request["request_id"],
                "ok": True,
                "intents": intents,
            }
        )

def read_frame():
    encoded = sys.stdin.buffer.readline()
    if not encoded:
        return None
    if not encoded.endswith(b"\n"):
        raise RuntimeError("strategy host received an incomplete frame")
    frame = json.loads(encoded)
    if not isinstance(frame, dict):
        raise RuntimeError("strategy host received a non-object frame")
    return frame

def exact_request(frame, expected_request_id):
    if (
        frame is None
        or type(frame.get("request_id")) is not int
        or frame["request_id"] != expected_request_id
        or type(frame.get("request_token")) is not str
        or len(frame["request_token"]) != 32
        or frame.get("protocol_version") != 2
    ):
        return None
    if frame.get("frame_type") == "start":
        if set(frame) != {"protocol_version", "frame_type", "request_id", "request_token"}:
            return None
        return frame
    if (
        set(frame)
        != {"protocol_version", "frame_type", "request_id", "request_token", "bar"}
        or frame.get("frame_type") != "bar"
        or not isinstance(frame.get("bar"), dict)
    ):
        return None
    return frame

def _serve():
    root = pathlib.Path(sys.argv[1]).resolve()
    protocol_stdout = sys.stdout
    sys.stdout = sys.stderr
    sys.__stdout__ = sys.stderr
    requests = queue.Queue(maxsize=1)
    results = queue.Queue(maxsize=1)
    candidate_thread = threading.Thread(
        target=run_candidate,
        args=(root, requests, results),
        daemon=True,
    )
    candidate_thread.start()
    try:
        ready = results.get(timeout=5.0)
        if ready != {"kind": "ready", "ok": True}:
            raise RuntimeError("strategy.py could not load")

        def exchange(request, response_type):
            candidate_request = {
                "request_id": request["request_id"],
                "frame_type": request["frame_type"],
            }
            if request["frame_type"] == "bar":
                candidate_request["bar"] = request["bar"]
            requests.put(candidate_request, timeout=5.0)
            response = results.get(timeout=5.0)
            if (
                not isinstance(response, dict)
                or set(response) not in (
                    {"kind", "request_id", "ok"},
                    {"kind", "request_id", "ok", "intents"},
                )
                or response.get("kind") != "response"
                or response.get("request_id") != request["request_id"]
                or response.get("ok") is not True
                or not isinstance(response.get("intents"), list)
            ):
                raise RuntimeError("strategy host received an invalid callback result")
            encoded = json.dumps(
                {
                    "protocol_version": 2,
                    "frame_type": response_type,
                    "request_id": request["request_id"],
                    "request_token": request["request_token"],
                    "intents": response["intents"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode() + b"\n"
            protocol_stdout.buffer.write(encoded)
            protocol_stdout.flush()

        expected_request_id = 1
        start = exact_request(read_frame(), expected_request_id)
        if start is None or start["frame_type"] != "start":
            raise RuntimeError("strategy host received an invalid start frame")
        exchange(start, "start_response")

        while True:
            expected_request_id += 1
            frame = read_frame()
            if frame is None:
                return
            request = exact_request(frame, expected_request_id)
            if request is None or request["frame_type"] != "bar":
                raise RuntimeError("strategy host received an invalid bar frame")
            exchange(request, "bar_response")
    finally:
        try:
            requests.put(None, timeout=1.0)
        except queue.Full:
            pass
        candidate_thread.join(timeout=1.0)

_serve()
"""

STRATEGY_BROKER_PROGRAM = (
    r"""
import json
import os
import pathlib
import selectors
import subprocess
import sys
import time

MAX_FRAME_BYTES = 1_048_576
FRAME_TIMEOUT_SECONDS = 5.0
PROCESS_EXIT_TIMEOUT_SECONDS = 1.0
CALLBACK_PROGRAM = __CALLBACK_PROGRAM__

def read_bounded_frame(fd, reader, timeout):
    deadline = time.monotonic() + timeout
    frame = bytearray()
    while len(frame) < MAX_FRAME_BYTES:
        remaining_time = deadline - time.monotonic()
        if remaining_time <= 0:
            return None
        if not reader.select(remaining_time):
            return None
        chunk = os.read(fd, min(4096, MAX_FRAME_BYTES - len(frame)))
        if not chunk:
            return None
        newline = chunk.find(b"\n")
        if newline >= 0:
            if newline != len(chunk) - 1:
                return None
            frame.extend(chunk)
            return bytes(frame)
        frame.extend(chunk)
    return None

def decode_frame(encoded):
    try:
        frame = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(frame, dict):
        return None
    return frame

def encode_frame(frame):
    encoded = json.dumps(frame, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if len(encoded) > MAX_FRAME_BYTES:
        return None
    return encoded

def exact_request(frame, frame_type, request_id):
    if (
        frame is None
        or type(frame.get("request_id")) is not int
        or frame.get("request_id") != request_id
        or type(frame.get("request_token")) is not str
        or len(frame.get("request_token")) != 32
        or frame.get("protocol_version") != 2
        or frame.get("frame_type") != frame_type
    ):
        return None
    if frame_type == "start":
        if set(frame) != {"protocol_version", "frame_type", "request_id", "request_token"}:
            return None
        return frame
    if set(frame) != {"protocol_version", "frame_type", "request_id", "request_token", "bar"}:
        return None
    if not isinstance(frame.get("bar"), dict):
        return None
    return frame

def exact_response(frame, frame_type, request_id, request_token):
    if (
        frame is None
        or set(frame)
        != {"protocol_version", "frame_type", "request_id", "request_token", "intents"}
        or frame.get("protocol_version") != 2
        or frame.get("frame_type") != frame_type
        or type(frame.get("request_id")) is not int
        or frame.get("request_id") != request_id
        or frame.get("request_token") != request_token
        or not isinstance(frame.get("intents"), list)
    ):
        return None
    return frame

def no_pending_bytes(fd, reader):
    if not reader.select(0):
        return True
    try:
        os.read(fd, 1)
    except OSError:
        pass
    return False

def send_frame(stream, frame):
    encoded = encode_frame(frame)
    if encoded is None:
        return False
    stream.write(encoded)
    stream.flush()
    return True

def stop_callback(callback):
    if callback.stdin is not None:
        callback.stdin.close()
    if callback.poll() is None:
        try:
            callback.wait(timeout=PROCESS_EXIT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            callback.terminate()
            try:
                callback.wait(timeout=PROCESS_EXIT_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                callback.kill()
                callback.wait()
    if callback.stdout is not None:
        callback.stdout.close()

def run():
    root = pathlib.Path(sys.argv[1]).resolve()
    callback = subprocess.Popen(
        [sys.executable, "-I", "-c", CALLBACK_PROGRAM, str(root)],
        cwd=root,
        env={},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=2,
        close_fds=True,
        bufsize=0,
    )
    if callback.stdin is None or callback.stdout is None:
        return 1
    callback_reader = selectors.DefaultSelector()
    callback_reader.register(callback.stdout, selectors.EVENT_READ)
    parent_reader = selectors.DefaultSelector()
    parent_reader.register(sys.stdin, selectors.EVENT_READ)
    callback_fd = callback.stdout.fileno()
    parent_fd = sys.stdin.fileno()

    def callback_exchange(request, response_type):
        if not send_frame(callback.stdin, request):
            return None
        encoded = read_bounded_frame(callback_fd, callback_reader, FRAME_TIMEOUT_SECONDS)
        response = exact_response(
            decode_frame(encoded),
            response_type,
            request["request_id"],
            request["request_token"],
        )
        if response is None or not no_pending_bytes(callback_fd, callback_reader):
            return None
        return response

    try:
        encoded = read_bounded_frame(parent_fd, parent_reader, FRAME_TIMEOUT_SECONDS)
        expected_request_id = 1
        start = exact_request(decode_frame(encoded), "start", expected_request_id)
        if start is None:
            return 1
        response = callback_exchange(start, "start_response")
        if response is None or not send_frame(sys.stdout.buffer, response):
            return 1
        if not no_pending_bytes(parent_fd, parent_reader):
            return 1

        while True:
            encoded = read_bounded_frame(parent_fd, parent_reader, FRAME_TIMEOUT_SECONDS)
            if encoded is None:
                if not parent_reader.select(0):
                    return 1
                return 0 if not os.read(parent_fd, 1) else 1
            expected_request_id += 1
            request = exact_request(
                decode_frame(encoded), "bar", expected_request_id
            )
            if request is None:
                return 1
            response = callback_exchange(request, "bar_response")
            if response is None or not send_frame(sys.stdout.buffer, response):
                return 1
            if not no_pending_bytes(parent_fd, parent_reader):
                return 1
    finally:
        callback_reader.close()
        parent_reader.close()
        stop_callback(callback)

raise SystemExit(run())
""".replace("__CALLBACK_PROGRAM__", repr(STRATEGY_CALLBACK_PROGRAM))
)

# Kept as a compatibility alias for local callers that imported the old name.
STRATEGY_IMPORT_PROGRAM = STRATEGY_BROKER_PROGRAM


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


def _read_bounded_frame(
    stream: object, reader: selectors.BaseSelector, timeout: float
) -> bytes | None:
    file_descriptor = stream.fileno()
    deadline = time.monotonic() + timeout
    frame = bytearray()
    while len(frame) < MAX_STRATEGY_FRAME_BYTES:
        remaining_time = deadline - time.monotonic()
        if remaining_time <= 0:
            return None
        if not reader.select(remaining_time):
            return None
        chunk = os.read(
            file_descriptor,
            min(4096, MAX_STRATEGY_FRAME_BYTES - len(frame)),
        )
        if not chunk:
            return None
        newline = chunk.find(b"\n")
        if newline >= 0:
            if newline != len(chunk) - 1:
                return None
            frame.extend(chunk)
            return bytes(frame)
        frame.extend(chunk)
    return None


def _no_pending_bytes(stream: object, reader: selectors.BaseSelector) -> bool:
    if not reader.select(0):
        return True
    try:
        os.read(stream.fileno(), 1)
    except OSError:
        pass
    return False


def _encode_frame(frame: dict[str, object]) -> bytes | None:
    encoded = json.dumps(frame, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if len(encoded) > MAX_STRATEGY_FRAME_BYTES:
        return None
    return encoded


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
            or type(bar.get("session_seq")) is not int
            for bar in bars
        )
    ):
        return None
    with tempfile.TemporaryDirectory(prefix="oqs-strategy-import-") as temporary:
        root = Path(temporary)
        (root / "strategy.py").write_bytes(strategy_source)
        process: subprocess.Popen[bytes] | None = None
        response_reader: selectors.BaseSelector | None = None
        try:
            command = [
                sys.executable,
                "-I",
                "-c",
                STRATEGY_BROKER_PROGRAM,
                str(root),
            ]
            process = subprocess.Popen(
                command,
                cwd=root,
                env={},
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                bufsize=0,
            )
            if process.stdin is None or process.stdout is None:
                return None

            response_reader = selectors.DefaultSelector()
            response_reader.register(process.stdout, selectors.EVENT_READ)

            def read_response(
                frame_type: str, request_id: int, request_token: str
            ) -> object | None:
                encoded = _read_bounded_frame(
                    process.stdout, response_reader, STRATEGY_RESPONSE_TIMEOUT_SECONDS
                )
                if encoded is None:
                    return None
                try:
                    response = json.loads(encoded)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return None
                if (
                    not isinstance(response, dict)
                    or set(response)
                    != {
                        "protocol_version",
                        "frame_type",
                        "request_id",
                        "request_token",
                        "intents",
                    }
                    or response.get("protocol_version") != STRATEGY_PROTOCOL_VERSION
                    or response.get("frame_type") != frame_type
                    or type(response.get("request_id")) is not int
                    or response.get("request_id") != request_id
                    or response.get("request_token") != request_token
                    or not isinstance(response.get("intents"), list)
                ):
                    return None
                if not _no_pending_bytes(process.stdout, response_reader):
                    return None
                return response["intents"]

            def send_frame(frame: dict[str, object]) -> bool:
                encoded = _encode_frame(frame)
                if encoded is None:
                    return False
                process.stdin.write(encoded)
                process.stdin.flush()
                return True

            request_id = 1
            request_token = secrets.token_hex(16)
            if not send_frame(
                {
                    "protocol_version": STRATEGY_PROTOCOL_VERSION,
                    "frame_type": "start",
                    "request_id": request_id,
                    "request_token": request_token,
                }
            ):
                return None
            start_intents = read_response(
                "start_response", request_id, request_token
            )
            if start_intents is None:
                return None

            emitted: list[object] = []
            last_intent_seq: int | None = None

            def append_intents(
                intents: object,
                known_session_seq: int,
                effective_session_seq: int,
            ) -> bool:
                nonlocal last_intent_seq
                if not isinstance(intents, list):
                    return False
                for intent in intents:
                    if not isinstance(intent, dict) or type(intent.get("intent_seq")) is not int:
                        return False
                    stable_seq = intent["intent_seq"]
                    if last_intent_seq is not None and stable_seq <= last_intent_seq:
                        return False
                    requested_effective_at = intent.get("effective_at")
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
                        or type(requested_effective_at.get("session_seq")) is not int
                        or requested_effective_at["session_seq"] < effective_session_seq
                        or requested_effective_at.get("phase") != "open"
                        or type(requested_effective_at.get("stable_seq")) is not int
                    ):
                        return False
                    else:
                        effective_at = dict(requested_effective_at)
                    stamped = dict(intent)
                    stamped["known_at"] = {
                        "session_seq": known_session_seq,
                        "phase": "close",
                        "stable_seq": stable_seq,
                    }
                    stamped["effective_at"] = effective_at
                    emitted.append(stamped)
                    last_intent_seq = stable_seq
                return True

            if not append_intents(start_intents, 0, bars[0]["session_seq"]):
                return None
            for index, bar in enumerate(bars):
                request_id += 1
                request_token = secrets.token_hex(16)
                if not send_frame(
                    {
                        "protocol_version": STRATEGY_PROTOCOL_VERSION,
                        "frame_type": "bar",
                        "request_id": request_id,
                        "request_token": request_token,
                        "bar": bar,
                    }
                ):
                    return None
                intents = read_response("bar_response", request_id, request_token)
                if intents is None:
                    return None
                if index == len(bars) - 1:
                    continue
                if not append_intents(
                    intents,
                    bar["session_seq"],
                    bars[index + 1]["session_seq"],
                ):
                    return None

            process.stdin.close()
            if process.wait(
                timeout=STRATEGY_PROCESS_EXIT_TIMEOUT_SECONDS + 2
            ) != 0:
                return None
            if response_reader.select(0) and os.read(process.stdout.fileno(), 1):
                return None
            return emitted
        except (BrokenPipeError, OSError, selectors.error, subprocess.TimeoutExpired):
            return None
        finally:
            if response_reader is not None:
                response_reader.close()
            if process is not None and process.stdin is not None:
                try:
                    process.stdin.close()
                except OSError:
                    pass
            if process is not None and process.stdout is not None:
                try:
                    process.stdout.close()
                except OSError:
                    pass
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=STRATEGY_PROCESS_EXIT_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
