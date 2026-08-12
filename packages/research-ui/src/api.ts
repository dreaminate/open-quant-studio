import type {
  Activity,
  ArchiveLogSelection,
  BuiltInStrategy,
  ChatEvent,
  Context,
  DataImportPreview,
  DataSnapshot,
  DataSnapshotMapping,
  DataSnapshotMarket,
  DataSnapshotPriceBasis,
  DataSnapshotSourceArtifact,
  DataSnapshotSourceFormat,
  ForwardTest,
  LocalDataImportFile,
  LogListFilters,
  LogPage,
  Project,
  Revision,
  RevisionComparison,
  RevisionFile,
  RenderedStrategyNotebook,
  RunDetail,
  RunReportReadModel,
  RunSummary,
  Variant,
} from "./types.js";

const PROJECT_ARCHIVE_MEDIA_TYPE = "application/vnd.open-quant-studio.project-archive+zip";

type ForwardTestCommandReceipt = {
  event: {
    payload: {
      forward_test_id: string;
    };
  };
};

export class ResearchApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly body: unknown;

  constructor(status: number, code: string, body: unknown) {
    super(`${code} (${status})`);
    this.name = "ResearchApiError";
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

type ListEnvelope<T> = { [key: string]: unknown; items?: T[] };

function listFrom<T>(value: unknown, key: string): T[] {
  if (Array.isArray(value)) return value as T[];
  if (typeof value === "object" && value !== null) {
    const candidate = (value as Record<string, unknown>)[key];
    if (Array.isArray(candidate)) return candidate as T[];
    const items = (value as ListEnvelope<T>).items;
    if (Array.isArray(items)) return items;
  }
  throw new Error(`${key} response has an invalid shape`);
}

function encode(value: string): string {
  return encodeURIComponent(value);
}

function dataImportSourceFormat(fileName: string): DataSnapshotSourceFormat {
  const extension = fileName.split(".").at(-1)?.toLowerCase();
  if (extension !== "csv" && extension !== "parquet") {
    throw new Error("Data import file must use .csv or .parquet");
  }
  return extension;
}

export interface CreateChildRevisionRequest {
  projectId: string;
  activityId: string;
  sessionId?: string;
  workbenchId?: string;
  variantId: string;
  baseRevisionId: string;
  expectedRevisionId: string;
  message: string;
  files: Array<Pick<RevisionFile, "path" | "body">>;
  removedPaths?: string[];
}

export interface CreateVariantRequest {
  projectId: string;
  activityId: string;
  sessionId?: string;
  workbenchId?: string;
  baseRevisionId: string;
  message: string;
}

export interface CreateMergeCandidateRequest {
  projectId: string;
  activityId: string;
  variantId: string;
  candidateRevisionId: string;
  message: string;
  files: Array<Pick<RevisionFile, "path" | "body">>;
}

export interface CreateDataSnapshotRequest {
  source: DataSnapshotSourceArtifact;
  source_format: DataSnapshotSourceFormat;
  file_name: string;
  mapping: DataSnapshotMapping;
  market: DataSnapshotMarket;
  timezone: string;
  price_basis: DataSnapshotPriceBasis;
  cutoff: string;
}

export interface ResearchApi {
  getContext(): Promise<Context>;
  listProjects(): Promise<Project[]>;
  listActivities(projectId: string): Promise<Activity[]>;
  listBuiltInStrategies(): Promise<BuiltInStrategy[]>;
  renderStrategyNotebook(strategyId: string, source: string): Promise<RenderedStrategyNotebook>;
  getRevisionHead(projectId: string): Promise<{ project_id: string; head_revision_id: string }>;
  listVariants(projectId: string): Promise<Variant[]>;
  getRevision(projectId: string, revisionId: string): Promise<Revision>;
  compareRevisions(projectId: string, leftRevisionId: string, rightRevisionId: string): Promise<RevisionComparison>;
  listRuns(projectId: string, activityId?: string): Promise<RunSummary[]>;
  getRun(runId: string, projectId?: string): Promise<RunDetail>;
  getRunReport(runId: string, projectId?: string): Promise<RunReportReadModel>;
  downloadRunReport(runId: string, format: "json" | "html"): Promise<Blob>;
  listLogs(filters?: LogListFilters): Promise<LogPage>;
  deleteLogs(logIds: string[]): Promise<unknown>;
  createStrategyVariant(request: CreateVariantRequest): Promise<unknown>;
  createChildRevision(request: CreateChildRevisionRequest): Promise<unknown>;
  createMergeCandidate(request: CreateMergeCandidateRequest): Promise<unknown>;
  previewDataImport(file: File): Promise<DataImportPreview>;
  listLocalDataImports(): Promise<LocalDataImportFile[]>;
  previewLocalDataImport(fileName: string): Promise<DataImportPreview>;
  listDataSnapshots(): Promise<DataSnapshot[]>;
  getDataSnapshot(snapshotId: string): Promise<DataSnapshot>;
  createDataSnapshot(request: CreateDataSnapshotRequest): Promise<unknown>;
  requestFormalRun(candidateRevisionId: string, dataSnapshotId?: string): Promise<unknown>;
  requestForwardTest(runId: string): Promise<{ forward_test_id: string }>;
  getForwardTest(forwardTestId: string): Promise<ForwardTest>;
  downloadProjectArchive(projectId: string, selectedLogs: ArchiveLogSelection): Promise<Blob>;
  importProjectArchive(archive: File): Promise<unknown>;
  promoteRun(runId: string): Promise<unknown>;
  prompt(text: string): Promise<unknown>;
  subscribeChatEvents(
    projectId: string,
    listener: (event: ChatEvent) => void,
    onConnectionChange?: (connected: boolean) => void,
  ): () => void;
}

export function createResearchApi(basePath = "/api/v1"): ResearchApi {
  const root = basePath.replace(/\/$/, "");

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${root}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    });
    if (!response.ok) {
      const text = await response.text();
      let body: unknown = undefined;
      if (text) {
        try {
          body = JSON.parse(text) as unknown;
        } catch {
          body = text;
        }
      }
      const details = typeof body === "object" && body !== null ? body as Record<string, unknown> : {};
      const code = typeof details.error === "string" ? details.error : `http_${response.status}`;
      throw new ResearchApiError(response.status, code, body);
    }
    const text = await response.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  async function requestText(path: string): Promise<string> {
    const response = await fetch(`${root}${path}`, { headers: { Accept: "text/plain" } });
    if (!response.ok) {
      let body: unknown;
      try {
        body = await response.json() as unknown;
      } catch {
        body = undefined;
      }
      const details = typeof body === "object" && body !== null ? body as Record<string, unknown> : {};
      const code = typeof details.error === "string" ? details.error : `http_${response.status}`;
      throw new ResearchApiError(response.status, code, body);
    }
    return response.text();
  }

  async function requestBlob(path: string, accept = PROJECT_ARCHIVE_MEDIA_TYPE): Promise<Blob> {
    const response = await fetch(`${root}${path}`, { headers: { Accept: accept } });
    if (!response.ok) {
      const text = await response.text();
      let body: unknown = undefined;
      if (text) {
        try {
          body = JSON.parse(text) as unknown;
        } catch {
          body = text;
        }
      }
      const details = typeof body === "object" && body !== null ? body as Record<string, unknown> : {};
      const code = typeof details.error === "string" ? details.error : `http_${response.status}`;
      throw new ResearchApiError(response.status, code, body);
    }
    return response.blob();
  }

  return {
    async getContext() {
      return request<Context>("/context");
    },
    async listProjects() {
      return request<unknown>("/projects").then((value) => listFrom<Project>(value, "projects"));
    },
    async listActivities(projectId) {
      void projectId;
      return request<unknown>("/activities").then((value) => listFrom<Activity>(value, "activities"));
    },
    async listBuiltInStrategies() {
      return request<unknown>("/strategies").then((value) =>
        listFrom<BuiltInStrategy>(value, "strategies")
      );
    },
    async renderStrategyNotebook(strategyId, source) {
      return request<RenderedStrategyNotebook>(
        `/strategies/${encode(strategyId)}/notebook`,
        { method: "POST", body: JSON.stringify({ source }) },
      );
    },
    async getRevisionHead(projectId) {
      void projectId;
      return request<{ project_id: string; head_revision_id: string }>("/revision-head");
    },
    async listVariants(projectId) {
      void projectId;
      return request<unknown>("/variants").then((value) => listFrom<Variant>(value, "variants"));
    },
    async getRevision(projectId, revisionId) {
      void projectId;
      const revision = await request<Revision>(`/revisions/${encode(revisionId)}`);
      const files = await Promise.all(revision.files.map(async (file) => {
        if (typeof file.body === "string") return file;
        const artifactId = typeof file.artifact_id === "string" ? file.artifact_id : undefined;
        if (!artifactId) return file;
        return { ...file, body: await requestText(`/revisions/${encode(revisionId)}/files/${encode(artifactId)}/content`) };
      }));
      return { ...revision, files };
    },
    async compareRevisions(projectId, leftRevisionId, rightRevisionId) {
      void projectId;
      return request<RevisionComparison>(`/revision-comparison?leftRevisionId=${encode(leftRevisionId)}&rightRevisionId=${encode(rightRevisionId)}`);
    },
    async listRuns(projectId, activityId) {
      void projectId;
      void activityId;
      return request<unknown>("/runs").then((value) => listFrom<RunSummary>(value, "runs"));
    },
    async getRun(runId, projectId) {
      void projectId;
      return request<RunDetail>(`/runs/${encode(runId)}`);
    },
    async getRunReport(runId, projectId) {
      void projectId;
      return request<RunReportReadModel>(`/runs/${encode(runId)}/report`);
    },
    async downloadRunReport(runId, format) {
      const accept = format === "json"
        ? "application/vnd.open-quant-studio.run-report+json"
        : "application/vnd.open-quant-studio.run-report+html";
      return requestBlob(`/runs/${encode(runId)}/report.${format}`, accept);
    },
    async listLogs(filters = {}) {
      const search = new URLSearchParams();
      if (filters.runId !== undefined) search.set("run_id", filters.runId);
      if (filters.activityId !== undefined) search.set("activity_id", filters.activityId);
      if (filters.sessionId !== undefined) search.set("session_id", filters.sessionId);
      if (filters.level !== undefined) search.set("level", filters.level);
      if (filters.priority !== undefined) search.set("priority", filters.priority);
      if (filters.query !== undefined) search.set("query", filters.query);
      if (filters.afterLogSeq !== undefined) search.set("after_log_seq", String(filters.afterLogSeq));
      if (filters.limit !== undefined) search.set("limit", String(filters.limit));
      const query = search.toString();
      return request<LogPage>(`/logs${query ? `?${query}` : ""}`);
    },
    async deleteLogs(logIds) {
      return request<unknown>("/logs/delete", {
        method: "POST",
        body: JSON.stringify({ log_ids: logIds }),
      });
    },
    async createStrategyVariant(requestBody) {
      void requestBody;
      return request<unknown>("/variants", { method: "POST", body: "{}" });
    },
    async createChildRevision(requestBody) {
      return request<unknown>(`/variants/${encode(requestBody.variantId)}/revisions`, {
        method: "POST",
        body: JSON.stringify({
          message: requestBody.message,
          files: requestBody.files,
          ...(requestBody.removedPaths === undefined
            ? {}
            : { removed_paths: requestBody.removedPaths }),
        }),
      });
    },
    async createMergeCandidate(requestBody) {
      return request<unknown>(`/variants/${encode(requestBody.variantId)}/merge-candidates`, { method: "POST", body: JSON.stringify({ message: requestBody.message, files: requestBody.files }) });
    },
    async previewDataImport(file) {
      const sourceFormat = dataImportSourceFormat(file.name);
      return request<DataImportPreview>(`/data-imports/preview?file_name=${encode(file.name)}&source_format=${sourceFormat}`, {
        method: "POST",
        body: file,
        headers: {
          "Content-Type": sourceFormat === "csv"
            ? "text/csv"
            : "application/vnd.apache.parquet",
        },
      });
    },
    async listLocalDataImports() {
      return request<unknown>("/data-imports/local-files").then((value) =>
        listFrom<LocalDataImportFile>(value, "files")
      );
    },
    async previewLocalDataImport(fileName) {
      return request<DataImportPreview>("/data-imports/local-preview", {
        method: "POST",
        body: JSON.stringify({ file_name: fileName }),
      });
    },
    async listDataSnapshots() {
      return request<unknown>("/data-snapshots").then((value) =>
        listFrom<DataSnapshot>(value, "snapshots")
      );
    },
    async getDataSnapshot(snapshotId) {
      return request<DataSnapshot>(`/data-snapshots/${encode(snapshotId)}`);
    },
    async createDataSnapshot(requestBody) {
      return request<unknown>("/data-snapshots", {
        method: "POST",
        body: JSON.stringify(requestBody),
      });
    },
    async requestFormalRun(candidateRevisionId, dataSnapshotId) {
      return request<unknown>(`/revisions/${encode(candidateRevisionId)}/runs`, {
        method: "POST",
        body: JSON.stringify(
          dataSnapshotId === undefined ? {} : { data_snapshot_id: dataSnapshotId },
        ),
      });
    },
    async requestForwardTest(runId) {
      const receipt = await request<ForwardTestCommandReceipt>(`/runs/${encode(runId)}/forward-tests`, { method: "POST", body: "{}" });
      return { forward_test_id: receipt.event.payload.forward_test_id };
    },
    async getForwardTest(forwardTestId) {
      return request<ForwardTest>(`/forward-tests/${encode(forwardTestId)}`);
    },
    async downloadProjectArchive(projectId, selectedLogs) {
      return requestBlob(`/projects/${encode(projectId)}/archive?selected_logs=${encode(selectedLogs)}`);
    },
    async importProjectArchive(archive) {
      return request<unknown>("/project-archives/import", {
        method: "POST",
        body: archive,
        headers: { "Content-Type": PROJECT_ARCHIVE_MEDIA_TYPE },
      });
    },
    async promoteRun(runId) {
      return request<unknown>(`/runs/${encode(runId)}/promote`, { method: "POST", body: "{}" });
    },
    async prompt(text) {
      return request<unknown>("/chat/prompt", { method: "POST", body: JSON.stringify({ text }) });
    },
    subscribeChatEvents(projectId, listener, onConnectionChange) {
      void projectId;
      const source = new EventSource(`${root}/chat/events`);
      const onMessage = (event: MessageEvent<string>) => {
        try {
          const value = JSON.parse(event.data) as unknown;
          if (typeof value === "object" && value !== null) listener(value as ChatEvent);
        } catch {
          listener({ type: "text", text: event.data });
        }
      };
      source.addEventListener("message", onMessage);
      source.addEventListener("domain.event", onMessage);
      source.addEventListener("pi.chat", onMessage);
      source.addEventListener("open", () => onConnectionChange?.(true));
      source.addEventListener("error", () => onConnectionChange?.(false));
      return () => {
        source.close();
        onConnectionChange?.(false);
      };
    },
  };
}
