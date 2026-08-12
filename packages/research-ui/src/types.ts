export type WorkbenchId =
  | "canvas"
  | "chat"
  | "code"
  | "compare"
  | "backtest"
  | "forward-test"
  | "run-detail"
  | "data"
  | "logs"
  | "settings";

export interface Project {
  project_id: string;
  name?: string;
  created_at: string;
  [key: string]: unknown;
}

export interface Activity {
  activity_id: string;
  project_id: string;
  name?: string;
  created_at: string;
  [key: string]: unknown;
}

export interface Context {
  sessionId?: string;
  projectId?: string;
  activityId?: string;
  activeWorkbenchId?: string;
  isStreaming?: boolean;
  [key: string]: unknown;
}

export interface Variant {
  variant_id: string;
  project_id?: string;
  activity_id?: string;
  base_revision_id?: string;
  head_revision_id: string;
  version?: number;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface RevisionFile {
  path: string;
  body: string;
  sha256?: string;
  git_blob_oid?: string;
  [key: string]: unknown;
}

export interface Revision {
  revision_id: string;
  project_id?: string;
  activity_id?: string;
  variant_id?: string;
  base_revision_id?: string | null;
  parent_revision_id?: string | null;
  git_commit_oid?: string;
  git_tree_oid?: string;
  message?: string;
  files: RevisionFile[];
  created_at?: string;
  [key: string]: unknown;
}

export interface ComparisonChange {
  path: string;
  left_sha256?: string | null;
  right_sha256?: string | null;
  left_body?: string | null;
  right_body?: string | null;
  status?: string;
  [key: string]: unknown;
}

export interface RevisionComparison {
  project_id?: string;
  left_revision_id: string;
  right_revision_id: string;
  changes: ComparisonChange[];
  [key: string]: unknown;
}

export interface RunSummary {
  run_id: string;
  project_id?: string;
  activity_id?: string;
  variant_id?: string;
  candidate_revision_id?: string;
  status?: string;
  created_at?: string;
  finished_at?: string;
  [key: string]: unknown;
}

export interface RunDetail {
  run?: RunSummary;
  run_spec?: Record<string, unknown>;
  validation?: Record<string, unknown>;
  artifacts?: Record<string, unknown>;
  manifest?: Record<string, unknown>;
  engine_result?: Record<string, unknown>;
  intent_tape?: unknown[];
  logs?: LogEntry[];
  [key: string]: unknown;
}

export interface RunReportArtifactPointer {
  artifact_id: string;
  sha256: string;
  media_type: string;
  byte_size: number;
  storage_uri: string;
}

export interface RunReportRunIdentity {
  run_id: string;
  run_spec_id: string;
  project_id: string;
  activity_id: string;
  variant_id: string;
  candidate_revision_id: string;
  status: string;
  calculation_hash: string;
  finished_at: string | null;
}

export interface RunReportIdentities {
  engine_result_sha256: string;
  engine_version: string;
  engine_schema_version: string | number;
  account_model: string;
  data_snapshot_id: string;
  data_snapshot_sha256: string;
  strategy_tree_oid: string;
  parameters_sha256: string;
  cost_model_sha256: string;
  environment_lock_sha256: string;
  price_basis: string;
  cutoff: string;
  timezone: string;
  sample_start: string;
  sample_end: string;
}

export interface RunReportPeriod {
  start_at: string | null;
  end_at: string | null;
  session_count: number;
}

export interface RunReportSummary {
  starting_equity_atoms: string;
  ending_equity_atoms: string;
  net_pnl_atoms: string;
  total_return_rate_atoms: string;
  max_drawdown_atoms: string;
  max_drawdown_rate_atoms: string;
  gross_exposure_atoms: string;
  net_exposure_atoms: string;
  total_fees_atoms: string;
  total_stamp_duty_atoms: string;
  total_funding_atoms: string;
  total_slippage_atoms: string;
  order_count: number;
  fill_count: number;
  closed_trade_count: number;
  open_position_count: number;
}

export interface RunReportReconciliationCheck {
  field: string;
  expected: string | number;
  actual: string | number;
  passed: boolean;
}

export interface RunReportReconciliation {
  passed: boolean;
  checks: RunReportReconciliationCheck[];
}

export interface RunReportDefinition {
  field: string;
  name: string;
  unit: string;
  formula: string;
  inputs: string[];
  empty_behavior: string;
}

export interface RunReport {
  report_version: string;
  run: RunReportRunIdentity;
  identities: RunReportIdentities;
  period: RunReportPeriod;
  summary: RunReportSummary;
  reconciliation: RunReportReconciliation;
  definitions: RunReportDefinition[];
  source: {
    engine_result_artifact_id: string;
    manifest_artifact_id: string;
  };
}

export interface RunReportReadModel {
  report: RunReport;
  json_artifact: RunReportArtifactPointer;
  html_artifact: RunReportArtifactPointer;
}

export type DataSnapshotSourceFormat = "csv" | "parquet";
export type DataSnapshotMarket = "a_share_daily" | "crypto_linear_perp";
export type DataSnapshotPriceBasis = "raw" | "qfq" | "hfq";

export interface DataSnapshotMapping {
  timestamp: string;
  symbol: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

export interface DataSnapshotSourceArtifact {
  artifact_id: string;
  sha256: string;
  media_type: "text/csv" | "application/vnd.apache.parquet";
  byte_size: number;
  storage_uri: string;
  producing_revision_id: null;
  producing_run_id: null;
  provenance: {
    origin_kind: "user_upload";
    source_ref: string;
  };
}

export interface DataImportPreview {
  source: DataSnapshotSourceArtifact;
  source_format: DataSnapshotSourceFormat;
  file_name: string;
  columns: string[];
  suggested_mapping: DataSnapshotMapping;
  preview_rows: Array<Record<string, string>>;
  total_rows: number;
}

export interface DataImportRowError {
  row_number: number;
  field: string;
  message: string;
}

export interface LocalDataImportFile {
  file_name: string;
  source_format: DataSnapshotSourceFormat;
  byte_size: number;
}

export interface DataSnapshot {
  snapshot_id: string;
  source_artifact_id: string;
  normalized_artifact_id: string;
  market_input_artifact_id: string;
  market: DataSnapshotMarket;
  symbol: string | null;
  symbols: string[];
  timezone: string;
  price_basis: DataSnapshotPriceBasis;
  cutoff: string;
  schema_version: 1 | 2;
  sample_start: string;
  sample_end: string;
  row_count: number;
  session_count: number;
  sha256: string;
  created_at: string;
  project_id: string;
  mapping: DataSnapshotMapping;
  source_sha256: string;
  normalized_sha256: string;
  market_input_sha256: string;
}

export interface BuiltInStrategyParameter {
  name: string;
  value: string | number;
  meaning: string;
}

export interface BuiltInStrategy {
  strategy_id: string;
  title: string;
  market: DataSnapshotMarket;
  source: string;
  notebook: string;
  summary: string;
  assumptions: string[];
  parameters: BuiltInStrategyParameter[];
  tags: string[];
  source_body: string;
  source_sha256: string;
}

export interface RenderedStrategyNotebook {
  strategy_id: string;
  file_name: "strategy.ipynb";
  body: string;
  sha256: string;
}

export type ArchiveLogSelection = "full" | "warn_error" | "none";

export interface ForwardTest {
  forward_test_id: string;
  source_run_id: string;
  source_revision_id: string;
  data_snapshot_id: string;
  protocol_version: string;
  released_bar_count: number;
  transcript_artifact_id: string;
  transcript_sha256: string;
  intent_tape_sha256: string;
  status: "passed" | "failed";
  error_code: string | null;
  project_id: string;
  activity_id: string;
  variant_id: string;
  created_at: string;
  [key: string]: unknown;
}

export type LogLevel = "debug" | "info" | "warn" | "error";

export type LogPriority = "p1" | "p2" | "p3" | "p4";

export interface LogListFilters {
  runId?: string;
  activityId?: string;
  sessionId?: string;
  level?: LogLevel;
  priority?: LogPriority;
  query?: string;
  afterLogSeq?: number;
  limit?: number;
}

export interface LogPage {
  logs: LogEntry[];
  next_after_log_seq: number | null;
}

export interface LogEntry {
  log_id: string;
  log_seq?: number;
  run_id?: string;
  activity_id?: string;
  session_id?: string;
  level?: LogLevel;
  priority?: LogPriority;
  event_code?: string;
  message?: string;
  created_at?: string;
  timestamp?: string;
  [key: string]: unknown;
}

export interface ChatEvent {
  type?: string;
  text?: string;
  delta?: string;
  message?: string;
  status?: string;
  [key: string]: unknown;
}
