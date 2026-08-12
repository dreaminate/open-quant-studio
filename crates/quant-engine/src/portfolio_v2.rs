use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use super::{Atom, EngineError, checked_add, checked_div, checked_mul, checked_sub};

const ENGINE_VERSION_V2: &str = "oqs-quant-engine/0.2.0";
const CHECKPOINT_SCHEMA_VERSION_V2: u32 = 2;

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct EngineInputV2 {
    schema_version: u32,
    account: PortfolioAccountV2,
    sessions: Vec<PortfolioSessionV2>,
    intents: Vec<PortfolioIntentV2>,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct PortfolioAccountV2 {
    model: String,
    symbols: Vec<String>,
    price_scale: u32,
    cash_scale: u32,
    rate_scale: i128,
    starting_balance_atoms: Atom,
    lot_size: i128,
    commission_rate_atoms: Atom,
    stamp_duty_rate_atoms: Atom,
    slippage_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PortfolioSessionV2 {
    session_seq: u64,
    timestamp: String,
    bars: Vec<PortfolioBarV2>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PortfolioBarV2 {
    symbol: String,
    open_atoms: Atom,
    high_atoms: Atom,
    low_atoms: Atom,
    close_atoms: Atom,
    can_buy: bool,
    can_sell: bool,
}

#[derive(Clone, Copy, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
enum SideV2 {
    Buy,
    Sell,
}

#[derive(Clone, Copy, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
enum PositionEffectV2 {
    Open,
    Close,
}

#[derive(Clone, Copy, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
enum OrderTypeV2 {
    Market,
}

#[derive(Clone, Copy, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
enum TimeInForceV2 {
    Day,
}

#[derive(Clone, Copy, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
enum EventPhaseV2 {
    Open,
    Close,
}

#[derive(Clone, Copy, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(deny_unknown_fields)]
struct EventKeyV2 {
    session_seq: u64,
    phase: EventPhaseV2,
    stable_seq: u64,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct PortfolioIntentV2 {
    intent_id: String,
    intent_seq: u64,
    symbol: String,
    side: SideV2,
    position_effect: PositionEffectV2,
    quantity: Atom,
    order_type: OrderTypeV2,
    known_at: EventKeyV2,
    effective_at: EventKeyV2,
    limit_price_atoms: Option<Atom>,
    stop_price_atoms: Option<Atom>,
    time_in_force: TimeInForceV2,
    oco_group: Option<String>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PortfolioLotV2 {
    quantity_atoms: Atom,
    acquired_session_seq: u64,
}

#[derive(Clone, Deserialize, Serialize)]
struct PortfolioOrderRecordV2 {
    intent_id: String,
    intent_seq: u64,
    symbol: String,
    status: String,
    side: SideV2,
    position_effect: PositionEffectV2,
    order_type: OrderTypeV2,
    quantity: Atom,
    filled_session_seq: Option<u64>,
    filled_phase: Option<String>,
}

#[derive(Clone, Deserialize, Serialize)]
struct PortfolioTradeRecordV2 {
    trade_id: String,
    intent_id: String,
    symbol: String,
    session_seq: u64,
    side: SideV2,
    position_effect: PositionEffectV2,
    quantity: Atom,
    fill_price_atoms: Atom,
    notional_atoms: Atom,
    fee_atoms: Atom,
    stamp_duty_atoms: Atom,
    slippage_atoms: Atom,
    liquidity: String,
}

#[derive(Clone, Deserialize, Serialize)]
struct PortfolioPositionRecordV2 {
    intent_id: String,
    symbol: String,
    session_seq: u64,
    signed_quantity: Atom,
    eligible_quantity: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
struct PortfolioCashRecordV2 {
    intent_id: String,
    symbol: String,
    session_seq: u64,
    notional_delta_atoms: Atom,
    fee_delta_atoms: Atom,
    stamp_duty_delta_atoms: Atom,
    realized_pnl_delta_atoms: Atom,
    funding_delta_atoms: Atom,
    resulting_cash_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
struct PortfolioEquityPointV2 {
    session_seq: u64,
    timestamp: String,
    cash_atoms: Atom,
    market_value_atoms: Atom,
    equity_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
struct PortfolioDrawdownPointV2 {
    session_seq: u64,
    equity_atoms: Atom,
    peak_equity_atoms: Atom,
    drawdown_atoms: Atom,
    drawdown_rate_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
struct PortfolioMetricsV2 {
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
struct PortfolioCostsV2 {
    commission_atoms: Atom,
    stamp_duty_atoms: Atom,
    funding_atoms: Atom,
    slippage_atoms: Atom,
}

#[derive(Clone, Deserialize, Serialize)]
struct PortfolioAssumptionsV2 {
    fill_model: String,
    partial_fills: bool,
    liquidate_on_end: bool,
    research_short: bool,
    research_short_notice: Option<String>,
    one_x_notional: bool,
    shared_cash: bool,
    per_symbol_t_plus_one: bool,
}

#[derive(Serialize)]
struct PortfolioOutputV2 {
    schema_version: u32,
    engine_version: String,
    account_model: String,
    orders: Vec<PortfolioOrderRecordV2>,
    trades: Vec<PortfolioTradeRecordV2>,
    positions: Vec<PortfolioPositionRecordV2>,
    cash_ledger: Vec<PortfolioCashRecordV2>,
    funding_ledger: Vec<serde_json::Value>,
    equity_curve: Vec<PortfolioEquityPointV2>,
    drawdown_curve: Vec<PortfolioDrawdownPointV2>,
    metrics: PortfolioMetricsV2,
    costs: PortfolioCostsV2,
    assumptions: PortfolioAssumptionsV2,
}

#[derive(Clone, Deserialize, Serialize)]
struct PortfolioStateV2 {
    cash_atoms: Atom,
    lots_by_symbol: BTreeMap<String, Vec<PortfolioLotV2>>,
    completed_intent_ids: BTreeSet<String>,
    orders: Vec<PortfolioOrderRecordV2>,
    trades: Vec<PortfolioTradeRecordV2>,
    positions: Vec<PortfolioPositionRecordV2>,
    cash_ledger: Vec<PortfolioCashRecordV2>,
    equity_curve: Vec<PortfolioEquityPointV2>,
    drawdown_curve: Vec<PortfolioDrawdownPointV2>,
    peak_equity_atoms: Atom,
    max_drawdown_atoms: Atom,
    max_drawdown_rate_atoms: Atom,
    total_fees_atoms: Atom,
    total_stamp_duty_atoms: Atom,
    total_slippage_atoms: Atom,
    closed_trade_count: u64,
}

impl PortfolioStateV2 {
    fn new(account: &PortfolioAccountV2) -> Self {
        Self {
            cash_atoms: account.starting_balance_atoms,
            lots_by_symbol: account
                .symbols
                .iter()
                .cloned()
                .map(|symbol| (symbol, Vec::new()))
                .collect(),
            completed_intent_ids: BTreeSet::new(),
            orders: Vec::new(),
            trades: Vec::new(),
            positions: Vec::new(),
            cash_ledger: Vec::new(),
            equity_curve: Vec::new(),
            drawdown_curve: Vec::new(),
            peak_equity_atoms: account.starting_balance_atoms,
            max_drawdown_atoms: Atom::ZERO,
            max_drawdown_rate_atoms: Atom::ZERO,
            total_fees_atoms: Atom::ZERO,
            total_stamp_duty_atoms: Atom::ZERO,
            total_slippage_atoms: Atom::ZERO,
            closed_trade_count: 0,
        }
    }

    fn position_quantity(&self, symbol: &str) -> Result<i128, EngineError> {
        self.lots_by_symbol[symbol]
            .iter()
            .try_fold(0_i128, |total, lot| {
                checked_add(total, lot.quantity_atoms.0, "portfolio position quantity")
            })
    }

    fn eligible_quantity(&self, symbol: &str, session_seq: u64) -> Result<i128, EngineError> {
        self.lots_by_symbol[symbol]
            .iter()
            .filter(|lot| lot.acquired_session_seq < session_seq)
            .try_fold(0_i128, |total, lot| {
                checked_add(total, lot.quantity_atoms.0, "portfolio eligible quantity")
            })
    }

    fn consume_eligible_lots(
        &mut self,
        symbol: &str,
        quantity: i128,
        session_seq: u64,
    ) -> Result<(), EngineError> {
        if self.eligible_quantity(symbol, session_seq)? < quantity {
            return Err(EngineError::new("T+1 eligible quantity is insufficient"));
        }
        let lots = self.lots_by_symbol.get_mut(symbol).unwrap();
        let mut remaining = quantity;
        for lot in lots
            .iter_mut()
            .filter(|lot| lot.acquired_session_seq < session_seq)
        {
            let consumed = lot.quantity_atoms.0.min(remaining);
            lot.quantity_atoms.0 -= consumed;
            remaining -= consumed;
            if remaining == 0 {
                break;
            }
        }
        lots.retain(|lot| lot.quantity_atoms != Atom::ZERO);
        Ok(())
    }

    fn record_expired(&mut self, intent: &PortfolioIntentV2) {
        self.orders.push(PortfolioOrderRecordV2 {
            intent_id: intent.intent_id.clone(),
            intent_seq: intent.intent_seq,
            symbol: intent.symbol.clone(),
            status: "expired".to_owned(),
            side: intent.side,
            position_effect: intent.position_effect,
            order_type: intent.order_type,
            quantity: intent.quantity,
            filled_session_seq: None,
            filled_phase: None,
        });
        self.completed_intent_ids.insert(intent.intent_id.clone());
    }

    fn process_session(
        &mut self,
        input: &EngineInputV2,
        session: &PortfolioSessionV2,
    ) -> Result<(), EngineError> {
        let bars_by_symbol = session
            .bars
            .iter()
            .map(|bar| (bar.symbol.as_str(), bar))
            .collect::<BTreeMap<_, _>>();
        let mut due_intents = input
            .intents
            .iter()
            .filter(|intent| {
                !self.completed_intent_ids.contains(&intent.intent_id)
                    && intent.effective_at.session_seq == session.session_seq
            })
            .collect::<Vec<_>>();
        due_intents.sort_by(|left, right| {
            position_effect_priority(left.position_effect)
                .cmp(&position_effect_priority(right.position_effect))
                .then(left.symbol.cmp(&right.symbol))
                .then(left.intent_seq.cmp(&right.intent_seq))
        });

        for intent in due_intents {
            let bar = bars_by_symbol[intent.symbol.as_str()];
            if (intent.side == SideV2::Buy && !bar.can_buy)
                || (intent.side == SideV2::Sell && !bar.can_sell)
            {
                self.record_expired(intent);
                continue;
            }

            let fill_price = match intent.side {
                SideV2::Buy => checked_add(
                    bar.open_atoms.0,
                    input.account.slippage_atoms.0,
                    "portfolio buy market fill price",
                )?,
                SideV2::Sell => checked_sub(
                    bar.open_atoms.0,
                    input.account.slippage_atoms.0,
                    "portfolio sell market fill price",
                )?,
            };
            let notional = checked_mul(fill_price, intent.quantity.0, "portfolio trade notional")?;
            let fee = rate_charge_v2(
                notional,
                input.account.commission_rate_atoms.0,
                input.account.rate_scale,
            )?;
            let stamp_duty = match intent.side {
                SideV2::Buy => 0,
                SideV2::Sell => rate_charge_v2(
                    notional,
                    input.account.stamp_duty_rate_atoms.0,
                    input.account.rate_scale,
                )?,
            };
            let slippage = checked_mul(
                input.account.slippage_atoms.0,
                intent.quantity.0,
                "portfolio trade slippage",
            )?;
            let notional_delta = match (intent.side, intent.position_effect) {
                (SideV2::Buy, PositionEffectV2::Open) => {
                    let debit = checked_add(notional, fee, "portfolio buy cash debit")?;
                    if debit > self.cash_atoms.0 {
                        return Err(EngineError::new(
                            "portfolio buy/open exceeds shared cash capacity",
                        ));
                    }
                    self.cash_atoms.0 =
                        checked_sub(self.cash_atoms.0, debit, "portfolio buy cash")?;
                    self.lots_by_symbol
                        .get_mut(&intent.symbol)
                        .unwrap()
                        .push(PortfolioLotV2 {
                            quantity_atoms: intent.quantity,
                            acquired_session_seq: session.session_seq,
                        });
                    -notional
                }
                (SideV2::Sell, PositionEffectV2::Close) => {
                    self.consume_eligible_lots(
                        &intent.symbol,
                        intent.quantity.0,
                        session.session_seq,
                    )?;
                    let costs = checked_add(fee, stamp_duty, "portfolio sell costs")?;
                    self.cash_atoms.0 = checked_add(
                        self.cash_atoms.0,
                        checked_sub(notional, costs, "portfolio sell proceeds")?,
                        "portfolio sell cash",
                    )?;
                    if self.position_quantity(&intent.symbol)? == 0 {
                        self.closed_trade_count = self
                            .closed_trade_count
                            .checked_add(1)
                            .ok_or_else(|| EngineError::new("portfolio closed trade overflow"))?;
                    }
                    notional
                }
                _ => {
                    return Err(EngineError::new(
                        "portfolio supports only long buy/open and sell/close intents",
                    ));
                }
            };

            self.total_fees_atoms.0 =
                checked_add(self.total_fees_atoms.0, fee, "portfolio total fees")?;
            self.total_stamp_duty_atoms.0 = checked_add(
                self.total_stamp_duty_atoms.0,
                stamp_duty,
                "portfolio total stamp duty",
            )?;
            self.total_slippage_atoms.0 = checked_add(
                self.total_slippage_atoms.0,
                slippage,
                "portfolio total slippage",
            )?;
            self.orders.push(PortfolioOrderRecordV2 {
                intent_id: intent.intent_id.clone(),
                intent_seq: intent.intent_seq,
                symbol: intent.symbol.clone(),
                status: "filled".to_owned(),
                side: intent.side,
                position_effect: intent.position_effect,
                order_type: intent.order_type,
                quantity: intent.quantity,
                filled_session_seq: Some(session.session_seq),
                filled_phase: Some("open".to_owned()),
            });
            self.trades.push(PortfolioTradeRecordV2 {
                trade_id: format!("fill:{}", intent.intent_id),
                intent_id: intent.intent_id.clone(),
                symbol: intent.symbol.clone(),
                session_seq: session.session_seq,
                side: intent.side,
                position_effect: intent.position_effect,
                quantity: intent.quantity,
                fill_price_atoms: Atom(fill_price),
                notional_atoms: Atom(notional),
                fee_atoms: Atom(fee),
                stamp_duty_atoms: Atom(stamp_duty),
                slippage_atoms: Atom(slippage),
                liquidity: "taker".to_owned(),
            });
            self.positions.push(PortfolioPositionRecordV2 {
                intent_id: intent.intent_id.clone(),
                symbol: intent.symbol.clone(),
                session_seq: session.session_seq,
                signed_quantity: Atom(self.position_quantity(&intent.symbol)?),
                eligible_quantity: Atom(
                    self.eligible_quantity(&intent.symbol, session.session_seq)?,
                ),
            });
            self.cash_ledger.push(PortfolioCashRecordV2 {
                intent_id: intent.intent_id.clone(),
                symbol: intent.symbol.clone(),
                session_seq: session.session_seq,
                notional_delta_atoms: Atom(notional_delta),
                fee_delta_atoms: Atom(-fee),
                stamp_duty_delta_atoms: Atom(-stamp_duty),
                realized_pnl_delta_atoms: Atom::ZERO,
                funding_delta_atoms: Atom::ZERO,
                resulting_cash_atoms: self.cash_atoms,
            });
            self.completed_intent_ids.insert(intent.intent_id.clone());
        }

        let market_value = input
            .account
            .symbols
            .iter()
            .try_fold(0_i128, |total, symbol| {
                let quantity = self.position_quantity(symbol)?;
                let close = bars_by_symbol[symbol.as_str()].close_atoms.0;
                checked_add(
                    total,
                    checked_mul(quantity, close, "portfolio marked position")?,
                    "portfolio market value",
                )
            })?;
        let equity = checked_add(self.cash_atoms.0, market_value, "portfolio marked equity")?;
        self.peak_equity_atoms.0 = self.peak_equity_atoms.0.max(equity);
        let drawdown = checked_sub(equity, self.peak_equity_atoms.0, "portfolio drawdown")?;
        let drawdown_rate = checked_div(
            checked_mul(
                drawdown,
                input.account.rate_scale,
                "portfolio drawdown numerator",
            )?,
            self.peak_equity_atoms.0,
            "portfolio drawdown rate",
        )?;
        self.max_drawdown_atoms.0 = self.max_drawdown_atoms.0.min(drawdown);
        self.max_drawdown_rate_atoms.0 = self.max_drawdown_rate_atoms.0.min(drawdown_rate);
        self.equity_curve.push(PortfolioEquityPointV2 {
            session_seq: session.session_seq,
            timestamp: session.timestamp.clone(),
            cash_atoms: self.cash_atoms,
            market_value_atoms: Atom(market_value),
            equity_atoms: Atom(equity),
        });
        self.drawdown_curve.push(PortfolioDrawdownPointV2 {
            session_seq: session.session_seq,
            equity_atoms: Atom(equity),
            peak_equity_atoms: self.peak_equity_atoms,
            drawdown_atoms: Atom(drawdown),
            drawdown_rate_atoms: Atom(drawdown_rate),
        });
        Ok(())
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct CheckpointV2 {
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
    state: PortfolioStateV2,
}

pub fn run_engine_v2(input_bytes: &[u8]) -> Result<Vec<u8>, EngineError> {
    let input = parse_input_v2(input_bytes)?;
    let mut state = PortfolioStateV2::new(&input.account);
    for session in &input.sessions {
        state.process_session(&input, session)?;
    }
    serialize_output_v2(finish_v2(state, &input)?)
}

pub fn start_engine_checkpoint_v2(
    input_bytes: &[u8],
    calculation_context_sha256: &str,
    batch_session_count: usize,
) -> Result<Vec<u8>, EngineError> {
    validate_context_v2(calculation_context_sha256)?;
    if batch_session_count == 0 {
        return Err(checkpoint_error_v2("batch_size_zero"));
    }
    let input = parse_checkpoint_input_v2(input_bytes)?;
    make_checkpoint_v2(
        &input,
        input_bytes,
        calculation_context_sha256,
        batch_session_count,
        0,
        PortfolioStateV2::new(&input.account),
    )
}

pub fn step_engine_checkpoint_v2(
    input_bytes: &[u8],
    calculation_context_sha256: &str,
    checkpoint_bytes: &[u8],
) -> Result<Vec<u8>, EngineError> {
    let (input, checkpoint) =
        decode_checkpoint_v2(input_bytes, calculation_context_sha256, checkpoint_bytes)?;
    if checkpoint.status == "complete" {
        return Ok(checkpoint_bytes.to_vec());
    }
    let mut state = checkpoint.state;
    let start = checkpoint.next_unprocessed_session_index;
    let end = start
        .saturating_add(checkpoint.batch_session_count)
        .min(input.sessions.len());
    for session in &input.sessions[start..end] {
        state
            .process_session(&input, session)
            .map_err(|error| checkpoint_error_detail_v2("state_inconsistent", error))?;
    }
    make_checkpoint_v2(
        &input,
        input_bytes,
        calculation_context_sha256,
        checkpoint.batch_session_count,
        end,
        state,
    )
}

pub fn finalize_engine_checkpoint_v2(
    input_bytes: &[u8],
    calculation_context_sha256: &str,
    checkpoint_bytes: &[u8],
) -> Result<Vec<u8>, EngineError> {
    let (input, checkpoint) =
        decode_checkpoint_v2(input_bytes, calculation_context_sha256, checkpoint_bytes)?;
    if checkpoint.status != "complete" {
        return Err(checkpoint_error_v2("incomplete"));
    }
    serialize_output_v2(
        finish_v2(checkpoint.state, &input)
            .map_err(|error| checkpoint_error_detail_v2("state_inconsistent", error))?,
    )
    .map_err(|error| checkpoint_error_detail_v2("state_inconsistent", error))
}

fn parse_input_v2(input_bytes: &[u8]) -> Result<EngineInputV2, EngineError> {
    let input: EngineInputV2 = serde_json::from_slice(input_bytes)
        .map_err(|error| EngineError::new(format!("engine input is invalid: {error}")))?;
    validate_input_v2(&input)?;
    Ok(input)
}

fn parse_checkpoint_input_v2(input_bytes: &[u8]) -> Result<EngineInputV2, EngineError> {
    parse_input_v2(input_bytes)
        .map_err(|error| checkpoint_error_detail_v2("invalid_checkpoint", error))
}

fn validate_input_v2(input: &EngineInputV2) -> Result<(), EngineError> {
    let account = &input.account;
    if input.schema_version != 2 {
        return Err(EngineError::new(
            "unsupported portfolio engine input schema",
        ));
    }
    if account.model != "a_share_portfolio_cash" {
        return Err(EngineError::new("unsupported portfolio account model"));
    }
    if account.symbols.is_empty()
        || account.symbols.windows(2).any(|pair| pair[0] >= pair[1])
        || account.symbols.iter().any(String::is_empty)
    {
        return Err(EngineError::new(
            "portfolio account symbols must be nonempty and strictly sorted",
        ));
    }
    if account.price_scale == 0 || account.price_scale != account.cash_scale {
        return Err(EngineError::new(
            "portfolio price and cash scales must be equal and nonzero",
        ));
    }
    if account.rate_scale <= 0 || account.starting_balance_atoms.0 <= 0 {
        return Err(EngineError::new(
            "portfolio rate scale and starting balance must be positive",
        ));
    }
    if account.lot_size != 100 {
        return Err(EngineError::new(
            "portfolio A-share account requires a fixed 100-share lot",
        ));
    }
    if account.commission_rate_atoms.0 < 0
        || account.commission_rate_atoms.0 > account.rate_scale
        || account.stamp_duty_rate_atoms.0 < 0
        || account.stamp_duty_rate_atoms.0 > account.rate_scale
        || account.slippage_atoms.0 < 0
    {
        return Err(EngineError::new(
            "portfolio A-share costs must be non-negative and rates cannot exceed their scale",
        ));
    }
    if input.sessions.is_empty()
        || input
            .sessions
            .windows(2)
            .any(|pair| pair[0].session_seq >= pair[1].session_seq)
    {
        return Err(EngineError::new(
            "portfolio sessions must be nonempty and have increasing session_seq",
        ));
    }
    for session in &input.sessions {
        if session.timestamp.is_empty()
            || session.bars.len() != account.symbols.len()
            || session
                .bars
                .iter()
                .map(|bar| &bar.symbol)
                .ne(account.symbols.iter())
        {
            return Err(EngineError::new(
                "each portfolio session must contain exactly the sorted account symbols",
            ));
        }
        for bar in &session.bars {
            validate_bar_v2(bar, account.slippage_atoms.0)?;
        }
    }
    if input
        .intents
        .windows(2)
        .any(|pair| pair[0].intent_seq >= pair[1].intent_seq)
    {
        return Err(EngineError::new(
            "portfolio intents must have increasing intent_seq",
        ));
    }
    let session_sequences = input
        .sessions
        .iter()
        .map(|session| session.session_seq)
        .collect::<BTreeSet<_>>();
    let mut intent_ids = BTreeSet::new();
    for intent in &input.intents {
        if intent.intent_id.is_empty() || !intent_ids.insert(&intent.intent_id) {
            return Err(EngineError::new(
                "portfolio intent_id must be nonempty and unique",
            ));
        }
        if account.symbols.binary_search(&intent.symbol).is_err() {
            return Err(EngineError::new(
                "portfolio intent symbol does not belong to the account",
            ));
        }
        if intent.known_at >= intent.effective_at
            || intent.effective_at.phase != EventPhaseV2::Open
            || !session_sequences.contains(&intent.effective_at.session_seq)
        {
            return Err(EngineError::new(
                "portfolio intent must be known before an existing session open",
            ));
        }
        if intent.quantity.0 <= 0 || intent.quantity.0 % account.lot_size != 0 {
            return Err(EngineError::new(
                "portfolio A-share quantity must use whole lots",
            ));
        }
        if intent.order_type != OrderTypeV2::Market
            || intent.limit_price_atoms.is_some()
            || intent.stop_price_atoms.is_some()
            || intent.time_in_force != TimeInForceV2::Day
            || intent.oco_group.is_some()
        {
            return Err(EngineError::new(
                "portfolio supports only Market DAY intents without price or OCO fields",
            ));
        }
        if !matches!(
            (intent.side, intent.position_effect),
            (SideV2::Buy, PositionEffectV2::Open) | (SideV2::Sell, PositionEffectV2::Close)
        ) {
            return Err(EngineError::new(
                "portfolio supports only long buy/open and sell/close intents",
            ));
        }
    }
    Ok(())
}

fn validate_bar_v2(bar: &PortfolioBarV2, slippage: i128) -> Result<(), EngineError> {
    if bar.open_atoms.0 <= 0
        || bar.high_atoms.0 <= 0
        || bar.low_atoms.0 <= 0
        || bar.close_atoms.0 <= 0
    {
        return Err(EngineError::new(
            "portfolio bar OHLC prices must be positive",
        ));
    }
    if bar.low_atoms.0 > bar.open_atoms.0
        || bar.low_atoms.0 > bar.close_atoms.0
        || bar.high_atoms.0 < bar.open_atoms.0
        || bar.high_atoms.0 < bar.close_atoms.0
    {
        return Err(EngineError::new(
            "portfolio bar OHLC prices must be coherent",
        ));
    }
    if slippage >= bar.open_atoms.0 {
        return Err(EngineError::new(
            "portfolio slippage must remain below every positive bar open",
        ));
    }
    Ok(())
}

fn position_effect_priority(effect: PositionEffectV2) -> u8 {
    match effect {
        PositionEffectV2::Close => 0,
        PositionEffectV2::Open => 1,
    }
}

fn rate_charge_v2(notional: i128, rate: i128, scale: i128) -> Result<i128, EngineError> {
    let numerator = checked_mul(notional, rate, "portfolio rate charge numerator")?;
    if numerator == 0 {
        return Ok(0);
    }
    checked_div(
        checked_add(numerator, scale - 1, "portfolio rate charge rounding")?,
        scale,
        "portfolio rate charge",
    )
}

fn finish_v2(
    mut state: PortfolioStateV2,
    input: &EngineInputV2,
) -> Result<PortfolioOutputV2, EngineError> {
    for intent in &input.intents {
        if !state.completed_intent_ids.contains(&intent.intent_id) {
            state.record_expired(intent);
        }
    }
    let ending_equity = state
        .equity_curve
        .last()
        .map(|point| point.equity_atoms.0)
        .unwrap_or(input.account.starting_balance_atoms.0);
    let net_pnl = checked_sub(
        ending_equity,
        input.account.starting_balance_atoms.0,
        "portfolio net pnl",
    )?;
    let total_return_rate = checked_div(
        checked_mul(
            net_pnl,
            input.account.rate_scale,
            "portfolio total return numerator",
        )?,
        input.account.starting_balance_atoms.0,
        "portfolio total return",
    )?;
    let fill_count = state.trades.len();
    let open_position_count = state
        .lots_by_symbol
        .keys()
        .try_fold(0_u64, |count, symbol| {
            if state.position_quantity(symbol)? == 0 {
                Ok(count)
            } else {
                count
                    .checked_add(1)
                    .ok_or_else(|| EngineError::new("portfolio open position overflow"))
            }
        })?;
    Ok(PortfolioOutputV2 {
        schema_version: 2,
        engine_version: ENGINE_VERSION_V2.to_owned(),
        account_model: "a_share_portfolio_cash".to_owned(),
        orders: state.orders,
        trades: state.trades,
        positions: state.positions,
        cash_ledger: state.cash_ledger,
        funding_ledger: Vec::new(),
        equity_curve: state.equity_curve,
        drawdown_curve: state.drawdown_curve,
        metrics: PortfolioMetricsV2 {
            starting_equity_atoms: input.account.starting_balance_atoms,
            ending_equity_atoms: Atom(ending_equity),
            net_pnl_atoms: Atom(net_pnl),
            total_return_rate_atoms: Atom(total_return_rate),
            max_drawdown_atoms: state.max_drawdown_atoms,
            max_drawdown_rate_atoms: state.max_drawdown_rate_atoms,
            total_fees_atoms: state.total_fees_atoms,
            total_stamp_duty_atoms: state.total_stamp_duty_atoms,
            total_funding_atoms: Atom::ZERO,
            total_slippage_atoms: state.total_slippage_atoms,
            fill_count,
            closed_trade_count: state.closed_trade_count,
            open_position_count,
        },
        costs: PortfolioCostsV2 {
            commission_atoms: state.total_fees_atoms,
            stamp_duty_atoms: state.total_stamp_duty_atoms,
            funding_atoms: Atom::ZERO,
            slippage_atoms: state.total_slippage_atoms,
        },
        assumptions: PortfolioAssumptionsV2 {
            fill_model: "portfolio_ohlc_market_open_v2".to_owned(),
            partial_fills: false,
            liquidate_on_end: false,
            research_short: false,
            research_short_notice: None,
            one_x_notional: false,
            shared_cash: true,
            per_symbol_t_plus_one: true,
        },
    })
}

fn serialize_output_v2(output: PortfolioOutputV2) -> Result<Vec<u8>, EngineError> {
    serde_json::to_vec(&output)
        .map_err(|error| EngineError::new(format!("portfolio engine output failed: {error}")))
}

fn validate_context_v2(context: &str) -> Result<(), EngineError> {
    if context.len() != 64
        || !context
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(checkpoint_error_v2("invalid_context_hash"));
    }
    Ok(())
}

fn checkpoint_error_v2(code: &str) -> EngineError {
    EngineError::new(format!("[checkpoint_v2:{code}]"))
}

fn checkpoint_error_detail_v2(code: &str, detail: impl std::fmt::Display) -> EngineError {
    EngineError::new(format!("[checkpoint_v2:{code}] {detail}"))
}

fn sha256_hex_v2(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn checkpoint_prefix_sha256_v2(
    input: &EngineInputV2,
    cursor: usize,
) -> Result<String, EngineError> {
    let sessions = input
        .sessions
        .get(..cursor)
        .ok_or_else(|| checkpoint_error_v2("cursor_out_of_range"))?;
    let bytes = serde_json::to_vec(sessions)
        .map_err(|error| checkpoint_error_detail_v2("state_inconsistent", error))?;
    Ok(sha256_hex_v2(&bytes))
}

fn checkpoint_state_sha256_v2(
    batch_session_count: usize,
    cursor: usize,
    state: &PortfolioStateV2,
) -> Result<String, EngineError> {
    let bytes = serde_json::to_vec(&(batch_session_count, cursor, state))
        .map_err(|error| checkpoint_error_detail_v2("state_inconsistent", error))?;
    Ok(sha256_hex_v2(&bytes))
}

fn make_checkpoint_v2(
    input: &EngineInputV2,
    input_bytes: &[u8],
    context: &str,
    batch_session_count: usize,
    cursor: usize,
    state: PortfolioStateV2,
) -> Result<Vec<u8>, EngineError> {
    let checkpoint = CheckpointV2 {
        checkpoint_schema_version: CHECKPOINT_SCHEMA_VERSION_V2,
        engine_version: ENGINE_VERSION_V2.to_owned(),
        input_schema_version: input.schema_version,
        output_schema_version: 2,
        account_model: input.account.model.clone(),
        calculation_context_sha256: context.to_owned(),
        input_sha256: sha256_hex_v2(input_bytes),
        processed_prefix_sha256: checkpoint_prefix_sha256_v2(input, cursor)?,
        total_session_count: input.sessions.len(),
        next_unprocessed_session_index: cursor,
        batch_session_count,
        status: if cursor == input.sessions.len() {
            "complete".to_owned()
        } else {
            "running".to_owned()
        },
        state_sha256: checkpoint_state_sha256_v2(batch_session_count, cursor, &state)?,
        state,
    };
    serde_json::to_vec(&checkpoint)
        .map_err(|error| checkpoint_error_detail_v2("state_inconsistent", error))
}

fn decode_checkpoint_v2(
    input_bytes: &[u8],
    context: &str,
    checkpoint_bytes: &[u8],
) -> Result<(EngineInputV2, CheckpointV2), EngineError> {
    validate_context_v2(context)?;
    let input = parse_checkpoint_input_v2(input_bytes)?;
    let checkpoint: CheckpointV2 = serde_json::from_slice(checkpoint_bytes)
        .map_err(|error| checkpoint_error_detail_v2("invalid_checkpoint", error))?;
    if checkpoint.checkpoint_schema_version != CHECKPOINT_SCHEMA_VERSION_V2
        || checkpoint.engine_version != ENGINE_VERSION_V2
        || checkpoint.input_schema_version != 2
        || checkpoint.output_schema_version != 2
        || checkpoint.account_model != input.account.model
        || checkpoint.calculation_context_sha256 != context
        || checkpoint.input_sha256 != sha256_hex_v2(input_bytes)
        || checkpoint.total_session_count != input.sessions.len()
        || checkpoint.batch_session_count == 0
        || checkpoint.next_unprocessed_session_index > input.sessions.len()
    {
        return Err(checkpoint_error_v2("state_inconsistent"));
    }
    if checkpoint.processed_prefix_sha256
        != checkpoint_prefix_sha256_v2(&input, checkpoint.next_unprocessed_session_index)?
        || checkpoint.state_sha256
            != checkpoint_state_sha256_v2(
                checkpoint.batch_session_count,
                checkpoint.next_unprocessed_session_index,
                &checkpoint.state,
            )?
    {
        return Err(checkpoint_error_v2("state_inconsistent"));
    }
    let expected_status = if checkpoint.next_unprocessed_session_index == input.sessions.len() {
        "complete"
    } else {
        "running"
    };
    if checkpoint.status != expected_status {
        return Err(checkpoint_error_v2("state_inconsistent"));
    }
    Ok((input, checkpoint))
}
