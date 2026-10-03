use oqs_quant_engine::{
    finalize_engine_checkpoint_v3, run_engine_v3, start_engine_checkpoint_v3,
    step_engine_checkpoint_v3,
};
use serde_json::Value;

fn fixture() -> Value {
    serde_json::from_str(include_str!(
        "../../../fixtures/backtests/a-share-research-v3-long-t1.json"
    ))
    .unwrap()
}

fn assert_equity_identity(output: &Value) {
    for point in output["equity_curve"].as_array().unwrap() {
        let atom = |field: &str| point[field].as_str().unwrap().parse::<i128>().unwrap();
        assert_eq!(
            atom("gross_market_value_atoms"),
            atom("long_market_value_atoms") + atom("short_liability_atoms")
        );
        assert_eq!(
            atom("net_market_value_atoms"),
            atom("long_market_value_atoms") - atom("short_liability_atoms")
        );
        assert_eq!(atom("market_value_atoms"), atom("net_market_value_atoms"));
        assert_eq!(
            atom("equity_atoms"),
            atom("available_cash_atoms")
                + atom("net_market_value_atoms")
                + atom("frozen_margin_atoms")
                + atom("isolated_short_proceeds_atoms")
        );
    }
}

fn dual_open_input() -> Value {
    let mut input = fixture()["input"].clone();
    let long_open = input["intents"][0].clone();
    let mut short_open = long_open.clone();
    short_open["intent_id"] = serde_json::json!("short-open");
    short_open["intent_seq"] = serde_json::json!(2);
    short_open["book"] = serde_json::json!("research_short");
    short_open["side"] = serde_json::json!("sell");
    short_open["position_effect"] = serde_json::json!("open");
    short_open["known_at"]["stable_seq"] = serde_json::json!(2);
    short_open["effective_at"]["stable_seq"] = serde_json::json!(2);
    input["intents"] = serde_json::json!([long_open, short_open]);
    input
}

#[test]
fn long_t_plus_one_rejects_same_day_close_and_fills_next_session() {
    let fixture = fixture();
    let output: Value = serde_json::from_slice(
        &run_engine_v3(&serde_json::to_vec(&fixture["input"]).unwrap()).unwrap(),
    )
    .unwrap();
    let expected = &fixture["expected"];
    let status = |intent_id: &str| {
        output["orders"]
            .as_array()
            .unwrap()
            .iter()
            .find(|order| order["intent_id"] == intent_id)
            .unwrap()
    };

    assert_eq!(output["schema_version"], 3);
    assert_eq!(output["engine_version"], "oqs-quant-engine/0.3.0");
    assert_eq!(output["account_model"], "a_share_portfolio_research");
    assert_eq!(
        status("long-open")["status"],
        expected["order_statuses"]["long-open"]
    );
    assert_eq!(
        status("long-close-same-day")["status"],
        expected["order_statuses"]["long-close-same-day"]
    );
    assert_eq!(
        status("long-close-same-day")["reject_reason"],
        expected["same_day_reject_reason"]
    );
    assert_eq!(
        status("long-close-next-day")["status"],
        expected["order_statuses"]["long-close-next-day"]
    );
    assert_eq!(
        output["fills"]
            .as_array()
            .unwrap()
            .iter()
            .map(|fill| fill["intent_id"].clone())
            .collect::<Vec<_>>(),
        expected["fill_intent_ids"].as_array().unwrap().to_vec()
    );
    assert_eq!(
        output["equity_curve"].as_array().unwrap().last().unwrap()["available_cash_atoms"],
        expected["ending_available_cash_atoms"]
    );
    assert_eq!(
        output["metrics"]["ending_equity_atoms"],
        expected["ending_equity_atoms"]
    );
    assert_eq!(
        output["metrics"]["closed_trade_count"],
        expected["closed_trade_count"]
    );
    assert_eq!(
        output["metrics"]["open_position_count"],
        expected["open_position_count"]
    );
    assert_equity_identity(&output);
}

#[test]
fn checkpoint_v3_uses_the_same_transition_kernel_and_is_byte_identical() {
    let fixture = fixture();
    let input = serde_json::to_vec(&fixture["input"]).unwrap();
    let direct = run_engine_v3(&input).unwrap();
    let context = "a".repeat(64);
    let mut checkpoint = start_engine_checkpoint_v3(&input, &context, 1).unwrap();
    while serde_json::from_slice::<Value>(&checkpoint).unwrap()["status"] != "complete" {
        checkpoint = step_engine_checkpoint_v3(&input, &context, &checkpoint).unwrap();
    }
    assert_eq!(
        finalize_engine_checkpoint_v3(&input, &context, &checkpoint).unwrap(),
        direct
    );
    assert_eq!(
        step_engine_checkpoint_v3(&input, &context, &checkpoint).unwrap(),
        checkpoint
    );
}

#[test]
fn checkpoint_v3_binds_canonical_input_not_json_whitespace() {
    let fixture = fixture();
    let compact = serde_json::to_vec(&fixture["input"]).unwrap();
    let pretty = serde_json::to_vec_pretty(&fixture["input"]).unwrap();
    let context = "b".repeat(64);
    let mut checkpoint = start_engine_checkpoint_v3(&pretty, &context, 1).unwrap();
    while serde_json::from_slice::<Value>(&checkpoint).unwrap()["status"] != "complete" {
        checkpoint = step_engine_checkpoint_v3(&compact, &context, &checkpoint).unwrap();
    }
    let direct = run_engine_v3(&compact).unwrap();
    assert_eq!(
        finalize_engine_checkpoint_v3(&pretty, &context, &checkpoint).unwrap(),
        direct
    );
}

#[test]
fn v3_rejects_unknown_input_fields_before_state_transition() {
    let mut input = fixture()["input"].clone();
    input["unexpected"] = serde_json::json!(true);
    let error = run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap_err();
    assert!(error.to_string().contains("unknown field"));
}

#[test]
fn condition_intent_lineage_is_echoed_without_affecting_execution() {
    let mut input = fixture()["input"].clone();
    input["intents"][0]["condition_intent_id"] = serde_json::json!("condition:breakout-above-10");
    input["intents"] = serde_json::json!([input["intents"][0].clone()]);
    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    assert_eq!(output["orders"][0]["status"], "filled");
    assert_eq!(
        output["orders"][0]["condition_intent_id"],
        "condition:breakout-above-10"
    );
    assert_eq!(
        output["fills"][0]["condition_intent_id"],
        "condition:breakout-above-10"
    );

    let default_output: Value = serde_json::from_slice(
        &run_engine_v3(&serde_json::to_vec(&fixture()["input"]).unwrap()).unwrap(),
    )
    .unwrap();
    assert_eq!(
        default_output["orders"][0]["condition_intent_id"],
        Value::Null
    );
    assert_eq!(
        default_output["fills"][0]["condition_intent_id"],
        Value::Null
    );
}

#[test]
fn research_short_isolated_margin_and_t_plus_one_cover() {
    let mut input = fixture()["input"].clone();
    input["intents"][0]["intent_id"] = serde_json::json!("short-open");
    input["intents"][0]["book"] = serde_json::json!("research_short");
    input["intents"][0]["side"] = serde_json::json!("sell");
    input["intents"][0]["position_effect"] = serde_json::json!("open");
    input["intents"][1]["intent_id"] = serde_json::json!("short-cover-same-day");
    input["intents"][1]["book"] = serde_json::json!("research_short");
    input["intents"][1]["side"] = serde_json::json!("buy");
    input["intents"][1]["position_effect"] = serde_json::json!("close");
    input["intents"][2]["intent_id"] = serde_json::json!("short-cover-next-day");
    input["intents"][2]["book"] = serde_json::json!("research_short");
    input["intents"][2]["side"] = serde_json::json!("buy");
    input["intents"][2]["position_effect"] = serde_json::json!("close");
    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let order = output["orders"]
        .as_array()
        .unwrap()
        .iter()
        .find(|order| order["intent_id"] == "short-open")
        .unwrap();
    assert_eq!(order["status"], "filled");
    let same_day = output["orders"]
        .as_array()
        .unwrap()
        .iter()
        .find(|order| order["intent_id"] == "short-cover-same-day")
        .unwrap();
    assert_eq!(same_day["status"], "rejected");
    assert_eq!(same_day["reject_reason"], "t_plus_one");
    let next_day = output["orders"]
        .as_array()
        .unwrap()
        .iter()
        .find(|order| order["intent_id"] == "short-cover-next-day")
        .unwrap();
    assert_eq!(next_day["status"], "filled");
    assert_eq!(output["fills"].as_array().unwrap().len(), 2);
    assert_eq!(output["equity_curve"][0]["available_cash_atoms"], "900000");
    assert_eq!(output["equity_curve"][0]["frozen_margin_atoms"], "100000");
    assert_eq!(
        output["equity_curve"][0]["isolated_short_proceeds_atoms"],
        "100000"
    );
    assert_eq!(output["equity_curve"][1]["available_cash_atoms"], "1000000");
    assert_eq!(output["equity_curve"][1]["frozen_margin_atoms"], "0");
    assert_eq!(
        output["equity_curve"][1]["isolated_short_proceeds_atoms"],
        "0"
    );
    assert_eq!(output["metrics"]["closed_trade_count"], 1);
    assert_eq!(output["metrics"]["open_position_count"], 0);
    assert_equity_identity(&output);
}

#[test]
fn cash_long_and_research_short_books_coexist_without_netting() {
    let mut input = fixture()["input"].clone();
    let long_open = input["intents"][0].clone();
    let mut short_open = long_open.clone();
    short_open["intent_id"] = serde_json::json!("short-open");
    short_open["intent_seq"] = serde_json::json!(2);
    short_open["book"] = serde_json::json!("research_short");
    short_open["side"] = serde_json::json!("sell");
    short_open["position_effect"] = serde_json::json!("open");
    short_open["known_at"]["stable_seq"] = serde_json::json!(2);
    short_open["effective_at"]["stable_seq"] = serde_json::json!(2);
    let mut long_close = long_open.clone();
    long_close["intent_id"] = serde_json::json!("long-close");
    long_close["intent_seq"] = serde_json::json!(3);
    long_close["side"] = serde_json::json!("sell");
    long_close["position_effect"] = serde_json::json!("close");
    long_close["known_at"]["session_seq"] = serde_json::json!(1);
    long_close["known_at"]["stable_seq"] = serde_json::json!(3);
    long_close["effective_at"]["session_seq"] = serde_json::json!(2);
    long_close["effective_at"]["stable_seq"] = serde_json::json!(3);
    let mut short_cover = long_close.clone();
    short_cover["intent_id"] = serde_json::json!("short-cover");
    short_cover["intent_seq"] = serde_json::json!(4);
    short_cover["book"] = serde_json::json!("research_short");
    short_cover["side"] = serde_json::json!("buy");
    short_cover["position_effect"] = serde_json::json!("close");
    short_cover["known_at"]["stable_seq"] = serde_json::json!(4);
    short_cover["effective_at"]["stable_seq"] = serde_json::json!(4);
    input["intents"] = serde_json::json!([long_open, short_open, long_close, short_cover]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    assert_eq!(output["fills"].as_array().unwrap().len(), 4);
    assert_eq!(
        output["fills"]
            .as_array()
            .unwrap()
            .iter()
            .map(|fill| fill["book"].clone())
            .collect::<Vec<_>>(),
        vec![
            serde_json::json!("cash_long"),
            serde_json::json!("research_short"),
            serde_json::json!("cash_long"),
            serde_json::json!("research_short")
        ]
    );
    assert_eq!(output["equity_curve"][0]["available_cash_atoms"], "800000");
    assert_eq!(output["equity_curve"][0]["frozen_margin_atoms"], "100000");
    assert_eq!(output["equity_curve"][1]["available_cash_atoms"], "1000000");
    assert_eq!(output["equity_curve"][1]["frozen_margin_atoms"], "0");
    assert_eq!(output["metrics"]["closed_trade_count"], 2);
    assert_eq!(output["metrics"]["open_position_count"], 0);
    assert_equity_identity(&output);
}

#[test]
fn shared_participation_capacity_fills_partial_then_carries_gtc() {
    let mut input = fixture()["input"].clone();
    input["account"]["starting_cash_atoms"] = serde_json::json!("3000000");
    input["account"]["max_participation_rate_atoms"] = serde_json::json!("100000");
    let mut first = input["intents"][0].clone();
    first["intent_id"] = serde_json::json!("partial-first");
    first["intent_seq"] = serde_json::json!(1);
    first["quantity"] = serde_json::json!("700");
    let mut second = first.clone();
    second["intent_id"] = serde_json::json!("partial-gtc");
    second["intent_seq"] = serde_json::json!(2);
    second["quantity"] = serde_json::json!("700");
    second["time_in_force"] = serde_json::json!("gtc");
    second["known_at"]["stable_seq"] = serde_json::json!(2);
    second["effective_at"]["stable_seq"] = serde_json::json!(2);
    input["intents"] = serde_json::json!([first, second]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let fills = output["fills"].as_array().unwrap();
    assert_eq!(fills.len(), 3);
    assert_eq!(fills[0]["intent_id"], "partial-first");
    assert_eq!(fills[0]["quantity"], "700");
    assert_eq!(fills[1]["intent_id"], "partial-gtc");
    assert_eq!(fills[1]["quantity"], "300");
    assert_eq!(fills[1]["volume_before"], "9300");
    assert_eq!(fills[1]["remaining_quantity"], "400");
    assert_eq!(fills[2]["intent_id"], "partial-gtc");
    assert_eq!(fills[2]["quantity"], "400");
    assert_eq!(fills[2]["remaining_quantity"], "0");
    let order = output["orders"]
        .as_array()
        .unwrap()
        .iter()
        .find(|order| order["intent_id"] == "partial-gtc")
        .unwrap();
    assert_eq!(order["status"], "filled");
    assert_eq!(order["remaining_quantity"], "0");
    assert_eq!(output["assumptions"]["partial_fills"], true);
}

#[test]
fn day_partial_expires_with_remaining_quantity() {
    let mut input = fixture()["input"].clone();
    input["account"]["starting_cash_atoms"] = serde_json::json!("3000000");
    let mut first = input["intents"][0].clone();
    first["intent_id"] = serde_json::json!("day-first");
    first["intent_seq"] = serde_json::json!(1);
    first["quantity"] = serde_json::json!("700");
    let mut second = first.clone();
    second["intent_id"] = serde_json::json!("day-partial");
    second["intent_seq"] = serde_json::json!(2);
    second["quantity"] = serde_json::json!("700");
    second["known_at"]["stable_seq"] = serde_json::json!(2);
    second["effective_at"]["stable_seq"] = serde_json::json!(2);
    input["intents"] = serde_json::json!([first, second]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let order = output["orders"]
        .as_array()
        .unwrap()
        .iter()
        .find(|order| order["intent_id"] == "day-partial")
        .unwrap();
    assert_eq!(order["status"], "expired");
    assert_eq!(order["reject_reason"], "day_expired");
    assert_eq!(order["remaining_quantity"], "400");
    assert_eq!(output["fills"].as_array().unwrap().len(), 2);
}

#[test]
fn limit_order_uses_limit_price_when_intraday_bar_touches() {
    let mut input = fixture()["input"].clone();
    input["sessions"][0]["bars"][0]["raw"]["open_atoms"] = serde_json::json!("1200");
    input["sessions"][0]["bars"][0]["raw"]["high_atoms"] = serde_json::json!("1300");
    input["sessions"][0]["bars"][0]["raw"]["low_atoms"] = serde_json::json!("1000");
    input["sessions"][0]["bars"][0]["raw"]["close_atoms"] = serde_json::json!("1100");
    input["sessions"][0]["bars"][0]["research"]["open_atoms"] = serde_json::json!("1200");
    input["sessions"][0]["bars"][0]["research"]["high_atoms"] = serde_json::json!("1300");
    input["sessions"][0]["bars"][0]["research"]["low_atoms"] = serde_json::json!("1000");
    input["sessions"][0]["bars"][0]["research"]["close_atoms"] = serde_json::json!("1100");
    let mut order = input["intents"][0].clone();
    order["intent_id"] = serde_json::json!("limit-buy");
    order["order_type"] = serde_json::json!("limit");
    order["limit_price_atoms"] = serde_json::json!("1100");
    input["intents"] = serde_json::json!([order]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    assert_eq!(output["fills"][0]["fill_price_atoms"], "1100");
    assert_eq!(output["assumptions"]["limit_orders"], true);
}

#[test]
fn limit_order_uses_raw_open_for_a_favorable_gap() {
    let mut input = fixture()["input"].clone();
    for basis in ["raw", "research"] {
        input["sessions"][0]["bars"][0][basis]["open_atoms"] = serde_json::json!("900");
        input["sessions"][0]["bars"][0][basis]["high_atoms"] = serde_json::json!("1000");
        input["sessions"][0]["bars"][0][basis]["low_atoms"] = serde_json::json!("900");
        input["sessions"][0]["bars"][0][basis]["close_atoms"] = serde_json::json!("950");
    }
    let mut order = input["intents"][0].clone();
    order["intent_id"] = serde_json::json!("gap-limit-buy");
    order["order_type"] = serde_json::json!("limit");
    order["limit_price_atoms"] = serde_json::json!("1000");
    input["intents"] = serde_json::json!([order]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    assert_eq!(output["fills"][0]["fill_price_atoms"], "900");
}

#[test]
fn execution_priority_is_market_then_limit_price_then_stable_id() {
    let mut stable_input = fixture()["input"].clone();
    stable_input["sessions"][0]["bars"][0]["raw"]["volume_quantity"] = serde_json::json!("1000");
    let mut z_market = stable_input["intents"][0].clone();
    z_market["intent_id"] = serde_json::json!("z-market");
    let mut a_market = z_market.clone();
    a_market["intent_id"] = serde_json::json!("a-market");
    a_market["intent_seq"] = serde_json::json!(2);
    stable_input["intents"] = serde_json::json!([z_market, a_market]);
    let stable_output: Value = serde_json::from_slice(
        &run_engine_v3(&serde_json::to_vec(&stable_input).unwrap()).unwrap(),
    )
    .unwrap();
    assert_eq!(stable_output["fills"][0]["intent_id"], "a-market");

    let mut type_input = fixture()["input"].clone();
    type_input["sessions"][0]["bars"][0]["raw"]["volume_quantity"] = serde_json::json!("1000");
    let mut a_limit = type_input["intents"][0].clone();
    a_limit["intent_id"] = serde_json::json!("a-limit");
    a_limit["order_type"] = serde_json::json!("limit");
    a_limit["limit_price_atoms"] = serde_json::json!("1100");
    let mut z_market = a_limit.clone();
    z_market["intent_id"] = serde_json::json!("z-market");
    z_market["intent_seq"] = serde_json::json!(2);
    z_market["order_type"] = serde_json::json!("market");
    z_market["limit_price_atoms"] = Value::Null;
    type_input["intents"] = serde_json::json!([a_limit, z_market]);
    let type_output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&type_input).unwrap()).unwrap())
            .unwrap();
    assert_eq!(type_output["fills"][0]["intent_id"], "z-market");

    let mut price_input = fixture()["input"].clone();
    price_input["sessions"][0]["bars"][0]["raw"]["volume_quantity"] = serde_json::json!("1000");
    for basis in ["raw", "research"] {
        price_input["sessions"][0]["bars"][0][basis]["open_atoms"] = serde_json::json!("1300");
        price_input["sessions"][0]["bars"][0][basis]["high_atoms"] = serde_json::json!("1300");
        price_input["sessions"][0]["bars"][0][basis]["low_atoms"] = serde_json::json!("1000");
        price_input["sessions"][0]["bars"][0][basis]["close_atoms"] = serde_json::json!("1100");
    }
    let mut low_limit = price_input["intents"][0].clone();
    low_limit["intent_id"] = serde_json::json!("a-low-limit");
    low_limit["order_type"] = serde_json::json!("limit");
    low_limit["limit_price_atoms"] = serde_json::json!("1100");
    let mut high_limit = low_limit.clone();
    high_limit["intent_id"] = serde_json::json!("z-high-limit");
    high_limit["intent_seq"] = serde_json::json!(2);
    high_limit["limit_price_atoms"] = serde_json::json!("1200");
    price_input["intents"] = serde_json::json!([low_limit, high_limit]);
    let price_output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&price_input).unwrap()).unwrap())
            .unwrap();
    assert_eq!(price_output["fills"][0]["intent_id"], "z-high-limit");
    assert_eq!(price_output["fills"][0]["fill_price_atoms"], "1200");
}

#[test]
fn minimum_commission_is_charged_per_fill() {
    let mut input = fixture()["input"].clone();
    input["account"]["commission_rate_atoms"] = serde_json::json!("1");
    input["account"]["minimum_commission_atoms"] = serde_json::json!("250");
    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    assert_eq!(output["fills"][0]["fee_atoms"], "250");
    assert_eq!(output["fills"][1]["fee_atoms"], "250");
    assert_eq!(output["metrics"]["total_fees_atoms"], "500");
}

#[test]
fn minimum_commission_is_not_repeated_across_partial_fills() {
    let mut input = fixture()["input"].clone();
    input["account"]["starting_cash_atoms"] = serde_json::json!("3000000");
    input["account"]["minimum_commission_atoms"] = serde_json::json!("250");
    let mut first = input["intents"][0].clone();
    first["intent_id"] = serde_json::json!("fee-first");
    first["intent_seq"] = serde_json::json!(1);
    first["quantity"] = serde_json::json!("700");
    let mut second = first.clone();
    second["intent_id"] = serde_json::json!("fee-gtc");
    second["intent_seq"] = serde_json::json!(2);
    second["quantity"] = serde_json::json!("700");
    second["time_in_force"] = serde_json::json!("gtc");
    second["known_at"]["stable_seq"] = serde_json::json!(2);
    second["effective_at"]["stable_seq"] = serde_json::json!(2);
    input["intents"] = serde_json::json!([first, second]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let fee_fills = output["fills"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|fill| fill["intent_id"] == "fee-gtc")
        .collect::<Vec<_>>();
    assert_eq!(fee_fills[0]["fee_atoms"], "250");
    assert_eq!(fee_fills[1]["fee_atoms"], "0");
    assert_eq!(output["metrics"]["total_fees_atoms"], "500");
}

#[test]
fn partial_fill_commission_charges_only_the_cumulative_minimum_top_up() {
    let mut input = fixture()["input"].clone();
    input["account"]["starting_cash_atoms"] = serde_json::json!("3000000");
    input["account"]["commission_rate_atoms"] = serde_json::json!("500");
    input["account"]["minimum_commission_atoms"] = serde_json::json!("250");
    let mut first = input["intents"][0].clone();
    first["intent_id"] = serde_json::json!("fee-first");
    first["intent_seq"] = serde_json::json!(1);
    first["quantity"] = serde_json::json!("700");
    let mut second = first.clone();
    second["intent_id"] = serde_json::json!("fee-gtc");
    second["intent_seq"] = serde_json::json!(2);
    second["quantity"] = serde_json::json!("700");
    second["time_in_force"] = serde_json::json!("gtc");
    second["known_at"]["stable_seq"] = serde_json::json!(2);
    second["effective_at"]["stable_seq"] = serde_json::json!(2);
    input["intents"] = serde_json::json!([first, second]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let fee_fills = output["fills"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|fill| fill["intent_id"] == "fee-gtc")
        .collect::<Vec<_>>();
    // Raw fees are 150 and 200.  The first fill tops the order up to the
    // 250-atom minimum; the second owes only the remaining 100 atoms once
    // cumulative raw commission reaches 350.
    assert_eq!(fee_fills[0]["fee_atoms"], "250");
    assert_eq!(fee_fills[1]["fee_atoms"], "100");
    assert_eq!(output["metrics"]["total_fees_atoms"], "700");
}

#[test]
fn cancel_intent_cancels_a_pending_gtc_before_it_can_fill() {
    let mut input = fixture()["input"].clone();
    let mut target = input["intents"][0].clone();
    target["intent_id"] = serde_json::json!("pending-limit");
    target["order_type"] = serde_json::json!("limit");
    target["limit_price_atoms"] = serde_json::json!("900");
    target["time_in_force"] = serde_json::json!("gtc");
    target["effective_at"]["session_seq"] = serde_json::json!(2);
    target["effective_at"]["stable_seq"] = serde_json::json!(2);
    target["known_at"]["session_seq"] = serde_json::json!(1);
    target["known_at"]["stable_seq"] = serde_json::json!(1);
    let mut cancel = target.clone();
    cancel["intent_kind"] = serde_json::json!("cancel");
    cancel["intent_id"] = serde_json::json!("cancel-pending-limit");
    cancel["intent_seq"] = serde_json::json!(2);
    cancel["quantity"] = serde_json::json!("0");
    cancel["effective_at"]["stable_seq"] = serde_json::json!(1);
    cancel["known_at"]["stable_seq"] = serde_json::json!(0);
    cancel["cancelled_intent_id"] = serde_json::json!("pending-limit");
    input["intents"] = serde_json::json!([target, cancel]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let target_order = output["orders"]
        .as_array()
        .unwrap()
        .iter()
        .find(|order| order["intent_id"] == "pending-limit")
        .unwrap();
    assert_eq!(target_order["status"], "cancelled");
    assert_eq!(target_order["cancelled_intent_id"], "cancel-pending-limit");
    assert_eq!(output["fills"].as_array().unwrap().len(), 0);
    let cancel_order = output["orders"]
        .as_array()
        .unwrap()
        .iter()
        .find(|order| order["intent_id"] == "cancel-pending-limit")
        .unwrap();
    assert_eq!(cancel_order["status"], "filled");
    assert_eq!(cancel_order["cancelled_intent_id"], "pending-limit");
}

#[test]
fn later_same_session_cancel_cannot_preempt_an_earlier_fill() {
    let mut input = fixture()["input"].clone();
    let mut target = input["intents"][0].clone();
    target["intent_id"] = serde_json::json!("same-session-market");
    target["effective_at"]["session_seq"] = serde_json::json!(2);
    target["effective_at"]["stable_seq"] = serde_json::json!(1);
    target["known_at"]["session_seq"] = serde_json::json!(1);
    target["known_at"]["stable_seq"] = serde_json::json!(1);

    let mut cancel = target.clone();
    cancel["intent_kind"] = serde_json::json!("cancel");
    cancel["intent_id"] = serde_json::json!("cancel-same-session-market");
    cancel["intent_seq"] = serde_json::json!(2);
    cancel["quantity"] = serde_json::json!("0");
    cancel["effective_at"]["stable_seq"] = serde_json::json!(2);
    cancel["known_at"]["stable_seq"] = serde_json::json!(2);
    cancel["cancelled_intent_id"] = serde_json::json!("same-session-market");
    input["intents"] = serde_json::json!([target, cancel]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let order = |intent_id: &str| {
        output["orders"]
            .as_array()
            .unwrap()
            .iter()
            .find(|candidate| candidate["intent_id"] == intent_id)
            .unwrap()
    };

    assert_eq!(order("same-session-market")["status"], "filled");
    assert_eq!(order("cancel-same-session-market")["status"], "rejected");
    assert_eq!(
        order("cancel-same-session-market")["reject_reason"],
        "target_not_open"
    );
    assert_eq!(output["fills"].as_array().unwrap().len(), 1);
    assert_eq!(output["fills"][0]["intent_id"], "same-session-market");
}

#[test]
fn cash_dividend_and_split_apply_to_both_books_before_session_orders() {
    let mut input = dual_open_input();
    for basis in ["raw", "research"] {
        input["sessions"][1]["bars"][0][basis]["open_atoms"] = serde_json::json!("500");
        input["sessions"][1]["bars"][0][basis]["high_atoms"] = serde_json::json!("500");
        input["sessions"][1]["bars"][0][basis]["low_atoms"] = serde_json::json!("500");
        input["sessions"][1]["bars"][0][basis]["close_atoms"] = serde_json::json!("500");
    }
    input["corporate_actions"] = serde_json::json!([
        {
            "action_id": "dividend-1",
            "symbol": "AAA.XSHG",
            "effective_at": {"session_seq": 2, "phase": "open", "stable_seq": 1},
            "action_type": "cash_dividend",
            "cash_per_share_atoms": "10",
            "numerator": null,
            "denominator": null,
            "settlement_price_atoms": null
        },
        {
            "action_id": "split-1",
            "symbol": "AAA.XSHG",
            "effective_at": {"session_seq": 2, "phase": "open", "stable_seq": 2},
            "action_type": "split",
            "cash_per_share_atoms": null,
            "numerator": 2,
            "denominator": 1,
            "settlement_price_atoms": null
        }
    ]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let ledger = output["corporate_action_ledger"].as_array().unwrap();
    assert_eq!(ledger.len(), 4);
    assert_eq!(ledger[0]["action_id"], "dividend-1");
    assert_eq!(ledger[0]["book"], "cash_long");
    assert_eq!(ledger[0]["available_cash_delta_atoms"], "1000");
    assert_eq!(ledger[1]["book"], "research_short");
    assert_eq!(ledger[1]["available_cash_delta_atoms"], "-1000");
    assert_eq!(ledger[2]["action_id"], "split-1");
    assert_eq!(ledger[2]["quantity_before"], "100");
    assert_eq!(ledger[2]["quantity_after"], "200");
    assert_eq!(ledger[3]["book"], "research_short");
    assert_eq!(ledger[3]["quantity_after"], "200");
    assert_eq!(output["equity_curve"][1]["available_cash_atoms"], "800000");
    assert_eq!(output["equity_curve"][1]["frozen_margin_atoms"], "100000");
    assert_eq!(output["equity_curve"][1]["equity_atoms"], "1000000");
    assert_eq!(output["metrics"]["open_position_count"], 2);
    assert_eq!(output["assumptions"]["corporate_actions"], true);
    assert_equity_identity(&output);
}

#[test]
fn delist_settlement_closes_both_books_releases_pools_and_cancels_gtc() {
    let mut input = dual_open_input();
    input["sessions"][1]["bars"][0]["trading_status"] = serde_json::json!("delisted");
    for basis in ["raw", "research"] {
        input["sessions"][1]["bars"][0][basis]["open_atoms"] = serde_json::json!("900");
        input["sessions"][1]["bars"][0][basis]["high_atoms"] = serde_json::json!("900");
        input["sessions"][1]["bars"][0][basis]["low_atoms"] = serde_json::json!("900");
        input["sessions"][1]["bars"][0][basis]["close_atoms"] = serde_json::json!("900");
    }
    let mut pending = input["intents"][0].clone();
    pending["intent_id"] = serde_json::json!("pending-gtc");
    pending["intent_seq"] = serde_json::json!(3);
    pending["order_type"] = serde_json::json!("limit");
    pending["limit_price_atoms"] = serde_json::json!("500");
    pending["time_in_force"] = serde_json::json!("gtc");
    pending["known_at"]["stable_seq"] = serde_json::json!(3);
    pending["effective_at"]["stable_seq"] = serde_json::json!(3);
    input["intents"].as_array_mut().unwrap().push(pending);
    input["corporate_actions"] = serde_json::json!([{
        "action_id": "delist-1",
        "symbol": "AAA.XSHG",
        "effective_at": {"session_seq": 2, "phase": "open", "stable_seq": 1},
        "action_type": "delist_settlement",
        "cash_per_share_atoms": null,
        "numerator": null,
        "denominator": null,
        "settlement_price_atoms": "900"
    }]);

    let input_bytes = serde_json::to_vec(&input).unwrap();
    let direct = run_engine_v3(&input_bytes).unwrap();
    let output: Value = serde_json::from_slice(&direct).unwrap();
    let ledger = output["corporate_action_ledger"].as_array().unwrap();
    assert_eq!(ledger.len(), 2);
    assert_eq!(ledger[0]["book"], "cash_long");
    assert_eq!(ledger[0]["available_cash_delta_atoms"], "90000");
    assert_eq!(ledger[0]["realized_pnl_delta_atoms"], "-10000");
    assert_eq!(ledger[1]["book"], "research_short");
    assert_eq!(ledger[1]["available_cash_delta_atoms"], "110000");
    assert_eq!(ledger[1]["frozen_margin_delta_atoms"], "-100000");
    assert_eq!(ledger[1]["isolated_proceeds_delta_atoms"], "-100000");
    assert_eq!(ledger[1]["realized_pnl_delta_atoms"], "10000");
    let pending_order = output["orders"]
        .as_array()
        .unwrap()
        .iter()
        .find(|order| order["intent_id"] == "pending-gtc")
        .unwrap();
    assert_eq!(pending_order["status"], "cancelled");
    assert_eq!(pending_order["reject_reason"], "delisted_settlement");
    assert_eq!(output["equity_curve"][1]["available_cash_atoms"], "1000000");
    assert_eq!(output["equity_curve"][1]["frozen_margin_atoms"], "0");
    assert_eq!(
        output["equity_curve"][1]["isolated_short_proceeds_atoms"],
        "0"
    );
    assert_eq!(output["metrics"]["closed_trade_count"], 2);
    assert_eq!(output["metrics"]["open_position_count"], 0);
    assert_equity_identity(&output);

    let context = "c".repeat(64);
    let mut checkpoint = start_engine_checkpoint_v3(&input_bytes, &context, 1).unwrap();
    while serde_json::from_slice::<Value>(&checkpoint).unwrap()["status"] != "complete" {
        checkpoint = step_engine_checkpoint_v3(&input_bytes, &context, &checkpoint).unwrap();
    }
    assert_eq!(
        finalize_engine_checkpoint_v3(&input_bytes, &context, &checkpoint).unwrap(),
        direct
    );
}

#[test]
fn unsupported_corporate_action_fails_preflight() {
    let mut input = fixture()["input"].clone();
    input["corporate_actions"] = serde_json::json!([{
        "action_id": "rights-1",
        "symbol": "AAA.XSHG",
        "effective_at": {"session_seq": 2, "phase": "open", "stable_seq": 1},
        "action_type": "rights_issue",
        "cash_per_share_atoms": null,
        "numerator": null,
        "denominator": null,
        "settlement_price_atoms": null
    }]);
    let error = run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap_err();
    assert!(error.to_string().contains("unknown variant"));
}

#[test]
fn reverse_split_preserves_lot_age_and_basis_for_next_session_closes() {
    let mut input = dual_open_input();
    input["intents"][0]["quantity"] = serde_json::json!("200");
    input["intents"][1]["quantity"] = serde_json::json!("200");
    for basis in ["raw", "research"] {
        input["sessions"][1]["bars"][0][basis]["open_atoms"] = serde_json::json!("2000");
        input["sessions"][1]["bars"][0][basis]["high_atoms"] = serde_json::json!("2000");
        input["sessions"][1]["bars"][0][basis]["low_atoms"] = serde_json::json!("2000");
        input["sessions"][1]["bars"][0][basis]["close_atoms"] = serde_json::json!("2000");
    }
    let mut long_close = input["intents"][0].clone();
    long_close["intent_id"] = serde_json::json!("long-close-after-reverse-split");
    long_close["intent_seq"] = serde_json::json!(3);
    long_close["side"] = serde_json::json!("sell");
    long_close["position_effect"] = serde_json::json!("close");
    long_close["quantity"] = serde_json::json!("100");
    long_close["known_at"]["session_seq"] = serde_json::json!(1);
    long_close["known_at"]["stable_seq"] = serde_json::json!(3);
    long_close["effective_at"]["session_seq"] = serde_json::json!(2);
    long_close["effective_at"]["stable_seq"] = serde_json::json!(3);
    let mut short_close = long_close.clone();
    short_close["intent_id"] = serde_json::json!("short-close-after-reverse-split");
    short_close["intent_seq"] = serde_json::json!(4);
    short_close["book"] = serde_json::json!("research_short");
    short_close["side"] = serde_json::json!("buy");
    short_close["known_at"]["stable_seq"] = serde_json::json!(4);
    short_close["effective_at"]["stable_seq"] = serde_json::json!(4);
    input["intents"].as_array_mut().unwrap().push(long_close);
    input["intents"].as_array_mut().unwrap().push(short_close);
    input["corporate_actions"] = serde_json::json!([{
        "action_id": "reverse-split-1",
        "symbol": "AAA.XSHG",
        "effective_at": {"session_seq": 2, "phase": "open", "stable_seq": 1},
        "action_type": "reverse_split",
        "cash_per_share_atoms": null,
        "numerator": 1,
        "denominator": 2,
        "settlement_price_atoms": null
    }]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    assert_eq!(
        output["corporate_action_ledger"][0]["quantity_before"],
        "200"
    );
    assert_eq!(
        output["corporate_action_ledger"][0]["quantity_after"],
        "100"
    );
    assert_eq!(
        output["corporate_action_ledger"][1]["quantity_after"],
        "100"
    );
    assert_eq!(output["fills"].as_array().unwrap().len(), 4);
    assert_eq!(output["cash_ledger"][2]["realized_pnl_delta_atoms"], "0");
    assert_eq!(output["cash_ledger"][3]["realized_pnl_delta_atoms"], "0");
    assert_eq!(output["metrics"]["ending_equity_atoms"], "1000000");
    assert_eq!(output["metrics"]["open_position_count"], 0);
    assert_equity_identity(&output);
}

#[test]
fn isolated_short_proceeds_do_not_fund_available_cash() {
    let mut input = fixture()["input"].clone();
    input["account"]["starting_cash_atoms"] = serde_json::json!("150000");
    let long_open = input["intents"][0].clone();
    let mut short_open = long_open.clone();
    short_open["intent_id"] = serde_json::json!("short-open");
    short_open["intent_seq"] = serde_json::json!(2);
    short_open["book"] = serde_json::json!("research_short");
    short_open["side"] = serde_json::json!("sell");
    short_open["position_effect"] = serde_json::json!("open");
    short_open["known_at"]["stable_seq"] = serde_json::json!(2);
    short_open["effective_at"]["stable_seq"] = serde_json::json!(2);
    input["intents"] = serde_json::json!([long_open, short_open]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let short_order = output["orders"]
        .as_array()
        .unwrap()
        .iter()
        .find(|order| order["intent_id"] == "short-open")
        .unwrap();
    assert_eq!(short_order["status"], "rejected");
    assert_eq!(short_order["reject_reason"], "insufficient_cash_for_short");
    assert_eq!(output["equity_curve"][0]["available_cash_atoms"], "50000");
    assert_eq!(output["equity_curve"][0]["frozen_margin_atoms"], "0");
    assert_eq!(
        output["equity_curve"][0]["isolated_short_proceeds_atoms"],
        "0"
    );
    assert_equity_identity(&output);
}

#[test]
fn suspended_day_expires_while_gtc_carries_to_the_next_tradable_session() {
    let mut input = fixture()["input"].clone();
    input["sessions"][0]["bars"][0]["trading_status"] = serde_json::json!("suspended");
    let mut day = input["intents"][0].clone();
    day["intent_id"] = serde_json::json!("suspended-day");
    let mut gtc = day.clone();
    gtc["intent_id"] = serde_json::json!("suspended-gtc");
    gtc["intent_seq"] = serde_json::json!(2);
    gtc["time_in_force"] = serde_json::json!("gtc");
    gtc["known_at"]["stable_seq"] = serde_json::json!(2);
    gtc["effective_at"]["stable_seq"] = serde_json::json!(2);
    input["intents"] = serde_json::json!([day, gtc]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let order = |id: &str| {
        output["orders"]
            .as_array()
            .unwrap()
            .iter()
            .find(|candidate| candidate["intent_id"] == id)
            .unwrap()
    };
    assert_eq!(order("suspended-day")["status"], "rejected");
    assert_eq!(order("suspended-day")["reject_reason"], "not_tradable");
    assert_eq!(order("suspended-gtc")["status"], "filled");
    assert_eq!(output["fills"][0]["intent_id"], "suspended-gtc");
    assert_eq!(output["fills"][0]["session_seq"], 2);
}

#[test]
fn price_limit_blocks_day_but_carries_gtc() {
    let mut input = fixture()["input"].clone();
    input["sessions"][0]["bars"][0]["price_limit_state"] = serde_json::json!("limit_up");
    let mut day = input["intents"][0].clone();
    day["intent_id"] = serde_json::json!("limit-day");
    let mut gtc = day.clone();
    gtc["intent_id"] = serde_json::json!("limit-gtc");
    gtc["intent_seq"] = serde_json::json!(2);
    gtc["time_in_force"] = serde_json::json!("gtc");
    gtc["known_at"]["stable_seq"] = serde_json::json!(2);
    gtc["effective_at"]["stable_seq"] = serde_json::json!(2);
    input["intents"] = serde_json::json!([day, gtc]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let order = |id: &str| {
        output["orders"]
            .as_array()
            .unwrap()
            .iter()
            .find(|candidate| candidate["intent_id"] == id)
            .unwrap()
    };
    assert_eq!(order("limit-day")["status"], "rejected");
    assert_eq!(order("limit-day")["reject_reason"], "price_limit");
    assert_eq!(order("limit-gtc")["status"], "filled");
    assert_eq!(output["fills"][0]["intent_id"], "limit-gtc");
    assert_eq!(output["fills"][0]["session_seq"], 2);
}

#[test]
fn limit_down_blocks_a_cash_long_sell() {
    let mut input = fixture()["input"].clone();
    input["sessions"][1]["bars"][0]["price_limit_state"] = serde_json::json!("limit_down");
    input["intents"] =
        serde_json::json!([input["intents"][0].clone(), input["intents"][2].clone()]);
    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let close = output["orders"]
        .as_array()
        .unwrap()
        .iter()
        .find(|order| order["intent_id"] == "long-close-next-day")
        .unwrap();
    assert_eq!(close["status"], "rejected");
    assert_eq!(close["reject_reason"], "price_limit");
    assert_eq!(output["fills"].as_array().unwrap().len(), 1);
}

#[test]
fn market_costs_use_checked_integer_fee_stamp_and_slippage_atoms() {
    let mut input = fixture()["input"].clone();
    input["account"]["commission_rate_atoms"] = serde_json::json!("10000");
    input["account"]["stamp_duty_rate_atoms"] = serde_json::json!("10000");
    input["account"]["market_slippage_atoms"] = serde_json::json!("10");
    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    let fills = output["fills"].as_array().unwrap();
    assert_eq!(fills.len(), 2);
    assert_eq!(fills[0]["fill_price_atoms"], "1010");
    assert_eq!(fills[0]["notional_atoms"], "101000");
    assert_eq!(fills[0]["fee_atoms"], "1010");
    assert_eq!(fills[0]["stamp_duty_atoms"], "0");
    assert_eq!(fills[0]["slippage_atoms"], "1000");
    assert_eq!(fills[1]["fill_price_atoms"], "990");
    assert_eq!(fills[1]["notional_atoms"], "99000");
    assert_eq!(fills[1]["fee_atoms"], "990");
    assert_eq!(fills[1]["stamp_duty_atoms"], "990");
    assert_eq!(fills[1]["slippage_atoms"], "1000");
    assert_eq!(output["metrics"]["total_fees_atoms"], "2000");
    assert_eq!(output["metrics"]["total_stamp_duty_atoms"], "990");
    assert_eq!(output["metrics"]["total_slippage_atoms"], "2000");
    assert_eq!(output["metrics"]["ending_equity_atoms"], "995010");
}

#[test]
fn odd_lot_order_is_rejected_before_transition() {
    let mut input = fixture()["input"].clone();
    input["intents"][0]["quantity"] = serde_json::json!("50");
    let error = run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap_err();
    assert!(error.to_string().contains("whole lots"));
}

#[test]
fn missing_selected_symbol_bar_fails_preflight() {
    let mut input = fixture()["input"].clone();
    input["sessions"][1]["bars"] = serde_json::json!([]);
    let error = run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap_err();
    assert!(
        error
            .to_string()
            .contains("sessions must contain exactly the sorted account symbols")
    );
}

#[test]
fn reverse_split_adjusts_lot_unit_so_integer_residual_can_close() {
    let mut input = fixture()["input"].clone();
    for basis in ["raw", "research"] {
        input["sessions"][1]["bars"][0][basis]["open_atoms"] = serde_json::json!("2000");
        input["sessions"][1]["bars"][0][basis]["high_atoms"] = serde_json::json!("2000");
        input["sessions"][1]["bars"][0][basis]["low_atoms"] = serde_json::json!("2000");
        input["sessions"][1]["bars"][0][basis]["close_atoms"] = serde_json::json!("2000");
    }
    let long_open = input["intents"][0].clone();
    let mut close = long_open.clone();
    close["intent_id"] = serde_json::json!("close-residual");
    close["intent_seq"] = serde_json::json!(2);
    close["side"] = serde_json::json!("sell");
    close["position_effect"] = serde_json::json!("close");
    close["quantity"] = serde_json::json!("50");
    close["known_at"]["session_seq"] = serde_json::json!(1);
    close["known_at"]["stable_seq"] = serde_json::json!(2);
    close["effective_at"]["session_seq"] = serde_json::json!(2);
    close["effective_at"]["stable_seq"] = serde_json::json!(2);
    input["intents"] = serde_json::json!([long_open, close]);
    input["corporate_actions"] = serde_json::json!([{
        "action_id": "reverse-split-residual",
        "symbol": "AAA.XSHG",
        "effective_at": {"session_seq": 2, "phase": "open", "stable_seq": 1},
        "action_type": "reverse_split",
        "cash_per_share_atoms": null,
        "numerator": 1,
        "denominator": 2,
        "settlement_price_atoms": null
    }]);

    let output: Value =
        serde_json::from_slice(&run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap())
            .unwrap();
    assert_eq!(output["fills"].as_array().unwrap().len(), 2);
    assert_eq!(output["fills"][1]["quantity"], "50");
    assert_eq!(output["orders"][1]["status"], "filled");
    assert_eq!(output["metrics"]["ending_equity_atoms"], "1000000");
}

#[test]
fn split_rejects_non_integral_entry_price_instead_of_erasing_basis_metadata() {
    let mut input = fixture()["input"].clone();
    for basis in ["raw", "research"] {
        input["sessions"][0]["bars"][0][basis]["open_atoms"] = serde_json::json!("1001");
        input["sessions"][0]["bars"][0][basis]["high_atoms"] = serde_json::json!("1001");
        input["sessions"][0]["bars"][0][basis]["low_atoms"] = serde_json::json!("1001");
        input["sessions"][0]["bars"][0][basis]["close_atoms"] = serde_json::json!("1001");
    }
    input["intents"] = serde_json::json!([input["intents"][0].clone()]);
    input["corporate_actions"] = serde_json::json!([{
        "action_id": "split-non-integral-price",
        "symbol": "AAA.XSHG",
        "effective_at": {"session_seq": 2, "phase": "open", "stable_seq": 1},
        "action_type": "split",
        "cash_per_share_atoms": null,
        "numerator": 2,
        "denominator": 1,
        "settlement_price_atoms": null
    }]);
    let error = run_engine_v3(&serde_json::to_vec(&input).unwrap()).unwrap_err();
    assert!(error.to_string().contains("non-integral long entry price"));
}
