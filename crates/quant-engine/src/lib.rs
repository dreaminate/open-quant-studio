use std::collections::HashSet;
use std::fmt::{Display, Formatter};

use serde::{Deserialize, Deserializer, Serialize, Serializer};

const ENGINE_VERSION: &str = "oqs-quant-engine/0.1.0";

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
struct Atom(i128);

impl Atom {
    const ZERO: Self = Self(0);
}

impl<'de> Deserialize<'de> for Atom {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        value
            .parse::<i128>()
            .map(Self)
            .map_err(serde::de::Error::custom)
    }
}

impl Serialize for Atom {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(&self.0.to_string())
    }
}

#[derive(Debug, Eq, PartialEq)]
pub struct EngineError(String);

impl EngineError {
    fn new(message: impl Into<String>) -> Self {
        Self(message.into())
    }
}

impl Display for EngineError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for EngineError {}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct EngineInputV1 {
    schema_version: u32,
    account: AccountSpec,
    bars: Vec<Bar>,
    funding_events: Vec<FundingEvent>,
    intents: Vec<OrderIntent>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AccountSpec {
    model: String,
    symbol: String,
    price_scale: u32,
    cash_scale: u32,
    rate_scale: i128,
    starting_balance_atoms: Atom,
    lot_size: i128,
    allow_research_short: bool,
    commission_rate_atoms: Atom,
    stamp_duty_rate_atoms: Atom,
    maker_fee_rate_atoms: Atom,
    taker_fee_rate_atoms: Atom,
    slippage_atoms: Atom,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Bar {
    session_seq: u64,
    timestamp: String,
    open_atoms: Atom,
    high_atoms: Atom,
    low_atoms: Atom,
    close_atoms: Atom,
    can_buy: bool,
    can_sell: bool,
}

#[derive(Clone, Copy, Deserialize, Eq, Ord, PartialEq, PartialOrd)]
#[serde(rename_all = "snake_case")]
enum EventPhase {
    Open,
    Intrabar,
    Close,
}

#[derive(Clone, Copy, Deserialize, Eq, Ord, PartialEq, PartialOrd)]
#[serde(deny_unknown_fields)]
struct EventKey {
    session_seq: u64,
    phase: EventPhase,
    stable_seq: u64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct FundingEvent {
    event_id: String,
    session_seq: u64,
    phase: EventPhase,
    stable_seq: u64,
    rate_atoms: Atom,
    mark_price_atoms: Atom,
}

#[derive(Clone, Copy, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum Side {
    Buy,
    Sell,
}

#[derive(Clone, Copy, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum PositionEffect {
    Open,
    Close,
}

#[derive(Clone, Copy, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum OrderType {
    Market,
    Limit,
    Stop,
}

#[derive(Clone, Copy, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum TimeInForce {
    Day,
    Gtc,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct OrderIntent {
    intent_id: String,
    intent_seq: u64,
    symbol: String,
    side: Side,
    position_effect: PositionEffect,
    quantity: Atom,
    order_type: OrderType,
    known_at: EventKey,
    effective_at: EventKey,
    limit_price_atoms: Option<Atom>,
    stop_price_atoms: Option<Atom>,
    time_in_force: TimeInForce,
    oco_group: Option<String>,
}

#[derive(Serialize)]
struct EngineOutputV1 {
    schema_version: u32,
    engine_version: &'static str,
    account_model: &'static str,
    orders: Vec<OrderRecord>,
    trades: Vec<TradeRecord>,
    positions: Vec<PositionRecord>,
    cash_ledger: Vec<CashRecord>,
    funding_ledger: Vec<FundingRecord>,
    equity_curve: Vec<EquityPoint>,
    drawdown_curve: Vec<DrawdownPoint>,
    metrics: Metrics,
    costs: CostSummary,
    assumptions: Assumptions,
}

#[derive(Serialize)]
struct OrderRecord {
    intent_id: String,
    intent_seq: u64,
    status: &'static str,
    side: Side,
    position_effect: PositionEffect,
    order_type: OrderType,
    quantity: Atom,
    filled_session_seq: Option<u64>,
    filled_phase: Option<&'static str>,
}

#[derive(Serialize)]
struct TradeRecord {
    trade_id: String,
    intent_id: String,
    session_seq: u64,
    side: Side,
    position_effect: PositionEffect,
    quantity: Atom,
    fill_price_atoms: Atom,
    notional_atoms: Atom,
    fee_atoms: Atom,
    stamp_duty_atoms: Atom,
    slippage_atoms: Atom,
    liquidity: &'static str,
}

#[derive(Serialize)]
struct PositionRecord {
    intent_id: String,
    session_seq: u64,
    signed_quantity: Atom,
    eligible_quantity: Atom,
}

#[derive(Serialize)]
struct CashRecord {
    intent_id: String,
    session_seq: u64,
    notional_delta_atoms: Atom,
    fee_delta_atoms: Atom,
    stamp_duty_delta_atoms: Atom,
    realized_pnl_delta_atoms: Atom,
    funding_delta_atoms: Atom,
    resulting_cash_atoms: Atom,
}

#[derive(Serialize)]
struct FundingRecord {
    event_id: String,
    session_seq: u64,
    signed_quantity: Atom,
    rate_atoms: Atom,
    mark_price_atoms: Atom,
    wallet_delta_atoms: Atom,
    resulting_wallet_atoms: Atom,
}

#[derive(Serialize)]
struct EquityPoint {
    session_seq: u64,
    timestamp: String,
    mark_price_atoms: Atom,
    cash_atoms: Atom,
    signed_quantity: Atom,
    equity_atoms: Atom,
}

#[derive(Serialize)]
struct DrawdownPoint {
    session_seq: u64,
    equity_atoms: Atom,
    peak_equity_atoms: Atom,
    drawdown_atoms: Atom,
    drawdown_rate_atoms: Atom,
}

#[derive(Serialize)]
struct Metrics {
    starting_equity_atoms: Atom,
    ending_equity_atoms: Atom,
    net_pnl_atoms: Atom,
    total_return_rate_atoms: Atom,
    max_drawdown_atoms: Atom,
    max_drawdown_rate_atoms: Atom,
    total_fees_atoms: Atom,
    total_stamp_duty_atoms: Atom,
    total_funding_atoms: Atom,
    total_slippage_atoms: Atom,
    fill_count: usize,
    closed_trade_count: u64,
    open_position_count: u64,
}

#[derive(Serialize)]
struct CostSummary {
    commission_atoms: Atom,
    stamp_duty_atoms: Atom,
    funding_atoms: Atom,
    slippage_atoms: Atom,
}

#[derive(Serialize)]
struct Assumptions {
    fill_model: &'static str,
    partial_fills: bool,
    liquidate_on_end: bool,
    research_short: bool,
    research_short_notice: Option<&'static str>,
    one_x_notional: bool,
}

struct LongLot {
    quantity: i128,
    acquired_session_seq: u64,
}

struct FillDecision {
    price: i128,
    slippage_per_unit_atoms: i128,
    liquidity: &'static str,
    phase: &'static str,
}

pub fn run_engine_v1(input: &[u8]) -> Result<Vec<u8>, EngineError> {
    let input: EngineInputV1 = serde_json::from_slice(input)
        .map_err(|error| EngineError::new(format!("engine input is invalid: {error}")))?;
    let account_model = input.account.model.clone();
    let output = match account_model.as_str() {
        "a_share_cash" => run_a_share_cash(input)?,
        "crypto_linear_perp" => run_crypto_linear_perp(input)?,
        _ => return Err(EngineError::new("unsupported account model")),
    };
    serde_json::to_vec(&output)
        .map_err(|error| EngineError::new(format!("engine output failed: {error}")))
}

fn run_a_share_cash(input: EngineInputV1) -> Result<EngineOutputV1, EngineError> {
    validate_a_share_input(&input)?;
    let account = &input.account;
    let mut cash = account.starting_balance_atoms.0;
    let mut signed_quantity = 0_i128;
    let mut lots: Vec<LongLot> = Vec::new();
    let mut short_lots: Vec<LongLot> = Vec::new();
    let mut orders = Vec::new();
    let mut trades = Vec::new();
    let mut positions = Vec::new();
    let mut cash_ledger = Vec::new();
    let mut equity_curve = Vec::new();
    let mut drawdown_curve = Vec::new();
    let mut peak_equity = cash;
    let mut max_drawdown = 0_i128;
    let mut max_drawdown_rate = 0_i128;
    let mut total_fees = 0_i128;
    let mut total_stamp_duty = 0_i128;
    let mut total_slippage = 0_i128;
    let mut closed_trade_count = 0_u64;
    let mut filled_oco_groups = HashSet::new();
    let mut completed_intents = HashSet::new();

    for bar in &input.bars {
        let mut bar_intents: Vec<&OrderIntent> = input
            .intents
            .iter()
            .filter(|intent| {
                !completed_intents.contains(&intent.intent_id)
                    && match intent.time_in_force {
                        TimeInForce::Day => intent.effective_at.session_seq == bar.session_seq,
                        TimeInForce::Gtc => intent.effective_at.session_seq <= bar.session_seq,
                    }
            })
            .collect();
        bar_intents.sort_by(|left, right| intent_execution_order(left, right));
        for intent in bar_intents {
            if intent
                .oco_group
                .as_ref()
                .is_some_and(|group| filled_oco_groups.contains(group))
            {
                orders.push(order_record(intent, "cancelled", None, None));
                completed_intents.insert(intent.intent_id.clone());
                continue;
            }
            let Some(fill) = fill_decision(account, bar, intent)? else {
                if matches!(intent.time_in_force, TimeInForce::Day) {
                    orders.push(order_record(intent, "expired", None, None));
                    completed_intents.insert(intent.intent_id.clone());
                }
                continue;
            };
            let fill_price = fill.price;
            let quantity = intent.quantity.0;
            let notional = checked_mul(fill_price, quantity, "trade notional")?;
            let slippage = checked_mul(fill.slippage_per_unit_atoms, quantity, "trade slippage")?;
            let fee = rate_charge(
                notional,
                account.commission_rate_atoms.0,
                account.rate_scale,
            )?;
            let stamp_duty = if matches!(intent.side, Side::Sell) {
                rate_charge(
                    notional,
                    account.stamp_duty_rate_atoms.0,
                    account.rate_scale,
                )?
            } else {
                0
            };

            let notional_delta;
            match (intent.side, intent.position_effect) {
                (Side::Buy, PositionEffect::Open) => {
                    if signed_quantity < 0 {
                        return Err(EngineError::new(
                            "buy/open cannot cross an existing research short",
                        ));
                    }
                    let debit = checked_add(notional, fee, "buy cash debit")?;
                    cash = checked_sub(cash, debit, "buy cash")?;
                    signed_quantity =
                        checked_add(signed_quantity, quantity, "long position quantity")?;
                    lots.push(LongLot {
                        quantity,
                        acquired_session_seq: bar.session_seq,
                    });
                    notional_delta = -notional;
                }
                (Side::Sell, PositionEffect::Close) => {
                    if signed_quantity <= 0 {
                        return Err(EngineError::new(
                            "sell/close requires an existing long position",
                        ));
                    }
                    consume_eligible_lots(&mut lots, quantity, bar.session_seq)?;
                    signed_quantity =
                        checked_sub(signed_quantity, quantity, "long close quantity")?;
                    let costs = checked_add(fee, stamp_duty, "sell costs")?;
                    cash = checked_add(
                        cash,
                        checked_sub(notional, costs, "sell proceeds")?,
                        "sell cash",
                    )?;
                    notional_delta = notional;
                    if signed_quantity == 0 {
                        closed_trade_count += 1;
                    }
                }
                (Side::Sell, PositionEffect::Open) if account.allow_research_short => {
                    if signed_quantity > 0 {
                        return Err(EngineError::new(
                            "sell/open cannot cross an existing long position",
                        ));
                    }
                    signed_quantity = checked_sub(
                        signed_quantity,
                        quantity,
                        "research short position quantity",
                    )?;
                    short_lots.push(LongLot {
                        quantity,
                        acquired_session_seq: bar.session_seq,
                    });
                    let costs = checked_add(fee, stamp_duty, "short sale costs")?;
                    cash = checked_add(
                        cash,
                        checked_sub(notional, costs, "short sale proceeds")?,
                        "short sale cash",
                    )?;
                    notional_delta = notional;
                }
                (Side::Buy, PositionEffect::Close) if account.allow_research_short => {
                    if signed_quantity >= 0 {
                        return Err(EngineError::new(
                            "buy/close requires an existing research short",
                        ));
                    }
                    consume_eligible_lots(&mut short_lots, quantity, bar.session_seq)?;
                    signed_quantity =
                        checked_add(signed_quantity, quantity, "research short cover quantity")?;
                    let debit = checked_add(notional, fee, "cover cash debit")?;
                    cash = checked_sub(cash, debit, "cover cash")?;
                    notional_delta = -notional;
                    if signed_quantity == 0 {
                        closed_trade_count += 1;
                    }
                }
                _ => {
                    return Err(EngineError::new(
                        "A-share side and position effect are not enabled by the account model",
                    ));
                }
            }

            total_fees = checked_add(total_fees, fee, "total fees")?;
            total_stamp_duty = checked_add(total_stamp_duty, stamp_duty, "total stamp duty")?;
            total_slippage = checked_add(total_slippage, slippage, "total slippage")?;
            let eligible_quantity = if signed_quantity >= 0 {
                eligible_lot_quantity(&lots, bar.session_seq)?
            } else {
                -eligible_lot_quantity(&short_lots, bar.session_seq)?
            };

            orders.push(order_record(
                intent,
                "filled",
                Some(bar.session_seq),
                Some(fill.phase),
            ));
            trades.push(TradeRecord {
                trade_id: format!("fill:{}", intent.intent_id),
                intent_id: intent.intent_id.clone(),
                session_seq: bar.session_seq,
                side: intent.side,
                position_effect: intent.position_effect,
                quantity: intent.quantity,
                fill_price_atoms: Atom(fill_price),
                notional_atoms: Atom(notional),
                fee_atoms: Atom(fee),
                stamp_duty_atoms: Atom(stamp_duty),
                slippage_atoms: Atom(slippage),
                liquidity: fill.liquidity,
            });
            if let Some(group) = &intent.oco_group {
                filled_oco_groups.insert(group.clone());
            }
            completed_intents.insert(intent.intent_id.clone());
            positions.push(PositionRecord {
                intent_id: intent.intent_id.clone(),
                session_seq: bar.session_seq,
                signed_quantity: Atom(signed_quantity),
                eligible_quantity: Atom(eligible_quantity),
            });
            cash_ledger.push(CashRecord {
                intent_id: intent.intent_id.clone(),
                session_seq: bar.session_seq,
                notional_delta_atoms: Atom(notional_delta),
                fee_delta_atoms: Atom(-fee),
                stamp_duty_delta_atoms: Atom(-stamp_duty),
                realized_pnl_delta_atoms: Atom::ZERO,
                funding_delta_atoms: Atom::ZERO,
                resulting_cash_atoms: Atom(cash),
            });
        }

        let marked_position =
            checked_mul(signed_quantity, bar.close_atoms.0, "marked position value")?;
        let equity = checked_add(cash, marked_position, "marked equity")?;
        peak_equity = peak_equity.max(equity);
        let drawdown = checked_sub(equity, peak_equity, "drawdown")?;
        let drawdown_rate = checked_div(
            checked_mul(drawdown, account.rate_scale, "drawdown rate numerator")?,
            peak_equity,
            "drawdown rate",
        )?;
        max_drawdown = max_drawdown.min(drawdown);
        max_drawdown_rate = max_drawdown_rate.min(drawdown_rate);
        equity_curve.push(EquityPoint {
            session_seq: bar.session_seq,
            timestamp: bar.timestamp.clone(),
            mark_price_atoms: bar.close_atoms,
            cash_atoms: Atom(cash),
            signed_quantity: Atom(signed_quantity),
            equity_atoms: Atom(equity),
        });
        drawdown_curve.push(DrawdownPoint {
            session_seq: bar.session_seq,
            equity_atoms: Atom(equity),
            peak_equity_atoms: Atom(peak_equity),
            drawdown_atoms: Atom(drawdown),
            drawdown_rate_atoms: Atom(drawdown_rate),
        });
    }

    for intent in &input.intents {
        if !completed_intents.contains(&intent.intent_id) {
            orders.push(order_record(intent, "expired", None, None));
        }
    }

    let ending_equity = equity_curve
        .last()
        .map(|point| point.equity_atoms.0)
        .unwrap_or(account.starting_balance_atoms.0);
    let net_pnl = checked_sub(ending_equity, account.starting_balance_atoms.0, "net pnl")?;
    let total_return_rate = checked_div(
        checked_mul(net_pnl, account.rate_scale, "total return numerator")?,
        account.starting_balance_atoms.0,
        "total return",
    )?;
    let fill_count = trades.len();
    orders.sort_by_key(|order| order.intent_seq);

    Ok(EngineOutputV1 {
        schema_version: 1,
        engine_version: ENGINE_VERSION,
        account_model: "a_share_cash",
        orders,
        trades,
        positions,
        cash_ledger,
        funding_ledger: Vec::new(),
        equity_curve,
        drawdown_curve,
        metrics: Metrics {
            starting_equity_atoms: account.starting_balance_atoms,
            ending_equity_atoms: Atom(ending_equity),
            net_pnl_atoms: Atom(net_pnl),
            total_return_rate_atoms: Atom(total_return_rate),
            max_drawdown_atoms: Atom(max_drawdown),
            max_drawdown_rate_atoms: Atom(max_drawdown_rate),
            total_fees_atoms: Atom(total_fees),
            total_stamp_duty_atoms: Atom(total_stamp_duty),
            total_funding_atoms: Atom::ZERO,
            total_slippage_atoms: Atom(total_slippage),
            fill_count,
            closed_trade_count,
            open_position_count: u64::from(signed_quantity != 0),
        },
        costs: CostSummary {
            commission_atoms: Atom(total_fees),
            stamp_duty_atoms: Atom(total_stamp_duty),
            funding_atoms: Atom::ZERO,
            slippage_atoms: Atom(total_slippage),
        },
        assumptions: Assumptions {
            fill_model: "ohlc_full_fill_v1",
            partial_fills: false,
            liquidate_on_end: false,
            research_short: account.allow_research_short,
            research_short_notice: account.allow_research_short.then_some(
                "hypothetical research model; not ordinary cash-account trading capability",
            ),
            one_x_notional: false,
        },
    })
}

fn run_crypto_linear_perp(input: EngineInputV1) -> Result<EngineOutputV1, EngineError> {
    validate_crypto_input(&input)?;
    let account = &input.account;
    let mut wallet = account.starting_balance_atoms.0;
    let mut signed_quantity = 0_i128;
    let mut entry_price: Option<i128> = None;
    let mut orders = Vec::new();
    let mut trades = Vec::new();
    let mut positions = Vec::new();
    let mut cash_ledger = Vec::new();
    let mut funding_ledger = Vec::new();
    let mut equity_curve = Vec::new();
    let mut drawdown_curve = Vec::new();
    let mut peak_equity = wallet;
    let mut max_drawdown = 0_i128;
    let mut max_drawdown_rate = 0_i128;
    let mut total_fees = 0_i128;
    let mut total_funding = 0_i128;
    let mut total_slippage = 0_i128;
    let mut closed_trade_count = 0_u64;
    let mut filled_oco_groups = HashSet::new();
    let mut completed_intents = HashSet::new();

    for bar in &input.bars {
        let mut bar_intents: Vec<&OrderIntent> = input
            .intents
            .iter()
            .filter(|intent| {
                !completed_intents.contains(&intent.intent_id)
                    && match intent.time_in_force {
                        TimeInForce::Day => intent.effective_at.session_seq == bar.session_seq,
                        TimeInForce::Gtc => intent.effective_at.session_seq <= bar.session_seq,
                    }
            })
            .collect();
        bar_intents.sort_by(|left, right| intent_execution_order(left, right));
        for intent in bar_intents {
            if intent
                .oco_group
                .as_ref()
                .is_some_and(|group| filled_oco_groups.contains(group))
            {
                orders.push(order_record(intent, "cancelled", None, None));
                completed_intents.insert(intent.intent_id.clone());
                continue;
            }
            let Some(fill) = fill_decision(account, bar, intent)? else {
                if matches!(intent.time_in_force, TimeInForce::Day) {
                    orders.push(order_record(intent, "expired", None, None));
                    completed_intents.insert(intent.intent_id.clone());
                }
                continue;
            };
            let quantity = intent.quantity.0;
            let notional = checked_mul(fill.price, quantity, "perp fill notional")?;
            let slippage = checked_mul(
                fill.slippage_per_unit_atoms,
                quantity,
                "perp trade slippage",
            )?;
            let fee_rate = if fill.liquidity == "maker" {
                account.maker_fee_rate_atoms.0
            } else {
                account.taker_fee_rate_atoms.0
            };
            let fee = rate_charge(notional, fee_rate, account.rate_scale)?;
            let mut realized_pnl = 0_i128;

            match (intent.side, intent.position_effect) {
                (Side::Buy, PositionEffect::Open) => {
                    require_flat_position(signed_quantity)?;
                    require_one_x_capacity(wallet, notional, fee)?;
                    signed_quantity = quantity;
                    entry_price = Some(fill.price);
                }
                (Side::Sell, PositionEffect::Close) => {
                    if signed_quantity != quantity {
                        return Err(EngineError::new(
                            "sell/close must exactly close the active long position",
                        ));
                    }
                    realized_pnl = checked_mul(
                        checked_sub(fill.price, entry_price.unwrap(), "long price pnl")?,
                        quantity,
                        "long realized pnl",
                    )?;
                    signed_quantity = 0;
                    entry_price = None;
                    closed_trade_count += 1;
                }
                (Side::Sell, PositionEffect::Open) => {
                    require_flat_position(signed_quantity)?;
                    require_one_x_capacity(wallet, notional, fee)?;
                    signed_quantity = -quantity;
                    entry_price = Some(fill.price);
                }
                (Side::Buy, PositionEffect::Close) => {
                    if signed_quantity != -quantity {
                        return Err(EngineError::new(
                            "buy/close must exactly close the active short position",
                        ));
                    }
                    realized_pnl = checked_mul(
                        checked_sub(entry_price.unwrap(), fill.price, "short price pnl")?,
                        quantity,
                        "short realized pnl",
                    )?;
                    signed_quantity = 0;
                    entry_price = None;
                    closed_trade_count += 1;
                }
            }
            wallet = checked_add(wallet, realized_pnl, "wallet realized pnl")?;
            wallet = checked_sub(wallet, fee, "wallet fee")?;
            total_fees = checked_add(total_fees, fee, "total perp fees")?;
            total_slippage = checked_add(total_slippage, slippage, "total perp slippage")?;

            orders.push(order_record(
                intent,
                "filled",
                Some(bar.session_seq),
                Some(fill.phase),
            ));
            trades.push(TradeRecord {
                trade_id: format!("fill:{}", intent.intent_id),
                intent_id: intent.intent_id.clone(),
                session_seq: bar.session_seq,
                side: intent.side,
                position_effect: intent.position_effect,
                quantity: intent.quantity,
                fill_price_atoms: Atom(fill.price),
                notional_atoms: Atom(notional),
                fee_atoms: Atom(fee),
                stamp_duty_atoms: Atom::ZERO,
                slippage_atoms: Atom(slippage),
                liquidity: fill.liquidity,
            });
            positions.push(PositionRecord {
                intent_id: intent.intent_id.clone(),
                session_seq: bar.session_seq,
                signed_quantity: Atom(signed_quantity),
                eligible_quantity: Atom::ZERO,
            });
            cash_ledger.push(CashRecord {
                intent_id: intent.intent_id.clone(),
                session_seq: bar.session_seq,
                notional_delta_atoms: Atom::ZERO,
                fee_delta_atoms: Atom(-fee),
                stamp_duty_delta_atoms: Atom::ZERO,
                realized_pnl_delta_atoms: Atom(realized_pnl),
                funding_delta_atoms: Atom::ZERO,
                resulting_cash_atoms: Atom(wallet),
            });
            if let Some(group) = &intent.oco_group {
                filled_oco_groups.insert(group.clone());
            }
            completed_intents.insert(intent.intent_id.clone());
        }

        for event in input
            .funding_events
            .iter()
            .filter(|event| event.session_seq == bar.session_seq)
        {
            let funding_cost = if signed_quantity == 0 {
                0
            } else {
                let notional = checked_mul(
                    signed_quantity
                        .checked_abs()
                        .ok_or_else(|| EngineError::new("perp funding position overflow"))?,
                    event.mark_price_atoms.0,
                    "funding notional",
                )?;
                let signed_rate =
                    signed_rate_charge(notional, event.rate_atoms.0, account.rate_scale)?;
                if signed_quantity > 0 {
                    signed_rate
                } else {
                    checked_sub(0, signed_rate, "short funding direction")?
                }
            };
            let wallet_delta = checked_sub(0, funding_cost, "funding wallet delta")?;
            wallet = checked_add(wallet, wallet_delta, "funding wallet")?;
            total_funding = checked_add(total_funding, funding_cost, "total funding")?;
            cash_ledger.push(CashRecord {
                intent_id: format!("funding:{}", event.event_id),
                session_seq: event.session_seq,
                notional_delta_atoms: Atom::ZERO,
                fee_delta_atoms: Atom::ZERO,
                stamp_duty_delta_atoms: Atom::ZERO,
                realized_pnl_delta_atoms: Atom::ZERO,
                funding_delta_atoms: Atom(wallet_delta),
                resulting_cash_atoms: Atom(wallet),
            });
            funding_ledger.push(FundingRecord {
                event_id: event.event_id.clone(),
                session_seq: event.session_seq,
                signed_quantity: Atom(signed_quantity),
                rate_atoms: event.rate_atoms,
                mark_price_atoms: event.mark_price_atoms,
                wallet_delta_atoms: Atom(wallet_delta),
                resulting_wallet_atoms: Atom(wallet),
            });
        }

        let unrealized_pnl = perp_unrealized_pnl(signed_quantity, entry_price, bar.close_atoms.0)?;
        let equity = checked_add(wallet, unrealized_pnl, "perp marked equity")?;
        peak_equity = peak_equity.max(equity);
        let drawdown = checked_sub(equity, peak_equity, "perp drawdown")?;
        let drawdown_rate = checked_div(
            checked_mul(drawdown, account.rate_scale, "perp drawdown numerator")?,
            peak_equity,
            "perp drawdown rate",
        )?;
        max_drawdown = max_drawdown.min(drawdown);
        max_drawdown_rate = max_drawdown_rate.min(drawdown_rate);
        equity_curve.push(EquityPoint {
            session_seq: bar.session_seq,
            timestamp: bar.timestamp.clone(),
            mark_price_atoms: bar.close_atoms,
            cash_atoms: Atom(wallet),
            signed_quantity: Atom(signed_quantity),
            equity_atoms: Atom(equity),
        });
        drawdown_curve.push(DrawdownPoint {
            session_seq: bar.session_seq,
            equity_atoms: Atom(equity),
            peak_equity_atoms: Atom(peak_equity),
            drawdown_atoms: Atom(drawdown),
            drawdown_rate_atoms: Atom(drawdown_rate),
        });
    }

    for intent in &input.intents {
        if !completed_intents.contains(&intent.intent_id) {
            orders.push(order_record(intent, "expired", None, None));
        }
    }
    orders.sort_by_key(|order| order.intent_seq);
    let ending_equity = equity_curve
        .last()
        .map(|point| point.equity_atoms.0)
        .unwrap_or(account.starting_balance_atoms.0);
    let net_pnl = checked_sub(
        ending_equity,
        account.starting_balance_atoms.0,
        "perp net pnl",
    )?;
    let total_return_rate = checked_div(
        checked_mul(net_pnl, account.rate_scale, "perp return numerator")?,
        account.starting_balance_atoms.0,
        "perp total return",
    )?;
    let fill_count = trades.len();

    Ok(EngineOutputV1 {
        schema_version: 1,
        engine_version: ENGINE_VERSION,
        account_model: "crypto_linear_perp",
        orders,
        trades,
        positions,
        cash_ledger,
        funding_ledger,
        equity_curve,
        drawdown_curve,
        metrics: Metrics {
            starting_equity_atoms: account.starting_balance_atoms,
            ending_equity_atoms: Atom(ending_equity),
            net_pnl_atoms: Atom(net_pnl),
            total_return_rate_atoms: Atom(total_return_rate),
            max_drawdown_atoms: Atom(max_drawdown),
            max_drawdown_rate_atoms: Atom(max_drawdown_rate),
            total_fees_atoms: Atom(total_fees),
            total_stamp_duty_atoms: Atom::ZERO,
            total_funding_atoms: Atom(total_funding),
            total_slippage_atoms: Atom(total_slippage),
            fill_count,
            closed_trade_count,
            open_position_count: u64::from(signed_quantity != 0),
        },
        costs: CostSummary {
            commission_atoms: Atom(total_fees),
            stamp_duty_atoms: Atom::ZERO,
            funding_atoms: Atom(total_funding),
            slippage_atoms: Atom(total_slippage),
        },
        assumptions: Assumptions {
            fill_model: "ohlc_full_fill_v1",
            partial_fills: false,
            liquidate_on_end: false,
            research_short: false,
            research_short_notice: None,
            one_x_notional: true,
        },
    })
}

fn validate_a_share_input(input: &EngineInputV1) -> Result<(), EngineError> {
    let account = &input.account;
    if input.schema_version != 1 {
        return Err(EngineError::new("unsupported engine input schema"));
    }
    if account.model != "a_share_cash" {
        return Err(EngineError::new("unsupported account model"));
    }
    if account.price_scale == 0 || account.price_scale != account.cash_scale {
        return Err(EngineError::new(
            "price and cash scales must be equal and nonzero",
        ));
    }
    if account.rate_scale <= 0 || account.starting_balance_atoms.0 <= 0 {
        return Err(EngineError::new(
            "account scales and starting balance must be positive",
        ));
    }
    if account.commission_rate_atoms.0 < 0
        || account.commission_rate_atoms.0 > account.rate_scale
        || account.stamp_duty_rate_atoms.0 < 0
        || account.stamp_duty_rate_atoms.0 > account.rate_scale
        || account.slippage_atoms.0 < 0
    {
        return Err(EngineError::new(
            "A-share costs must be non-negative and rates cannot exceed their scale",
        ));
    }
    if account.lot_size != 100 {
        return Err(EngineError::new(
            "A-share account model requires a fixed 100-share lot",
        ));
    }
    if account.maker_fee_rate_atoms != Atom::ZERO
        || account.taker_fee_rate_atoms != Atom::ZERO
        || !input.funding_events.is_empty()
    {
        return Err(EngineError::new(
            "A-share input cannot contain crypto costs",
        ));
    }
    validate_bars(input, account.slippage_atoms.0)?;
    for bars in input.bars.windows(2) {
        if bars[0].session_seq >= bars[1].session_seq {
            return Err(EngineError::new("bars must have increasing session_seq"));
        }
    }
    let mut intent_ids = HashSet::new();
    for intents in input.intents.windows(2) {
        if intents[0].intent_seq >= intents[1].intent_seq {
            return Err(EngineError::new("intents must have increasing intent_seq"));
        }
    }
    for intent in &input.intents {
        if intent.intent_id.is_empty() || !intent_ids.insert(&intent.intent_id) {
            return Err(EngineError::new("intent_id must be nonempty and unique"));
        }
        if intent.symbol != account.symbol {
            return Err(EngineError::new("intent symbol does not match the account"));
        }
        if intent.known_at >= intent.effective_at {
            return Err(EngineError::new("effective_at must be after known_at"));
        }
        if intent.effective_at.phase != EventPhase::Open {
            return Err(EngineError::new("market intents must be effective at open"));
        }
        if intent.quantity.0 <= 0 || intent.quantity.0 % account.lot_size != 0 {
            return Err(EngineError::new("A-share quantity must use whole lots"));
        }
        match intent.order_type {
            OrderType::Market
                if intent.limit_price_atoms.is_none() && intent.stop_price_atoms.is_none() => {}
            OrderType::Limit
                if intent.limit_price_atoms.is_some() && intent.stop_price_atoms.is_none() => {}
            OrderType::Stop
                if intent.limit_price_atoms.is_none() && intent.stop_price_atoms.is_some() => {}
            _ => {
                return Err(EngineError::new(
                    "order type must carry exactly its matching price",
                ));
            }
        }
        validate_order_price(intent)?;
        if intent.oco_group.is_some()
            && (matches!(intent.order_type, OrderType::Market)
                || !matches!(intent.position_effect, PositionEffect::Close))
        {
            return Err(EngineError::new(
                "OCO is limited to protective Limit/Stop close orders",
            ));
        }
    }
    Ok(())
}

fn validate_crypto_input(input: &EngineInputV1) -> Result<(), EngineError> {
    let account = &input.account;
    if input.schema_version != 1 {
        return Err(EngineError::new("unsupported engine input schema"));
    }
    if account.model != "crypto_linear_perp" {
        return Err(EngineError::new("unsupported account model"));
    }
    if account.price_scale == 0 || account.price_scale != account.cash_scale {
        return Err(EngineError::new(
            "price and cash scales must be equal and nonzero",
        ));
    }
    if account.rate_scale <= 0 || account.starting_balance_atoms.0 <= 0 || account.lot_size <= 0 {
        return Err(EngineError::new(
            "crypto scales, lot size, and starting wallet must be positive",
        ));
    }
    if account.allow_research_short
        || account.commission_rate_atoms != Atom::ZERO
        || account.stamp_duty_rate_atoms != Atom::ZERO
    {
        return Err(EngineError::new(
            "crypto input cannot contain A-share account settings",
        ));
    }
    if account.maker_fee_rate_atoms.0 < 0
        || account.maker_fee_rate_atoms.0 > account.rate_scale
        || account.taker_fee_rate_atoms.0 < 0
        || account.taker_fee_rate_atoms.0 > account.rate_scale
        || account.slippage_atoms.0 < 0
    {
        return Err(EngineError::new(
            "crypto costs must be non-negative and rates cannot exceed their scale",
        ));
    }
    validate_bars(input, account.slippage_atoms.0)?;
    for bars in input.bars.windows(2) {
        if bars[0].session_seq >= bars[1].session_seq {
            return Err(EngineError::new("bars must have increasing session_seq"));
        }
    }

    let mut intent_ids = HashSet::new();
    for intents in input.intents.windows(2) {
        if intents[0].intent_seq >= intents[1].intent_seq {
            return Err(EngineError::new("intents must have increasing intent_seq"));
        }
    }
    for intent in &input.intents {
        if intent.intent_id.is_empty() || !intent_ids.insert(&intent.intent_id) {
            return Err(EngineError::new("intent_id must be nonempty and unique"));
        }
        if intent.symbol != account.symbol {
            return Err(EngineError::new("intent symbol does not match the account"));
        }
        if intent.known_at >= intent.effective_at {
            return Err(EngineError::new("effective_at must be after known_at"));
        }
        if intent.effective_at.phase != EventPhase::Open {
            return Err(EngineError::new("orders must be effective at open"));
        }
        if intent.quantity.0 <= 0 || intent.quantity.0 % account.lot_size != 0 {
            return Err(EngineError::new("crypto quantity must use whole lots"));
        }
        match intent.order_type {
            OrderType::Market
                if intent.limit_price_atoms.is_none() && intent.stop_price_atoms.is_none() => {}
            OrderType::Limit
                if intent.limit_price_atoms.is_some() && intent.stop_price_atoms.is_none() => {}
            OrderType::Stop
                if intent.limit_price_atoms.is_none() && intent.stop_price_atoms.is_some() => {}
            _ => {
                return Err(EngineError::new(
                    "order type must carry exactly its matching price",
                ));
            }
        }
        validate_order_price(intent)?;
        if intent.oco_group.is_some()
            && (matches!(intent.order_type, OrderType::Market)
                || !matches!(intent.position_effect, PositionEffect::Close))
        {
            return Err(EngineError::new(
                "OCO is limited to protective Limit/Stop close orders",
            ));
        }
    }

    let mut funding_ids = HashSet::new();
    for events in input.funding_events.windows(2) {
        let left = (events[0].session_seq, events[0].phase, events[0].stable_seq);
        let right = (events[1].session_seq, events[1].phase, events[1].stable_seq);
        if left >= right {
            return Err(EngineError::new("funding events must be ordered"));
        }
    }
    for event in &input.funding_events {
        if event.event_id.is_empty() || !funding_ids.insert(&event.event_id) {
            return Err(EngineError::new(
                "funding event_id must be nonempty and unique",
            ));
        }
        if event.phase != EventPhase::Close
            || event.mark_price_atoms.0 <= 0
            || !input
                .bars
                .iter()
                .any(|bar| bar.session_seq == event.session_seq)
        {
            return Err(EngineError::new(
                "funding event must bind an existing bar close and positive mark",
            ));
        }
    }
    Ok(())
}

fn validate_bars(input: &EngineInputV1, slippage: i128) -> Result<(), EngineError> {
    for bar in &input.bars {
        if bar.open_atoms.0 <= 0
            || bar.high_atoms.0 <= 0
            || bar.low_atoms.0 <= 0
            || bar.close_atoms.0 <= 0
        {
            return Err(EngineError::new("bar OHLC prices must be positive"));
        }
        if bar.low_atoms.0 > bar.open_atoms.0
            || bar.low_atoms.0 > bar.close_atoms.0
            || bar.high_atoms.0 < bar.open_atoms.0
            || bar.high_atoms.0 < bar.close_atoms.0
        {
            return Err(EngineError::new("bar OHLC prices must be coherent"));
        }
        if slippage >= bar.open_atoms.0 {
            return Err(EngineError::new(
                "slippage must remain below every positive bar open",
            ));
        }
    }
    Ok(())
}

fn validate_order_price(intent: &OrderIntent) -> Result<(), EngineError> {
    let price = match intent.order_type {
        OrderType::Market => return Ok(()),
        OrderType::Limit => intent.limit_price_atoms.unwrap().0,
        OrderType::Stop => intent.stop_price_atoms.unwrap().0,
    };
    if price <= 0 {
        return Err(EngineError::new("Limit and Stop prices must be positive"));
    }
    Ok(())
}

fn fill_decision(
    account: &AccountSpec,
    bar: &Bar,
    intent: &OrderIntent,
) -> Result<Option<FillDecision>, EngineError> {
    match intent.side {
        Side::Buy if !bar.can_buy => return Ok(None),
        Side::Sell if !bar.can_sell => return Ok(None),
        _ => {}
    }

    match (intent.order_type, intent.side) {
        (OrderType::Market, Side::Buy) => Ok(Some(FillDecision {
            price: checked_add(
                bar.open_atoms.0,
                account.slippage_atoms.0,
                "buy market fill price",
            )?,
            slippage_per_unit_atoms: account.slippage_atoms.0,
            liquidity: "taker",
            phase: "open",
        })),
        (OrderType::Market, Side::Sell) => Ok(Some(FillDecision {
            price: checked_sub(
                bar.open_atoms.0,
                account.slippage_atoms.0,
                "sell market fill price",
            )?,
            slippage_per_unit_atoms: account.slippage_atoms.0,
            liquidity: "taker",
            phase: "open",
        })),
        (OrderType::Limit, Side::Buy) => {
            let limit = intent.limit_price_atoms.unwrap().0;
            let (reference, liquidity, phase) = if bar.open_atoms.0 <= limit {
                (bar.open_atoms.0, "taker", "open")
            } else if bar.low_atoms.0 <= limit {
                (limit, "maker", "intrabar")
            } else {
                return Ok(None);
            };
            let price =
                checked_add(reference, account.slippage_atoms.0, "buy limit fill")?.min(limit);
            Ok(Some(FillDecision {
                price,
                slippage_per_unit_atoms: checked_sub(price, reference, "buy limit slippage")?,
                liquidity,
                phase,
            }))
        }
        (OrderType::Limit, Side::Sell) => {
            let limit = intent.limit_price_atoms.unwrap().0;
            let (reference, liquidity, phase) = if bar.open_atoms.0 >= limit {
                (bar.open_atoms.0, "taker", "open")
            } else if bar.high_atoms.0 >= limit {
                (limit, "maker", "intrabar")
            } else {
                return Ok(None);
            };
            let price =
                checked_sub(reference, account.slippage_atoms.0, "sell limit fill")?.max(limit);
            Ok(Some(FillDecision {
                price,
                slippage_per_unit_atoms: checked_sub(reference, price, "sell limit slippage")?,
                liquidity,
                phase,
            }))
        }
        (OrderType::Stop, Side::Buy) => {
            let stop = intent.stop_price_atoms.unwrap().0;
            let (reference, phase) = if bar.open_atoms.0 >= stop {
                (bar.open_atoms.0, "open")
            } else if bar.high_atoms.0 >= stop {
                (stop, "intrabar")
            } else {
                return Ok(None);
            };
            Ok(Some(FillDecision {
                price: checked_add(reference, account.slippage_atoms.0, "buy stop fill")?,
                slippage_per_unit_atoms: account.slippage_atoms.0,
                liquidity: "taker",
                phase,
            }))
        }
        (OrderType::Stop, Side::Sell) => {
            let stop = intent.stop_price_atoms.unwrap().0;
            let (reference, phase) = if bar.open_atoms.0 <= stop {
                (bar.open_atoms.0, "open")
            } else if bar.low_atoms.0 <= stop {
                (stop, "intrabar")
            } else {
                return Ok(None);
            };
            Ok(Some(FillDecision {
                price: checked_sub(reference, account.slippage_atoms.0, "sell stop fill")?,
                slippage_per_unit_atoms: account.slippage_atoms.0,
                liquidity: "taker",
                phase,
            }))
        }
    }
}

fn order_record(
    intent: &OrderIntent,
    status: &'static str,
    filled_session_seq: Option<u64>,
    filled_phase: Option<&'static str>,
) -> OrderRecord {
    OrderRecord {
        intent_id: intent.intent_id.clone(),
        intent_seq: intent.intent_seq,
        status,
        side: intent.side,
        position_effect: intent.position_effect,
        order_type: intent.order_type,
        quantity: intent.quantity,
        filled_session_seq,
        filled_phase,
    }
}

fn intent_execution_order(left: &OrderIntent, right: &OrderIntent) -> std::cmp::Ordering {
    let same_oco_event = left.oco_group.is_some()
        && left.oco_group == right.oco_group
        && left.effective_at.session_seq == right.effective_at.session_seq
        && left.effective_at.phase == right.effective_at.phase;
    if same_oco_event {
        order_type_priority(left.order_type)
            .cmp(&order_type_priority(right.order_type))
            .then(left.effective_at.cmp(&right.effective_at))
            .then(left.intent_seq.cmp(&right.intent_seq))
    } else {
        left.effective_at
            .cmp(&right.effective_at)
            .then(left.intent_seq.cmp(&right.intent_seq))
    }
}

fn order_type_priority(order_type: OrderType) -> u8 {
    match order_type {
        OrderType::Stop => 0,
        OrderType::Market => 1,
        OrderType::Limit => 2,
    }
}

fn require_flat_position(signed_quantity: i128) -> Result<(), EngineError> {
    if signed_quantity != 0 {
        return Err(EngineError::new(
            "crypto open requires the prior position to be flat",
        ));
    }
    Ok(())
}

fn require_one_x_capacity(wallet: i128, notional: i128, fee: i128) -> Result<(), EngineError> {
    if checked_add(notional, fee, "one x capacity")? > wallet {
        return Err(EngineError::new("crypto open exceeds the 1x notional cap"));
    }
    Ok(())
}

fn perp_unrealized_pnl(
    signed_quantity: i128,
    entry_price: Option<i128>,
    mark_price: i128,
) -> Result<i128, EngineError> {
    if signed_quantity == 0 {
        return Ok(0);
    }
    let entry = entry_price.unwrap();
    if signed_quantity > 0 {
        checked_mul(
            checked_sub(mark_price, entry, "long unrealized price")?,
            signed_quantity,
            "long unrealized pnl",
        )
    } else {
        checked_mul(
            checked_sub(entry, mark_price, "short unrealized price")?,
            signed_quantity
                .checked_abs()
                .ok_or_else(|| EngineError::new("short position overflow"))?,
            "short unrealized pnl",
        )
    }
}

fn eligible_lot_quantity(lots: &[LongLot], session_seq: u64) -> Result<i128, EngineError> {
    lots.iter()
        .filter(|lot| lot.acquired_session_seq < session_seq)
        .try_fold(0_i128, |total, lot| {
            checked_add(total, lot.quantity, "eligible quantity")
        })
}

fn consume_eligible_lots(
    lots: &mut Vec<LongLot>,
    quantity: i128,
    session_seq: u64,
) -> Result<(), EngineError> {
    let eligible = lots
        .iter()
        .filter(|lot| lot.acquired_session_seq < session_seq)
        .try_fold(0_i128, |total, lot| {
            checked_add(total, lot.quantity, "eligible sell quantity")
        })?;
    if eligible < quantity {
        return Err(EngineError::new("T+1 eligible quantity is insufficient"));
    }
    let mut remaining = quantity;
    for lot in lots
        .iter_mut()
        .filter(|lot| lot.acquired_session_seq < session_seq)
    {
        let consumed = lot.quantity.min(remaining);
        lot.quantity -= consumed;
        remaining -= consumed;
        if remaining == 0 {
            break;
        }
    }
    lots.retain(|lot| lot.quantity != 0);
    Ok(())
}

fn rate_charge(notional: i128, rate: i128, scale: i128) -> Result<i128, EngineError> {
    let numerator = checked_mul(notional, rate, "rate charge numerator")?;
    if numerator == 0 {
        return Ok(0);
    }
    let rounded = checked_add(numerator, scale - 1, "rate charge rounding")?;
    checked_div(rounded, scale, "rate charge")
}

fn signed_rate_charge(notional: i128, rate: i128, scale: i128) -> Result<i128, EngineError> {
    let magnitude = rate_charge(
        notional,
        rate.checked_abs()
            .ok_or_else(|| EngineError::new("signed rate overflow"))?,
        scale,
    )?;
    if rate < 0 {
        checked_sub(0, magnitude, "negative rate charge")
    } else {
        Ok(magnitude)
    }
}

fn checked_add(left: i128, right: i128, label: &str) -> Result<i128, EngineError> {
    left.checked_add(right)
        .ok_or_else(|| EngineError::new(format!("{label} overflow")))
}

fn checked_sub(left: i128, right: i128, label: &str) -> Result<i128, EngineError> {
    left.checked_sub(right)
        .ok_or_else(|| EngineError::new(format!("{label} overflow")))
}

fn checked_mul(left: i128, right: i128, label: &str) -> Result<i128, EngineError> {
    left.checked_mul(right)
        .ok_or_else(|| EngineError::new(format!("{label} overflow")))
}

fn checked_div(left: i128, right: i128, label: &str) -> Result<i128, EngineError> {
    left.checked_div(right)
        .ok_or_else(|| EngineError::new(format!("{label} division failed")))
}

#[cfg(feature = "python")]
#[pyo3::pymodule]
mod oqs_quant_engine {
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;
    use pyo3::types::PyBytes;

    #[pyfunction]
    fn run_engine_v1<'python>(
        python: Python<'python>,
        input: &[u8],
    ) -> PyResult<Bound<'python, PyBytes>> {
        let output = super::run_engine_v1(input)
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        Ok(PyBytes::new(python, &output))
    }
}
