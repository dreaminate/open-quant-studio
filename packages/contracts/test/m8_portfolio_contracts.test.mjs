import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  validateFormalEngineResultV2,
  validateFormalRunCommand,
  validateFormalRunEvent,
  validateFormalRunManifestV1,
} from "../dist/index.js";

const fixturesDir = join(import.meta.dirname, "../fixtures/v1");
const fixture = (name) =>
  JSON.parse(readFileSync(join(fixturesDir, name), "utf8"));

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
