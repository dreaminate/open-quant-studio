import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import test from "node:test";

import {
  validateFormalEngineInputV3,
  validateFormalEngineResultV2,
  validateFormalEngineResultV3,
  validateFormalRunCommand,
  validateFormalRunEvent,
  validateFormalRunManifestV1,
} from "../dist/index.js";

const fixturesDir = join(import.meta.dirname, "../fixtures/v1");
const repoRoot = resolve(import.meta.dirname, "../../..");
const fixture = (name) =>
  JSON.parse(readFileSync(join(fixturesDir, name), "utf8"));

function generatedAShareV3Input() {
  const sourceRoot = join(repoRoot, "services/quant-domain/src");
  const python = spawnSync(
    "uv",
    [
      "run",
      "--project",
      join(repoRoot, "services/quant-domain"),
      "--frozen",
      "python",
      "-c",
      [
        "from quant_domain.data_import import build_data_snapshot",
        "body = b'timestamp,symbol,open,high,low,close,volume\\n2026-01-02T07:00:00Z,AAA.XSHG,10,10.2,9.9,10.1,1000000\\n2026-01-05T07:00:00Z,AAA.XSHG,10.1,10.4,10,10.3,1200000\\n'",
        "material = build_data_snapshot(body, source_format='csv', mapping={'timestamp':'timestamp','symbol':'symbol','open':'open','high':'high','low':'low','close':'close','volume':'volume'}, market='a_share_daily', timezone='Asia/Shanghai', price_basis='raw', cutoff='2026-01-06T00:00:00Z', execution_profile='a-share-v3')",
        "print(material.market_input_body.decode('utf-8'))",
      ].join("\n"),
    ],
    {
      cwd: repoRoot,
      encoding: "utf8",
      env: { ...process.env, PYTHONPATH: sourceRoot },
    },
  );
  assert.equal(python.status, 0, python.stderr);
  return JSON.parse(python.stdout);
}

test("M8 portfolio Formal Run binds its engine, stream and checkpoint profiles", () => {
  const command = fixture("command.formal-run-request-m5.valid.json");
  Object.assign(command.payload, {
    engine_version: "oqs-quant-engine/0.2.0",
    output_schema_version: 2,
    gate_policy_version: "m8-v1",
    strategy_protocol_version: "oqs-strategy-host/m8-portfolio-v1",
    engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v2",
  });
  assert.equal(validateFormalRunCommand(command).valid, true);

  const checkpoint = fixture("event.formal-run-checkpointed.valid.json");
  checkpoint.payload.lifecycle_version = "m8-v1";
  checkpoint.payload.next_session_index = checkpoint.payload.next_bar_index;
  delete checkpoint.payload.next_bar_index;
  assert.equal(validateFormalRunEvent(checkpoint).valid, true);

  const manifest = fixture("formal-run-manifest-m5.valid.json");
  manifest.manifest_version = "m8-v1";
  Object.assign(manifest.run_spec, {
    engine_version: "oqs-quant-engine/0.2.0",
    output_schema_version: 2,
    gate_policy_version: "m8-v1",
    strategy_protocol_version: "oqs-strategy-host/m8-portfolio-v1",
    engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v2",
  });
  manifest.strategy_execution.timing_authority =
    "oqs-strategy-host/m8-portfolio-v1";
  manifest.checkpoint.engine_checkpoint_abi =
    "oqs-quant-engine/checkpoint-v2";
  manifest.checkpoint.final_next_session_index =
    manifest.checkpoint.final_next_bar_index;
  delete manifest.checkpoint.final_next_bar_index;
  manifest.engine_result.schema_version = 2;
  manifest.engine_result.engine_version = "oqs-quant-engine/0.2.0";
  assert.equal(validateFormalRunManifestV1(manifest).valid, true);
});

test("M8 portfolio engine result exposes shared-cash and per-symbol T+1 assumptions", () => {
  const result = {
    schema_version: 2,
    engine_version: "oqs-quant-engine/0.2.0",
    account_model: "a_share_portfolio_cash",
    orders: [],
    trades: [],
    positions: [],
    cash_ledger: [],
    funding_ledger: [],
    equity_curve: [
      {
        session_seq: 1,
        timestamp: "2026-02-02T07:00:00Z",
        cash_atoms: "1000000",
        market_value_atoms: "0",
        equity_atoms: "1000000",
      },
    ],
    drawdown_curve: [
      {
        session_seq: 1,
        equity_atoms: "1000000",
        peak_equity_atoms: "1000000",
        drawdown_atoms: "0",
        drawdown_rate_atoms: "0",
      },
    ],
    metrics: {
      starting_equity_atoms: "1000000",
      ending_equity_atoms: "1000000",
      net_pnl_atoms: "0",
      total_return_rate_atoms: "0",
      max_drawdown_atoms: "0",
      max_drawdown_rate_atoms: "0",
      total_fees_atoms: "0",
      total_stamp_duty_atoms: "0",
      total_funding_atoms: "0",
      total_slippage_atoms: "0",
      fill_count: 0,
      closed_trade_count: 0,
      open_position_count: 0,
    },
    costs: {
      commission_atoms: "0",
      stamp_duty_atoms: "0",
      funding_atoms: "0",
      slippage_atoms: "0",
    },
    assumptions: {
      fill_model: "portfolio_ohlc_market_open_v2",
      partial_fills: false,
      liquidate_on_end: false,
      research_short: false,
      research_short_notice: null,
      one_x_notional: false,
      shared_cash: true,
      per_symbol_t_plus_one: true,
    },
  };

  assert.equal(validateFormalEngineResultV2(result).valid, true);
  result.assumptions.shared_cash = false;
  assert.equal(validateFormalEngineResultV2(result).valid, false);
});

test("A-share v3 manifest and engine result bind the v3 execution profile", () => {
  const manifest = fixture("formal-run-manifest-m5.valid.json");
  manifest.manifest_version = "a-share-v3";
  Object.assign(manifest.run_spec, {
    execution_profile: "a-share-v3",
    engine_version: "oqs-quant-engine/0.3.0",
    output_schema_version: 3,
    gate_policy_version: "a-share-v3",
    strategy_protocol_version: "oqs-strategy-host/a-share-v3",
    engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v3",
  });
  manifest.strategy_execution.timing_authority =
    "oqs-strategy-host/a-share-v3";
  manifest.checkpoint.engine_checkpoint_abi =
    "oqs-quant-engine/checkpoint-v3";
  manifest.checkpoint.final_next_session_index =
    manifest.checkpoint.final_next_bar_index;
  delete manifest.checkpoint.final_next_bar_index;
  manifest.engine_result.schema_version = 3;
  manifest.engine_result.engine_version = "oqs-quant-engine/0.3.0";
  const reviewAttestation = {
    attestation_id: "a9a9a9a9-a9a9-49a9-89a9-a9a9a9a9a9a9",
    status: "approved",
    candidate_revision_id: manifest.run_spec.candidate_revision_id,
    strategy_tree_oid: manifest.run_spec.strategy_tree_oid,
    data_snapshot_sha256: manifest.run_spec.data_snapshot_sha256,
    parameters_sha256: manifest.run_spec.parameters_sha256,
    cost_model_sha256: manifest.run_spec.cost_model_sha256,
    reviewer_id: "test-user",
    reviewed_at: "2026-08-13T00:00:00Z",
  };
  manifest.run_spec.review_attestation = reviewAttestation;
  manifest.run_spec.review_attestation_id = reviewAttestation.attestation_id;
  manifest.run_spec.review_attestation_sha256 = "a".repeat(64);
  manifest.review_attestation = reviewAttestation;
  manifest.review_attestation_id = reviewAttestation.attestation_id;
  manifest.review_attestation_sha256 = "a".repeat(64);
  assert.equal(validateFormalRunManifestV1(manifest).valid, true);

  const result = {
    schema_version: 3,
    engine_version: "oqs-quant-engine/0.3.0",
    account_model: "a_share_portfolio_research",
    orders: [],
    fills: [],
    positions: [],
    cash_ledger: [],
    corporate_action_ledger: [],
    equity_curve: [
      {
        session_seq: 1,
        timestamp: "2026-02-02T07:00:00Z",
        available_cash_atoms: "1000000",
        long_market_value_atoms: "0",
        short_liability_atoms: "0",
        gross_market_value_atoms: "0",
        net_market_value_atoms: "0",
        market_value_atoms: "0",
        equity_atoms: "1000000",
        frozen_margin_atoms: "0",
        isolated_short_proceeds_atoms: "0",
      },
    ],
    drawdown_curve: [
      {
        session_seq: 1,
        equity_atoms: "1000000",
        peak_equity_atoms: "1000000",
        drawdown_atoms: "0",
        drawdown_rate_atoms: "0",
      },
    ],
    metrics: {
      starting_equity_atoms: "1000000",
      ending_equity_atoms: "1000000",
      net_pnl_atoms: "0",
      total_return_rate_atoms: "0",
      max_drawdown_atoms: "0",
      max_drawdown_rate_atoms: "0",
      total_fees_atoms: "0",
      total_stamp_duty_atoms: "0",
      total_slippage_atoms: "0",
      fill_count: 0,
      closed_trade_count: 0,
      open_position_count: 0,
    },
    costs: {
      commission_atoms: "0",
      stamp_duty_atoms: "0",
      slippage_atoms: "0",
    },
    assumptions: {
      fill_model: "a_share_dual_book_market_open_v3",
      partial_fills: true,
      liquidate_on_end: false,
      cash_long: true,
      research_short: true,
      limit_orders: true,
      corporate_actions: true,
      tradability_gates: true,
      t_plus_one: true,
    },
  };
  assert.equal(validateFormalEngineResultV3(result).valid, true);
  result.assumptions.t_plus_one = false;
  assert.equal(validateFormalEngineResultV3(result).valid, false);
});

test("A-share v3 engine input accepts the real local snapshot materialization", () => {
  const input = generatedAShareV3Input();

  assert.equal(validateFormalEngineInputV3(input).valid, true);
  assert.equal(input.schema_version, 3);
  assert.equal(input.market_rules_version, "cn-a-share-research/2026-08-14");
  assert.deepEqual(input.account, {
    model: "a_share_portfolio_research",
    symbols: ["AAA.XSHG"],
    price_scale: 10000,
    cash_scale: 10000,
    rate_scale: 1000000,
    starting_cash_atoms: "1000000000",
    lot_size: 100,
    max_participation_rate_atoms: "100000",
    commission_rate_atoms: "600",
    minimum_commission_atoms: "0",
    stamp_duty_rate_atoms: "1000",
    market_slippage_atoms: "10",
    research_short_margin_rate_atoms: "1000000",
  });
  assert.deepEqual(input.sessions[0].bars[0], {
    symbol: "AAA.XSHG",
    trading_status: "tradable",
    price_limit_state: "none",
    raw: {
      open_atoms: "100000",
      high_atoms: "102000",
      low_atoms: "99000",
      close_atoms: "101000",
      volume_quantity: "1000000",
    },
    research: {
      open_atoms: "100000",
      high_atoms: "102000",
      low_atoms: "99000",
      close_atoms: "101000",
    },
  });

  const extraInputField = structuredClone(input);
  extraInputField.unfrozen_runtime_switch = true;
  assert.equal(validateFormalEngineInputV3(extraInputField).valid, false);
});

test("A-share v3 engine input keeps dual-book orders and cancels structurally strict", () => {
  const source = JSON.parse(
    readFileSync(
      join(repoRoot, "fixtures/backtests/a-share-research-v3-long-t1.json"),
      "utf8",
    ),
  ).input;
  const shortOpen = {
    ...structuredClone(source.intents[0]),
    intent_id: "short-open",
    intent_seq: 4,
    book: "research_short",
    side: "sell",
    position_effect: "open",
    time_in_force: "gtc",
    known_at: { session_seq: 1, phase: "close", stable_seq: 4 },
    effective_at: { session_seq: 2, phase: "open", stable_seq: 4 },
  };
  const cancelShort = {
    ...structuredClone(shortOpen),
    intent_kind: "cancel",
    intent_id: "cancel-short-open",
    intent_seq: 5,
    quantity: "0",
    known_at: { session_seq: 1, phase: "close", stable_seq: 5 },
    effective_at: { session_seq: 2, phase: "open", stable_seq: 5 },
    cancelled_intent_id: "short-open",
  };
  const input = { ...source, intents: [...source.intents, shortOpen, cancelShort] };

  assert.equal(validateFormalEngineInputV3(input).valid, true);

  const invalidBookTuple = structuredClone(input);
  invalidBookTuple.intents[3].book = "cash_long";
  assert.equal(validateFormalEngineInputV3(invalidBookTuple).valid, false);

  const orderCarriesCancelTarget = structuredClone(input);
  orderCarriesCancelTarget.intents[3].cancelled_intent_id = "long-open";
  assert.equal(validateFormalEngineInputV3(orderCarriesCancelTarget).valid, false);

  const cancelWithoutTarget = structuredClone(input);
  delete cancelWithoutTarget.intents[4].cancelled_intent_id;
  assert.equal(validateFormalEngineInputV3(cancelWithoutTarget).valid, false);

  const marketOrderWithLimit = structuredClone(input);
  marketOrderWithLimit.intents[3].limit_price_atoms = "1000";
  assert.equal(validateFormalEngineInputV3(marketOrderWithLimit).valid, false);
});

test("A-share v3 engine input freezes the reverse-split corporate-action ABI", () => {
  const source = JSON.parse(
    readFileSync(
      join(repoRoot, "fixtures/backtests/a-share-research-v3-long-t1.json"),
      "utf8",
    ),
  ).input;
  const input = {
    ...source,
    corporate_actions: [
      {
        action_id: "cash-dividend-1",
        symbol: "AAA.XSHG",
        effective_at: { session_seq: 2, phase: "open", stable_seq: 1 },
        action_type: "cash_dividend",
        cash_per_share_atoms: "10",
        numerator: null,
        denominator: null,
        settlement_price_atoms: null,
      },
      {
        action_id: "split-1",
        symbol: "AAA.XSHG",
        effective_at: { session_seq: 2, phase: "open", stable_seq: 2 },
        action_type: "split",
        cash_per_share_atoms: null,
        numerator: 2,
        denominator: 1,
        settlement_price_atoms: null,
      },
      {
        action_id: "reverse-split-1",
        symbol: "AAA.XSHG",
        effective_at: { session_seq: 2, phase: "open", stable_seq: 3 },
        action_type: "reverse_split",
        cash_per_share_atoms: null,
        numerator: 1,
        denominator: 2,
        settlement_price_atoms: null,
      },
      {
        action_id: "delist-1",
        symbol: "AAA.XSHG",
        effective_at: { session_seq: 2, phase: "open", stable_seq: 4 },
        action_type: "delist_settlement",
        cash_per_share_atoms: null,
        numerator: null,
        denominator: null,
        settlement_price_atoms: "1000",
      },
    ],
  };

  assert.equal(validateFormalEngineInputV3(input).valid, true);

  const reverseSplitHasSettlementPrice = structuredClone(input);
  reverseSplitHasSettlementPrice.corporate_actions[2].settlement_price_atoms = "1000";
  assert.equal(validateFormalEngineInputV3(reverseSplitHasSettlementPrice).valid, false);

  const dividendHasNoPerShareAmount = structuredClone(input);
  delete dividendHasNoPerShareAmount.corporate_actions[0].cash_per_share_atoms;
  assert.equal(validateFormalEngineInputV3(dividendHasNoPerShareAmount).valid, false);
});
