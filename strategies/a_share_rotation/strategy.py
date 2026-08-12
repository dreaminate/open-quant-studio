"""Three-symbol A-share rotation on completed-session close-to-close momentum.

The portfolio callback contract streams one bar for each member of UNIVERSE per
session and sets ``session_end`` only on that session's final bar. The strategy
waits for that marker, ranks momentum, and emits close-before-open intents for
the next session so the engine can apply shared-cash semantics.
"""

STRATEGY_ID = "a_share_rotation"
UNIVERSE = ("AAA.XSHG", "BBB.XSHG", "CCC.XSHG")
MOMENTUM_PERIODS = 1
MIN_MOMENTUM_BPS = 10_100
LOT_SIZE = 100

STATE = {}


def on_start():
    global STATE
    STATE = {
        "active_session": None,
        "session_closes": {},
        "history": {symbol: [] for symbol in UNIVERSE},
        "held_symbol": None,
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


def leader_after_completed_session():
    return min(
        UNIVERSE,
        key=lambda symbol: (
            -(
                STATE["history"][symbol][-1]
                * 10_000
                // STATE["history"][symbol][-1 - MOMENTUM_PERIODS]
            ),
            symbol,
        ),
    )


def momentum_bps(symbol):
    return (
        STATE["history"][symbol][-1]
        * 10_000
        // STATE["history"][symbol][-1 - MOMENTUM_PERIODS]
    )


def on_bar(bar):
    if STATE["active_session"] != bar["session_seq"]:
        STATE["active_session"] = bar["session_seq"]
        STATE["session_closes"] = {}

    STATE["session_closes"][bar["symbol"]] = int(bar["close_atoms"])
    if not bar["session_end"]:
        return []

    for symbol in UNIVERSE:
        STATE["history"][symbol].append(STATE["session_closes"][symbol])
    if len(STATE["history"][UNIVERSE[0]]) <= MOMENTUM_PERIODS:
        return []

    leader = leader_after_completed_session()
    target_symbol = (
        leader if momentum_bps(leader) >= MIN_MOMENTUM_BPS else None
    )
    held_symbol = STATE["held_symbol"]
    if held_symbol == target_symbol:
        return []

    intents = []
    if held_symbol is not None:
        intents.append(order(held_symbol, "sell", "close"))
    if target_symbol is not None:
        intents.append(order(target_symbol, "buy", "open"))
    STATE["held_symbol"] = target_symbol
    return intents
