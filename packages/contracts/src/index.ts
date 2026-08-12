import { Ajv2020, type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import artifactVerificationEventSchemaDocument from "../schemas/v1/artifact-verification-event.schema.json" with { type: "json" };
import artifactRefSchemaDocument from "../schemas/v1/artifact-ref.schema.json" with { type: "json" };
import artifactReadModelSchemaDocument from "../schemas/v1/artifact-read-model.schema.json" with { type: "json" };
import commandEnvelopeSchemaDocument from "../schemas/v1/command-envelope.schema.json" with { type: "json" };
import contextCaptureCommandSchemaDocument from "../schemas/v1/context-capture-command.schema.json" with { type: "json" };
import contextCapturedEventSchemaDocument from "../schemas/v1/context-captured-event.schema.json" with { type: "json" };
import dataSnapshotCommandSchemaDocument from "../schemas/v1/data-snapshot-command.schema.json" with { type: "json" };
import dataSnapshotEventSchemaDocument from "../schemas/v1/data-snapshot-event.schema.json" with { type: "json" };
import dataSnapshotReadModelSchemaDocument from "../schemas/v1/data-snapshot-read-model.schema.json" with { type: "json" };
import diagnosticLogSchemaDocument from "../schemas/v1/diagnostic-log.schema.json" with { type: "json" };
import diagnosticCommandSchemaDocument from "../schemas/v1/diagnostic-command.schema.json" with { type: "json" };
import diagnosticEventSchemaDocument from "../schemas/v1/diagnostic-event.schema.json" with { type: "json" };
import diagnosticLogReadModelSchemaDocument from "../schemas/v1/diagnostic-log-read-model.schema.json" with { type: "json" };
import eventEnvelopeSchemaDocument from "../schemas/v1/event-envelope.schema.json" with { type: "json" };
import formalEngineResultSchemaDocument from "../schemas/v1/formal-engine-result.schema.json" with { type: "json" };
import formalEngineResultV2SchemaDocument from "../schemas/v1/formal-engine-result-v2.schema.json" with { type: "json" };
import formalRunCommandSchemaDocument from "../schemas/v1/formal-run-command.schema.json" with { type: "json" };
import formalRunEventSchemaDocument from "../schemas/v1/formal-run-event.schema.json" with { type: "json" };
import formalRunManifestSchemaDocument from "../schemas/v1/formal-run-manifest.schema.json" with { type: "json" };
import formalRunReadModelSchemaDocument from "../schemas/v1/formal-run-read-model.schema.json" with { type: "json" };
import forwardTestCommandSchemaDocument from "../schemas/v1/forward-test-command.schema.json" with { type: "json" };
import forwardTestEventSchemaDocument from "../schemas/v1/forward-test-event.schema.json" with { type: "json" };
import forwardTestReadModelSchemaDocument from "../schemas/v1/forward-test-read-model.schema.json" with { type: "json" };
import projectArchiveCommandSchemaDocument from "../schemas/v1/project-archive-command.schema.json" with { type: "json" };
import projectArchiveEventSchemaDocument from "../schemas/v1/project-archive-event.schema.json" with { type: "json" };
import projectArchiveManifestSchemaDocument from "../schemas/v1/project-archive-manifest.schema.json" with { type: "json" };
import projectReadModelSchemaDocument from "../schemas/v1/project-read-model.schema.json" with { type: "json" };
import revisionCommandSchemaDocument from "../schemas/v1/revision-command.schema.json" with { type: "json" };
import revisionEventSchemaDocument from "../schemas/v1/revision-event.schema.json" with { type: "json" };
import runReportSchemaDocument from "../schemas/v1/run-report.schema.json" with { type: "json" };
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
export const dataSnapshotCommandSchema: Record<string, unknown> =
  dataSnapshotCommandSchemaDocument;
export const dataSnapshotEventSchema: Record<string, unknown> =
  dataSnapshotEventSchemaDocument;
export const dataSnapshotReadModelSchema: Record<string, unknown> =
  dataSnapshotReadModelSchemaDocument;
export const diagnosticLogSchema: Record<string, unknown> =
  diagnosticLogSchemaDocument;
export const diagnosticCommandSchema: Record<string, unknown> =
  diagnosticCommandSchemaDocument;
export const diagnosticEventSchema: Record<string, unknown> =
  diagnosticEventSchemaDocument;
export const diagnosticLogReadModelSchema: Record<string, unknown> =
  diagnosticLogReadModelSchemaDocument;
export const eventEnvelopeSchema: Record<string, unknown> =
  eventEnvelopeSchemaDocument;
export const formalEngineResultSchema: Record<string, unknown> =
  formalEngineResultSchemaDocument;
export const formalEngineResultV2Schema: Record<string, unknown> =
  formalEngineResultV2SchemaDocument;
export const formalRunCommandSchema: Record<string, unknown> =
  formalRunCommandSchemaDocument;
export const formalRunEventSchema: Record<string, unknown> =
  formalRunEventSchemaDocument;
export const formalRunManifestSchema: Record<string, unknown> =
  formalRunManifestSchemaDocument;
export const formalRunReadModelSchema: Record<string, unknown> =
  formalRunReadModelSchemaDocument;
export const forwardTestCommandSchema: Record<string, unknown> =
  forwardTestCommandSchemaDocument;
export const forwardTestEventSchema: Record<string, unknown> =
  forwardTestEventSchemaDocument;
export const forwardTestReadModelSchema: Record<string, unknown> =
  forwardTestReadModelSchemaDocument;
export const projectArchiveCommandSchema: Record<string, unknown> =
  projectArchiveCommandSchemaDocument;
export const projectArchiveEventSchema: Record<string, unknown> =
  projectArchiveEventSchemaDocument;
export const projectArchiveManifestSchema: Record<string, unknown> =
  projectArchiveManifestSchemaDocument;
export const projectReadModelSchema: Record<string, unknown> =
  projectReadModelSchemaDocument;
export const revisionCommandSchema: Record<string, unknown> =
  revisionCommandSchemaDocument;
export const revisionEventSchema: Record<string, unknown> = revisionEventSchemaDocument;
export const runReportSchema: Record<string, unknown> = runReportSchemaDocument;
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
  removed_paths?: string[];
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

export interface FormalRunRequestPayloadCommon extends Record<string, unknown> {
  run_spec_id: string;
  run_id: string;
  validation_id: string;
  candidate_revision_id: string;
  market_input: ArtifactRef;
  data_snapshot_id: string;
  data_snapshot_sha256: string;
  strategy_tree_oid: string;
  parameters_sha256: string;
  cost_model_sha256: string;
  environment_lock_sha256: string;
  price_basis: "raw" | "qfq" | "hfq";
  cutoff: string;
  timezone: string;
  sample_start: string;
  sample_end: string;
  random_seed: number;
  checkpoint_batch_size: number;
}

export interface FormalRunM5RequestPayload extends FormalRunRequestPayloadCommon {
  engine_version: "oqs-quant-engine/0.1.0";
  output_schema_version: 1;
  gate_policy_version: "m5-v1";
  strategy_protocol_version: "oqs-strategy-host/m5-stream-v2";
  engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v1";
}

export interface FormalRunM8RequestPayload extends FormalRunRequestPayloadCommon {
  engine_version: "oqs-quant-engine/0.2.0";
  output_schema_version: 2;
  gate_policy_version: "m8-v1";
  strategy_protocol_version: "oqs-strategy-host/m8-portfolio-v1";
  engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v2";
}

export type FormalRunRequestPayload =
  | FormalRunM5RequestPayload
  | FormalRunM8RequestPayload;

export type FormalRunRequestCommand = CommandEnvelope<FormalRunRequestPayload> & {
  command_type: "formal.run_request";
  expected_revision_id: string;
  variant_id: string;
  base_revision_id: string;
};

export interface FormalRunCancelPayload extends Record<string, unknown> {
  run_id: string;
  expected_status: "pending" | "running";
  expected_execution_version: number;
  reason: "user_requested";
}

export type FormalRunCancelCommand = CommandEnvelope<FormalRunCancelPayload> & {
  command_type: "formal.run_cancel";
  expected_revision_id: string;
  variant_id: string;
  base_revision_id: string;
};

export interface FormalRunRetryPayload extends Record<string, unknown> {
  source_run_id: string;
  source_execution_version: number;
  run_id: string;
  validation_id: string;
}

export type FormalRunRetryCommand = CommandEnvelope<FormalRunRetryPayload> & {
  command_type: "formal.run_retry";
  expected_revision_id: string;
  variant_id: string;
  base_revision_id: string;
};

export type FormalRunCommand =
  | FormalRunRequestCommand
  | FormalRunCancelCommand
  | FormalRunRetryCommand;

export interface FormalRunActivePayload extends Record<string, unknown> {
  job_id: string;
  run_spec_id: string;
  run_id: string;
  validation_id: string;
  candidate_revision_id: string;
  run_spec_hash: string;
}

export interface FormalRunCompletedSucceededPayload extends FormalRunActivePayload {
  status: "succeeded";
  gates: {
    contract: "passed";
    strategy_import: "passed";
    smoke_run: "passed";
  };
  engine_result_artifact_id: string;
  engine_result_sha256: string;
  manifest_artifact_id: string;
  manifest_sha256: string;
  calculation_hash: string;
  error_code: null;
}

export interface FormalRunCompletedFailedPayload extends FormalRunActivePayload {
  status: "failed";
  gates: {
    contract: "passed" | "failed";
    strategy_import: "passed" | "failed";
    smoke_run: "passed" | "failed";
  };
  engine_result_artifact_id: null;
  engine_result_sha256: null;
  manifest_artifact_id: null;
  manifest_sha256: null;
  calculation_hash: null;
  error_code: FormalRunErrorCode;
}

export type FormalRunCompletedPayload =
  | FormalRunCompletedSucceededPayload
  | FormalRunCompletedFailedPayload;

export interface FormalRunM5ActivePayload extends FormalRunActivePayload {
  lifecycle_version: "m5-v1" | "m8-v1";
  execution_version: number;
}

export interface FormalRunCheckpointPayloadCommon extends FormalRunM5ActivePayload {
  claim_epoch: number;
  checkpoint_seq: number;
  checkpoint_artifact_id: string;
  checkpoint_sha256: string;
  calculation_context_sha256: string;
}

export type FormalRunCheckpointPayload =
  | (FormalRunCheckpointPayloadCommon & {
      lifecycle_version: "m5-v1";
      next_bar_index: number;
    })
  | (FormalRunCheckpointPayloadCommon & {
      lifecycle_version: "m8-v1";
      next_session_index: number;
    });

export type FormalRunM5CompletedPayload = FormalRunCompletedPayload & {
  lifecycle_version: "m5-v1" | "m8-v1";
  execution_version: number;
};

export interface FormalRunCancelledPayload extends FormalRunM5ActivePayload {
  status: "cancelled";
  validation_outcome: "not_run";
  gates: {
    contract: "not_run";
    strategy_import: "not_run";
    smoke_run: "not_run";
  };
  engine_result_artifact_id: null;
  manifest_artifact_id: null;
  calculation_hash: null;
  error_code: null;
  cancel_reason: "user_requested";
}

export interface FormalRunRetriedPayload extends FormalRunM5ActivePayload {
  execution_version: 0;
  source_run_id: string;
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
    })
  | (EventEnvelope<FormalRunM5ActivePayload> & {
      event_type: "formal.run_queued" | "formal.run_started" | "formal.run_prepared";
      variant_id: string;
      base_revision_id: string;
    })
  | (EventEnvelope<FormalRunCheckpointPayload> & {
      event_type: "formal.run_checkpointed" | "formal.run_resumed";
      variant_id: string;
      base_revision_id: string;
    })
  | (EventEnvelope<FormalRunM5CompletedPayload> & {
      event_type: "formal.run_completed";
      variant_id: string;
      base_revision_id: string;
    })
  | (EventEnvelope<FormalRunCancelledPayload> & {
      event_type: "formal.run_cancelled";
      variant_id: string;
      base_revision_id: string;
    })
  | (EventEnvelope<FormalRunRetriedPayload> & {
      event_type: "formal.run_retried";
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

export const FORMAL_RUN_COMMAND_TYPES = new Set([
  "formal.run_request",
  "formal.run_cancel",
  "formal.run_retry",
]);
export const FORMAL_RUN_EVENT_TYPES = new Set([
  "formal.run_queued",
  "formal.run_started",
  "formal.run_prepared",
  "formal.run_checkpointed",
  "formal.run_resumed",
  "formal.run_completed",
  "formal.run_cancelled",
  "formal.run_retried",
]);

export const M3_COMMAND_TYPES = new Set([
  ...REVISION_COMMAND_TYPES,
  "formal.run_request",
]);
export const M3_EVENT_TYPES = new Set([
  ...REVISION_EVENT_TYPES,
  "formal.run_queued",
  "formal.run_started",
  "formal.run_completed",
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

export interface DiagnosticLogDeletePayload extends Record<string, unknown> {
  selection:
    | { log_ids: string[] }
    | {
        activity_id?: string;
        session_id?: string;
        run_id?: string;
        from?: string;
        to?: string;
        levels?: Array<"debug" | "info" | "warn" | "error">;
        priorities?: Array<"p1" | "p2" | "p3" | "p4">;
        query?: string;
      };
}

export interface DiagnosticRetentionConfigurePayload
  extends Record<string, unknown> {
  debug_days: number;
  info_days: number;
  warn_days: number;
  quota_bytes: number;
}

export type DiagnosticCommand =
  | (CommandEnvelope<DiagnosticLogDeletePayload> & {
      command_type: "diagnostic.log_delete";
      expected_revision_id: null;
      variant_id: null;
      base_revision_id: null;
    })
  | (CommandEnvelope<DiagnosticRetentionConfigurePayload> & {
      command_type: "diagnostic.log_retention_configure";
      expected_revision_id: null;
      variant_id: null;
      base_revision_id: null;
    });

export interface DiagnosticDeletionReceipt extends Record<string, unknown> {
  receipt_id: string;
  reason: "user" | "retention" | "quota";
  selection_sha256: string;
  deleted_count: number;
  completed_at: string;
}

export type DiagnosticEvent = EventEnvelope<DiagnosticDeletionReceipt> & {
  event_type: "diagnostic.logs_deleted" | "diagnostic.retention_applied";
  variant_id: null;
  base_revision_id: null;
};

export interface ProjectArchiveCasObjectV1 {
  sha256: string;
  path: string;
  byte_size: number;
}

export interface ProjectArchiveManifestV1 {
  schema_version: 1;
  archive_schema_version: "oqs-project-archive/v1";
  project_id: string;
  activity_ids: string[];
  selected_logs: "full" | "warn_error" | "none";
  created_at: string;
  git: {
    bundle_path: "git/project.bundle";
    sha256: string;
    byte_size: number;
    object_format: "sha1";
    refs: Array<{ name: string; oid: string }>;
  };
  run_spec_ids: string[];
  run_ids: string[];
  report_artifact_ids: string[];
  cas_objects: ProjectArchiveCasObjectV1[];
}

export interface ProjectArchiveImportPayload extends Record<string, unknown> {
  expected_project_id: string;
  archive: ArtifactRef;
}

export type ProjectArchiveCommand = CommandEnvelope<ProjectArchiveImportPayload> & {
  command_type: "project.archive_import";
  expected_revision_id: null;
  variant_id: null;
  base_revision_id: null;
};

export interface ProjectArchiveImportedPayload extends Record<string, unknown> {
  archive_artifact_id: string;
  archive_sha256: string;
  manifest_sha256: string;
  restored_project_id: string;
  run_count: number;
  artifact_count: number;
  git_ref_count: number;
}

export type ProjectArchiveEvent = EventEnvelope<ProjectArchiveImportedPayload> & {
  event_type: "project.archive_imported";
  variant_id: null;
  base_revision_id: null;
};

export interface ForwardTestRequestPayload extends Record<string, unknown> {
  forward_test_id: string;
  source_run_id: string;
  protocol_version: "oqs-forward-replay/m5-v1";
}

export type ForwardTestCommand = CommandEnvelope<ForwardTestRequestPayload> & {
  command_type: "forward_test.request";
  expected_revision_id: string;
  variant_id: string;
  base_revision_id: string;
};

export interface ForwardTestCompletedPayload extends Record<string, unknown> {
  forward_test_id: string;
  source_run_id: string;
  source_revision_id: string;
  data_snapshot_id: string;
  protocol_version: "oqs-forward-replay/m5-v1";
  released_bar_count: number;
  transcript_artifact_id: string;
  transcript_sha256: string;
  intent_tape_sha256: string;
  status: "passed" | "failed";
  error_code:
    | "source_run_not_succeeded"
    | "strategy_protocol_failed"
    | "transcript_integrity_mismatch"
    | null;
}

export type ForwardTestEvent = EventEnvelope<ForwardTestCompletedPayload> & {
  event_type: "forward_test.completed";
  variant_id: string;
  base_revision_id: string;
};

export interface ForwardTestReadModel extends ForwardTestCompletedPayload {
  project_id: string;
  activity_id: string;
  variant_id: string;
  created_at: string;
}

export const DIAGNOSTIC_COMMAND_TYPES = new Set([
  "diagnostic.log_delete",
  "diagnostic.log_retention_configure",
]);
export const DIAGNOSTIC_EVENT_TYPES = new Set([
  "diagnostic.logs_deleted",
  "diagnostic.retention_applied",
]);
export const PROJECT_ARCHIVE_COMMAND_TYPES = new Set(["project.archive_import"]);
export const PROJECT_ARCHIVE_EVENT_TYPES = new Set(["project.archive_imported"]);
export const FORWARD_TEST_COMMAND_TYPES = new Set(["forward_test.request"]);
export const FORWARD_TEST_EVENT_TYPES = new Set(["forward_test.completed"]);

export const M5_COMMAND_TYPES = new Set([
  ...FORMAL_RUN_COMMAND_TYPES,
  ...DIAGNOSTIC_COMMAND_TYPES,
  ...PROJECT_ARCHIVE_COMMAND_TYPES,
  ...FORWARD_TEST_COMMAND_TYPES,
]);
export const M5_EVENT_TYPES = new Set([
  ...FORMAL_RUN_EVENT_TYPES,
  ...DIAGNOSTIC_EVENT_TYPES,
  ...PROJECT_ARCHIVE_EVENT_TYPES,
  ...FORWARD_TEST_EVENT_TYPES,
]);

export interface DataSnapshotMapping extends Record<string, unknown> {
  timestamp: string;
  symbol: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

export type DataSnapshotMarket = "a_share_daily" | "crypto_linear_perp";
export type DataSnapshotSourceFormat = "csv" | "parquet";
export type DataSnapshotPriceBasis = "raw" | "qfq" | "hfq";

export interface DataSnapshotSourceArtifact extends M1ArtifactRef {
  media_type: "text/csv" | "application/vnd.apache.parquet";
  byte_size: number;
  provenance: {
    origin_kind: "user_upload";
    source_ref: string;
  };
}

export interface DataSnapshotCreatePayload extends Record<string, unknown> {
  snapshot_id: string;
  source: DataSnapshotSourceArtifact;
  source_format: DataSnapshotSourceFormat;
  file_name: string;
  mapping: DataSnapshotMapping;
  market: DataSnapshotMarket;
  timezone: string;
  price_basis: DataSnapshotPriceBasis;
  cutoff: string;
}

export type DataSnapshotCreateCommand = CommandEnvelope<DataSnapshotCreatePayload> & {
  command_type: "data.snapshot_create";
  expected_revision_id: null;
  variant_id: null;
  base_revision_id: null;
};

export interface DataSnapshotCreatedPayload extends Record<string, unknown> {
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
}

export type DataSnapshotCreatedEvent = EventEnvelope<DataSnapshotCreatedPayload> & {
  event_type: "data.snapshot_created";
  variant_id: null;
  base_revision_id: null;
};

export interface DataImportPreviewReadModel {
  source: DataSnapshotSourceArtifact;
  source_format: DataSnapshotSourceFormat;
  file_name: string;
  columns: string[];
  suggested_mapping: DataSnapshotMapping;
  preview_rows: Array<Record<string, string>>;
  total_rows: number;
}

export interface DataSnapshotReadModel extends DataSnapshotCreatedPayload {
  project_id: string;
  mapping: DataSnapshotMapping;
  source_sha256: string;
  normalized_sha256: string;
  market_input_sha256: string;
}

export interface DataSnapshotListReadModel {
  snapshots: DataSnapshotReadModel[];
}

export const DATA_SNAPSHOT_COMMAND_TYPES = new Set(["data.snapshot_create"]);
export const DATA_SNAPSHOT_EVENT_TYPES = new Set(["data.snapshot_created"]);
export const M7_COMMAND_TYPES = new Set([
  ...M5_COMMAND_TYPES,
  ...DATA_SNAPSHOT_COMMAND_TYPES,
]);
export const M7_EVENT_TYPES = new Set([
  ...M5_EVENT_TYPES,
  ...DATA_SNAPSHOT_EVENT_TYPES,
]);

export type DomainEvent =
  | ContextCapturedEvent
  | ArtifactVerificationEvent
  | SessionEvent
  | RevisionEvent
  | FormalRunEvent
  | DiagnosticEvent
  | ProjectArchiveEvent
  | ForwardTestEvent
  | DataSnapshotCreatedEvent;

export interface DiagnosticLog {
  log_id: string;
  log_seq: number;
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

export interface DiagnosticLogListReadModel {
  logs: DiagnosticLog[];
  next_after_log_seq: number | null;
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
    kind: "intent_tape" | "engine_result" | "manifest" | "report_json" | "report_html";
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

export interface FormalEngineResultV2 {
  schema_version: 2;
  engine_version: "oqs-quant-engine/0.2.0";
  account_model: "a_share_portfolio_cash";
  orders: Array<FormalEngineOrderV1 & { symbol: string }>;
  trades: Array<FormalEngineTradeV1 & { symbol: string }>;
  positions: Array<FormalEnginePositionV1 & { symbol: string }>;
  cash_ledger: Array<FormalEngineCashLedgerV1 & { symbol: string }>;
  funding_ledger: [];
  equity_curve: Array<{
    session_seq: number;
    timestamp: string;
    cash_atoms: FormalAtom;
    market_value_atoms: FormalAtom;
    equity_atoms: FormalAtom;
  }>;
  drawdown_curve: FormalEngineDrawdownPointV1[];
  metrics: FormalEngineMetricsV1;
  costs: FormalEngineCostsV1;
  assumptions: {
    fill_model: "portfolio_ohlc_market_open_v2";
    partial_fills: false;
    liquidate_on_end: false;
    research_short: false;
    research_short_notice: null;
    one_x_notional: false;
    shared_cash: true;
    per_symbol_t_plus_one: true;
  };
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

export interface FormalRunManifestRunSpecM5V1 {
  run_spec_id: string;
  spec_hash: string;
  project_id: string;
  activity_id: string;
  variant_id: string;
  candidate_revision_id: string;
  market_input_artifact_id: string;
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
  gate_policy_version: "m5-v1";
  strategy_protocol_version: "oqs-strategy-host/m5-stream-v2";
  checkpoint_batch_size: number;
  engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v1";
}

export type FormalRunManifestRunSpecM8V1 = Omit<
  FormalRunManifestRunSpecM5V1,
  | "engine_version"
  | "output_schema_version"
  | "gate_policy_version"
  | "strategy_protocol_version"
  | "engine_checkpoint_abi"
> & {
  engine_version: "oqs-quant-engine/0.2.0";
  output_schema_version: 2;
  gate_policy_version: "m8-v1";
  strategy_protocol_version: "oqs-strategy-host/m8-portfolio-v1";
  engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v2";
};

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

export interface FormalRunManifestStrategyExecutionM5V1 {
  intent_tape_artifact_id: string;
  intent_tape_sha256: string;
  intent_tape_byte_size: number;
  intent_tape_storage_uri: string;
  timing_authority: "oqs-strategy-host/m5-stream-v2";
  frozen: true;
}

export type FormalRunManifestStrategyExecutionM8V1 = Omit<
  FormalRunManifestStrategyExecutionM5V1,
  "timing_authority"
> & {
  timing_authority: "oqs-strategy-host/m8-portfolio-v1";
};

export interface FormalRunManifestCheckpointM5V1 {
  engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v1";
  checkpoint_batch_size: number;
  final_checkpoint_seq: number;
  final_next_bar_index: number;
  calculation_context_sha256: string;
}

export interface FormalRunManifestCheckpointM8V1 {
  engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v2";
  checkpoint_batch_size: number;
  final_checkpoint_seq: number;
  final_next_session_index: number;
  calculation_context_sha256: string;
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

export type FormalRunManifestEngineResultM8V1 = Omit<
  FormalRunManifestEngineResultV1,
  "schema_version" | "engine_version"
> & {
  schema_version: 2;
  engine_version: "oqs-quant-engine/0.2.0";
};

export interface FormalRunManifestM3V1 {
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

export interface FormalRunManifestM5V1 {
  schema_version: 1;
  manifest_version: "m5-v1";
  run_id: string;
  validation_id: string;
  run_spec: FormalRunManifestRunSpecM5V1;
  revision: FormalRunManifestRevisionV1;
  market_input: FormalRunManifestEngineInputV1;
  strategy_execution: FormalRunManifestStrategyExecutionM5V1;
  resolved_engine_input: FormalRunManifestEngineInputV1;
  checkpoint: FormalRunManifestCheckpointM5V1;
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

export interface FormalRunManifestM8V1 {
  schema_version: 1;
  manifest_version: "m8-v1";
  run_id: string;
  validation_id: string;
  run_spec: FormalRunManifestRunSpecM8V1;
  revision: FormalRunManifestRevisionV1;
  market_input: FormalRunManifestEngineInputV1;
  strategy_execution: FormalRunManifestStrategyExecutionM8V1;
  resolved_engine_input: FormalRunManifestEngineInputV1;
  checkpoint: FormalRunManifestCheckpointM8V1;
  engine_result: FormalRunManifestEngineResultM8V1;
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

export type FormalRunManifestV1 =
  | FormalRunManifestM3V1
  | FormalRunManifestM5V1
  | FormalRunManifestM8V1;

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

export interface FormalRunM5SpecReadModel {
  run_spec_id: string;
  project_id: string;
  activity_id: string;
  variant_id: string;
  candidate_revision_id: string;
  market_input_artifact_id: string;
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
  gate_policy_version: "m5-v1";
  strategy_protocol_version: "oqs-strategy-host/m5-stream-v2";
  checkpoint_batch_size: number;
  engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v1";
  spec_hash: string;
  created_at: string;
}

export type FormalRunM8SpecReadModel = Omit<
  FormalRunM5SpecReadModel,
  | "engine_version"
  | "output_schema_version"
  | "gate_policy_version"
  | "strategy_protocol_version"
  | "engine_checkpoint_abi"
> & {
  engine_version: "oqs-quant-engine/0.2.0";
  output_schema_version: 2;
  gate_policy_version: "m8-v1";
  strategy_protocol_version: "oqs-strategy-host/m8-portfolio-v1";
  engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v2";
};

export type FormalRunErrorCode =
  | "contract_gate_failed"
  | "strategy_import_failed"
  | "strategy_protocol_failed"
  | "engine_input_missing"
  | "engine_input_integrity_mismatch"
  | "checkpoint_integrity_mismatch"
  | "worker_interrupted_by_m5_upgrade"
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

export interface FormalRunM5ValidationReadModel {
  validation_id: string;
  gate_policy_version: "m5-v1";
  engine_version: "oqs-quant-engine/0.1.0";
  gates: FormalRunGates | {
    contract: "not_run";
    strategy_import: "not_run";
    smoke_run: "not_run";
  };
  outcome: "passed" | "failed" | "not_run";
  manifest_artifact_id: string | null;
  created_at: string;
}

export type FormalRunM8ValidationReadModel = Omit<
  FormalRunM5ValidationReadModel,
  "gate_policy_version" | "engine_version"
> & {
  gate_policy_version: "m8-v1";
  engine_version: "oqs-quant-engine/0.2.0";
};

export interface FormalRunActiveListEntry {
  run_id: string;
  run_spec_id: string;
  project_id: string;
  activity_id: string;
  variant_id: string;
  candidate_revision_id: string;
  status: "pending" | "running";
  engine_result_artifact_id: null;
  manifest_artifact_id: null;
  calculation_hash: null;
  error_code: null;
  queued_at: string;
  started_at: string | null;
  finished_at: null;
  execution_version: number;
  checkpoint_seq: number;
  next_bar_index: number;
  retry_of_run_id: string | null;
  validation_id: string;
  validation_outcome: "not_run";
  gates: {
    contract: "not_run";
    strategy_import: "not_run";
    smoke_run: "not_run";
  };
}

export interface FormalRunCancelledListEntry
  extends Omit<FormalRunActiveListEntry, "status" | "finished_at"> {
  status: "cancelled";
  finished_at: string;
  cancel_reason: "user_requested";
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
  | FormalRunActiveListEntry
  | FormalRunCancelledListEntry
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

export interface FormalRunActiveRecord extends FormalRunActiveListEntry {
  job_id: string;
  job_finished_at: null;
}

export interface FormalRunCancelledRecord extends FormalRunCancelledListEntry {
  job_id: string;
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
    report_json?: ArtifactMetadataReadModel;
    report_html?: ArtifactMetadataReadModel;
  };
  manifest: FormalRunManifestV1;
  engine_result: FormalEngineResultV1;
  intent_tape: FormalRunIntentV1[];
  logs: DiagnosticLog[];
}

export interface FormalRunM5SucceededDetailReadModel
  extends Omit<FormalRunSucceededDetailReadModel, "run_spec" | "validation"> {
  run_spec: FormalRunM5SpecReadModel;
  validation: FormalRunM5ValidationReadModel & {
    gates: FormalRunSucceededListEntry["gates"];
    outcome: "passed";
    manifest_artifact_id: string;
  };
  manifest: FormalRunManifestM5V1;
}

export interface FormalRunM8SucceededDetailReadModel
  extends Omit<
    FormalRunSucceededDetailReadModel,
    "run_spec" | "validation" | "manifest" | "engine_result"
  > {
  run_spec: FormalRunM8SpecReadModel;
  validation: FormalRunM8ValidationReadModel & {
    gates: FormalRunSucceededListEntry["gates"];
    outcome: "passed";
    manifest_artifact_id: string;
  };
  manifest: FormalRunManifestM8V1;
  engine_result: FormalEngineResultV2;
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

export interface FormalRunM5FailedDetailReadModel
  extends Omit<FormalRunFailedDetailReadModel, "run_spec" | "validation"> {
  run_spec: FormalRunM5SpecReadModel;
  validation: FormalRunM5ValidationReadModel & {
    gates: FormalRunGates;
    outcome: "failed";
    manifest_artifact_id: null;
  };
}

export interface FormalRunM8FailedDetailReadModel
  extends Omit<FormalRunFailedDetailReadModel, "run_spec" | "validation"> {
  run_spec: FormalRunM8SpecReadModel;
  validation: FormalRunM8ValidationReadModel & {
    gates: FormalRunGates;
    outcome: "failed";
    manifest_artifact_id: null;
  };
}

export interface FormalRunActiveDetailReadModel {
  run: FormalRunActiveRecord;
  run_spec: FormalRunM5SpecReadModel | FormalRunM8SpecReadModel;
  validation: (FormalRunM5ValidationReadModel | FormalRunM8ValidationReadModel) & {
    gates: FormalRunActiveListEntry["gates"];
    outcome: "not_run";
    manifest_artifact_id: null;
  };
  artifacts: Record<string, never>;
  manifest: null;
  engine_result: null;
  intent_tape: null;
  logs: DiagnosticLog[];
}

export interface FormalRunCancelledDetailReadModel {
  run: FormalRunCancelledRecord;
  run_spec: FormalRunM5SpecReadModel | FormalRunM8SpecReadModel;
  validation: (FormalRunM5ValidationReadModel | FormalRunM8ValidationReadModel) & {
    gates: FormalRunActiveListEntry["gates"];
    outcome: "not_run";
    manifest_artifact_id: null;
  };
  artifacts: Record<string, never>;
  manifest: null;
  engine_result: null;
  intent_tape: null;
  logs: DiagnosticLog[];
}

export type FormalRunDetailReadModel =
  | FormalRunActiveDetailReadModel
  | FormalRunCancelledDetailReadModel
  | FormalRunSucceededDetailReadModel
  | FormalRunFailedDetailReadModel
  | FormalRunM5SucceededDetailReadModel
  | FormalRunM5FailedDetailReadModel
  | FormalRunM8SucceededDetailReadModel
  | FormalRunM8FailedDetailReadModel;

export type ReportArtifactMediaType =
  | "application/vnd.open-quant-studio.run-report+json"
  | "application/vnd.open-quant-studio.run-report+html";

export interface ReportArtifactPointer {
  artifact_id: string;
  sha256: string;
  media_type: ReportArtifactMediaType;
  byte_size: number;
  storage_uri: string;
}

export interface RunReportRun {
  run_id: string;
  run_spec_id: string;
  project_id: string;
  activity_id: string;
  variant_id: string;
  candidate_revision_id: string;
  status: "succeeded";
  calculation_hash: string;
  finished_at: string;
}

export interface RunReportIdentities {
  engine_result_sha256: string;
  engine_version: string;
  engine_schema_version: number;
  account_model: string;
  data_snapshot_id: string;
  data_snapshot_sha256: string;
  strategy_tree_oid: string;
  parameters_sha256: string;
  cost_model_sha256: string;
  environment_lock_sha256: string;
  price_basis: "raw" | "qfq" | "hfq";
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
  starting_equity_atoms: FormalAtom;
  ending_equity_atoms: FormalAtom;
  net_pnl_atoms: FormalAtom;
  total_return_rate_atoms: FormalAtom;
  max_drawdown_atoms: FormalAtom;
  max_drawdown_rate_atoms: FormalAtom;
  gross_exposure_atoms: FormalAtom;
  net_exposure_atoms: FormalAtom;
  total_fees_atoms: FormalAtom;
  total_stamp_duty_atoms: FormalAtom;
  total_funding_atoms: FormalAtom;
  total_slippage_atoms: FormalAtom;
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

export interface RunReportSource {
  engine_result_artifact_id: string;
  manifest_artifact_id: string;
}

export interface RunReport {
  report_version: "m9-v1";
  run: RunReportRun;
  identities: RunReportIdentities;
  period: RunReportPeriod;
  summary: RunReportSummary;
  reconciliation: RunReportReconciliation;
  definitions: RunReportDefinition[];
  source: RunReportSource;
}

export interface RunReportReadModel {
  report: RunReport;
  json_artifact: ReportArtifactPointer & {
    media_type: "application/vnd.open-quant-studio.run-report+json";
  };
  html_artifact: ReportArtifactPointer & {
    media_type: "application/vnd.open-quant-studio.run-report+html";
  };
}

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
const validateDataSnapshotCommandSchema = validator.compile<DataSnapshotCreateCommand>(
  dataSnapshotCommandSchemaDocument,
);
const validateDataSnapshotEventSchema = validator.compile<DataSnapshotCreatedEvent>(
  dataSnapshotEventSchemaDocument,
);
const validateDataSnapshotReadModelSchema = validator.compile<
  DataImportPreviewReadModel | DataSnapshotReadModel | DataSnapshotListReadModel
>(dataSnapshotReadModelSchemaDocument);
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
const validateDiagnosticCommandSchema = validator.compile<DiagnosticCommand>(
  diagnosticCommandSchemaDocument,
);
const validateDiagnosticEventSchema = validator.compile<DiagnosticEvent>(
  diagnosticEventSchemaDocument,
);
const validateLog = validator.compile<DiagnosticLog>(diagnosticLogSchema);
const validateDiagnosticLogReadModelSchema =
  validator.compile<DiagnosticLogListReadModel>(diagnosticLogReadModelSchemaDocument);
const validateProjectArchiveManifestSchema =
  validator.compile<ProjectArchiveManifestV1>(projectArchiveManifestSchemaDocument);
const validateProjectArchiveCommandSchema =
  validator.compile<ProjectArchiveCommand>(projectArchiveCommandSchemaDocument);
const validateProjectArchiveEventSchema =
  validator.compile<ProjectArchiveEvent>(projectArchiveEventSchemaDocument);
const validateForwardTestCommandSchema =
  validator.compile<ForwardTestCommand>(forwardTestCommandSchemaDocument);
const validateForwardTestEventSchema =
  validator.compile<ForwardTestEvent>(forwardTestEventSchemaDocument);
const validateForwardTestReadModelSchema =
  validator.compile<ForwardTestReadModel>(forwardTestReadModelSchemaDocument);
const validateProjectReadModelSchema = validator.compile<
  ProjectListReadModel | ActivityListReadModel
>(projectReadModelSchemaDocument);
const validateArtifactMetadataSchema = validator.compile<ArtifactMetadataReadModel>(
  artifactReadModelSchemaDocument,
);
const validateFormalEngineResultSchema = validator.compile<FormalEngineResultV1>(
  formalEngineResultSchemaDocument,
);
const validateFormalEngineResultV2Schema = validator.compile<FormalEngineResultV2>(
  formalEngineResultV2SchemaDocument,
);
const validateFormalRunManifestSchema = validator.compile<FormalRunManifestV1>(
  formalRunManifestSchemaDocument,
);
const validateFormalRunReadModelSchema = validator.compile<
  FormalRunListReadModel | FormalRunDetailReadModel
>(formalRunReadModelSchemaDocument);
const validateRunReportReadModelSchema = validator.compile<RunReportReadModel>(
  runReportSchemaDocument,
);

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
  if (DIAGNOSTIC_COMMAND_TYPES.has(commandType)) {
    return validateDiagnosticCommand(value) as unknown as ContractValidation<CommandEnvelope>;
  }
  if (PROJECT_ARCHIVE_COMMAND_TYPES.has(commandType)) {
    return validateProjectArchiveCommand(value) as unknown as ContractValidation<CommandEnvelope>;
  }
  if (FORWARD_TEST_COMMAND_TYPES.has(commandType)) {
    return validateForwardTestCommand(value) as unknown as ContractValidation<CommandEnvelope>;
  }
  if (DATA_SNAPSHOT_COMMAND_TYPES.has(commandType)) {
    return validateDataSnapshotCommand(value) as unknown as ContractValidation<CommandEnvelope>;
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
  if (DIAGNOSTIC_EVENT_TYPES.has(eventType)) {
    return validateDiagnosticEvent(value) as unknown as ContractValidation<EventEnvelope>;
  }
  if (PROJECT_ARCHIVE_EVENT_TYPES.has(eventType)) {
    return validateProjectArchiveEvent(value) as unknown as ContractValidation<EventEnvelope>;
  }
  if (FORWARD_TEST_EVENT_TYPES.has(eventType)) {
    return validateForwardTestEvent(value) as unknown as ContractValidation<EventEnvelope>;
  }
  if (DATA_SNAPSHOT_EVENT_TYPES.has(eventType)) {
    return validateDataSnapshotEvent(value) as unknown as ContractValidation<EventEnvelope>;
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
  if (DIAGNOSTIC_COMMAND_TYPES.has(commandType)) {
    return validateDiagnosticCommand(value) as unknown as ContractValidation<CommandEnvelope>;
  }
  if (PROJECT_ARCHIVE_COMMAND_TYPES.has(commandType)) {
    return validateProjectArchiveCommand(value) as unknown as ContractValidation<CommandEnvelope>;
  }
  if (FORWARD_TEST_COMMAND_TYPES.has(commandType)) {
    return validateForwardTestCommand(value) as unknown as ContractValidation<CommandEnvelope>;
  }
  if (DATA_SNAPSHOT_COMMAND_TYPES.has(commandType)) {
    return validateDataSnapshotCommand(value) as unknown as ContractValidation<CommandEnvelope>;
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
  if (DIAGNOSTIC_EVENT_TYPES.has(eventType)) {
    return validateDiagnosticEvent(value) as unknown as ContractValidation<EventEnvelope>;
  }
  if (PROJECT_ARCHIVE_EVENT_TYPES.has(eventType)) {
    return validateProjectArchiveEvent(value) as unknown as ContractValidation<EventEnvelope>;
  }
  if (FORWARD_TEST_EVENT_TYPES.has(eventType)) {
    return validateForwardTestEvent(value) as unknown as ContractValidation<EventEnvelope>;
  }
  if (DATA_SNAPSHOT_EVENT_TYPES.has(eventType)) {
    return validateDataSnapshotEvent(value) as unknown as ContractValidation<EventEnvelope>;
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
    if (value.command_type === "workspace.revision_create") {
      const removedPaths = value.payload.removed_paths ?? [];
      if (value.expected_revision_id === null && removedPaths.length > 0) {
        errors.push("/payload/removed_paths is only valid for a child revision");
      }
      for (const [index, path] of removedPaths.entries()) {
        if (paths.has(path)) {
          errors.push(`/payload/removed_paths/${index} must not overlap /payload/files`);
        }
      }
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
  const errors: string[] = [];
  if (value.expected_revision_id !== value.base_revision_id) {
    errors.push("/expected_revision_id must match /base_revision_id");
  }
  if (value.command_type === "formal.run_request") {
    errors.push(
      ...artifactIdentityErrors(value.payload.market_input).map(
        (error) => `/payload/market_input${error}`,
      ),
    );
    if (value.payload.candidate_revision_id !== value.base_revision_id) {
      errors.push("/payload/candidate_revision_id must match /base_revision_id");
    }
  }
  if (
    value.command_type === "formal.run_retry" &&
    value.payload.source_run_id === value.payload.run_id
  ) {
    errors.push("/payload/run_id must differ from /payload/source_run_id");
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
    value.event_type === "formal.run_retried" &&
    value.payload.source_run_id === value.payload.run_id
  ) {
    errors.push("/payload/run_id must differ from /payload/source_run_id");
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

export function validateDiagnosticCommand(
  value: unknown,
): ContractValidation<DiagnosticCommand> {
  if (validateDiagnosticCommandSchema(value)) {
    return { valid: true, value };
  }
  return {
    valid: false,
    errors: validationErrors(validateDiagnosticCommandSchema.errors),
  };
}

export function validateDiagnosticEvent(
  value: unknown,
): ContractValidation<DiagnosticEvent> {
  if (validateDiagnosticEventSchema(value)) {
    return { valid: true, value };
  }
  return {
    valid: false,
    errors: validationErrors(validateDiagnosticEventSchema.errors),
  };
}

export function validateDiagnosticLogListReadModel(
  value: unknown,
): ContractValidation<DiagnosticLogListReadModel> {
  if (validateDiagnosticLogReadModelSchema(value)) {
    return { valid: true, value };
  }
  return {
    valid: false,
    errors: validationErrors(validateDiagnosticLogReadModelSchema.errors),
  };
}

function duplicateValue(values: string[]): boolean {
  return new Set(values).size !== values.length;
}

function isSorted(values: string[]): boolean {
  return values.every((value, index) => index === 0 || values[index - 1]! < value);
}

export function validateProjectArchiveManifestV1(
  value: unknown,
): ContractValidation<ProjectArchiveManifestV1> {
  if (!validateProjectArchiveManifestSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateProjectArchiveManifestSchema.errors),
    };
  }
  const errors: string[] = [];
  for (const [path, identities] of [
    ["/activity_ids", value.activity_ids],
    ["/run_spec_ids", value.run_spec_ids],
    ["/run_ids", value.run_ids],
    ["/report_artifact_ids", value.report_artifact_ids],
  ] as const) {
    if (duplicateValue(identities) || !isSorted(identities)) {
      errors.push(`${path} must contain sorted unique identities`);
    }
  }
  const refNames = value.git.refs.map((entry) => entry.name);
  if (duplicateValue(refNames) || !isSorted(refNames)) {
    errors.push("/git/refs must contain sorted unique names");
  }
  const casHashes = value.cas_objects.map((entry) => entry.sha256);
  const casPaths = value.cas_objects.map((entry) => entry.path);
  if (
    duplicateValue(casHashes) ||
    duplicateValue(casPaths) ||
    !isSorted(casPaths)
  ) {
    errors.push("/cas_objects must contain sorted unique hashes and paths");
  }
  value.cas_objects.forEach((entry, index) => {
    const expectedPath = `cas/sha256/${entry.sha256.slice(0, 2)}/${entry.sha256}`;
    if (entry.path !== expectedPath) {
      errors.push(`/cas_objects/${index}/path must match /cas_objects/${index}/sha256`);
    }
  });
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value };
}

export function validateProjectArchiveCommand(
  value: unknown,
): ContractValidation<ProjectArchiveCommand> {
  if (!validateProjectArchiveCommandSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateProjectArchiveCommandSchema.errors),
    };
  }
  const errors = artifactIdentityErrors(value.payload.archive).map(
    (error) => `/payload/archive${error}`,
  );
  if (value.payload.expected_project_id !== value.project_id) {
    errors.push("/payload/expected_project_id must match /project_id");
  }
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value };
}

export function validateProjectArchiveEvent(
  value: unknown,
): ContractValidation<ProjectArchiveEvent> {
  if (!validateProjectArchiveEventSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateProjectArchiveEventSchema.errors),
    };
  }
  return value.payload.restored_project_id === value.project_id
    ? { valid: true, value }
    : {
        valid: false,
        errors: ["/payload/restored_project_id must match /project_id"],
      };
}

export function validateForwardTestCommand(
  value: unknown,
): ContractValidation<ForwardTestCommand> {
  if (!validateForwardTestCommandSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateForwardTestCommandSchema.errors),
    };
  }
  const errors: string[] = [];
  if (value.expected_revision_id !== value.base_revision_id) {
    errors.push("/expected_revision_id must match /base_revision_id");
  }
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value };
}

export function validateForwardTestEvent(
  value: unknown,
): ContractValidation<ForwardTestEvent> {
  if (!validateForwardTestEventSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateForwardTestEventSchema.errors),
    };
  }
  return value.payload.source_revision_id === value.base_revision_id
    ? { valid: true, value }
    : {
        valid: false,
        errors: ["/payload/source_revision_id must match /base_revision_id"],
      };
}

export function validateForwardTestReadModel(
  value: unknown,
): ContractValidation<ForwardTestReadModel> {
  if (validateForwardTestReadModelSchema(value)) {
    return { valid: true, value };
  }
  return {
    valid: false,
    errors: validationErrors(validateForwardTestReadModelSchema.errors),
  };
}

export function validateDataSnapshotCommand(
  value: unknown,
): ContractValidation<DataSnapshotCreateCommand> {
  if (!validateDataSnapshotCommandSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateDataSnapshotCommandSchema.errors),
    };
  }
  const errors = artifactIdentityErrors(value.payload.source).map(
    (error) => `/payload/source${error}`,
  );
  const expectedMediaType =
    value.payload.source_format === "csv"
      ? "text/csv"
      : "application/vnd.apache.parquet";
  if (value.payload.source.media_type !== expectedMediaType) {
    errors.push("/payload/source/media_type must match /payload/source_format");
  }
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value };
}

export function validateDataSnapshotEvent(
  value: unknown,
): ContractValidation<DataSnapshotCreatedEvent> {
  if (validateDataSnapshotEventSchema(value)) {
    return { valid: true, value };
  }
  return {
    valid: false,
    errors: validationErrors(validateDataSnapshotEventSchema.errors),
  };
}

export function validateDataImportPreviewReadModel(
  value: unknown,
): ContractValidation<DataImportPreviewReadModel> {
  if (!validateDataSnapshotReadModelSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateDataSnapshotReadModelSchema.errors),
    };
  }
  if (!("source" in value)) {
    return {
      valid: false,
      errors: ["/source must be present for a data import preview"],
    };
  }
  const preview = value as DataImportPreviewReadModel;
  const errors = artifactIdentityErrors(preview.source).map(
    (error) => `/source${error}`,
  );
  const expectedMediaType =
    preview.source_format === "csv"
      ? "text/csv"
      : "application/vnd.apache.parquet";
  if (preview.source.media_type !== expectedMediaType) {
    errors.push("/source/media_type must match /source_format");
  }
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value: preview };
}

export function validateDataSnapshotReadModel(
  value: unknown,
): ContractValidation<DataSnapshotReadModel> {
  if (!validateDataSnapshotReadModelSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateDataSnapshotReadModelSchema.errors),
    };
  }
  if (!("snapshot_id" in value) || !("project_id" in value)) {
    return {
      valid: false,
      errors: ["/snapshot_id and /project_id must be present for a data snapshot"],
    };
  }
  return { valid: true, value: value as DataSnapshotReadModel };
}

export function validateDataSnapshotListReadModel(
  value: unknown,
): ContractValidation<DataSnapshotListReadModel> {
  if (!validateDataSnapshotReadModelSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateDataSnapshotReadModelSchema.errors),
    };
  }
  if (!("snapshots" in value)) {
    return {
      valid: false,
      errors: ["/snapshots must be present for a data snapshot list"],
    };
  }
  return { valid: true, value: value as DataSnapshotListReadModel };
}

function manifestSemanticErrors(value: FormalRunManifestV1): string[] {
  const errors: string[] = [];
  if (value.logs.run_id !== value.run_id) {
    errors.push("/logs/run_id must match /run_id");
  }
  if (
    value.revision.candidate_revision_id !==
    value.run_spec.candidate_revision_id
  ) {
    errors.push(
      "/revision/candidate_revision_id must match /run_spec/candidate_revision_id",
    );
  }
  const sourceInput =
    value.manifest_version === "m3-v1" ? value.engine_input : value.market_input;
  const sourceInputPath =
    value.manifest_version === "m3-v1" ? "engine_input" : "market_input";
  if (sourceInput.storage_uri !== `cas://sha256/${sourceInput.sha256}`) {
    errors.push(
      `/${sourceInputPath}/storage_uri must match /${sourceInputPath}/sha256`,
    );
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
  if (value.manifest_version !== "m3-v1") {
    if (
      value.resolved_engine_input.storage_uri !==
      `cas://sha256/${value.resolved_engine_input.sha256}`
    ) {
      errors.push(
        "/resolved_engine_input/storage_uri must match /resolved_engine_input/sha256",
      );
    }
    if (
      value.market_input.artifact_id !==
      value.run_spec.market_input_artifact_id
    ) {
      errors.push(
        "/market_input/artifact_id must match /run_spec/market_input_artifact_id",
      );
    }
    if (
      value.checkpoint.checkpoint_batch_size !==
      value.run_spec.checkpoint_batch_size
    ) {
      errors.push(
        "/checkpoint/checkpoint_batch_size must match /run_spec/checkpoint_batch_size",
      );
    }
    if (
      value.checkpoint.engine_checkpoint_abi !==
      value.run_spec.engine_checkpoint_abi
    ) {
      errors.push(
        "/checkpoint/engine_checkpoint_abi must match /run_spec/engine_checkpoint_abi",
      );
    }
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

export function validateFormalEngineResultV2(
  value: unknown,
): ContractValidation<FormalEngineResultV2> {
  if (!validateFormalEngineResultV2Schema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateFormalEngineResultV2Schema.errors),
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
  kind: "intent_tape" | "engine_result" | "manifest" | "report_json" | "report_html",
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

  if (
    run.status === "failed" ||
    run.status === "pending" ||
    run.status === "running" ||
    run.status === "cancelled"
  ) {
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
  if (manifest.manifest_version === "m3-v1") {
    if (
      manifest.engine_input.artifact_id !==
      (runSpec as FormalRunSpecReadModel).engine_input_artifact_id
    ) {
      errors.push(
        "/manifest/engine_input/artifact_id must match /run_spec/engine_input_artifact_id",
      );
    }
    if (
      manifest.engine_input.storage_uri !==
      `cas://sha256/${manifest.engine_input.sha256}`
    ) {
      errors.push(
        "/manifest/engine_input/storage_uri must match /engine_input/sha256",
      );
    }
  } else {
    const m5RunSpec = runSpec as FormalRunM5SpecReadModel;
    if (
      manifest.market_input.artifact_id !==
      m5RunSpec.market_input_artifact_id
    ) {
      errors.push(
        "/manifest/market_input/artifact_id must match /run_spec/market_input_artifact_id",
      );
    }
    if (
      manifest.run_spec.strategy_protocol_version !==
      m5RunSpec.strategy_protocol_version
    ) {
      errors.push(
        "/manifest/run_spec/strategy_protocol_version must match /run_spec/strategy_protocol_version",
      );
    }
    if (
      manifest.run_spec.checkpoint_batch_size !==
      m5RunSpec.checkpoint_batch_size
    ) {
      errors.push(
        "/manifest/run_spec/checkpoint_batch_size must match /run_spec/checkpoint_batch_size",
      );
    }
    if (
      manifest.run_spec.engine_checkpoint_abi !==
      m5RunSpec.engine_checkpoint_abi
    ) {
      errors.push(
        "/manifest/run_spec/engine_checkpoint_abi must match /run_spec/engine_checkpoint_abi",
      );
    }
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
  const reportArtifacts = [
    ["report_json", succeeded.artifacts.report_json],
    ["report_html", succeeded.artifacts.report_html],
  ] as const;
  if (
    (succeeded.artifacts.report_json === undefined)
    !== (succeeded.artifacts.report_html === undefined)
  ) {
    errors.push("/artifacts report_json and report_html must appear together");
  }
  for (const [kind, artifact] of reportArtifacts) {
    if (artifact === undefined) continue;
    const identityErrors = artifactIdentityErrors(artifact);
    errors.push(
      ...identityErrors.map((error) => `/artifacts/${kind}${error}`),
    );
    if (!hasRunKind(artifact, run.run_id, kind)) {
      errors.push(`/artifacts/${kind}/run_kinds must contain /run/run_id and kind`);
    }
    if (artifact.project_id !== run.project_id) {
      errors.push(`/artifacts/${kind}/project_id must match /run/project_id`);
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

function runReportSemanticErrors(value: RunReportReadModel): string[] {
  const errors: string[] = [];
  if (
    value.report.run.calculation_hash
    !== value.report.identities.engine_result_sha256
  ) {
    errors.push(
      "/report/identities/engine_result_sha256 must match /report/run/calculation_hash",
    );
  }
  for (const [path, artifact] of [
    ["/json_artifact", value.json_artifact],
    ["/html_artifact", value.html_artifact],
  ] as const) {
    if (artifact.storage_uri !== `cas://sha256/${artifact.sha256}`) {
      errors.push(`${path}/storage_uri must match ${path}/sha256`);
    }
  }

  const expectedDefinitionFields = new Set<string>([
    "start_at",
    "end_at",
    "session_count",
    ...Object.keys(value.report.summary),
  ]);
  const definitionFields = value.report.definitions.map((definition) => definition.field);
  if (
    new Set(definitionFields).size !== definitionFields.length ||
    definitionFields.length !== expectedDefinitionFields.size ||
    definitionFields.some((field) => !expectedDefinitionFields.has(field))
  ) {
    errors.push(
      "/report/definitions/field set must exactly cover period and summary fields without duplicates",
    );
  }

  const checksPassed = value.report.reconciliation.checks.every(
    (check) => check.passed,
  );
  if (value.report.reconciliation.passed !== checksPassed) {
    errors.push(
      "/report/reconciliation/passed must equal every /report/reconciliation/checks/passed",
    );
  }
  return errors;
}

export function validateRunReportReadModel(
  value: unknown,
): ContractValidation<RunReportReadModel> {
  if (!validateRunReportReadModelSchema(value)) {
    return {
      valid: false,
      errors: validationErrors(validateRunReportReadModelSchema.errors),
    };
  }
  const report = value as RunReportReadModel;
  const errors = runReportSemanticErrors(report);
  return errors.length > 0 ? { valid: false, errors } : { valid: true, value: report };
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
  if (DIAGNOSTIC_EVENT_TYPES.has(envelope.value.event_type)) {
    return validateDiagnosticEvent(value);
  }
  if (PROJECT_ARCHIVE_EVENT_TYPES.has(envelope.value.event_type)) {
    return validateProjectArchiveEvent(value);
  }
  if (FORWARD_TEST_EVENT_TYPES.has(envelope.value.event_type)) {
    return validateForwardTestEvent(value);
  }
  if (DATA_SNAPSHOT_EVENT_TYPES.has(envelope.value.event_type)) {
    return validateDataSnapshotEvent(value);
  }
  return {
    valid: false,
    errors: [`unsupported domain event type ${envelope.value.event_type}`],
  };
}
