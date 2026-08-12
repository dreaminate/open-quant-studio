from __future__ import annotations

import hashlib
import json
import unittest

from quant_domain.domain import QuantDomain
from quant_domain.formal_runner import run_strategy_host
from quant_domain.forward_replay import canonical_json_bytes, replay_forward_test
from test_m1_http import HttpTestCase
from test_m2_session import (
    ACTIVITY_ID,
    CORRELATION_ID,
    PROJECT_ID,
    SENDER_SESSION_ID,
    register_command,
)
import test_m3_formal_runs as _m3


SOURCE_RUN = {
    "run_id": "18181818-1818-4181-8181-181818181818",
    "status": "succeeded",
}
FORWARD_TEST_ID = "52525252-5252-4252-8252-525252525252"

MARKET_INPUT = canonical_json_bytes(
    {
        "schema_version": 1,
        "account": {
            "model": "a_share_cash",
            "symbol": "SYNTH.XSHG",
            "price_scale": 100,
            "cash_scale": 100,
            "rate_scale": 1000000,
            "starting_balance_atoms": "1000000",
            "lot_size": 100,
            "allow_research_short": True,
            "commission_rate_atoms": "600",
            "stamp_duty_rate_atoms": "1000",
            "maker_fee_rate_atoms": "0",
            "taker_fee_rate_atoms": "0",
            "slippage_atoms": "10",
        },
        "bars": [
            {
                "session_seq": 1,
                "timestamp": "2026-01-02T07:00:00Z",
                "open_atoms": "1000",
                "high_atoms": "1120",
                "low_atoms": "990",
                "close_atoms": "1100",
                "can_buy": True,
                "can_sell": True,
            },
            {
                "session_seq": 2,
                "timestamp": "2026-01-05T07:00:00Z",
                "open_atoms": "1200",
                "high_atoms": "1210",
                "low_atoms": "1180",
                "close_atoms": "1200",
                "can_buy": True,
                "can_sell": True,
            },
            {
                "session_seq": 3,
                "timestamp": "2026-01-06T07:00:00Z",
                "open_atoms": "1000",
                "high_atoms": "1020",
                "low_atoms": "980",
                "close_atoms": "1000",
                "can_buy": True,
                "can_sell": True,
            },
            {
                "session_seq": 4,
                "timestamp": "2026-01-07T07:00:00Z",
                "open_atoms": "900",
                "high_atoms": "920",
                "low_atoms": "880",
                "close_atoms": "900",
                "can_buy": True,
                "can_sell": True,
            },
        ],
        "funding_events": [],
    }
)

STRATEGY_SOURCE = b"""
INTENTS = {
    0: [{
        'intent_id': 'long-entry', 'intent_seq': 1, 'symbol': 'SYNTH.XSHG',
        'side': 'buy', 'position_effect': 'open', 'quantity': '100',
        'order_type': 'market', 'limit_price_atoms': None, 'stop_price_atoms': None,
        'time_in_force': 'day', 'oco_group': None,
    }],
    1: [{
        'intent_id': 'long-exit', 'intent_seq': 2, 'symbol': 'SYNTH.XSHG',
        'side': 'sell', 'position_effect': 'close', 'quantity': '100',
        'order_type': 'market', 'limit_price_atoms': None, 'stop_price_atoms': None,
        'time_in_force': 'day', 'oco_group': None,
    }],
    2: [{
        'intent_id': 'short-entry', 'intent_seq': 3, 'symbol': 'SYNTH.XSHG',
        'side': 'sell', 'position_effect': 'open', 'quantity': '100',
        'order_type': 'market', 'limit_price_atoms': None, 'stop_price_atoms': None,
        'time_in_force': 'day', 'oco_group': None,
    }],
    3: [{
        'intent_id': 'short-cover', 'intent_seq': 4, 'symbol': 'SYNTH.XSHG',
        'side': 'buy', 'position_effect': 'close', 'quantity': '100',
        'order_type': 'market', 'limit_price_atoms': None, 'stop_price_atoms': None,
        'time_in_force': 'day', 'oco_group': None,
    }],
}

def on_start():
    return INTENTS.get(0, [])

def on_bar(bar):
    return INTENTS.get(bar['session_seq'], [])
"""


def source_manifest(source_tape: bytes) -> dict[str, object]:
    return {
        "manifest_version": "m5-v1",
        "run_spec": {
            "candidate_revision_id": "77777777-7777-4777-8777-777777777777",
            "data_snapshot_id": "23232323-2323-4232-8232-232323232323",
            "strategy_protocol_version": "oqs-strategy-host/m5-stream-v2",
        },
        "revision": {
            "candidate_revision_id": "77777777-7777-4777-8777-777777777777",
        },
        "strategy_execution": {
            "intent_tape_sha256": hashlib.sha256(source_tape).hexdigest(),
            "timing_authority": "oqs-strategy-host/m5-stream-v2",
        },
    }


class M5ForwardTestReplayTest(unittest.TestCase):
    def _tape_for(self, strategy_source: bytes) -> bytes:
        emitted = run_strategy_host(strategy_source, MARKET_INPUT)
        self.assertIsNotNone(emitted)
        return canonical_json_bytes(emitted)

    def test_identical_legal_replay_produces_a_deterministic_transcript(self) -> None:
        source_tape = self._tape_for(STRATEGY_SOURCE)

        result = replay_forward_test(
            forward_test_id=FORWARD_TEST_ID,
            source_run=SOURCE_RUN,
            source_manifest=source_manifest(source_tape),
            strategy_source=STRATEGY_SOURCE,
            market_input=MARKET_INPUT,
            source_intent_tape=source_tape,
        )

        self.assertEqual(result.status, "passed")
        self.assertIsNone(result.error_code)
        self.assertEqual(result.released_bar_count, 4)
        self.assertEqual(result.intent_tape, source_tape)
        replayed_again = replay_forward_test(
            forward_test_id=FORWARD_TEST_ID,
            source_run=SOURCE_RUN,
            source_manifest=source_manifest(source_tape),
            strategy_source=STRATEGY_SOURCE,
            market_input=MARKET_INPUT,
            source_intent_tape=source_tape,
        )
        self.assertEqual(result.transcript, replayed_again.transcript)
        self.assertEqual(
            result.intent_tape_sha256, hashlib.sha256(source_tape).hexdigest()
        )
        self.assertEqual(
            result.transcript_sha256, hashlib.sha256(result.transcript).hexdigest()
        )
        transcript = json.loads(result.transcript)
        self.assertEqual(
            transcript["source_run"],
            {
                "run_id": SOURCE_RUN["run_id"],
                "revision_id": "77777777-7777-4777-8777-777777777777",
                "data_snapshot_id": "23232323-2323-4232-8232-232323232323",
            },
        )
        self.assertEqual(transcript["forward_test_id"], FORWARD_TEST_ID)
        self.assertEqual(
            [item["bar"]["session_seq"] for item in transcript["bar_observations"]],
            [1, 2, 3, 4],
        )
        self.assertEqual(
            transcript["start_intent_group"][0]["intent_id"], "long-entry"
        )
        self.assertEqual(
            transcript["bar_observations"][0]["intent_group"][0]["intent_id"],
            "long-exit",
        )
        self.assertEqual(transcript["bar_observations"][-1]["intent_group"], [])

    def test_legal_source_tape_difference_is_reported_as_a_forward_test_failure(
        self,
    ) -> None:
        alternate_source = STRATEGY_SOURCE.replace(
            b"'quantity': '100'", b"'quantity': '200'", 2
        )
        source_tape = self._tape_for(alternate_source)

        result = replay_forward_test(
            forward_test_id=FORWARD_TEST_ID,
            source_run=SOURCE_RUN,
            source_manifest=source_manifest(source_tape),
            strategy_source=STRATEGY_SOURCE,
            market_input=MARKET_INPUT,
            source_intent_tape=source_tape,
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "transcript_integrity_mismatch")
        self.assertNotEqual(result.intent_tape, source_tape)
        transcript = json.loads(result.transcript)
        self.assertEqual(transcript["status"], "failed")
        self.assertEqual(
            transcript["intent_tape_sha256"], result.intent_tape_sha256
        )


class M5ForwardTestDomainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _m3.M3FormalRunDomainTest(
            "test_merge_candidate_is_two_parent_immutable_and_moves_no_head"
        )
        self.fixture.setUp()
        self.domain: QuantDomain = self.fixture.domain
        self.domain.submit_command(self.fixture._merge_command())
        self.domain.submit_command(self.fixture._formal_run_command())
        completed = self.domain.run_next_job()
        self.assertEqual(completed["status"], "succeeded")

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def _command(self) -> dict[str, object]:
        return {
            "command_id": "53535353-5353-4353-8353-535353535353",
            "schema_version": 1,
            "command_type": "forward_test.request",
            "project_id": PROJECT_ID,
            "activity_id": ACTIVITY_ID,
            "session_id": SENDER_SESSION_ID,
            "workbench_id": "canvas",
            "correlation_id": CORRELATION_ID,
            "expected_revision_id": _m3.MERGE_REVISION_ID,
            "variant_id": _m3.VARIANT_ID,
            "base_revision_id": _m3.MERGE_REVISION_ID,
            "payload": {
                "forward_test_id": FORWARD_TEST_ID,
                "source_run_id": _m3.RUN_ID,
                "protocol_version": "oqs-forward-replay/m5-v1",
            },
        }

    def test_command_replays_a_succeeded_run_and_is_idempotent(self) -> None:
        command = self._command()

        accepted = self.domain.submit_command(command)
        replayed = self.domain.submit_command(command)

        self.assertEqual(accepted["event"]["event_type"], "forward_test.completed")
        self.assertEqual(accepted["event"]["payload"]["status"], "passed")
        self.assertEqual(replayed["disposition"], "replayed")
        detail = self.domain.forward_test(PROJECT_ID, FORWARD_TEST_ID)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["source_run_id"], _m3.RUN_ID)
        self.assertEqual(detail["released_bar_count"], 4)
        transcript = self.domain.artifact_content(
            PROJECT_ID, detail["transcript_artifact_id"]
        )
        self.assertIsNotNone(transcript)
        self.assertEqual(
            hashlib.sha256(transcript[1]).hexdigest(), detail["transcript_sha256"]
        )


class M5ForwardTestHttpTest(HttpTestCase):
    def test_forward_test_read_endpoint_returns_the_persisted_result(self) -> None:
        scenario = _m3.M3FormalRunDomainTest(
            "test_merge_candidate_is_two_parent_immutable_and_moves_no_head"
        )
        scenario.data_root = self.data_root
        scenario.domain = QuantDomain(self.data_root)
        scenario.domain.submit_command(register_command())
        scenario._create_variant_revision()
        scenario.domain.submit_command(scenario._merge_command())
        scenario.domain.submit_command(scenario._formal_run_command())
        self.assertEqual(scenario.domain.run_next_job()["status"], "succeeded")
        command = M5ForwardTestDomainTest._command(self)  # type: ignore[arg-type]
        scenario.domain.submit_command(command)

        status, _, body = self.request(
            "GET",
            f"/v1/projects/{PROJECT_ID}/forward-tests/{FORWARD_TEST_ID}",
        )

        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["source_run_id"], _m3.RUN_ID)


if __name__ == "__main__":
    unittest.main()
