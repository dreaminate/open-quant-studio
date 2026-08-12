"""Deterministic local historical Forward Test replay for M5."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, cast

from .formal_runner import run_strategy_host


FORWARD_REPLAY_PROTOCOL = "oqs-forward-replay/m5-v1"


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class ForwardReplayResult:
    forward_test_id: str
    source_run_id: str
    source_revision_id: str
    data_snapshot_id: str
    protocol_version: str
    released_bar_count: int
    status: str
    error_code: str | None
    intent_tape: bytes
    intent_tape_sha256: str
    transcript: bytes
    transcript_sha256: str


def replay_forward_test(
    *,
    forward_test_id: str,
    source_run: Mapping[str, object],
    source_manifest: Mapping[str, object],
    strategy_source: bytes,
    market_input: bytes,
    source_intent_tape: bytes,
) -> ForwardReplayResult:
    """Replay a succeeded M5 Run over its historical bars through the normal host.

    ``run_strategy_host`` owns the sequential bar release and timing stamps.  This
    function records that same deterministic output as a local Forward Test
    transcript; it neither consumes live market data nor submits paper orders.
    """

    manifest = cast(dict[str, Any], source_manifest)
    run_spec = cast(dict[str, Any], manifest["run_spec"])
    revision = cast(dict[str, Any], manifest["revision"])
    strategy_execution = cast(dict[str, Any], manifest["strategy_execution"])
    source_run_id = cast(str, source_run["run_id"])
    source_revision_id = cast(str, revision["candidate_revision_id"])
    data_snapshot_id = cast(str, run_spec["data_snapshot_id"])
    strategy_protocol_version = cast(str, run_spec["strategy_protocol_version"])
    timing_authority = cast(str, strategy_execution["timing_authority"])
    source_intent_tape_sha256 = cast(
        str, strategy_execution["intent_tape_sha256"]
    )
    parsed_market_input = cast(dict[str, Any], json.loads(market_input))
    bars = cast(list[dict[str, Any]], parsed_market_input["bars"])

    if source_run["status"] != "succeeded":
        return _result(
            forward_test_id=forward_test_id,
            source_run_id=source_run_id,
            source_revision_id=source_revision_id,
            data_snapshot_id=data_snapshot_id,
            strategy_protocol_version=strategy_protocol_version,
            timing_authority=timing_authority,
            source_intent_tape_sha256=source_intent_tape_sha256,
            source_intent_tape=source_intent_tape,
            bars=[],
            replayed_intents=[],
            released_bar_count=0,
            status="failed",
            error_code="source_run_not_succeeded",
        )

    replayed = run_strategy_host(strategy_source, market_input)
    if replayed is None:
        return _result(
            forward_test_id=forward_test_id,
            source_run_id=source_run_id,
            source_revision_id=source_revision_id,
            data_snapshot_id=data_snapshot_id,
            strategy_protocol_version=strategy_protocol_version,
            timing_authority=timing_authority,
            source_intent_tape_sha256=source_intent_tape_sha256,
            source_intent_tape=source_intent_tape,
            bars=[],
            replayed_intents=[],
            released_bar_count=0,
            status="failed",
            error_code="strategy_protocol_failed",
        )

    replayed_tape = canonical_json_bytes(replayed)
    return _result(
        forward_test_id=forward_test_id,
        source_run_id=source_run_id,
        source_revision_id=source_revision_id,
        data_snapshot_id=data_snapshot_id,
        strategy_protocol_version=strategy_protocol_version,
        timing_authority=timing_authority,
        source_intent_tape_sha256=source_intent_tape_sha256,
        source_intent_tape=source_intent_tape,
        bars=bars,
        replayed_intents=replayed,
        released_bar_count=len(bars),
        status=("passed" if replayed_tape == source_intent_tape else "failed"),
        error_code=(
            None
            if replayed_tape == source_intent_tape
            else "transcript_integrity_mismatch"
        ),
    )


def _result(
    *,
    forward_test_id: str,
    source_run_id: str,
    source_revision_id: str,
    data_snapshot_id: str,
    strategy_protocol_version: str,
    timing_authority: str,
    source_intent_tape_sha256: str,
    source_intent_tape: bytes,
    bars: list[dict[str, Any]],
    replayed_intents: list[object],
    released_bar_count: int,
    status: str,
    error_code: str | None,
) -> ForwardReplayResult:
    intent_tape = canonical_json_bytes(replayed_intents)
    intent_tape_sha256 = hashlib.sha256(intent_tape).hexdigest()
    intent_groups: dict[int, list[dict[str, Any]]] = {
        0: [],
        **{bar["session_seq"]: [] for bar in bars},
    }
    for item in replayed_intents:
        intent = cast(dict[str, Any], item)
        known_at = cast(dict[str, Any], intent["known_at"])
        intent_groups[cast(int, known_at["session_seq"])].append(intent)

    transcript = {
        "schema_version": 1,
        "transcript_version": FORWARD_REPLAY_PROTOCOL,
        "forward_test_id": forward_test_id,
        "source_run": {
            "run_id": source_run_id,
            "revision_id": source_revision_id,
            "data_snapshot_id": data_snapshot_id,
        },
        "strategy_protocol": {
            "version": strategy_protocol_version,
            "timing_authority": timing_authority,
        },
        "start_intent_group": intent_groups[0],
        "bar_observations": [
            {
                "bar_index": index,
                "bar": bar,
                "intent_group": intent_groups[bar["session_seq"]],
            }
            for index, bar in enumerate(bars)
        ],
        "released_bar_count": released_bar_count,
        "source_intent_tape_sha256": source_intent_tape_sha256,
        "source_intent_tape_byte_size": len(source_intent_tape),
        "intent_tape_sha256": intent_tape_sha256,
        "intent_tape_byte_size": len(intent_tape),
        "status": status,
        "error_code": error_code,
    }
    transcript_body = canonical_json_bytes(transcript)
    return ForwardReplayResult(
        forward_test_id=forward_test_id,
        source_run_id=source_run_id,
        source_revision_id=source_revision_id,
        data_snapshot_id=data_snapshot_id,
        protocol_version=FORWARD_REPLAY_PROTOCOL,
        released_bar_count=released_bar_count,
        status=status,
        error_code=error_code,
        intent_tape=intent_tape,
        intent_tape_sha256=intent_tape_sha256,
        transcript=transcript_body,
        transcript_sha256=hashlib.sha256(transcript_body).hexdigest(),
    )
