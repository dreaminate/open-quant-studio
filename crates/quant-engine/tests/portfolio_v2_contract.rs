use oqs_quant_engine::{
    finalize_engine_checkpoint_v2, run_engine_v2, start_engine_checkpoint_v2,
    step_engine_checkpoint_v2,
};
use serde_json::{Value, json};

fn fixture() -> Value {
    serde_json::from_str(include_str!(
        "../../../fixtures/backtests/m8-a-share-rotation-v2.json"
    ))
    .unwrap()
}

fn fixture_input() -> Vec<u8> {
    serde_json::to_vec(&fixture()["input"]).unwrap()
}

fn finish_checkpoint(input: &[u8], batch_session_count: usize) -> Vec<u8> {
    let context = "a".repeat(64);
    let mut checkpoint = start_engine_checkpoint_v2(input, &context, batch_session_count).unwrap();
    while serde_json::from_slice::<Value>(&checkpoint).unwrap()["status"] != "complete" {
        checkpoint = step_engine_checkpoint_v2(input, &context, &checkpoint).unwrap();
    }
    assert_eq!(
        step_engine_checkpoint_v2(input, &context, &checkpoint).unwrap(),
        checkpoint
    );
    finalize_engine_checkpoint_v2(input, &context, &checkpoint).unwrap()
}

#[test]
fn rotation_fixture_uses_shared_cash_close_before_open_and_one_portfolio_equity_point() {
    let fixture = fixture();
    let output: Value = serde_json::from_slice(&run_engine_v2(&fixture_input()).unwrap()).unwrap();
    let expected = &fixture["expected"];

    assert_eq!(output["schema_version"], 2);
    assert_eq!(output["engine_version"], "oqs-quant-engine/0.2.0");
    assert_eq!(output["account_model"], "a_share_portfolio_cash");
    assert_eq!(
        output["trades"]
            .as_array()
            .unwrap()
            .iter()
            .map(|trade| trade["intent_id"].clone())
            .collect::<Vec<_>>(),
        expected["trade_intent_ids"].as_array().unwrap().to_vec()
    );
    assert_eq!(
        output["trades"]
            .as_array()
            .unwrap()
            .iter()
            .map(|trade| trade["symbol"].clone())
            .collect::<Vec<_>>(),
        vec![
            json!("AAA.XSHG"),
            json!("AAA.XSHG"),
            json!("BBB.XSHG"),
            json!("BBB.XSHG"),
            json!("AAA.XSHG"),
            json!("CCC.XSHG"),
            json!("AAA.XSHG"),
            json!("CCC.XSHG"),
        ]
    );
    assert_eq!(
        output["equity_curve"]
            .as_array()
            .unwrap()
            .iter()
            .map(|point| point["cash_atoms"].clone())
            .collect::<Vec<_>>(),
        expected["cash_atoms"].as_array().unwrap().to_vec()
    );
    assert_eq!(
        output["equity_curve"]
            .as_array()
            .unwrap()
            .iter()
            .map(|point| point["market_value_atoms"].clone())
            .collect::<Vec<_>>(),
        expected["market_value_atoms"].as_array().unwrap().to_vec()
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
    assert_eq!(output["equity_curve"].as_array().unwrap().len(), 4);
    assert_eq!(
        output["metrics"]["ending_equity_atoms"],
        expected["ending_equity_atoms"]
    );
    assert_eq!(
        output["metrics"]["net_pnl_atoms"],
        expected["net_pnl_atoms"]
    );
    assert_eq!(
        output["metrics"]["closed_trade_count"],
        expected["closed_trade_count"]
    );
    assert_eq!(
        output["metrics"]["open_position_count"],
        expected["open_position_count"]
    );
}

#[test]
fn portfolio_open_rejects_shared_cash_overcommit() {
    let mut input = fixture()["input"].clone();
    input["intents"] = json!([input["intents"][0].clone(), input["intents"][1].clone()]);

    let error = run_engine_v2(&serde_json::to_vec(&input).unwrap()).unwrap_err();

    assert_eq!(
        error.to_string(),
        "portfolio buy/open exceeds shared cash capacity"
    );
}

#[test]
fn portfolio_t_plus_one_is_tracked_per_symbol() {
    let mut input = fixture()["input"].clone();
    input["intents"] = json!([
        input["intents"][0].clone(),
        {
            "intent_id": "close-bbb-with-only-aaa-position",
            "intent_seq": 2,
            "symbol": "BBB.XSHG",
            "side": "sell",
            "position_effect": "close",
            "quantity": "100",
            "order_type": "market",
            "known_at": {"session_seq": 0, "phase": "close", "stable_seq": 2},
            "effective_at": {"session_seq": 1, "phase": "open", "stable_seq": 2},
            "limit_price_atoms": null,
            "stop_price_atoms": null,
            "time_in_force": "day",
            "oco_group": null
        }
    ]);

    let error = run_engine_v2(&serde_json::to_vec(&input).unwrap()).unwrap_err();

    assert_eq!(error.to_string(), "T+1 eligible quantity is insufficient");
}

#[test]
fn checkpoint_batches_restart_to_the_same_direct_v2_output() {
    let input = fixture_input();
    let direct = run_engine_v2(&input).unwrap();

    assert_eq!(finish_checkpoint(&input, 1), direct);
    assert_eq!(finish_checkpoint(&input, 2), direct);
}
