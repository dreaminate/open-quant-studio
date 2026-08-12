from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from quant_domain.formal_runner import run_strategy_host
from oqs_quant_engine import run_engine_v1


ROOT = Path(__file__).resolve().parents[3]
STRATEGY_DIRECTORY = ROOT / "strategies"
CATALOG_PATH = STRATEGY_DIRECTORY / "catalog.json"
FINALIZER_PATH = ROOT / "scripts" / "finalize-strategy-notebooks.py"

EXPECTED_STRATEGY_IDS = (
    "a_share_trend_breakout",
    "a_share_research_short",
    "a_share_rotation",
    "crypto_trend",
    "crypto_mean_reversion",
    "crypto_breakout",
)

SINGLE_SYMBOL_CASES = {
    "a_share_trend_breakout": {
        "symbol": "SYNTH.XSHG",
        "closes": [100, 101, 102, 104, 105, 102, 100, 99, 99],
        "orders": [("buy", "open"), ("sell", "close")],
    },
    "a_share_research_short": {
        "symbol": "SYNTH.XSHG",
        "closes": [100, 99, 98, 95, 94, 97, 100, 102, 102],
        "orders": [("sell", "open"), ("buy", "close")],
    },
    "crypto_trend": {
        "symbol": "BTCUSDT.PERP",
        "closes": [100, 102, 104, 107, 110, 107, 104, 102, 102],
        "orders": [("buy", "open"), ("sell", "close")],
    },
    "crypto_mean_reversion": {
        "symbol": "BTCUSDT.PERP",
        "closes": [100, 100, 100, 90, 95, 100, 103, 100, 100],
        "orders": [("buy", "open"), ("sell", "close")],
    },
    "crypto_breakout": {
        "symbol": "BTCUSDT.PERP",
        "closes": [100, 101, 102, 106, 108, 103, 100, 99, 99],
        "orders": [("buy", "open"), ("sell", "close")],
    },
}


def load_catalog() -> dict[str, object]:
    return json.loads(CATALOG_PATH.read_text())


def strategy_record(strategy_id: str) -> dict[str, object]:
    catalog = load_catalog()
    return next(
        record
        for record in catalog["strategies"]
        if record["strategy_id"] == strategy_id
    )


def market_input(symbol: str, closes: list[int]) -> bytes:
    bars = [
        {
            "session_seq": index,
            "timestamp": f"2026-01-{index:02d}T00:00:00Z",
            "symbol": symbol,
            "open_atoms": str(close - 1),
            "high_atoms": str(close + 2),
            "low_atoms": str(close - 3),
            "close_atoms": str(close),
            "can_buy": True,
            "can_sell": True,
        }
        for index, close in enumerate(closes, start=1)
    ]
    return json.dumps({"schema_version": 1, "bars": bars, "intents": []}, sort_keys=True).encode()


def formal_input(symbol: str, closes: list[int], intents: list[object], market: str) -> bytes:
    streamed = json.loads(market_input(symbol, closes))
    account = {
        "model": market,
        "symbol": symbol,
        "price_scale": 100,
        "cash_scale": 100,
        "rate_scale": 1_000_000,
        "starting_balance_atoms": "1000000",
        "lot_size": 100 if market == "a_share_cash" else 1,
        "allow_research_short": market == "a_share_cash",
        "commission_rate_atoms": "600" if market == "a_share_cash" else "0",
        "stamp_duty_rate_atoms": "1000" if market == "a_share_cash" else "0",
        "maker_fee_rate_atoms": "0" if market == "a_share_cash" else "200",
        "taker_fee_rate_atoms": "0" if market == "a_share_cash" else "600",
        "slippage_atoms": "0",
    }
    return json.dumps(
        {
            "schema_version": 1,
            "account": account,
            "bars": [
                {key: value for key, value in bar.items() if key != "symbol"}
                for bar in streamed["bars"]
            ],
            "funding_events": [],
            "intents": intents,
        },
        sort_keys=True,
    ).encode()


def rotation_input() -> bytes:
    closes_by_session = (
        {"AAA.XSHG": 100, "BBB.XSHG": 100, "CCC.XSHG": 100},
        {"AAA.XSHG": 110, "BBB.XSHG": 105, "CCC.XSHG": 102},
        {"AAA.XSHG": 111, "BBB.XSHG": 120, "CCC.XSHG": 102},
        {"AAA.XSHG": 112, "BBB.XSHG": 132, "CCC.XSHG": 103},
        {"AAA.XSHG": 113, "BBB.XSHG": 145, "CCC.XSHG": 104},
    )
    bars = []
    for session_seq, closes in enumerate(closes_by_session, start=1):
        for symbol_index, symbol in enumerate(("AAA.XSHG", "BBB.XSHG", "CCC.XSHG")):
            close = closes[symbol]
            bars.append(
                {
                    "session_seq": session_seq,
                    "timestamp": f"2026-02-{session_seq:02d}T00:00:00Z",
                    "symbol": symbol,
                    "open_atoms": str(close - 1),
                    "high_atoms": str(close + 2),
                    "low_atoms": str(close - 3),
                    "close_atoms": str(close),
                    "can_buy": True,
                    "can_sell": True,
                    "session_end": symbol_index == 2,
                }
            )
    return json.dumps({"schema_version": 1, "bars": bars, "intents": []}, sort_keys=True).encode()


class M8StrategyLibraryTest(unittest.TestCase):
    def _source(self, strategy_id: str) -> bytes:
        record = strategy_record(strategy_id)
        return (ROOT / record["source"]).read_bytes()

    def _assert_legal_intents(self, emitted: list[object]) -> None:
        self.assertTrue(emitted)
        self.assertEqual(
            [intent["intent_seq"] for intent in emitted],
            list(range(1, len(emitted) + 1)),
        )
        for intent in emitted:
            self.assertEqual(
                set(intent),
                {
                    "intent_id",
                    "intent_seq",
                    "symbol",
                    "side",
                    "position_effect",
                    "quantity",
                    "order_type",
                    "limit_price_atoms",
                    "stop_price_atoms",
                    "time_in_force",
                    "oco_group",
                    "known_at",
                    "effective_at",
                },
            )
            self.assertIn(intent["side"], {"buy", "sell"})
            self.assertIn(intent["position_effect"], {"open", "close"})
            self.assertGreater(int(intent["quantity"]), 0)
            self.assertEqual(intent["order_type"], "market")
            self.assertEqual(intent["time_in_force"], "day")
            self.assertIsNone(intent["limit_price_atoms"])
            self.assertIsNone(intent["stop_price_atoms"])
            self.assertIsNone(intent["oco_group"])
            self.assertEqual(intent["known_at"]["phase"], "close")
            self.assertEqual(intent["effective_at"]["phase"], "open")
            self.assertGreater(
                intent["effective_at"]["session_seq"],
                intent["known_at"]["session_seq"],
            )

    def test_catalog_has_exactly_six_unique_strategy_ids(self) -> None:
        catalog = load_catalog()

        self.assertEqual(catalog["schema_version"], 1)
        records = catalog["strategies"]
        self.assertEqual(
            tuple(record["strategy_id"] for record in records), EXPECTED_STRATEGY_IDS
        )
        self.assertEqual(len({record["strategy_id"] for record in records}), 6)
        for record in records:
            self.assertTrue((ROOT / record["source"]).is_file())
            self.assertTrue((ROOT / record["notebook"]).is_file())

    def test_notebook_finalization_is_deterministic(self) -> None:
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as temporary:
            output_directory = Path(temporary)
            command = [
                sys.executable,
                str(FINALIZER_PATH),
                "--catalog",
                str(CATALOG_PATH),
                "--output-dir",
                str(output_directory),
            ]
            subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            first = {
                record["notebook"]: (output_directory / record["notebook"]).read_bytes()
                for record in catalog["strategies"]
            }
            subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            second = {
                record["notebook"]: (output_directory / record["notebook"]).read_bytes()
                for record in catalog["strategies"]
            }

        self.assertEqual(first, second)
        self.assertEqual(
            first,
            {
                record["notebook"]: (ROOT / record["notebook"]).read_bytes()
                for record in catalog["strategies"]
            },
        )

    def test_notebook_source_cells_match_the_authoritative_python_sources(self) -> None:
        for record in load_catalog()["strategies"]:
            source_path = ROOT / record["source"]
            source = source_path.read_text()
            notebook = json.loads((ROOT / record["notebook"]).read_text())
            source_cells = [
                cell
                for cell in notebook["cells"]
                if cell["cell_type"] == "code"
                and cell["metadata"].get("oqs", {}).get("role")
                == "authoritative_source"
            ]
            example_cells = [
                cell
                for cell in notebook["cells"]
                if cell["cell_type"] == "code"
                and cell["metadata"].get("oqs", {}).get("role")
                == "example_not_executed"
            ]

            self.assertEqual(len(source_cells), 1)
            self.assertEqual(source_cells[0]["source"], source)
            self.assertEqual(len(example_cells), 1)
            self.assertIsNone(example_cells[0]["execution_count"])
            self.assertEqual(
                notebook["metadata"]["oqs"]["source_sha256"],
                hashlib.sha256(source.encode()).hexdigest(),
            )
            self.assertEqual(
                notebook["metadata"]["oqs"]["generator"],
                "oqs-finalize-strategy-notebooks/v1",
            )

    def test_single_symbol_strategies_emit_legal_next_bar_intents(self) -> None:
        for strategy_id, case in SINGLE_SYMBOL_CASES.items():
            with self.subTest(strategy_id=strategy_id):
                emitted = run_strategy_host(
                    self._source(strategy_id),
                    market_input(case["symbol"], case["closes"]),
                )

                self.assertIsNotNone(emitted)
                self._assert_legal_intents(emitted)
                self.assertEqual(
                    [(intent["side"], intent["position_effect"]) for intent in emitted],
                    case["orders"],
                )

    def test_five_single_symbol_strategies_complete_real_formal_engine_runs(self) -> None:
        for strategy_id, case in SINGLE_SYMBOL_CASES.items():
            with self.subTest(strategy_id=strategy_id):
                source_input = market_input(case["symbol"], case["closes"])
                emitted = run_strategy_host(self._source(strategy_id), source_input)
                self.assertIsNotNone(emitted)
                market = (
                    "a_share_cash"
                    if strategy_id.startswith("a_share_")
                    else "crypto_linear_perp"
                )
                result = json.loads(
                    run_engine_v1(
                        formal_input(case["symbol"], case["closes"], emitted, market)
                    )
                )

                self.assertEqual(result["metrics"]["fill_count"], 2)
                self.assertEqual(len(result["orders"]), 2)
                self.assertEqual(len(result["trades"]), 2)
                self.assertEqual(result["metrics"]["open_position_count"], 0)

    def test_rotation_ranks_completed_three_symbol_sessions_and_preserves_state(self) -> None:
        emitted = run_strategy_host(
            self._source("a_share_rotation"),
            rotation_input(),
        )

        self.assertIsNotNone(emitted)
        self._assert_legal_intents(emitted)
        self.assertEqual(
            [
                (intent["symbol"], intent["side"], intent["position_effect"])
                for intent in emitted
            ],
            [
                ("AAA.XSHG", "buy", "open"),
                ("AAA.XSHG", "sell", "close"),
                ("BBB.XSHG", "buy", "open"),
            ],
        )
        self.assertEqual(
            [intent["known_at"]["session_seq"] for intent in emitted],
            [2, 3, 3],
        )


if __name__ == "__main__":
    unittest.main()
