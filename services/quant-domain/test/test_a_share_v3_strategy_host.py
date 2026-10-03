from __future__ import annotations

import json
import unittest
from pathlib import Path

from quant_domain.formal_runner import run_strategy_host


V3_STRATEGY_INPUT = json.dumps(
    {
        "schema_version": 3,
        "bars": [
            {
                "session_seq": 1,
                "timestamp": "2026-01-02T07:00:00Z",
                "session_end": False,
                "symbol": "AAA.XSHG",
                "trading_status": "tradable",
                "price_limit_state": "none",
                "raw": {
                    "open_atoms": "100000",
                    "high_atoms": "104000",
                    "low_atoms": "99000",
                    "close_atoms": "103000",
                    "volume_quantity": "1000000",
                },
                "research": {
                    "open_atoms": "90000",
                    "high_atoms": "94000",
                    "low_atoms": "89000",
                    "close_atoms": "93000",
                },
            },
            {
                "session_seq": 1,
                "timestamp": "2026-01-02T07:00:00Z",
                "session_end": True,
                "symbol": "BBB.XSHG",
                "trading_status": "tradable",
                "price_limit_state": "none",
                "raw": {
                    "open_atoms": "200000",
                    "high_atoms": "204000",
                    "low_atoms": "199000",
                    "close_atoms": "203000",
                    "volume_quantity": "800000",
                },
                "research": {
                    "open_atoms": "190000",
                    "high_atoms": "194000",
                    "low_atoms": "189000",
                    "close_atoms": "193000",
                },
            },
            {
                "session_seq": 2,
                "timestamp": "2026-01-05T07:00:00Z",
                "session_end": True,
                "symbol": "AAA.XSHG",
                "trading_status": "tradable",
                "price_limit_state": "none",
                "raw": {
                    "open_atoms": "110000",
                    "high_atoms": "114000",
                    "low_atoms": "109000",
                    "close_atoms": "113000",
                    "volume_quantity": "1200000",
                },
                "research": {
                    "open_atoms": "100000",
                    "high_atoms": "104000",
                    "low_atoms": "99000",
                    "close_atoms": "103000",
                },
            },
        ],
        "intents": [],
    },
    sort_keys=True,
    separators=(",", ":"),
).encode()


class AShareV3StrategyHostTest(unittest.TestCase):
    def test_builtin_a_share_sources_emit_explicit_v3_books(self) -> None:
        root = Path(__file__).resolve().parents[3]
        bars = []
        symbols = ["AAA.XSHG", "BBB.XSHG", "CCC.XSHG"]
        for session_seq in range(1, 9):
            for index, symbol in enumerate(symbols):
                close = 100 + session_seq * (index + 1)
                bars.append(
                    {
                        "session_seq": session_seq,
                        "timestamp": f"2026-01-{session_seq:02d}T07:00:00Z",
                        "session_end": index == len(symbols) - 1,
                        "symbol": symbol,
                        "trading_status": "tradable",
                        "price_limit_state": "none",
                        "raw": {
                            "open_atoms": str(close - 1),
                            "high_atoms": str(close + 2),
                            "low_atoms": str(close - 3),
                            "close_atoms": str(close),
                            "volume_quantity": "1000000",
                        },
                        "research": {
                            "open_atoms": str(close - 1),
                            "high_atoms": str(close + 2),
                            "low_atoms": str(close - 3),
                            "close_atoms": str(close),
                        },
                    }
                )
        engine_input = json.dumps(
            {"schema_version": 3, "bars": bars, "intents": []},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        for strategy_id in (
            "a_share_trend_breakout",
            "a_share_research_short",
            "a_share_rotation",
        ):
            source = (root / "strategies" / strategy_id / "strategy.py").read_bytes()
            emitted = run_strategy_host(
                source,
                engine_input,
                strategy_protocol_version="oqs-strategy-host/a-share-v3",
            )
            self.assertIsNotNone(emitted, strategy_id)
            for intent in emitted or []:
                self.assertEqual(intent["intent_kind"], "order")
                self.assertIn(intent["book"], {"cash_long", "research_short"})
                self.assertNotIn("stop_price_atoms", intent)
                self.assertNotIn("oco_group", intent)

    def test_v3_on_bar_receives_only_flattened_pit_view_and_executes_next_session(self) -> None:
        source = b"""
def on_start():
    return []

def on_bar(bar):
    expected = {
        'session_seq', 'timestamp', 'session_end', 'symbol',
        'trading_status', 'price_limit_state',
        'open_atoms', 'high_atoms', 'low_atoms', 'close_atoms', 'volume_quantity'
    }
    if set(bar) != expected or 'raw' in bar or 'research' in bar:
        raise RuntimeError('v3 view leaked or is not flat')
    if bar['symbol'] == 'AAA.XSHG' and bar['session_seq'] == 1:
        if bar['open_atoms'] != '90000' or bar['volume_quantity'] != '1000000':
            raise RuntimeError('strategy did not receive the PIT research view')
        return [{
            'intent_id': 'next-session', 'intent_seq': 1,
            'symbol': 'AAA.XSHG', 'side': 'buy', 'quantity': '100'
        }]
    if bar['session_seq'] == 2:
        return [{
            'intent_id': 'no-future-session', 'intent_seq': 2,
            'symbol': 'AAA.XSHG', 'side': 'buy', 'quantity': '100'
        }]
    return []
"""

        emitted = run_strategy_host(
            source,
            V3_STRATEGY_INPUT,
            strategy_protocol_version="oqs-strategy-host/a-share-v3",
        )

        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["intent_id"], "next-session")
        self.assertEqual(emitted[0]["known_at"]["session_seq"], 1)
        self.assertEqual(emitted[0]["effective_at"]["session_seq"], 2)

    def test_v3_strategy_host_rejects_a_mismatched_protocol_label(self) -> None:
        source = b"def on_bar(bar):\n    return []\n"

        self.assertIsNone(
            run_strategy_host(
                source,
                V3_STRATEGY_INPUT,
                strategy_protocol_version="oqs-strategy-host/m5-stream-v2",
            )
        )


if __name__ == "__main__":
    unittest.main()
