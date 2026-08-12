use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::fmt::{Display, Formatter};

use serde::{Deserialize, Deserializer, Serialize, Serializer};
use serde_json::Value;
use sha2::{Digest, Sha256};

mod portfolio_v2;

pub use portfolio_v2::{
    finalize_engine_checkpoint_v2, run_engine_v2, start_engine_checkpoint_v2,
    step_engine_checkpoint_v2,
};

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

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct EngineInputV1 {
    schema_version: u32,
    account: AccountSpec,
    bars: Vec<Bar>,
    funding_events: Vec<FundingEvent>,
    intents: Vec<OrderIntent>,
}

#[derive(Clone, Deserialize, Serialize)]
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

#[derive(Clone, Deserialize, Serialize)]
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

#[derive(Clone, Copy, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
enum EventPhase {
    Open,
    Intrabar,
    Close,
}

#[derive(Clone, Copy, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(deny_unknown_fields)]
struct EventKey {
    session_seq: u64,
    phase: EventPhase,
    stable_seq: u64,
}

#[derive(Clone, Deserialize, Serialize)]
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

#[derive(Clone, Deserialize, Serialize)]
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

#[derive(Clone, Deserialize, Serialize)]
struct EngineOutputV1 {
    schema_version: u32,
    engine_version: String,
    account_model: String,
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

#[derive(Clone, Deserialize, Serialize)]
struct OrderRecord {
    intent_id: String,
    intent_seq: u64,
    status: String,
    side: Side,
    position_effect: PositionEffect,
    order_type: OrderType,
    quantity: Atom,
    filled_session_seq: Option<u64>,
    filled_phase: Option<String>,
}

#[derive(Clone, Deserialize, Serialize)]
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
    liquidity: String,
}

#[derive(Clone, Deserialize, Serialize)]
struct PositionRecord {
    intent_id: String,
    session_seq: u64,
    signed_quantity: Atom,
    eligible_quantity: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
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

#[derive(Clone, Deserialize, Serialize)]
struct FundingRecord {
    event_id: String,
    session_seq: u64,
    signed_quantity: Atom,
    rate_atoms: Atom,
    mark_price_atoms: Atom,
    wallet_delta_atoms: Atom,
    resulting_wallet_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
struct EquityPoint {
    session_seq: u64,
    timestamp: String,
    mark_price_atoms: Atom,
    cash_atoms: Atom,
    signed_quantity: Atom,
    equity_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
struct DrawdownPoint {
    session_seq: u64,
    equity_atoms: Atom,
    peak_equity_atoms: Atom,
    drawdown_atoms: Atom,
    drawdown_rate_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
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

#[derive(Clone, Deserialize, Serialize)]
struct CostSummary {
    commission_atoms: Atom,
    stamp_duty_atoms: Atom,
    funding_atoms: Atom,
    slippage_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
struct Assumptions {
    fill_model: String,
    partial_fills: bool,
    liquidate_on_end: bool,
    research_short: bool,
    research_short_notice: Option<String>,
    one_x_notional: bool,
}

#[derive(Clone, Deserialize, Serialize)]
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

#[derive(Clone, Deserialize, Eq, PartialEq, Serialize)]
struct LotCheckpointV1 {
    quantity_atoms: Atom,
    acquired_session_seq: u64,
}

#[derive(Clone, Deserialize, Serialize)]
struct CheckpointStateV1 {
    cash_atoms: Atom,
    wallet_atoms: Atom,
    signed_quantity: Atom,
    entry_price_atoms: Option<Atom>,
    long_lots: Vec<LotCheckpointV1>,
    short_lots: Vec<LotCheckpointV1>,
    filled_oco_groups: BTreeSet<String>,
    completed_intents: BTreeSet<String>,
    orders: Vec<OrderRecord>,
    trades: Vec<TradeRecord>,
    positions: Vec<PositionRecord>,
    cash_ledger: Vec<CashRecord>,
    funding_ledger: Vec<FundingRecord>,
    equity_curve: Vec<EquityPoint>,
    drawdown_curve: Vec<DrawdownPoint>,
    peak_equity_atoms: Atom,
    max_drawdown_atoms: Atom,
    max_drawdown_rate_atoms: Atom,
    total_fees_atoms: Atom,
    total_stamp_duty_atoms: Atom,
    total_funding_atoms: Atom,
    total_slippage_atoms: Atom,
    closed_trade_count: u64,
}

struct ExecutionState {
    cash: i128,
    wallet: i128,
    signed_quantity: i128,
    entry_price: Option<i128>,
    lots: Vec<LongLot>,
    short_lots: Vec<LongLot>,
    orders: Vec<OrderRecord>,
    trades: Vec<TradeRecord>,
    positions: Vec<PositionRecord>,
    cash_ledger: Vec<CashRecord>,
    funding_ledger: Vec<FundingRecord>,
    equity_curve: Vec<EquityPoint>,
    drawdown_curve: Vec<DrawdownPoint>,
    peak_equity: i128,
    max_drawdown: i128,
    max_drawdown_rate: i128,
    total_fees: i128,
    total_stamp_duty: i128,
    total_funding: i128,
    total_slippage: i128,
    closed_trade_count: u64,
    filled_oco_groups: BTreeSet<String>,
    completed_intents: BTreeSet<String>,
}

impl ExecutionState {
    fn new(account: &AccountSpec) -> Self {
        Self {
            cash: account.starting_balance_atoms.0,
            wallet: account.starting_balance_atoms.0,
            signed_quantity: 0,
            entry_price: None,
            lots: Vec::new(),
            short_lots: Vec::new(),
            orders: Vec::new(),
            trades: Vec::new(),
            positions: Vec::new(),
            cash_ledger: Vec::new(),
            funding_ledger: Vec::new(),
            equity_curve: Vec::new(),
            drawdown_curve: Vec::new(),
            peak_equity: account.starting_balance_atoms.0,
            max_drawdown: 0,
            max_drawdown_rate: 0,
            total_fees: 0,
            total_stamp_duty: 0,
            total_funding: 0,
            total_slippage: 0,
            closed_trade_count: 0,
            filled_oco_groups: BTreeSet::new(),
            completed_intents: BTreeSet::new(),
        }
    }

    fn from_checkpoint(state: CheckpointStateV1) -> Result<Self, EngineError> {
        let long_lots = state
            .long_lots
            .into_iter()
            .map(|lot| LongLot {
                quantity: lot.quantity_atoms.0,
                acquired_session_seq: lot.acquired_session_seq,
            })
            .collect();
        let short_lots = state
            .short_lots
            .into_iter()
            .map(|lot| LongLot {
                quantity: lot.quantity_atoms.0,
                acquired_session_seq: lot.acquired_session_seq,
            })
            .collect();
        Ok(Self {
            cash: state.cash_atoms.0,
            wallet: state.wallet_atoms.0,
            signed_quantity: state.signed_quantity.0,
            entry_price: state.entry_price_atoms.map(|value| value.0),
            lots: long_lots,
            short_lots,
            orders: state.orders,
            trades: state.trades,
            positions: state.positions,
            cash_ledger: state.cash_ledger,
            funding_ledger: state.funding_ledger,
            equity_curve: state.equity_curve,
            drawdown_curve: state.drawdown_curve,
            peak_equity: state.peak_equity_atoms.0,
            max_drawdown: state.max_drawdown_atoms.0,
            max_drawdown_rate: state.max_drawdown_rate_atoms.0,
            total_fees: state.total_fees_atoms.0,
            total_stamp_duty: state.total_stamp_duty_atoms.0,
            total_funding: state.total_funding_atoms.0,
            total_slippage: state.total_slippage_atoms.0,
            closed_trade_count: state.closed_trade_count,
            filled_oco_groups: state.filled_oco_groups,
            completed_intents: state.completed_intents,
        })
    }

    fn checkpoint(&self) -> CheckpointStateV1 {
        let encode_lots = |lots: &[LongLot]| {
            lots.iter()
                .map(|lot| LotCheckpointV1 {
                    quantity_atoms: Atom(lot.quantity),
                    acquired_session_seq: lot.acquired_session_seq,
                })
                .collect()
        };
        CheckpointStateV1 {
            cash_atoms: Atom(self.cash),
            wallet_atoms: Atom(self.wallet),
            signed_quantity: Atom(self.signed_quantity),
            entry_price_atoms: self.entry_price.map(Atom),
            long_lots: encode_lots(&self.lots),
            short_lots: encode_lots(&self.short_lots),
            filled_oco_groups: self.filled_oco_groups.clone(),
            completed_intents: self.completed_intents.clone(),
            orders: self.orders.clone(),
            trades: self.trades.clone(),
            positions: self.positions.clone(),
            cash_ledger: self.cash_ledger.clone(),
            funding_ledger: self.funding_ledger.clone(),
            equity_curve: self.equity_curve.clone(),
            drawdown_curve: self.drawdown_curve.clone(),
            peak_equity_atoms: Atom(self.peak_equity),
            max_drawdown_atoms: Atom(self.max_drawdown),
            max_drawdown_rate_atoms: Atom(self.max_drawdown_rate),
            total_fees_atoms: Atom(self.total_fees),
            total_stamp_duty_atoms: Atom(self.total_stamp_duty),
            total_funding_atoms: Atom(self.total_funding),
            total_slippage_atoms: Atom(self.total_slippage),
            closed_trade_count: self.closed_trade_count,
        }
    }
}

impl ExecutionState {
    fn process_a_share_bar(&mut self, input: &EngineInputV1, bar: &Bar) -> Result<(), EngineError> {
        let account = &input.account;
        let mut bar_intents: Vec<&OrderIntent> = input
            .intents
            .iter()
            .filter(|intent| {
                !self.completed_intents.contains(&intent.intent_id)
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
                .is_some_and(|group| self.filled_oco_groups.contains(group))
            {
                self.orders
                    .push(order_record(intent, "cancelled", None, None));
                self.completed_intents.insert(intent.intent_id.clone());
                continue;
            }
            let Some(fill) = fill_decision(account, bar, intent)? else {
                if matches!(intent.time_in_force, TimeInForce::Day) {
                    self.orders
                        .push(order_record(intent, "expired", None, None));
                    self.completed_intents.insert(intent.intent_id.clone());
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
                    if self.signed_quantity < 0 {
                        return Err(EngineError::new(
                            "buy/open cannot cross an existing research short",
                        ));
                    }
                    let debit = checked_add(notional, fee, "buy cash debit")?;
                    self.cash = checked_sub(self.cash, debit, "buy cash")?;
                    self.signed_quantity =
                        checked_add(self.signed_quantity, quantity, "long position quantity")?;
                    self.lots.push(LongLot {
                        quantity,
                        acquired_session_seq: bar.session_seq,
                    });
                    notional_delta = -notional;
                }
                (Side::Sell, PositionEffect::Close) => {
                    if self.signed_quantity <= 0 {
                        return Err(EngineError::new(
                            "sell/close requires an existing long position",
                        ));
                    }
                    consume_eligible_lots(&mut self.lots, quantity, bar.session_seq)?;
                    self.signed_quantity =
                        checked_sub(self.signed_quantity, quantity, "long close quantity")?;
                    let costs = checked_add(fee, stamp_duty, "sell costs")?;
                    self.cash = checked_add(
                        self.cash,
                        checked_sub(notional, costs, "sell proceeds")?,
                        "sell cash",
                    )?;
                    notional_delta = notional;
                    if self.signed_quantity == 0 {
                        self.closed_trade_count += 1;
                    }
                }
                (Side::Sell, PositionEffect::Open) if account.allow_research_short => {
                    if self.signed_quantity > 0 {
                        return Err(EngineError::new(
                            "sell/open cannot cross an existing long position",
                        ));
                    }
                    self.signed_quantity = checked_sub(
                        self.signed_quantity,
                        quantity,
                        "research short position quantity",
                    )?;
                    self.short_lots.push(LongLot {
                        quantity,
                        acquired_session_seq: bar.session_seq,
                    });
                    let costs = checked_add(fee, stamp_duty, "short sale costs")?;
                    self.cash = checked_add(
                        self.cash,
                        checked_sub(notional, costs, "short sale proceeds")?,
                        "short sale cash",
                    )?;
                    notional_delta = notional;
                }
                (Side::Buy, PositionEffect::Close) if account.allow_research_short => {
                    if self.signed_quantity >= 0 {
                        return Err(EngineError::new(
                            "buy/close requires an existing research short",
                        ));
                    }
                    consume_eligible_lots(&mut self.short_lots, quantity, bar.session_seq)?;
                    self.signed_quantity = checked_add(
                        self.signed_quantity,
                        quantity,
                        "research short cover quantity",
                    )?;
                    let debit = checked_add(notional, fee, "cover cash debit")?;
                    self.cash = checked_sub(self.cash, debit, "cover cash")?;
                    notional_delta = -notional;
                    if self.signed_quantity == 0 {
                        self.closed_trade_count += 1;
                    }
                }
                _ => {
                    return Err(EngineError::new(
                        "A-share side and position effect are not enabled by the account model",
                    ));
                }
            }

            self.total_fees = checked_add(self.total_fees, fee, "total fees")?;
            self.total_stamp_duty =
                checked_add(self.total_stamp_duty, stamp_duty, "total stamp duty")?;
            self.total_slippage = checked_add(self.total_slippage, slippage, "total slippage")?;
            let eligible_quantity = if self.signed_quantity >= 0 {
                eligible_lot_quantity(&self.lots, bar.session_seq)?
            } else {
                -eligible_lot_quantity(&self.short_lots, bar.session_seq)?
            };

            self.orders.push(order_record(
                intent,
                "filled",
                Some(bar.session_seq),
                Some(fill.phase),
            ));
            self.trades.push(TradeRecord {
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
                liquidity: fill.liquidity.to_owned(),
            });
            if let Some(group) = &intent.oco_group {
                self.filled_oco_groups.insert(group.clone());
            }
            self.completed_intents.insert(intent.intent_id.clone());
            self.positions.push(PositionRecord {
                intent_id: intent.intent_id.clone(),
                session_seq: bar.session_seq,
                signed_quantity: Atom(self.signed_quantity),
                eligible_quantity: Atom(eligible_quantity),
            });
            self.cash_ledger.push(CashRecord {
                intent_id: intent.intent_id.clone(),
                session_seq: bar.session_seq,
                notional_delta_atoms: Atom(notional_delta),
                fee_delta_atoms: Atom(-fee),
                stamp_duty_delta_atoms: Atom(-stamp_duty),
                realized_pnl_delta_atoms: Atom::ZERO,
                funding_delta_atoms: Atom::ZERO,
                resulting_cash_atoms: Atom(self.cash),
            });
        }

        let marked_position = checked_mul(
            self.signed_quantity,
            bar.close_atoms.0,
            "marked position value",
        )?;
        let equity = checked_add(self.cash, marked_position, "marked equity")?;
        self.peak_equity = self.peak_equity.max(equity);
        let drawdown = checked_sub(equity, self.peak_equity, "drawdown")?;
        let drawdown_rate = checked_div(
            checked_mul(drawdown, account.rate_scale, "drawdown rate numerator")?,
            self.peak_equity,
            "drawdown rate",
        )?;
        self.max_drawdown = self.max_drawdown.min(drawdown);
        self.max_drawdown_rate = self.max_drawdown_rate.min(drawdown_rate);
        self.equity_curve.push(EquityPoint {
            session_seq: bar.session_seq,
            timestamp: bar.timestamp.clone(),
            mark_price_atoms: bar.close_atoms,
            cash_atoms: Atom(self.cash),
            signed_quantity: Atom(self.signed_quantity),
            equity_atoms: Atom(equity),
        });
        self.drawdown_curve.push(DrawdownPoint {
            session_seq: bar.session_seq,
            equity_atoms: Atom(equity),
            peak_equity_atoms: Atom(self.peak_equity),
            drawdown_atoms: Atom(drawdown),
            drawdown_rate_atoms: Atom(drawdown_rate),
        });
        self.wallet = self.cash;
        Ok(())
    }

    fn process_crypto_bar(&mut self, input: &EngineInputV1, bar: &Bar) -> Result<(), EngineError> {
        let account = &input.account;
        let mut bar_intents: Vec<&OrderIntent> = input
            .intents
            .iter()
            .filter(|intent| {
                !self.completed_intents.contains(&intent.intent_id)
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
                .is_some_and(|group| self.filled_oco_groups.contains(group))
            {
                self.orders
                    .push(order_record(intent, "cancelled", None, None));
                self.completed_intents.insert(intent.intent_id.clone());
                continue;
            }
            let Some(fill) = fill_decision(account, bar, intent)? else {
                if matches!(intent.time_in_force, TimeInForce::Day) {
                    self.orders
                        .push(order_record(intent, "expired", None, None));
                    self.completed_intents.insert(intent.intent_id.clone());
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
                    require_flat_position(self.signed_quantity)?;
                    require_one_x_capacity(self.wallet, notional, fee)?;
                    self.signed_quantity = quantity;
                    self.entry_price = Some(fill.price);
                }
                (Side::Sell, PositionEffect::Close) => {
                    if self.signed_quantity != quantity {
                        return Err(EngineError::new(
                            "sell/close must exactly close the active long position",
                        ));
                    }
                    realized_pnl = checked_mul(
                        checked_sub(fill.price, self.entry_price.unwrap(), "long price pnl")?,
                        quantity,
                        "long realized pnl",
                    )?;
                    self.signed_quantity = 0;
                    self.entry_price = None;
                    self.closed_trade_count += 1;
                }
                (Side::Sell, PositionEffect::Open) => {
                    require_flat_position(self.signed_quantity)?;
                    require_one_x_capacity(self.wallet, notional, fee)?;
                    self.signed_quantity = -quantity;
                    self.entry_price = Some(fill.price);
                }
                (Side::Buy, PositionEffect::Close) => {
                    if self.signed_quantity != -quantity {
                        return Err(EngineError::new(
                            "buy/close must exactly close the active short position",
                        ));
                    }
                    realized_pnl = checked_mul(
                        checked_sub(self.entry_price.unwrap(), fill.price, "short price pnl")?,
                        quantity,
                        "short realized pnl",
                    )?;
                    self.signed_quantity = 0;
                    self.entry_price = None;
                    self.closed_trade_count += 1;
                }
            }
            self.wallet = checked_add(self.wallet, realized_pnl, "wallet realized pnl")?;
            self.wallet = checked_sub(self.wallet, fee, "wallet fee")?;
            self.cash = self.wallet;
            self.total_fees = checked_add(self.total_fees, fee, "total perp fees")?;
            self.total_slippage =
                checked_add(self.total_slippage, slippage, "total perp slippage")?;

            self.orders.push(order_record(
                intent,
                "filled",
                Some(bar.session_seq),
                Some(fill.phase),
            ));
            self.trades.push(TradeRecord {
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
                liquidity: fill.liquidity.to_owned(),
            });
            self.positions.push(PositionRecord {
                intent_id: intent.intent_id.clone(),
                session_seq: bar.session_seq,
                signed_quantity: Atom(self.signed_quantity),
                eligible_quantity: Atom::ZERO,
            });
            self.cash_ledger.push(CashRecord {
                intent_id: intent.intent_id.clone(),
                session_seq: bar.session_seq,
                notional_delta_atoms: Atom::ZERO,
                fee_delta_atoms: Atom(-fee),
                stamp_duty_delta_atoms: Atom::ZERO,
                realized_pnl_delta_atoms: Atom(realized_pnl),
                funding_delta_atoms: Atom::ZERO,
                resulting_cash_atoms: Atom(self.wallet),
            });
            if let Some(group) = &intent.oco_group {
                self.filled_oco_groups.insert(group.clone());
            }
            self.completed_intents.insert(intent.intent_id.clone());
        }

        for event in input
            .funding_events
            .iter()
            .filter(|event| event.session_seq == bar.session_seq)
        {
            let funding_cost = if self.signed_quantity == 0 {
                0
            } else {
                let notional = checked_mul(
                    self.signed_quantity
                        .checked_abs()
                        .ok_or_else(|| EngineError::new("perp funding position overflow"))?,
                    event.mark_price_atoms.0,
                    "funding notional",
                )?;
                let signed_rate =
                    signed_rate_charge(notional, event.rate_atoms.0, account.rate_scale)?;
                if self.signed_quantity > 0 {
                    signed_rate
                } else {
                    checked_sub(0, signed_rate, "short funding direction")?
                }
            };
            let wallet_delta = checked_sub(0, funding_cost, "funding wallet delta")?;
            self.wallet = checked_add(self.wallet, wallet_delta, "funding wallet")?;
            self.cash = self.wallet;
            self.total_funding = checked_add(self.total_funding, funding_cost, "total funding")?;
            self.cash_ledger.push(CashRecord {
                intent_id: format!("funding:{}", event.event_id),
                session_seq: event.session_seq,
                notional_delta_atoms: Atom::ZERO,
                fee_delta_atoms: Atom::ZERO,
                stamp_duty_delta_atoms: Atom::ZERO,
                realized_pnl_delta_atoms: Atom::ZERO,
                funding_delta_atoms: Atom(wallet_delta),
                resulting_cash_atoms: Atom(self.wallet),
            });
            self.funding_ledger.push(FundingRecord {
                event_id: event.event_id.clone(),
                session_seq: event.session_seq,
                signed_quantity: Atom(self.signed_quantity),
                rate_atoms: event.rate_atoms,
                mark_price_atoms: event.mark_price_atoms,
                wallet_delta_atoms: Atom(wallet_delta),
                resulting_wallet_atoms: Atom(self.wallet),
            });
        }

        let unrealized_pnl =
            perp_unrealized_pnl(self.signed_quantity, self.entry_price, bar.close_atoms.0)?;
        let equity = checked_add(self.wallet, unrealized_pnl, "perp marked equity")?;
        self.peak_equity = self.peak_equity.max(equity);
        let drawdown = checked_sub(equity, self.peak_equity, "perp drawdown")?;
        let drawdown_rate = checked_div(
            checked_mul(drawdown, account.rate_scale, "perp drawdown numerator")?,
            self.peak_equity,
            "perp drawdown rate",
        )?;
        self.max_drawdown = self.max_drawdown.min(drawdown);
        self.max_drawdown_rate = self.max_drawdown_rate.min(drawdown_rate);
        self.equity_curve.push(EquityPoint {
            session_seq: bar.session_seq,
            timestamp: bar.timestamp.clone(),
            mark_price_atoms: bar.close_atoms,
            cash_atoms: Atom(self.wallet),
            signed_quantity: Atom(self.signed_quantity),
            equity_atoms: Atom(equity),
        });
        self.drawdown_curve.push(DrawdownPoint {
            session_seq: bar.session_seq,
            equity_atoms: Atom(equity),
            peak_equity_atoms: Atom(self.peak_equity),
            drawdown_atoms: Atom(drawdown),
            drawdown_rate_atoms: Atom(drawdown_rate),
        });
        Ok(())
    }
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

const CHECKPOINT_SCHEMA_VERSION: u32 = 1;
const OUTPUT_SCHEMA_VERSION: u32 = 1;

fn checkpoint_error(code: &str) -> EngineError {
    EngineError::new(format!("[checkpoint_v1:{code}]"))
}

fn checkpoint_error_detail(code: &str, detail: impl Display) -> EngineError {
    EngineError::new(format!("[checkpoint_v1:{code}] {detail}"))
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn validate_calculation_context(context: &str) -> Result<(), EngineError> {
    if context.len() != 64
        || !context
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(checkpoint_error("invalid_context_hash"));
    }
    Ok(())
}

fn parse_checkpoint_input(input_bytes: &[u8]) -> Result<EngineInputV1, EngineError> {
    let input: EngineInputV1 = serde_json::from_slice(input_bytes)
        .map_err(|error| checkpoint_error_detail("invalid_checkpoint", error))?;
    if input.schema_version != 1 {
        return Err(checkpoint_error("unsupported_schema"));
    }
    match input.account.model.as_str() {
        "a_share_cash" => validate_a_share_input(&input),
        "crypto_linear_perp" => validate_crypto_input(&input),
        _ => Err(checkpoint_error("invalid_checkpoint")),
    }
    .map(|()| input)
    .map_err(|error| {
        if error.to_string().starts_with("[checkpoint_v1:") {
            error
        } else {
            checkpoint_error_detail("invalid_checkpoint", error)
        }
    })
}

fn checkpoint_prefix_sha256(input: &EngineInputV1, cursor: usize) -> Result<String, EngineError> {
    let bars = input
        .bars
        .get(..cursor)
        .ok_or_else(|| checkpoint_error("cursor_out_of_range"))?;
    let bytes = serde_json::to_vec(bars)
        .map_err(|error| checkpoint_error_detail("state_inconsistent", error))?;
    Ok(sha256_hex(&bytes))
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct CheckpointAuthoritativeV1 {
    checkpoint_schema_version: u32,
    engine_version: String,
    input_schema_version: u32,
    output_schema_version: u32,
    account_model: String,
    calculation_context_sha256: String,
    input_sha256: String,
    processed_prefix_sha256: String,
    total_bar_count: usize,
    next_unprocessed_bar_index: usize,
    batch_bar_count: usize,
    status: String,
    state_sha256: String,
    state: CheckpointStateV1,
}

fn authoritative_checkpoint_state_hash(
    batch_bar_count: usize,
    next_unprocessed_bar_index: usize,
    state: &CheckpointStateV1,
) -> Result<String, EngineError> {
    // This public digest protects the serialized state structure. Python/domain integration owns
    // the external CAS identity for the persisted checkpoint; Rust intentionally does not add a
    // secret or MAC here.
    // Convert through serde_json::Value so object keys use the same canonical ordering that an
    // external CAS verifier receives after decoding the public checkpoint bytes.
    let state_value = serde_json::to_value(state)
        .map_err(|error| checkpoint_error_detail("state_inconsistent", error))?;
    let bytes = serde_json::to_vec(&(batch_bar_count, next_unprocessed_bar_index, state_value))
        .map_err(|error| checkpoint_error_detail("state_inconsistent", error))?;
    Ok(sha256_hex(&bytes))
}

fn authoritative_make_checkpoint(
    input: &EngineInputV1,
    input_bytes: &[u8],
    context: &str,
    batch_bar_count: usize,
    cursor: usize,
    state: &ExecutionState,
) -> Result<Vec<u8>, EngineError> {
    let state = state.checkpoint();
    let state_sha256 = authoritative_checkpoint_state_hash(batch_bar_count, cursor, &state)?;
    let checkpoint = CheckpointAuthoritativeV1 {
        checkpoint_schema_version: CHECKPOINT_SCHEMA_VERSION,
        engine_version: ENGINE_VERSION.to_owned(),
        input_schema_version: input.schema_version,
        output_schema_version: OUTPUT_SCHEMA_VERSION,
        account_model: input.account.model.clone(),
        calculation_context_sha256: context.to_owned(),
        input_sha256: sha256_hex(input_bytes),
        processed_prefix_sha256: checkpoint_prefix_sha256(input, cursor)?,
        total_bar_count: input.bars.len(),
        next_unprocessed_bar_index: cursor,
        batch_bar_count,
        status: if cursor == input.bars.len() {
            "complete".to_owned()
        } else {
            "running".to_owned()
        },
        state_sha256,
        state,
    };
    serde_json::to_vec(&checkpoint)
        .map_err(|error| checkpoint_error_detail("state_inconsistent", error))
}

trait HasSessionSeq {
    fn session_seq(&self) -> u64;
}

impl HasSessionSeq for TradeRecord {
    fn session_seq(&self) -> u64 {
        self.session_seq
    }
}

impl HasSessionSeq for PositionRecord {
    fn session_seq(&self) -> u64 {
        self.session_seq
    }
}

impl HasSessionSeq for CashRecord {
    fn session_seq(&self) -> u64 {
        self.session_seq
    }
}

impl HasSessionSeq for FundingRecord {
    fn session_seq(&self) -> u64 {
        self.session_seq
    }
}

impl HasSessionSeq for EquityPoint {
    fn session_seq(&self) -> u64 {
        self.session_seq
    }
}

impl HasSessionSeq for DrawdownPoint {
    fn session_seq(&self) -> u64 {
        self.session_seq
    }
}

fn validate_record_sessions<T: HasSessionSeq>(
    records: &[T],
    max_session: Option<u64>,
) -> Result<(), EngineError> {
    for record in records {
        if let Some(max) = max_session
            && record.session_seq() <= max
        {
            continue;
        }
        return Err(checkpoint_error("state_inconsistent"));
    }
    Ok(())
}

fn validate_record_order<T: HasSessionSeq>(records: &[T]) -> Result<(), EngineError> {
    for pair in records.windows(2) {
        if pair[0].session_seq() > pair[1].session_seq() {
            return Err(checkpoint_error("state_inconsistent"));
        }
    }
    Ok(())
}

fn validate_curve_semantics(
    input: &EngineInputV1,
    bars: &[Bar],
    state: &CheckpointStateV1,
) -> Result<(), EngineError> {
    let starting_balance = input.account.starting_balance_atoms.0;
    let mut signed_quantity = 0_i128;
    let mut cash = starting_balance;
    let mut entry_price = None;
    let mut peak_equity = starting_balance;
    let mut position_index = 0;
    let mut cash_index = 0;
    let mut trade_index = 0;

    for (index, bar) in bars.iter().enumerate() {
        while position_index < state.positions.len()
            && state.positions[position_index].session_seq <= bar.session_seq
        {
            signed_quantity = state.positions[position_index].signed_quantity.0;
            position_index += 1;
        }
        while cash_index < state.cash_ledger.len()
            && state.cash_ledger[cash_index].session_seq <= bar.session_seq
        {
            cash = state.cash_ledger[cash_index].resulting_cash_atoms.0;
            cash_index += 1;
        }
        while trade_index < state.trades.len()
            && state.trades[trade_index].session_seq <= bar.session_seq
        {
            let trade = &state.trades[trade_index];
            match trade.position_effect {
                PositionEffect::Open => entry_price = Some(trade.fill_price_atoms.0),
                PositionEffect::Close => entry_price = None,
            }
            trade_index += 1;
        }

        let point = state
            .equity_curve
            .get(index)
            .ok_or_else(|| checkpoint_error("state_inconsistent"))?;
        if point.session_seq != bar.session_seq
            || point.timestamp != bar.timestamp
            || point.mark_price_atoms != bar.close_atoms
            || point.signed_quantity.0 != signed_quantity
            || point.cash_atoms.0 != cash
        {
            return Err(checkpoint_error("state_inconsistent"));
        }

        let unrealized_pnl = if input.account.model == "crypto_linear_perp" {
            perp_unrealized_pnl(signed_quantity, entry_price, bar.close_atoms.0)
                .map_err(|_| checkpoint_error("state_inconsistent"))?
        } else {
            checked_mul(
                signed_quantity,
                bar.close_atoms.0,
                "checkpoint marked position",
            )
            .map_err(|_| checkpoint_error("state_inconsistent"))?
        };
        let expected_equity = checked_add(cash, unrealized_pnl, "checkpoint marked equity")
            .map_err(|_| checkpoint_error("state_inconsistent"))?;
        peak_equity = peak_equity.max(expected_equity);
        let expected_drawdown = checked_sub(expected_equity, peak_equity, "checkpoint drawdown")
            .map_err(|_| checkpoint_error("state_inconsistent"))?;
        let expected_drawdown_rate = checked_div(
            checked_mul(
                expected_drawdown,
                input.account.rate_scale,
                "checkpoint drawdown numerator",
            )
            .map_err(|_| checkpoint_error("state_inconsistent"))?,
            peak_equity,
            "checkpoint drawdown rate",
        )
        .map_err(|_| checkpoint_error("state_inconsistent"))?;
        let drawdown = state
            .drawdown_curve
            .get(index)
            .ok_or_else(|| checkpoint_error("state_inconsistent"))?;
        if point.equity_atoms.0 != expected_equity
            || drawdown.session_seq != bar.session_seq
            || drawdown.equity_atoms.0 != expected_equity
            || drawdown.peak_equity_atoms.0 != peak_equity
            || drawdown.drawdown_atoms.0 != expected_drawdown
            || drawdown.drawdown_rate_atoms.0 != expected_drawdown_rate
        {
            return Err(checkpoint_error("state_inconsistent"));
        }
    }
    Ok(())
}

fn validate_trade_semantics(
    input: &EngineInputV1,
    bars: &[Bar],
    state: &CheckpointStateV1,
) -> Result<(), EngineError> {
    if state.positions.len() != state.trades.len() {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let account = &input.account;
    let bars_by_session = bars
        .iter()
        .map(|bar| (bar.session_seq, bar))
        .collect::<BTreeMap<_, _>>();
    let intents_by_id = input
        .intents
        .iter()
        .map(|intent| (intent.intent_id.as_str(), intent))
        .collect::<BTreeMap<_, _>>();
    for pair in state.trades.windows(2) {
        if pair[0].session_seq == pair[1].session_seq {
            let left = intents_by_id
                .get(pair[0].intent_id.as_str())
                .copied()
                .ok_or_else(|| checkpoint_error("state_inconsistent"))?;
            let right = intents_by_id
                .get(pair[1].intent_id.as_str())
                .copied()
                .ok_or_else(|| checkpoint_error("state_inconsistent"))?;
            if intent_execution_order(left, right) == std::cmp::Ordering::Greater {
                return Err(checkpoint_error("state_inconsistent"));
            }
        }
    }
    let mut seen_intents = BTreeSet::new();
    let mut signed_quantity = 0_i128;
    let mut long_lots = Vec::new();
    let mut short_lots = Vec::new();
    let mut entry_price = None;

    for (index, trade) in state.trades.iter().enumerate() {
        if !seen_intents.insert(trade.intent_id.clone())
            || trade.trade_id != format!("fill:{}", trade.intent_id)
        {
            return Err(checkpoint_error("state_inconsistent"));
        }
        let intent = intents_by_id
            .get(trade.intent_id.as_str())
            .copied()
            .ok_or_else(|| checkpoint_error("state_inconsistent"))?;
        let bar = bars_by_session
            .get(&trade.session_seq)
            .copied()
            .ok_or_else(|| checkpoint_error("state_inconsistent"))?;
        if trade.session_seq < intent.effective_at.session_seq
            || (matches!(intent.time_in_force, TimeInForce::Day)
                && trade.session_seq != intent.effective_at.session_seq)
        {
            return Err(checkpoint_error("state_inconsistent"));
        }
        let fill = fill_decision(account, bar, intent)
            .map_err(|_| checkpoint_error("state_inconsistent"))?
            .ok_or_else(|| checkpoint_error("state_inconsistent"))?;
        let notional = checked_mul(fill.price, intent.quantity.0, "checkpoint trade notional")
            .map_err(|_| checkpoint_error("state_inconsistent"))?;
        let slippage = checked_mul(
            fill.slippage_per_unit_atoms,
            intent.quantity.0,
            "checkpoint trade slippage",
        )
        .map_err(|_| checkpoint_error("state_inconsistent"))?;
        let fee_rate = if account.model == "a_share_cash" {
            account.commission_rate_atoms.0
        } else if fill.liquidity == "maker" {
            account.maker_fee_rate_atoms.0
        } else {
            account.taker_fee_rate_atoms.0
        };
        let fee = rate_charge(notional, fee_rate, account.rate_scale)
            .map_err(|_| checkpoint_error("state_inconsistent"))?;
        let stamp_duty = if account.model == "a_share_cash" && matches!(intent.side, Side::Sell) {
            rate_charge(
                notional,
                account.stamp_duty_rate_atoms.0,
                account.rate_scale,
            )
            .map_err(|_| checkpoint_error("state_inconsistent"))?
        } else {
            0
        };
        if trade.intent_id != intent.intent_id
            || trade.session_seq != bar.session_seq
            || trade.side as u8 != intent.side as u8
            || trade.position_effect as u8 != intent.position_effect as u8
            || trade.quantity != intent.quantity
            || trade.fill_price_atoms.0 != fill.price
            || trade.notional_atoms.0 != notional
            || trade.fee_atoms.0 != fee
            || trade.stamp_duty_atoms.0 != stamp_duty
            || trade.slippage_atoms.0 != slippage
            || trade.liquidity != fill.liquidity
        {
            return Err(checkpoint_error("state_inconsistent"));
        }

        let eligible_quantity = if account.model == "a_share_cash" {
            match (intent.side, intent.position_effect) {
                (Side::Buy, PositionEffect::Open) => {
                    if signed_quantity < 0 {
                        return Err(checkpoint_error("state_inconsistent"));
                    }
                    signed_quantity = checked_add(
                        signed_quantity,
                        intent.quantity.0,
                        "checkpoint long quantity",
                    )
                    .map_err(|_| checkpoint_error("state_inconsistent"))?;
                    long_lots.push(LongLot {
                        quantity: intent.quantity.0,
                        acquired_session_seq: bar.session_seq,
                    });
                }
                (Side::Sell, PositionEffect::Close) => {
                    if signed_quantity <= 0
                        || consume_eligible_lots(&mut long_lots, intent.quantity.0, bar.session_seq)
                            .is_err()
                    {
                        return Err(checkpoint_error("state_inconsistent"));
                    }
                    signed_quantity = checked_sub(
                        signed_quantity,
                        intent.quantity.0,
                        "checkpoint long close quantity",
                    )
                    .map_err(|_| checkpoint_error("state_inconsistent"))?;
                }
                (Side::Sell, PositionEffect::Open) => {
                    if !account.allow_research_short || signed_quantity > 0 {
                        return Err(checkpoint_error("state_inconsistent"));
                    }
                    signed_quantity = checked_sub(
                        signed_quantity,
                        intent.quantity.0,
                        "checkpoint short quantity",
                    )
                    .map_err(|_| checkpoint_error("state_inconsistent"))?;
                    short_lots.push(LongLot {
                        quantity: intent.quantity.0,
                        acquired_session_seq: bar.session_seq,
                    });
                }
                (Side::Buy, PositionEffect::Close) => {
                    if !account.allow_research_short
                        || signed_quantity >= 0
                        || consume_eligible_lots(
                            &mut short_lots,
                            intent.quantity.0,
                            bar.session_seq,
                        )
                        .is_err()
                    {
                        return Err(checkpoint_error("state_inconsistent"));
                    }
                    signed_quantity = checked_add(
                        signed_quantity,
                        intent.quantity.0,
                        "checkpoint short cover quantity",
                    )
                    .map_err(|_| checkpoint_error("state_inconsistent"))?;
                }
            }
            if signed_quantity >= 0 {
                eligible_lot_quantity(&long_lots, bar.session_seq)
                    .map_err(|_| checkpoint_error("state_inconsistent"))?
            } else {
                -eligible_lot_quantity(&short_lots, bar.session_seq)
                    .map_err(|_| checkpoint_error("state_inconsistent"))?
            }
        } else {
            match (intent.side, intent.position_effect) {
                (Side::Buy, PositionEffect::Open) | (Side::Sell, PositionEffect::Open) => {
                    if signed_quantity != 0 {
                        return Err(checkpoint_error("state_inconsistent"));
                    }
                    signed_quantity = if matches!(intent.side, Side::Buy) {
                        intent.quantity.0
                    } else {
                        -intent.quantity.0
                    };
                    entry_price = Some(fill.price);
                }
                (Side::Sell, PositionEffect::Close) => {
                    if signed_quantity != intent.quantity.0 {
                        return Err(checkpoint_error("state_inconsistent"));
                    }
                    if entry_price.is_none() {
                        return Err(checkpoint_error("state_inconsistent"));
                    }
                    signed_quantity = 0;
                    entry_price = None;
                }
                (Side::Buy, PositionEffect::Close) => {
                    if signed_quantity != -intent.quantity.0 {
                        return Err(checkpoint_error("state_inconsistent"));
                    }
                    if entry_price.is_none() {
                        return Err(checkpoint_error("state_inconsistent"));
                    }
                    signed_quantity = 0;
                    entry_price = None;
                }
            }
            0
        };
        let position = state
            .positions
            .get(index)
            .ok_or_else(|| checkpoint_error("state_inconsistent"))?;
        if position.intent_id != intent.intent_id
            || position.session_seq != bar.session_seq
            || position.signed_quantity.0 != signed_quantity
            || position.eligible_quantity.0 != eligible_quantity
        {
            return Err(checkpoint_error("state_inconsistent"));
        }
    }

    if input.account.model == "crypto_linear_perp" && state.signed_quantity.0 != signed_quantity {
        return Err(checkpoint_error("state_inconsistent"));
    }
    Ok(())
}

fn reconstruct_a_share_lots(
    input: &EngineInputV1,
    bars: &[Bar],
    state: &CheckpointStateV1,
) -> Result<(Vec<LotCheckpointV1>, Vec<LotCheckpointV1>), EngineError> {
    if input.account.model != "a_share_cash" {
        return Ok((Vec::new(), Vec::new()));
    }
    let bars_by_session = bars
        .iter()
        .map(|bar| (bar.session_seq, bar))
        .collect::<BTreeMap<_, _>>();
    let mut signed_quantity = 0_i128;
    let mut long_lots = Vec::new();
    let mut short_lots = Vec::new();
    for trade in &state.trades {
        let quantity = trade.quantity.0;
        if quantity <= 0 {
            return Err(checkpoint_error("state_inconsistent"));
        }
        let bar = bars_by_session
            .get(&trade.session_seq)
            .copied()
            .ok_or_else(|| checkpoint_error("state_inconsistent"))?;
        match (trade.side, trade.position_effect) {
            (Side::Buy, PositionEffect::Open) => {
                if signed_quantity < 0 {
                    return Err(checkpoint_error("state_inconsistent"));
                }
                signed_quantity = checked_add(
                    signed_quantity,
                    quantity,
                    "checkpoint reconstructed long quantity",
                )
                .map_err(|_| checkpoint_error("state_inconsistent"))?;
                long_lots.push(LongLot {
                    quantity,
                    acquired_session_seq: bar.session_seq,
                });
            }
            (Side::Sell, PositionEffect::Close) => {
                if signed_quantity <= 0
                    || consume_eligible_lots(&mut long_lots, quantity, bar.session_seq).is_err()
                {
                    return Err(checkpoint_error("state_inconsistent"));
                }
                signed_quantity = checked_sub(
                    signed_quantity,
                    quantity,
                    "checkpoint reconstructed long close quantity",
                )
                .map_err(|_| checkpoint_error("state_inconsistent"))?;
            }
            (Side::Sell, PositionEffect::Open) => {
                if !input.account.allow_research_short || signed_quantity > 0 {
                    return Err(checkpoint_error("state_inconsistent"));
                }
                signed_quantity = checked_sub(
                    signed_quantity,
                    quantity,
                    "checkpoint reconstructed short quantity",
                )
                .map_err(|_| checkpoint_error("state_inconsistent"))?;
                short_lots.push(LongLot {
                    quantity,
                    acquired_session_seq: bar.session_seq,
                });
            }
            (Side::Buy, PositionEffect::Close) => {
                if !input.account.allow_research_short
                    || signed_quantity >= 0
                    || consume_eligible_lots(&mut short_lots, quantity, bar.session_seq).is_err()
                {
                    return Err(checkpoint_error("state_inconsistent"));
                }
                signed_quantity = checked_add(
                    signed_quantity,
                    quantity,
                    "checkpoint reconstructed short cover quantity",
                )
                .map_err(|_| checkpoint_error("state_inconsistent"))?;
            }
        }
    }
    if signed_quantity != state.signed_quantity.0 {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let encode = |lots: &[LongLot]| {
        lots.iter()
            .map(|lot| LotCheckpointV1 {
                quantity_atoms: Atom(lot.quantity),
                acquired_session_seq: lot.acquired_session_seq,
            })
            .collect()
    };
    Ok((encode(&long_lots), encode(&short_lots)))
}

fn validate_order_semantics(
    input: &EngineInputV1,
    bars: &[Bar],
    state: &CheckpointStateV1,
) -> Result<(), EngineError> {
    let trades_by_intent = state
        .trades
        .iter()
        .map(|trade| (trade.intent_id.as_str(), trade))
        .collect::<BTreeMap<_, _>>();
    if trades_by_intent.len() != state.trades.len() {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let mut expected_orders = Vec::new();
    let mut expected_completed = BTreeSet::new();
    let mut expected_filled_oco_groups = BTreeSet::new();
    let mut seen_trades = BTreeSet::new();

    for bar in bars {
        let mut bar_intents = input
            .intents
            .iter()
            .filter(|intent| {
                !expected_completed.contains(&intent.intent_id)
                    && match intent.time_in_force {
                        TimeInForce::Day => intent.effective_at.session_seq == bar.session_seq,
                        TimeInForce::Gtc => intent.effective_at.session_seq <= bar.session_seq,
                    }
            })
            .collect::<Vec<_>>();
        bar_intents.sort_by(|left, right| intent_execution_order(left, right));

        for intent in bar_intents {
            if intent
                .oco_group
                .as_ref()
                .is_some_and(|group| expected_filled_oco_groups.contains(group))
            {
                expected_orders.push(order_record(intent, "cancelled", None, None));
                expected_completed.insert(intent.intent_id.clone());
                continue;
            }

            let fill = fill_decision(&input.account, bar, intent)
                .map_err(|_| checkpoint_error("state_inconsistent"))?;
            let trade = trades_by_intent.get(intent.intent_id.as_str()).copied();
            match (trade, fill) {
                (Some(trade), Some(fill)) if trade.session_seq == bar.session_seq => {
                    expected_orders.push(order_record(
                        intent,
                        "filled",
                        Some(bar.session_seq),
                        Some(fill.phase),
                    ));
                    expected_completed.insert(intent.intent_id.clone());
                    seen_trades.insert(trade.intent_id.as_str());
                    if let Some(group) = &intent.oco_group {
                        expected_filled_oco_groups.insert(group.clone());
                    }
                }
                (Some(_), Some(_)) => return Err(checkpoint_error("state_inconsistent")),
                (Some(trade), _) if trade.session_seq <= bar.session_seq => {
                    return Err(checkpoint_error("state_inconsistent"));
                }
                (Some(_), None) => {
                    if matches!(intent.time_in_force, TimeInForce::Day) {
                        return Err(checkpoint_error("state_inconsistent"));
                    }
                    return Err(checkpoint_error("state_inconsistent"));
                }
                (None, Some(_)) => return Err(checkpoint_error("state_inconsistent")),
                (None, None) if matches!(intent.time_in_force, TimeInForce::Day) => {
                    expected_orders.push(order_record(intent, "expired", None, None));
                    expected_completed.insert(intent.intent_id.clone());
                }
                (None, None) => {}
            }
        }
    }

    if seen_trades.len() != state.trades.len()
        || serde_json::to_vec(&expected_orders)
            .map_err(|_| checkpoint_error("state_inconsistent"))?
            != serde_json::to_vec(&state.orders)
                .map_err(|_| checkpoint_error("state_inconsistent"))?
        || expected_completed != state.completed_intents
        || expected_filled_oco_groups != state.filled_oco_groups
    {
        return Err(checkpoint_error("state_inconsistent"));
    }
    Ok(())
}

fn reconstruct_ledgers(
    input: &EngineInputV1,
    bars: &[Bar],
    state: &CheckpointStateV1,
) -> Result<(Vec<CashRecord>, Vec<FundingRecord>, i128), EngineError> {
    let mut trades_by_session = BTreeMap::<u64, Vec<&TradeRecord>>::new();
    for trade in &state.trades {
        trades_by_session
            .entry(trade.session_seq)
            .or_default()
            .push(trade);
    }
    let mut expected_cash_ledger = Vec::new();
    let mut expected_funding_ledger = Vec::new();
    let mut cash = input.account.starting_balance_atoms.0;
    let mut signed_quantity = 0_i128;
    let mut entry_price = None;
    let mut total_funding = 0_i128;

    for bar in bars {
        for trade in trades_by_session
            .get(&bar.session_seq)
            .into_iter()
            .flatten()
        {
            let (notional_delta, realized_pnl) = if input.account.model == "a_share_cash" {
                let notional_delta = if matches!(trade.side, Side::Buy) {
                    checked_sub(0, trade.notional_atoms.0, "checkpoint buy notional")?
                } else {
                    trade.notional_atoms.0
                };
                signed_quantity = if matches!(trade.side, Side::Buy) {
                    checked_add(
                        signed_quantity,
                        trade.quantity.0,
                        "checkpoint A-share quantity",
                    )?
                } else {
                    checked_sub(
                        signed_quantity,
                        trade.quantity.0,
                        "checkpoint A-share quantity",
                    )?
                };
                (notional_delta, 0)
            } else {
                let realized_pnl = match (trade.side, trade.position_effect) {
                    (Side::Buy, PositionEffect::Open) => {
                        signed_quantity = trade.quantity.0;
                        entry_price = Some(trade.fill_price_atoms.0);
                        0
                    }
                    (Side::Sell, PositionEffect::Open) => {
                        signed_quantity = -trade.quantity.0;
                        entry_price = Some(trade.fill_price_atoms.0);
                        0
                    }
                    (Side::Sell, PositionEffect::Close) => {
                        let entry =
                            entry_price.ok_or_else(|| checkpoint_error("state_inconsistent"))?;
                        signed_quantity = 0;
                        entry_price = None;
                        checked_mul(
                            checked_sub(
                                trade.fill_price_atoms.0,
                                entry,
                                "checkpoint long realized pnl",
                            )?,
                            trade.quantity.0,
                            "checkpoint long realized pnl",
                        )?
                    }
                    (Side::Buy, PositionEffect::Close) => {
                        let entry =
                            entry_price.ok_or_else(|| checkpoint_error("state_inconsistent"))?;
                        signed_quantity = 0;
                        entry_price = None;
                        checked_mul(
                            checked_sub(
                                entry,
                                trade.fill_price_atoms.0,
                                "checkpoint short realized pnl",
                            )?,
                            trade.quantity.0,
                            "checkpoint short realized pnl",
                        )?
                    }
                };
                (0, realized_pnl)
            };
            let cash_delta = checked_add(
                notional_delta,
                checked_sub(0, trade.fee_atoms.0, "checkpoint trade fee")?,
                "checkpoint trade cash",
            )?;
            let cash_delta = checked_add(
                cash_delta,
                checked_sub(0, trade.stamp_duty_atoms.0, "checkpoint trade stamp duty")?,
                "checkpoint trade cash",
            )?;
            let cash_delta =
                checked_add(cash_delta, realized_pnl, "checkpoint trade realized pnl")?;
            cash = checked_add(cash, cash_delta, "checkpoint trade cash")?;
            expected_cash_ledger.push(CashRecord {
                intent_id: trade.intent_id.clone(),
                session_seq: trade.session_seq,
                notional_delta_atoms: Atom(notional_delta),
                fee_delta_atoms: Atom(-trade.fee_atoms.0),
                stamp_duty_delta_atoms: Atom(-trade.stamp_duty_atoms.0),
                realized_pnl_delta_atoms: Atom(realized_pnl),
                funding_delta_atoms: Atom::ZERO,
                resulting_cash_atoms: Atom(cash),
            });
        }

        for event in input
            .funding_events
            .iter()
            .filter(|event| event.session_seq == bar.session_seq)
        {
            if input.account.model != "crypto_linear_perp" {
                return Err(checkpoint_error("state_inconsistent"));
            }
            let funding_cost = if signed_quantity == 0 {
                0
            } else {
                let notional = checked_mul(
                    signed_quantity
                        .checked_abs()
                        .ok_or_else(|| checkpoint_error("state_inconsistent"))?,
                    event.mark_price_atoms.0,
                    "checkpoint funding notional",
                )?;
                let signed_rate =
                    signed_rate_charge(notional, event.rate_atoms.0, input.account.rate_scale)?;
                if signed_quantity > 0 {
                    signed_rate
                } else {
                    checked_sub(0, signed_rate, "checkpoint short funding direction")?
                }
            };
            let wallet_delta = checked_sub(0, funding_cost, "checkpoint funding wallet delta")?;
            cash = checked_add(cash, wallet_delta, "checkpoint funding cash")?;
            total_funding = checked_add(total_funding, funding_cost, "checkpoint total funding")?;
            expected_cash_ledger.push(CashRecord {
                intent_id: format!("funding:{}", event.event_id),
                session_seq: event.session_seq,
                notional_delta_atoms: Atom::ZERO,
                fee_delta_atoms: Atom::ZERO,
                stamp_duty_delta_atoms: Atom::ZERO,
                realized_pnl_delta_atoms: Atom::ZERO,
                funding_delta_atoms: Atom(wallet_delta),
                resulting_cash_atoms: Atom(cash),
            });
            expected_funding_ledger.push(FundingRecord {
                event_id: event.event_id.clone(),
                session_seq: event.session_seq,
                signed_quantity: Atom(signed_quantity),
                rate_atoms: event.rate_atoms,
                mark_price_atoms: event.mark_price_atoms,
                wallet_delta_atoms: Atom(wallet_delta),
                resulting_wallet_atoms: Atom(cash),
            });
        }
    }
    Ok((expected_cash_ledger, expected_funding_ledger, total_funding))
}

fn validate_authoritative_state(
    input: &EngineInputV1,
    cursor: usize,
    state: &CheckpointStateV1,
) -> Result<(), EngineError> {
    let bars = input
        .bars
        .get(..cursor)
        .ok_or_else(|| checkpoint_error("cursor_out_of_range"))?;
    let max_session = bars.last().map(|bar| bar.session_seq);
    validate_record_sessions(&state.trades, max_session)?;
    validate_record_sessions(&state.positions, max_session)?;
    validate_record_sessions(&state.cash_ledger, max_session)?;
    validate_record_sessions(&state.funding_ledger, max_session)?;
    validate_record_sessions(&state.equity_curve, max_session)?;
    validate_record_sessions(&state.drawdown_curve, max_session)?;
    validate_record_order(&state.trades)?;
    validate_record_order(&state.positions)?;
    validate_record_order(&state.cash_ledger)?;
    validate_record_order(&state.funding_ledger)?;
    validate_record_order(&state.equity_curve)?;
    validate_record_order(&state.drawdown_curve)?;
    if state.equity_curve.len() != cursor || state.drawdown_curve.len() != cursor {
        return Err(checkpoint_error("state_inconsistent"));
    }
    if state.orders.len() < state.trades.len() {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let expected_signed = state
        .positions
        .last()
        .map(|position| position.signed_quantity.0)
        .unwrap_or(0);
    if expected_signed != state.signed_quantity.0 {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let expected_cash = state
        .cash_ledger
        .last()
        .map(|record| record.resulting_cash_atoms.0)
        .unwrap_or(input.account.starting_balance_atoms.0);
    if input.account.model == "a_share_cash" && expected_cash != state.cash_atoms.0 {
        return Err(checkpoint_error("state_inconsistent"));
    }
    if input.account.model == "crypto_linear_perp" && expected_cash != state.wallet_atoms.0 {
        return Err(checkpoint_error("state_inconsistent"));
    }
    if state.cash_atoms != state.wallet_atoms {
        return Err(checkpoint_error("state_inconsistent"));
    }
    validate_trade_semantics(input, bars, state)?;
    let (expected_long_lots, expected_short_lots) = reconstruct_a_share_lots(input, bars, state)?;
    if expected_long_lots != state.long_lots || expected_short_lots != state.short_lots {
        return Err(checkpoint_error("state_inconsistent"));
    }
    validate_order_semantics(input, bars, state)?;
    let (expected_cash_ledger, expected_funding_ledger, expected_total_funding) =
        reconstruct_ledgers(input, bars, state)?;
    if serde_json::to_vec(&expected_cash_ledger)
        .map_err(|_| checkpoint_error("state_inconsistent"))?
        != serde_json::to_vec(&state.cash_ledger)
            .map_err(|_| checkpoint_error("state_inconsistent"))?
        || serde_json::to_vec(&expected_funding_ledger)
            .map_err(|_| checkpoint_error("state_inconsistent"))?
            != serde_json::to_vec(&state.funding_ledger)
                .map_err(|_| checkpoint_error("state_inconsistent"))?
        || expected_total_funding != state.total_funding_atoms.0
    {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let mut reconstructed_cash = input.account.starting_balance_atoms.0;
    for record in &state.cash_ledger {
        let delta = checked_add(
            checked_add(
                checked_add(
                    record.notional_delta_atoms.0,
                    record.fee_delta_atoms.0,
                    "checkpoint cash ledger fee",
                )?,
                record.stamp_duty_delta_atoms.0,
                "checkpoint cash ledger stamp duty",
            )?,
            checked_add(
                record.realized_pnl_delta_atoms.0,
                record.funding_delta_atoms.0,
                "checkpoint cash ledger realized/funding",
            )?,
            "checkpoint cash ledger delta",
        )?;
        reconstructed_cash = checked_add(
            reconstructed_cash,
            delta,
            "checkpoint cash ledger resulting cash",
        )?;
        if record.resulting_cash_atoms.0 != reconstructed_cash {
            return Err(checkpoint_error("state_inconsistent"));
        }
    }
    if reconstructed_cash != state.cash_atoms.0 {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let total_fees = state.trades.iter().try_fold(0_i128, |total, trade| {
        checked_add(total, trade.fee_atoms.0, "checkpoint state fees")
    })?;
    let total_stamp_duty = state.trades.iter().try_fold(0_i128, |total, trade| {
        checked_add(
            total,
            trade.stamp_duty_atoms.0,
            "checkpoint state stamp duty",
        )
    })?;
    let total_slippage = state.trades.iter().try_fold(0_i128, |total, trade| {
        checked_add(total, trade.slippage_atoms.0, "checkpoint state slippage")
    })?;
    let total_funding = state
        .funding_ledger
        .iter()
        .try_fold(0_i128, |total, record| {
            checked_add(
                total,
                -record.wallet_delta_atoms.0,
                "checkpoint state funding",
            )
        })?;
    if total_fees != state.total_fees_atoms.0
        || total_stamp_duty != state.total_stamp_duty_atoms.0
        || total_slippage != state.total_slippage_atoms.0
        || total_funding != state.total_funding_atoms.0
    {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let expected_closed_trade_count = state
        .positions
        .windows(2)
        .filter(|window| window[0].signed_quantity.0 != 0 && window[1].signed_quantity.0 == 0)
        .count() as u64;
    if expected_closed_trade_count != state.closed_trade_count {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let expected_peak = state
        .drawdown_curve
        .last()
        .map(|point| point.peak_equity_atoms)
        .unwrap_or(input.account.starting_balance_atoms);
    let expected_max_drawdown = state
        .drawdown_curve
        .iter()
        .map(|point| point.drawdown_atoms.0)
        .min()
        .unwrap_or(0);
    let expected_max_drawdown_rate = state
        .drawdown_curve
        .iter()
        .map(|point| point.drawdown_rate_atoms.0)
        .min()
        .unwrap_or(0);
    if expected_peak != state.peak_equity_atoms
        || expected_max_drawdown != state.max_drawdown_atoms.0
        || expected_max_drawdown_rate != state.max_drawdown_rate_atoms.0
    {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let mut completed = BTreeSet::new();
    for order in &state.orders {
        completed.insert(order.intent_id.clone());
    }
    if completed.len() != state.orders.len() || completed != state.completed_intents {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let known_intents = input
        .intents
        .iter()
        .map(|intent| intent.intent_id.as_str())
        .collect::<BTreeSet<_>>();
    if state
        .completed_intents
        .iter()
        .any(|intent_id| !known_intents.contains(intent_id.as_str()))
    {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let expected_oco_groups = state
        .trades
        .iter()
        .filter_map(|trade| {
            input
                .intents
                .iter()
                .find(|intent| intent.intent_id == trade.intent_id)
                .and_then(|intent| intent.oco_group.clone())
        })
        .collect::<BTreeSet<_>>();
    if expected_oco_groups != state.filled_oco_groups {
        return Err(checkpoint_error("state_inconsistent"));
    }
    if input.account.model == "crypto_linear_perp" {
        let expected_entry = if state.signed_quantity.0 == 0 {
            None
        } else {
            state
                .trades
                .iter()
                .rev()
                .find(|trade| matches!(trade.position_effect, PositionEffect::Open))
                .map(|trade| trade.fill_price_atoms)
        };
        if state.entry_price_atoms != expected_entry {
            return Err(checkpoint_error("state_inconsistent"));
        }
    } else if state.entry_price_atoms.is_some() {
        return Err(checkpoint_error("state_inconsistent"));
    }
    let expected_long = state.long_lots.iter().try_fold(0_i128, |total, lot| {
        if lot.quantity_atoms.0 <= 0 {
            return Err(checkpoint_error("state_inconsistent"));
        }
        checked_add(total, lot.quantity_atoms.0, "checkpoint long lots")
    })?;
    let expected_short = state.short_lots.iter().try_fold(0_i128, |total, lot| {
        if lot.quantity_atoms.0 <= 0 {
            return Err(checkpoint_error("state_inconsistent"));
        }
        checked_add(total, lot.quantity_atoms.0, "checkpoint short lots")
    })?;
    if input.account.model == "a_share_cash"
        && ((state.signed_quantity.0 >= 0 && expected_long != state.signed_quantity.0)
            || (state.signed_quantity.0 < 0 && expected_short != -state.signed_quantity.0))
    {
        return Err(checkpoint_error("state_inconsistent"));
    }
    validate_curve_semantics(input, bars, state)?;
    Ok(())
}

fn authoritative_decode_checkpoint(
    input_bytes: &[u8],
    context: &str,
    checkpoint_bytes: &[u8],
) -> Result<(EngineInputV1, CheckpointAuthoritativeV1), EngineError> {
    validate_calculation_context(context)?;
    let input = parse_checkpoint_input(input_bytes)?;
    let value: Value = serde_json::from_slice(checkpoint_bytes)
        .map_err(|error| checkpoint_error_detail("invalid_checkpoint", error))?;
    let state_sha256 = value
        .get("state_sha256")
        .and_then(Value::as_str)
        .ok_or_else(|| checkpoint_error("invalid_checkpoint"))?
        .to_owned();
    let checkpoint: CheckpointAuthoritativeV1 = serde_json::from_value(value)
        .map_err(|error| checkpoint_error_detail("invalid_checkpoint", error))?;
    if checkpoint.checkpoint_schema_version != CHECKPOINT_SCHEMA_VERSION
        || checkpoint.input_schema_version != 1
        || checkpoint.output_schema_version != OUTPUT_SCHEMA_VERSION
    {
        return Err(checkpoint_error("unsupported_schema"));
    }
    if checkpoint.engine_version != ENGINE_VERSION {
        return Err(checkpoint_error("engine_version_mismatch"));
    }
    if checkpoint.calculation_context_sha256 != context {
        return Err(checkpoint_error("context_hash_mismatch"));
    }
    if checkpoint.input_sha256 != sha256_hex(input_bytes) {
        return Err(checkpoint_error("input_hash_mismatch"));
    }
    if checkpoint.account_model != input.account.model {
        return Err(checkpoint_error("state_inconsistent"));
    }
    if checkpoint.total_bar_count != input.bars.len() {
        return Err(checkpoint_error("bar_count_mismatch"));
    }
    if checkpoint.batch_bar_count == 0 {
        return Err(checkpoint_error("batch_size_zero"));
    }
    if checkpoint.next_unprocessed_bar_index > checkpoint.total_bar_count {
        return Err(checkpoint_error("cursor_out_of_range"));
    }
    if checkpoint.processed_prefix_sha256
        != checkpoint_prefix_sha256(&input, checkpoint.next_unprocessed_bar_index)?
    {
        return Err(checkpoint_error("input_prefix_mismatch"));
    }
    if state_sha256
        != authoritative_checkpoint_state_hash(
            checkpoint.batch_bar_count,
            checkpoint.next_unprocessed_bar_index,
            &checkpoint.state,
        )?
    {
        return Err(checkpoint_error("state_inconsistent"));
    }
    validate_authoritative_state(
        &input,
        checkpoint.next_unprocessed_bar_index,
        &checkpoint.state,
    )?;
    let expected_status = if checkpoint.next_unprocessed_bar_index == checkpoint.total_bar_count {
        "complete"
    } else {
        "running"
    };
    if checkpoint.status != expected_status {
        return Err(checkpoint_error("state_inconsistent"));
    }
    Ok((input, checkpoint))
}

fn authoritative_finish_a_share(
    mut state: ExecutionState,
    input: &EngineInputV1,
) -> Result<EngineOutputV1, EngineError> {
    for intent in &input.intents {
        if !state.completed_intents.contains(&intent.intent_id) {
            state
                .orders
                .push(order_record(intent, "expired", None, None));
        }
    }
    let account = &input.account;
    let ending_equity = state
        .equity_curve
        .last()
        .map(|point| point.equity_atoms.0)
        .unwrap_or(account.starting_balance_atoms.0);
    let net_pnl = checked_sub(ending_equity, account.starting_balance_atoms.0, "net pnl")?;
    let total_return_rate = checked_div(
        checked_mul(net_pnl, account.rate_scale, "total return numerator")?,
        account.starting_balance_atoms.0,
        "total return",
    )?;
    let fill_count = state.trades.len();
    state.orders.sort_by_key(|order| order.intent_seq);
    Ok(EngineOutputV1 {
        schema_version: 1,
        engine_version: ENGINE_VERSION.to_owned(),
        account_model: "a_share_cash".to_owned(),
        orders: state.orders,
        trades: state.trades,
        positions: state.positions,
        cash_ledger: state.cash_ledger,
        funding_ledger: Vec::new(),
        equity_curve: state.equity_curve,
        drawdown_curve: state.drawdown_curve,
        metrics: Metrics {
            starting_equity_atoms: account.starting_balance_atoms,
            ending_equity_atoms: Atom(ending_equity),
            net_pnl_atoms: Atom(net_pnl),
            total_return_rate_atoms: Atom(total_return_rate),
            max_drawdown_atoms: Atom(state.max_drawdown),
            max_drawdown_rate_atoms: Atom(state.max_drawdown_rate),
            total_fees_atoms: Atom(state.total_fees),
            total_stamp_duty_atoms: Atom(state.total_stamp_duty),
            total_funding_atoms: Atom::ZERO,
            total_slippage_atoms: Atom(state.total_slippage),
            fill_count,
            closed_trade_count: state.closed_trade_count,
            open_position_count: u64::from(state.signed_quantity != 0),
        },
        costs: CostSummary {
            commission_atoms: Atom(state.total_fees),
            stamp_duty_atoms: Atom(state.total_stamp_duty),
            funding_atoms: Atom::ZERO,
            slippage_atoms: Atom(state.total_slippage),
        },
        assumptions: Assumptions {
            fill_model: "ohlc_full_fill_v1".to_owned(),
            partial_fills: false,
            liquidate_on_end: false,
            research_short: account.allow_research_short,
            research_short_notice: account.allow_research_short.then_some(
                "hypothetical research model; not ordinary cash-account trading capability"
                    .to_owned(),
            ),
            one_x_notional: false,
        },
    })
}

fn authoritative_finish_crypto(
    mut state: ExecutionState,
    input: &EngineInputV1,
) -> Result<EngineOutputV1, EngineError> {
    for intent in &input.intents {
        if !state.completed_intents.contains(&intent.intent_id) {
            state
                .orders
                .push(order_record(intent, "expired", None, None));
        }
    }
    let account = &input.account;
    state.orders.sort_by_key(|order| order.intent_seq);
    let ending_equity = state
        .equity_curve
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
    let fill_count = state.trades.len();
    Ok(EngineOutputV1 {
        schema_version: 1,
        engine_version: ENGINE_VERSION.to_owned(),
        account_model: "crypto_linear_perp".to_owned(),
        orders: state.orders,
        trades: state.trades,
        positions: state.positions,
        cash_ledger: state.cash_ledger,
        funding_ledger: state.funding_ledger,
        equity_curve: state.equity_curve,
        drawdown_curve: state.drawdown_curve,
        metrics: Metrics {
            starting_equity_atoms: account.starting_balance_atoms,
            ending_equity_atoms: Atom(ending_equity),
            net_pnl_atoms: Atom(net_pnl),
            total_return_rate_atoms: Atom(total_return_rate),
            max_drawdown_atoms: Atom(state.max_drawdown),
            max_drawdown_rate_atoms: Atom(state.max_drawdown_rate),
            total_fees_atoms: Atom(state.total_fees),
            total_stamp_duty_atoms: Atom::ZERO,
            total_funding_atoms: Atom(state.total_funding),
            total_slippage_atoms: Atom(state.total_slippage),
            fill_count,
            closed_trade_count: state.closed_trade_count,
            open_position_count: u64::from(state.signed_quantity != 0),
        },
        costs: CostSummary {
            commission_atoms: Atom(state.total_fees),
            stamp_duty_atoms: Atom::ZERO,
            funding_atoms: Atom(state.total_funding),
            slippage_atoms: Atom(state.total_slippage),
        },
        assumptions: Assumptions {
            fill_model: "ohlc_full_fill_v1".to_owned(),
            partial_fills: false,
            liquidate_on_end: false,
            research_short: false,
            research_short_notice: None,
            one_x_notional: true,
        },
    })
}

pub fn start_engine_checkpoint_v1(
    input_bytes: &[u8],
    calculation_context_sha256: &str,
    batch_bar_count: usize,
) -> Result<Vec<u8>, EngineError> {
    validate_calculation_context(calculation_context_sha256)?;
    if batch_bar_count == 0 {
        return Err(checkpoint_error("batch_size_zero"));
    }
    let input = parse_checkpoint_input(input_bytes)?;
    let state = ExecutionState::new(&input.account);
    authoritative_make_checkpoint(
        &input,
        input_bytes,
        calculation_context_sha256,
        batch_bar_count,
        0,
        &state,
    )
}

pub fn step_engine_checkpoint_v1(
    input_bytes: &[u8],
    calculation_context_sha256: &str,
    checkpoint_bytes: &[u8],
) -> Result<Vec<u8>, EngineError> {
    let (input, checkpoint) =
        authoritative_decode_checkpoint(input_bytes, calculation_context_sha256, checkpoint_bytes)?;
    if checkpoint.status == "complete" {
        return Ok(checkpoint_bytes.to_vec());
    }
    let mut state = ExecutionState::from_checkpoint(checkpoint.state)?;
    let start = checkpoint.next_unprocessed_bar_index;
    let end = start
        .saturating_add(checkpoint.batch_bar_count)
        .min(input.bars.len());
    for bar in &input.bars[start..end] {
        if input.account.model == "a_share_cash" {
            state
                .process_a_share_bar(&input, bar)
                .map_err(|error| checkpoint_error_detail("state_inconsistent", error))?;
        } else {
            state
                .process_crypto_bar(&input, bar)
                .map_err(|error| checkpoint_error_detail("state_inconsistent", error))?;
        }
    }
    authoritative_make_checkpoint(
        &input,
        input_bytes,
        calculation_context_sha256,
        checkpoint.batch_bar_count,
        end,
        &state,
    )
}

pub fn finalize_engine_checkpoint_v1(
    input_bytes: &[u8],
    calculation_context_sha256: &str,
    checkpoint_bytes: &[u8],
) -> Result<Vec<u8>, EngineError> {
    let (input, checkpoint) =
        authoritative_decode_checkpoint(input_bytes, calculation_context_sha256, checkpoint_bytes)?;
    if checkpoint.status != "complete" {
        return Err(checkpoint_error("incomplete"));
    }
    let state = ExecutionState::from_checkpoint(checkpoint.state)?;
    let output = if input.account.model == "a_share_cash" {
        authoritative_finish_a_share(state, &input)
            .map_err(|error| checkpoint_error_detail("state_inconsistent", error))?
    } else {
        authoritative_finish_crypto(state, &input)
            .map_err(|error| checkpoint_error_detail("state_inconsistent", error))?
    };
    serde_json::to_vec(&output)
        .map_err(|error| checkpoint_error_detail("state_inconsistent", error))
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
                liquidity: fill.liquidity.to_owned(),
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
        engine_version: ENGINE_VERSION.to_owned(),
        account_model: "a_share_cash".to_owned(),
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
            fill_model: "ohlc_full_fill_v1".to_owned(),
            partial_fills: false,
            liquidate_on_end: false,
            research_short: account.allow_research_short,
            research_short_notice: account.allow_research_short.then_some(
                "hypothetical research model; not ordinary cash-account trading capability"
                    .to_owned(),
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
                liquidity: fill.liquidity.to_owned(),
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
        engine_version: ENGINE_VERSION.to_owned(),
        account_model: "crypto_linear_perp".to_owned(),
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
            fill_model: "ohlc_full_fill_v1".to_owned(),
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
        status: status.to_owned(),
        side: intent.side,
        position_effect: intent.position_effect,
        order_type: intent.order_type,
        quantity: intent.quantity,
        filled_session_seq,
        filled_phase: filled_phase.map(ToOwned::to_owned),
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

    #[pyfunction]
    fn start_engine_checkpoint_v1<'python>(
        python: Python<'python>,
        input: &[u8],
        calculation_context_sha256: &str,
        batch_bar_count: usize,
    ) -> PyResult<Bound<'python, PyBytes>> {
        let output =
            super::start_engine_checkpoint_v1(input, calculation_context_sha256, batch_bar_count)
                .map_err(|error| PyValueError::new_err(error.to_string()))?;
        Ok(PyBytes::new(python, &output))
    }

    #[pyfunction]
    fn step_engine_checkpoint_v1<'python>(
        python: Python<'python>,
        input: &[u8],
        calculation_context_sha256: &str,
        checkpoint: &[u8],
    ) -> PyResult<Bound<'python, PyBytes>> {
        let output =
            super::step_engine_checkpoint_v1(input, calculation_context_sha256, checkpoint)
                .map_err(|error| PyValueError::new_err(error.to_string()))?;
        Ok(PyBytes::new(python, &output))
    }

    #[pyfunction]
    fn finalize_engine_checkpoint_v1<'python>(
        python: Python<'python>,
        input: &[u8],
        calculation_context_sha256: &str,
        checkpoint: &[u8],
    ) -> PyResult<Bound<'python, PyBytes>> {
        let output =
            super::finalize_engine_checkpoint_v1(input, calculation_context_sha256, checkpoint)
                .map_err(|error| PyValueError::new_err(error.to_string()))?;
        Ok(PyBytes::new(python, &output))
    }

    #[pyfunction]
    fn run_engine_v2<'python>(
        python: Python<'python>,
        input: &[u8],
    ) -> PyResult<Bound<'python, PyBytes>> {
        let output = super::run_engine_v2(input)
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        Ok(PyBytes::new(python, &output))
    }

    #[pyfunction]
    fn start_engine_checkpoint_v2<'python>(
        python: Python<'python>,
        input: &[u8],
        calculation_context_sha256: &str,
        batch_session_count: usize,
    ) -> PyResult<Bound<'python, PyBytes>> {
        let output = super::start_engine_checkpoint_v2(
            input,
            calculation_context_sha256,
            batch_session_count,
        )
        .map_err(|error| PyValueError::new_err(error.to_string()))?;
        Ok(PyBytes::new(python, &output))
    }

    #[pyfunction]
    fn step_engine_checkpoint_v2<'python>(
        python: Python<'python>,
        input: &[u8],
        calculation_context_sha256: &str,
        checkpoint: &[u8],
    ) -> PyResult<Bound<'python, PyBytes>> {
        let output =
            super::step_engine_checkpoint_v2(input, calculation_context_sha256, checkpoint)
                .map_err(|error| PyValueError::new_err(error.to_string()))?;
        Ok(PyBytes::new(python, &output))
    }

    #[pyfunction]
    fn finalize_engine_checkpoint_v2<'python>(
        python: Python<'python>,
        input: &[u8],
        calculation_context_sha256: &str,
        checkpoint: &[u8],
    ) -> PyResult<Bound<'python, PyBytes>> {
        let output =
            super::finalize_engine_checkpoint_v2(input, calculation_context_sha256, checkpoint)
                .map_err(|error| PyValueError::new_err(error.to_string()))?;
        Ok(PyBytes::new(python, &output))
    }
}
