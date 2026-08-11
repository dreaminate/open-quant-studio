use oqs_quant_engine::run_engine_v1;
use serde_json::{Value, json};

#[test]
fn a_share_market_round_trip_uses_the_formal_fee_ledger() {
    let input = json!({
        "schema_version": 1,
        "account": {
            "model": "a_share_cash",
            "symbol": "600000.XSHG",
            "price_scale": 100,
            "cash_scale": 100,
            "rate_scale": 1_000_000,
            "starting_balance_atoms": "1000000",
            "lot_size": 100,
            "allow_research_short": false,
            "commission_rate_atoms": "600",
            "stamp_duty_rate_atoms": "0",
            "maker_fee_rate_atoms": "0",
            "taker_fee_rate_atoms": "0",
            "slippage_atoms": "0"
        },
        "bars": [
            {
                "session_seq": 1,
                "timestamp": "2026-01-02T07:00:00Z",
                "open_atoms": "1000",
                "high_atoms": "1120",
                "low_atoms": "990",
                "close_atoms": "1100",
                "can_buy": true,
                "can_sell": true
            },
            {
                "session_seq": 2,
                "timestamp": "2026-01-05T07:00:00Z",
                "open_atoms": "1200",
                "high_atoms": "1210",
                "low_atoms": "1180",
                "close_atoms": "1200",
                "can_buy": true,
                "can_sell": true
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
                "known_at": {"session_seq": 0, "phase": "close", "stable_seq": 1},
                "effective_at": {"session_seq": 1, "phase": "open", "stable_seq": 1},
                "limit_price_atoms": null,
                "stop_price_atoms": null,
                "time_in_force": "day",
                "oco_group": null
            },
            {
                "intent_id": "sell-1",
                "intent_seq": 2,
                "symbol": "600000.XSHG",
                "side": "sell",
                "position_effect": "close",
                "quantity": "100",
                "order_type": "market",
                "known_at": {"session_seq": 1, "phase": "close", "stable_seq": 2},
                "effective_at": {"session_seq": 2, "phase": "open", "stable_seq": 2},
                "limit_price_atoms": null,
                "stop_price_atoms": null,
                "time_in_force": "day",
                "oco_group": null
            }
        ]
    });

    let output: Value =
        serde_json::from_slice(&run_engine_v1(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();

    assert_eq!(output["engine_version"], "oqs-quant-engine/0.1.0");
    assert_eq!(output["trades"].as_array().unwrap().len(), 2);
    assert_eq!(output["trades"][0]["fill_price_atoms"], "1000");
    assert_eq!(output["trades"][0]["fee_atoms"], "60");
    assert_eq!(output["trades"][1]["fill_price_atoms"], "1200");
    assert_eq!(output["trades"][1]["fee_atoms"], "72");
    assert_eq!(output["positions"][0]["signed_quantity"], "100");
    assert_eq!(output["positions"][1]["signed_quantity"], "0");
    assert_eq!(output["equity_curve"][0]["equity_atoms"], "1009940");
    assert_eq!(output["equity_curve"][1]["equity_atoms"], "1019868");
    assert_eq!(output["metrics"]["ending_equity_atoms"], "1019868");
    assert_eq!(output["metrics"]["net_pnl_atoms"], "19868");
    assert_eq!(output["metrics"]["total_fees_atoms"], "132");
    assert_eq!(output["metrics"]["total_return_rate_atoms"], "19868");
    assert_eq!(output["metrics"]["fill_count"], 2);
    assert_eq!(output["metrics"]["closed_trade_count"], 1);
    assert_eq!(output["metrics"]["open_position_count"], 0);
}

#[test]
fn a_share_formal_fixture_matches_every_frozen_accounting_surface() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../fixtures/backtests/m3-a-share-long-short-v1.json"
    ))
    .unwrap();
    let output: Value = serde_json::from_slice(
        &run_engine_v1(&serde_json::to_vec(&fixture["input"]).unwrap()).unwrap(),
    )
    .unwrap();
    let expected = &fixture["expected"];

    assert_eq!(
        output["trades"]
            .as_array()
            .unwrap()
            .iter()
            .map(|trade| trade["fill_price_atoms"].clone())
            .collect::<Vec<_>>(),
        expected["fill_prices_atoms"].as_array().unwrap().to_vec()
    );
    assert_eq!(
        output["trades"]
            .as_array()
            .unwrap()
            .iter()
            .map(|trade| trade["fee_atoms"].clone())
            .collect::<Vec<_>>(),
        expected["fees_atoms"].as_array().unwrap().to_vec()
    );
    assert_eq!(
        output["trades"]
            .as_array()
            .unwrap()
            .iter()
            .map(|trade| trade["stamp_duty_atoms"].clone())
            .collect::<Vec<_>>(),
        expected["stamp_duty_atoms"].as_array().unwrap().to_vec()
    );
    assert_eq!(
        output["trades"]
            .as_array()
            .unwrap()
            .iter()
            .map(|trade| trade["slippage_atoms"].clone())
            .collect::<Vec<_>>(),
        expected["slippage_atoms"].as_array().unwrap().to_vec()
    );
    assert_eq!(
        output["positions"]
            .as_array()
            .unwrap()
            .iter()
            .map(|position| position["signed_quantity"].clone())
            .collect::<Vec<_>>(),
        expected["signed_quantities"].as_array().unwrap().to_vec()
    );
    assert_eq!(
        output["equity_curve"]
            .as_array()
            .unwrap()
            .iter()
            .map(|point| point["equity_atoms"].clone())
            .collect::<Vec<_>>(),
        expected["equity_atoms"].as_array().unwrap().to_vec()
    );
    for field in [
        "ending_equity_atoms",
        "net_pnl_atoms",
        "total_fees_atoms",
        "total_stamp_duty_atoms",
        "total_slippage_atoms",
        "fill_count",
        "closed_trade_count",
        "open_position_count",
    ] {
        assert_eq!(output["metrics"][field], expected[field], "{field}");
    }
    assert_eq!(output["assumptions"]["research_short"], true);
}

#[test]
fn a_share_limit_and_stop_gaps_fill_at_the_open_with_adverse_slippage() {
    let input = json!({
        "schema_version": 1,
        "account": a_share_account("10", false),
        "bars": [
            bar(1, "900", "1010", "890", "1000"),
            bar(2, "1200", "1210", "1090", "1150"),
            bar(3, "1000", "1020", "980", "1000"),
            bar(4, "900", "960", "880", "920")
        ],
        "funding_events": [],
        "intents": [
            intent("limit-buy", 1, "buy", "open", "limit", 0, 1, Some("1000"), None),
            intent("limit-sell", 2, "sell", "close", "limit", 1, 2, Some("1100"), None),
            intent("market-buy", 3, "buy", "open", "market", 2, 3, None, None),
            intent("stop-sell", 4, "sell", "close", "stop", 3, 4, None, Some("950"))
        ]
    });

    let output: Value =
        serde_json::from_slice(&run_engine_v1(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();

    assert_eq!(output["trades"][0]["fill_price_atoms"], "910");
    assert_eq!(output["trades"][0]["slippage_atoms"], "1000");
    assert_eq!(output["trades"][0]["liquidity"], "taker");
    assert_eq!(output["trades"][1]["fill_price_atoms"], "1190");
    assert_eq!(output["trades"][1]["liquidity"], "taker");
    assert_eq!(output["trades"][2]["fill_price_atoms"], "1010");
    assert_eq!(output["trades"][3]["fill_price_atoms"], "890");
    assert_eq!(output["metrics"]["total_slippage_atoms"], "4000");
    assert_eq!(output["costs"]["slippage_atoms"], "4000");
}

#[test]
fn a_share_oco_executes_stop_first_when_stop_and_target_touch_the_same_bar() {
    let input = json!({
        "schema_version": 1,
        "account": a_share_account("0", false),
        "bars": [
            bar(1, "1000", "1010", "990", "1000"),
            bar(2, "1000", "1300", "800", "1000")
        ],
        "funding_events": [],
        "intents": [
            intent("entry", 1, "buy", "open", "market", 0, 1, None, None),
            oco_intent("target", 2, "limit", Some("1200"), None, "exit-1"),
            oco_intent("stop", 3, "stop", None, Some("900"), "exit-1")
        ]
    });

    let output: Value =
        serde_json::from_slice(&run_engine_v1(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();

    assert_eq!(output["trades"].as_array().unwrap().len(), 2);
    assert_eq!(output["trades"][1]["intent_id"], "stop");
    assert_eq!(output["trades"][1]["fill_price_atoms"], "900");
    assert_eq!(output["orders"][1]["intent_id"], "target");
    assert_eq!(output["orders"][1]["status"], "cancelled");
    assert_eq!(output["orders"][2]["intent_id"], "stop");
    assert_eq!(output["orders"][2]["status"], "filled");
}

#[test]
fn a_share_research_short_cover_obeys_t_plus_one_and_stays_explicit() {
    let invalid_same_session = json!({
        "schema_version": 1,
        "account": a_share_account("0", true),
        "bars": [bar(1, "1000", "1010", "890", "900")],
        "funding_events": [],
        "intents": [
            intent("short", 1, "sell", "open", "market", 0, 1, None, None),
            intent("cover", 2, "buy", "close", "market", 0, 1, None, None)
        ]
    });
    let error = run_engine_v1(&serde_json::to_vec(&invalid_same_session).unwrap()).unwrap_err();
    assert!(error.to_string().contains("T+1"));

    let valid_next_session = json!({
        "schema_version": 1,
        "account": a_share_account("0", true),
        "bars": [
            bar(1, "1000", "1010", "990", "1000"),
            bar(2, "900", "920", "880", "900")
        ],
        "funding_events": [],
        "intents": [
            intent("short", 1, "sell", "open", "market", 0, 1, None, None),
            intent("cover", 2, "buy", "close", "market", 1, 2, None, None)
        ]
    });
    let output: Value = serde_json::from_slice(
        &run_engine_v1(&serde_json::to_vec(&valid_next_session).unwrap()).unwrap(),
    )
    .unwrap();

    assert_eq!(output["positions"][0]["signed_quantity"], "-100");
    assert_eq!(output["positions"][1]["signed_quantity"], "0");
    assert_eq!(output["metrics"]["ending_equity_atoms"], "1010000");
    assert_eq!(output["metrics"]["net_pnl_atoms"], "10000");
    assert_eq!(output["assumptions"]["research_short"], true);
    assert_eq!(
        output["assumptions"]["research_short_notice"],
        "hypothetical research model; not ordinary cash-account trading capability"
    );
}

#[test]
fn a_share_gtc_waits_for_the_first_directionally_tradable_bar() {
    let mut suspended = bar(1, "900", "1000", "890", "950");
    suspended["can_buy"] = json!(false);
    let mut pending = intent(
        "pending-limit",
        1,
        "buy",
        "open",
        "limit",
        0,
        1,
        Some("1200"),
        None,
    );
    pending["time_in_force"] = json!("gtc");
    let input = json!({
        "schema_version": 1,
        "account": a_share_account("0", false),
        "bars": [
            suspended,
            bar(2, "1100", "1150", "1080", "1120")
        ],
        "funding_events": [],
        "intents": [pending]
    });

    let output: Value =
        serde_json::from_slice(&run_engine_v1(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();

    assert_eq!(output["orders"][0]["status"], "filled");
    assert_eq!(output["orders"][0]["filled_session_seq"], 2);
    assert_eq!(output["trades"][0]["fill_price_atoms"], "1100");
    assert_eq!(output["trades"][0]["liquidity"], "taker");
}

#[test]
fn crypto_linear_perp_reconciles_wallet_realized_pnl_fees_and_funding() {
    let input = json!({
        "schema_version": 1,
        "account": crypto_account(),
        "bars": [
            bar(1, "1000", "1120", "990", "1100"),
            bar(2, "1200", "1210", "1180", "1200"),
            bar(3, "1000", "1100", "980", "1000"),
            bar(4, "900", "920", "880", "900")
        ],
        "funding_events": [
            funding("funding-long", 1, "1000", "1100"),
            funding("funding-short", 3, "1000", "1000")
        ],
        "intents": [
            crypto_intent("long", 1, "buy", "open", "market", 0, 1, None),
            crypto_intent("sell", 2, "sell", "close", "market", 1, 2, None),
            crypto_intent("short", 3, "sell", "open", "limit", 2, 3, Some("1100")),
            crypto_intent("cover", 4, "buy", "close", "market", 3, 4, None)
        ]
    });

    let output: Value =
        serde_json::from_slice(&run_engine_v1(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();

    assert_eq!(output["account_model"], "crypto_linear_perp");
    assert_eq!(output["equity_curve"][0]["equity_atoms"], "1009830");
    assert_eq!(output["trades"][2]["liquidity"], "maker");
    assert_eq!(output["trades"][2]["fee_atoms"], "22");
    assert_eq!(output["funding_ledger"][0]["wallet_delta_atoms"], "-110");
    assert_eq!(output["funding_ledger"][1]["wallet_delta_atoms"], "100");
    assert_eq!(output["metrics"]["ending_equity_atoms"], "1039782");
    assert_eq!(output["metrics"]["net_pnl_atoms"], "39782");
    assert_eq!(output["metrics"]["total_fees_atoms"], "208");
    assert_eq!(output["metrics"]["total_funding_atoms"], "10");
    assert_eq!(output["metrics"]["closed_trade_count"], 2);
    assert_eq!(output["cash_ledger"][0]["notional_delta_atoms"], "0");
    assert_eq!(output["cash_ledger"][0]["resulting_cash_atoms"], "999940");
}

#[test]
fn crypto_oco_executes_stop_first_when_stop_and_target_touch_the_same_bar() {
    let mut target = crypto_intent("target", 2, "sell", "close", "limit", 1, 2, Some("1200"));
    target["oco_group"] = json!("exit-1");
    let mut stop = crypto_intent("stop", 3, "sell", "close", "stop", 1, 2, None);
    stop["stop_price_atoms"] = json!("900");
    stop["oco_group"] = json!("exit-1");
    let input = json!({
        "schema_version": 1,
        "account": crypto_account(),
        "bars": [
            bar(1, "1000", "1010", "990", "1000"),
            bar(2, "1000", "1300", "800", "1000")
        ],
        "funding_events": [],
        "intents": [
            crypto_intent("entry", 1, "buy", "open", "market", 0, 1, None),
            target,
            stop
        ]
    });

    let output: Value =
        serde_json::from_slice(&run_engine_v1(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();

    assert_eq!(output["trades"].as_array().unwrap().len(), 2);
    assert_eq!(output["trades"][1]["intent_id"], "stop");
    assert_eq!(output["trades"][1]["fill_price_atoms"], "900");
    assert_eq!(output["orders"][1]["intent_id"], "target");
    assert_eq!(output["orders"][1]["status"], "cancelled");
    assert_eq!(output["orders"][2]["intent_id"], "stop");
    assert_eq!(output["orders"][2]["status"], "filled");
}

#[test]
fn a_share_account_contract_cannot_relax_the_hundred_share_lot() {
    let mut account = a_share_account("0", false);
    account["lot_size"] = json!(1);
    let mut small_order = intent("small", 1, "buy", "open", "market", 0, 1, None, None);
    small_order["quantity"] = json!("1");
    let input = json!({
        "schema_version": 1,
        "account": account,
        "bars": [bar(1, "1000", "1010", "990", "1000")],
        "funding_events": [],
        "intents": [small_order]
    });

    let error = run_engine_v1(&serde_json::to_vec(&input).unwrap()).unwrap_err();

    assert!(error.to_string().contains("100-share"));
}

#[test]
fn event_key_stable_sequence_controls_same_event_execution_order() {
    let mut later_event = intent(
        "intent-seq-first",
        1,
        "buy",
        "open",
        "market",
        0,
        1,
        None,
        None,
    );
    later_event["effective_at"]["stable_seq"] = json!(2);
    let mut earlier_event = intent(
        "eventkey-first",
        2,
        "buy",
        "open",
        "market",
        0,
        1,
        None,
        None,
    );
    earlier_event["effective_at"]["stable_seq"] = json!(1);
    let input = json!({
        "schema_version": 1,
        "account": a_share_account("0", false),
        "bars": [bar(1, "1000", "1010", "990", "1000")],
        "funding_events": [],
        "intents": [later_event, earlier_event]
    });

    let output: Value =
        serde_json::from_slice(&run_engine_v1(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();

    assert_eq!(output["trades"][0]["intent_id"], "eventkey-first");
    assert_eq!(output["trades"][1]["intent_id"], "intent-seq-first");
}

#[test]
fn malformed_market_and_cost_inputs_fail_closed() {
    let negative_slippage = json!({
        "schema_version": 1,
        "account": a_share_account("-10", false),
        "bars": [bar(1, "1000", "1010", "990", "1000")],
        "funding_events": [],
        "intents": [intent("buy", 1, "buy", "open", "market", 0, 1, None, None)]
    });
    let error = run_engine_v1(&serde_json::to_vec(&negative_slippage).unwrap()).unwrap_err();
    assert!(error.to_string().contains("non-negative"));

    let zero_price = json!({
        "schema_version": 1,
        "account": a_share_account("0", false),
        "bars": [bar(1, "0", "10", "0", "5")],
        "funding_events": [],
        "intents": [intent("buy", 1, "buy", "open", "market", 0, 1, None, None)]
    });
    let error = run_engine_v1(&serde_json::to_vec(&zero_price).unwrap()).unwrap_err();
    assert!(error.to_string().contains("positive"));

    let mut negative_crypto_fee = crypto_account();
    negative_crypto_fee["maker_fee_rate_atoms"] = json!("-1");
    let invalid_crypto_cost = json!({
        "schema_version": 1,
        "account": negative_crypto_fee,
        "bars": [bar(1, "1000", "1010", "990", "1000")],
        "funding_events": [],
        "intents": []
    });
    let error = run_engine_v1(&serde_json::to_vec(&invalid_crypto_cost).unwrap()).unwrap_err();
    assert!(error.to_string().contains("non-negative"));

    let mut incoherent_bar = bar(1, "1000", "900", "990", "1000");
    incoherent_bar["can_buy"] = json!(false);
    incoherent_bar["can_sell"] = json!(false);
    let invalid_crypto_bar = json!({
        "schema_version": 1,
        "account": crypto_account(),
        "bars": [incoherent_bar],
        "funding_events": [],
        "intents": []
    });
    let error = run_engine_v1(&serde_json::to_vec(&invalid_crypto_bar).unwrap()).unwrap_err();
    assert!(error.to_string().contains("coherent"));

    let invalid_crypto_stop = json!({
        "schema_version": 1,
        "account": crypto_account(),
        "bars": [bar(1, "1000", "1010", "990", "1000")],
        "funding_events": [],
        "intents": [
            {
                "intent_id": "invalid-stop",
                "intent_seq": 1,
                "symbol": "BTC-PERP",
                "side": "buy",
                "position_effect": "open",
                "quantity": "100",
                "order_type": "stop",
                "known_at": {"session_seq": 0, "phase": "close", "stable_seq": 1},
                "effective_at": {"session_seq": 1, "phase": "open", "stable_seq": 1},
                "limit_price_atoms": null,
                "stop_price_atoms": "0",
                "time_in_force": "day",
                "oco_group": null
            }
        ]
    });
    let error = run_engine_v1(&serde_json::to_vec(&invalid_crypto_stop).unwrap()).unwrap_err();
    assert!(error.to_string().contains("positive"));

    let mut unknown_event_field = json!({
        "schema_version": 1,
        "account": a_share_account("0", false),
        "bars": [bar(1, "1000", "1010", "990", "1000")],
        "funding_events": [],
        "intents": [intent("buy", 1, "buy", "open", "market", 0, 1, None, None)]
    });
    unknown_event_field["intents"][0]["effective_at"]["unexpected"] = json!(true);
    let error = run_engine_v1(&serde_json::to_vec(&unknown_event_field).unwrap()).unwrap_err();
    assert!(error.to_string().contains("unknown field"));

    let mut unknown_intent_field = unknown_event_field;
    unknown_intent_field["intents"][0]["effective_at"] =
        json!({"session_seq": 1, "phase": "open", "stable_seq": 1});
    unknown_intent_field["intents"][0]["unexpected"] = json!(true);
    let error = run_engine_v1(&serde_json::to_vec(&unknown_intent_field).unwrap()).unwrap_err();
    assert!(error.to_string().contains("unknown field"));

    let mut unknown_input_field = unknown_intent_field;
    unknown_input_field["intents"][0]
        .as_object_mut()
        .unwrap()
        .remove("unexpected");
    unknown_input_field["unexpected"] = json!(true);
    let error = run_engine_v1(&serde_json::to_vec(&unknown_input_field).unwrap()).unwrap_err();
    assert!(error.to_string().contains("unknown field"));
}

fn a_share_account(slippage_atoms: &str, allow_research_short: bool) -> Value {
    json!({
        "model": "a_share_cash",
        "symbol": "600000.XSHG",
        "price_scale": 100,
        "cash_scale": 100,
        "rate_scale": 1_000_000,
        "starting_balance_atoms": "1000000",
        "lot_size": 100,
        "allow_research_short": allow_research_short,
        "commission_rate_atoms": "0",
        "stamp_duty_rate_atoms": "0",
        "maker_fee_rate_atoms": "0",
        "taker_fee_rate_atoms": "0",
        "slippage_atoms": slippage_atoms
    })
}

fn crypto_account() -> Value {
    json!({
        "model": "crypto_linear_perp",
        "symbol": "BTC-PERP",
        "price_scale": 100,
        "cash_scale": 100,
        "rate_scale": 1_000_000,
        "starting_balance_atoms": "1000000",
        "lot_size": 1,
        "allow_research_short": false,
        "commission_rate_atoms": "0",
        "stamp_duty_rate_atoms": "0",
        "maker_fee_rate_atoms": "200",
        "taker_fee_rate_atoms": "600",
        "slippage_atoms": "0"
    })
}

fn funding(event_id: &str, session_seq: u64, rate_atoms: &str, mark: &str) -> Value {
    json!({
        "event_id": event_id,
        "session_seq": session_seq,
        "phase": "close",
        "stable_seq": session_seq,
        "rate_atoms": rate_atoms,
        "mark_price_atoms": mark
    })
}

#[allow(clippy::too_many_arguments)]
fn crypto_intent(
    intent_id: &str,
    intent_seq: u64,
    side: &str,
    position_effect: &str,
    order_type: &str,
    known_session: u64,
    effective_session: u64,
    limit_price_atoms: Option<&str>,
) -> Value {
    json!({
        "intent_id": intent_id,
        "intent_seq": intent_seq,
        "symbol": "BTC-PERP",
        "side": side,
        "position_effect": position_effect,
        "quantity": "100",
        "order_type": order_type,
        "known_at": {"session_seq": known_session, "phase": "close", "stable_seq": intent_seq},
        "effective_at": {"session_seq": effective_session, "phase": "open", "stable_seq": intent_seq},
        "limit_price_atoms": limit_price_atoms,
        "stop_price_atoms": null,
        "time_in_force": "day",
        "oco_group": null
    })
}

fn bar(session_seq: u64, open: &str, high: &str, low: &str, close: &str) -> Value {
    json!({
        "session_seq": session_seq,
        "timestamp": format!("2026-01-{session_seq:02}T07:00:00Z"),
        "open_atoms": open,
        "high_atoms": high,
        "low_atoms": low,
        "close_atoms": close,
        "can_buy": true,
        "can_sell": true
    })
}

#[allow(clippy::too_many_arguments)]
fn intent(
    intent_id: &str,
    intent_seq: u64,
    side: &str,
    position_effect: &str,
    order_type: &str,
    known_session: u64,
    effective_session: u64,
    limit_price_atoms: Option<&str>,
    stop_price_atoms: Option<&str>,
) -> Value {
    json!({
        "intent_id": intent_id,
        "intent_seq": intent_seq,
        "symbol": "600000.XSHG",
        "side": side,
        "position_effect": position_effect,
        "quantity": "100",
        "order_type": order_type,
        "known_at": {"session_seq": known_session, "phase": "close", "stable_seq": intent_seq},
        "effective_at": {"session_seq": effective_session, "phase": "open", "stable_seq": intent_seq},
        "limit_price_atoms": limit_price_atoms,
        "stop_price_atoms": stop_price_atoms,
        "time_in_force": "day",
        "oco_group": null
    })
}

fn oco_intent(
    intent_id: &str,
    intent_seq: u64,
    order_type: &str,
    limit_price_atoms: Option<&str>,
    stop_price_atoms: Option<&str>,
    oco_group: &str,
) -> Value {
    let mut value = intent(
        intent_id,
        intent_seq,
        "sell",
        "close",
        order_type,
        1,
        2,
        limit_price_atoms,
        stop_price_atoms,
    );
    value["oco_group"] = json!(oco_group);
    value
}
