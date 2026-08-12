import { createHash, randomUUID } from "node:crypto";

import {
  type ActivityListReadModel,
  type ArtifactRef,
  type ArtifactMetadataReadModel,
  type DataImportPreviewReadModel,
  type DataSnapshotCreateCommand,
  type DataSnapshotListReadModel,
  type DataSnapshotMapping,
  type DataSnapshotMarket,
  type DataSnapshotPriceBasis,
  type DataSnapshotReadModel,
  type DataSnapshotSourceArtifact,
  type DataSnapshotSourceFormat,
  type DiagnosticCommand,
  type DiagnosticLog,
  type DiagnosticLogListReadModel,
  type FormalRunCommand,
  type FormalRunRequestPayload,
  type FormalRunDetailReadModel,
  type FormalRunListReadModel,
  type ForwardTestCommand,
  type ForwardTestReadModel,
  type M3ArtifactRef,
  type ProjectArchiveCommand,
  type ProjectListReadModel,
  type RunReportReadModel,
  type RevisionCreatePayload,
  type StrategyVariantCreateCommand,
  type WorkspaceMergeCreateCommand,
  type WorkspaceRevisionCreateChildCommand,
  type WorkspaceRevisionCreateCommand,
  type WorkspaceRevisionCreateRootCommand,
  type WorkspaceRevisionPromoteCommand,
  validateActivityListReadModel,
  validateArtifactMetadataReadModel,
  validateDataImportPreviewReadModel,
  validateDataSnapshotCommand,
  validateDataSnapshotListReadModel,
  validateDataSnapshotReadModel,
  validateDiagnosticCommand,
  validateDiagnosticLogListReadModel,
  validateFormalRunCommand,
  validateFormalRunDetailReadModel,
  validateFormalRunListReadModel,
  validateForwardTestCommand,
  validateForwardTestReadModel,
  validateProjectArchiveCommand,
  validateProjectListReadModel,
  validateRunReportReadModel,
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

export const PROJECT_ARCHIVE_MEDIA_TYPE =
  "application/vnd.open-quant-studio.project-archive+zip";
export const PROJECT_ARCHIVE_MAX_BYTES = 10 * 1024 * 1024 * 1024;
export type ProjectArchiveLogSelection = "full" | "warn_error" | "none";

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
  removedPaths?: string[];
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
  marketInputJson: string;
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
  marketInputOriginKind?: "fixture" | "service_generated";
  marketInputSourceRef?: string;
  checkpointBatchSize?: number;
  runSpecId?: string;
  runId?: string;
  validationId?: string;
}

export interface DataSnapshotCreateRequest extends RevisionCommandContext {
  source: DataSnapshotSourceArtifact;
  sourceFormat: DataSnapshotSourceFormat;
  fileName: string;
  mapping: DataSnapshotMapping;
  market: DataSnapshotMarket;
  timezone: string;
  priceBasis: DataSnapshotPriceBasis;
  cutoff: string;
  snapshotId?: string;
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

export interface BuiltInStrategyParameter {
  name: string;
  value: string | number;
  meaning: string;
}

export interface BuiltInStrategy {
  strategy_id: string;
  title: string;
  market: "a_share_daily" | "crypto_linear_perp";
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

export class DataImportPreviewHttpError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly details: DataImportRowError[],
  ) {
    super(`quant-domain data import preview returned HTTP ${status} (${code})`);
    this.name = "DataImportPreviewHttpError";
  }
}

export interface ForwardTestRequest extends RevisionCommandContext {
  sourceRunId: string;
  sourceRevisionId: string;
  variantId: string;
  forwardTestId?: string;
}

export interface ProjectArchiveImportRequest extends RevisionCommandContext {
  archive: Uint8Array<ArrayBuffer>;
}

export interface DiagnosticLogListFilters {
  runId?: string;
  activityId?: string;
  sessionId?: string;
  level?: DiagnosticLog["level"];
  priority?: DiagnosticLog["priority"];
  query?: string;
  afterLogSeq?: number;
  limit?: number;
}

export interface DiagnosticLogDeleteRequest extends RevisionCommandContext {
  logIds: string[];
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
  marketInput: ArtifactRef;
}

interface PreparedProjectArchiveImport {
  command: ProjectArchiveCommand;
  archive: ArtifactRef;
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

  buildDataSnapshotCreateCommand(
    request: DataSnapshotCreateRequest,
  ): DataSnapshotCreateCommand {
    const commandId = this.#commandId(request.commandId);
    const correlationId = this.#correlationId(request.correlationId, commandId);
    const command: DataSnapshotCreateCommand = {
      command_id: commandId,
      schema_version: 1,
      command_type: "data.snapshot_create",
      project_id: request.projectId,
      activity_id: request.activityId,
      session_id: request.sessionId,
      workbench_id: request.workbenchId,
      correlation_id: correlationId,
      expected_revision_id: null,
      variant_id: null,
      base_revision_id: null,
      payload: {
        snapshot_id: request.snapshotId ?? stableIdentityUuid(`${commandId}:data-snapshot`),
        source: request.source,
        source_format: request.sourceFormat,
        file_name: request.fileName,
        mapping: request.mapping,
        market: request.market,
        timezone: request.timezone,
        price_basis: request.priceBasis,
        cutoff: request.cutoff,
      },
    };
    return assertValidCommand(
      validateDataSnapshotCommand(command),
      "data.snapshot_create",
    );
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
    const staged = await this.#sessionClient.stageJson(request.marketInputJson);
    assertStagedJsonIdentity(staged, prepared.marketInput);
    return this.#sessionClient.postCommand(prepared.command);
  }

  async createDataSnapshot(
    request: DataSnapshotCreateRequest,
  ): Promise<CommandReceipt> {
    return this.#sessionClient.postCommand(
      this.buildDataSnapshotCreateCommand(request),
    );
  }

  async requestForwardTest(request: ForwardTestRequest): Promise<CommandReceipt> {
    return this.#sessionClient.postCommand(this.#prepareForwardTest(request));
  }

  async deleteLogs(request: DiagnosticLogDeleteRequest): Promise<CommandReceipt> {
    return this.#sessionClient.postCommand(this.#prepareDiagnosticLogDelete(request));
  }

  async importProjectArchive(
    request: ProjectArchiveImportRequest,
  ): Promise<CommandReceipt> {
    const prepared = this.#prepareProjectArchiveImport(request);
    const staged = await this.#stageProjectArchive(request.archive, prepared.archive);
    assertStagedProjectArchiveIdentity(staged, prepared.archive);
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
  runForwardTest = this.requestForwardTest.bind(this);
  importArchive = this.importProjectArchive.bind(this);
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

  async listProjects(): Promise<ProjectListReadModel> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects`,
      { headers: { Accept: "application/json" } },
    );
    return assertReadContract(
      validateProjectListReadModel(await this.#jsonResponse(response)),
      "projects response",
    );
  }

  async listActivities(projectId: string): Promise<ActivityListReadModel> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/activities`,
      { headers: { Accept: "application/json" } },
    );
    const activities = assertReadContract(
      validateActivityListReadModel(await this.#jsonResponse(response)),
      "activities response",
    );
    if (activities.activities.some((activity) => activity.project_id !== projectId)) {
      throw new Error("quant-domain activities response crossed project identity");
    }
    return activities;
  }

  async listBuiltInStrategies(): Promise<BuiltInStrategy[]> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/strategies`,
      { headers: { Accept: "application/json" } },
    );
    const payload = asRecord(
      await this.#jsonResponse(response),
      "strategy catalog response",
    );
    if (!Array.isArray(payload.strategies)) {
      throw new Error("quant-domain strategy catalog response has an invalid shape");
    }
    return payload.strategies as BuiltInStrategy[];
  }

  async renderStrategyNotebook(
    strategyId: string,
    source: string,
  ): Promise<RenderedStrategyNotebook> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/strategies/${encodeURIComponent(strategyId)}/notebook`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ source }),
      },
    );
    return await this.#jsonResponse(response) as RenderedStrategyNotebook;
  }

  async listRuns(
    projectId: string,
    activityId: string,
  ): Promise<FormalRunListReadModel> {
    const query = new URLSearchParams({ activity_id: activityId });
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/runs?${query}`,
      { headers: { Accept: "application/json" } },
    );
    const runs = assertReadContract(
      validateFormalRunListReadModel(await this.#jsonResponse(response)),
      "Formal Run list response",
    );
    if (
      runs.runs.some(
        (run) => run.project_id !== projectId || run.activity_id !== activityId,
      )
    ) {
      throw new Error("quant-domain Formal Run list crossed request identity");
    }
    return runs;
  }

  async previewDataImport(
    projectId: string,
    fileName: string,
    sourceFormat: DataSnapshotSourceFormat,
    body: Uint8Array<ArrayBuffer>,
  ): Promise<DataImportPreviewReadModel> {
    const query = new URLSearchParams({ file_name: fileName, source_format: sourceFormat });
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/data-imports/preview?${query}`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": sourceFormat === "csv"
            ? "text/csv"
            : "application/vnd.apache.parquet",
        },
        body,
      },
    );
    if (!response.ok) {
      throw await dataImportPreviewError(response);
    }
    return assertReadContract(
      validateDataImportPreviewReadModel(await response.json()),
      "data import preview response",
    );
  }

  async listLocalDataImports(projectId: string): Promise<LocalDataImportFile[]> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/data-imports/local-files`,
      { headers: { Accept: "application/json" } },
    );
    const record = asRecord(await this.#jsonResponse(response), "local data imports response");
    if (!Array.isArray(record.files)) {
      throw new Error("quant-domain local data imports response has an invalid shape");
    }
    return record.files.map((file) => {
      const item = asRecord(file, "local data import file");
      if (
        typeof item.file_name !== "string"
        || (item.source_format !== "csv" && item.source_format !== "parquet")
        || !Number.isInteger(item.byte_size)
      ) {
        throw new Error("quant-domain local data import file has an invalid shape");
      }
      return {
        file_name: item.file_name,
        source_format: item.source_format,
        byte_size: item.byte_size as number,
      };
    });
  }

  async previewLocalDataImport(
    projectId: string,
    fileName: string,
  ): Promise<DataImportPreviewReadModel> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/data-imports/local-preview`,
      {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ file_name: fileName }),
      },
    );
    if (!response.ok) {
      throw await dataImportPreviewError(response);
    }
    return assertReadContract(
      validateDataImportPreviewReadModel(await response.json()),
      "local data import preview response",
    );
  }

  async listDataSnapshots(projectId: string): Promise<DataSnapshotListReadModel> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/data-snapshots`,
      { headers: { Accept: "application/json" } },
    );
    const snapshots = assertReadContract(
      validateDataSnapshotListReadModel(await this.#jsonResponse(response)),
      "data snapshot list response",
    );
    if (snapshots.snapshots.some((snapshot) => snapshot.project_id !== projectId)) {
      throw new Error("quant-domain data snapshot list crossed project identity");
    }
    return snapshots;
  }

  async getDataSnapshot(
    projectId: string,
    snapshotId: string,
  ): Promise<DataSnapshotReadModel> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/data-snapshots/${encodeURIComponent(snapshotId)}`,
      { headers: { Accept: "application/json" } },
    );
    const snapshot = assertReadContract(
      validateDataSnapshotReadModel(await this.#jsonResponse(response)),
      "data snapshot response",
    );
    if (snapshot.project_id !== projectId || snapshot.snapshot_id !== snapshotId) {
      throw new Error("quant-domain data snapshot response crossed request identity");
    }
    return snapshot;
  }

  async getDataSnapshotMarketInput(
    projectId: string,
    snapshot: DataSnapshotReadModel,
  ): Promise<string> {
    if (snapshot.project_id !== projectId) {
      throw new Error("quant-domain data snapshot crossed request identity");
    }
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/data-snapshots/${encodeURIComponent(snapshot.snapshot_id)}/market-input`,
      { headers: { Accept: "application/json" } },
    );
    if (!response.ok) {
      throw new QuantDomainHttpError({
        status: response.status,
        code: await boundedResponseCode(response),
      });
    }
    const mediaType = response.headers.get("content-type")?.split(";", 1)[0]?.trim();
    if (mediaType !== "application/json") {
      throw new Error("quant-domain data snapshot market input returned the wrong media type");
    }
    const marketInputJson = await response.text();
    JSON.parse(marketInputJson);
    if (createHash("sha256").update(marketInputJson).digest("hex") !== snapshot.market_input_sha256) {
      throw new Error("quant-domain data snapshot market input failed identity verification");
    }
    return marketInputJson;
  }

  async listLogs(
    projectId: string,
    filters: DiagnosticLogListFilters = {},
  ): Promise<DiagnosticLogListReadModel> {
    const query = new URLSearchParams({ project_id: projectId });
    if (filters.runId !== undefined) {
      query.set("run_id", filters.runId);
    }
    if (filters.activityId !== undefined) {
      query.set("activity_id", filters.activityId);
    }
    if (filters.sessionId !== undefined) {
      query.set("session_id", filters.sessionId);
    }
    if (filters.level !== undefined) {
      query.set("level", filters.level);
    }
    if (filters.priority !== undefined) {
      query.set("priority", filters.priority);
    }
    if (filters.query !== undefined) {
      query.set("query", filters.query);
    }
    if (filters.afterLogSeq !== undefined) {
      query.set("after_log_seq", String(filters.afterLogSeq));
    }
    if (filters.limit !== undefined) {
      query.set("limit", String(filters.limit));
    }
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/logs?${query}`,
      { headers: { Accept: "application/json" } },
    );
    const logs = assertReadContract(
      validateDiagnosticLogListReadModel(await this.#jsonResponse(response)),
      "diagnostic log list response",
    );
    if (logs.logs.some((log) => log.project_id !== projectId)) {
      throw new Error("quant-domain diagnostic log list crossed project identity");
    }
    return logs;
  }

  async getRun(projectId: string, runId: string): Promise<FormalRunDetailReadModel> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}`,
      { headers: { Accept: "application/json" } },
    );
    const run = assertReadContract(
      validateFormalRunDetailReadModel(await this.#jsonResponse(response)),
      "Formal Run detail response",
    );
    if (run.run.project_id !== projectId || run.run.run_id !== runId) {
      throw new Error("quant-domain Formal Run detail crossed request identity");
    }
    if (run.run.status === "succeeded") {
      const [intentTapeBytes, engineResultBytes, manifestBytes] = await Promise.all([
        this.getArtifactContent(projectId, run.artifacts.intent_tape),
        this.getArtifactContent(projectId, run.artifacts.engine_result),
        this.getArtifactContent(projectId, run.artifacts.manifest),
      ]);
      assertEmbeddedArtifact(
        run.intent_tape,
        parseJsonArtifact(intentTapeBytes, "intent_tape"),
        "intent_tape",
      );
      assertEmbeddedArtifact(
        run.engine_result,
        parseJsonArtifact(engineResultBytes, "engine_result"),
        "engine_result",
      );
      assertEmbeddedArtifact(
        run.manifest,
        parseJsonArtifact(manifestBytes, "manifest"),
        "manifest",
      );
    }
    return run;
  }

  async getRunReport(projectId: string, runId: string): Promise<RunReportReadModel> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/report`,
      { headers: { Accept: "application/json" } },
    );
    const report = assertReadContract(
      validateRunReportReadModel(await this.#jsonResponse(response)),
      "Formal Run report response",
    );
    if (report.report.run.project_id !== projectId || report.report.run.run_id !== runId) {
      throw new Error("quant-domain Formal Run report crossed request identity");
    }
    return report;
  }

  async getForwardTest(
    projectId: string,
    forwardTestId: string,
  ): Promise<ForwardTestReadModel> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/forward-tests/${encodeURIComponent(forwardTestId)}`,
      { headers: { Accept: "application/json" } },
    );
    const forwardTest = assertReadContract(
      validateForwardTestReadModel(await this.#jsonResponse(response)),
      "Forward Test response",
    );
    if (
      forwardTest.project_id !== projectId
      || forwardTest.forward_test_id !== forwardTestId
    ) {
      throw new Error("quant-domain Forward Test response crossed request identity");
    }
    return forwardTest;
  }

  async getProjectArchive(
    projectId: string,
    selectedLogs: ProjectArchiveLogSelection = "full",
  ): Promise<Uint8Array> {
    const query = new URLSearchParams({ selected_logs: selectedLogs });
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/archive?${query}`,
      { headers: { Accept: PROJECT_ARCHIVE_MEDIA_TYPE } },
    );
    if (!response.ok) {
      throw new QuantDomainHttpError({
        status: response.status,
        code: await boundedResponseCode(response),
      });
    }
    const mediaType = response.headers.get("content-type")?.split(";", 1)[0]?.trim();
    if (mediaType !== PROJECT_ARCHIVE_MEDIA_TYPE) {
      throw new Error("quant-domain project archive returned the wrong media type");
    }
    return new Uint8Array(await response.arrayBuffer());
  }

  async getArtifact(
    projectId: string,
    artifactId: string,
  ): Promise<ArtifactMetadataReadModel> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}`,
      { headers: { Accept: "application/json" } },
    );
    const artifact = assertReadContract(
      validateArtifactMetadataReadModel(await this.#jsonResponse(response)),
      "artifact metadata response",
    );
    if (artifact.artifact_id !== artifactId || artifact.project_id !== projectId) {
      throw new Error("quant-domain artifact metadata crossed request identity");
    }
    return artifact;
  }

  async getArtifactContent(
    projectId: string,
    artifact: ArtifactMetadataReadModel,
  ): Promise<Uint8Array> {
    if (artifact.project_id !== projectId) {
      throw new Error("quant-domain artifact metadata crossed request identity");
    }
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifact.artifact_id)}/content`,
      { headers: { Accept: artifact.media_type } },
    );
    if (!response.ok) {
      throw new QuantDomainHttpError({
        status: response.status,
        code: await boundedResponseCode(response),
      });
    }
    const mediaType = response.headers.get("content-type")?.split(";", 1)[0]?.trim();
    if (mediaType !== artifact.media_type) {
      throw new Error("quant-domain artifact content returned the wrong media type");
    }
    const content = new Uint8Array(await response.arrayBuffer());
    if (
      content.byteLength !== artifact.byte_size
      || createHash("sha256").update(content).digest("hex") !== artifact.sha256
    ) {
      throw new Error("quant-domain artifact content failed identity verification");
    }
    return content;
  }

  getVariants = this.listVariants.bind(this);
  compare = this.compareRevisions.bind(this);
  projectHead = this.getProjectRevisionHead.bind(this);
  getProjects = this.listProjects.bind(this);
  getActivities = this.listActivities.bind(this);
  getRuns = this.listRuns.bind(this);
  getDataSnapshots = this.listDataSnapshots.bind(this);

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
      ...(request.removedPaths === undefined
        ? {}
        : { removed_paths: request.removedPaths }),
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
    const marketInput = canonicalJsonArtifactRef(
      request.marketInputJson,
      request.marketInputOriginKind,
      request.marketInputSourceRef,
    );
    const inputSchemaVersion = asRecord(
      JSON.parse(request.marketInputJson),
      "Formal Run market input",
    ).schema_version;
    const engineProfile = inputSchemaVersion === 2
      ? {
          engine_version: "oqs-quant-engine/0.2.0" as const,
          output_schema_version: 2 as const,
          gate_policy_version: "m8-v1" as const,
          strategy_protocol_version: "oqs-strategy-host/m8-portfolio-v1" as const,
          engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v2" as const,
        }
      : {
          engine_version: "oqs-quant-engine/0.1.0" as const,
          output_schema_version: 1 as const,
          gate_policy_version: "m5-v1" as const,
          strategy_protocol_version: "oqs-strategy-host/m5-stream-v2" as const,
          engine_checkpoint_abi: "oqs-quant-engine/checkpoint-v1" as const,
        };
    const payload: FormalRunRequestPayload = {
      run_spec_id: request.runSpecId ?? stableIdentityUuid(`${commandId}:run-spec`),
      run_id: request.runId ?? stableIdentityUuid(`${commandId}:run`),
      validation_id: request.validationId ?? stableIdentityUuid(`${commandId}:validation`),
      candidate_revision_id: request.candidateRevisionId,
      market_input: marketInput,
      data_snapshot_id: request.dataSnapshotId,
      data_snapshot_sha256: request.dataSnapshotSha256,
      strategy_tree_oid: request.strategyTreeOid,
      parameters_sha256: request.parametersSha256,
      cost_model_sha256: request.costModelSha256,
      environment_lock_sha256: request.environmentLockSha256,
      price_basis: request.priceBasis,
      cutoff: request.cutoff,
      timezone: request.timezone,
      sample_start: request.sampleStart,
      sample_end: request.sampleEnd,
      random_seed: request.randomSeed,
      checkpoint_batch_size: request.checkpointBatchSize ?? 4096,
      ...engineProfile,
    };
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
      payload,
    };
    return {
      command: assertFormalRunCommand(
        validateFormalRunCommand(command),
        "formal.run_request",
      ),
      marketInput,
    };
  }

  #prepareForwardTest(request: ForwardTestRequest): ForwardTestCommand {
    const commandId = this.#commandId(request.commandId);
    const correlationId = this.#correlationId(request.correlationId, commandId);
    const forwardTestId = request.forwardTestId ??
      stableIdentityUuid(`${commandId}:forward-test`);
    const command: ForwardTestCommand = {
      command_id: commandId,
      schema_version: 1,
      command_type: "forward_test.request",
      project_id: request.projectId,
      activity_id: request.activityId,
      session_id: request.sessionId,
      workbench_id: request.workbenchId,
      correlation_id: correlationId,
      expected_revision_id: request.sourceRevisionId,
      variant_id: request.variantId,
      base_revision_id: request.sourceRevisionId,
      payload: {
        forward_test_id: forwardTestId,
        source_run_id: request.sourceRunId,
        protocol_version: "oqs-forward-replay/m5-v1",
      },
    };
    return assertValidCommand(
      validateForwardTestCommand(command),
      "forward_test.request",
    );
  }

  #prepareDiagnosticLogDelete(
    request: DiagnosticLogDeleteRequest,
  ): DiagnosticCommand {
    const commandId = this.#commandId(request.commandId);
    const correlationId = this.#correlationId(request.correlationId, commandId);
    const command: DiagnosticCommand = {
      command_id: commandId,
      schema_version: 1,
      command_type: "diagnostic.log_delete",
      project_id: request.projectId,
      activity_id: request.activityId,
      session_id: request.sessionId,
      workbench_id: request.workbenchId,
      correlation_id: correlationId,
      expected_revision_id: null,
      variant_id: null,
      base_revision_id: null,
      payload: {
        selection: {
          log_ids: request.logIds,
        },
      },
    };
    return assertValidCommand(
      validateDiagnosticCommand(command),
      "diagnostic.log_delete",
    );
  }

  #prepareProjectArchiveImport(
    request: ProjectArchiveImportRequest,
  ): PreparedProjectArchiveImport {
    const commandId = this.#commandId(request.commandId);
    const correlationId = this.#correlationId(request.correlationId, commandId);
    const archive = projectArchiveArtifact(request.archive, commandId);
    const command: ProjectArchiveCommand = {
      command_id: commandId,
      schema_version: 1,
      command_type: "project.archive_import",
      project_id: request.projectId,
      activity_id: request.activityId,
      session_id: request.sessionId,
      workbench_id: request.workbenchId,
      correlation_id: correlationId,
      expected_revision_id: null,
      variant_id: null,
      base_revision_id: null,
      payload: {
        expected_project_id: request.projectId,
        archive,
      },
    };
    return {
      command: assertValidCommand(
        validateProjectArchiveCommand(command),
        "project.archive_import",
      ),
      archive,
    };
  }

  async #stageFiles(files: PreparedRevisionFile[]): Promise<void> {
    for (const file of files) {
      const staged = await this.#sessionClient.stageText(file.body);
      assertStagedIdentity(staged, file.artifact);
    }
  }

  async #stageProjectArchive(
    body: Uint8Array<ArrayBuffer>,
    archive: ArtifactRef,
  ): Promise<ArtifactBlobReceipt> {
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/artifact-blobs/${archive.sha256}`,
      {
        method: "PUT",
        headers: { "Content-Type": PROJECT_ARCHIVE_MEDIA_TYPE },
        body,
      },
    );
    return await this.#jsonResponse(response) as ArtifactBlobReceipt;
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
    throw new Error("staged formal market input identity changed before command submission");
  }
}

function assertStagedProjectArchiveIdentity(
  staged: ArtifactBlobReceipt,
  archive: ArtifactRef,
): void {
  if (
    staged.sha256 !== archive.sha256
    || staged.byte_size !== archive.byte_size
    || staged.storage_uri !== archive.storage_uri
  ) {
    throw new Error("staged project archive identity changed before command submission");
  }
}

function canonicalJsonArtifactRef(
  body: string,
  originKind: "fixture" | "service_generated" = "service_generated",
  sourceRef?: string,
): ArtifactRef {
  const bytes = new TextEncoder().encode(body);
  if (bytes.byteLength < 2 || bytes.byteLength > 5 * 1024 * 1024) {
    throw new Error("formal market input must contain between 2 and 5242880 UTF-8 bytes");
  }
  JSON.parse(body);
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  return {
    artifact_id: stableIdentityUuid(`${sha256}:formal-market-input-artifact`),
    sha256,
    media_type: "application/json",
    byte_size: bytes.byteLength,
    storage_uri: `cas://sha256/${sha256}`,
    producing_revision_id: null,
    producing_run_id: null,
    provenance: {
      origin_kind: originKind,
      source_ref: sourceRef
        ?? stableIdentityUuid(`${sha256}:formal-market-input-provenance`),
    },
  };
}

function projectArchiveArtifact(body: Uint8Array<ArrayBuffer>, commandId: string): ArtifactRef {
  if (body.byteLength < 1 || body.byteLength > PROJECT_ARCHIVE_MAX_BYTES) {
    throw new Error("project archive must contain between 1 and 10737418240 bytes");
  }
  const sha256 = createHash("sha256").update(body).digest("hex");
  return {
    artifact_id: stableIdentityUuid(`${sha256}:project-archive-artifact`),
    sha256,
    media_type: PROJECT_ARCHIVE_MEDIA_TYPE,
    byte_size: body.byteLength,
    storage_uri: `cas://sha256/${sha256}`,
    producing_revision_id: null,
    producing_run_id: null,
    provenance: {
      origin_kind: "user_upload",
      source_ref: stableIdentityUuid(`${commandId}:project-archive-upload`),
    },
  };
}

function parseJsonArtifact(bytes: Uint8Array, label: string): unknown {
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new Error(`verified ${label} artifact is not valid JSON`);
  }
}

function assertEmbeddedArtifact(
  embedded: unknown,
  verified: unknown,
  label: string,
): void {
  if (canonicalJsonValue(embedded) !== canonicalJsonValue(verified)) {
    throw new Error(`embedded ${label} does not match verified artifact bytes`);
  }
}

function canonicalJsonValue(value: unknown): string {
  if (value === undefined) {
    return "null";
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJsonValue(item)).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value).sort(([left], [right]) =>
      left.localeCompare(right)
    );
    return `{${entries.map(([key, item]) =>
      `${JSON.stringify(key)}:${canonicalJsonValue(item)}`
    ).join(",")}}`;
  }
  return JSON.stringify(value);
}

function assertValidCommand<T>(
  result: { valid: true; value: T } | { valid: false; errors: string[] },
  commandType: string,
): T {
  if (!result.valid) {
    throw new Error(`${commandType} command contract violation: ${result.errors.join("; ")}`);
  }
  return result.value;
}

function assertReadContract<T>(
  result: { valid: true; value: T } | { valid: false; errors: string[] },
  label: string,
): T {
  if (!result.valid) {
    throw new Error(
      `quant-domain ${label} contract violation: ${result.errors.join("; ")}`,
    );
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

async function dataImportPreviewError(
  response: Response,
): Promise<DataImportPreviewHttpError> {
  const record = asRecord(
    JSON.parse(await response.text()),
    "data import preview error response",
  );
  const details = Array.isArray(record.details)
    ? record.details.map((detail) => {
        const item = asRecord(detail, "data import preview row error");
        return {
          row_number: item.row_number as number,
          field: item.field as string,
          message: item.message as string,
        };
      })
    : [];
  return new DataImportPreviewHttpError(
    response.status,
    typeof record.error === "string" ? record.error : `http_${response.status}`,
    details,
  );
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
