import { Ajv2020, type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import artifactVerificationEventSchemaDocument from "../schemas/v1/artifact-verification-event.schema.json" with { type: "json" };
import artifactRefSchemaDocument from "../schemas/v1/artifact-ref.schema.json" with { type: "json" };
import commandEnvelopeSchemaDocument from "../schemas/v1/command-envelope.schema.json" with { type: "json" };
import contextCaptureCommandSchemaDocument from "../schemas/v1/context-capture-command.schema.json" with { type: "json" };
import contextCapturedEventSchemaDocument from "../schemas/v1/context-captured-event.schema.json" with { type: "json" };
import diagnosticLogSchemaDocument from "../schemas/v1/diagnostic-log.schema.json" with { type: "json" };
import eventEnvelopeSchemaDocument from "../schemas/v1/event-envelope.schema.json" with { type: "json" };
import formalRunCommandSchemaDocument from "../schemas/v1/formal-run-command.schema.json" with { type: "json" };
import formalRunEventSchemaDocument from "../schemas/v1/formal-run-event.schema.json" with { type: "json" };
import revisionCommandSchemaDocument from "../schemas/v1/revision-command.schema.json" with { type: "json" };
import revisionEventSchemaDocument from "../schemas/v1/revision-event.schema.json" with { type: "json" };
import sessionCommandSchemaDocument from "../schemas/v1/session-command.schema.json" with { type: "json" };
import sessionEventSchemaDocument from "../schemas/v1/session-event.schema.json" with { type: "json" };

export const artifactRefSchema: Record<string, unknown> = artifactRefSchemaDocument;
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
export const formalRunCommandSchema: Record<string, unknown> =
  formalRunCommandSchemaDocument;
export const formalRunEventSchema: Record<string, unknown> =
  formalRunEventSchemaDocument;
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

function validationErrors(errors: ErrorObject[] | null | undefined): string[] {
  return (errors ?? []).map(
    ({ instancePath, message }) => `${instancePath || "/"} ${message}`,
  );
}

function artifactIdentityErrors(artifact: ArtifactRef): string[] {
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
