"""Crypto linear-perpetual completed-close fast/slow trend crossover."""

STRATEGY_ID = "crypto_trend"
FAST_WINDOW = 3
SLOW_WINDOW = 4
STOP_LOSS_BPS = 500
CONTRACTS = 1

STATE = {}


def on_start():
    global STATE
    STATE = {
        "closes": [],
        "position": 0,
        "entry_close": None,
        "intent_seq": 0,
    }
    return []


def order(symbol, side, position_effect):
    STATE["intent_seq"] += 1
    return {
        "intent_id": f"{STRATEGY_ID}:{STATE['intent_seq']}",
        "intent_seq": STATE["intent_seq"],
        "symbol": symbol,
        "side": side,
        "position_effect": position_effect,
        "quantity": str(CONTRACTS),
        "order_type": "market",
        "limit_price_atoms": None,
        "stop_price_atoms": None,
        "time_in_force": "day",
        "oco_group": None,
    }


def on_bar(bar):
    close = int(bar["close_atoms"])
    closes = STATE["closes"]
    closes.append(close)
    if len(closes) < SLOW_WINDOW:
        return []

    fast_average = sum(closes[-FAST_WINDOW:]) // FAST_WINDOW
    slow_average = sum(closes[-SLOW_WINDOW:]) // SLOW_WINDOW
    if STATE["position"] == 0 and fast_average > slow_average:
        STATE["position"] = 1
        STATE["entry_close"] = close
        return [order(bar["symbol"], "buy", "open")]

    if STATE["position"] == 1:
        stop_hit = close * 10_000 <= STATE["entry_close"] * (10_000 - STOP_LOSS_BPS)
        trend_reversed = fast_average < slow_average
        if stop_hit or trend_reversed:
            STATE["position"] = 0
            STATE["entry_close"] = None
            return [order(bar["symbol"], "sell", "close")]
    return []
