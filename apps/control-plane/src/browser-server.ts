import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { extname, join } from "node:path";

import type {
  ActivityListReadModel,
  ArtifactMetadataReadModel,
  DataImportPreviewReadModel,
  DataSnapshotListReadModel,
  DataSnapshotMapping,
  DataSnapshotMarket,
  DataSnapshotPriceBasis,
  DataSnapshotReadModel,
  DataSnapshotSourceArtifact,
  DataSnapshotSourceFormat,
  DiagnosticLogListReadModel,
  FormalRunDetailReadModel,
  FormalRunListReadModel,
  ForwardTestReadModel,
  ProjectListReadModel,
  RunReportReadModel,
} from "@open-quant-studio/contracts";

import { QuantDomainHttpError, type CommandReceipt } from "./domain-session-client.js";
import {
  DataImportPreviewHttpError,
  PROJECT_ARCHIVE_MAX_BYTES,
  PROJECT_ARCHIVE_MEDIA_TYPE,
} from "./domain-revision-client.js";
import type {
  DataSnapshotCreateRequest,
  FormalRunRequest,
  ForwardTestRequest,
  MergeCreateRequest,
  DiagnosticLogDeleteRequest,
  DiagnosticLogListFilters,
  ProjectArchiveImportRequest,
  ProjectArchiveLogSelection,
  BuiltInStrategy,
  RenderedStrategyNotebook,
  LocalDataImportFile,
  ProjectRevisionHead,
  RevisionCreateRequest,
  RevisionDetail,
  RevisionFileInput,
  RevisionPromoteRequest,
  StrategyVariantSummary,
  VariantCreateRequest,
} from "./domain-revision-client.js";
import type { PiChatEvent } from "./pi-session-adapter.js";
import { canonicalJson } from "./pi-session-adapter.js";

const JSON_BODY_LIMIT = 1024 * 1024;
const MAX_FILES = 32;
const MAX_TEXT_BYTES = 64 * 1024;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const M4_FULL_FIXTURE_INPUT_SHA256 = "520d7c4b4faecbd63b21fa761a741f76e8aa961c09af244348441236ea854699";
const M4_FORMAL_FIXTURE_SOURCE_REF = "76767676-7676-4676-8676-767676767676";
const trustedM4FormalRunFixtures = new WeakSet<object>();

export interface M4FormalRunFixture {
  readonly marketInputJson: string;
  readonly strategyInputJson: string;
  readonly dataSnapshotId: string;
  readonly dataSnapshotSha256: string;
  readonly parametersSha256: string;
  readonly costModelSha256: string;
  readonly environmentLockSha256: string;
  readonly priceBasis: "raw" | "qfq" | "hfq";
  readonly cutoff: string;
  readonly timezone: string;
  readonly sampleStart: string;
  readonly sampleEnd: string;
  readonly randomSeed: number;
  readonly marketInputOriginKind: "fixture";
  readonly marketInputSourceRef: string;
}

export async function loadM4FormalRunFixture(
  fixturePath: string,
): Promise<M4FormalRunFixture> {
  const document = JSON.parse(await readFile(fixturePath, "utf8")) as unknown;
  const record = fixtureRecord(document);
  const provenance = fixtureRecord(record.provenance);
  if (
    record.spec_id !== "oqs.m3.a-share-long-short.v1"
    || record.schema_version !== 1
    || record.status !== "formal_engine_contract"
    || provenance.kind !== "synthetic"
  ) {
    throw new Error("M4 Formal Run fixture identity is invalid");
  }
  const strategyInputJson = canonicalJson(record.input);
  if (sha256(strategyInputJson) !== M4_FULL_FIXTURE_INPUT_SHA256) {
    throw new Error("M4 Formal Run fixture input identity is invalid");
  }
  const marketInput = { ...fixtureRecord(record.input) };
  delete marketInput.intents;
  const marketInputJson = canonicalJson(marketInput);
  const dataSnapshotSha256 = sha256(marketInputJson);
  const fixture: M4FormalRunFixture = Object.freeze({
    marketInputJson,
    strategyInputJson,
    dataSnapshotId: "77777777-7777-4777-8777-777777777777",
    dataSnapshotSha256,
    parametersSha256: sha256("{}"),
    costModelSha256: sha256("m3-fixture-costs"),
    environmentLockSha256: sha256("test-lock"),
    priceBasis: "raw",
    cutoff: "2026-01-01T00:00:00Z",
    timezone: "Asia/Shanghai",
    sampleStart: "2026-01-02T00:00:00Z",
    sampleEnd: "2026-01-07T23:59:59Z",
    randomSeed: 0,
    marketInputOriginKind: "fixture",
    marketInputSourceRef: M4_FORMAL_FIXTURE_SOURCE_REF,
  });
  trustedM4FormalRunFixtures.add(fixture);
  return fixture;
}

interface BrowserSessionStatus {
  sessionId: string;
  projectId: string;
  activityId: string;
  activeWorkbenchId: string;
  isStreaming: boolean;
}

interface BrowserPiAdapter {
  prompt(text: string): Promise<void>;
  subscribe(listener: (event: PiChatEvent) => void): () => void;
}

export interface BrowserSessionRegistry {
  status(sessionId: string): BrowserSessionStatus | undefined;
  get(sessionId: string): BrowserPiAdapter | undefined;
}

export interface BrowserRevisionClient {
  listProjects(): Promise<ProjectListReadModel>;
  listActivities(projectId: string): Promise<ActivityListReadModel>;
  listBuiltInStrategies(): Promise<BuiltInStrategy[]>;
  renderStrategyNotebook(
    strategyId: string,
    source: string,
  ): Promise<RenderedStrategyNotebook>;
  getProjectRevisionHead(projectId: string): Promise<ProjectRevisionHead>;
  listVariants(projectId: string): Promise<StrategyVariantSummary[]>;
  getRevision(projectId: string, revisionId: string): Promise<RevisionDetail>;
  compareRevisions(
    projectId: string,
    leftRevisionId: string,
    rightRevisionId: string,
  ): Promise<unknown>;
  listRuns(projectId: string, activityId: string): Promise<FormalRunListReadModel>;
  previewDataImport(
    projectId: string,
    fileName: string,
    sourceFormat: DataSnapshotSourceFormat,
    body: Uint8Array<ArrayBuffer>,
  ): Promise<DataImportPreviewReadModel>;
  listLocalDataImports(projectId: string): Promise<LocalDataImportFile[]>;
  previewLocalDataImport(
    projectId: string,
    fileName: string,
  ): Promise<DataImportPreviewReadModel>;
  listDataSnapshots(projectId: string): Promise<DataSnapshotListReadModel>;
  getDataSnapshot(projectId: string, snapshotId: string): Promise<DataSnapshotReadModel>;
  getDataSnapshotMarketInput(
    projectId: string,
    snapshot: DataSnapshotReadModel,
  ): Promise<string>;
  listLogs(
    projectId: string,
    filters: DiagnosticLogListFilters,
  ): Promise<DiagnosticLogListReadModel>;
  getRun(projectId: string, runId: string): Promise<FormalRunDetailReadModel>;
  getRunReport(projectId: string, runId: string): Promise<RunReportReadModel>;
  getForwardTest(projectId: string, forwardTestId: string): Promise<ForwardTestReadModel>;
  getProjectArchive(
    projectId: string,
    selectedLogs: ProjectArchiveLogSelection,
  ): Promise<Uint8Array>;
  getArtifact?(
    projectId: string,
    artifactId: string,
  ): Promise<ArtifactMetadataReadModel>;
  getArtifactContent?(
    projectId: string,
    artifact: ArtifactMetadataReadModel,
  ): Promise<Uint8Array>;
  createStrategyVariant(request: VariantCreateRequest): Promise<CommandReceipt>;
  createRevisionChild(request: RevisionCreateRequest): Promise<CommandReceipt>;
  createMergeCandidate(request: MergeCreateRequest): Promise<CommandReceipt>;
  requestFormalRun(request: FormalRunRequest): Promise<CommandReceipt>;
  createDataSnapshot(request: DataSnapshotCreateRequest): Promise<CommandReceipt>;
  requestForwardTest(request: ForwardTestRequest): Promise<CommandReceipt>;
  deleteLogs(request: DiagnosticLogDeleteRequest): Promise<CommandReceipt>;
  importProjectArchive(request: ProjectArchiveImportRequest): Promise<CommandReceipt>;
  promoteRevision(request: RevisionPromoteRequest): Promise<CommandReceipt>;
}

export interface OqsBrowserServerOptions {
  activeSessionId: string;
  registry: BrowserSessionRegistry;
  revisionClient: BrowserRevisionClient;
  formalRunFixture?: M4FormalRunFixture;
  webRoot?: string;
}

type ResolvedBrowserServerOptions = Omit<
  OqsBrowserServerOptions,
  "formalRunFixture"
> & { formalRunFixture: M4FormalRunFixture };

interface BrowserActor {
  projectId: string;
  activityId: string;
  sessionId: string;
  workbenchId: string;
}

class PublicHttpError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
  }
}

export function createOqsBrowserServer(options: OqsBrowserServerOptions): Server {
  const formalRunFixture = options.formalRunFixture;
  if (formalRunFixture === undefined) {
    throw new Error("formal Run fixture is required");
  }
  if (!trustedM4FormalRunFixtures.has(formalRunFixture)) {
    throw new Error("formal Run fixture must be loaded from the pinned fixture");
  }
  const resolvedOptions = { ...options, formalRunFixture };
  return createServer((request, response) => {
    void routeRequest(resolvedOptions, request, response).catch((error: unknown) => {
      if (response.headersSent) {
        response.destroy();
        return;
      }
      if (error instanceof DataImportPreviewHttpError) {
        sendJson(response, error.status, { error: error.code, details: error.details });
        return;
      }
      if (error instanceof QuantDomainHttpError) {
        sendError(response, error.status, error.code ?? "upstream_error");
        return;
      }
      if (error instanceof PublicHttpError) {
        sendError(response, error.status, error.code);
        return;
      }
      sendError(response, 500, "internal_error");
    });
  });
}

async function routeRequest(
  options: ResolvedBrowserServerOptions,
  request: IncomingMessage,
  response: ServerResponse,
): Promise<void> {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  if (request.method === "GET" && options.webRoot !== undefined) {
    const assetName = url.pathname.match(/^\/assets\/([A-Za-z0-9][A-Za-z0-9._-]*)$/)?.[1];
    if (url.pathname === "/" || url.pathname === "/index.html") {
      await sendWebFile(response, join(options.webRoot, "index.html"), "text/html; charset=utf-8", false);
      return;
    }
    if (assetName !== undefined) {
      await sendWebFile(
        response,
        join(options.webRoot, "assets", assetName),
        webAssetMediaType(assetName),
        true,
      );
      return;
    }
  }
  const actor = activeActor(options);

  if (request.method === "GET" && url.pathname === "/api/v1/context") {
    assertNoQuery(url);
    const status = options.registry.status(options.activeSessionId);
    if (status === undefined) {
      throw new PublicHttpError(503, "active_session_unavailable");
    }
    sendJson(response, 200, {
      sessionId: actor.sessionId,
      projectId: actor.projectId,
      activityId: actor.activityId,
      activeWorkbenchId: actor.workbenchId,
      isStreaming: status.isStreaming,
    });
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/v1/projects") {
    assertNoQuery(url);
    const payload = await options.revisionClient.listProjects();
    sendJson(response, 200, {
      projects: payload.projects.filter((project) => project.project_id === actor.projectId),
    });
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/v1/activities") {
    assertNoQuery(url);
    const payload = await options.revisionClient.listActivities(actor.projectId);
    sendJson(response, 200, {
      activities: payload.activities.filter(
        (activity) => activity.activity_id === actor.activityId,
      ),
    });
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/v1/strategies") {
    assertNoQuery(url);
    sendJson(response, 200, {
      strategies: await options.revisionClient.listBuiltInStrategies(),
    });
    return;
  }

  const strategyNotebookMatch = url.pathname.match(
    /^\/api\/v1\/strategies\/([^/]+)\/notebook$/,
  );
  if (request.method === "POST" && strategyNotebookMatch !== null) {
    assertNoQuery(url);
    const body = exactObject(
      await readJsonBody(request),
      ["source"],
      ["source"],
    );
    sendJson(
      response,
      200,
      await options.revisionClient.renderStrategyNotebook(
        strategyNotebookMatch[1]!,
        boundedText(body.source, "source"),
      ),
    );
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/v1/revision-head") {
    assertNoQuery(url);
    sendJson(
      response,
      200,
      await scopedProjectHead(options.revisionClient, actor),
    );
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/v1/variants") {
    assertNoQuery(url);
    const variants = await options.revisionClient.listVariants(actor.projectId);
    sendJson(response, 200, {
      variants: variants.filter((variant) => variant.activity_id === actor.activityId),
    });
    return;
  }

  const revisionMatch = url.pathname.match(/^\/api\/v1\/revisions\/([^/]+)$/);
  if (request.method === "GET" && revisionMatch !== null) {
    assertNoQuery(url);
    const revisionId = assertResourceId(revisionMatch[1]);
    sendJson(
      response,
      200,
      await scopedRevision(options.revisionClient, actor, revisionId),
    );
    return;
  }

  const artifactContentMatch = url.pathname.match(
    /^\/api\/v1\/revisions\/([^/]+)\/files\/([^/]+)\/content$/,
  );
  if (request.method === "GET" && artifactContentMatch !== null) {
    assertNoQuery(url);
    const revisionId = assertResourceId(artifactContentMatch[1]);
    const artifactId = assertResourceId(artifactContentMatch[2]);
    const revision = await scopedRevision(options.revisionClient, actor, revisionId);
    if (
      options.revisionClient.getArtifact === undefined
      || options.revisionClient.getArtifactContent === undefined
      || !revision.files.some((file) => file.artifact_id === artifactId)
    ) {
      throw new PublicHttpError(404, "resource_not_found");
    }
    const artifact = await options.revisionClient.getArtifact(actor.projectId, artifactId);
    if (
      !artifact.revision_paths.some((path) => path.revision_id === revisionId)
    ) {
      throw new PublicHttpError(404, "resource_not_found");
    }
    const content = await options.revisionClient.getArtifactContent(
      actor.projectId,
      artifact,
    );
    response.writeHead(200, {
      "Content-Type": artifact.media_type,
      "Content-Length": content.byteLength,
      "Cache-Control": "no-store",
    });
    response.end(content);
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/v1/revision-comparison") {
    assertOnlyQuery(url, ["leftRevisionId", "rightRevisionId"]);
    const leftRevisionId = assertResourceId(url.searchParams.get("leftRevisionId"));
    const rightRevisionId = assertResourceId(url.searchParams.get("rightRevisionId"));
    await Promise.all([
      scopedRevision(options.revisionClient, actor, leftRevisionId),
      scopedRevision(options.revisionClient, actor, rightRevisionId),
    ]);
    sendJson(
      response,
      200,
      await options.revisionClient.compareRevisions(
        actor.projectId,
        leftRevisionId,
        rightRevisionId,
      ),
    );
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/v1/runs") {
    assertNoQuery(url);
    const payload = await options.revisionClient.listRuns(
      actor.projectId,
      actor.activityId,
    );
    sendJson(response, 200, {
      runs: payload.runs.filter(
        (run) => run.project_id === actor.projectId && run.activity_id === actor.activityId,
      ),
    });
    return;
  }

  if (request.method === "POST" && url.pathname === "/api/v1/data-imports/preview") {
    assertOnlyQuery(url, ["file_name", "source_format"]);
    const fileName = boundedText(url.searchParams.get("file_name"), "file_name");
    const sourceFormat = dataSnapshotSourceFormat(url.searchParams.get("source_format"));
    const body = await readDataImportBody(request, sourceFormat);
    sendJson(
      response,
      200,
      await options.revisionClient.previewDataImport(
        actor.projectId,
        fileName,
        sourceFormat,
        body,
      ),
    );
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/v1/data-imports/local-files") {
    assertNoQuery(url);
    sendJson(response, 200, {
      files: await options.revisionClient.listLocalDataImports(actor.projectId),
    });
    return;
  }

  if (request.method === "POST" && url.pathname === "/api/v1/data-imports/local-preview") {
    assertNoQuery(url);
    const body = exactObject(await readJsonBody(request), ["file_name"], ["file_name"]);
    sendJson(
      response,
      200,
      await options.revisionClient.previewLocalDataImport(
        actor.projectId,
        boundedText(body.file_name, "file_name"),
      ),
    );
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/v1/data-snapshots") {
    assertNoQuery(url);
    const payload = await options.revisionClient.listDataSnapshots(actor.projectId);
    sendJson(response, 200, {
      snapshots: payload.snapshots.filter(
        (snapshot) => snapshot.project_id === actor.projectId,
      ),
    });
    return;
  }

  if (request.method === "POST" && url.pathname === "/api/v1/data-snapshots") {
    assertNoQuery(url);
    const body = exactObject(
      await readJsonBody(request),
      [
        "source",
        "source_format",
        "file_name",
        "mapping",
        "market",
        "timezone",
        "price_basis",
        "cutoff",
      ],
      [
        "source",
        "source_format",
        "file_name",
        "mapping",
        "market",
        "timezone",
        "price_basis",
        "cutoff",
      ],
    );
    const sourceFormat = dataSnapshotSourceFormat(body.source_format);
    sendJson(
      response,
      200,
      await options.revisionClient.createDataSnapshot({
        ...actor,
        source: dataSnapshotSource(body.source, sourceFormat),
        sourceFormat,
        fileName: boundedText(body.file_name, "file_name"),
        mapping: dataSnapshotMapping(body.mapping),
        market: dataSnapshotMarket(body.market),
        timezone: boundedText(body.timezone, "timezone"),
        priceBasis: dataSnapshotPriceBasis(body.price_basis),
        cutoff: boundedText(body.cutoff, "cutoff"),
      }),
    );
    return;
  }

  const dataSnapshotMatch = url.pathname.match(/^\/api\/v1\/data-snapshots\/([^/]+)$/);
  if (request.method === "GET" && dataSnapshotMatch !== null) {
    assertNoQuery(url);
    sendJson(
      response,
      200,
      await scopedDataSnapshot(
        options.revisionClient,
        actor,
        assertResourceId(dataSnapshotMatch[1]),
      ),
    );
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/v1/logs") {
    sendJson(
      response,
      200,
      await options.revisionClient.listLogs(
        actor.projectId,
        diagnosticLogListFilters(url),
      ),
    );
    return;
  }

  const runMatch = url.pathname.match(/^\/api\/v1\/runs\/([^/]+)$/);
  if (request.method === "GET" && runMatch !== null) {
    assertNoQuery(url);
    const run = await scopedRun(
      options.revisionClient,
      actor,
      assertResourceId(runMatch[1]),
    );
    sendJson(response, 200, run);
    return;
  }

  const runReportMatch = url.pathname.match(/^\/api\/v1\/runs\/([^/]+)\/report(?:\.(json|html))?$/);
  if (request.method === "GET" && runReportMatch !== null) {
    assertNoQuery(url);
    const runId = assertResourceId(runReportMatch[1]);
    const report = await scopedRunReport(
      options.revisionClient,
      actor,
      runId,
    );
    const format = runReportMatch[2];
    if (format === undefined) {
      sendJson(response, 200, report);
      return;
    }
    const pointer = format === "json" ? report.json_artifact : report.html_artifact;
    if (
      options.revisionClient.getArtifact === undefined
      || options.revisionClient.getArtifactContent === undefined
    ) {
      throw new PublicHttpError(404, "resource_not_found");
    }
    const artifact = await options.revisionClient.getArtifact(actor.projectId, pointer.artifact_id);
    if (
      artifact.project_id !== actor.projectId
      || artifact.artifact_id !== pointer.artifact_id
      || artifact.sha256 !== pointer.sha256
      || artifact.media_type !== pointer.media_type
      || artifact.byte_size !== pointer.byte_size
    ) {
      throw new PublicHttpError(404, "resource_not_found");
    }
    const content = await options.revisionClient.getArtifactContent(actor.projectId, artifact);
    response.writeHead(200, {
      "Content-Type": pointer.media_type,
      "Content-Length": content.byteLength,
      "Content-Disposition": `attachment; filename="${runId}.report.${format}"`,
      "Cache-Control": "no-store",
    });
    response.end(content);
    return;
  }

  const forwardTestMatch = url.pathname.match(/^\/api\/v1\/forward-tests\/([^/]+)$/);
  if (request.method === "GET" && forwardTestMatch !== null) {
    assertNoQuery(url);
    sendJson(
      response,
      200,
      await scopedForwardTest(
        options.revisionClient,
        actor,
        assertResourceId(forwardTestMatch[1]),
      ),
    );
    return;
  }

  const archiveMatch = url.pathname.match(/^\/api\/v1\/projects\/([^/]+)\/archive$/);
  if (request.method === "GET" && archiveMatch !== null) {
    const projectId = assertResourceId(archiveMatch[1]);
    if (projectId !== actor.projectId) {
      throw new PublicHttpError(404, "resource_not_found");
    }
    const content = await options.revisionClient.getProjectArchive(
      actor.projectId,
      archiveLogSelection(url),
    );
    response.writeHead(200, {
      "Content-Type": PROJECT_ARCHIVE_MEDIA_TYPE,
      "Content-Length": content.byteLength,
      "Content-Disposition": `attachment; filename="${projectId}.oqs.zip"`,
      "Cache-Control": "no-store",
    });
    response.end(content);
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/v1/chat/events") {
    assertNoQuery(url);
    const adapter = activeAdapter(options);
    response.writeHead(200, {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-store",
      Connection: "keep-alive",
    });
    response.write(": open-quant-studio pi chat\n\n");
    const unsubscribe = adapter.subscribe((event) => {
      response.write(`event: pi.chat\ndata: ${JSON.stringify(event)}\n\n`);
    });
    request.once("close", unsubscribe);
    return;
  }

  if (request.method === "POST" && url.pathname === "/api/v1/chat/prompt") {
    assertNoQuery(url);
    const body = exactObject(await readJsonBody(request), ["text"], ["text"]);
    const text = boundedText(body.text, "text");
    await activeAdapter(options).prompt(text);
    response.writeHead(204, { "Cache-Control": "no-store" });
    response.end();
    return;
  }

  if (request.method === "POST" && url.pathname === "/api/v1/variants") {
    assertNoQuery(url);
    exactObject(await readJsonBody(request), [], []);
    const head = await scopedProjectHead(options.revisionClient, actor);
    sendJson(
      response,
      200,
      await options.revisionClient.createStrategyVariant({
        ...actor,
        baseRevisionId: head.head_revision_id,
      }),
    );
    return;
  }

  const childMatch = url.pathname.match(
    /^\/api\/v1\/variants\/([^/]+)\/revisions$/,
  );
  if (request.method === "POST" && childMatch !== null) {
    assertNoQuery(url);
    const variantId = assertResourceId(childMatch[1]);
    const body = exactObject(
      await readJsonBody(request),
      ["message", "files", "removed_paths"],
      ["message", "files"],
    );
    const variant = await scopedVariant(options.revisionClient, actor, variantId);
    sendJson(
      response,
      200,
      await options.revisionClient.createRevisionChild({
        ...actor,
        variantId,
        baseRevisionId: variant.head_revision_id,
        expectedRevisionId: variant.head_revision_id,
        message: boundedText(body.message, "message"),
        files: revisionFiles(body.files),
        removedPaths: body.removed_paths === undefined
          ? undefined
          : revisionRemovedPaths(body.removed_paths),
      }),
    );
    return;
  }

  const mergeMatch = url.pathname.match(
    /^\/api\/v1\/variants\/([^/]+)\/merge-candidates$/,
  );
  if (request.method === "POST" && mergeMatch !== null) {
    assertNoQuery(url);
    const variantId = assertResourceId(mergeMatch[1]);
    const body = exactObject(
      await readJsonBody(request),
      ["message", "files"],
      ["message", "files"],
    );
    const files = revisionFiles(body.files);
    const [head, variant] = await Promise.all([
      scopedProjectHead(options.revisionClient, actor),
      scopedVariant(options.revisionClient, actor, variantId),
    ]);
    const variantHead = await scopedRevision(
      options.revisionClient,
      actor,
      variant.head_revision_id,
    );
    const expectedPaths = variantHead.files.map((file) => file.path).sort();
    const submittedPaths = files.map((file) => file.path).sort();
    if (JSON.stringify(expectedPaths) !== JSON.stringify(submittedPaths)) {
      throw new PublicHttpError(422, "incomplete_revision_tree");
    }
    sendJson(
      response,
      200,
      await options.revisionClient.createMergeCandidate({
        ...actor,
        expectedRevisionId: head.head_revision_id,
        variantId,
        baseRevisionId: variant.head_revision_id,
        message: boundedText(body.message, "message"),
        files,
      }),
    );
    return;
  }

  const formalMatch = url.pathname.match(/^\/api\/v1\/revisions\/([^/]+)\/runs$/);
  if (request.method === "POST" && formalMatch !== null) {
    assertNoQuery(url);
    const body = exactObject(
      await readJsonBody(request),
      ["data_snapshot_id"],
      [],
    );
    const candidateRevisionId = assertResourceId(formalMatch[1]);
    const candidate = await scopedRevision(
      options.revisionClient,
      actor,
      candidateRevisionId,
    );
    if (candidate.variant_id === null) {
      throw new PublicHttpError(409, "revision_is_not_a_merge_candidate");
    }
    const dataSnapshotId = body.data_snapshot_id === undefined
      ? undefined
      : assertResourceId(body.data_snapshot_id as string);
    let formalRunRequest: FormalRunRequest;
    if (dataSnapshotId === undefined) {
      formalRunRequest = {
        ...actor,
        candidateRevisionId,
        variantId: candidate.variant_id,
        strategyTreeOid: candidate.git_tree_oid,
        ...options.formalRunFixture,
      };
    } else {
      const snapshot = await scopedDataSnapshot(
        options.revisionClient,
        actor,
        dataSnapshotId,
      );
      const marketInputJson = await options.revisionClient.getDataSnapshotMarketInput(
        actor.projectId,
        snapshot,
      );
      if (sha256(marketInputJson) !== snapshot.market_input_sha256) {
        throw new Error("selected data snapshot market input identity changed");
      }
      formalRunRequest = {
        ...actor,
        candidateRevisionId,
        variantId: candidate.variant_id,
        strategyTreeOid: candidate.git_tree_oid,
        marketInputJson,
        dataSnapshotId: snapshot.snapshot_id,
        dataSnapshotSha256: snapshot.sha256,
        parametersSha256: options.formalRunFixture.parametersSha256,
        costModelSha256: options.formalRunFixture.costModelSha256,
        environmentLockSha256: options.formalRunFixture.environmentLockSha256,
        priceBasis: snapshot.price_basis,
        cutoff: snapshot.cutoff,
        timezone: snapshot.timezone,
        sampleStart: snapshot.sample_start,
        sampleEnd: snapshot.sample_end,
        randomSeed: options.formalRunFixture.randomSeed,
        marketInputOriginKind: "service_generated",
        marketInputSourceRef: snapshot.market_input_artifact_id,
      };
    }
    sendJson(
      response,
      200,
      await options.revisionClient.requestFormalRun(formalRunRequest),
    );
    return;
  }

  const forwardRequestMatch = url.pathname.match(
    /^\/api\/v1\/runs\/([^/]+)\/forward-tests$/,
  );
  if (request.method === "POST" && forwardRequestMatch !== null) {
    assertNoQuery(url);
    exactObject(await readJsonBody(request), [], []);
    const sourceRun = await scopedRun(
      options.revisionClient,
      actor,
      assertResourceId(forwardRequestMatch[1]),
    );
    sendJson(
      response,
      200,
      await options.revisionClient.requestForwardTest({
        ...actor,
        sourceRunId: sourceRun.run.run_id,
        sourceRevisionId: sourceRun.run.candidate_revision_id,
        variantId: sourceRun.run.variant_id,
      }),
    );
    return;
  }

  if (request.method === "POST" && url.pathname === "/api/v1/project-archives/import") {
    assertNoQuery(url);
    const archive = await readProjectArchiveBody(request);
    sendJson(
      response,
      200,
      await options.revisionClient.importProjectArchive({
        ...actor,
        archive,
      }),
    );
    return;
  }

  if (request.method === "POST" && url.pathname === "/api/v1/logs/delete") {
    assertNoQuery(url);
    const body = exactObject(
      await readJsonBody(request),
      ["log_ids"],
      ["log_ids"],
    );
    sendJson(
      response,
      200,
      await options.revisionClient.deleteLogs({
        ...actor,
        logIds: diagnosticLogIds(body.log_ids),
      }),
    );
    return;
  }

  const promoteMatch = url.pathname.match(/^\/api\/v1\/runs\/([^/]+)\/promote$/);
  if (request.method === "POST" && promoteMatch !== null) {
    assertNoQuery(url);
    exactObject(await readJsonBody(request), [], []);
    const run = await scopedRun(
      options.revisionClient,
      actor,
      assertResourceId(promoteMatch[1]),
    );
    if (run.run.status !== "succeeded" || run.validation.outcome !== "passed") {
      throw new PublicHttpError(409, "run_not_promotable");
    }
    const head = await scopedProjectHead(options.revisionClient, actor);
    sendJson(
      response,
      200,
      await options.revisionClient.promoteRevision({
        ...actor,
        expectedRevisionId: head.head_revision_id,
        variantId: run.run.variant_id,
        candidateRevisionId: run.run.candidate_revision_id,
        validationId: run.validation.validation_id,
      }),
    );
    return;
  }

  throw new PublicHttpError(404, "not_found");
}

async function sendWebFile(
  response: ServerResponse,
  path: string,
  mediaType: string,
  immutable: boolean,
): Promise<void> {
  let content: Uint8Array;
  try {
    content = await readFile(path);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      throw new PublicHttpError(404, "not_found");
    }
    throw error;
  }
  response.writeHead(200, {
    "Content-Type": mediaType,
    "Content-Length": content.byteLength,
    "Cache-Control": immutable ? "public, max-age=31536000, immutable" : "no-store",
  });
  response.end(content);
}

function webAssetMediaType(assetName: string): string {
  switch (extname(assetName)) {
    case ".css":
      return "text/css; charset=utf-8";
    case ".js":
      return "text/javascript; charset=utf-8";
    case ".svg":
      return "image/svg+xml";
    case ".png":
      return "image/png";
    case ".woff2":
      return "font/woff2";
    default:
      throw new PublicHttpError(404, "not_found");
  }
}

function activeActor(options: OqsBrowserServerOptions): BrowserActor {
  const status = options.registry.status(options.activeSessionId);
  if (status === undefined) {
    throw new PublicHttpError(503, "active_session_unavailable");
  }
  return {
    projectId: status.projectId,
    activityId: status.activityId,
    sessionId: options.activeSessionId,
    workbenchId: status.activeWorkbenchId,
  };
}

function activeAdapter(options: OqsBrowserServerOptions): BrowserPiAdapter {
  const adapter = options.registry.get(options.activeSessionId);
  if (adapter === undefined) {
    throw new PublicHttpError(503, "active_session_unavailable");
  }
  return adapter;
}

async function scopedProjectHead(
  client: BrowserRevisionClient,
  actor: BrowserActor,
): Promise<ProjectRevisionHead> {
  const head = await client.getProjectRevisionHead(actor.projectId);
  await scopedRevision(client, actor, head.head_revision_id);
  return head;
}

async function scopedVariant(
  client: BrowserRevisionClient,
  actor: BrowserActor,
  variantId: string,
): Promise<StrategyVariantSummary> {
  const variants = await client.listVariants(actor.projectId);
  const variant = variants.find(
    (item) => item.variant_id === variantId && item.activity_id === actor.activityId,
  );
  if (variant === undefined) {
    throw new PublicHttpError(404, "resource_not_found");
  }
  return variant;
}

async function scopedRevision(
  client: BrowserRevisionClient,
  actor: BrowserActor,
  revisionId: string,
): Promise<RevisionDetail> {
  const revision = await client.getRevision(actor.projectId, revisionId);
  if (
    revision.project_id !== actor.projectId
    || revision.activity_id !== actor.activityId
  ) {
    throw new PublicHttpError(404, "resource_not_found");
  }
  return revision;
}

async function scopedRun(
  client: BrowserRevisionClient,
  actor: BrowserActor,
  runId: string,
): Promise<FormalRunDetailReadModel> {
  const run = await client.getRun(actor.projectId, runId);
  if (
    run.run.project_id !== actor.projectId
    || run.run.activity_id !== actor.activityId
  ) {
    throw new PublicHttpError(404, "resource_not_found");
  }
  return run;
}

async function scopedRunReport(
  client: BrowserRevisionClient,
  actor: BrowserActor,
  runId: string,
): Promise<RunReportReadModel> {
  const report = await client.getRunReport(actor.projectId, runId);
  if (
    report.report.run.project_id !== actor.projectId
    || report.report.run.activity_id !== actor.activityId
    || report.report.run.run_id !== runId
  ) {
    throw new PublicHttpError(404, "resource_not_found");
  }
  return report;
}

async function scopedForwardTest(
  client: BrowserRevisionClient,
  actor: BrowserActor,
  forwardTestId: string,
): Promise<ForwardTestReadModel> {
  const forwardTest = await client.getForwardTest(actor.projectId, forwardTestId);
  if (
    forwardTest.project_id !== actor.projectId
    || forwardTest.activity_id !== actor.activityId
    || forwardTest.forward_test_id !== forwardTestId
  ) {
    throw new PublicHttpError(404, "resource_not_found");
  }
  return forwardTest;
}

async function scopedDataSnapshot(
  client: BrowserRevisionClient,
  actor: BrowserActor,
  snapshotId: string,
): Promise<DataSnapshotReadModel> {
  const snapshot = await client.getDataSnapshot(actor.projectId, snapshotId);
  if (
    snapshot.project_id !== actor.projectId
    || snapshot.snapshot_id !== snapshotId
  ) {
    throw new PublicHttpError(404, "resource_not_found");
  }
  return snapshot;
}

async function readJsonBody(request: IncomingMessage): Promise<unknown> {
  if (!request.headers["content-type"]?.startsWith("application/json")) {
    throw new PublicHttpError(415, "json_required");
  }
  const chunks: Uint8Array[] = [];
  let byteLength = 0;
  for await (const chunk of request) {
    const bytes = typeof chunk === "string" ? new TextEncoder().encode(chunk) : chunk;
    byteLength += bytes.byteLength;
    if (byteLength > JSON_BODY_LIMIT) {
      throw new PublicHttpError(413, "request_too_large");
    }
    chunks.push(bytes);
  }
  const body = new Uint8Array(byteLength);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(body));
  } catch {
    throw new PublicHttpError(422, "invalid_request");
  }
}

async function readProjectArchiveBody(
  request: IncomingMessage,
): Promise<Uint8Array<ArrayBuffer>> {
  if (!request.headers["content-type"]?.startsWith(PROJECT_ARCHIVE_MEDIA_TYPE)) {
    throw new PublicHttpError(415, "project_archive_required");
  }
  const chunks: Uint8Array[] = [];
  let byteLength = 0;
  for await (const chunk of request) {
    const bytes = typeof chunk === "string" ? new TextEncoder().encode(chunk) : chunk;
    byteLength += bytes.byteLength;
    if (byteLength > PROJECT_ARCHIVE_MAX_BYTES) {
      throw new PublicHttpError(413, "request_too_large");
    }
    chunks.push(bytes);
  }
  const archive = new Uint8Array(byteLength);
  let offset = 0;
  for (const chunk of chunks) {
    archive.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return archive;
}

async function readDataImportBody(
  request: IncomingMessage,
  sourceFormat: DataSnapshotSourceFormat,
): Promise<Uint8Array<ArrayBuffer>> {
  const expectedMediaType = sourceFormat === "csv"
    ? "text/csv"
    : "application/vnd.apache.parquet";
  if (!request.headers["content-type"]?.startsWith(expectedMediaType)) {
    throw new PublicHttpError(415, "data_import_media_type_required");
  }
  const chunks: Uint8Array[] = [];
  let byteLength = 0;
  for await (const chunk of request) {
    const bytes = typeof chunk === "string" ? new TextEncoder().encode(chunk) : chunk;
    byteLength += bytes.byteLength;
    if (byteLength > 1024 * 1024 * 1024) {
      throw new PublicHttpError(413, "request_too_large");
    }
    chunks.push(bytes);
  }
  if (byteLength < 1) {
    throw new PublicHttpError(422, "invalid_request");
  }
  const body = new Uint8Array(byteLength);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

function exactObject(
  value: unknown,
  allowedKeys: string[],
  requiredKeys: string[],
): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new PublicHttpError(422, "invalid_request");
  }
  const record = value as Record<string, unknown>;
  if (
    Object.keys(record).some((key) => !allowedKeys.includes(key))
    || requiredKeys.some((key) => !(key in record))
  ) {
    throw new PublicHttpError(422, "invalid_request");
  }
  return record;
}

function revisionFiles(value: unknown): RevisionFileInput[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > MAX_FILES) {
    throw new PublicHttpError(422, "invalid_request");
  }
  const files = value.map((item) => {
    const file = exactObject(item, ["path", "body"], ["path", "body"]);
    return {
      path: boundedText(file.path, "path"),
      body: boundedText(file.body, "body"),
    };
  });
  if (new Set(files.map((file) => file.path)).size !== files.length) {
    throw new PublicHttpError(422, "invalid_request");
  }
  return files;
}

function revisionRemovedPaths(value: unknown): string[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > MAX_FILES) {
    throw new PublicHttpError(422, "invalid_request");
  }
  const paths = value.map((path) => boundedText(path, "removed_path"));
  if (new Set(paths).size !== paths.length) {
    throw new PublicHttpError(422, "invalid_request");
  }
  return paths;
}

function diagnosticLogIds(value: unknown): string[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 10_000) {
    throw new PublicHttpError(422, "invalid_request");
  }
  const logIds = value.map((logId) => {
    if (typeof logId !== "string") {
      throw new PublicHttpError(422, "invalid_request");
    }
    return assertResourceId(logId);
  });
  if (new Set(logIds).size !== logIds.length) {
    throw new PublicHttpError(422, "invalid_request");
  }
  return logIds;
}

function dataSnapshotSourceFormat(value: unknown): DataSnapshotSourceFormat {
  if (value !== "csv" && value !== "parquet") {
    throw new PublicHttpError(422, "invalid_request");
  }
  return value;
}

function dataSnapshotMarket(value: unknown): DataSnapshotMarket {
  if (value !== "a_share_daily" && value !== "crypto_linear_perp") {
    throw new PublicHttpError(422, "invalid_request");
  }
  return value;
}

function dataSnapshotPriceBasis(value: unknown): DataSnapshotPriceBasis {
  if (value !== "raw" && value !== "qfq" && value !== "hfq") {
    throw new PublicHttpError(422, "invalid_request");
  }
  return value;
}

function dataSnapshotMapping(value: unknown): DataSnapshotMapping {
  const record = exactObject(
    value,
    ["timestamp", "symbol", "open", "high", "low", "close", "volume"],
    ["timestamp", "symbol", "open", "high", "low", "close", "volume"],
  );
  return {
    timestamp: boundedText(record.timestamp, "timestamp"),
    symbol: boundedText(record.symbol, "symbol"),
    open: boundedText(record.open, "open"),
    high: boundedText(record.high, "high"),
    low: boundedText(record.low, "low"),
    close: boundedText(record.close, "close"),
    volume: boundedText(record.volume, "volume"),
  };
}

function dataSnapshotSource(
  value: unknown,
  sourceFormat: DataSnapshotSourceFormat,
): DataSnapshotSourceArtifact {
  const record = exactObject(
    value,
    [
      "artifact_id",
      "sha256",
      "media_type",
      "byte_size",
      "storage_uri",
      "producing_revision_id",
      "producing_run_id",
      "provenance",
    ],
    [
      "artifact_id",
      "sha256",
      "media_type",
      "byte_size",
      "storage_uri",
      "producing_revision_id",
      "producing_run_id",
      "provenance",
    ],
  );
  const provenance = exactObject(
    record.provenance,
    ["origin_kind", "source_ref"],
    ["origin_kind", "source_ref"],
  );
  return {
    artifact_id: record.artifact_id as string,
    sha256: record.sha256 as string,
    media_type: sourceFormat === "csv" ? "text/csv" : "application/vnd.apache.parquet",
    byte_size: record.byte_size as number,
    storage_uri: record.storage_uri as string,
    producing_revision_id: record.producing_revision_id as null,
    producing_run_id: record.producing_run_id as null,
    provenance: {
      origin_kind: provenance.origin_kind as "user_upload",
      source_ref: provenance.source_ref as string,
    },
  };
}

function diagnosticLogListFilters(url: URL): DiagnosticLogListFilters {
  assertAllowedQuery(url, [
    "run_id",
    "activity_id",
    "session_id",
    "level",
    "priority",
    "query",
    "after_log_seq",
    "limit",
  ]);
  const level = url.searchParams.get("level");
  if (level !== null && level !== "debug" && level !== "info" && level !== "warn" && level !== "error") {
    throw new PublicHttpError(422, "invalid_request");
  }
  const priority = url.searchParams.get("priority");
  if (priority !== null && priority !== "p1" && priority !== "p2" && priority !== "p3" && priority !== "p4") {
    throw new PublicHttpError(422, "invalid_request");
  }
  return {
    runId: url.searchParams.get("run_id") ?? undefined,
    activityId: url.searchParams.get("activity_id") ?? undefined,
    sessionId: url.searchParams.get("session_id") ?? undefined,
    level: level ?? undefined,
    priority: priority ?? undefined,
    query: url.searchParams.get("query") ?? undefined,
    afterLogSeq: optionalIntegerQuery(url, "after_log_seq"),
    limit: optionalIntegerQuery(url, "limit"),
  };
}

function boundedText(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length < 1) {
    throw new PublicHttpError(422, "invalid_request");
  }
  const byteLength = new TextEncoder().encode(value).byteLength;
  if (byteLength > MAX_TEXT_BYTES) {
    throw new PublicHttpError(422, `${label}_too_large`);
  }
  return value;
}

function assertResourceId(value: string | null | undefined): string {
  if (value === null || value === undefined || !UUID_PATTERN.test(value)) {
    throw new PublicHttpError(422, "invalid_resource_id");
  }
  return value;
}

function assertNoQuery(url: URL): void {
  if (url.search !== "") {
    throw new PublicHttpError(422, "invalid_request");
  }
}

function assertOnlyQuery(url: URL, names: string[]): void {
  const keys = [...url.searchParams.keys()];
  if (
    keys.length !== names.length
    || keys.some((key) => !names.includes(key))
    || names.some((name) => url.searchParams.getAll(name).length !== 1)
  ) {
    throw new PublicHttpError(422, "invalid_request");
  }
}

function assertAllowedQuery(url: URL, names: string[]): void {
  const keys = [...url.searchParams.keys()];
  if (
    keys.some((key) => !names.includes(key))
    || keys.some((key) => url.searchParams.getAll(key).length !== 1)
  ) {
    throw new PublicHttpError(422, "invalid_request");
  }
}

function optionalIntegerQuery(url: URL, name: string): number | undefined {
  const value = url.searchParams.get(name);
  if (value === null) {
    return undefined;
  }
  const integer = Number(value);
  if (!Number.isInteger(integer)) {
    throw new PublicHttpError(422, "invalid_request");
  }
  return integer;
}

function archiveLogSelection(url: URL): ProjectArchiveLogSelection {
  if (url.search === "") {
    return "full";
  }
  assertOnlyQuery(url, ["selected_logs"]);
  const selectedLogs = url.searchParams.get("selected_logs");
  if (
    selectedLogs !== "full"
    && selectedLogs !== "warn_error"
    && selectedLogs !== "none"
  ) {
    throw new PublicHttpError(422, "invalid_request");
  }
  return selectedLogs;
}

function sendJson(response: ServerResponse, status: number, value: unknown): void {
  const body = JSON.stringify(value);
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  });
  response.end(body);
}

function sendError(response: ServerResponse, status: number, code: string): void {
  sendJson(response, status, { error: code });
}

function fixtureRecord(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("M4 Formal Run fixture has an invalid shape");
  }
  return value as Record<string, unknown>;
}

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
