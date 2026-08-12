export function runReportFixture({
  projectId,
  activityId,
  variantId,
  revisionId,
  snapshotId,
  runId,
}: {
  projectId: string;
  activityId: string;
  variantId: string;
  revisionId: string;
  snapshotId: string;
  runId: string;
}) {
  return {
    report: {
      report_version: "m9-v1",
      run: {
        run_id: runId,
        run_spec_id: "75757575-7575-4575-8575-757575757575",
        project_id: projectId,
        activity_id: activityId,
        variant_id: variantId,
        candidate_revision_id: revisionId,
        status: "succeeded",
        calculation_hash: "a".repeat(64),
        finished_at: "2026-08-12T00:05:00Z",
      },
      identities: {
        engine_result_sha256: "a".repeat(64),
        engine_version: "oqs-quant-engine/0.1.0",
        engine_schema_version: 1,
        account_model: "a_share_cash",
        data_snapshot_id: snapshotId,
        data_snapshot_sha256: "b".repeat(64),
        strategy_tree_oid: "c".repeat(40),
        parameters_sha256: "d".repeat(64),
        cost_model_sha256: "e".repeat(64),
        environment_lock_sha256: "f".repeat(64),
        price_basis: "raw",
        cutoff: "2026-12-31T23:59:59Z",
        timezone: "Asia/Shanghai",
        sample_start: "2026-01-01T00:00:00Z",
        sample_end: "2026-01-31T00:00:00Z",
      },
      period: {
        start_at: "2026-01-01T00:00:00Z",
        end_at: "2026-01-31T00:00:00Z",
        session_count: 8,
      },
      summary: {
        starting_equity_atoms: "10000",
        ending_equity_atoms: "10100",
        net_pnl_atoms: "100",
        total_return_rate_atoms: "10000",
        max_drawdown_atoms: "0",
        max_drawdown_rate_atoms: "0",
        gross_exposure_atoms: "0",
        net_exposure_atoms: "0",
        total_fees_atoms: "6",
        total_stamp_duty_atoms: "0",
        total_funding_atoms: "0",
        total_slippage_atoms: "0",
        order_count: 0,
        fill_count: 0,
        closed_trade_count: 0,
        open_position_count: 0,
      },
      reconciliation: {
        passed: true,
        checks: [{
          field: "metrics.ending_equity_atoms",
          expected: "10100",
          actual: "10100",
          passed: true,
        }],
      },
      definitions: [],
      source: {
        engine_result_artifact_id: "76767676-7676-4676-8676-767676767676",
        manifest_artifact_id: "77777777-7777-4777-8777-777777777777",
      },
    },
    json_artifact: {
      artifact_id: "78787878-7878-4787-8787-787878787878",
      sha256: "1".repeat(64),
      media_type: "application/vnd.open-quant-studio.run-report+json",
      byte_size: 2,
      storage_uri: `cas://sha256/${"1".repeat(64)}`,
    },
    html_artifact: {
      artifact_id: "79797979-7979-4797-8797-797979797979",
      sha256: "2".repeat(64),
      media_type: "application/vnd.open-quant-studio.run-report+html",
      byte_size: 2,
      storage_uri: `cas://sha256/${"2".repeat(64)}`,
    },
  };
}
