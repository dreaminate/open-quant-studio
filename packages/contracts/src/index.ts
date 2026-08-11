import { Ajv2020, type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import artifactVerificationEventSchemaDocument from "../schemas/v1/artifact-verification-event.schema.json" with { type: "json" };
import artifactRefSchemaDocument from "../schemas/v1/artifact-ref.schema.json" with { type: "json" };
import commandEnvelopeSchemaDocument from "../schemas/v1/command-envelope.schema.json" with { type: "json" };
import contextCaptureCommandSchemaDocument from "../schemas/v1/context-capture-command.schema.json" with { type: "json" };
import contextCapturedEventSchemaDocument from "../schemas/v1/context-captured-event.schema.json" with { type: "json" };
import diagnosticLogSchemaDocument from "../schemas/v1/diagnostic-log.schema.json" with { type: "json" };
import eventEnvelopeSchemaDocument from "../schemas/v1/event-envelope.schema.json" with { type: "json" };

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

export type DomainEvent = ContextCapturedEvent | ArtifactVerificationEvent;

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
  if (validateCommand(value)) {
    return { valid: true, value };
  }

  return { valid: false, errors: validationErrors(validateCommand.errors) };
}

export function validateEventEnvelope(
  value: unknown,
): ContractValidation<EventEnvelope> {
  if (validateEvent(value)) {
    return { valid: true, value };
  }

  return { valid: false, errors: validationErrors(validateEvent.errors) };
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
  return {
    valid: false,
    errors: [`unsupported domain event type ${envelope.value.event_type}`],
  };
}
