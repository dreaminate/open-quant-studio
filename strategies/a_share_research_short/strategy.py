"""Labelled research-only A-share completed-close breakdown short strategy."""

STRATEGY_ID = "a_share_research_short"
BREAKDOWN_WINDOW = 3
COVER_WINDOW = 3
STOP_LOSS_BPS = 600
LOT_SIZE = 100

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
        "quantity": str(LOT_SIZE),
        "order_type": "market",
        "limit_price_atoms": None,
        "stop_price_atoms": None,
        "time_in_force": "day",
        "oco_group": None,
    }


def on_bar(bar):
    close = int(bar["close_atoms"])
    closes = STATE["closes"]
    prior_closes = closes[-BREAKDOWN_WINDOW:]
    closes.append(close)

    if STATE["position"] == 0:
        if len(prior_closes) == BREAKDOWN_WINDOW and close < min(prior_closes):
            STATE["position"] = -1
            STATE["entry_close"] = close
            return [order(bar["symbol"], "sell", "open")]
        return []

    cover_average = sum(closes[-COVER_WINDOW:]) // min(len(closes), COVER_WINDOW)
    stop_hit = close * 10_000 >= STATE["entry_close"] * (10_000 + STOP_LOSS_BPS)
    trend_reversed = close > cover_average
    if stop_hit or trend_reversed:
        STATE["position"] = 0
        STATE["entry_close"] = None
        return [order(bar["symbol"], "buy", "close")]
    return []
