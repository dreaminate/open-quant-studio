from __future__ import annotations

import csv
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path


MONEY = Decimal("0.0001")
RATIO = Decimal("0.0000000000000001")


def money(value: Decimal) -> str:
    return str(value.quantize(MONEY))


repo_root = Path(__file__).resolve().parents[1]
spec_path = repo_root / sys.argv[1]
spec = json.loads(spec_path.read_text())
market_path = repo_root / spec["market_data"]["path"]
market_sha = hashlib.sha256(market_path.read_bytes()).hexdigest()
assert market_sha == spec["market_data"]["sha256"]
assert spec["formal_engine_integrated"] is False
assert spec["status"] == "test_oracle_only"

with market_path.open(newline="") as market_file:
    bars = list(csv.DictReader(market_file))

actions = {action["timestamp"]: action for action in spec["actions"]}
assert set(actions) <= {bar["timestamp"] for bar in bars}

starting_cash = Decimal(spec["assumptions"]["starting_cash"])
fee_rate = Decimal(spec["assumptions"]["fee_rate_per_side"])
cash = starting_cash
position = Decimal("0")
open_position = None
fills = []
round_trips = []
equity = []

for bar in bars:
    timestamp = bar["timestamp"]
    price = Decimal(bar["close"])
    action = actions.get(timestamp)

    if action:
        action_name = action["action"]
        quantity = Decimal(action["quantity"])
        notional = price * quantity
        fee = notional * fee_rate

        if action_name == "buy":
            assert position == 0
            cash -= notional + fee
            position += quantity
            open_position = {
                "side": "long",
                "timestamp": timestamp,
                "price": price,
                "quantity": quantity,
                "fee": fee,
            }
        elif action_name == "sell":
            assert open_position and open_position["side"] == "long"
            assert position == quantity
            cash += notional - fee
            position -= quantity
            gross_pnl = (price - open_position["price"]) * quantity
            fees = open_position["fee"] + fee
            round_trips.append(
                {
                    "side": "long",
                    "entry_timestamp": open_position["timestamp"],
                    "exit_timestamp": timestamp,
                    "quantity": str(quantity),
                    "gross_pnl": money(gross_pnl),
                    "fees": money(fees),
                    "net_pnl": money(gross_pnl - fees),
                }
            )
            open_position = None
        elif action_name == "short":
            assert position == 0
            cash += notional - fee
            position -= quantity
            open_position = {
                "side": "short",
                "timestamp": timestamp,
                "price": price,
                "quantity": quantity,
                "fee": fee,
            }
        elif action_name == "cover":
            assert open_position and open_position["side"] == "short"
            assert position == -quantity
            cash -= notional + fee
            position += quantity
            gross_pnl = (open_position["price"] - price) * quantity
            fees = open_position["fee"] + fee
            round_trips.append(
                {
                    "side": "short",
                    "entry_timestamp": open_position["timestamp"],
                    "exit_timestamp": timestamp,
                    "quantity": str(quantity),
                    "gross_pnl": money(gross_pnl),
                    "fees": money(fees),
                    "net_pnl": money(gross_pnl - fees),
                }
            )
            open_position = None
        else:
            raise AssertionError(f"Unsupported golden action: {action_name}")

        fills.append(
            {
                "timestamp": timestamp,
                "action": action_name,
                "quantity": str(quantity),
                "price": money(price),
                "notional": money(notional),
                "fee": money(fee),
                "cash_after": money(cash),
                "position_after": str(position),
            }
        )

    equity.append(
        {
            "timestamp": timestamp,
            "equity": money(cash + position * price),
        }
    )

assert position == 0
assert open_position is None

equity_values = [Decimal(point["equity"]) for point in equity]
peak = equity_values[0]
max_drawdown = Decimal("0")
for equity_value in equity_values:
    peak = max(peak, equity_value)
    max_drawdown = max(max_drawdown, (peak - equity_value) / peak)

gross_pnl = sum(Decimal(item["gross_pnl"]) for item in round_trips)
total_fees = sum(Decimal(fill["fee"]) for fill in fills)
net_pnl = cash - starting_cash
computed = {
    "fills": fills,
    "round_trips": round_trips,
    "equity": equity,
    "summary": {
        "ending_cash": money(cash),
        "ending_position": str(position),
        "gross_pnl": money(gross_pnl),
        "total_fees": money(total_fees),
        "net_pnl": money(net_pnl),
        "total_return": str(net_pnl / starting_cash),
        "max_drawdown": str(max_drawdown.quantize(RATIO)),
    },
}

assert computed == spec["expected"]
sys.stdout.write(
    f"Golden backtest specification verified: {spec['spec_id']} "
    f"sha256={market_sha} formal_engine_integrated=false\n"
)
