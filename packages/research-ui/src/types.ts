export type WorkbenchId =
  | "canvas"
  | "chat"
  | "code"
  | "compare"
  | "backtest"
  | "forward-test"
  | "run-detail"
  | "data"
  | "logs"
  | "settings";

export interface Project {
  project_id: string;
  name?: string;
  created_at: string;
  [key: string]: unknown;
}

export interface Activity {
  activity_id: string;
  project_id: string;
  name?: string;
  created_at: string;
  [key: string]: unknown;
}

export interface Context {
  sessionId?: string;
  projectId?: string;
  activityId?: string;
  activeWorkbenchId?: string;
  isStreaming?: boolean;
  [key: string]: unknown;
}

export interface Variant {
  variant_id: string;
  project_id?: string;
  activity_id?: string;
  base_revision_id?: string;
  head_revision_id: string;
  version?: number;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface RevisionFile {
  path: string;
  body: string;
  sha256?: string;
  git_blob_oid?: string;
  [key: string]: unknown;
}

export interface Revision {
  revision_id: string;
  project_id?: string;
  activity_id?: string;
  variant_id?: string;
  base_revision_id?: string | null;
  parent_revision_id?: string | null;
  git_commit_oid?: string;
  git_tree_oid?: string;
  message?: string;
  files: RevisionFile[];
  created_at?: string;
  [key: string]: unknown;
}

export interface ComparisonChange {
  path: string;
  left_sha256?: string | null;
  right_sha256?: string | null;
  left_body?: string | null;
  right_body?: string | null;
  status?: string;
  [key: string]: unknown;
}

export interface RevisionComparison {
  project_id?: string;
  left_revision_id: string;
  right_revision_id: string;
  changes: ComparisonChange[];
  [key: string]: unknown;
}

export interface RunSummary {
  run_id: string;
  project_id?: string;
  activity_id?: string;
  variant_id?: string;
  candidate_revision_id?: string;
  status?: string;
  created_at?: string;
  finished_at?: string;
  [key: string]: unknown;
}

export interface RunDetail {
  run?: RunSummary;
  run_spec?: Record<string, unknown>;
  validation?: Record<string, unknown>;
  artifacts?: Record<string, unknown>;
  manifest?: Record<string, unknown>;
  engine_result?: Record<string, unknown>;
  intent_tape?: unknown[];
  logs?: LogEntry[];
  [key: string]: unknown;
}

export interface LogEntry {
  run_id?: string;
  level?: string;
  priority?: string;
  event_code?: string;
  message?: string;
  created_at?: string;
  timestamp?: string;
  [key: string]: unknown;
}

export interface ChatEvent {
  type?: string;
  text?: string;
  delta?: string;
  message?: string;
  status?: string;
  [key: string]: unknown;
}
