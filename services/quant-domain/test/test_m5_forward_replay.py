from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from quant_domain.formal_runner import run_strategy_host


class M5StreamedStrategyHostTest(unittest.TestCase):
    def test_strategy_receives_only_each_released_bar(self) -> None:
        source = b"""
seen = []

def on_start():
    return []

def on_bar(bar):
    seen.append(bar['session_seq'])
    if any(key in bar for key in ('future_bar', 'bars', 'engine_input')):
        raise RuntimeError('future data was exposed')
    if seen == [1]:
        return [{'intent_seq': 1}]
    return []
"""
        engine_input = json.dumps(
            {
                "bars": [
                    {"session_seq": 1, "close": "10"},
                    {"session_seq": 2, "close": "11"},
                ],
                "intents": [],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

        self.assertEqual(
            run_strategy_host(source, engine_input),
            [
                {
                    "intent_seq": 1,
                    "known_at": {
                        "session_seq": 1,
                        "phase": "close",
                        "stable_seq": 1,
                    },
                    "effective_at": {
                        "session_seq": 2,
                        "phase": "open",
                        "stable_seq": 1,
                    },
                }
            ],
        )

    def test_streamed_strategy_matches_the_expected_intent_tape(self) -> None:
        source = b"""
def on_start():
    return [{
        'intent_id': 'entry', 'intent_seq': 1,
        'side': 'buy', 'quantity': '100', 'order_type': 'market'
    }]

def on_bar(bar):
    if bar['session_seq'] == 1:
        return [{
            'intent_id': 'exit', 'intent_seq': 2,
            'side': 'sell', 'quantity': '100', 'order_type': 'market'
        }]
    return []
"""
        engine_input = b'{"bars":[{"session_seq":1},{"session_seq":2}],"intents":[]}'

        self.assertEqual(
            run_strategy_host(source, engine_input),
            [
                {
                    "intent_id": "entry",
                    "intent_seq": 1,
                    "side": "buy",
                    "quantity": "100",
                    "order_type": "market",
                    "known_at": {
                        "session_seq": 0,
                        "phase": "close",
                        "stable_seq": 1,
                    },
                    "effective_at": {
                        "session_seq": 1,
                        "phase": "open",
                        "stable_seq": 1,
                    },
                },
                {
                    "intent_id": "exit",
                    "intent_seq": 2,
                    "side": "sell",
                    "quantity": "100",
                    "order_type": "market",
                    "known_at": {
                        "session_seq": 1,
                        "phase": "close",
                        "stable_seq": 2,
                    },
                    "effective_at": {
                        "session_seq": 2,
                        "phase": "open",
                        "stable_seq": 2,
                    },
                },
            ],
        )

    def test_candidate_module_state_persists_across_streamed_bars(self) -> None:
        source = b"""
state = []

def on_start():
    state.append('started')
    return []

def on_bar(bar):
    state.append(bar['session_seq'])
    if state == ['started', 1]:
        return [{'intent_seq': 1}]
    if state == ['started', 1, 2]:
        return []
    raise RuntimeError('state was not preserved')
"""

        result = run_strategy_host(
            source,
            b'{"bars":[{"session_seq":1},{"session_seq":2}],"intents":[]}',
        )
        self.assertEqual(result[0]["intent_seq"], 1)

    def test_final_bar_signal_is_ignored_without_a_next_execution_bar(self) -> None:
        source = b"""
def on_start():
    return []

def on_bar(bar):
    if bar['session_seq'] == 2:
        return [{'intent_seq': 1}]
    return []
"""

        self.assertEqual(
            run_strategy_host(
                source,
                b'{"bars":[{"session_seq":1},{"session_seq":2}],"intents":[]}',
            ),
            [],
        )

    def test_effective_at_must_be_current_or_later_open(self) -> None:
        earlier = b"""
def on_start():
    return [{'intent_seq': 1, 'effective_at': {
        'session_seq': 0, 'phase': 'open', 'stable_seq': 1
    }}]

def on_bar(bar):
    return []
"""
        later = b"""
def on_start():
    return [{'intent_seq': 1, 'effective_at': {
        'session_seq': 3, 'phase': 'open', 'stable_seq': 1
    }}]

def on_bar(bar):
    return []
"""
        engine_input = b'{"bars":[{"session_seq":1},{"session_seq":2}],"intents":[]}'
        self.assertIsNone(run_strategy_host(earlier, engine_input))
        self.assertEqual(
            run_strategy_host(later, engine_input)[0]["effective_at"]["session_seq"],
            3,
        )

    def test_hung_strategy_times_out_and_process_is_reaped(self) -> None:
        source = b"""
import time

def on_start():
    time.sleep(20)
    return []

def on_bar(bar):
    return []
"""
        with patch(
            "quant_domain.formal_runner.STRATEGY_RESPONSE_TIMEOUT_SECONDS", 0.05
        ):
            self.assertIsNone(
                run_strategy_host(
                    source,
                    b'{"bars":[{"session_seq":1}],"intents":[]}',
                )
            )


if __name__ == "__main__":
    unittest.main()
