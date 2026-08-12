import { Ajv2020, type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import artifactVerificationEventSchemaDocument from "../schemas/v1/artifact-verification-event.schema.json" with { type: "json" };
import artifactRefSchemaDocument from "../schemas/v1/artifact-ref.schema.json" with { type: "json" };
import artifactReadModelSchemaDocument from "../schemas/v1/artifact-read-model.schema.json" with { type: "json" };
import commandEnvelopeSchemaDocument from "../schemas/v1/command-envelope.schema.json" with { type: "json" };
import contextCaptureCommandSchemaDocument from "../schemas/v1/context-capture-command.schema.json" with { type: "json" };
import contextCapturedEventSchemaDocument from "../schemas/v1/context-captured-event.schema.json" with { type: "json" };
import diagnosticLogSchemaDocument from "../schemas/v1/diagnostic-log.schema.json" with { type: "json" };
import eventEnvelopeSchemaDocument from "../schemas/v1/event-envelope.schema.json" with { type: "json" };
import formalEngineResultSchemaDocument from "../schemas/v1/formal-engine-result.schema.json" with { type: "json" };
import formalRunCommandSchemaDocument from "../schemas/v1/formal-run-command.schema.json" with { type: "json" };
import formalRunEventSchemaDocument from "../schemas/v1/formal-run-event.schema.json" with { type: "json" };
import formalRunManifestSchemaDocument from "../schemas/v1/formal-run-manifest.schema.json" with { type: "json" };
import formalRunReadModelSchemaDocument from "../schemas/v1/formal-run-read-model.schema.json" with { type: "json" };
import projectReadModelSchemaDocument from "../schemas/v1/project-read-model.schema.json" with { type: "json" };
import revisionCommandSchemaDocument from "../schemas/v1/revision-command.schema.json" with { type: "json" };
import revisionEventSchemaDocument from "../schemas/v1/revision-event.schema.json" with { type: "json" };
import sessionCommandSchemaDocument from "../schemas/v1/session-command.schema.json" with { type: "json" };
import sessionEventSchemaDocument from "../schemas/v1/session-event.schema.json" with { type: "json" };

export const artifactRefSchema: Record<string, unknown> = artifactRefSchemaDocument;
export const artifactReadModelSchema: Record<string, unknown> = artifactReadModelSchemaDocument;
export const artifactVerificationEventSchema: Record<string, unknown> =
  artifactVerificationEventSchemaDocument;
export const commandEnvelopeSchema: Record<string, unknown> =
  commandEnvelopeSchemaDocument;
export const contextCaptureCommandSchema: Record<string, unknown> =
  contextCaptureCommandSchemaDocument;
export const contextCapturedEventSchema: Record<string, unknown> =
  contextCapturedEventSchemaDocument;
export const diagnosticLogSchema: Record<string, unknown> =
  diagnosticLogSchemaDocument;
export const eventEnvelopeSchema: Record<string, unknown> =
  eventEnvelopeSchemaDocument;
export const formalEngineResultSchema: Record<string, unknown> =
  formalEngineResultSchemaDocument;
export const formalRunCommandSchema: Record<string, unknown> =
  formalRunCommandSchemaDocument;
export const formalRunEventSchema: Record<string, unknown> =
  formalRunEventSchemaDocument;
export const formalRunManifestSchema: Record<string, unknown> =
  formalRunManifestSchemaDocument;
export const formalRunReadModelSchema: Record<string, unknown> =
  formalRunReadModelSchemaDocument;
export const projectReadModelSchema: Record<string, unknown> =
  projectReadModelSchemaDocument;
export const revisionCommandSchema: Record<string, unknown> =
  revisionCommandSchemaDocument;
export const revisionEventSchema: Record<string, unknown> = revisionEventSchemaDocument;
export const sessionCommandSchema: Record<string, unknown> =
  sessionCommandSchemaDocument;
export const sessionEventSchema: Record<string, unknown> = sessionEventSchemaDocument;

export interface ArtifactRef {
  artifact_id: string;
  sha256: string;
  media_type: string;
  byte_size: number;
  storage_uri: string;
  producing_revision_id: string | null;
  producing_run_id: string | null;
  provenance: {
    origin_kind: "fixture" | "user_upload" | "service_generated";
    source_ref: string;
  };
}

export interface M1ArtifactRef extends ArtifactRef {
  producing_revision_id: null;
  producing_run_id: null;
}

export interface CommandEnvelope<
  TPayload extends Record<string, unknown> = Record<string, unknown>,
> {
  command_id: string;
  schema_version: 1;
  command_type: string;
  project_id: string;
  activity_id: string;
  session_id: string;
  workbench_id: string;
  correlation_id: string;
  expected_revision_id: string | null;
  variant_id: string | null;
  base_revision_id: string | null;
  payload: TPayload;
}

export interface EventEnvelope<
  TPayload extends Record<string, unknown> = Record<string, unknown>,
> {
  event_id: string;
  stream_seq: number;
  schema_version: 1;
  event_type: string;
  project_id: string;
  activity_id: string;
  session_id: string | null;
  workbench_id: string | null;
  correlation_id: string;
  causation_id: string;
  recorded_at: string;
  variant_id: string | null;
  base_revision_id: string | null;
  payload: TPayload;
}

export interface ContextCapturePayload extends Record<string, unknown> {
  context_item_id: string;
  title: string;
  trust_state: "raw_evidence";
  artifact: M1ArtifactRef;
}

export interface ContextCaptureCommand
  extends CommandEnvelope<ContextCapturePayload> {
  command_type: "context.capture";
  expected_revision_id: null;
  variant_id: null;
  base_revision_id: null;
}

export interface ContextCapturedEvent
  extends EventEnvelope<ContextCapturePayload> {
  event_type: "context.captured";
  variant_id: null;
  base_revision_id: null;
}

export interface SessionSourceRef {
  session_id: string;
  entry_id: string;
  leaf_id: string;
  sha256: string;
  source_uri: string;
}

export interface M2ArtifactRef extends ArtifactRef {
  producing_revision_id: null;
  producing_run_id: null;
}

export interface SessionRegisterPayload extends Record<string, unknown> {
  pi_session_id: string;
  session_uri: string;
}

export interface SessionWorkbenchBindPayload extends Record<string, unknown> {
  workbench_id: string;
}

export interface SessionMessagePayload extends Record<string, unknown> {
  message_id: string;
  recipient_session_id: string;
  message_kind: "send" | "ask" | "reply";
  reply_to: string | null;
  source_refs: SessionSourceRef[];
  artifact: M2ArtifactRef;
}

export interface SessionReceiptPayload<
  TState extends "queued" | "receiver_received" | "injected" =
    | "queued"
    | "receiver_received"
    | "injected",
  TVersion extends 0 | 1 | 2 = 0 | 1 | 2,
> extends Record<string, unknown> {
  message_id: string;
  expected_state: TState;
  expected_version: TVersion;
}

export type SessionRegisterCommand = CommandEnvelope<SessionRegisterPayload> & {
  command_type: "session.register";
  expected_revision_id: null;
  variant_id: null;
  base_revision_id: null;
};

export type SessionWorkbenchBindCommand = CommandEnvelope<SessionWorkbenchBindPayload> & {
  command_type: "session.workbench_bind";
  expected_revision_id: null;
  variant_id: null;
  base_revision_id: null;
};

export type SessionMessageSendCommand = CommandEnvelope<SessionMessagePayload> & {
  command_type: "session.message_send";
  expected_revision_id: null;
  variant_id: null;
  base_revision_id: null;
};

export type SessionMessageReplyCommand = CommandEnvelope<
  SessionMessagePayload & { reply_to: string }
> & {
  command_type: "session.message_reply";
  expected_revision_id: null;
  variant_id: null;
  base_revision_id: null;
};

export type SessionMessageReceiveCommand = CommandEnvelope<
  SessionReceiptPayload<"queued", 0>
> & {
  command_type: "session.message_receive";
  expected_revision_id: null;
  variant_id: null;
  base_revision_id: null;
};

export type SessionMessageMarkInjectedCommand = CommandEnvelope<
  SessionReceiptPayload<"receiver_received", 1>
> & {
  command_type: "session.message_mark_injected";
  expected_revision_id: null;
  variant_id: null;
  base_revision_id: null;
};

export type SessionMessageAcknowledgeCommand = CommandEnvelope<
  SessionReceiptPayload<"injected", 2>
> & {
  command_type: "session.message_acknowledge";
  expected_revision_id: null;
  variant_id: null;
  base_revision_id: null;
};

export type SessionCommand =
  | SessionRegisterCommand
  | SessionWorkbenchBindCommand
  | SessionMessageSendCommand
  | SessionMessageReplyCommand
  | SessionMessageReceiveCommand
  | SessionMessageMarkInjectedCommand
  | SessionMessageAcknowledgeCommand;

export interface SessionRegisteredEvent extends EventEnvelope<{
  session_id: string;
  pi_session_id: string;
  session_uri: string;
  workbench_id: string;
}> {
  event_type: "session.registered";
  variant_id: null;
  base_revision_id: null;
}

export interface SessionWorkbenchBoundEvent extends EventEnvelope<{
  session_id: string;
  workbench_id: string;
}> {
  event_type: "session.workbench_bound";
  variant_id: null;
  base_revision_id: null;
}

export interface SessionMessageEventPayload extends Record<string, unknown> {
  message_id: string;
  recipient_session_id: string;
  message_kind: "send" | "ask" | "reply";
  artifact_id: string;
  artifact_sha256: string;
  state: "queued" | "receiver_received" | "injected" | "acknowledged";
  receipt_version: number;
  reply_to: string | null;
  source_refs: SessionSourceRef[];
}

export type SessionMessageQueuedEvent = EventEnvelope<
  SessionMessageEventPayload & { state: "queued"; receipt_version: 0 }
> & {
  event_type: "session.message_queued";
  variant_id: null;
  base_revision_id: null;
};

export type SessionMessageReceivedEvent = EventEnvelope<
  SessionMessageEventPayload & {
    state: "receiver_received";
    receipt_version: 1;
  }
> & {
  event_type: "session.message_receiver_received";
  variant_id: null;
  base_revision_id: null;
};

export type SessionMessageInjectedEvent = EventEnvelope<
  SessionMessageEventPayload & { state: "injected"; receipt_version: 2 }
> & {
  event_type: "session.message_injected";
  variant_id: null;
  base_revision_id: null;
};

export type SessionMessageAcknowledgedEvent = EventEnvelope<
  SessionMessageEventPayload & { state: "acknowledged"; receipt_version: 3 }
> & {
  event_type: "session.message_acknowledged";
  variant_id: null;
  base_revision_id: null;
};

export type SessionMessageEvent =
  | SessionMessageQueuedEvent
  | SessionMessageReceivedEvent
  | SessionMessageInjectedEvent
  | SessionMessageAcknowledgedEvent;

export type SessionEvent =
  | SessionRegisteredEvent
  | SessionWorkbenchBoundEvent
  | SessionMessageEvent;

export const SESSION_COMMAND_TYPES = new Set([
  "session.register",
  "session.workbench_bind",
  "session.message_send",
  "session.message_reply",
  "session.message_receive",
  "session.message_mark_injected",
  "session.message_acknowledge",
]);

export const SESSION_EVENT_TYPES = new Set([
  "session.registered",
  "session.workbench_bound",
  "session.message_queued",
  "session.message_receiver_received",
  "session.message_injected",
  "session.message_acknowledged",
]);

export interface M3ArtifactRef extends M1ArtifactRef {
  media_type: "text/plain";
}

export interface RevisionFile extends Record<string, unknown> {
  path: string;
  artifact: M3ArtifactRef;
}

export interface RevisionCreatePayload extends Record<string, unknown> {
  revision_id: string;
  message: string;
  files: RevisionFile[];
}

export type WorkspaceRevisionCreateRootCommand =
  CommandEnvelope<RevisionCreatePayload> & {
    command_type: "workspace.revision_create";
    expected_revision_id: null;
    variant_id: null;
    base_revision_id: null;
  };

export type WorkspaceRevisionCreateChildCommand =
  CommandEnvelope<RevisionCreatePayload> & {
    command_type: "workspace.revision_create";
    expected_revision_id: string;
    variant_id: string;
    base_revision_id: string;
  };

export type WorkspaceRevisionCreateCommand =
  | WorkspaceRevisionCreateRootCommand
  | WorkspaceRevisionCreateChildCommand;

export interface VariantCreatePayload extends Record<string, unknown> {
  variant_id: string;
  base_revision_id: string;
}

export type StrategyVariantCreateCommand =
  CommandEnvelope<VariantCreatePayload> & {
    command_type: "strategy.variant_create";
    expected_revision_id: null;
    variant_id: string;
    base_revision_id: string;
  };

export interface RevisionPromotePayload extends Record<string, unknown> {
  variant_id: string;
  candidate_revision_id: string;
  validation_id: string;
}

export type WorkspaceRevisionPromoteCommand =
  CommandEnvelope<RevisionPromotePayload> & {
    command_type: "workspace.revision_promote";
    expected_revision_id: string;
    variant_id: string;
    base_revision_id: string;
  };

export type RevisionCommand =
  | WorkspaceRevisionCreateCommand
  | StrategyVariantCreateCommand
  | WorkspaceMergeCreateCommand
  | WorkspaceRevisionPromoteCommand;

export interface MergeCreatePayload extends Record<string, unknown> {
  candidate_revision_id: string;
  message: string;
  files: RevisionFile[];
}

export type WorkspaceMergeCreateCommand = CommandEnvelope<MergeCreatePayload> & {
  command_type: "workspace.merge_create";
  expected_revision_id: string;
  variant_id: string;
  base_revision_id: string;
};

export interface RevisionCreatedPayload extends Record<string, unknown> {
  revision_id: string;
  parent_revision_id: string | null;
  git_commit_oid: string;
  git_tree_oid: string;
  file_count: number;
}

export type WorkspaceRevisionCreatedRootEvent =
  EventEnvelope<RevisionCreatedPayload> & {
    event_type: "workspace.revision_created";
    variant_id: null;
    base_revision_id: null;
  };

export type WorkspaceRevisionCreatedChildEvent =
  EventEnvelope<RevisionCreatedPayload> & {
    event_type: "workspace.revision_created";
    variant_id: string;
    base_revision_id: string;
  };

export type WorkspaceRevisionCreatedEvent =
  | WorkspaceRevisionCreatedRootEvent
  | WorkspaceRevisionCreatedChildEvent;

export interface VariantCreatedPayload extends Record<string, unknown> {
  variant_id: string;
  revision_id: string;
}

export type StrategyVariantCreatedEvent =
  EventEnvelope<VariantCreatedPayload> & {
    event_type: "strategy.variant_created";
    variant_id: string;
    base_revision_id: string;
  };

export interface RevisionPromotedPayload extends Record<string, unknown> {
  variant_id: string;
  previous_revision_id: string;
  promoted_revision_id: string;
  validation_id: string;
  git_commit_oid: string;
  git_tree_oid: string;
}

export type WorkspaceRevisionPromotedEvent =
  EventEnvelope<RevisionPromotedPayload> & {
    event_type: "workspace.revision_promoted";
    variant_id: string;
    base_revision_id: string;
  };

export type RevisionEvent =
  | WorkspaceRevisionCreatedEvent
  | StrategyVariantCreatedEvent
  | WorkspaceMergeCandidateCreatedEvent
  | WorkspaceRevisionPromotedEvent;

export interface MergeCandidateCreatedPayload extends Record<string, unknown> {
  candidate_revision_id: string;
  project_parent_revision_id: string;
  variant_parent_revision_id: string;
  git_commit_oid: string;
  git_tree_oid: string;
  file_count: number;
}

export type WorkspaceMergeCandidateCreatedEvent =
  EventEnvelope<MergeCandidateCreatedPayload> & {
    event_type: "workspace.merge_candidate_created";
    variant_id: string;
    base_revision_id: string;
  };

export interface FormalRunRequestPayload extends Record<string, unknown> {
  run_spec_id: string;
  run_id: string;
  validation_id: string;
  candidate_revision_id: string;
  engine_input: ArtifactRef;
  data_snapshot_id: string;
  data_snapshot_sha256: string;
  strategy_tree_oid: string;
  parameters_sha256: string;
  cost_model_sha256: string;
  environment_lock_sha256: string;
  engine_version: "oqs-quant-engine/0.1.0";
  price_basis: "raw" | "qfq" | "hfq";
  cutoff: string;
  timezone: string;
  sample_start: string;
  sample_end: string;
  random_seed: number;
  output_schema_version: 1;
  gate_policy_version: "m3-v1";
}

export type FormalRunCommand = CommandEnvelope<FormalRunRequestPayload> & {
  command_type: "formal.run_request";
  expected_revision_id: string;
  variant_id: string;
  base_revision_id: string;
};

export interface FormalRunActivePayload extends Record<string, unknown> {
  job_id: string;
  run_spec_id: string;
  run_id: string;
  validation_id: string;
  candidate_revision_id: string;
  run_spec_hash: string;
}

export interface FormalRunCompletedPayload extends FormalRunActivePayload {
  status: "succeeded" | "failed";
  gates: {
    contract: "passed" | "failed";
    strategy_import: "passed" | "failed";
    smoke_run: "passed" | "failed";
  };
  engine_result_artifact_id: string | null;
  engine_result_sha256: string | null;
  manifest_artifact_id: string | null;
  manifest_sha256: string | null;
  calculation_hash: string | null;
  error_code: string | null;
}

export type FormalRunEvent =
  | (EventEnvelope<FormalRunActivePayload> & {
      event_type: "formal.run_queued" | "formal.run_started";
      variant_id: string;
      base_revision_id: string;
    })
  | (EventEnvelope<FormalRunCompletedPayload> & {
      event_type: "formal.run_completed";
      variant_id: string;
      base_revision_id: string;
    });

export const REVISION_COMMAND_TYPES = new Set([
  "workspace.revision_create",
  "strategy.variant_create",
  "workspace.merge_create",
  "workspace.revision_promote",
]);

export const REVISION_EVENT_TYPES = new Set([
  "workspace.revision_created",
  "strategy.variant_created",
  "workspace.merge_candidate_created",
  "workspace.revision_promoted",
]);

export const FORMAL_RUN_COMMAND_TYPES = new Set(["formal.run_request"]);
export const FORMAL_RUN_EVENT_TYPES = new Set([
  "formal.run_queued",
  "formal.run_started",
  "formal.run_completed",
]);

export const M3_COMMAND_TYPES = new Set([
  ...REVISION_COMMAND_TYPES,
  ...FORMAL_RUN_COMMAND_TYPES,
]);
export const M3_EVENT_TYPES = new Set([
  ...REVISION_EVENT_TYPES,
  ...FORMAL_RUN_EVENT_TYPES,
]);


export type ArtifactVerificationEvent =
  | (EventEnvelope<{
      artifact_id: string;
      job_id: string;
      result: null;
      error_code: null;
    }> & { event_type: "artifact.verification_started" })
  | (EventEnvelope<{
      artifact_id: string;
      job_id: string;
      result: { sha256: string; byte_size: number };
      error_code: null;
    }> & { event_type: "artifact.verification_succeeded" })
  | (EventEnvelope<{
      artifact_id: string;
      job_id: string;
      result: null;
      error_code: "artifact_blob_missing" | "artifact_integrity_mismatch";
    }> & { event_type: "artifact.verification_failed" });

export type DomainEvent =
  | ContextCapturedEvent
  | ArtifactVerificationEvent
  | SessionEvent
  | RevisionEvent
  | FormalRunEvent;

export interface DiagnosticLog {
  timestamp: string;
  level: "debug" | "info" | "warn" | "error";
  priority: "p1" | "p2" | "p3" | "p4";
  component: string;
  event_code: string;
  project_id: string | null;
  activity_id: string | null;
  session_id: string | null;
  task_id: string | null;
  job_id: string | null;
  run_id: string | null;
  correlation_id: string | null;
  message: string;
}

export interface ProjectReadModel {
  project_id: string;
  created_at: string;
}

export interface ProjectListReadModel {
  projects: ProjectReadModel[];
}

export interface ActivityReadModel {
  activity_id: string;
  project_id: string;
  created_at: string;
}

export interface ActivityListReadModel {
  activities: ActivityReadModel[];
}

export interface ArtifactMetadataReadModel {
  artifact_id: string;
  project_id: string;
  sha256: string;
  media_type: string;
  byte_size: number;
  storage_uri: string;
  producing_revision_id: string | null;
  producing_run_id: string | null;
  origin_kind: "fixture" | "user_upload" | "service_generated";
  source_ref: string;
  created_at: string;
  revision_paths: Array<{ revision_id: string; path: string }>;
  run_kinds: Array<{
    run_id: string;
    kind: "intent_tape" | "engine_result" | "manifest";
  }>;
}

export type FormalAtom = string;

export interface FormalEngineOrderV1 {
  intent_id: string;
  intent_seq: number;
  status: "filled" | "expired" | "cancelled";
  side: "buy" | "sell";
  position_effect: "open" | "close";
  order_type: "market" | "limit" | "stop";
  quantity: FormalAtom;
  filled_session_seq: number | null;
  filled_phase: "open" | "intrabar" | null;
}

export interface FormalEngineTradeV1 {
  trade_id: string;
  intent_id: string;
  session_seq: number;
  side: "buy" | "sell";
  position_effect: "open" | "close";
  quantity: FormalAtom;
  fill_price_atoms: FormalAtom;
  notional_atoms: FormalAtom;
  fee_atoms: FormalAtom;
  stamp_duty_atoms: FormalAtom;
  slippage_atoms: FormalAtom;
  liquidity: "maker" | "taker";
}

export interface FormalEnginePositionV1 {
  intent_id: string;
  session_seq: number;
  signed_quantity: FormalAtom;
  eligible_quantity: FormalAtom;
}

export interface FormalEngineCashLedgerV1 {
  intent_id: string;
  session_seq: number;
  notional_delta_atoms: FormalAtom;
  fee_delta_atoms: FormalAtom;
  stamp_duty_delta_atoms: FormalAtom;
  realized_pnl_delta_atoms: FormalAtom;
  funding_delta_atoms: FormalAtom;
  resulting_cash_atoms: FormalAtom;
}

export interface FormalEngineFundingLedgerV1 {
  event_id: string;
  session_seq: number;
  signed_quantity: FormalAtom;
  rate_atoms: FormalAtom;
  mark_price_atoms: FormalAtom;
  wallet_delta_atoms: FormalAtom;
  resulting_wallet_atoms: FormalAtom;
}

export interface FormalEngineEquityPointV1 {
  session_seq: number;
  timestamp: string;
  mark_price_atoms: FormalAtom;
  cash_atoms: FormalAtom;
  signed_quantity: FormalAtom;
  equity_atoms: FormalAtom;
}

export interface FormalEngineDrawdownPointV1 {
  session_seq: number;
  equity_atoms: FormalAtom;
  peak_equity_atoms: FormalAtom;
  drawdown_atoms: FormalAtom;
  drawdown_rate_atoms: FormalAtom;
}

export interface FormalEngineMetricsV1 {
  starting_equity_atoms: FormalAtom;
  ending_equity_atoms: FormalAtom;
  net_pnl_atoms: FormalAtom;
  total_return_rate_atoms: FormalAtom;
  max_drawdown_atoms: FormalAtom;
  max_drawdown_rate_atoms: FormalAtom;
  total_fees_atoms: FormalAtom;
  total_stamp_duty_atoms: FormalAtom;
  total_funding_atoms: FormalAtom;
  total_slippage_atoms: FormalAtom;
  fill_count: number;
  closed_trade_count: number;
  open_position_count: number;
}

export interface FormalEngineCostsV1 {
  commission_atoms: FormalAtom;
  stamp_duty_atoms: FormalAtom;
  funding_atoms: FormalAtom;
  slippage_atoms: FormalAtom;
}

export interface FormalEngineAssumptionsV1 {
  fill_model: "ohlc_full_fill_v1";
  partial_fills: boolean;
  liquidate_on_end: boolean;
  research_short: boolean;
  research_short_notice: string | null;
  one_x_notional: boolean;
}

export interface FormalEngineResultV1 {
  schema_version: 1;
  engine_version: "oqs-quant-engine/0.1.0";
  account_model: "a_share_cash" | "crypto_linear_perp";
  orders: FormalEngineOrderV1[];
  trades: FormalEngineTradeV1[];
  positions: FormalEnginePositionV1[];
  cash_ledger: FormalEngineCashLedgerV1[];
  funding_ledger: FormalEngineFundingLedgerV1[];
  equity_curve: FormalEngineEquityPointV1[];
  drawdown_curve: FormalEngineDrawdownPointV1[];
  metrics: FormalEngineMetricsV1;
  costs: FormalEngineCostsV1;
  assumptions: FormalEngineAssumptionsV1;
}

export interface FormalRunManifestRunSpecV1 {
  run_spec_id: string;
  spec_hash: string;
  project_id: string;
  activity_id: string;
  variant_id: string;
  candidate_revision_id: string;
  data_snapshot_id: string;
  data_snapshot_sha256: string;
  strategy_tree_oid: string;
  parameters_sha256: string;
  cost_model_sha256: string;
  environment_lock_sha256: string;
  engine_version: "oqs-quant-engine/0.1.0";
  price_basis: "raw" | "qfq" | "hfq";
  cutoff: string;
  timezone: string;
  sample_start: string;
  sample_end: string;
  random_seed: number;
  output_schema_version: 1;
  gate_policy_version: "m3-v1";
}

export interface FormalRunManifestRevisionV1 {
  candidate_revision_id: string;
  git_commit_oid: string;
  git_tree_oid: string;
  strategy_path: "strategy.py";
  strategy_artifact_id: string;
  strategy_sha256: string;
  strategy_git_blob_oid: string;
  project_parent_revision_id: string;
  variant_parent_revision_id: string;
  expected_project_head_version: number;
  expected_variant_head_version: number;
}

export interface FormalRunManifestEngineInputV1 {
  artifact_id: string;
  sha256: string;
  media_type: "application/json";
  byte_size: number;
  storage_uri: string;
}

export interface FormalRunManifestStrategyExecutionV1 {
  intent_tape_artifact_id: string;
  intent_tape_sha256: string;
  intent_tape_byte_size: number;
  intent_tape_storage_uri: string;
  timing_authority: "oqs-strategy-host/m3-v1";
}

export interface FormalRunManifestEngineResultV1 {
  artifact_id: string;
  sha256: string;
  media_type: "application/json";
  byte_size: number;
  storage_uri: string;
  schema_version: 1;
  engine_version: "oqs-quant-engine/0.1.0";
}

export interface FormalRunManifestV1 {
  schema_version: 1;
  manifest_version: "m3-v1";
  run_id: string;
  validation_id: string;
  run_spec: FormalRunManifestRunSpecV1;
  revision: FormalRunManifestRevisionV1;
  engine_input: FormalRunManifestEngineInputV1;
  strategy_execution: FormalRunManifestStrategyExecutionV1;
  engine_result: FormalRunManifestEngineResultV1;
  gates: {
    contract: "passed";
    strategy_import: "passed";
    smoke_run: "passed";
  };
  logs: {
    run_id: string;
    deletable: true;
    included_in_calculation_hash: false;
  };
}

export interface FormalRunSpecReadModel {
  run_spec_id: string;
  project_id: string;
  activity_id: string;
  variant_id: string;
  candidate_revision_id: string;
  engine_input_artifact_id: string;
  data_snapshot_id: string;
  data_snapshot_sha256: string;
  strategy_tree_oid: string;
  parameters_sha256: string;
  cost_model_sha256: string;
  environment_lock_sha256: string;
  engine_version: "oqs-quant-engine/0.1.0";
  price_basis: "raw" | "qfq" | "hfq";
  cutoff: string;
  timezone: string;
  sample_start: string;
  sample_end: string;
  random_seed: number;
  output_schema_version: 1;
  gate_policy_version: "m3-v1";
  spec_hash: string;
  created_at: string;
}

export type FormalRunErrorCode =
  | "contract_gate_failed"
  | "strategy_import_failed"
  | "engine_input_missing"
  | "engine_input_integrity_mismatch"
  | "smoke_run_failed"
  | "engine_result_contract_failed";

export interface FormalRunGates {
  contract: "passed" | "failed";
  strategy_import: "passed" | "failed";
  smoke_run: "passed" | "failed";
}

export interface FormalRunValidationReadModel {
  validation_id: string;
  gate_policy_version: "m3-v1";
  engine_version: "oqs-quant-engine/0.1.0";
  gates: FormalRunGates;
  outcome: "passed" | "failed";
  manifest_artifact_id: string | null;
  created_at: string;
}

export interface FormalRunSucceededListEntry {
  run_id: string;
  run_spec_id: string;
  project_id: string;
  activity_id: string;
  variant_id: string;
  candidate_revision_id: string;
  status: "succeeded";
  engine_result_artifact_id: string;
  manifest_artifact_id: string;
  calculation_hash: string;
  error_code: null;
  finished_at: string;
  validation_id: string;
  validation_outcome: "passed";
  gates: {
    contract: "passed";
    strategy_import: "passed";
    smoke_run: "passed";
  };
}

export interface FormalRunFailedListEntry {
  run_id: string;
  run_spec_id: string;
  project_id: string;
  activity_id: string;
  variant_id: string;
  candidate_revision_id: string;
  status: "failed";
  engine_result_artifact_id: null;
  manifest_artifact_id: null;
  calculation_hash: null;
  error_code: FormalRunErrorCode;
  finished_at: string;
  validation_id: string;
  validation_outcome: "failed";
  gates: FormalRunGates;
}

export type FormalRunListEntry =
  | FormalRunSucceededListEntry
  | FormalRunFailedListEntry;

export interface FormalRunListReadModel {
  runs: FormalRunListEntry[];
}

export interface FormalRunSucceededRecord
  extends Omit<
    FormalRunSucceededListEntry,
    "validation_id" | "validation_outcome" | "gates"
  > {
  job_id: string;
  queued_at: string;
  started_at: string;
  job_finished_at: string;
}

export interface FormalRunFailedRecord
  extends Omit<
    FormalRunFailedListEntry,
    "validation_id" | "validation_outcome" | "gates"
  > {
  job_id: string;
  queued_at: string;
  started_at: string;
  job_finished_at: string;
}

export interface FormalRunIntentV1 {
  intent_id: string;
  intent_seq: number;
  symbol: string;
  side: "buy" | "sell";
  position_effect: "open" | "close";
  quantity: FormalAtom;
  order_type: "market" | "limit" | "stop";
  known_at: { session_seq: number; phase: "open" | "intrabar" | "close"; stable_seq: number };
  effective_at: { session_seq: number; phase: "open" | "intrabar" | "close"; stable_seq: number };
  limit_price_atoms: FormalAtom | null;
  stop_price_atoms: FormalAtom | null;
  time_in_force: "day" | "gtc";
  oco_group: string | null;
}

export interface FormalRunSucceededDetailReadModel {
  run: FormalRunSucceededRecord;
  run_spec: FormalRunSpecReadModel;
  validation: FormalRunValidationReadModel;
  artifacts: {
    intent_tape: ArtifactMetadataReadModel;
    engine_result: ArtifactMetadataReadModel;
    manifest: ArtifactMetadataReadModel;
  };
  manifest: FormalRunManifestV1;
  engine_result: FormalEngineResultV1;
  intent_tape: FormalRunIntentV1[];
  logs: DiagnosticLog[];
}

export interface FormalRunFailedDetailReadModel {
  run: FormalRunFailedRecord;
  run_spec: FormalRunSpecReadModel;
  validation: FormalRunValidationReadModel;
  artifacts: Record<string, never>;
  manifest: null;
  engine_result: null;
  intent_tape: null;
  logs: DiagnosticLog[];
}

export type FormalRunDetailReadModel =
  | FormalRunSucceededDetailReadModel
  | FormalRunFailedDetailReadModel;

export type ContractValidation<T> =
  | { valid: true; value: T }
  | { valid: false; errors: string[] };

const validator = new Ajv2020({ allErrors: true, strict: true });
addFormats.default(validator, ["date-time"]);
const validateCommand = validator.compile<CommandEnvelope>(commandEnvelopeSchema);
const validateEvent = validator.compile<EventEnvelope>(eventEnvelopeSchema);
const validateArtifact = validator.compile<ArtifactRef>(artifactRefSchema);
const validateArtifactVerification = validator.compile<ArtifactVerificationEvent>(
  artifactVerificationEventSchema,
);
const validateContextCommand = validator.compile<ContextCaptureCommand>(
  contextCaptureCommandSchema,
);
const validateContextEvent = validator.compile<ContextCapturedEvent>(
  contextCapturedEventSchema,
);
const validateSessionCommandSchema = validator.compile<SessionCommand>(
  sessionCommandSchemaDocument,
);
const validateSessionEventSchema = validator.compile<SessionEvent>(
  sessionEventSchemaDocument,
);
const validateRevisionCommandSchema = validator.compile<RevisionCommand>(
  revisionCommandSchemaDocument,
);
const validateRevisionEventSchema = validator.compile<RevisionEvent>(
  revisionEventSchemaDocument,
);
const validateFormalRunCommandSchema = validator.compile<FormalRunCommand>(
  formalRunCommandSchemaDocument,
);
const validateFormalRunEventSchema = validator.compile<FormalRunEvent>(
  formalRunEventSchemaDocument,
);
const validateLog = validator.compile<DiagnosticLog>(diagnosticLogSchema);
const validateProjectReadModelSchema = validator.compile<
  ProjectListReadModel | ActivityListReadModel
>(projectReadModelSchemaDocument);
const validateArtifactMetadataSchema = validator.compile<ArtifactMetadataReadModel>(
  artifactReadModelSchemaDocument,
);
const validateFormalEngineResultSchema = validator.compile<FormalEngineResultV1>(
  formalEngineResultSchemaDocument,
);
const validateFormalRunManifestSchema = validator.compile<FormalRunManifestV1>(
  formalRunManifestSchemaDocument,
);
const validateFormalRunReadModelSchema = validator.compile<
  FormalRunListReadModel | FormalRunDetailReadModel
>(formalRunReadModelSchemaDocument);

function validationErrors(errors: ErrorObject[] | null | undefined): string[] {
  return (errors ?? []).map(
    ({ instancePath, message }) => `${instancePath || "/"} ${message}`,
  );
}

function artifactIdentityErrors(artifact: {
  sha256: string;
  storage_uri: string;
}): string[] {
  const expectedStorageUri = `cas://sha256/${artifact.sha256}`;
  return artifact.storage_uri === expectedStorageUri
    ? []
    : ["/storage_uri must match /sha256"];
}

export function validateCommandEnvelope(
  value: unknown,
): ContractValidation<CommandEnvelope> {
  if (!validateCommand(value)) {
    return { valid: false, errors: validationErrors(validateCommand.errors) };
  }

  const commandType = value.command_type;
  if (commandType === "context.capture") {
    return validateContextCaptureCommand(value);
  }
  if (SESSION_COMMAND_TYPES.has(commandType)) {
    return validateSessionCommand(value) as unknown as ContractValidation<CommandEnvelope>;
  }
  if (REVISION_COMMAND_TYPES.has(commandType)) {
    return validateRevisionCommand(value) as unknown as ContractValidation<CommandEnvelope>;
  }
  if (FORMAL_RUN_COMMAND_TYPES.has(commandType)) {
    return validateFormalRunCommand(value) as unknown as ContractValidation<CommandEnvelope>;
  }
  return { valid: true, value };
}

export function validateEventEnvelope(
  value: unknown,
): ContractValidation<EventEnvelope> {
  if (!validateEvent(value)) {
    return { valid: false, errors: validationErrors(validateEvent.errors) };
  }

  const eventType = value.event_type;
  if (eventType === "context.captured") {
    return validateContextCapturedEvent(value);
  }
  if (SESSION_EVENT_TYPES.has(eventType)) {
    return validateSessionEvent(value) as unknown as ContractValidation<EventEnvelope>;
  }
  if (REVISION_EVENT_TYPES.has(eventType)) {
    return validateRevisionEvent(value) as unknown as ContractValidation<EventEnvelope>;
  }
  if (FORMAL_RUN_EVENT_TYPES.has(eventType)) {
    return validateFormalRunEvent(value) as unknown as ContractValidation<EventEnvelope>;
  }
  return { valid: true, value };
}

export function validateTypedCommandEnvelope(
  value: unknown,
): ContractValidation<CommandEnvelope> {
  if (!validateCommand(value)) {
    return { valid: false, errors: validationErrors(validateCommand.errors) };
  }
  const commandType = value.command_type;
  if (commandType === "context.capture") {
    return validateContextCaptureCommand(value);
  }
  if (SESSION_COMMAND_TYPES.has(commandType)) {
    return validateSessionCommand(value) as unknown as ContractValidation<CommandEnvelope>;
  }
  if (REVISION_COMMAND_TYPES.has(commandType)) {
    return validateRevisionCommand(value) as unknown as ContractValidation<CommandEnvelope>;
  }
  if (FORMAL_RUN_COMMAND_TYPES.has(commandType)) {
    return validateFormalRunCommand(value) as unknown as ContractValidation<CommandEnvelope>;
  }
  return { valid: false, errors: [`unsupported command type ${commandType}`] };
}

export function validateTypedEventEnvelope(
  value: unknown,
): ContractValidation<EventEnvelope> {
  if (!validateEvent(value)) {
    return { valid: false, errors: validationErrors(validateEvent.errors) };
  }
  const eventType = value.event_type;
  if (eventType === "context.captured") {
    return validateContextCapturedEvent(value);
  }
  if (SESSION_EVENT_TYPES.has(eventType)) {
    return validateSessionEvent(value) as unknown as ContractValidation<EventEnvelope>;
  }
  if (REVISION_EVENT_TYPES.has(eventType)) {
    return validateRevisionEvent(value) as unknown as ContractValidation<EventEnvelope>;
  }
  if (FORMAL_RUN_EVENT_TYPES.has(eventType)) {
    return validateFormalRunEvent(value) as unknown as ContractValidation<EventEnvelope>;
  }
  return { valid: false, errors: [`unsupported event type ${eventType}`] };
}

export function validateArtifactRef(
  value: unknown,
): ContractValidation<ArtifactRef> {
  if (validateArtifact(value)) {
    const errors = artifactIdentityErrors(value);
    if (errors.length > 0) {
      return { valid: false, errors };
    }
    return { valid: true, value };
  }

  return { valid: false, errors: validationErrors(validateArtifact.errors) };
}

export function validateArtifactVerificationEvent(
  value: unknown,
): ContractValidation<ArtifactVerificationEvent> {
  if (validateArtifactVerification(value)) {
    return { valid: true, value };
  }

  return {
    valid: false,
    errors: validationErrors(validateArtifactVerification.errors),
  };
}

export function validateContextCaptureCommand(
  value: unknown,
): ContractValidation<ContextCaptureCommand> {
  if (validateContextCommand(value)) {
    const errors = artifactIdentityErrors(value.payload.artifact);
    if (errors.length > 0) {
      return {
        valid: false,
        errors: errors.map((error) => `/payload/artifact${error}`),
      };
    }
    return { valid: true, value };
  }

  return {
    valid: false,
    errors: validationErrors(validateContextCommand.errors),
  };
}

export function validateContextCapturedEvent(
  value: unknown,
): ContractValidation<ContextCapturedEvent> {
  if (validateContextEvent(value)) {
    const errors = artifactIdentityErrors(value.payload.artifact);
    if (errors.length > 0) {
      return {
        valid: false,
        errors: errors.map((error) => `/payload/artifact${error}`),
      };
    }
    return { valid: true, value };
  }

  return {
    valid: false,
    errors: validationErrors(validateContextEvent.errors),
  };
}

export function validateSessionCommand(
  value: unknown,
): ContractValidation<SessionCommand> {
  if (validateSessionCommandSchema(value)) {
    const payload = value.payload as unknown as {
      artifact?: ArtifactRef;
    };
    if (payload.artifact !== undefined) {
      const errors = artifactIdentityErrors(payload.artifact);
      if (errors.length > 0) {
        return {
          valid: false,
          errors: errors.map((error) => `/payload/artifact${error}`),
        };
      }
      if (
        payload.artifact.media_type !== "text/plain" ||
        payload.artifact.byte_size > 64 * 1024
      ) {
        return {
          valid: false,
          errors: ["/payload/artifact must be bounded UTF-8 text/plain"],
        };
      }
    }
    if (
      value.command_type === "session.register" &&
      value.payload.session_uri !==
        `pi-jsonl://session/${value.payload.pi_session_id}`
    ) {
      return {
        valid: false,
        errors: ["/payload/session_uri must match pi_session_id"],
      };
    }
    if (
      value.command_type === "session.workbench_bind" &&
      value.payload.workbench_id !== value.workbench_id
    ) {
      return {
        valid: false,
        errors: ["/payload/workbench_id must match /workbench_id"],
      };
    }
    return { valid: true, value };
  }
  return {
    valid: false,
    errors: validationErrors(validateSessionCommandSchema.errors),
  };
}

function validateSessionCommandType(
  value: unknown,
  commandType: SessionCommand["command_type"],
): ContractValidation<SessionCommand> {
  const result = validateSessionCommand(value);
  if (!result.valid) {
    return result;
  }
  if (result.value.command_type !== commandType) {
    return { valid: false, errors: [`/command_type must equal ${commandType}`] };
  }
  return result;
}

export function validateSessionRegisterCommand(
  value: unknown,
): ContractValidation<SessionRegisterCommand> {
  return validateSessionCommandType(value, "session.register") as ContractValidation<SessionRegisterCommand>;
}

export function validateSessionWorkbenchBindCommand(
  value: unknown,
): ContractValidation<SessionWorkbenchBindCommand> {
  return validateSessionCommandType(value, "session.workbench_bind") as ContractValidation<SessionWorkbenchBindCommand>;
}

export function validateSessionMessageSendCommand(
  value: unknown,
): ContractValidation<SessionMessageSendCommand> {
  return validateSessionCommandType(value, "session.message_send") as ContractValidation<SessionMessageSendCommand>;
}

export function validateSessionMessageReplyCommand(
  value: unknown,
): ContractValidation<SessionMessageReplyCommand> {
  return validateSessionCommandType(value, "session.message_reply") as ContractValidation<SessionMessageReplyCommand>;
}

export function validateSessionMessageReceiveCommand(
  value: unknown,
): ContractValidation<SessionMessageReceiveCommand> {
  return validateSessionCommandType(value, "session.message_receive") as ContractValidation<SessionMessageReceiveCommand>;
}

export function validateSessionMessageMarkInjectedCommand(
  value: unknown,
): ContractValidation<SessionMessageMarkInjectedCommand> {
  return validateSessionCommandType(value, "session.message_mark_injected") as ContractValidation<SessionMessageMarkInjectedCommand>;
}

export function validateSessionMessageAcknowledgeCommand(
  value: unknown,
): ContractValidation<SessionMessageAcknowledgeCommand> {
  return validateSessionCommandType(value, "session.message_acknowledge") as ContractValidation<SessionMessageAcknowledgeCommand>;
}

export function validateSessionEvent(
  value: unknown,
): ContractValidation<SessionEvent> {
  if (validateSessionEventSchema(value)) {
    return { valid: true, value };
  }
  return {
    valid: false,
    errors: validationErrors(validateSessionEventSchema.errors),
  };
}

function revisionCommandSemanticErrors(value: RevisionCommand): string[] {
  if (
    value.command_type === "workspace.revision_create" ||
    value.command_type === "workspace.merge_create"
  ) {
    const errors: string[] = [];
    const paths = new Set<string>();
    for (const [index, file] of value.payload.files.entries()) {
      if (paths.has(file.path)) {
        errors.push(`/payload/files/${index}/path must be unique within the command`);
      }
      if (file.path.split("/").some((component) => component.toLowerCase() === ".git")) {
        errors.push(`/payload/files/${index}/path must not contain a .git component`);
      }
      if (
        [...paths].some(
          (path) => path.startsWith(`${file.path}/`) || file.path.startsWith(`${path}/`),
        )
      ) {
        errors.push(`/payload/files/${index}/path must not collide with a file/directory ancestor`);
      }
      paths.add(file.path);
      const artifactErrors = artifactIdentityErrors(file.artifact);
      errors.push(
        ...artifactErrors.map(
          (error) => `/payload/files/${index}/artifact${error}`,
        ),
      );
    }
    if (
      value.command_type === "workspace.revision_create" &&
      value.expected_revision_id !== null &&
      value.expected_revision_id !== value.base_revision_id
    ) {
      errors.push("/expected_revision_id must match /base_revision_id");
    }
    if (
      value.command_type === "workspace.merge_create" &&
      value.expected_revision_id === value.base_revision_id
    ) {
      errors.push("merge project and variant parents must be distinct revisions");
    }
    return errors;
  }

  if (value.command_type === "strategy.variant_create") {
    const errors: string[] = [];
    if (value.payload.variant_id !== value.variant_id) {
      errors.push("/payload/variant_id must match /variant_id");
    }
    if (value.payload.base_revision_id !== value.base_revision_id) {
      errors.push("/payload/base_revision_id must match /base_revision_id");
    }
    return errors;
  }

  const errors: string[] = [];
  if (value.expected_revision_id !== value.base_revision_id) {
    errors.push("/expected_revision_id must match /base_revision_id");
  }
  if (value.payload.variant_id !== value.variant_id) {
    errors.push("/payload/variant_id must match /variant_id");
  }
  return errors;
}

export function validateRevisionCommand(
  value: unknown,
): ContractValidation<RevisionCommand> {
  if (!validateRevisionCommandSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateRevisionCommandSchema.errors),
    };
  }
  const errors = revisionCommandSemanticErrors(value);
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value };
}

function validateRevisionCommandType(
  value: unknown,
  commandType: RevisionCommand["command_type"],
): ContractValidation<RevisionCommand> {
  const result = validateRevisionCommand(value);
  if (!result.valid) {
    return result;
  }
  if (result.value.command_type !== commandType) {
    return { valid: false, errors: [`/command_type must equal ${commandType}`] };
  }
  return result;
}

export function validateWorkspaceRevisionCreateCommand(
  value: unknown,
): ContractValidation<WorkspaceRevisionCreateCommand> {
  return validateRevisionCommandType(
    value,
    "workspace.revision_create",
  ) as ContractValidation<WorkspaceRevisionCreateCommand>;
}

export function validateStrategyVariantCreateCommand(
  value: unknown,
): ContractValidation<StrategyVariantCreateCommand> {
  return validateRevisionCommandType(
    value,
    "strategy.variant_create",
  ) as ContractValidation<StrategyVariantCreateCommand>;
}

export function validateWorkspaceMergeCreateCommand(
  value: unknown,
): ContractValidation<WorkspaceMergeCreateCommand> {
  return validateRevisionCommandType(
    value,
    "workspace.merge_create",
  ) as ContractValidation<WorkspaceMergeCreateCommand>;
}

export function validateWorkspaceRevisionPromoteCommand(
  value: unknown,
): ContractValidation<WorkspaceRevisionPromoteCommand> {
  return validateRevisionCommandType(
    value,
    "workspace.revision_promote",
  ) as ContractValidation<WorkspaceRevisionPromoteCommand>;
}

function revisionEventSemanticErrors(value: RevisionEvent): string[] {
  if (value.event_type === "workspace.revision_created") {
    const isRoot = value.variant_id === null && value.base_revision_id === null;
    if (isRoot) {
      return value.payload.parent_revision_id === null
        ? []
        : ["/payload/parent_revision_id must be null for a root revision"];
    }
    return value.payload.parent_revision_id === value.base_revision_id
      ? []
      : ["/payload/parent_revision_id must match /base_revision_id"];
  }

  if (value.event_type === "strategy.variant_created") {
    const errors: string[] = [];
    if (value.payload.variant_id !== value.variant_id) {
      errors.push("/payload/variant_id must match /variant_id");
    }
    if (value.payload.revision_id !== value.base_revision_id) {
      errors.push("/payload/revision_id must match /base_revision_id");
    }
    return errors;
  }

  if (value.event_type === "workspace.merge_candidate_created") {
    const errors: string[] = [];
    if (value.payload.variant_parent_revision_id !== value.base_revision_id) {
      errors.push(
        "/payload/variant_parent_revision_id must match /base_revision_id",
      );
    }
    if (
      value.payload.project_parent_revision_id ===
      value.payload.variant_parent_revision_id
    ) {
      errors.push("merge parent revisions must be distinct");
    }
    return errors;
  }

  const errors: string[] = [];
  if (value.payload.variant_id !== value.variant_id) {
    errors.push("/payload/variant_id must match /variant_id");
  }
  if (value.payload.previous_revision_id !== value.base_revision_id) {
    errors.push("/payload/previous_revision_id must match /base_revision_id");
  }
  return errors;
}

export function validateRevisionEvent(
  value: unknown,
): ContractValidation<RevisionEvent> {
  if (!validateRevisionEventSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateRevisionEventSchema.errors),
    };
  }
  const errors = revisionEventSemanticErrors(value);
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value };
}

function validateRevisionEventType(
  value: unknown,
  eventType: RevisionEvent["event_type"],
): ContractValidation<RevisionEvent> {
  const result = validateRevisionEvent(value);
  if (!result.valid) {
    return result;
  }
  if (result.value.event_type !== eventType) {
    return { valid: false, errors: [`/event_type must equal ${eventType}`] };
  }
  return result;
}

export function validateWorkspaceRevisionCreatedEvent(
  value: unknown,
): ContractValidation<WorkspaceRevisionCreatedEvent> {
  return validateRevisionEventType(
    value,
    "workspace.revision_created",
  ) as ContractValidation<WorkspaceRevisionCreatedEvent>;
}

export function validateStrategyVariantCreatedEvent(
  value: unknown,
): ContractValidation<StrategyVariantCreatedEvent> {
  return validateRevisionEventType(
    value,
    "strategy.variant_created",
  ) as ContractValidation<StrategyVariantCreatedEvent>;
}

export function validateWorkspaceMergeCandidateCreatedEvent(
  value: unknown,
): ContractValidation<WorkspaceMergeCandidateCreatedEvent> {
  return validateRevisionEventType(
    value,
    "workspace.merge_candidate_created",
  ) as ContractValidation<WorkspaceMergeCandidateCreatedEvent>;
}

export function validateWorkspaceRevisionPromotedEvent(
  value: unknown,
): ContractValidation<WorkspaceRevisionPromotedEvent> {
  return validateRevisionEventType(
    value,
    "workspace.revision_promoted",
  ) as ContractValidation<WorkspaceRevisionPromotedEvent>;
}

export function validateFormalRunCommand(
  value: unknown,
): ContractValidation<FormalRunCommand> {
  if (!validateFormalRunCommandSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateFormalRunCommandSchema.errors),
    };
  }
  const errors = artifactIdentityErrors(value.payload.engine_input);
  if (value.expected_revision_id !== value.base_revision_id) {
    errors.push("/expected_revision_id must match /base_revision_id");
  }
  if (value.payload.candidate_revision_id !== value.base_revision_id) {
    errors.push("/payload/candidate_revision_id must match /base_revision_id");
  }
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value };
}

export function validateFormalRunEvent(
  value: unknown,
): ContractValidation<FormalRunEvent> {
  if (!validateFormalRunEventSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateFormalRunEventSchema.errors),
    };
  }
  const errors: string[] = [];
  if (value.payload.candidate_revision_id !== value.base_revision_id) {
    errors.push("/payload/candidate_revision_id must match /base_revision_id");
  }
  if (
    value.event_type === "formal.run_completed" &&
    value.payload.status === "succeeded" &&
    value.payload.calculation_hash !== value.payload.engine_result_sha256
  ) {
    errors.push(
      "/payload/calculation_hash must match /payload/engine_result_sha256",
    );
  }
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value };
}

export function validateDiagnosticLog(
  value: unknown,
): ContractValidation<DiagnosticLog> {
  if (validateLog(value)) {
    return { valid: true, value };
  }

  return { valid: false, errors: validationErrors(validateLog.errors) };
}

function manifestSemanticErrors(value: FormalRunManifestV1): string[] {
  const errors: string[] = [];
  if (
    value.engine_input.storage_uri !==
    `cas://sha256/${value.engine_input.sha256}`
  ) {
    errors.push("/engine_input/storage_uri must match /engine_input/sha256");
  }
  if (
    value.strategy_execution.intent_tape_storage_uri !==
    `cas://sha256/${value.strategy_execution.intent_tape_sha256}`
  ) {
    errors.push(
      "/strategy_execution/intent_tape_storage_uri must match /strategy_execution/intent_tape_sha256",
    );
  }
  if (
    value.engine_result.storage_uri !==
    `cas://sha256/${value.engine_result.sha256}`
  ) {
    errors.push("/engine_result/storage_uri must match /engine_result/sha256");
  }
  return errors;
}

export function validateProjectListReadModel(
  value: unknown,
): ContractValidation<ProjectListReadModel> {
  if (!validateProjectReadModelSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateProjectReadModelSchema.errors),
    };
  }
  if (!("projects" in value)) {
    return { valid: false, errors: ["/projects must be present"] };
  }
  return { valid: true, value: value as ProjectListReadModel };
}

export function validateActivityListReadModel(
  value: unknown,
): ContractValidation<ActivityListReadModel> {
  if (!validateProjectReadModelSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateProjectReadModelSchema.errors),
    };
  }
  if (!("activities" in value)) {
    return { valid: false, errors: ["/activities must be present"] };
  }
  return { valid: true, value: value as ActivityListReadModel };
}

export function validateArtifactMetadataReadModel(
  value: unknown,
): ContractValidation<ArtifactMetadataReadModel> {
  if (!validateArtifactMetadataSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateArtifactMetadataSchema.errors),
    };
  }
  const errors = artifactIdentityErrors(value);
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value };
}

export function validateFormalEngineResultV1(
  value: unknown,
): ContractValidation<FormalEngineResultV1> {
  if (!validateFormalEngineResultSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateFormalEngineResultSchema.errors),
    };
  }
  return { valid: true, value };
}

export function validateFormalRunManifestV1(
  value: unknown,
): ContractValidation<FormalRunManifestV1> {
  if (!validateFormalRunManifestSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateFormalRunManifestSchema.errors),
    };
  }
  const errors = manifestSemanticErrors(value);
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value };
}

function hasRunKind(
  artifact: ArtifactMetadataReadModel,
  runId: string,
  kind: "intent_tape" | "engine_result" | "manifest",
): boolean {
  return artifact.run_kinds.some(
    (entry) => entry.run_id === runId && entry.kind === kind,
  );
}

function formalRunDetailSemanticErrors(
  value: FormalRunDetailReadModel,
): string[] {
  const errors: string[] = [];
  const run = value.run;
  const runSpec = value.run_spec;
  const validation = value.validation;

  if (run.run_spec_id !== runSpec.run_spec_id) {
    errors.push("/run/run_spec_id must match /run_spec/run_spec_id");
  }
  if (run.project_id !== runSpec.project_id) {
    errors.push("/run/project_id must match /run_spec/project_id");
  }
  if (run.activity_id !== runSpec.activity_id) {
    errors.push("/run/activity_id must match /run_spec/activity_id");
  }
  if (run.variant_id !== runSpec.variant_id) {
    errors.push("/run/variant_id must match /run_spec/variant_id");
  }
  if (run.candidate_revision_id !== runSpec.candidate_revision_id) {
    errors.push(
      "/run/candidate_revision_id must match /run_spec/candidate_revision_id",
    );
  }
  if (validation.engine_version !== runSpec.engine_version) {
    errors.push("/validation/engine_version must match /run_spec/engine_version");
  }
  if (validation.gate_policy_version !== runSpec.gate_policy_version) {
    errors.push(
      "/validation/gate_policy_version must match /run_spec/gate_policy_version",
    );
  }

  for (const [index, log] of value.logs.entries()) {
    if (log.project_id !== run.project_id) {
      errors.push(`/logs/${index}/project_id must match /run/project_id`);
    }
    if (log.activity_id !== run.activity_id) {
      errors.push(`/logs/${index}/activity_id must match /run/activity_id`);
    }
    if (log.run_id !== run.run_id) {
      errors.push(`/logs/${index}/run_id must match /run/run_id`);
    }
    if (log.job_id !== run.job_id) {
      errors.push(`/logs/${index}/job_id must match /run/job_id`);
    }
  }

  if (run.status === "failed") {
    return errors;
  }

  const succeeded = value as FormalRunSucceededDetailReadModel;
  const manifest = succeeded.manifest;
  const engineResult = succeeded.engine_result;
  const intentArtifact = succeeded.artifacts.intent_tape;
  const engineArtifact = succeeded.artifacts.engine_result;
  const manifestArtifact = succeeded.artifacts.manifest;

  if (manifest.engine_result.sha256 !== run.calculation_hash) {
    return ["/manifest/engine_result/sha256 must match /run/calculation_hash"];
  }
  if (manifest.engine_result.artifact_id !== run.engine_result_artifact_id) {
    errors.push(
      "/manifest/engine_result/artifact_id must match /run/engine_result_artifact_id",
    );
  }
  if (engineArtifact.artifact_id !== run.engine_result_artifact_id) {
    errors.push(
      "/artifacts/engine_result/artifact_id must match /run/engine_result_artifact_id",
    );
  }
  if (engineArtifact.sha256 !== run.calculation_hash) {
    errors.push("/artifacts/engine_result/sha256 must match /run/calculation_hash");
  }
  if (manifestArtifact.artifact_id !== run.manifest_artifact_id) {
    errors.push(
      "/artifacts/manifest/artifact_id must match /run/manifest_artifact_id",
    );
  }
  if (validation.manifest_artifact_id !== run.manifest_artifact_id) {
    errors.push(
      "/validation/manifest_artifact_id must match /run/manifest_artifact_id",
    );
  }
  if (manifest.run_id !== run.run_id) {
    errors.push("/manifest/run_id must match /run/run_id");
  }
  if (manifest.validation_id !== validation.validation_id) {
    errors.push("/manifest/validation_id must match /validation/validation_id");
  }
  if (manifest.run_spec.run_spec_id !== runSpec.run_spec_id) {
    errors.push("/manifest/run_spec/run_spec_id must match /run_spec/run_spec_id");
  }
  if (manifest.run_spec.spec_hash !== runSpec.spec_hash) {
    errors.push("/manifest/run_spec/spec_hash must match /run_spec/spec_hash");
  }
  if (manifest.run_spec.project_id !== runSpec.project_id) {
    errors.push("/manifest/run_spec/project_id must match /run_spec/project_id");
  }
  if (manifest.run_spec.activity_id !== runSpec.activity_id) {
    errors.push("/manifest/run_spec/activity_id must match /run_spec/activity_id");
  }
  if (manifest.run_spec.variant_id !== runSpec.variant_id) {
    errors.push("/manifest/run_spec/variant_id must match /run_spec/variant_id");
  }
  if (
    manifest.run_spec.candidate_revision_id !== runSpec.candidate_revision_id
  ) {
    errors.push(
      "/manifest/run_spec/candidate_revision_id must match /run_spec/candidate_revision_id",
    );
  }
  const manifestRunSpecBindings = [
    ["data_snapshot_id", "/manifest/run_spec/data_snapshot_id"],
    ["data_snapshot_sha256", "/manifest/run_spec/data_snapshot_sha256"],
    ["strategy_tree_oid", "/manifest/run_spec/strategy_tree_oid"],
    ["parameters_sha256", "/manifest/run_spec/parameters_sha256"],
    ["cost_model_sha256", "/manifest/run_spec/cost_model_sha256"],
    ["environment_lock_sha256", "/manifest/run_spec/environment_lock_sha256"],
    ["engine_version", "/manifest/run_spec/engine_version"],
    ["price_basis", "/manifest/run_spec/price_basis"],
    ["cutoff", "/manifest/run_spec/cutoff"],
    ["timezone", "/manifest/run_spec/timezone"],
    ["sample_start", "/manifest/run_spec/sample_start"],
    ["sample_end", "/manifest/run_spec/sample_end"],
    ["random_seed", "/manifest/run_spec/random_seed"],
    ["output_schema_version", "/manifest/run_spec/output_schema_version"],
    ["gate_policy_version", "/manifest/run_spec/gate_policy_version"],
  ] as const;
  for (const [key, path] of manifestRunSpecBindings) {
    if (manifest.run_spec[key] !== runSpec[key]) {
      errors.push(`${path} must match /run_spec/${key}`);
    }
  }
  if (manifest.revision.candidate_revision_id !== run.candidate_revision_id) {
    errors.push(
      "/manifest/revision/candidate_revision_id must match /run/candidate_revision_id",
    );
  }
  if (manifest.engine_input.artifact_id !== runSpec.engine_input_artifact_id) {
    errors.push(
      "/manifest/engine_input/artifact_id must match /run_spec/engine_input_artifact_id",
    );
  }
  if (
    manifest.strategy_execution.intent_tape_artifact_id !==
    intentArtifact.artifact_id
  ) {
    errors.push(
      "/manifest/strategy_execution/intent_tape_artifact_id must match /artifacts/intent_tape/artifact_id",
    );
  }
  if (
    manifest.strategy_execution.intent_tape_sha256 !== intentArtifact.sha256
  ) {
    errors.push(
      "/manifest/strategy_execution/intent_tape_sha256 must match /artifacts/intent_tape/sha256",
    );
  }
  if (
    manifest.strategy_execution.intent_tape_storage_uri !==
    intentArtifact.storage_uri
  ) {
    errors.push(
      "/manifest/strategy_execution/intent_tape_storage_uri must match /artifacts/intent_tape/storage_uri",
    );
  }
  if (
    manifest.engine_input.storage_uri !==
    `cas://sha256/${manifest.engine_input.sha256}`
  ) {
    errors.push("/manifest/engine_input/storage_uri must match /engine_input/sha256");
  }
  if (
    manifest.engine_result.storage_uri !==
    `cas://sha256/${manifest.engine_result.sha256}`
  ) {
    errors.push("/manifest/engine_result/storage_uri must match /engine_result/sha256");
  }
  if (manifest.engine_result.storage_uri !== engineArtifact.storage_uri) {
    errors.push(
      "/manifest/engine_result/storage_uri must match /artifacts/engine_result/storage_uri",
    );
  }
  if (engineResult.schema_version !== manifest.engine_result.schema_version) {
    errors.push(
      "/engine_result/schema_version must match /manifest/engine_result/schema_version",
    );
  }
  if (engineResult.schema_version !== runSpec.output_schema_version) {
    errors.push(
      "/engine_result/schema_version must match /run_spec/output_schema_version",
    );
  }
  if (engineResult.engine_version !== manifest.engine_result.engine_version) {
    errors.push(
      "/engine_result/engine_version must match /manifest/engine_result/engine_version",
    );
  }
  if (engineResult.engine_version !== runSpec.engine_version) {
    errors.push("/engine_result/engine_version must match /run_spec/engine_version");
  }
  if (manifest.logs.run_id !== run.run_id) {
    errors.push("/manifest/logs/run_id must match /run/run_id");
  }

  for (const [artifactName, artifact, kind] of [
    ["intent_tape", intentArtifact, "intent_tape"],
    ["engine_result", engineArtifact, "engine_result"],
    ["manifest", manifestArtifact, "manifest"],
  ] as const) {
    const identityErrors = artifactIdentityErrors(artifact);
    errors.push(
      ...identityErrors.map((error) => `/artifacts/${artifactName}${error}`),
    );
    if (!hasRunKind(artifact, run.run_id, kind)) {
      errors.push(
        `/artifacts/${artifactName}/run_kinds must contain /run/run_id and kind`,
      );
    }
    if (artifact.project_id !== run.project_id) {
      errors.push(
        `/artifacts/${artifactName}/project_id must match /run/project_id`,
      );
    }
  }
  return errors;
}

export function validateFormalRunListReadModel(
  value: unknown,
): ContractValidation<FormalRunListReadModel> {
  if (!validateFormalRunReadModelSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateFormalRunReadModelSchema.errors),
    };
  }
  if (!("runs" in value)) {
    return { valid: false, errors: ["/runs must be present"] };
  }
  return { valid: true, value: value as FormalRunListReadModel };
}

export function validateFormalRunDetailReadModel(
  value: unknown,
): ContractValidation<FormalRunDetailReadModel> {
  if (!validateFormalRunReadModelSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateFormalRunReadModelSchema.errors),
    };
  }
  if (!("run" in value)) {
    return { valid: false, errors: ["/run must be present"] };
  }
  const detail = value as FormalRunDetailReadModel;
  const errors = formalRunDetailSemanticErrors(detail);
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value: detail };
}

export function validateDomainEvent(
  value: unknown,
): ContractValidation<DomainEvent> {
  const envelope = validateEventEnvelope(value);
  if (!envelope.valid) {
    return envelope;
  }
  if (envelope.value.event_type === "context.captured") {
    return validateContextCapturedEvent(value);
  }
  if (
    envelope.value.event_type === "artifact.verification_succeeded" ||
    envelope.value.event_type === "artifact.verification_failed" ||
    envelope.value.event_type === "artifact.verification_started"
  ) {
    return validateArtifactVerificationEvent(value);
  }
  if (SESSION_EVENT_TYPES.has(envelope.value.event_type)) {
    return validateSessionEvent(value);
  }
  if (REVISION_EVENT_TYPES.has(envelope.value.event_type)) {
    return validateRevisionEvent(value);
  }
  if (FORMAL_RUN_EVENT_TYPES.has(envelope.value.event_type)) {
    return validateFormalRunEvent(value);
  }
  return {
    valid: false,
    errors: [`unsupported domain event type ${envelope.value.event_type}`],
  };
}
