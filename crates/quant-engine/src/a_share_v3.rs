//! Versioned A-share research portfolio seam.
//!
//! Version 3 is one small, auditable A-share research seam: isolated
//! `cash_long` and `research_short` books, raw-price OHLC fills, deterministic
//! market/limit matching, shared participation capacity, and T+1 lot
//! eligibility.  Corporate actions are typed and applied at the session-open
//! transition, while unsupported action kinds fail closed during preflight.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use super::{Atom, EngineError, checked_add, checked_div, checked_mul, checked_sub};

const ENGINE_VERSION_V3: &str = "oqs-quant-engine/0.3.0";
const CHECKPOINT_SCHEMA_VERSION_V3: u32 = 3;

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct EngineInputV3 {
    schema_version: u32,
    market_rules_version: String,
    account: AccountV3,
    sessions: Vec<SessionV3>,
    corporate_actions: Vec<CorporateActionV3>,
    intents: Vec<IntentV3>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct AccountV3 {
    model: String,
    symbols: Vec<String>,
    price_scale: u32,
    cash_scale: u32,
    rate_scale: i128,
    starting_cash_atoms: Atom,
    lot_size: i128,
    max_participation_rate_atoms: Atom,
    commission_rate_atoms: Atom,
    minimum_commission_atoms: Atom,
    stamp_duty_rate_atoms: Atom,
    market_slippage_atoms: Atom,
    research_short_margin_rate_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct SessionV3 {
    session_seq: u64,
    timestamp: String,
    bars: Vec<BarV3>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct BarV3 {
    symbol: String,
    trading_status: TradingStatusV3,
    price_limit_state: PriceLimitStateV3,
    raw: RawBarV3,
    research: ResearchBarV3,
}

#[derive(Clone, Copy, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum TradingStatusV3 {
    Tradable,
    Suspended,
    NotListed,
    Delisted,
    NonTrading,
    Missing,
}

#[derive(Clone, Copy, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum PriceLimitStateV3 {
    None,
    LimitUp,
    LimitDown,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RawBarV3 {
    open_atoms: Atom,
    high_atoms: Atom,
    low_atoms: Atom,
    close_atoms: Atom,
    volume_quantity: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ResearchBarV3 {
    open_atoms: Atom,
    high_atoms: Atom,
    low_atoms: Atom,
    close_atoms: Atom,
}

#[derive(Clone, Copy, Deserialize, Serialize, Eq, Ord, PartialEq, PartialOrd)]
#[serde(rename_all = "snake_case")]
enum EventPhaseV3 {
    Open,
    Intraday,
    Close,
}

#[derive(Clone, Copy, Deserialize, Serialize, Eq, Ord, PartialEq, PartialOrd)]
#[serde(deny_unknown_fields)]
struct EventKeyV3 {
    session_seq: u64,
    phase: EventPhaseV3,
    stable_seq: u64,
}

#[derive(Clone, Copy, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum CorporateActionTypeV3 {
    CashDividend,
    Split,
    ReverseSplit,
    DelistSettlement,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct CorporateActionV3 {
    action_id: String,
    symbol: String,
    effective_at: EventKeyV3,
    action_type: CorporateActionTypeV3,
    #[serde(default)]
    cash_per_share_atoms: Option<Atom>,
    #[serde(default)]
    numerator: Option<i128>,
    #[serde(default)]
    denominator: Option<i128>,
    #[serde(default)]
    settlement_price_atoms: Option<Atom>,
}

#[derive(Clone, Copy, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum IntentKindV3 {
    Order,
    Cancel,
}

#[derive(Clone, Copy, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum PositionBookV3 {
    CashLong,
    ResearchShort,
}

#[derive(Clone, Copy, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum SideV3 {
    Buy,
    Sell,
}

#[derive(Clone, Copy, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum PositionEffectV3 {
    Open,
    Close,
}

#[derive(Clone, Copy, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum OrderTypeV3 {
    Market,
    Limit,
}

#[derive(Clone, Copy, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum TimeInForceV3 {
    Day,
    Gtc,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct IntentV3 {
    intent_kind: IntentKindV3,
    intent_id: String,
    intent_seq: u64,
    symbol: String,
    book: PositionBookV3,
    side: SideV3,
    position_effect: PositionEffectV3,
    quantity: Atom,
    order_type: OrderTypeV3,
    known_at: EventKeyV3,
    effective_at: EventKeyV3,
    limit_price_atoms: Option<Atom>,
    time_in_force: TimeInForceV3,
    #[serde(default)]
    condition_intent_id: Option<String>,
    #[serde(default, alias = "target_intent_id", alias = "cancel_target_intent_id")]
    cancelled_intent_id: Option<String>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct LotV3 {
    quantity_atoms: Atom,
    acquired_session_seq: u64,
    #[serde(default)]
    entry_price_atoms: Option<Atom>,
    #[serde(default)]
    cost_basis_atoms: Atom,
    #[serde(default)]
    allocated_margin_atoms: Atom,
    #[serde(default)]
    allocated_proceeds_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PendingOrderV3 {
    remaining_quantity: Atom,
    filled_quantity: Atom,
    #[serde(default)]
    commission_charged_atoms: Atom,
    #[serde(default)]
    raw_commission_accrued_atoms: Atom,
    first_fill_session_seq: Option<u64>,
    last_fill_session_seq: Option<u64>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct OrderRecordV3 {
    intent_id: String,
    intent_seq: u64,
    symbol: String,
    book: PositionBookV3,
    status: String,
    reject_reason: Option<String>,
    side: SideV3,
    position_effect: PositionEffectV3,
    order_type: OrderTypeV3,
    quantity: Atom,
    remaining_quantity: Atom,
    filled_session_seq: Option<u64>,
    filled_phase: Option<String>,
    #[serde(default)]
    cancelled_intent_id: Option<String>,
    condition_intent_id: Option<String>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct FillRecordV3 {
    fill_id: String,
    intent_id: String,
    intent_seq: u64,
    symbol: String,
    book: PositionBookV3,
    session_seq: u64,
    side: SideV3,
    position_effect: PositionEffectV3,
    quantity: Atom,
    fill_price_atoms: Atom,
    notional_atoms: Atom,
    fee_atoms: Atom,
    stamp_duty_atoms: Atom,
    slippage_atoms: Atom,
    liquidity: String,
    #[serde(default)]
    volume_before: Atom,
    #[serde(default)]
    volume_after: Atom,
    #[serde(default)]
    remaining_quantity: Atom,
    #[serde(default)]
    frozen_margin_delta_atoms: Atom,
    #[serde(default)]
    isolated_proceeds_delta_atoms: Atom,
    condition_intent_id: Option<String>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PositionRecordV3 {
    intent_id: String,
    symbol: String,
    book: PositionBookV3,
    session_seq: u64,
    signed_quantity: Atom,
    eligible_quantity: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct CashRecordV3 {
    intent_id: String,
    symbol: String,
    book: PositionBookV3,
    session_seq: u64,
    notional_delta_atoms: Atom,
    fee_delta_atoms: Atom,
    stamp_duty_delta_atoms: Atom,
    realized_pnl_delta_atoms: Atom,
    resulting_available_cash_atoms: Atom,
    #[serde(default)]
    frozen_margin_delta_atoms: Atom,
    #[serde(default)]
    isolated_proceeds_delta_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct CorporateActionRecordV3 {
    action_id: String,
    symbol: String,
    session_seq: u64,
    action_type: CorporateActionTypeV3,
    book: PositionBookV3,
    quantity_before: Atom,
    quantity_after: Atom,
    available_cash_delta_atoms: Atom,
    frozen_margin_delta_atoms: Atom,
    isolated_proceeds_delta_atoms: Atom,
    realized_pnl_delta_atoms: Atom,
    resulting_available_cash_atoms: Atom,
    resulting_frozen_margin_atoms: Atom,
    resulting_isolated_proceeds_atoms: Atom,
}

#[derive(Clone, Copy)]
struct CorporateActionEffectV3 {
    quantity_before: i128,
    quantity_after: i128,
    available_cash_delta: i128,
    frozen_margin_delta: i128,
    isolated_proceeds_delta: i128,
    realized_pnl_delta: i128,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct EquityPointV3 {
    session_seq: u64,
    timestamp: String,
    available_cash_atoms: Atom,
    long_market_value_atoms: Atom,
    short_liability_atoms: Atom,
    gross_market_value_atoms: Atom,
    net_market_value_atoms: Atom,
    market_value_atoms: Atom,
    equity_atoms: Atom,
    #[serde(default)]
    frozen_margin_atoms: Atom,
    #[serde(default)]
    isolated_short_proceeds_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct DrawdownPointV3 {
    session_seq: u64,
    equity_atoms: Atom,
    peak_equity_atoms: Atom,
    drawdown_atoms: Atom,
    drawdown_rate_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
struct MetricsV3 {
    starting_equity_atoms: Atom,
    ending_equity_atoms: Atom,
    net_pnl_atoms: Atom,
    total_return_rate_atoms: Atom,
    max_drawdown_atoms: Atom,
    max_drawdown_rate_atoms: Atom,
    total_fees_atoms: Atom,
    total_stamp_duty_atoms: Atom,
    total_slippage_atoms: Atom,
    fill_count: usize,
    closed_trade_count: u64,
    open_position_count: u64,
}

#[derive(Clone, Deserialize, Serialize)]
struct CostsV3 {
    commission_atoms: Atom,
    stamp_duty_atoms: Atom,
    slippage_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
struct AssumptionsV3 {
    fill_model: String,
    partial_fills: bool,
    liquidate_on_end: bool,
    cash_long: bool,
    research_short: bool,
    limit_orders: bool,
    corporate_actions: bool,
    tradability_gates: bool,
    t_plus_one: bool,
}

#[derive(Serialize)]
struct OutputV3 {
    schema_version: u32,
    engine_version: String,
    account_model: String,
    orders: Vec<OrderRecordV3>,
    fills: Vec<FillRecordV3>,
    positions: Vec<PositionRecordV3>,
    cash_ledger: Vec<CashRecordV3>,
    corporate_action_ledger: Vec<CorporateActionRecordV3>,
    equity_curve: Vec<EquityPointV3>,
    drawdown_curve: Vec<DrawdownPointV3>,
    metrics: MetricsV3,
    costs: CostsV3,
    assumptions: AssumptionsV3,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct StateV3 {
    available_cash_atoms: Atom,
    lots_by_symbol: BTreeMap<String, Vec<LotV3>>,
    short_lots_by_symbol: BTreeMap<String, Vec<LotV3>>,
    frozen_margin_atoms: Atom,
    isolated_short_proceeds_atoms: Atom,
    pending_orders: BTreeMap<String, PendingOrderV3>,
    completed_intent_ids: BTreeSet<String>,
    cancelled_intent_ids: BTreeSet<String>,
    delisted_symbols: BTreeSet<String>,
    orders: Vec<OrderRecordV3>,
    fills: Vec<FillRecordV3>,
    positions: Vec<PositionRecordV3>,
    cash_ledger: Vec<CashRecordV3>,
    corporate_action_ledger: Vec<CorporateActionRecordV3>,
    equity_curve: Vec<EquityPointV3>,
    drawdown_curve: Vec<DrawdownPointV3>,
    peak_equity_atoms: Atom,
    max_drawdown_atoms: Atom,
    max_drawdown_rate_atoms: Atom,
    total_fees_atoms: Atom,
    total_stamp_duty_atoms: Atom,
    total_slippage_atoms: Atom,
    closed_trade_count: u64,
}

impl StateV3 {
    fn new(account: &AccountV3) -> Self {
        Self {
            available_cash_atoms: account.starting_cash_atoms,
            lots_by_symbol: account
                .symbols
                .iter()
                .cloned()
                .map(|symbol| (symbol, Vec::new()))
                .collect(),
            short_lots_by_symbol: account
                .symbols
                .iter()
                .cloned()
                .map(|symbol| (symbol, Vec::new()))
                .collect(),
            frozen_margin_atoms: Atom::ZERO,
            isolated_short_proceeds_atoms: Atom::ZERO,
            pending_orders: BTreeMap::new(),
            completed_intent_ids: BTreeSet::new(),
            cancelled_intent_ids: BTreeSet::new(),
            delisted_symbols: BTreeSet::new(),
            orders: Vec::new(),
            fills: Vec::new(),
            positions: Vec::new(),
            cash_ledger: Vec::new(),
            corporate_action_ledger: Vec::new(),
            equity_curve: Vec::new(),
            drawdown_curve: Vec::new(),
            peak_equity_atoms: account.starting_cash_atoms,
            max_drawdown_atoms: Atom::ZERO,
            max_drawdown_rate_atoms: Atom::ZERO,
            total_fees_atoms: Atom::ZERO,
            total_stamp_duty_atoms: Atom::ZERO,
            total_slippage_atoms: Atom::ZERO,
            closed_trade_count: 0,
        }
    }

    fn position_quantity(&self, symbol: &str) -> Result<i128, EngineError> {
        self.lots_by_symbol
            .get(symbol)
            .ok_or_else(|| EngineError::new("v3 position symbol is not in the account"))?
            .iter()
            .try_fold(0_i128, |total, lot| {
                checked_add(total, lot.quantity_atoms.0, "v3 position quantity")
            })
    }

    fn eligible_quantity(&self, symbol: &str, session_seq: u64) -> Result<i128, EngineError> {
        self.lots_by_symbol
            .get(symbol)
            .ok_or_else(|| EngineError::new("v3 eligible symbol is not in the account"))?
            .iter()
            .filter(|lot| lot.acquired_session_seq < session_seq)
            .try_fold(0_i128, |total, lot| {
                checked_add(total, lot.quantity_atoms.0, "v3 eligible quantity")
            })
    }

    fn short_position_quantity(&self, symbol: &str) -> Result<i128, EngineError> {
        self.short_lots_by_symbol
            .get(symbol)
            .ok_or_else(|| EngineError::new("v3 short position symbol is not in the account"))?
            .iter()
            .try_fold(0_i128, |total, lot| {
                checked_add(total, lot.quantity_atoms.0, "v3 short position quantity")
            })
    }

    fn short_eligible_quantity(&self, symbol: &str, session_seq: u64) -> Result<i128, EngineError> {
        self.short_lots_by_symbol
            .get(symbol)
            .ok_or_else(|| EngineError::new("v3 short eligible symbol is not in the account"))?
            .iter()
            .filter(|lot| lot.acquired_session_seq < session_seq)
            .try_fold(0_i128, |total, lot| {
                checked_add(total, lot.quantity_atoms.0, "v3 short eligible quantity")
            })
    }

    /// Consume FIFO short lots and return the isolated margin and proceeds
    /// released for the consumed quantity.  Allocations are split with
    /// checked integer arithmetic; the final piece of a lot receives any
    /// remainder so the ledger always balances exactly.
    fn consume_short_eligible_lots(
        &mut self,
        symbol: &str,
        quantity: i128,
        session_seq: u64,
    ) -> Result<(i128, i128), EngineError> {
        if self.short_eligible_quantity(symbol, session_seq)? < quantity {
            return Err(EngineError::new(
                "v3 short T+1 eligible quantity is insufficient",
            ));
        }
        let lots = self
            .short_lots_by_symbol
            .get_mut(symbol)
            .ok_or_else(|| EngineError::new("v3 short eligible symbol is not in the account"))?;
        let mut remaining = quantity;
        let mut released_margin = 0_i128;
        let mut released_proceeds = 0_i128;
        for lot in lots
            .iter_mut()
            .filter(|lot| lot.acquired_session_seq < session_seq)
        {
            if remaining == 0 {
                break;
            }
            let original_quantity = lot.quantity_atoms.0;
            let consumed = original_quantity.min(remaining);
            let (margin, proceeds) = if consumed == original_quantity {
                (lot.allocated_margin_atoms.0, lot.allocated_proceeds_atoms.0)
            } else {
                (
                    checked_div(
                        checked_mul(
                            lot.allocated_margin_atoms.0,
                            consumed,
                            "v3 short margin allocation",
                        )?,
                        original_quantity,
                        "v3 short margin allocation division",
                    )?,
                    checked_div(
                        checked_mul(
                            lot.allocated_proceeds_atoms.0,
                            consumed,
                            "v3 short proceeds allocation",
                        )?,
                        original_quantity,
                        "v3 short proceeds allocation division",
                    )?,
                )
            };
            lot.quantity_atoms.0 = checked_sub(
                lot.quantity_atoms.0,
                consumed,
                "v3 short consumed lot quantity",
            )?;
            lot.allocated_margin_atoms.0 = checked_sub(
                lot.allocated_margin_atoms.0,
                margin,
                "v3 short remaining margin allocation",
            )?;
            lot.allocated_proceeds_atoms.0 = checked_sub(
                lot.allocated_proceeds_atoms.0,
                proceeds,
                "v3 short remaining proceeds allocation",
            )?;
            remaining = checked_sub(remaining, consumed, "v3 short remaining quantity")?;
            released_margin = checked_add(released_margin, margin, "v3 released short margin")?;
            released_proceeds =
                checked_add(released_proceeds, proceeds, "v3 released short proceeds")?;
        }
        lots.retain(|lot| lot.quantity_atoms.0 != 0);
        Ok((released_margin, released_proceeds))
    }

    fn consume_eligible_lots(
        &mut self,
        symbol: &str,
        quantity: i128,
        session_seq: u64,
    ) -> Result<i128, EngineError> {
        if self.eligible_quantity(symbol, session_seq)? < quantity {
            return Err(EngineError::new("v3 T+1 eligible quantity is insufficient"));
        }
        let lots = self
            .lots_by_symbol
            .get_mut(symbol)
            .ok_or_else(|| EngineError::new("v3 eligible symbol is not in the account"))?;
        let mut remaining = quantity;
        let mut entry_notional = 0_i128;
        for lot in lots
            .iter_mut()
            .filter(|lot| lot.acquired_session_seq < session_seq)
        {
            let original_quantity = lot.quantity_atoms.0;
            let consumed = original_quantity.min(remaining);
            let consumed_basis = if consumed == original_quantity {
                lot.cost_basis_atoms.0
            } else {
                checked_div(
                    checked_mul(
                        lot.cost_basis_atoms.0,
                        consumed,
                        "v3 consumed long basis allocation",
                    )?,
                    original_quantity,
                    "v3 consumed long basis allocation division",
                )?
            };
            entry_notional = checked_add(
                entry_notional,
                consumed_basis,
                "v3 consumed long entry notional total",
            )?;
            lot.quantity_atoms.0 =
                checked_sub(lot.quantity_atoms.0, consumed, "v3 consumed lot quantity")?;
            lot.cost_basis_atoms.0 = checked_sub(
                lot.cost_basis_atoms.0,
                consumed_basis,
                "v3 remaining long cost basis",
            )?;
            remaining = checked_sub(remaining, consumed, "v3 remaining lot quantity")?;
            if remaining == 0 {
                break;
            }
        }
        lots.retain(|lot| lot.quantity_atoms.0 != 0);
        Ok(entry_notional)
    }

    fn record_order(
        &mut self,
        intent: &IntentV3,
        status: &str,
        reason: Option<&str>,
        filled_session_seq: Option<u64>,
        remaining_quantity: i128,
    ) {
        if let Some(order) = self
            .orders
            .iter_mut()
            .find(|order| order.intent_id == intent.intent_id)
        {
            order.status = status.to_owned();
            order.reject_reason = reason.map(str::to_owned);
            order.remaining_quantity = Atom(remaining_quantity);
            if filled_session_seq.is_some() && order.filled_session_seq.is_none() {
                order.filled_session_seq = filled_session_seq;
                order.filled_phase = Some("open".to_owned());
            }
            return;
        }
        self.orders.push(OrderRecordV3 {
            intent_id: intent.intent_id.clone(),
            intent_seq: intent.intent_seq,
            symbol: intent.symbol.clone(),
            book: intent.book,
            status: status.to_owned(),
            reject_reason: reason.map(str::to_owned),
            side: intent.side,
            position_effect: intent.position_effect,
            order_type: intent.order_type,
            quantity: intent.quantity,
            remaining_quantity: Atom(remaining_quantity),
            filled_session_seq,
            filled_phase: filled_session_seq.map(|_| "open".to_owned()),
            cancelled_intent_id: None,
            condition_intent_id: intent.condition_intent_id.clone(),
        });
    }

    fn remaining_quantity_for(&self, intent: &IntentV3) -> i128 {
        self.pending_orders
            .get(&intent.intent_id)
            .map_or(intent.quantity.0, |pending| pending.remaining_quantity.0)
    }

    fn commission_for_fill(
        &self,
        intent: &IntentV3,
        notional: i128,
        rate: i128,
        minimum: i128,
        scale: i128,
    ) -> Result<(i128, i128), EngineError> {
        let raw_fee = rate_charge(notional, rate, scale)?;
        let (charged_before, raw_accrued_before) = self
            .pending_orders
            .get(&intent.intent_id)
            .map_or((0, 0), |pending| {
                (
                    pending.commission_charged_atoms.0,
                    pending.raw_commission_accrued_atoms.0,
                )
            });
        let raw_accrued_after =
            checked_add(raw_accrued_before, raw_fee, "v3 cumulative raw commission")?;
        let required_charge_after = raw_accrued_after.max(minimum);
        let incremental_charge = checked_sub(
            required_charge_after,
            charged_before,
            "v3 incremental commission",
        )?;
        Ok((incremental_charge, raw_fee))
    }

    /// Keep a temporarily unfilled GTC order in the checkpoint state.  DAY
    /// orders have no later session to carry into, so the same helper emits a
    /// deterministic terminal expiry for them.
    fn defer_or_expire(
        &mut self,
        intent: &IntentV3,
        reason: &str,
        remaining_quantity: i128,
    ) -> Result<(), EngineError> {
        if matches!(intent.time_in_force, TimeInForceV3::Gtc) {
            let (status, first_fill_session_seq) = {
                let pending = self
                    .pending_orders
                    .entry(intent.intent_id.clone())
                    .or_insert(PendingOrderV3 {
                        remaining_quantity: Atom(remaining_quantity),
                        filled_quantity: Atom::ZERO,
                        commission_charged_atoms: Atom::ZERO,
                        raw_commission_accrued_atoms: Atom::ZERO,
                        first_fill_session_seq: None,
                        last_fill_session_seq: None,
                    });
                pending.remaining_quantity = Atom(remaining_quantity);
                if pending.filled_quantity.0 == 0 {
                    ("accepted", pending.first_fill_session_seq)
                } else {
                    ("partial", pending.first_fill_session_seq)
                }
            };
            self.record_order(
                intent,
                status,
                Some(reason),
                first_fill_session_seq,
                remaining_quantity,
            );
        } else {
            self.pending_orders.remove(&intent.intent_id);
            self.record_order(intent, "expired", Some(reason), None, remaining_quantity);
            self.completed_intent_ids.insert(intent.intent_id.clone());
        }
        Ok(())
    }

    fn reject_order(&mut self, intent: &IntentV3, reason: &str, remaining_quantity: i128) {
        self.pending_orders.remove(&intent.intent_id);
        self.record_order(intent, "rejected", Some(reason), None, remaining_quantity);
        self.completed_intent_ids.insert(intent.intent_id.clone());
    }

    fn record_corporate_action(
        &mut self,
        action: &CorporateActionV3,
        book: PositionBookV3,
        effect: CorporateActionEffectV3,
    ) {
        self.corporate_action_ledger.push(CorporateActionRecordV3 {
            action_id: action.action_id.clone(),
            symbol: action.symbol.clone(),
            session_seq: action.effective_at.session_seq,
            action_type: action.action_type,
            book,
            quantity_before: Atom(effect.quantity_before),
            quantity_after: Atom(effect.quantity_after),
            available_cash_delta_atoms: Atom(effect.available_cash_delta),
            frozen_margin_delta_atoms: Atom(effect.frozen_margin_delta),
            isolated_proceeds_delta_atoms: Atom(effect.isolated_proceeds_delta),
            realized_pnl_delta_atoms: Atom(effect.realized_pnl_delta),
            resulting_available_cash_atoms: self.available_cash_atoms,
            resulting_frozen_margin_atoms: self.frozen_margin_atoms,
            resulting_isolated_proceeds_atoms: self.isolated_short_proceeds_atoms,
        });
    }

    fn record_corporate_cash(
        &mut self,
        action: &CorporateActionV3,
        book: PositionBookV3,
        notional_delta: i128,
        realized_pnl_delta: i128,
        frozen_margin_delta: i128,
        isolated_proceeds_delta: i128,
    ) {
        self.cash_ledger.push(CashRecordV3 {
            intent_id: format!("corporate:{}", action.action_id),
            symbol: action.symbol.clone(),
            book,
            session_seq: action.effective_at.session_seq,
            notional_delta_atoms: Atom(notional_delta),
            fee_delta_atoms: Atom::ZERO,
            stamp_duty_delta_atoms: Atom::ZERO,
            realized_pnl_delta_atoms: Atom(realized_pnl_delta),
            resulting_available_cash_atoms: self.available_cash_atoms,
            frozen_margin_delta_atoms: Atom(frozen_margin_delta),
            isolated_proceeds_delta_atoms: Atom(isolated_proceeds_delta),
        });
    }

    fn record_corporate_position(
        &mut self,
        action: &CorporateActionV3,
        book: PositionBookV3,
        signed_quantity: i128,
        eligible_quantity: i128,
    ) {
        self.positions.push(PositionRecordV3 {
            intent_id: format!("corporate:{}", action.action_id),
            symbol: action.symbol.clone(),
            book,
            session_seq: action.effective_at.session_seq,
            signed_quantity: Atom(signed_quantity),
            eligible_quantity: Atom(eligible_quantity),
        });
    }

    fn cancel_pending_orders_for_symbol(
        &mut self,
        input: &EngineInputV3,
        action: &CorporateActionV3,
        reason: &str,
    ) {
        let pending_ids = self
            .pending_orders
            .keys()
            .filter(|intent_id| {
                input.intents.iter().any(|intent| {
                    intent.intent_id == intent_id.as_str() && intent.symbol == action.symbol
                })
            })
            .cloned()
            .collect::<Vec<_>>();
        for intent_id in pending_ids {
            let Some(intent) = input
                .intents
                .iter()
                .find(|intent| intent.intent_id == intent_id)
            else {
                continue;
            };
            let remaining = self.remaining_quantity_for(intent);
            self.pending_orders.remove(&intent_id);
            self.completed_intent_ids.insert(intent_id.clone());
            self.cancelled_intent_ids.insert(intent_id.clone());
            self.record_order(intent, "cancelled", Some(reason), None, remaining);
            if let Some(order) = self
                .orders
                .iter_mut()
                .find(|order| order.intent_id == intent_id)
            {
                order.cancelled_intent_id = Some(format!("corporate:{}", action.action_id));
            }
        }
    }

    fn apply_cash_dividend(&mut self, action: &CorporateActionV3) -> Result<(), EngineError> {
        let cash_per_share = action
            .cash_per_share_atoms
            .ok_or_else(|| EngineError::new("v3 cash dividend amount is required"))?
            .0;
        let long_quantity = self.position_quantity(&action.symbol)?;
        if long_quantity > 0 {
            let cash_delta = checked_mul(long_quantity, cash_per_share, "v3 long cash dividend")?;
            self.available_cash_atoms = Atom(checked_add(
                self.available_cash_atoms.0,
                cash_delta,
                "v3 available cash after long dividend",
            )?);
            self.record_corporate_action(
                action,
                PositionBookV3::CashLong,
                CorporateActionEffectV3 {
                    quantity_before: long_quantity,
                    quantity_after: long_quantity,
                    available_cash_delta: cash_delta,
                    frozen_margin_delta: 0,
                    isolated_proceeds_delta: 0,
                    realized_pnl_delta: cash_delta,
                },
            );
            self.record_corporate_cash(action, PositionBookV3::CashLong, 0, cash_delta, 0, 0);
        }
        let short_quantity = self.short_position_quantity(&action.symbol)?;
        if short_quantity > 0 {
            let cash_delta =
                -checked_mul(short_quantity, cash_per_share, "v3 short cash dividend")?;
            self.available_cash_atoms = Atom(checked_add(
                self.available_cash_atoms.0,
                cash_delta,
                "v3 available cash after short dividend",
            )?);
            self.record_corporate_action(
                action,
                PositionBookV3::ResearchShort,
                CorporateActionEffectV3 {
                    quantity_before: short_quantity,
                    quantity_after: short_quantity,
                    available_cash_delta: cash_delta,
                    frozen_margin_delta: 0,
                    isolated_proceeds_delta: 0,
                    realized_pnl_delta: cash_delta,
                },
            );
            self.record_corporate_cash(action, PositionBookV3::ResearchShort, 0, cash_delta, 0, 0);
        }
        Ok(())
    }

    fn apply_split(
        &mut self,
        input: &EngineInputV3,
        action: &CorporateActionV3,
    ) -> Result<(), EngineError> {
        self.cancel_pending_orders_for_symbol(
            input,
            action,
            "corporate_action_reprice_unsupported",
        );
        let numerator = action
            .numerator
            .ok_or_else(|| EngineError::new("v3 split numerator is required"))?;
        let denominator = action
            .denominator
            .ok_or_else(|| EngineError::new("v3 split denominator is required"))?;

        let long_before = self.position_quantity(&action.symbol)?;
        if long_before > 0 {
            let lots = self
                .lots_by_symbol
                .get_mut(&action.symbol)
                .ok_or_else(|| EngineError::new("v3 split long symbol is not in the account"))?;
            for lot in lots {
                let adjusted_numerator = checked_mul(
                    lot.quantity_atoms.0,
                    numerator,
                    "v3 split long quantity numerator",
                )?;
                if adjusted_numerator % denominator != 0 {
                    return Err(EngineError::new(
                        "v3 split would create a fractional long share",
                    ));
                }
                lot.quantity_atoms = Atom(checked_div(
                    adjusted_numerator,
                    denominator,
                    "v3 split long quantity",
                )?);
                if let Some(price) = lot.entry_price_atoms {
                    let adjusted =
                        checked_mul(price.0, denominator, "v3 split long entry-price numerator")?;
                    if adjusted % numerator != 0 {
                        return Err(EngineError::new(
                            "v3 split would create a non-integral long entry price",
                        ));
                    }
                    lot.entry_price_atoms = Some(Atom(checked_div(
                        adjusted,
                        numerator,
                        "v3 split long entry price",
                    )?));
                }
            }
            let long_after = self.position_quantity(&action.symbol)?;
            self.record_corporate_action(
                action,
                PositionBookV3::CashLong,
                CorporateActionEffectV3 {
                    quantity_before: long_before,
                    quantity_after: long_after,
                    available_cash_delta: 0,
                    frozen_margin_delta: 0,
                    isolated_proceeds_delta: 0,
                    realized_pnl_delta: 0,
                },
            );
            let eligible =
                self.eligible_quantity(&action.symbol, action.effective_at.session_seq)?;
            self.record_corporate_position(action, PositionBookV3::CashLong, long_after, eligible);
        }

        let short_before = self.short_position_quantity(&action.symbol)?;
        if short_before > 0 {
            let lots = self
                .short_lots_by_symbol
                .get_mut(&action.symbol)
                .ok_or_else(|| EngineError::new("v3 split short symbol is not in the account"))?;
            for lot in lots {
                let adjusted_numerator = checked_mul(
                    lot.quantity_atoms.0,
                    numerator,
                    "v3 split short quantity numerator",
                )?;
                if adjusted_numerator % denominator != 0 {
                    return Err(EngineError::new(
                        "v3 split would create a fractional short share",
                    ));
                }
                lot.quantity_atoms = Atom(checked_div(
                    adjusted_numerator,
                    denominator,
                    "v3 split short quantity",
                )?);
                if let Some(price) = lot.entry_price_atoms {
                    let adjusted =
                        checked_mul(price.0, denominator, "v3 split short entry-price numerator")?;
                    if adjusted % numerator != 0 {
                        return Err(EngineError::new(
                            "v3 split would create a non-integral short entry price",
                        ));
                    }
                    lot.entry_price_atoms = Some(Atom(checked_div(
                        adjusted,
                        numerator,
                        "v3 split short entry price",
                    )?));
                }
            }
            let short_after = self.short_position_quantity(&action.symbol)?;
            self.record_corporate_action(
                action,
                PositionBookV3::ResearchShort,
                CorporateActionEffectV3 {
                    quantity_before: short_before,
                    quantity_after: short_after,
                    available_cash_delta: 0,
                    frozen_margin_delta: 0,
                    isolated_proceeds_delta: 0,
                    realized_pnl_delta: 0,
                },
            );
            let eligible =
                -self.short_eligible_quantity(&action.symbol, action.effective_at.session_seq)?;
            self.record_corporate_position(
                action,
                PositionBookV3::ResearchShort,
                -short_after,
                eligible,
            );
        }
        Ok(())
    }

    fn apply_delist_settlement(
        &mut self,
        input: &EngineInputV3,
        action: &CorporateActionV3,
    ) -> Result<(), EngineError> {
        self.cancel_pending_orders_for_symbol(input, action, "delisted_settlement");
        let settlement_price = action
            .settlement_price_atoms
            .ok_or_else(|| EngineError::new("v3 delist settlement price is required"))?
            .0;

        let long_quantity = self.position_quantity(&action.symbol)?;
        if long_quantity > 0 {
            let long_basis = self
                .lots_by_symbol
                .get(&action.symbol)
                .ok_or_else(|| EngineError::new("v3 delist long symbol is not in the account"))?
                .iter()
                .try_fold(0_i128, |total, lot| {
                    checked_add(total, lot.cost_basis_atoms.0, "v3 delist long basis")
                })?;
            let settlement =
                checked_mul(long_quantity, settlement_price, "v3 delist long settlement")?;
            let realized_pnl = checked_sub(settlement, long_basis, "v3 delist long pnl")?;
            self.available_cash_atoms = Atom(checked_add(
                self.available_cash_atoms.0,
                settlement,
                "v3 cash after long delist settlement",
            )?);
            self.lots_by_symbol
                .get_mut(&action.symbol)
                .ok_or_else(|| EngineError::new("v3 delist long symbol is not in the account"))?
                .clear();
            self.closed_trade_count = self
                .closed_trade_count
                .checked_add(1)
                .ok_or_else(|| EngineError::new("v3 closed trade count overflow"))?;
            self.record_corporate_action(
                action,
                PositionBookV3::CashLong,
                CorporateActionEffectV3 {
                    quantity_before: long_quantity,
                    quantity_after: 0,
                    available_cash_delta: settlement,
                    frozen_margin_delta: 0,
                    isolated_proceeds_delta: 0,
                    realized_pnl_delta: realized_pnl,
                },
            );
            self.record_corporate_cash(
                action,
                PositionBookV3::CashLong,
                settlement,
                realized_pnl,
                0,
                0,
            );
            self.record_corporate_position(action, PositionBookV3::CashLong, 0, 0);
        }

        let short_quantity = self.short_position_quantity(&action.symbol)?;
        if short_quantity > 0 {
            let (released_margin, released_proceeds) = self
                .short_lots_by_symbol
                .get(&action.symbol)
                .ok_or_else(|| EngineError::new("v3 delist short symbol is not in the account"))?
                .iter()
                .try_fold((0_i128, 0_i128), |(margin, proceeds), lot| {
                    Ok::<(i128, i128), EngineError>((
                        checked_add(
                            margin,
                            lot.allocated_margin_atoms.0,
                            "v3 delist short margin",
                        )?,
                        checked_add(
                            proceeds,
                            lot.allocated_proceeds_atoms.0,
                            "v3 delist short proceeds",
                        )?,
                    ))
                })?;
            let settlement = checked_mul(
                short_quantity,
                settlement_price,
                "v3 delist short settlement",
            )?;
            let released_pools = checked_add(
                released_margin,
                released_proceeds,
                "v3 delist released short pools",
            )?;
            let cash_delta = checked_sub(
                released_pools,
                settlement,
                "v3 delist short cash settlement",
            )?;
            let realized_pnl = checked_sub(released_proceeds, settlement, "v3 delist short pnl")?;
            self.available_cash_atoms = Atom(checked_add(
                self.available_cash_atoms.0,
                cash_delta,
                "v3 cash after short delist settlement",
            )?);
            self.frozen_margin_atoms = Atom(checked_sub(
                self.frozen_margin_atoms.0,
                released_margin,
                "v3 margin after short delist settlement",
            )?);
            self.isolated_short_proceeds_atoms = Atom(checked_sub(
                self.isolated_short_proceeds_atoms.0,
                released_proceeds,
                "v3 proceeds after short delist settlement",
            )?);
            self.short_lots_by_symbol
                .get_mut(&action.symbol)
                .ok_or_else(|| EngineError::new("v3 delist short symbol is not in the account"))?
                .clear();
            self.closed_trade_count = self
                .closed_trade_count
                .checked_add(1)
                .ok_or_else(|| EngineError::new("v3 closed trade count overflow"))?;
            self.record_corporate_action(
                action,
                PositionBookV3::ResearchShort,
                CorporateActionEffectV3 {
                    quantity_before: short_quantity,
                    quantity_after: 0,
                    available_cash_delta: cash_delta,
                    frozen_margin_delta: -released_margin,
                    isolated_proceeds_delta: -released_proceeds,
                    realized_pnl_delta: realized_pnl,
                },
            );
            self.record_corporate_cash(
                action,
                PositionBookV3::ResearchShort,
                -settlement,
                realized_pnl,
                -released_margin,
                -released_proceeds,
            );
            self.record_corporate_position(action, PositionBookV3::ResearchShort, 0, 0);
        }
        self.delisted_symbols.insert(action.symbol.clone());
        Ok(())
    }

    fn validate_short_pools(&self) -> Result<(), EngineError> {
        let (expected_margin, expected_proceeds) = self
            .short_lots_by_symbol
            .values()
            .flatten()
            .try_fold((0_i128, 0_i128), |(margin, proceeds), lot| {
                Ok::<(i128, i128), EngineError>((
                    checked_add(
                        margin,
                        lot.allocated_margin_atoms.0,
                        "v3 expected short margin",
                    )?,
                    checked_add(
                        proceeds,
                        lot.allocated_proceeds_atoms.0,
                        "v3 expected short proceeds",
                    )?,
                ))
            })?;
        if expected_margin != self.frozen_margin_atoms.0
            || expected_proceeds != self.isolated_short_proceeds_atoms.0
            || expected_margin < 0
            || expected_proceeds < 0
        {
            return Err(EngineError::new("v3 isolated short pools do not reconcile"));
        }
        Ok(())
    }

    fn process_corporate_actions(
        &mut self,
        input: &EngineInputV3,
        session: &SessionV3,
    ) -> Result<(), EngineError> {
        for action in input
            .corporate_actions
            .iter()
            .filter(|action| action.effective_at.session_seq == session.session_seq)
        {
            match action.action_type {
                CorporateActionTypeV3::CashDividend => self.apply_cash_dividend(action)?,
                CorporateActionTypeV3::Split | CorporateActionTypeV3::ReverseSplit => {
                    self.apply_split(input, action)?
                }
                CorporateActionTypeV3::DelistSettlement => {
                    self.apply_delist_settlement(input, action)?;
                }
            }
            self.validate_short_pools()?;
        }
        Ok(())
    }

    fn process_cancel(
        &mut self,
        input: &EngineInputV3,
        intent: &IntentV3,
    ) -> Result<(), EngineError> {
        let Some(target_id) = intent.cancelled_intent_id.as_deref() else {
            self.reject_order(intent, "missing_cancel_target", intent.quantity.0);
            return Ok(());
        };
        let Some(target) = input
            .intents
            .iter()
            .find(|candidate| candidate.intent_id == target_id)
        else {
            self.reject_order(intent, "unknown_cancel_target", intent.quantity.0);
            return Ok(());
        };
        if self.completed_intent_ids.contains(target_id) {
            self.reject_order(intent, "target_not_open", intent.quantity.0);
            return Ok(());
        }

        let target_remaining = self.remaining_quantity_for(target);
        self.pending_orders.remove(target_id);
        self.completed_intent_ids.insert(target_id.to_owned());
        self.cancelled_intent_ids.insert(target_id.to_owned());
        if let Some(order) = self
            .orders
            .iter_mut()
            .find(|order| order.intent_id == target_id)
        {
            order.status = "cancelled".to_owned();
            order.reject_reason = Some("cancelled".to_owned());
            order.remaining_quantity = Atom(target_remaining);
            order.cancelled_intent_id = Some(intent.intent_id.clone());
        } else {
            self.record_order(
                target,
                "cancelled",
                Some("cancelled"),
                None,
                target_remaining,
            );
            if let Some(order) = self
                .orders
                .iter_mut()
                .find(|order| order.intent_id == target_id)
            {
                order.cancelled_intent_id = Some(intent.intent_id.clone());
            }
        }
        self.record_order(intent, "filled", None, None, 0);
        if let Some(order) = self
            .orders
            .iter_mut()
            .find(|order| order.intent_id == intent.intent_id)
        {
            order.cancelled_intent_id = Some(target_id.to_owned());
        }
        self.completed_intent_ids.insert(intent.intent_id.clone());
        Ok(())
    }

    fn process_session(
        &mut self,
        input: &EngineInputV3,
        session: &SessionV3,
    ) -> Result<(), EngineError> {
        let bars_by_symbol = session
            .bars
            .iter()
            .map(|bar| (bar.symbol.as_str(), bar))
            .collect::<BTreeMap<_, _>>();
        self.process_corporate_actions(input, session)?;
        let mut due_intents = input
            .intents
            .iter()
            .filter(|intent| {
                !self.completed_intent_ids.contains(&intent.intent_id)
                    && match intent.time_in_force {
                        TimeInForceV3::Day => {
                            intent.effective_at.session_seq == session.session_seq
                        }
                        TimeInForceV3::Gtc => {
                            intent.effective_at.session_seq <= session.session_seq
                        }
                    }
            })
            .collect::<Vec<_>>();
        let mut used_volume_by_symbol = BTreeMap::<String, i128>::new();
        // Within one effective event key, market orders have priority over
        // limits.  The remaining keys make that tie-break deterministic as
        // later order types are added without changing the event clock.
        due_intents.sort_by(|left, right| {
            // The effective event is the primary clock.  A cancellation may
            // outrank an order only when both share the exact same event key;
            // otherwise a later cancel must not retroactively prevent an
            // earlier fill in the same session.
            left.effective_at
                .cmp(&right.effective_at)
                .then(execution_priority(left).cmp(&execution_priority(right)))
                .then_with(|| limit_aggressiveness_cmp(left, right))
                .then(left.intent_id.cmp(&right.intent_id))
        });

        for intent in due_intents {
            if self.completed_intent_ids.contains(&intent.intent_id) {
                continue;
            }
            if intent.intent_kind == IntentKindV3::Cancel {
                self.process_cancel(input, intent)?;
                continue;
            }
            let bar = bars_by_symbol
                .get(intent.symbol.as_str())
                .copied()
                .ok_or_else(|| EngineError::new("v3 intent symbol has no session bar"))?;
            let requested_quantity = self.remaining_quantity_for(intent);
            if requested_quantity <= 0 {
                self.pending_orders.remove(&intent.intent_id);
                self.completed_intent_ids.insert(intent.intent_id.clone());
                continue;
            }

            if intent.intent_kind != IntentKindV3::Order {
                self.reject_order(intent, "unsupported_intent_kind", requested_quantity);
                continue;
            }
            if intent.order_type == OrderTypeV3::Limit && intent.limit_price_atoms.is_none() {
                self.reject_order(intent, "missing_limit_price", requested_quantity);
                continue;
            }
            if self.delisted_symbols.contains(&intent.symbol) {
                self.reject_order(intent, "delisted", requested_quantity);
                continue;
            }
            if bar.trading_status != TradingStatusV3::Tradable {
                if matches!(intent.time_in_force, TimeInForceV3::Gtc) {
                    self.defer_or_expire(intent, "not_tradable", requested_quantity)?;
                } else {
                    self.reject_order(intent, "not_tradable", requested_quantity);
                }
                continue;
            }
            let price_limit_blocks = matches!(
                (intent.side, bar.price_limit_state),
                (SideV3::Buy, PriceLimitStateV3::LimitUp)
                    | (SideV3::Sell, PriceLimitStateV3::LimitDown)
            );
            if price_limit_blocks {
                if matches!(intent.time_in_force, TimeInForceV3::Gtc) {
                    self.defer_or_expire(intent, "price_limit", requested_quantity)?;
                } else {
                    self.reject_order(intent, "price_limit", requested_quantity);
                }
                continue;
            }

            let max_quantity = participation_capacity(
                bar.raw.volume_quantity.0,
                input.account.max_participation_rate_atoms.0,
                input.account.rate_scale,
            )?;
            // A split/reverse-split can change the valid board-lot unit.  The
            // unit is part of the deterministic session state, so capacity
            // rounding must use the post-action unit rather than the account's
            // initial lot size.
            let lot_size =
                adjusted_lot_size_for_symbol_at(input, &intent.symbol, session.session_seq)?;
            let used_volume = used_volume_by_symbol
                .get(&intent.symbol)
                .copied()
                .unwrap_or(0);
            let remaining_capacity = checked_sub(
                max_quantity,
                used_volume,
                "v3 remaining participation capacity",
            )?;
            let capacity_quantity = remaining_capacity
                .checked_div(lot_size)
                .ok_or_else(|| EngineError::new("v3 lot size is zero"))?
                .checked_mul(lot_size)
                .ok_or_else(|| EngineError::new("v3 participation lot capacity overflow"))?;
            let quantity = requested_quantity.min(capacity_quantity);
            if quantity == 0 {
                self.defer_or_expire(intent, "volume_cap", requested_quantity)?;
                continue;
            }

            let is_short = intent.book == PositionBookV3::ResearchShort;
            let position_quantity = if is_short {
                self.short_position_quantity(&intent.symbol)?
            } else {
                self.position_quantity(&intent.symbol)?
            };
            let close_side = if is_short { SideV3::Buy } else { SideV3::Sell };
            let open_side = if is_short { SideV3::Sell } else { SideV3::Buy };
            if intent.side == close_side && intent.position_effect == PositionEffectV3::Close {
                let eligible = if is_short {
                    self.short_eligible_quantity(&intent.symbol, session.session_seq)?
                } else {
                    self.eligible_quantity(&intent.symbol, session.session_seq)?
                };
                if position_quantity < quantity {
                    self.reject_order(intent, "insufficient_position", requested_quantity);
                    continue;
                }
                if eligible < quantity {
                    self.reject_order(intent, "t_plus_one", requested_quantity);
                    continue;
                }
            } else if intent.side != open_side || intent.position_effect != PositionEffectV3::Open {
                self.reject_order(intent, "unsupported_side_effect", requested_quantity);
                continue;
            }

            let (fill_price, slippage_per_unit) = match (intent.order_type, intent.side) {
                (OrderTypeV3::Market, SideV3::Buy) => (
                    checked_add(
                        bar.raw.open_atoms.0,
                        input.account.market_slippage_atoms.0,
                        "v3 buy fill price",
                    )?,
                    input.account.market_slippage_atoms.0,
                ),
                (OrderTypeV3::Market, SideV3::Sell) => (
                    checked_sub(
                        bar.raw.open_atoms.0,
                        input.account.market_slippage_atoms.0,
                        "v3 sell fill price",
                    )?,
                    input.account.market_slippage_atoms.0,
                ),
                (OrderTypeV3::Limit, SideV3::Buy) => {
                    let limit = intent.limit_price_atoms.unwrap().0;
                    if bar.raw.open_atoms.0 <= limit {
                        (bar.raw.open_atoms.0, 0)
                    } else if bar.raw.low_atoms.0 <= limit {
                        (limit, 0)
                    } else {
                        self.defer_or_expire(intent, "limit_not_touched", requested_quantity)?;
                        continue;
                    }
                }
                (OrderTypeV3::Limit, SideV3::Sell) => {
                    let limit = intent.limit_price_atoms.unwrap().0;
                    if bar.raw.open_atoms.0 >= limit {
                        (bar.raw.open_atoms.0, 0)
                    } else if bar.raw.high_atoms.0 >= limit {
                        (limit, 0)
                    } else {
                        self.defer_or_expire(intent, "limit_not_touched", requested_quantity)?;
                        continue;
                    }
                }
            };
            if fill_price <= 0 {
                self.reject_order(intent, "invalid_fill_price", requested_quantity);
                continue;
            }
            let notional = checked_mul(fill_price, quantity, "v3 fill notional")?;
            let (fee, raw_commission) = self.commission_for_fill(
                intent,
                notional,
                input.account.commission_rate_atoms.0,
                input.account.minimum_commission_atoms.0,
                input.account.rate_scale,
            )?;
            let stamp_duty = if intent.side == SideV3::Sell {
                rate_charge(
                    notional,
                    input.account.stamp_duty_rate_atoms.0,
                    input.account.rate_scale,
                )?
            } else {
                0
            };
            let slippage = checked_mul(slippage_per_unit, quantity, "v3 fill slippage")?;

            let mut frozen_margin_delta = 0_i128;
            let mut isolated_proceeds_delta = 0_i128;
            let mut realized_pnl_delta = 0_i128;
            let (notional_delta, fee_delta, stamp_delta) =
                match (intent.book, intent.side, intent.position_effect) {
                    (PositionBookV3::CashLong, SideV3::Buy, PositionEffectV3::Open) => {
                        let debit = checked_add(
                            checked_add(notional, fee, "v3 buy debit")?,
                            stamp_duty,
                            "v3 buy total debit",
                        )?;
                        if debit > self.available_cash_atoms.0 {
                            self.reject_order(intent, "insufficient_cash", requested_quantity);
                            continue;
                        }
                        self.available_cash_atoms = Atom(checked_sub(
                            self.available_cash_atoms.0,
                            debit,
                            "v3 available cash after buy",
                        )?);
                        self.lots_by_symbol
                            .get_mut(&intent.symbol)
                            .ok_or_else(|| EngineError::new("v3 buy symbol is not in the account"))?
                            .push(LotV3 {
                                quantity_atoms: Atom(quantity),
                                acquired_session_seq: session.session_seq,
                                entry_price_atoms: Some(Atom(fill_price)),
                                cost_basis_atoms: Atom(notional),
                                allocated_margin_atoms: Atom::ZERO,
                                allocated_proceeds_atoms: Atom::ZERO,
                            });
                        (-notional, -fee, -stamp_duty)
                    }
                    (PositionBookV3::CashLong, SideV3::Sell, PositionEffectV3::Close) => {
                        let entry_notional = self.consume_eligible_lots(
                            &intent.symbol,
                            quantity,
                            session.session_seq,
                        )?;
                        let costs = checked_add(fee, stamp_duty, "v3 sell costs")?;
                        self.available_cash_atoms = Atom(checked_add(
                            self.available_cash_atoms.0,
                            checked_sub(notional, costs, "v3 sell proceeds")?,
                            "v3 available cash after sell",
                        )?);
                        if self.position_quantity(&intent.symbol)? == 0 {
                            self.closed_trade_count =
                                self.closed_trade_count.checked_add(1).ok_or_else(|| {
                                    EngineError::new("v3 closed trade count overflow")
                                })?;
                        }
                        realized_pnl_delta =
                            checked_sub(notional, entry_notional, "v3 long realized pnl")?;
                        (notional, -fee, -stamp_duty)
                    }
                    (PositionBookV3::ResearchShort, SideV3::Sell, PositionEffectV3::Open) => {
                        let margin = rate_charge(
                            notional,
                            input.account.research_short_margin_rate_atoms.0,
                            input.account.rate_scale,
                        )?;
                        let debit = checked_add(
                            checked_add(notional, fee, "v3 short open debit")?,
                            stamp_duty,
                            "v3 short open total debit",
                        )?;
                        if debit > self.available_cash_atoms.0 {
                            self.reject_order(
                                intent,
                                "insufficient_cash_for_short",
                                requested_quantity,
                            );
                            continue;
                        }
                        self.available_cash_atoms = Atom(checked_sub(
                            self.available_cash_atoms.0,
                            debit,
                            "v3 available cash after short open",
                        )?);
                        self.frozen_margin_atoms = Atom(checked_add(
                            self.frozen_margin_atoms.0,
                            margin,
                            "v3 frozen short margin",
                        )?);
                        self.isolated_short_proceeds_atoms = Atom(checked_add(
                            self.isolated_short_proceeds_atoms.0,
                            notional,
                            "v3 isolated short proceeds",
                        )?);
                        self.short_lots_by_symbol
                            .get_mut(&intent.symbol)
                            .ok_or_else(|| {
                                EngineError::new("v3 short symbol is not in the account")
                            })?
                            .push(LotV3 {
                                quantity_atoms: Atom(quantity),
                                acquired_session_seq: session.session_seq,
                                entry_price_atoms: Some(Atom(fill_price)),
                                cost_basis_atoms: Atom::ZERO,
                                allocated_margin_atoms: Atom(margin),
                                allocated_proceeds_atoms: Atom(notional),
                            });
                        frozen_margin_delta = margin;
                        isolated_proceeds_delta = notional;
                        (-notional, -fee, -stamp_duty)
                    }
                    (PositionBookV3::ResearchShort, SideV3::Buy, PositionEffectV3::Close) => {
                        let (released_margin, released_proceeds) = self
                            .consume_short_eligible_lots(
                                &intent.symbol,
                                quantity,
                                session.session_seq,
                            )?;
                        let costs = checked_add(fee, stamp_duty, "v3 short cover costs")?;
                        let release = checked_add(
                            released_margin,
                            released_proceeds,
                            "v3 short cover isolated release",
                        )?;
                        self.available_cash_atoms = Atom(checked_add(
                            self.available_cash_atoms.0,
                            checked_sub(
                                release,
                                checked_add(notional, costs, "v3 short cover debit")?,
                                "v3 short cover settlement",
                            )?,
                            "v3 available cash after short cover",
                        )?);
                        self.frozen_margin_atoms = Atom(checked_sub(
                            self.frozen_margin_atoms.0,
                            released_margin,
                            "v3 released short margin",
                        )?);
                        self.isolated_short_proceeds_atoms = Atom(checked_sub(
                            self.isolated_short_proceeds_atoms.0,
                            released_proceeds,
                            "v3 released short proceeds",
                        )?);
                        realized_pnl_delta =
                            checked_sub(released_proceeds, notional, "v3 short realized pnl")?;
                        frozen_margin_delta = -released_margin;
                        isolated_proceeds_delta = -released_proceeds;
                        if self.short_position_quantity(&intent.symbol)? == 0 {
                            self.closed_trade_count =
                                self.closed_trade_count.checked_add(1).ok_or_else(|| {
                                    EngineError::new("v3 closed trade count overflow")
                                })?;
                        }
                        (-notional, -fee, -stamp_duty)
                    }
                    _ => {
                        self.reject_order(intent, "unsupported_side_effect", requested_quantity);
                        continue;
                    }
                };

            self.total_fees_atoms =
                Atom(checked_add(self.total_fees_atoms.0, fee, "v3 total fees")?);
            self.total_stamp_duty_atoms = Atom(checked_add(
                self.total_stamp_duty_atoms.0,
                stamp_duty,
                "v3 total stamp duty",
            )?);
            self.total_slippage_atoms = Atom(checked_add(
                self.total_slippage_atoms.0,
                slippage,
                "v3 total slippage",
            )?);
            let volume_used_before_fill = used_volume_by_symbol
                .get(&intent.symbol)
                .copied()
                .unwrap_or(0);
            let volume_before = Atom(checked_sub(
                bar.raw.volume_quantity.0,
                volume_used_before_fill,
                "v3 fill volume before",
            )?);
            let used_volume = used_volume_by_symbol
                .entry(intent.symbol.clone())
                .or_insert(0);
            *used_volume = checked_add(*used_volume, quantity, "v3 used volume")?;
            let remaining_after_fill =
                checked_sub(requested_quantity, quantity, "v3 order remaining quantity")?;
            if remaining_after_fill > 0 {
                let filled_total = checked_sub(
                    intent.quantity.0,
                    remaining_after_fill,
                    "v3 order filled quantity",
                )?;
                let first_fill_session_seq = {
                    let pending = self
                        .pending_orders
                        .entry(intent.intent_id.clone())
                        .or_insert(PendingOrderV3 {
                            remaining_quantity: Atom(remaining_after_fill),
                            filled_quantity: Atom::ZERO,
                            commission_charged_atoms: Atom::ZERO,
                            raw_commission_accrued_atoms: Atom::ZERO,
                            first_fill_session_seq: None,
                            last_fill_session_seq: None,
                        });
                    pending.remaining_quantity = Atom(remaining_after_fill);
                    pending.filled_quantity = Atom(filled_total);
                    pending.commission_charged_atoms = Atom(checked_add(
                        pending.commission_charged_atoms.0,
                        fee,
                        "v3 cumulative commission",
                    )?);
                    pending.raw_commission_accrued_atoms = Atom(checked_add(
                        pending.raw_commission_accrued_atoms.0,
                        raw_commission,
                        "v3 cumulative raw commission",
                    )?);
                    if pending.first_fill_session_seq.is_none() {
                        pending.first_fill_session_seq = Some(session.session_seq);
                    }
                    pending.last_fill_session_seq = Some(session.session_seq);
                    pending.first_fill_session_seq
                };
                if matches!(intent.time_in_force, TimeInForceV3::Day) {
                    self.pending_orders.remove(&intent.intent_id);
                    self.record_order(
                        intent,
                        "expired",
                        Some("day_expired"),
                        first_fill_session_seq,
                        remaining_after_fill,
                    );
                    self.completed_intent_ids.insert(intent.intent_id.clone());
                } else {
                    self.record_order(
                        intent,
                        "partial",
                        None,
                        first_fill_session_seq,
                        remaining_after_fill,
                    );
                }
            } else {
                self.pending_orders.remove(&intent.intent_id);
                self.record_order(intent, "filled", None, Some(session.session_seq), 0);
                self.completed_intent_ids.insert(intent.intent_id.clone());
            }
            let fill_number = self
                .fills
                .iter()
                .filter(|fill| fill.intent_id == intent.intent_id)
                .count();
            let fill_id = if fill_number == 0 {
                format!("fill:{}", intent.intent_id)
            } else {
                format!("fill:{}:{}", intent.intent_id, fill_number + 1)
            };
            self.fills.push(FillRecordV3 {
                fill_id,
                intent_id: intent.intent_id.clone(),
                intent_seq: intent.intent_seq,
                symbol: intent.symbol.clone(),
                book: intent.book,
                session_seq: session.session_seq,
                side: intent.side,
                position_effect: intent.position_effect,
                quantity: Atom(quantity),
                fill_price_atoms: Atom(fill_price),
                notional_atoms: Atom(notional),
                fee_atoms: Atom(fee),
                stamp_duty_atoms: Atom(stamp_duty),
                slippage_atoms: Atom(slippage),
                liquidity: "taker".to_owned(),
                volume_before,
                volume_after: Atom(checked_sub(
                    volume_before.0,
                    quantity,
                    "v3 remaining bar volume",
                )?),
                remaining_quantity: Atom(remaining_after_fill),
                frozen_margin_delta_atoms: Atom(frozen_margin_delta),
                isolated_proceeds_delta_atoms: Atom(isolated_proceeds_delta),
                condition_intent_id: intent.condition_intent_id.clone(),
            });
            let (signed_quantity, eligible_quantity) = if is_short {
                (
                    -self.short_position_quantity(&intent.symbol)?,
                    -self.short_eligible_quantity(&intent.symbol, session.session_seq)?,
                )
            } else {
                (
                    self.position_quantity(&intent.symbol)?,
                    self.eligible_quantity(&intent.symbol, session.session_seq)?,
                )
            };
            self.positions.push(PositionRecordV3 {
                intent_id: intent.intent_id.clone(),
                symbol: intent.symbol.clone(),
                book: intent.book,
                session_seq: session.session_seq,
                signed_quantity: Atom(signed_quantity),
                eligible_quantity: Atom(eligible_quantity),
            });
            self.cash_ledger.push(CashRecordV3 {
                intent_id: intent.intent_id.clone(),
                symbol: intent.symbol.clone(),
                book: intent.book,
                session_seq: session.session_seq,
                notional_delta_atoms: Atom(notional_delta),
                fee_delta_atoms: Atom(fee_delta),
                stamp_duty_delta_atoms: Atom(stamp_delta),
                realized_pnl_delta_atoms: Atom(realized_pnl_delta),
                resulting_available_cash_atoms: self.available_cash_atoms,
                frozen_margin_delta_atoms: Atom(frozen_margin_delta),
                isolated_proceeds_delta_atoms: Atom(isolated_proceeds_delta),
            });
        }

        let (long_market_value, short_market_value) = input.account.symbols.iter().try_fold(
            (0_i128, 0_i128),
            |(long_total, short_total), symbol| {
                let close = bars_by_symbol
                    .get(symbol.as_str())
                    .ok_or_else(|| EngineError::new("v3 market-value symbol has no session bar"))?
                    .raw
                    .close_atoms
                    .0;
                let long_quantity = self.position_quantity(symbol)?;
                let short_quantity = self.short_position_quantity(symbol)?;
                Ok::<(i128, i128), EngineError>((
                    checked_add(
                        long_total,
                        checked_mul(long_quantity, close, "v3 marked long value")?,
                        "v3 long market value",
                    )?,
                    checked_add(
                        short_total,
                        checked_mul(short_quantity, close, "v3 marked short liability")?,
                        "v3 short market value",
                    )?,
                ))
            },
        )?;
        let market_value =
            checked_sub(long_market_value, short_market_value, "v3 net market value")?;
        let gross_market_value = checked_add(
            long_market_value,
            short_market_value,
            "v3 gross market value",
        )?;
        let equity_with_cash = checked_add(
            self.available_cash_atoms.0,
            market_value,
            "v3 marked equity cash",
        )?;
        let equity_with_margin = checked_add(
            equity_with_cash,
            self.frozen_margin_atoms.0,
            "v3 marked equity margin",
        )?;
        let equity = checked_add(
            equity_with_margin,
            self.isolated_short_proceeds_atoms.0,
            "v3 marked equity proceeds",
        )?;
        self.peak_equity_atoms = Atom(self.peak_equity_atoms.0.max(equity));
        let drawdown = checked_sub(equity, self.peak_equity_atoms.0, "v3 drawdown")?;
        let drawdown_rate = checked_div(
            checked_mul(drawdown, input.account.rate_scale, "v3 drawdown numerator")?,
            self.peak_equity_atoms.0,
            "v3 drawdown rate",
        )?;
        self.max_drawdown_atoms = Atom(self.max_drawdown_atoms.0.min(drawdown));
        self.max_drawdown_rate_atoms = Atom(self.max_drawdown_rate_atoms.0.min(drawdown_rate));
        self.equity_curve.push(EquityPointV3 {
            session_seq: session.session_seq,
            timestamp: session.timestamp.clone(),
            available_cash_atoms: self.available_cash_atoms,
            long_market_value_atoms: Atom(long_market_value),
            short_liability_atoms: Atom(short_market_value),
            gross_market_value_atoms: Atom(gross_market_value),
            net_market_value_atoms: Atom(market_value),
            market_value_atoms: Atom(market_value),
            equity_atoms: Atom(equity),
            frozen_margin_atoms: self.frozen_margin_atoms,
            isolated_short_proceeds_atoms: self.isolated_short_proceeds_atoms,
        });
        self.drawdown_curve.push(DrawdownPointV3 {
            session_seq: session.session_seq,
            equity_atoms: Atom(equity),
            peak_equity_atoms: self.peak_equity_atoms,
            drawdown_atoms: Atom(drawdown),
            drawdown_rate_atoms: Atom(drawdown_rate),
        });
        Ok(())
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct CheckpointV3 {
    checkpoint_schema_version: u32,
    engine_version: String,
    input_schema_version: u32,
    output_schema_version: u32,
    account_model: String,
    calculation_context_sha256: String,
    input_sha256: String,
    processed_prefix_sha256: String,
    total_session_count: usize,
    next_unprocessed_session_index: usize,
    batch_session_count: usize,
    status: String,
    state_sha256: String,
    state: StateV3,
}

pub fn run_engine_v3(input_bytes: &[u8]) -> Result<Vec<u8>, EngineError> {
    let input = parse_input_v3(input_bytes)?;
    let mut state = StateV3::new(&input.account);
    for session in &input.sessions {
        state.process_session(&input, session)?;
    }
    serialize_output_v3(finish_v3(state, &input)?)
}

pub fn start_engine_checkpoint_v3(
    input_bytes: &[u8],
    calculation_context_sha256: &str,
    batch_session_count: usize,
) -> Result<Vec<u8>, EngineError> {
    validate_context_v3(calculation_context_sha256)?;
    if batch_session_count == 0 {
        return Err(checkpoint_error_v3("batch_size_zero"));
    }
    let input = parse_input_v3(input_bytes)
        .map_err(|error| checkpoint_error_detail_v3("invalid_checkpoint", error))?;
    make_checkpoint_v3(
        &input,
        calculation_context_sha256,
        batch_session_count,
        0,
        StateV3::new(&input.account),
    )
}

pub fn step_engine_checkpoint_v3(
    input_bytes: &[u8],
    calculation_context_sha256: &str,
    checkpoint_bytes: &[u8],
) -> Result<Vec<u8>, EngineError> {
    let (input, checkpoint) =
        decode_checkpoint_v3(input_bytes, calculation_context_sha256, checkpoint_bytes)?;
    if checkpoint.status == "complete" {
        return Ok(checkpoint_bytes.to_vec());
    }
    let mut state = checkpoint.state;
    let start = checkpoint.next_unprocessed_session_index;
    let end = start
        .checked_add(checkpoint.batch_session_count)
        .ok_or_else(|| checkpoint_error_v3("cursor_out_of_range"))?
        .min(input.sessions.len());
    for session in &input.sessions[start..end] {
        state
            .process_session(&input, session)
            .map_err(|error| checkpoint_error_detail_v3("state_inconsistent", error))?;
    }
    make_checkpoint_v3(
        &input,
        calculation_context_sha256,
        checkpoint.batch_session_count,
        end,
        state,
    )
}

pub fn finalize_engine_checkpoint_v3(
    input_bytes: &[u8],
    calculation_context_sha256: &str,
    checkpoint_bytes: &[u8],
) -> Result<Vec<u8>, EngineError> {
    let (input, checkpoint) =
        decode_checkpoint_v3(input_bytes, calculation_context_sha256, checkpoint_bytes)?;
    if checkpoint.status != "complete" {
        return Err(checkpoint_error_v3("incomplete"));
    }
    serialize_output_v3(finish_v3(checkpoint.state, &input)?)
        .map_err(|error| checkpoint_error_detail_v3("state_inconsistent", error))
}

fn parse_input_v3(input_bytes: &[u8]) -> Result<EngineInputV3, EngineError> {
    let input: EngineInputV3 = serde_json::from_slice(input_bytes)
        .map_err(|error| EngineError::new(format!("v3 engine input is invalid: {error}")))?;
    validate_input_v3(&input)?;
    Ok(input)
}

fn validate_input_v3(input: &EngineInputV3) -> Result<(), EngineError> {
    if input.schema_version != 3 {
        return Err(EngineError::new(
            "unsupported A-share research v3 input schema",
        ));
    }
    if input.market_rules_version.trim().is_empty() {
        return Err(EngineError::new("v3 market rules version is required"));
    }
    if !input
        .market_rules_version
        .starts_with("cn-a-share-research/")
    {
        return Err(EngineError::new(
            "unsupported v3 A-share research market rules version",
        ));
    }
    let account = &input.account;
    if account.model != "a_share_portfolio_research" {
        return Err(EngineError::new(
            "unsupported A-share research v3 account model",
        ));
    }
    if account.symbols.is_empty()
        || account
            .symbols
            .iter()
            .any(|symbol| symbol.is_empty() || symbol.len() > 64 || symbol.trim() != symbol)
        || account.symbols.windows(2).any(|pair| pair[0] >= pair[1])
    {
        return Err(EngineError::new(
            "v3 account symbols must be nonempty and strictly sorted",
        ));
    }
    if account.price_scale == 0 || account.price_scale != account.cash_scale {
        return Err(EngineError::new(
            "v3 price and cash scales must be equal and nonzero",
        ));
    }
    if account.rate_scale <= 0 || account.starting_cash_atoms.0 <= 0 {
        return Err(EngineError::new(
            "v3 rate scale and starting cash must be positive",
        ));
    }
    if account.lot_size <= 0 {
        return Err(EngineError::new("v3 lot size must be positive"));
    }
    for (name, value) in [
        (
            "max participation rate",
            account.max_participation_rate_atoms.0,
        ),
        ("commission rate", account.commission_rate_atoms.0),
        ("stamp duty rate", account.stamp_duty_rate_atoms.0),
        (
            "research short margin rate",
            account.research_short_margin_rate_atoms.0,
        ),
    ] {
        if value < 0 || value > account.rate_scale {
            return Err(EngineError::new(format!(
                "v3 {name} must be within the rate scale"
            )));
        }
    }
    if account.minimum_commission_atoms.0 < 0 || account.market_slippage_atoms.0 < 0 {
        return Err(EngineError::new("v3 costs must be non-negative"));
    }
    if account.research_short_margin_rate_atoms.0 != account.rate_scale {
        return Err(EngineError::new(
            "v3 research short requires exactly 100 percent isolated margin",
        ));
    }
    if input.sessions.is_empty()
        || input
            .sessions
            .windows(2)
            .any(|pair| pair[0].session_seq >= pair[1].session_seq)
        || input
            .sessions
            .windows(2)
            .any(|pair| pair[0].timestamp >= pair[1].timestamp)
    {
        return Err(EngineError::new(
            "v3 sessions must be nonempty and strictly increasing",
        ));
    }
    let symbols = account.symbols.as_slice();
    let session_sequences = input
        .sessions
        .iter()
        .map(|session| session.session_seq)
        .collect::<BTreeSet<_>>();
    for session in &input.sessions {
        if session.timestamp.trim().is_empty()
            || session.bars.len() != symbols.len()
            || session
                .bars
                .iter()
                .map(|bar| bar.symbol.as_str())
                .ne(symbols.iter().map(String::as_str))
        {
            return Err(EngineError::new(
                "v3 sessions must contain exactly the sorted account symbols",
            ));
        }
        for bar in &session.bars {
            if bar.trading_status == TradingStatusV3::Missing {
                return Err(EngineError::new(
                    "v3 missing bar/security gap must be resolved before execution",
                ));
            }
            validate_bar_v3(bar)?;
        }
    }
    validate_corporate_actions_v3(input, symbols, &session_sequences)?;
    if input
        .intents
        .windows(2)
        .any(|pair| pair[0].intent_seq >= pair[1].intent_seq)
    {
        return Err(EngineError::new(
            "v3 intents must have increasing intent_seq",
        ));
    }
    let mut intent_ids = BTreeSet::new();
    for intent in &input.intents {
        if intent.intent_id.trim().is_empty()
            || intent.intent_id.len() > 256
            || !intent_ids.insert(intent.intent_id.as_str())
        {
            return Err(EngineError::new(
                "v3 intent ids must be nonempty and unique",
            ));
        }
        if symbols.binary_search(&intent.symbol).is_err() {
            return Err(EngineError::new("v3 intent symbol is not in the account"));
        }
        if intent.known_at >= intent.effective_at {
            return Err(EngineError::new(
                "v3 intent must be known before it is effective",
            ));
        }
        if intent.effective_at.phase != EventPhaseV3::Open
            || !session_sequences.contains(&intent.effective_at.session_seq)
        {
            return Err(EngineError::new(
                "v3 intent must become effective at an existing session open",
            ));
        }
        if intent.intent_kind == IntentKindV3::Order {
            let lot_size = adjusted_lot_size_for_symbol_at(
                input,
                &intent.symbol,
                intent.effective_at.session_seq,
            )?;
            if intent.quantity.0 <= 0 || intent.quantity.0 % lot_size != 0 {
                return Err(EngineError::new("v3 quantity must use whole lots"));
            }
        }
        if intent.intent_kind == IntentKindV3::Cancel && intent.cancelled_intent_id.is_none() {
            return Err(EngineError::new(
                "v3 cancel intent must identify its target",
            ));
        }
        if intent.intent_kind == IntentKindV3::Order
            && intent.order_type == OrderTypeV3::Market
            && intent.limit_price_atoms.is_some()
        {
            return Err(EngineError::new(
                "v3 market order cannot carry a limit price",
            ));
        }
        if intent.intent_kind == IntentKindV3::Order
            && intent.order_type == OrderTypeV3::Limit
            && intent.limit_price_atoms.is_some_and(|price| price.0 <= 0)
        {
            return Err(EngineError::new("v3 limit price must be positive"));
        }
        if intent.condition_intent_id.as_ref().is_some_and(|value| {
            value.trim().is_empty() || value.len() > 256 || value.trim() != value
        }) {
            return Err(EngineError::new(
                "v3 condition intent id must be nonempty and bounded",
            ));
        }
    }
    for intent in &input.intents {
        if let Some(target_id) = intent.cancelled_intent_id.as_deref()
            && intent.intent_kind == IntentKindV3::Cancel
        {
            if target_id == intent.intent_id {
                return Err(EngineError::new("v3 cancel intent cannot target itself"));
            }
            if !intent_ids.contains(target_id) {
                return Err(EngineError::new("v3 cancel target intent is unknown"));
            }
        }
    }
    Ok(())
}

fn validate_corporate_actions_v3(
    input: &EngineInputV3,
    symbols: &[String],
    session_sequences: &BTreeSet<u64>,
) -> Result<(), EngineError> {
    if input.corporate_actions.windows(2).any(|pair| {
        pair[0].effective_at > pair[1].effective_at
            || (pair[0].effective_at == pair[1].effective_at
                && pair[0].action_id >= pair[1].action_id)
    }) {
        return Err(EngineError::new(
            "v3 corporate actions must be sorted by effective event and action id",
        ));
    }

    let mut action_ids = BTreeSet::new();
    let mut delisted_symbols = BTreeSet::new();
    let mut adjusted_units = symbols
        .iter()
        .cloned()
        .map(|symbol| (symbol, input.account.lot_size))
        .collect::<BTreeMap<_, _>>();
    for action in &input.corporate_actions {
        if action.action_id.trim().is_empty()
            || action.action_id.len() > 256
            || !action_ids.insert(action.action_id.as_str())
        {
            return Err(EngineError::new(
                "v3 corporate action ids must be nonempty and unique",
            ));
        }
        if symbols.binary_search(&action.symbol).is_err() {
            return Err(EngineError::new(
                "v3 corporate action symbol is not in the account",
            ));
        }
        if action.effective_at.phase != EventPhaseV3::Open
            || !session_sequences.contains(&action.effective_at.session_seq)
        {
            return Err(EngineError::new(
                "v3 corporate action must become effective at an existing session open",
            ));
        }
        if delisted_symbols.contains(&action.symbol) {
            return Err(EngineError::new(
                "v3 corporate action cannot follow delist settlement",
            ));
        }

        match action.action_type {
            CorporateActionTypeV3::CashDividend => {
                if !matches!(action.cash_per_share_atoms, Some(Atom(value)) if value > 0)
                    || action.numerator.is_some()
                    || action.denominator.is_some()
                    || action.settlement_price_atoms.is_some()
                {
                    return Err(EngineError::new(
                        "v3 cash dividend requires only a positive per-share cash amount",
                    ));
                }
            }
            CorporateActionTypeV3::Split | CorporateActionTypeV3::ReverseSplit => {
                let (Some(numerator), Some(denominator)) = (action.numerator, action.denominator)
                else {
                    return Err(EngineError::new(
                        "v3 split requires numerator and denominator",
                    ));
                };
                if numerator <= 0
                    || denominator <= 0
                    || action.cash_per_share_atoms.is_some()
                    || action.settlement_price_atoms.is_some()
                {
                    return Err(EngineError::new(
                        "v3 split requires only a positive share ratio",
                    ));
                }
                if matches!(action.action_type, CorporateActionTypeV3::Split)
                    && numerator <= denominator
                {
                    return Err(EngineError::new(
                        "v3 split ratio must increase the share quantity",
                    ));
                }
                if matches!(action.action_type, CorporateActionTypeV3::ReverseSplit)
                    && numerator >= denominator
                {
                    return Err(EngineError::new(
                        "v3 reverse split ratio must reduce the share quantity",
                    ));
                }
                let unit = adjusted_units
                    .get_mut(&action.symbol)
                    .ok_or_else(|| EngineError::new("v3 split unit symbol is missing"))?;
                let unit_numerator = checked_mul(*unit, numerator, "v3 split unit numerator")?;
                if unit_numerator % denominator != 0 {
                    return Err(EngineError::new(
                        "v3 split ratio would create fractional shares",
                    ));
                }
                *unit = checked_div(unit_numerator, denominator, "v3 split adjusted unit")?;
                if *unit <= 0 {
                    return Err(EngineError::new(
                        "v3 split ratio would eliminate the share unit",
                    ));
                }
            }
            CorporateActionTypeV3::DelistSettlement => {
                if !matches!(action.settlement_price_atoms, Some(Atom(value)) if value > 0)
                    || action.cash_per_share_atoms.is_some()
                    || action.numerator.is_some()
                    || action.denominator.is_some()
                {
                    return Err(EngineError::new(
                        "v3 delist settlement requires only a positive settlement price",
                    ));
                }
                let session = input
                    .sessions
                    .iter()
                    .find(|session| session.session_seq == action.effective_at.session_seq)
                    .ok_or_else(|| EngineError::new("v3 delist settlement session is missing"))?;
                let bar = session
                    .bars
                    .iter()
                    .find(|bar| bar.symbol == action.symbol)
                    .ok_or_else(|| EngineError::new("v3 delist settlement bar is missing"))?;
                if bar.trading_status != TradingStatusV3::Delisted {
                    return Err(EngineError::new(
                        "v3 delist settlement requires a delisted security state",
                    ));
                }
                delisted_symbols.insert(action.symbol.clone());
            }
        }
    }
    Ok(())
}

/// Return the board-lot unit in force when an order for `symbol` executes.
///
/// Corporate actions are preflight-validated in effective-event order, so this
/// fold is deterministic and cannot produce a zero or fractional unit.  A
/// reverse split may legitimately create a smaller integer unit (for example,
/// 100 shares -> 50 shares); subsequent orders and participation rounding use
/// that adjusted unit so a residual lot remains closeable.
fn adjusted_lot_size_for_symbol_at(
    input: &EngineInputV3,
    symbol: &str,
    session_seq: u64,
) -> Result<i128, EngineError> {
    let mut unit = input.account.lot_size;
    for action in &input.corporate_actions {
        if action.effective_at.session_seq > session_seq {
            break;
        }
        if action.symbol != symbol {
            continue;
        }
        if matches!(
            action.action_type,
            CorporateActionTypeV3::Split | CorporateActionTypeV3::ReverseSplit
        ) {
            let numerator = action
                .numerator
                .ok_or_else(|| EngineError::new("v3 split numerator is required"))?;
            let denominator = action
                .denominator
                .ok_or_else(|| EngineError::new("v3 split denominator is required"))?;
            let scaled = checked_mul(unit, numerator, "v3 adjusted lot numerator")?;
            if scaled % denominator != 0 {
                return Err(EngineError::new(
                    "v3 corporate action would create a fractional lot unit",
                ));
            }
            unit = checked_div(scaled, denominator, "v3 adjusted lot unit")?;
            if unit <= 0 {
                return Err(EngineError::new(
                    "v3 corporate action would eliminate the lot unit",
                ));
            }
        }
    }
    Ok(unit)
}

fn validate_bar_v3(bar: &BarV3) -> Result<(), EngineError> {
    validate_ohlc_v3(
        bar.raw.open_atoms.0,
        bar.raw.high_atoms.0,
        bar.raw.low_atoms.0,
        bar.raw.close_atoms.0,
        "v3 raw bar",
    )?;
    validate_ohlc_v3(
        bar.research.open_atoms.0,
        bar.research.high_atoms.0,
        bar.research.low_atoms.0,
        bar.research.close_atoms.0,
        "v3 research bar",
    )?;
    if bar.raw.volume_quantity.0 < 0 {
        return Err(EngineError::new("v3 bar volume cannot be negative"));
    }
    Ok(())
}

fn validate_ohlc_v3(
    open: i128,
    high: i128,
    low: i128,
    close: i128,
    label: &str,
) -> Result<(), EngineError> {
    if open <= 0 || high <= 0 || low <= 0 || close <= 0 {
        return Err(EngineError::new(format!("{label} prices must be positive")));
    }
    if low > open || low > close || high < open || high < close {
        return Err(EngineError::new(format!(
            "{label} OHLC prices are incoherent"
        )));
    }
    Ok(())
}

fn order_type_priority(order_type: OrderTypeV3) -> u8 {
    match order_type {
        OrderTypeV3::Market => 0,
        OrderTypeV3::Limit => 1,
    }
}

fn execution_priority(intent: &IntentV3) -> u8 {
    if intent.intent_kind == IntentKindV3::Cancel {
        0
    } else {
        order_type_priority(intent.order_type) + 1
    }
}

fn limit_aggressiveness_cmp(left: &IntentV3, right: &IntentV3) -> std::cmp::Ordering {
    if left.order_type != OrderTypeV3::Limit || right.order_type != OrderTypeV3::Limit {
        return std::cmp::Ordering::Equal;
    }
    match (left.side, right.side) {
        (SideV3::Buy, SideV3::Buy) => right.limit_price_atoms.cmp(&left.limit_price_atoms),
        (SideV3::Sell, SideV3::Sell) => left.limit_price_atoms.cmp(&right.limit_price_atoms),
        _ => std::cmp::Ordering::Equal,
    }
}

fn participation_capacity(
    volume_quantity: i128,
    participation_rate: i128,
    rate_scale: i128,
) -> Result<i128, EngineError> {
    let numerator = checked_mul(
        volume_quantity,
        participation_rate,
        "v3 participation numerator",
    )?;
    checked_div(numerator, rate_scale, "v3 participation capacity")
}

fn rate_charge(notional: i128, rate: i128, scale: i128) -> Result<i128, EngineError> {
    if notional == 0 || rate == 0 {
        return Ok(0);
    }
    let numerator = checked_mul(notional, rate, "v3 rate charge numerator")?;
    checked_div(
        checked_add(numerator, scale - 1, "v3 rate charge rounding")?,
        scale,
        "v3 rate charge",
    )
}

fn finish_v3(mut state: StateV3, input: &EngineInputV3) -> Result<OutputV3, EngineError> {
    for intent in &input.intents {
        if !state.completed_intent_ids.contains(&intent.intent_id) {
            let remaining_quantity = state.remaining_quantity_for(intent);
            let first_fill_session_seq = state
                .pending_orders
                .get(&intent.intent_id)
                .and_then(|pending| pending.first_fill_session_seq);
            state.pending_orders.remove(&intent.intent_id);
            state.record_order(
                intent,
                "expired",
                Some("end_of_data"),
                first_fill_session_seq,
                remaining_quantity,
            );
        }
    }
    state.orders.sort_by(|left, right| {
        left.intent_seq
            .cmp(&right.intent_seq)
            .then(left.intent_id.cmp(&right.intent_id))
    });
    let ending_equity = state
        .equity_curve
        .last()
        .map(|point| point.equity_atoms.0)
        .unwrap_or(input.account.starting_cash_atoms.0);
    let fill_count = state.fills.len();
    let net_pnl = checked_sub(
        ending_equity,
        input.account.starting_cash_atoms.0,
        "v3 net pnl",
    )?;
    let total_return_rate = checked_div(
        checked_mul(
            net_pnl,
            input.account.rate_scale,
            "v3 total return numerator",
        )?,
        input.account.starting_cash_atoms.0,
        "v3 total return",
    )?;
    let open_position_count = input
        .account
        .symbols
        .iter()
        .try_fold(0_u64, |count, symbol| {
            let long_open = state.position_quantity(symbol)? != 0;
            let short_open = state.short_position_quantity(symbol)? != 0;
            if !long_open && !short_open {
                Ok(count)
            } else {
                count
                    .checked_add(u64::from(long_open) + u64::from(short_open))
                    .ok_or_else(|| EngineError::new("v3 open position count overflow"))
            }
        })?;
    Ok(OutputV3 {
        schema_version: 3,
        engine_version: ENGINE_VERSION_V3.to_owned(),
        account_model: input.account.model.clone(),
        orders: state.orders,
        fills: state.fills,
        positions: state.positions,
        cash_ledger: state.cash_ledger,
        corporate_action_ledger: state.corporate_action_ledger,
        equity_curve: state.equity_curve,
        drawdown_curve: state.drawdown_curve,
        metrics: MetricsV3 {
            starting_equity_atoms: input.account.starting_cash_atoms,
            ending_equity_atoms: Atom(ending_equity),
            net_pnl_atoms: Atom(net_pnl),
            total_return_rate_atoms: Atom(total_return_rate),
            max_drawdown_atoms: state.max_drawdown_atoms,
            max_drawdown_rate_atoms: state.max_drawdown_rate_atoms,
            total_fees_atoms: state.total_fees_atoms,
            total_stamp_duty_atoms: state.total_stamp_duty_atoms,
            total_slippage_atoms: state.total_slippage_atoms,
            fill_count,
            closed_trade_count: state.closed_trade_count,
            open_position_count,
        },
        costs: CostsV3 {
            commission_atoms: state.total_fees_atoms,
            stamp_duty_atoms: state.total_stamp_duty_atoms,
            slippage_atoms: state.total_slippage_atoms,
        },
        assumptions: AssumptionsV3 {
            fill_model: "a_share_dual_book_market_open_v3".to_owned(),
            partial_fills: true,
            liquidate_on_end: false,
            cash_long: true,
            research_short: true,
            limit_orders: true,
            corporate_actions: true,
            tradability_gates: true,
            t_plus_one: true,
        },
    })
}

fn serialize_output_v3(output: OutputV3) -> Result<Vec<u8>, EngineError> {
    serde_json::to_vec(&output)
        .map_err(|error| EngineError::new(format!("v3 engine output failed: {error}")))
}

fn validate_context_v3(context: &str) -> Result<(), EngineError> {
    if context.len() != 64
        || !context
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(checkpoint_error_v3("invalid_context_hash"));
    }
    Ok(())
}

fn checkpoint_error_v3(code: &str) -> EngineError {
    EngineError::new(format!("[checkpoint_v3:{code}]"))
}

fn checkpoint_error_detail_v3(code: &str, detail: impl std::fmt::Display) -> EngineError {
    EngineError::new(format!("[checkpoint_v3:{code}] {detail}"))
}

fn sha256_hex_v3(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn canonical_input_sha256_v3(input: &EngineInputV3) -> Result<String, EngineError> {
    let bytes = serde_json::to_vec(input)
        .map_err(|error| checkpoint_error_detail_v3("state_inconsistent", error))?;
    Ok(sha256_hex_v3(&bytes))
}

fn prefix_sha256_v3(input: &EngineInputV3, cursor: usize) -> Result<String, EngineError> {
    let prefix = input
        .sessions
        .get(..cursor)
        .ok_or_else(|| checkpoint_error_v3("cursor_out_of_range"))?;
    let bytes = serde_json::to_vec(prefix)
        .map_err(|error| checkpoint_error_detail_v3("state_inconsistent", error))?;
    Ok(sha256_hex_v3(&bytes))
}

fn state_sha256_v3(
    batch_session_count: usize,
    cursor: usize,
    state: &StateV3,
) -> Result<String, EngineError> {
    let bytes = serde_json::to_vec(&(batch_session_count, cursor, state))
        .map_err(|error| checkpoint_error_detail_v3("state_inconsistent", error))?;
    Ok(sha256_hex_v3(&bytes))
}

fn make_checkpoint_v3(
    input: &EngineInputV3,
    context: &str,
    batch_session_count: usize,
    cursor: usize,
    state: StateV3,
) -> Result<Vec<u8>, EngineError> {
    let checkpoint = CheckpointV3 {
        checkpoint_schema_version: CHECKPOINT_SCHEMA_VERSION_V3,
        engine_version: ENGINE_VERSION_V3.to_owned(),
        input_schema_version: input.schema_version,
        output_schema_version: 3,
        account_model: input.account.model.clone(),
        calculation_context_sha256: context.to_owned(),
        input_sha256: canonical_input_sha256_v3(input)?,
        processed_prefix_sha256: prefix_sha256_v3(input, cursor)?,
        total_session_count: input.sessions.len(),
        next_unprocessed_session_index: cursor,
        batch_session_count,
        status: if cursor == input.sessions.len() {
            "complete".to_owned()
        } else {
            "running".to_owned()
        },
        state_sha256: state_sha256_v3(batch_session_count, cursor, &state)?,
        state,
    };
    serde_json::to_vec(&checkpoint)
        .map_err(|error| checkpoint_error_detail_v3("state_inconsistent", error))
}

fn decode_checkpoint_v3(
    input_bytes: &[u8],
    context: &str,
    checkpoint_bytes: &[u8],
) -> Result<(EngineInputV3, CheckpointV3), EngineError> {
    validate_context_v3(context)?;
    let input = parse_input_v3(input_bytes)
        .map_err(|error| checkpoint_error_detail_v3("invalid_checkpoint", error))?;
    let checkpoint: CheckpointV3 = serde_json::from_slice(checkpoint_bytes)
        .map_err(|error| checkpoint_error_detail_v3("invalid_checkpoint", error))?;
    if checkpoint.checkpoint_schema_version != CHECKPOINT_SCHEMA_VERSION_V3
        || checkpoint.engine_version != ENGINE_VERSION_V3
        || checkpoint.input_schema_version != 3
        || checkpoint.output_schema_version != 3
        || checkpoint.account_model != input.account.model
        || checkpoint.calculation_context_sha256 != context
        || checkpoint.input_sha256 != canonical_input_sha256_v3(&input)?
        || checkpoint.total_session_count != input.sessions.len()
        || checkpoint.batch_session_count == 0
        || checkpoint.next_unprocessed_session_index > input.sessions.len()
    {
        return Err(checkpoint_error_v3("state_inconsistent"));
    }
    if checkpoint.processed_prefix_sha256
        != prefix_sha256_v3(&input, checkpoint.next_unprocessed_session_index)?
        || checkpoint.state_sha256
            != state_sha256_v3(
                checkpoint.batch_session_count,
                checkpoint.next_unprocessed_session_index,
                &checkpoint.state,
            )?
    {
        return Err(checkpoint_error_v3("state_inconsistent"));
    }
    let expected_status = if checkpoint.next_unprocessed_session_index == input.sessions.len() {
        "complete"
    } else {
        "running"
    };
    if checkpoint.status != expected_status {
        return Err(checkpoint_error_v3("state_inconsistent"));
    }
    Ok((input, checkpoint))
}
