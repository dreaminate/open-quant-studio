import type {
  Activity,
  ChatEvent,
  Context,
  LogEntry,
  Project,
  Revision,
  RevisionComparison,
  RevisionFile,
  RunDetail,
  RunSummary,
  Variant,
} from "./types.js";

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

export interface ResearchApi {
  getContext(): Promise<Context>;
  listProjects(): Promise<Project[]>;
  listActivities(projectId: string): Promise<Activity[]>;
  getRevisionHead(projectId: string): Promise<{ project_id: string; head_revision_id: string }>;
  listVariants(projectId: string): Promise<Variant[]>;
  getRevision(projectId: string, revisionId: string): Promise<Revision>;
  compareRevisions(projectId: string, leftRevisionId: string, rightRevisionId: string): Promise<RevisionComparison>;
  listRuns(projectId: string, activityId?: string): Promise<RunSummary[]>;
  getRun(runId: string, projectId?: string): Promise<RunDetail>;
  listLogs(projectId: string, runId: string): Promise<LogEntry[]>;
  createStrategyVariant(request: CreateVariantRequest): Promise<unknown>;
  createChildRevision(request: CreateChildRevisionRequest): Promise<unknown>;
  createMergeCandidate(request: CreateMergeCandidateRequest): Promise<unknown>;
  requestFormalRun(candidateRevisionId: string): Promise<unknown>;
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
    async listLogs(projectId, runId) {
      void projectId;
      const detail = await request<RunDetail>(`/runs/${encode(runId)}`);
      return Array.isArray(detail.logs) ? detail.logs as LogEntry[] : [];
    },
    async createStrategyVariant(requestBody) {
      void requestBody;
      return request<unknown>("/variants", { method: "POST", body: "{}" });
    },
    async createChildRevision(requestBody) {
      return request<unknown>(`/variants/${encode(requestBody.variantId)}/revisions`, { method: "POST", body: JSON.stringify({ message: requestBody.message, files: requestBody.files }) });
    },
    async createMergeCandidate(requestBody) {
      return request<unknown>(`/variants/${encode(requestBody.variantId)}/merge-candidates`, { method: "POST", body: JSON.stringify({ message: requestBody.message, files: requestBody.files }) });
    },
    async requestFormalRun(candidateRevisionId) {
      return request<unknown>(`/revisions/${encode(candidateRevisionId)}/runs`, { method: "POST", body: "{}" });
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
