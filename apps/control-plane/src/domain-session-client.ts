import { createHash, randomUUID } from "node:crypto";

import {
  type CommandEnvelope,
  type M2ArtifactRef,
  type SessionCommand,
  type SessionMessagePayload,
  type SessionReceiptPayload,
  type SessionSourceRef,
  validateTypedCommandEnvelope,
  validateTypedEventEnvelope,
} from "@open-quant-studio/contracts";
export type { SessionSourceRef } from "@open-quant-studio/contracts";

const MAX_MESSAGE_BYTES = 64 * 1024;
const MAX_SOURCE_ENTRY_BYTES = 256 * 1024;
const MAX_ERROR_BODY_BYTES = 1024;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ERROR_CODE_PATTERN = /^[a-z][a-z0-9_.-]{0,63}$/;

type FetchImplementation = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export interface QuantDomainHttpErrorInfo {
  status: number;
  code: string | null;
}

/** HTTP failures intentionally carry only a bounded server error code. */
export class QuantDomainHttpError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(info: QuantDomainHttpErrorInfo) {
    super(
      `quant-domain request returned HTTP ${info.status}${
        info.code === null ? "" : ` (${info.code})`
      }`,
    );
    this.name = "QuantDomainHttpError";
    this.status = info.status;
    this.code = info.code;
  }
}

export interface ArtifactBlobReceipt {
  sha256: string;
  byte_size: number;
  storage_uri: string;
}

export interface DurableSession {
  session_id: string;
  project_id: string;
  activity_id: string;
  pi_session_id: string;
  session_uri: string;
  created_at: string;
  workbench_ids: string[];
  active_workbench_id: string;
}

export interface InboxMessage {
  inbox_seq: number;
  message_id: string;
  project_id: string;
  activity_id: string;
  sender_session_id: string;
  recipient_session_id: string;
  correlation_id: string;
  message_kind: "send" | "ask" | "reply";
  artifact_id: string;
  artifact_sha256: string;
  reply_to: string | null;
  source_refs: SessionSourceRef[];
  created_at: string;
  state: "queued" | "receiver_received" | "injected" | "acknowledged";
  receipt_version: number;
}

export interface DurableMessage extends InboxMessage {
  body: string;
}

export interface CommandReceipt {
  command_id: string;
  disposition: "accepted" | "replayed";
  event: unknown;
}

export interface SessionCommandContext {
  projectId: string;
  activityId: string;
  sessionId: string;
  workbenchId: string;
  correlationId?: string;
  commandId?: string;
}

export interface RegisterSessionRequest extends SessionCommandContext {
  piSessionId: string;
  sessionUri?: string;
}

export type BindWorkbenchRequest = SessionCommandContext;

export interface SendMessageRequest extends SessionCommandContext {
  recipientSessionId: string;
  messageKind: "send" | "ask" | "reply";
  body: string;
  sourceRefs?: SessionSourceRef[];
  replyTo?: string | null;
  messageId?: string;
}

export interface ReceiptTransitionRequest extends SessionCommandContext {
  messageId: string;
  expectedState: "queued" | "receiver_received" | "injected";
  expectedVersion: number;
  commandType:
    | "session.message_receive"
    | "session.message_mark_injected"
    | "session.message_acknowledge";
}

export interface InboxRequest {
  projectId: string;
  sessionId: string;
  after?: number;
  limit?: number;
}

export interface MessageRequest {
  projectId: string;
  recipientSessionId: string;
  messageId: string;
}

export interface QuantDomainSessionClient {
  readonly baseUrl: string;
  stageText(body: string): Promise<ArtifactBlobReceipt>;
  stageSourceEntry(canonicalEntry: string): Promise<ArtifactBlobReceipt>;
  postCommand(command: unknown): Promise<CommandReceipt>;
  registerSession(request: RegisterSessionRequest): Promise<CommandReceipt>;
  bindWorkbench(request: BindWorkbenchRequest): Promise<CommandReceipt>;
  sendMessage(request: SendMessageRequest): Promise<CommandReceipt>;
  listSessions(projectId: string): Promise<DurableSession[]>;
  inbox(request: InboxRequest): Promise<InboxMessage[]>;
  getMessage(request: MessageRequest): Promise<DurableMessage>;
  transitionReceipt(request: ReceiptTransitionRequest): Promise<CommandReceipt>;
}

export class FetchQuantDomainSessionClient implements QuantDomainSessionClient {
  readonly #baseUrl: string;
  readonly #fetch: FetchImplementation;

  constructor(
    baseUrl: string,
    fetchImplementation: FetchImplementation = fetch,
  ) {
    this.#baseUrl = baseUrl.replace(/\/$/, "");
    this.#fetch = fetchImplementation;
  }

  get baseUrl(): string {
    return this.#baseUrl;
  }

  async stageText(body: string): Promise<ArtifactBlobReceipt> {
    const bytes = new TextEncoder().encode(body);
    assertBoundedText(bytes);
    return this.#stageBytes(bytes);
  }

  async stageSourceEntry(canonicalEntry: string): Promise<ArtifactBlobReceipt> {
    const bytes = new TextEncoder().encode(canonicalEntry);
    if (bytes.byteLength > MAX_SOURCE_ENTRY_BYTES) {
      throw new Error("Pi source entry must be no larger than 262144 bytes");
    }
    return this.#stageBytes(bytes);
  }

  async #stageBytes(bytes: Uint8Array<ArrayBuffer>): Promise<ArtifactBlobReceipt> {
    const sha256 = createHash("sha256").update(bytes).digest("hex");
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/artifact-blobs/${sha256}`,
      {
        method: "PUT",
        headers: { "Content-Type": "text/plain; charset=utf-8" },
        body: bytes,
      },
    );
    const receipt = await this.#jsonResponse<ArtifactBlobReceipt>(response);
    if (
      receipt.sha256 !== sha256 ||
      receipt.byte_size !== bytes.byteLength ||
      receipt.storage_uri !== `cas://sha256/${sha256}`
    ) {
      throw new Error("artifact blob response did not preserve content identity");
    }
    return receipt;
  }

  async postCommand(command: unknown): Promise<CommandReceipt> {
    const validation = validateTypedCommandEnvelope(command);
    if (!validation.valid) {
      throw new Error(`command contract violation: ${validation.errors.join("; ")}`);
    }
    const response = await this.#fetch(`${this.#baseUrl}/v1/commands`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(command),
    });
    const payload = await this.#jsonResponse<unknown>(response);
    const receipt = assertCommandReceipt(payload);
    assertReceiptBinding(receipt, validation.value);
    return receipt;
  }

  async registerSession(request: RegisterSessionRequest): Promise<CommandReceipt> {
    const piSessionId = request.piSessionId;
    if (!/^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$/.test(piSessionId)) {
      throw new Error("piSessionId is not a valid Pi identity");
    }
    const command = {
      ...envelope(request, "session.register"),
      command_type: "session.register",
      payload: {
        pi_session_id: piSessionId,
        session_uri: request.sessionUri ?? `pi-jsonl://session/${piSessionId}`,
      },
    } as unknown as SessionCommand;
    return this.postCommand(command);
  }

  async bindWorkbench(request: BindWorkbenchRequest): Promise<CommandReceipt> {
    const command = {
      ...envelope(request, "session.workbench_bind"),
      command_type: "session.workbench_bind",
      payload: { workbench_id: request.workbenchId },
    } as unknown as SessionCommand;
    return this.postCommand(command);
  }

  async sendMessage(request: SendMessageRequest): Promise<CommandReceipt> {
    const commandId = request.commandId ?? randomUUID();
    assertUuid(commandId, "commandId");
    const messageId = request.messageId ?? stableIdentityUuid(`${commandId}:message`);
    assertUuid(messageId, "messageId");
    const messageArtifact = canonicalTextArtifactRef(request.body);
    const { sha256 } = messageArtifact;
    const payload: SessionMessagePayload = {
      message_id: messageId,
      recipient_session_id: request.recipientSessionId,
      message_kind: request.messageKind,
      reply_to: request.replyTo ?? null,
      source_refs: request.sourceRefs ?? [],
      artifact: messageArtifact,
    };
    const commandType =
      request.messageKind === "reply"
        ? "session.message_reply"
        : "session.message_send";
    const command = {
      ...envelope({ ...request, commandId }, commandType),
      command_type: commandType,
      payload,
    } as SessionCommand;
    const validation = validateTypedCommandEnvelope(command);
    if (!validation.valid) {
      throw new Error(`command contract violation: ${validation.errors.join("; ")}`);
    }
    const staged = await this.stageText(request.body);
    if (
      staged.sha256 !== sha256 ||
      staged.byte_size !== messageArtifact.byte_size
    ) {
      throw new Error("staged message body identity changed before command submission");
    }
    return this.postCommand(command);
  }

  async listSessions(projectId: string): Promise<DurableSession[]> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/sessions?project_id=${encodeURIComponent(projectId)}`,
      { headers: { Accept: "application/json" } },
    );
    const payload = await this.#jsonResponse<{ sessions: unknown }>(response);
    if (!Array.isArray(payload.sessions)) {
      throw new Error("quant-domain sessions response has an invalid shape");
    }
    return payload.sessions.map((session) => {
      const durable = assertDurableSession(session);
      if (durable.project_id !== projectId) {
        throw new Error("quant-domain session response crossed project identity");
      }
      return durable;
    });
  }

  async inbox(request: InboxRequest): Promise<InboxMessage[]> {
    const after = request.after ?? 0;
    const limit = request.limit ?? 100;
    if (!Number.isInteger(after) || after < 0) {
      throw new Error("inbox after must be a non-negative integer");
    }
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
      throw new Error("inbox limit must be an integer between 1 and 100");
    }
    const query = new URLSearchParams({
      project_id: request.projectId,
      session_id: request.sessionId,
      after: String(after),
      limit: String(limit),
    });
    const response = await this.#fetch(`${this.#baseUrl}/v1/inbox?${query}`, {
      headers: { Accept: "application/json" },
    });
    const payload = await this.#jsonResponse<{ messages: unknown }>(response);
    if (!Array.isArray(payload.messages)) {
      throw new Error("quant-domain inbox response has an invalid shape");
    }
    return payload.messages.map((message) => {
      const inboxMessage = assertInboxMessage(message);
      if (
        inboxMessage.project_id !== request.projectId ||
        inboxMessage.recipient_session_id !== request.sessionId ||
        inboxMessage.inbox_seq <= after
      ) {
        throw new Error("quant-domain inbox response crossed request identity or cursor");
      }
      return inboxMessage;
    });
  }

  async getMessage(request: MessageRequest): Promise<DurableMessage> {
    const query = new URLSearchParams({
      project_id: request.projectId,
      recipient_session_id: request.recipientSessionId,
    });
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/messages/${encodeURIComponent(request.messageId)}?${query}`,
      { headers: { Accept: "application/json" },
      },
    );
    const payload = await this.#jsonResponse<unknown>(response);
    const message = assertDurableMessage(payload);
    if (
      message.message_id !== request.messageId ||
      message.project_id !== request.projectId ||
      message.recipient_session_id !== request.recipientSessionId
    ) {
      throw new Error("quant-domain message response crossed request identity");
    }
    return message;
  }

  async transitionReceipt(request: ReceiptTransitionRequest): Promise<CommandReceipt> {
    const payload: SessionReceiptPayload = {
      message_id: request.messageId,
      expected_state: request.expectedState,
      expected_version: asReceiptVersion(request.expectedVersion),
    };
    const command = {
      ...envelope(request, request.commandType),
      command_type: request.commandType,
      payload,
    } as SessionCommand;
    return this.postCommand(command);
  }

  async #jsonResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      throw new QuantDomainHttpError({
        status: response.status,
        code: await boundedResponseCode(response),
      });
    }
    return (await response.json()) as T;
  }
}

export function canonicalTextArtifactRef(body: string): M2ArtifactRef {
  const bytes = new TextEncoder().encode(body);
  assertBoundedText(bytes);
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  return {
    artifact_id: stableIdentityUuid(`${sha256}:message-artifact`),
    sha256,
    media_type: "text/plain",
    byte_size: bytes.byteLength,
    storage_uri: `cas://sha256/${sha256}`,
    producing_revision_id: null,
    producing_run_id: null,
    provenance: {
      origin_kind: "service_generated",
      source_ref: stableIdentityUuid(`${sha256}:message-provenance`),
    },
  };
}

function envelope(
  request: SessionCommandContext,
  commandType: string,
): CommandEnvelope {
  const commandId = request.commandId ?? randomUUID();
  const correlationId = request.correlationId ?? randomUUID();
  assertUuid(commandId, "commandId");
  assertUuid(correlationId, "correlationId");
  return {
    command_id: commandId,
    schema_version: 1,
    command_type: commandType,
    project_id: request.projectId,
    activity_id: request.activityId,
    session_id: request.sessionId,
    workbench_id: request.workbenchId,
    correlation_id: correlationId,
    expected_revision_id: null,
    variant_id: null,
    base_revision_id: null,
    payload: {},
  };
}

function assertUuid(value: string, name: string): void {
  if (!UUID_PATTERN.test(value)) {
    throw new Error(`${name} must be a UUID`);
  }
}

function assertBoundedText(bytes: Uint8Array): void {
  if (bytes.byteLength > MAX_MESSAGE_BYTES) {
    throw new Error("message body must be UTF-8 text no larger than 65536 bytes");
  }
}

export function stableIdentityUuid(seed: string): string {
  const bytes = createHash("sha256").update(seed).digest();
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = bytes.toString("hex").slice(0, 32);
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function asReceiptVersion(value: number): 0 | 1 | 2 {
  if (!Number.isInteger(value) || value < 0 || value > 2) {
    throw new Error("message receipt version must be an integer between 0 and 2");
  }
  return value as 0 | 1 | 2;
}

function assertCommandReceipt(value: unknown): CommandReceipt {
  const record = value as Record<string, unknown>;
  if (
    value === null ||
    typeof value !== "object" ||
    typeof record.command_id !== "string" ||
    !UUID_PATTERN.test(record.command_id) ||
    (record.disposition !== "accepted" && record.disposition !== "replayed")
  ) {
    throw new Error("quant-domain command response has an invalid shape");
  }
  if (record.event === undefined) {
    throw new Error("quant-domain command response omitted its durable event");
  }
  const validation = validateTypedEventEnvelope(record.event);
  if (!validation.valid) {
    throw new Error(`quant-domain command response event is invalid: ${validation.errors.join("; ")}`);
  }
  return value as CommandReceipt;
}

function assertReceiptBinding(
  receipt: CommandReceipt,
  command: CommandEnvelope,
): void {
  const event = receipt.event as Record<string, unknown>;
  const eventTypeByCommand: Record<string, string> = {
    "session.register": "session.registered",
    "session.workbench_bind": "session.workbench_bound",
    "session.message_send": "session.message_queued",
    "session.message_reply": "session.message_queued",
    "session.message_receive": "session.message_receiver_received",
    "session.message_mark_injected": "session.message_injected",
    "session.message_acknowledge": "session.message_acknowledged",
    "workspace.revision_create": "workspace.revision_created",
    "strategy.variant_create": "strategy.variant_created",
    "workspace.revision_promote": "workspace.revision_promoted",
  };
  if (
    receipt.command_id !== command.command_id ||
    event.event_type !== eventTypeByCommand[command.command_type] ||
    event.causation_id !== command.command_id ||
    event.project_id !== command.project_id ||
    event.activity_id !== command.activity_id ||
    event.session_id !== command.session_id ||
    event.workbench_id !== command.workbench_id ||
    event.correlation_id !== command.correlation_id ||
    (command.command_type.startsWith("workspace.revision") ||
      command.command_type === "strategy.variant_create") &&
      (event.variant_id !== command.variant_id ||
        event.base_revision_id !== command.base_revision_id)
  ) {
    throw new Error("quant-domain command response event did not preserve command identity");
  }
  const payload = event.payload as Record<string, unknown>;
  const commandPayload = command.payload as Record<string, unknown>;
  if (
    command.command_type === "workspace.revision_create" &&
    payload.revision_id !== commandPayload.revision_id
  ) {
    throw new Error("quant-domain command response event did not preserve revision identity");
  }
  if (
    command.command_type === "strategy.variant_create" &&
    payload.revision_id !== command.base_revision_id
  ) {
    throw new Error("quant-domain command response event did not preserve revision identity");
  }
  if (
    command.command_type === "workspace.revision_promote" &&
    payload.promoted_revision_id !== commandPayload.candidate_revision_id
  ) {
    throw new Error("quant-domain command response event did not preserve revision identity");
  }
  if (
    command.command_type.startsWith("session.") &&
    command.command_type !== "session.register" &&
    payload.message_id !== commandPayload.message_id
  ) {
    throw new Error("quant-domain command response event did not preserve message identity");
  }
}

function assertDurableSession(value: unknown): DurableSession {
  const record = value as Record<string, unknown>;
  if (
    value === null ||
    typeof value !== "object" ||
    typeof record.session_id !== "string" ||
    typeof record.project_id !== "string" ||
    typeof record.activity_id !== "string" ||
    typeof record.pi_session_id !== "string" ||
    typeof record.session_uri !== "string" ||
    typeof record.created_at !== "string" ||
    !Array.isArray(record.workbench_ids) ||
    record.workbench_ids.some((workbench) => typeof workbench !== "string") ||
    typeof record.active_workbench_id !== "string" ||
    !record.workbench_ids.includes(record.active_workbench_id)
  ) {
    throw new Error("quant-domain session response has an invalid shape");
  }
  return value as DurableSession;
}

function assertInboxMessage(value: unknown): InboxMessage {
  const record = value as Record<string, unknown>;
  if (
    value === null ||
    typeof value !== "object" ||
    typeof record.inbox_seq !== "number" ||
    !Number.isInteger(record.inbox_seq) ||
    typeof record.message_id !== "string" ||
    !UUID_PATTERN.test(record.message_id) ||
    typeof record.project_id !== "string" ||
    typeof record.activity_id !== "string" ||
    typeof record.sender_session_id !== "string" ||
    typeof record.recipient_session_id !== "string" ||
    typeof record.correlation_id !== "string" ||
    !UUID_PATTERN.test(record.correlation_id) ||
    !["send", "ask", "reply"].includes(record.message_kind as string) ||
    typeof record.artifact_id !== "string" ||
    !UUID_PATTERN.test(record.artifact_id) ||
    typeof record.artifact_sha256 !== "string" ||
    !/^[a-f0-9]{64}$/.test(record.artifact_sha256) ||
    (record.reply_to !== null && (typeof record.reply_to !== "string" || !UUID_PATTERN.test(record.reply_to))) ||
    !Array.isArray(record.source_refs) ||
    record.source_refs.some((source) => !isSourceRef(source)) ||
    typeof record.created_at !== "string" ||
    !["queued", "receiver_received", "injected", "acknowledged"].includes(record.state as string) ||
    typeof record.receipt_version !== "number" ||
    !Number.isInteger(record.receipt_version) ||
    !receiptStateVersionMatches(record.state, record.receipt_version)
  ) {
    throw new Error("quant-domain inbox message response has an invalid shape");
  }
  return value as InboxMessage;
}

function isSourceRef(value: unknown): value is SessionSourceRef {
  const source = value as Record<string, unknown>;
  return (
    value !== null &&
    typeof value === "object" &&
    typeof source.session_id === "string" &&
    typeof source.entry_id === "string" &&
    typeof source.leaf_id === "string" &&
    typeof source.sha256 === "string" &&
    /^[a-f0-9]{64}$/.test(source.sha256) &&
    typeof source.source_uri === "string" &&
    /^pi-jsonl:\/\/session\/[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?#entry=[A-Za-z0-9](?:[A-Za-z0-9._:-]{0,126}[A-Za-z0-9])?$/.test(source.source_uri)
  );
}

function assertDurableMessage(value: unknown): DurableMessage {
  const message = assertInboxMessage(value);
  const record = value as Record<string, unknown>;
  if (typeof record.body !== "string") {
    throw new Error("quant-domain message response has no bounded text body");
  }
  const bytes = new TextEncoder().encode(record.body);
  assertBoundedText(bytes);
  if (createHash("sha256").update(bytes).digest("hex") !== message.artifact_sha256) {
    throw new Error("quant-domain message body failed content identity verification");
  }
  return value as DurableMessage;
}

function receiptStateVersionMatches(state: unknown, version: unknown): boolean {
  return (
    (state === "queued" && version === 0) ||
    (state === "receiver_received" && version === 1) ||
    (state === "injected" && version === 2) ||
    (state === "acknowledged" && version === 3)
  );
}

export async function boundedResponseCode(response: Response): Promise<string | null> {
  if (response.body === null) {
    return null;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let byteLength = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      if (byteLength + value.byteLength > MAX_ERROR_BODY_BYTES) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
      byteLength += value.byteLength;
    }
    const body = new Uint8Array(byteLength);
    let offset = 0;
    for (const chunk of chunks) {
      body.set(chunk, offset);
      offset += chunk.byteLength;
    }
    const text = new TextDecoder("utf-8", { fatal: true }).decode(body);
    if (text === "") {
      return null;
    }
    const parsed: unknown = JSON.parse(text);
    if (
      parsed !== null &&
      typeof parsed === "object" &&
      "error" in parsed &&
      typeof parsed.error === "string" &&
      ERROR_CODE_PATTERN.test(parsed.error)
    ) {
      return parsed.error;
    }
  } catch {
    return null;
  }
  return null;
}
