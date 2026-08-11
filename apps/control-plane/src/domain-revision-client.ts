import { createHash, randomUUID } from "node:crypto";

import {
  type ArtifactRef,
  type FormalRunCommand,
  type M3ArtifactRef,
  type RevisionCommand,
  type RevisionCreatePayload,
  type StrategyVariantCreateCommand,
  type WorkspaceMergeCreateCommand,
  type WorkspaceRevisionCreateChildCommand,
  type WorkspaceRevisionCreateCommand,
  type WorkspaceRevisionCreateRootCommand,
  type WorkspaceRevisionPromoteCommand,
  validateFormalRunCommand,
  validateStrategyVariantCreateCommand,
  validateWorkspaceMergeCreateCommand,
  validateWorkspaceRevisionCreateCommand,
  validateWorkspaceRevisionPromoteCommand,
} from "@open-quant-studio/contracts";

import {
  QuantDomainHttpError,
  boundedResponseCode,
  canonicalTextArtifactRef,
  stableIdentityUuid,
  type ArtifactBlobReceipt,
  type CommandReceipt,
  type QuantDomainSessionClient,
  type SessionCommandContext,
} from "./domain-session-client.js";

const MAX_TEXT_BYTES = 64 * 1024;
const MAX_FILES = 32;
const MAX_VARIANTS = 64;
const MAX_CHANGES = 64;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256_PATTERN = /^[a-f0-9]{64}$/;
const GIT_OID_PATTERN = /^[a-f0-9]{40}$/;

export type RevisionFetchImplementation = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export type RevisionSessionClient = Pick<
  QuantDomainSessionClient,
  "baseUrl" | "stageJson" | "stageText" | "postCommand"
>;

export interface RevisionClientOptions {
  sessionClient: RevisionSessionClient;
  fetchImplementation?: RevisionFetchImplementation;
}

export type RevisionCommandContext = SessionCommandContext;

export interface RevisionFileInput {
  path: string;
  body: string;
}

export interface RevisionCreateRequest extends RevisionCommandContext {
  message: string;
  files: RevisionFileInput[];
  revisionId?: string;
  variantId?: string;
  baseRevisionId?: string;
  expectedRevisionId?: string;
}

export interface VariantCreateRequest extends RevisionCommandContext {
  baseRevisionId: string;
  variantId?: string;
}

export interface RevisionPromoteRequest extends RevisionCommandContext {
  expectedRevisionId: string;
  variantId: string;
  candidateRevisionId: string;
  validationId: string;
  baseRevisionId?: string;
}

export interface MergeCreateRequest extends RevisionCommandContext {
  expectedRevisionId: string;
  variantId: string;
  baseRevisionId: string;
  message: string;
  files: RevisionFileInput[];
  candidateRevisionId?: string;
}

export interface FormalRunRequest extends RevisionCommandContext {
  candidateRevisionId: string;
  variantId: string;
  engineInputJson: string;
  dataSnapshotId: string;
  dataSnapshotSha256: string;
  strategyTreeOid: string;
  parametersSha256: string;
  costModelSha256: string;
  environmentLockSha256: string;
  priceBasis: "raw" | "qfq" | "hfq";
  cutoff: string;
  timezone: string;
  sampleStart: string;
  sampleEnd: string;
  randomSeed: number;
  runSpecId?: string;
  runId?: string;
  validationId?: string;
}

export interface RevisionDetail {
  revision_id: string;
  project_id: string;
  activity_id: string;
  variant_id: string | null;
  base_revision_id: string | null;
  git_commit_oid: string;
  git_tree_oid: string;
  message: string;
  created_by_session_id: string;
  created_at: string;
  files: RevisionDetailFile[];
}

export interface RevisionDetailFile {
  path: string;
  artifact_id: string;
  git_blob_oid: string;
  sha256: string;
  byte_size: number;
  media_type: "text/plain";
  storage_uri: string;
}

export interface StrategyVariantSummary {
  variant_id: string;
  project_id: string;
  activity_id: string;
  base_revision_id: string;
  created_by_session_id: string;
  created_at: string;
  head_revision_id: string;
  version: number;
  updated_at: string;
}

export interface RevisionComparison {
  project_id: string;
  left_revision_id: string;
  right_revision_id: string;
  changes: RevisionComparisonChange[];
}

export interface RevisionComparisonChange {
  path: string;
  left_artifact_id: string | null;
  left_sha256: string | null;
  right_artifact_id: string | null;
  right_sha256: string | null;
}

export interface ProjectRevisionHead {
  project_id: string;
  head_revision_id: string;
}

interface PreparedRevisionFile {
  path: string;
  body: string;
  artifact: M3ArtifactRef;
}

interface PreparedRevision {
  command: WorkspaceRevisionCreateCommand;
  files: PreparedRevisionFile[];
}

interface PreparedMerge {
  command: WorkspaceMergeCreateCommand;
  files: PreparedRevisionFile[];
}

interface PreparedFormalRun {
  command: FormalRunCommand;
  engineInput: ArtifactRef;
}

/**
 * Typed TypeScript boundary for the M3 revision graph. Durable writes still
 * go through the injected M2 QuantDomainSessionClient; this class has no Pi
 * loop or durable state of its own.
 */
export class FetchQuantDomainRevisionClient {
  readonly #sessionClient: RevisionSessionClient;
  readonly #baseUrl: string;
  readonly #fetch: RevisionFetchImplementation;

  constructor(
    sessionClient: RevisionSessionClient,
    fetchImplementation?: RevisionFetchImplementation,
  );
  constructor(options: RevisionClientOptions);
  constructor(
    sessionClientOrOptions: RevisionSessionClient | RevisionClientOptions,
    fetchImplementation: RevisionFetchImplementation = fetch,
  ) {
    const sessionClient = "sessionClient" in sessionClientOrOptions
      ? sessionClientOrOptions.sessionClient
      : sessionClientOrOptions;
    this.#sessionClient = sessionClient;
    this.#baseUrl = sessionClient.baseUrl.replace(/\/$/, "");
    this.#fetch = "sessionClient" in sessionClientOrOptions
      ? sessionClientOrOptions.fetchImplementation ?? fetchImplementation
      : fetchImplementation;
  }

  get baseUrl(): string {
    return this.#baseUrl;
  }

  buildRevisionCreateRootCommand(
    request: RevisionCreateRequest,
  ): WorkspaceRevisionCreateRootCommand {
    return this.#prepareRevision(request, {
      expectedRevisionId: null,
      variantId: null,
      baseRevisionId: null,
    }).command as WorkspaceRevisionCreateRootCommand;
  }

  buildRevisionCreateChildCommand(
    request: RevisionCreateRequest,
  ): WorkspaceRevisionCreateChildCommand {
    const baseRevisionId = request.baseRevisionId;
    const variantId = request.variantId;
    if (baseRevisionId === undefined || variantId === undefined) {
      throw new Error("child revision requires baseRevisionId and variantId");
    }
    return this.#prepareRevision(request, {
      expectedRevisionId: request.expectedRevisionId ?? baseRevisionId,
      variantId,
      baseRevisionId,
    }).command as WorkspaceRevisionCreateChildCommand;
  }

  buildStrategyVariantCreateCommand(
    request: VariantCreateRequest,
  ): StrategyVariantCreateCommand {
    const commandId = this.#commandId(request.commandId);
    const correlationId = this.#correlationId(request.correlationId, commandId);
    const variantId = request.variantId ?? stableIdentityUuid(`${commandId}:variant`);
    const command: StrategyVariantCreateCommand = {
      command_id: commandId,
      schema_version: 1,
      command_type: "strategy.variant_create",
      project_id: request.projectId,
      activity_id: request.activityId,
      session_id: request.sessionId,
      workbench_id: request.workbenchId,
      correlation_id: correlationId,
      expected_revision_id: null,
      variant_id: variantId,
      base_revision_id: request.baseRevisionId,
      payload: {
        variant_id: variantId,
        base_revision_id: request.baseRevisionId,
      },
    };
    return assertValidCommand(
      validateStrategyVariantCreateCommand(command),
      "strategy.variant_create",
    );
  }

  buildMergeCreateCommand(request: MergeCreateRequest): WorkspaceMergeCreateCommand {
    return this.#prepareMerge(request).command;
  }

  buildFormalRunCommand(request: FormalRunRequest): FormalRunCommand {
    return this.#prepareFormalRun(request).command;
  }

  buildRevisionPromoteCommand(
    request: RevisionPromoteRequest,
  ): WorkspaceRevisionPromoteCommand {
    const commandId = this.#commandId(request.commandId);
    const correlationId = this.#correlationId(request.correlationId, commandId);
    const command: WorkspaceRevisionPromoteCommand = {
      command_id: commandId,
      schema_version: 1,
      command_type: "workspace.revision_promote",
      project_id: request.projectId,
      activity_id: request.activityId,
      session_id: request.sessionId,
      workbench_id: request.workbenchId,
      correlation_id: correlationId,
      expected_revision_id: request.expectedRevisionId,
      variant_id: request.variantId,
      base_revision_id: request.baseRevisionId ?? request.expectedRevisionId,
      payload: {
        variant_id: request.variantId,
        candidate_revision_id: request.candidateRevisionId,
        validation_id: request.validationId,
      },
    };
    return assertValidCommand(
      validateWorkspaceRevisionPromoteCommand(command),
      "workspace.revision_promote",
    );
  }

  async createRevisionRoot(request: RevisionCreateRequest): Promise<CommandReceipt> {
    const prepared = this.#prepareRevision(request, {
      expectedRevisionId: null,
      variantId: null,
      baseRevisionId: null,
    });
    await this.#stageFiles(prepared.files);
    return this.#sessionClient.postCommand(prepared.command);
  }

  async createRevisionChild(request: RevisionCreateRequest): Promise<CommandReceipt> {
    const baseRevisionId = request.baseRevisionId;
    const variantId = request.variantId;
    if (baseRevisionId === undefined || variantId === undefined) {
      throw new Error("child revision requires baseRevisionId and variantId");
    }
    const prepared = this.#prepareRevision(request, {
      expectedRevisionId: request.expectedRevisionId ?? baseRevisionId,
      variantId,
      baseRevisionId,
    });
    await this.#stageFiles(prepared.files);
    return this.#sessionClient.postCommand(prepared.command);
  }

  async createStrategyVariant(request: VariantCreateRequest): Promise<CommandReceipt> {
    return this.#sessionClient.postCommand(
      this.buildStrategyVariantCreateCommand(request),
    );
  }

  async createMergeCandidate(request: MergeCreateRequest): Promise<CommandReceipt> {
    const prepared = this.#prepareMerge(request);
    await this.#stageFiles(prepared.files);
    return this.#sessionClient.postCommand(prepared.command);
  }

  async requestFormalRun(request: FormalRunRequest): Promise<CommandReceipt> {
    const prepared = this.#prepareFormalRun(request);
    const staged = await this.#sessionClient.stageJson(request.engineInputJson);
    assertStagedJsonIdentity(staged, prepared.engineInput);
    return this.#sessionClient.postCommand(prepared.command);
  }

  async promoteRevision(request: RevisionPromoteRequest): Promise<CommandReceipt> {
    return this.#sessionClient.postCommand(
      this.buildRevisionPromoteCommand(request),
    );
  }

  // Explicit aliases keep the operation names close to the command/tool names.
  createRootRevision = this.createRevisionRoot.bind(this);
  createChildRevision = this.createRevisionChild.bind(this);
  createVariant = this.createStrategyVariant.bind(this);
  createMerge = this.createMergeCandidate.bind(this);
  runFormal = this.requestFormalRun.bind(this);
  promote = this.promoteRevision.bind(this);

  async getRevision(projectId: string, revisionId: string): Promise<RevisionDetail> {
    const query = new URLSearchParams({ project_id: projectId });
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/revisions/${encodeURIComponent(revisionId)}?${query}`,
      { headers: { Accept: "application/json" } },
    );
    return assertRevisionDetail(await this.#jsonResponse(response), projectId, revisionId);
  }

  async listVariants(projectId: string): Promise<StrategyVariantSummary[]> {
    const query = new URLSearchParams({ project_id: projectId });
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/variants?${query}`,
      { headers: { Accept: "application/json" } },
    );
    const payload = asRecord(await this.#jsonResponse(response), "variants response");
    if (!Array.isArray(payload.variants) || payload.variants.length > MAX_VARIANTS) {
      throw new Error("quant-domain variants response has an invalid shape");
    }
    return payload.variants.map((variant) => assertVariantSummary(variant, projectId));
  }

  async compareRevisions(
    projectId: string,
    leftRevisionId: string,
    rightRevisionId: string,
  ): Promise<RevisionComparison> {
    const query = new URLSearchParams({
      project_id: projectId,
      left_revision_id: leftRevisionId,
      right_revision_id: rightRevisionId,
    });
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/revisions/compare?${query}`,
      { headers: { Accept: "application/json" } },
    );
    return assertComparison(
      await this.#jsonResponse(response),
      projectId,
      leftRevisionId,
      rightRevisionId,
    );
  }

  async getProjectRevisionHead(projectId: string): Promise<ProjectRevisionHead> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/revision-head`,
      { headers: { Accept: "application/json" } },
    );
    return assertProjectHead(await this.#jsonResponse(response), projectId);
  }

  getVariants = this.listVariants.bind(this);
  compare = this.compareRevisions.bind(this);
  projectHead = this.getProjectRevisionHead.bind(this);

  #prepareRevision(
    request: RevisionCreateRequest,
    lineage: {
      expectedRevisionId: string | null;
      variantId: string | null;
      baseRevisionId: string | null;
    },
  ): PreparedRevision {
    const commandId = this.#commandId(request.commandId);
    const correlationId = this.#correlationId(request.correlationId, commandId);
    const revisionId = request.revisionId ?? stableIdentityUuid(`${commandId}:revision`);
    const files = prepareFiles(request.files);
    const payload: RevisionCreatePayload = {
      revision_id: revisionId,
      message: request.message,
      files: files.map(({ path, artifact }) => ({ path, artifact })),
    };
    const command = {
      command_id: commandId,
      schema_version: 1,
      command_type: "workspace.revision_create",
      project_id: request.projectId,
      activity_id: request.activityId,
      session_id: request.sessionId,
      workbench_id: request.workbenchId,
      correlation_id: correlationId,
      expected_revision_id: lineage.expectedRevisionId,
      variant_id: lineage.variantId,
      base_revision_id: lineage.baseRevisionId,
      payload,
    } as unknown as WorkspaceRevisionCreateCommand;
    const validated = assertValidCommand(
      validateWorkspaceRevisionCreateCommand(command),
      "workspace.revision_create",
    );
    return { command: validated, files };
  }

  #prepareMerge(request: MergeCreateRequest): PreparedMerge {
    const commandId = this.#commandId(request.commandId);
    const correlationId = this.#correlationId(request.correlationId, commandId);
    const candidateRevisionId = request.candidateRevisionId ??
      stableIdentityUuid(`${commandId}:merge-candidate`);
    const files = prepareFiles(request.files);
    const command: WorkspaceMergeCreateCommand = {
      command_id: commandId,
      schema_version: 1,
      command_type: "workspace.merge_create",
      project_id: request.projectId,
      activity_id: request.activityId,
      session_id: request.sessionId,
      workbench_id: request.workbenchId,
      correlation_id: correlationId,
      expected_revision_id: request.expectedRevisionId,
      variant_id: request.variantId,
      base_revision_id: request.baseRevisionId,
      payload: {
        candidate_revision_id: candidateRevisionId,
        message: request.message,
        files: files.map(({ path, artifact }) => ({ path, artifact })),
      },
    };
    return {
      command: assertValidCommand(
        validateWorkspaceMergeCreateCommand(command),
        "workspace.merge_create",
      ),
      files,
    };
  }

  #prepareFormalRun(request: FormalRunRequest): PreparedFormalRun {
    const commandId = this.#commandId(request.commandId);
    const correlationId = this.#correlationId(request.correlationId, commandId);
    const engineInput = canonicalJsonArtifactRef(request.engineInputJson);
    const command: FormalRunCommand = {
      command_id: commandId,
      schema_version: 1,
      command_type: "formal.run_request",
      project_id: request.projectId,
      activity_id: request.activityId,
      session_id: request.sessionId,
      workbench_id: request.workbenchId,
      correlation_id: correlationId,
      expected_revision_id: request.candidateRevisionId,
      variant_id: request.variantId,
      base_revision_id: request.candidateRevisionId,
      payload: {
        run_spec_id: request.runSpecId ?? stableIdentityUuid(`${commandId}:run-spec`),
        run_id: request.runId ?? stableIdentityUuid(`${commandId}:run`),
        validation_id: request.validationId ??
          stableIdentityUuid(`${commandId}:validation`),
        candidate_revision_id: request.candidateRevisionId,
        engine_input: engineInput,
        data_snapshot_id: request.dataSnapshotId,
        data_snapshot_sha256: request.dataSnapshotSha256,
        strategy_tree_oid: request.strategyTreeOid,
        parameters_sha256: request.parametersSha256,
        cost_model_sha256: request.costModelSha256,
        environment_lock_sha256: request.environmentLockSha256,
        engine_version: "oqs-quant-engine/0.1.0",
        price_basis: request.priceBasis,
        cutoff: request.cutoff,
        timezone: request.timezone,
        sample_start: request.sampleStart,
        sample_end: request.sampleEnd,
        random_seed: request.randomSeed,
        output_schema_version: 1,
        gate_policy_version: "m3-v1",
      },
    };
    return {
      command: assertFormalRunCommand(
        validateFormalRunCommand(command),
        "formal.run_request",
      ),
      engineInput,
    };
  }

  async #stageFiles(files: PreparedRevisionFile[]): Promise<void> {
    for (const file of files) {
      const staged = await this.#sessionClient.stageText(file.body);
      assertStagedIdentity(staged, file.artifact);
    }
  }

  #commandId(value: string | undefined): string {
    const commandId = value ?? randomUUID();
    assertUuid(commandId, "commandId");
    return commandId;
  }

  #correlationId(value: string | undefined, commandId: string): string {
    const correlationId = value ?? stableIdentityUuid(`${commandId}:correlation`);
    assertUuid(correlationId, "correlationId");
    return correlationId;
  }

  async #jsonResponse(response: Response): Promise<unknown> {
    if (!response.ok) {
      throw new QuantDomainHttpError({
        status: response.status,
        code: await boundedResponseCode(response),
      });
    }
    return response.json();
  }
}

export { FetchQuantDomainRevisionClient as QuantDomainRevisionClient };

function prepareFiles(files: RevisionFileInput[]): PreparedRevisionFile[] {
  if (!Array.isArray(files) || files.length < 1 || files.length > MAX_FILES) {
    throw new Error("revision files must contain between 1 and 32 files");
  }
  return files.map((file) => {
    const body = file.body;
    if (typeof body !== "string") {
      throw new Error("revision file body is required");
    }
    return {
      path: file.path,
      body,
      artifact: canonicalTextArtifactRef(body) as M3ArtifactRef,
    };
  });
}

function assertStagedIdentity(staged: ArtifactBlobReceipt, artifact: M3ArtifactRef): void {
  if (
    staged.sha256 !== artifact.sha256 ||
    staged.byte_size !== artifact.byte_size ||
    staged.storage_uri !== artifact.storage_uri
  ) {
    throw new Error("staged revision file identity changed before command submission");
  }
}

function assertStagedJsonIdentity(
  staged: ArtifactBlobReceipt,
  artifact: ArtifactRef,
): void {
  if (
    staged.sha256 !== artifact.sha256 ||
    staged.byte_size !== artifact.byte_size ||
    staged.storage_uri !== artifact.storage_uri
  ) {
    throw new Error("staged formal engine input identity changed before command submission");
  }
}

function canonicalJsonArtifactRef(body: string): ArtifactRef {
  const bytes = new TextEncoder().encode(body);
  if (bytes.byteLength < 2 || bytes.byteLength > 5 * 1024 * 1024) {
    throw new Error("formal engine input must contain between 2 and 5242880 UTF-8 bytes");
  }
  JSON.parse(body);
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  return {
    artifact_id: stableIdentityUuid(`${sha256}:formal-engine-input-artifact`),
    sha256,
    media_type: "application/json",
    byte_size: bytes.byteLength,
    storage_uri: `cas://sha256/${sha256}`,
    producing_revision_id: null,
    producing_run_id: null,
    provenance: {
      origin_kind: "service_generated",
      source_ref: stableIdentityUuid(`${sha256}:formal-engine-input-provenance`),
    },
  };
}

function assertValidCommand<T extends RevisionCommand>(
  result: { valid: true; value: T } | { valid: false; errors: string[] },
  commandType: string,
): T {
  if (!result.valid) {
    throw new Error(`${commandType} command contract violation: ${result.errors.join("; ")}`);
  }
  return result.value;
}

function assertFormalRunCommand(
  result:
    | { valid: true; value: FormalRunCommand }
    | { valid: false; errors: string[] },
  commandType: string,
): FormalRunCommand {
  if (!result.valid) {
    throw new Error(`${commandType} command contract violation: ${result.errors.join("; ")}`);
  }
  return result.value;
}

function assertUuid(value: string, name: string): void {
  if (!UUID_PATTERN.test(value)) {
    throw new Error(`${name} must be a UUID`);
  }
}

function asRecord(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`quant-domain ${label} has an invalid shape`);
  }
  return value as Record<string, unknown>;
}

function assertRevisionDetail(
  value: unknown,
  projectId: string,
  revisionId: string,
): RevisionDetail {
  const record = asRecord(value, "revision response");
  assertNoSourceBody(record);
  if (
    record.revision_id !== revisionId ||
    record.project_id !== projectId ||
    typeof record.activity_id !== "string" ||
    !isNullableUuid(record.variant_id) ||
    !isNullableUuid(record.base_revision_id) ||
    !isGitOid(record.git_commit_oid) ||
    !isGitOid(record.git_tree_oid) ||
    typeof record.message !== "string" ||
    record.message.length < 1 ||
    record.message.length > 256 ||
    typeof record.created_by_session_id !== "string" ||
    record.created_by_session_id.length < 1 ||
    typeof record.created_at !== "string" ||
    !Array.isArray(record.files) ||
    record.files.length < 1 ||
    record.files.length > MAX_FILES
  ) {
    throw new Error("quant-domain revision response has an invalid shape or identity");
  }
  return {
    revision_id: revisionId,
    project_id: projectId,
    activity_id: record.activity_id,
    variant_id: record.variant_id as string | null,
    base_revision_id: record.base_revision_id as string | null,
    git_commit_oid: record.git_commit_oid as string,
    git_tree_oid: record.git_tree_oid as string,
    message: record.message,
    created_by_session_id: record.created_by_session_id,
    created_at: record.created_at,
    files: record.files.map((file) => assertRevisionFile(file)),
  };
}

function assertRevisionFile(value: unknown): RevisionDetailFile {
  const record = asRecord(value, "revision file response");
  assertNoSourceBody(record);
  if (
    typeof record.path !== "string" ||
    record.path.length < 1 ||
    record.path.length > 240 ||
    !isUuid(record.artifact_id) ||
    !isGitOid(record.git_blob_oid) ||
    !isSha256(record.sha256) ||
    !Number.isInteger(record.byte_size) ||
    (record.byte_size as number) < 0 ||
    (record.byte_size as number) > MAX_TEXT_BYTES ||
    record.media_type !== "text/plain" ||
    record.storage_uri !== `cas://sha256/${record.sha256}`
  ) {
    throw new Error("quant-domain revision file response has an invalid shape");
  }
  return {
    path: record.path,
    artifact_id: record.artifact_id,
    git_blob_oid: record.git_blob_oid,
    sha256: record.sha256,
    byte_size: record.byte_size as number,
    media_type: "text/plain",
    storage_uri: record.storage_uri,
  };
}

function assertVariantSummary(value: unknown, projectId: string): StrategyVariantSummary {
  const record = asRecord(value, "variant response");
  assertNoSourceBody(record);
  if (
    !isUuid(record.variant_id) ||
    record.project_id !== projectId ||
    typeof record.activity_id !== "string" ||
    !isUuid(record.base_revision_id) ||
    typeof record.created_by_session_id !== "string" ||
    record.created_by_session_id.length < 1 ||
    typeof record.created_at !== "string" ||
    !isUuid(record.head_revision_id) ||
    !Number.isInteger(record.version) ||
    (record.version as number) < 0 ||
    typeof record.updated_at !== "string"
  ) {
    throw new Error("quant-domain variant response has an invalid shape or identity");
  }
  return {
    variant_id: record.variant_id,
    project_id: projectId,
    activity_id: record.activity_id,
    base_revision_id: record.base_revision_id,
    created_by_session_id: record.created_by_session_id,
    created_at: record.created_at,
    head_revision_id: record.head_revision_id,
    version: record.version as number,
    updated_at: record.updated_at,
  };
}

function assertComparison(
  value: unknown,
  projectId: string,
  leftRevisionId: string,
  rightRevisionId: string,
): RevisionComparison {
  const record = asRecord(value, "revision comparison response");
  assertNoSourceBody(record);
  if (
    record.project_id !== projectId ||
    record.left_revision_id !== leftRevisionId ||
    record.right_revision_id !== rightRevisionId ||
    !Array.isArray(record.changes) ||
    record.changes.length > MAX_CHANGES
  ) {
    throw new Error("quant-domain revision comparison crossed request identity or has an invalid shape");
  }
  return {
    project_id: projectId,
    left_revision_id: leftRevisionId,
    right_revision_id: rightRevisionId,
    changes: record.changes.map((change) => assertComparisonChange(change)),
  };
}

function assertComparisonChange(value: unknown): RevisionComparisonChange {
  const record = asRecord(value, "revision comparison change");
  assertNoSourceBody(record);
  if (
    typeof record.path !== "string" ||
    record.path.length < 1 ||
    record.path.length > 240 ||
    !isNullableUuid(record.left_artifact_id) ||
    !isNullableSha256(record.left_sha256) ||
    !isNullableUuid(record.right_artifact_id) ||
    !isNullableSha256(record.right_sha256)
  ) {
    throw new Error("quant-domain revision comparison change has an invalid shape");
  }
  return {
    path: record.path,
    left_artifact_id: record.left_artifact_id as string | null,
    left_sha256: record.left_sha256 as string | null,
    right_artifact_id: record.right_artifact_id as string | null,
    right_sha256: record.right_sha256 as string | null,
  };
}

function assertProjectHead(value: unknown, projectId: string): ProjectRevisionHead {
  const record = asRecord(value, "project revision head response");
  assertNoSourceBody(record);
  if (
    record.project_id !== projectId ||
    !isUuid(record.head_revision_id)
  ) {
    throw new Error("quant-domain project revision head crossed request identity or has an invalid shape");
  }
  return { project_id: projectId, head_revision_id: record.head_revision_id };
}

function assertNoSourceBody(record: Record<string, unknown>): void {
  for (const key of ["body", "content", "text", "source_body", "source_text", "bytes"]) {
    if (key in record) {
      throw new Error("quant-domain revision response must not include source bodies");
    }
  }
}

function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

function isNullableUuid(value: unknown): value is string | null {
  return value === null || isUuid(value);
}

function isSha256(value: unknown): value is string {
  return typeof value === "string" && SHA256_PATTERN.test(value);
}

function isNullableSha256(value: unknown): value is string | null {
  return value === null || isSha256(value);
}

function isGitOid(value: unknown): value is string {
  return typeof value === "string" && GIT_OID_PATTERN.test(value);
}
