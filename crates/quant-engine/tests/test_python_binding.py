from __future__ import annotations

import json
import unittest
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

import oqs_quant_engine


class PythonBindingTest(unittest.TestCase):
    def test_python_calls_the_same_deterministic_engine_bytes(self) -> None:
        engine_input = {
            "schema_version": 1,
            "account": {
                "model": "a_share_cash",
                "symbol": "600000.XSHG",
                "price_scale": 100,
                "cash_scale": 100,
                "rate_scale": 1_000_000,
                "starting_balance_atoms": "1000000",
                "lot_size": 100,
                "allow_research_short": False,
                "commission_rate_atoms": "600",
                "stamp_duty_rate_atoms": "0",
                "maker_fee_rate_atoms": "0",
                "taker_fee_rate_atoms": "0",
                "slippage_atoms": "0",
            },
            "bars": [
                {
                    "session_seq": 1,
                    "timestamp": "2026-01-02T07:00:00Z",
                    "open_atoms": "1000",
                    "high_atoms": "1100",
                    "low_atoms": "990",
                    "close_atoms": "1100",
                    "can_buy": True,
                    "can_sell": True,
                }
            ],
            "funding_events": [],
            "intents": [
                {
                    "intent_id": "buy-1",
                    "intent_seq": 1,
                    "symbol": "600000.XSHG",
                    "side": "buy",
                    "position_effect": "open",
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
                    "limit_price_atoms": None,
                    "stop_price_atoms": None,
                    "time_in_force": "day",
                    "oco_group": None,
                }
            ],
        }
        encoded = json.dumps(engine_input, separators=(",", ":")).encode()

        first = oqs_quant_engine.run_engine_v1(encoded)
        second = oqs_quant_engine.run_engine_v1(encoded)
        output = json.loads(first)

        self.assertIsInstance(first, bytes)
        self.assertEqual(first, second)
        self.assertEqual(output["engine_version"], "oqs-quant-engine/0.1.0")
        self.assertEqual(output["metrics"]["ending_equity_atoms"], "1009940")
        self.assertEqual(output["metrics"]["open_position_count"], 1)

    def test_formal_fixture_reconciles_with_independent_decimal_reference(self) -> None:
        fixture_path = (
            Path(__file__).parents[3]
            / "fixtures"
            / "backtests"
            / "m3-a-share-long-short-v1.json"
        )
        fixture = json.loads(fixture_path.read_text())
        engine_input = fixture["input"]
        output = json.loads(
            oqs_quant_engine.run_engine_v1(
                json.dumps(engine_input, separators=(",", ":")).encode()
            )
        )

        account = engine_input["account"]
        bars = {bar["session_seq"]: bar for bar in engine_input["bars"]}
        rate_scale = Decimal(account["rate_scale"])
        commission_rate = Decimal(account["commission_rate_atoms"])
        stamp_duty_rate = Decimal(account["stamp_duty_rate_atoms"])
        cash = Decimal(account["starting_balance_atoms"])
        signed_quantity = Decimal(0)
        total_fees = Decimal(0)
        total_stamp_duty = Decimal(0)
        total_slippage = Decimal(0)
        equity_atoms: list[str] = []

        for trade in output["trades"]:
            quantity = Decimal(trade["quantity"])
            fill_price = Decimal(trade["fill_price_atoms"])
            notional = fill_price * quantity
            fee = (notional * commission_rate / rate_scale).to_integral_value(
                rounding=ROUND_CEILING
            )
            stamp_duty = (
                (notional * stamp_duty_rate / rate_scale).to_integral_value(
                    rounding=ROUND_CEILING
                )
                if trade["side"] == "sell"
                else Decimal(0)
            )
            bar = bars[trade["session_seq"]]
            open_price = Decimal(bar["open_atoms"])
            slippage = abs(fill_price - open_price) * quantity

            self.assertEqual(Decimal(trade["notional_atoms"]), notional)
            self.assertEqual(Decimal(trade["fee_atoms"]), fee)
            self.assertEqual(Decimal(trade["stamp_duty_atoms"]), stamp_duty)
            self.assertEqual(Decimal(trade["slippage_atoms"]), slippage)

            if trade["side"] == "buy":
                cash -= notional + fee
            else:
                cash += notional - fee - stamp_duty
            if (trade["side"], trade["position_effect"]) in {
                ("buy", "open"),
                ("buy", "close"),
            }:
                signed_quantity += quantity
            else:
                signed_quantity -= quantity

            total_fees += fee
            total_stamp_duty += stamp_duty
            total_slippage += slippage
            close_price = Decimal(bar["close_atoms"])
            equity_atoms.append(str(cash + signed_quantity * close_price))

        self.assertEqual(
            [point["equity_atoms"] for point in output["equity_curve"]],
            equity_atoms,
        )
        self.assertEqual(Decimal(output["metrics"]["ending_equity_atoms"]), cash)
        self.assertEqual(Decimal(output["metrics"]["total_fees_atoms"]), total_fees)
        self.assertEqual(
            Decimal(output["metrics"]["total_stamp_duty_atoms"]),
            total_stamp_duty,
        )
        self.assertEqual(
            Decimal(output["metrics"]["total_slippage_atoms"]), total_slippage
        )

    def test_python_checkpoint_round_trip(self) -> None:
        fixture_path = (
            Path(__file__).parents[3]
            / "fixtures"
            / "backtests"
            / "m3-a-share-long-short-v1.json"
        )
        fixture = json.loads(fixture_path.read_text())
        encoded = json.dumps(fixture["input"], separators=(",", ":")).encode()
        context = "d" * 64
        expected = oqs_quant_engine.run_engine_v1(encoded)
        checkpoint = oqs_quant_engine.start_engine_checkpoint_v1(encoded, context, 1)
        while json.loads(checkpoint)["status"] != "complete":
            checkpoint = oqs_quant_engine.step_engine_checkpoint_v1(
                encoded, context, checkpoint
            )
        self.assertEqual(
            oqs_quant_engine.finalize_engine_checkpoint_v1(
                encoded, context, checkpoint
            ),
            expected,
        )

    def test_python_calls_the_portfolio_v2_engine_and_restarts_by_session_batch(self) -> None:
        fixture_path = (
            Path(__file__).parents[3]
            / "fixtures"
            / "backtests"
            / "m8-a-share-rotation-v2.json"
        )
        fixture = json.loads(fixture_path.read_text())
        encoded = json.dumps(fixture["input"], separators=(",", ":")).encode()
        context = "e" * 64

        direct = oqs_quant_engine.run_engine_v2(encoded)
        checkpoint = oqs_quant_engine.start_engine_checkpoint_v2(encoded, context, 2)
        while json.loads(checkpoint)["status"] != "complete":
            checkpoint = oqs_quant_engine.step_engine_checkpoint_v2(
                encoded, context, checkpoint
            )

        self.assertIsInstance(direct, bytes)
        self.assertEqual(
            oqs_quant_engine.finalize_engine_checkpoint_v2(
                encoded, context, checkpoint
            ),
            direct,
        )
        output = json.loads(direct)
        self.assertEqual(output["schema_version"], 2)
        self.assertEqual(output["engine_version"], "oqs-quant-engine/0.2.0")
        self.assertEqual(output["equity_curve"][2]["market_value_atoms"], "13500")


if __name__ == "__main__":
    unittest.main()
