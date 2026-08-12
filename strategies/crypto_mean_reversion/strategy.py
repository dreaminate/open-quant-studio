"""Crypto linear-perpetual completed-close mean-reversion long strategy."""

STRATEGY_ID = "crypto_mean_reversion"
MEAN_WINDOW = 3
ENTRY_DISCOUNT_BPS = 500
RECOVERY_BPS = 500
STOP_LOSS_BPS = 700
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
    prior_closes = closes[-MEAN_WINDOW:]
    closes.append(close)

    if STATE["position"] == 0:
        if len(prior_closes) == MEAN_WINDOW:
            reference_mean = sum(prior_closes) // MEAN_WINDOW
            discounted = close * 10_000 <= reference_mean * (10_000 - ENTRY_DISCOUNT_BPS)
            if discounted:
                STATE["position"] = 1
                STATE["entry_close"] = close
                return [order(bar["symbol"], "buy", "open")]
        return []

    recovered = close * 10_000 >= STATE["entry_close"] * (10_000 + RECOVERY_BPS)
    stop_hit = close * 10_000 <= STATE["entry_close"] * (10_000 - STOP_LOSS_BPS)
    if recovered or stop_hit:
        STATE["position"] = 0
        STATE["entry_close"] = None
        return [order(bar["symbol"], "sell", "close")]
    return []
