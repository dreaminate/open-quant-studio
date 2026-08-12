"""A-share completed-close trend breakout with a trailing trend exit."""

STRATEGY_ID = "a_share_trend_breakout"
BREAKOUT_WINDOW = 3
TREND_WINDOW = 3
STOP_LOSS_BPS = 600
LOT_SIZE = 100

STATE = {}


def on_start():
    global STATE
    STATE = {
        "closes": [],
        "symbol": None,
        "position": 0,
        "peak_close": None,
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
    prior_closes = closes[-BREAKOUT_WINDOW:]
    closes.append(close)
    STATE["symbol"] = bar["symbol"]

    if STATE["position"] == 0:
        if len(prior_closes) == BREAKOUT_WINDOW and close > max(prior_closes):
            STATE["position"] = 1
            STATE["peak_close"] = close
            return [order(bar["symbol"], "buy", "open")]
        return []

    STATE["peak_close"] = max(STATE["peak_close"], close)
    trend_average = sum(closes[-TREND_WINDOW:]) // min(len(closes), TREND_WINDOW)
    stop_hit = close * 10_000 <= STATE["peak_close"] * (10_000 - STOP_LOSS_BPS)
    trend_reversed = close < trend_average
    if stop_hit or trend_reversed:
        STATE["position"] = 0
        STATE["peak_close"] = None
        return [order(bar["symbol"], "sell", "close")]
    return []
