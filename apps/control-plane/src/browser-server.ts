import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { extname, join } from "node:path";

import type {
  ActivityListReadModel,
  ArtifactMetadataReadModel,
  FormalRunDetailReadModel,
  FormalRunListReadModel,
  ProjectListReadModel,
} from "@open-quant-studio/contracts";

import { QuantDomainHttpError, type CommandReceipt } from "./domain-session-client.js";
import type {
  FormalRunRequest,
  MergeCreateRequest,
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
const M4_FORMAL_INPUT_SHA256 = "520d7c4b4faecbd63b21fa761a741f76e8aa961c09af244348441236ea854699";
const M4_FORMAL_FIXTURE_SOURCE_REF = "76767676-7676-4676-8676-767676767676";
const trustedM4FormalRunFixtures = new WeakSet<object>();

export interface M4FormalRunFixture {
  readonly engineInputJson: string;
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
  readonly engineInputOriginKind: "fixture";
  readonly engineInputSourceRef: string;
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
  const engineInputJson = canonicalJson(record.input);
  const dataSnapshotSha256 = sha256(engineInputJson);
  if (dataSnapshotSha256 !== M4_FORMAL_INPUT_SHA256) {
    throw new Error("M4 Formal Run fixture input identity is invalid");
  }
  const fixture: M4FormalRunFixture = Object.freeze({
    engineInputJson,
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
    engineInputOriginKind: "fixture",
    engineInputSourceRef: M4_FORMAL_FIXTURE_SOURCE_REF,
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
  getProjectRevisionHead(projectId: string): Promise<ProjectRevisionHead>;
  listVariants(projectId: string): Promise<StrategyVariantSummary[]>;
  getRevision(projectId: string, revisionId: string): Promise<RevisionDetail>;
  compareRevisions(
    projectId: string,
    leftRevisionId: string,
    rightRevisionId: string,
  ): Promise<unknown>;
  listRuns(projectId: string, activityId: string): Promise<FormalRunListReadModel>;
  getRun(projectId: string, runId: string): Promise<FormalRunDetailReadModel>;
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
      ["message", "files"],
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
    exactObject(await readJsonBody(request), [], []);
    const candidateRevisionId = assertResourceId(formalMatch[1]);
    const candidate = await scopedRevision(
      options.revisionClient,
      actor,
      candidateRevisionId,
    );
    if (candidate.variant_id === null) {
      throw new PublicHttpError(409, "revision_is_not_a_merge_candidate");
    }
    sendJson(
      response,
      200,
      await options.revisionClient.requestFormalRun({
        ...actor,
        candidateRevisionId,
        variantId: candidate.variant_id,
        strategyTreeOid: candidate.git_tree_oid,
        ...options.formalRunFixture,
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
