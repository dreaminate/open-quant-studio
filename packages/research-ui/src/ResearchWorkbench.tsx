import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Background, Controls, ReactFlow, useEdgesState, useNodesState, type Edge, type Node } from "@xyflow/react";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import "@xyflow/react/dist/style.css";
import { createResearchApi, ResearchApiError, type ResearchApi } from "./api.js";
import type {
  Activity,
  ArchiveLogSelection,
  BuiltInStrategy,
  ChatEvent,
  ComparisonChange,
  Context,
  DataImportPreview,
  DataImportRowError,
  DataSnapshot,
  DataSnapshotCorporateAction,
  DataSnapshotMapping,
  DataSnapshotMarket,
  DataSnapshotPriceBasis,
  DataSnapshotExecutionProfile,
  ForwardTest,
  LocalDataImportFile,
  LogEntry,
  LogLevel,
  LogListFilters,
  LogPriority,
  Project,
  Revision,
  RevisionComparison,
  RenderedStrategyNotebook,
  RunDetail,
  ReviewAttestation,
  RunReportReadModel,
  RunSummary,
  Variant,
  WorkbenchId,
} from "./types.js";

export interface ResearchWorkbenchProps {
  api?: ResearchApi;
}

type CanvasNodeData = {
  kind: "Session" | "Strategy" | "Run" | "Artifact";
  title: string;
  label: string;
  subtitle: string;
  detail: string;
};

type LogFilterControls = Pick<LogListFilters, "level" | "priority" | "query">;

const NAV_ITEMS: Array<{ id: WorkbenchId; label: string; description: string }> = [
  { id: "canvas", label: "Canvas", description: "Project graph" },
  { id: "chat", label: "Pi Chat", description: "Bounded session" },
  { id: "code", label: "Code", description: "Strategy.py" },
  { id: "compare", label: "Compare", description: "Revision diff" },
  { id: "backtest", label: "Backtest", description: "Formal action" },
  { id: "forward-test", label: "Forward Test", description: "Historical replay" },
  { id: "run-detail", label: "Run Detail", description: "Immutable artifact" },
  { id: "data", label: "Data", description: "CSV / Parquet" },
  { id: "logs", label: "Logs", description: "Filter and delete" },
  { id: "settings", label: "Settings", description: "Archive export" },
];

const NAV_GROUPS: Array<{ label: string; ids: WorkbenchId[] }> = [
  { label: "ORCHESTRATE", ids: ["canvas", "chat"] },
  { label: "BUILD", ids: ["code", "compare", "data"] },
  { label: "VERIFY", ids: ["backtest", "forward-test", "run-detail", "logs", "settings"] },
];

const DATA_MAPPING_FIELDS: Array<{ key: keyof DataSnapshotMapping; label: string }> = [
  { key: "timestamp", label: "Timestamp" },
  { key: "symbol", label: "Symbol" },
  { key: "open", label: "Open" },
  { key: "high", label: "High" },
  { key: "low", label: "Low" },
  { key: "close", label: "Close" },
  { key: "volume", label: "Volume" },
  { key: "trading_status", label: "Trading status (optional)" },
  { key: "price_limit_state", label: "Price-limit state (optional)" },
];

const emptyNodes: Node<CanvasNodeData>[] = [];
const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

function shortId(value: string | undefined): string {
  return value ? value.slice(0, 8) : "—";
}

function timestamp(value: string | undefined): string {
  if (!value) return "—";
  return dateTimeFormatter.format(new Date(value));
}

function renderValue(value: unknown): string {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean"
    ? String(value)
    : JSON.stringify(value, null, 2);
}

function engineRecordKey(label: string, value: unknown): string {
  const record = recordValue(value);
  const identity = record?.trade_id
    ?? record?.event_id
    ?? (record?.intent_id === undefined ? undefined : `${record.intent_id}:${record.session_seq ?? ""}`)
    ?? (record?.session_seq === undefined ? undefined : record.session_seq);
  return `${label}:${String(identity ?? JSON.stringify(value))}`;
}

function logRecordKey(log: LogEntry): string {
  return String(
    log.log_id
      ?? log.event_id
      ?? `${log.timestamp ?? log.created_at ?? ""}:${log.event_code ?? ""}:${log.message ?? ""}`,
  );
}

function getRunId(value: unknown): string | undefined {
  if (typeof value === "string") return value;
  if (typeof value === "object" && value !== null) {
    const record = value as Record<string, unknown>;
    const run = record.run;
    if (typeof run === "object" && run !== null && typeof (run as Record<string, unknown>).run_id === "string") return (run as Record<string, unknown>).run_id as string;
    if (typeof record.run_id === "string") return record.run_id;
    for (const nested of [record.payload, record.event]) {
      const nestedId = getRunId(nested);
      if (nestedId) return nestedId;
    }
  }
  return undefined;
}

function getRevisionId(value: unknown): string | undefined {
  if (typeof value === "object" && value !== null) {
    const record = value as Record<string, unknown>;
    const candidates = [record.revision_id, record.candidate_revision_id];
    for (const candidate of candidates) if (typeof candidate === "string") return candidate;
    for (const nested of [record.payload, record.event]) {
      const nestedId = getRevisionId(nested);
      if (nestedId) return nestedId;
    }
  }
  return undefined;
}

function getSnapshotId(value: unknown): string | undefined {
  if (typeof value === "object" && value !== null) {
    const record = value as Record<string, unknown>;
    if (typeof record.snapshot_id === "string") return record.snapshot_id;
    for (const nested of [record.payload, record.event]) {
      const nestedId = getSnapshotId(nested);
      if (nestedId) return nestedId;
    }
  }
  return undefined;
}

function rowErrors(value: unknown): DataImportRowError[] {
  if (!(value instanceof ResearchApiError)) return [];
  const body = value.body as { details?: DataImportRowError[] } | undefined;
  return body?.details ?? [];
}

function getCodeFromRevision(revision: Revision | undefined): string {
  const file = revision?.files.find((entry) => entry.path === "strategy.py") ?? revision?.files[0];
  return file?.body ?? "";
}

function notebookStrategyId(body: string): string {
  const notebook = JSON.parse(body) as {
    metadata: { oqs: { strategy_id: string } };
  };
  return notebook.metadata.oqs.strategy_id;
}

function canvasNodes(context: Context | undefined, variant: Variant | undefined, run: RunSummary | undefined, revision: Revision | undefined): Node<CanvasNodeData>[] {
  return [
    {
      id: "session",
      type: "default",
      position: { x: 40, y: 120 },
      data: { kind: "Session", title: "Pi Session", label: "Pi Session", subtitle: shortId(context?.sessionId), detail: "One bounded AgentLoop session shared by workbenches." },
    },
    {
      id: "strategy",
      type: "default",
      position: { x: 300, y: 60 },
      data: { kind: "Strategy", title: "Strategy Variant", label: "Strategy Variant", subtitle: shortId(variant?.variant_id), detail: `Head revision ${shortId(variant?.head_revision_id)} · ${revision?.files.length ?? 0} files` },
    },
    {
      id: "run",
      type: "default",
      position: { x: 590, y: 120 },
      data: { kind: "Run", title: "Formal Run", label: "Formal Run", subtitle: shortId(run?.run_id), detail: run?.status ?? "No selected Run" },
    },
    {
      id: "artifact",
      type: "default",
      position: { x: 860, y: 60 },
      data: { kind: "Artifact", title: "Run Artifact", label: "Run Artifact", subtitle: run ? "immutable" : "awaiting Run", detail: "Engine output, manifest, gates, and logs." },
    },
  ];
}

function canvasEdges(): Edge[] {
  return [
    { id: "session-strategy", source: "session", target: "strategy", label: "edits" },
    { id: "strategy-run", source: "strategy", target: "run", label: "formal" },
    { id: "run-artifact", source: "run", target: "artifact", label: "produces" },
  ];
}

function ErrorNotice({ error }: { error: string | undefined }) {
  return error ? <div className="oqs-notice oqs-notice-error" role="alert">{error}</div> : null;
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return <div className="oqs-empty"><strong>{title}</strong><span>{body}</span></div>;
}

type ResearchOverviewProps = {
  projectLabel: string;
  activityLabel: string;
  context: Context | undefined;
  variant: Variant | undefined;
  revision: Revision | undefined;
  selectedStrategy: BuiltInStrategy | undefined;
  snapshot: DataSnapshot | undefined;
  runs: RunSummary[];
  selectedRun: RunSummary | undefined;
  onNavigate: (workbench: WorkbenchId) => void;
};

function OverviewState({ label, value, detail, tone = "pending" }: { label: string; value: string; detail: string; tone?: "ready" | "pending" | "active" }) {
  return <div className={`oqs-overview-state is-${tone}`}>
    <span className="oqs-state-dot" aria-hidden="true" />
    <div><span className="oqs-overview-state-label">{label}</span><strong>{value}</strong><small>{detail}</small></div>
  </div>;
}

function ResearchOverview({
  projectLabel,
  activityLabel,
  context,
  variant,
  revision,
  selectedStrategy,
  snapshot,
  runs,
  selectedRun,
  onNavigate,
}: ResearchOverviewProps) {
  const sessionValue = context?.isStreaming ? "Streaming" : context?.sessionId ? "Local session" : "Not bound";
  const sessionTone = context?.isStreaming ? "active" : context?.sessionId ? "ready" : "pending";
  const strategyValue = selectedStrategy?.title ?? (revision ? "Revision source" : "Choose a strategy");
  const dataValue = snapshot?.symbol ?? (snapshot ? `${snapshot.symbols.length} symbols` : "No snapshot");
  const runValue = selectedRun?.status ?? (runs.length > 0 ? `${runs.length} runs` : "No formal run");
  const runTone = selectedRun?.status === "succeeded" ? "ready" : selectedRun ? "active" : "pending";
  return <section className="oqs-overview-stack" data-testid="research-overview">
    <div className="oqs-overview-hero">
      <div className="oqs-overview-copy">
        <p className="oqs-kicker">QuantBT strategy desk / Vibe Trading session fabric</p>
        <h2>From research signal to immutable evidence.</h2>
        <p>One local thread for strategy discovery, Python revisions, snapshot-bound runs, and historical replay. The canvas is the map; the formal engine is the ledger.</p>
        <div className="oqs-overview-context"><span>{projectLabel}</span><span>/</span><span>{activityLabel}</span><span className="oqs-overview-context-divider" /><span className="oqs-mono">{shortId(context?.sessionId)}</span></div>
      </div>
      <div className="oqs-overview-actions">
        <button className="oqs-button oqs-button-primary" onClick={() => onNavigate("chat")}>Open Pi session</button>
        <button className="oqs-button" onClick={() => onNavigate("code")}>Shape strategy</button>
      </div>
    </div>
    <div className="oqs-overview-grid">
      <article className="oqs-overview-card oqs-overview-card-session">
        <div className="oqs-overview-card-heading"><span className="oqs-overview-index">01</span><span className="oqs-chip">VIBE TRADING</span></div>
        <h3>Session fabric</h3>
        <p>Pi stays with the Activity while you move between chat, code, canvas, and evidence.</p>
        <OverviewState label="Session" value={sessionValue} detail={shortId(context?.sessionId)} tone={sessionTone} />
      </article>
      <article className="oqs-overview-card oqs-overview-card-strategy">
        <div className="oqs-overview-card-heading"><span className="oqs-overview-index">02</span><span className="oqs-chip">QUANTBT LENS</span></div>
        <h3>Strategy bench</h3>
        <p>Keep the source in <span className="oqs-mono">strategy.py</span>; fork revisions when ideas diverge.</p>
        <OverviewState label="Head" value={strategyValue} detail={`${shortId(variant?.variant_id)} · rev ${shortId(revision?.revision_id)}`} tone={revision ? "ready" : "pending"} />
      </article>
      <article className="oqs-overview-card oqs-overview-card-data">
        <div className="oqs-overview-card-heading"><span className="oqs-overview-index">03</span><span className="oqs-chip">DATA BINDING</span></div>
        <h3>Snapshot gate</h3>
        <p>Every formal action starts from a local, immutable A-share or crypto snapshot.</p>
        <OverviewState label="Selected" value={dataValue} detail={snapshot ? `${snapshot.row_count} rows · ${snapshot.price_basis}` : "Choose Data to continue"} tone={snapshot ? "ready" : "pending"} />
      </article>
      <article className="oqs-overview-card oqs-overview-card-run">
        <div className="oqs-overview-card-heading"><span className="oqs-overview-index">04</span><span className="oqs-chip">FORMAL LEDGER</span></div>
        <h3>Run evidence</h3>
        <p>Metrics, costs, positions, and artifacts render from the same immutable Run.</p>
        <OverviewState label="Latest" value={runValue} detail={selectedRun ? shortId(selectedRun.run_id) : "No selected Run"} tone={runTone} />
      </article>
    </div>
    <div className="oqs-overview-rail">
      <div className="oqs-overview-rail-label"><span>RESEARCH LOOP</span><small>local-only, no order submission</small></div>
      {[{ id: "chat" as WorkbenchId, label: "Observe", detail: "Pi context" }, { id: "code" as WorkbenchId, label: "Shape", detail: "Python source" }, { id: "backtest" as WorkbenchId, label: "Formalize", detail: "Bounded Run" }, { id: "forward-test" as WorkbenchId, label: "Replay", detail: "Historical bars" }].map((stage, index) => <button key={stage.id} className="oqs-overview-stage" onClick={() => onNavigate(stage.id)}><span>{String(index + 1).padStart(2, "0")}</span><strong>{stage.label}</strong><small>{stage.detail}</small></button>)}
    </div>
  </section>;
}

function ContextRail({
  projectLabel,
  activityLabel,
  context,
  variant,
  revision,
  snapshot,
  selectedRun,
}: {
  projectLabel: string;
  activityLabel: string;
  context: Context | undefined;
  variant: Variant | undefined;
  revision: Revision | undefined;
  snapshot: DataSnapshot | undefined;
  selectedRun: RunSummary | undefined;
}) {
  return <div className="oqs-context-rail" data-testid="research-context-rail">
    <div className="oqs-context-rail-title"><span className="oqs-live-dot" />ACTIVE RESEARCH THREAD</div>
    <div className="oqs-context-rail-item"><span>Project</span><strong>{projectLabel}</strong></div>
    <div className="oqs-context-rail-item"><span>Activity</span><strong>{activityLabel}</strong></div>
    <div className="oqs-context-rail-item"><span>Revision</span><strong className="oqs-mono">{shortId(revision?.revision_id)}</strong></div>
    <div className="oqs-context-rail-item"><span>Snapshot</span><strong className="oqs-mono">{shortId(snapshot?.snapshot_id)}</strong></div>
    <div className="oqs-context-rail-item"><span>Run</span><strong className="oqs-mono">{selectedRun ? `${shortId(selectedRun.run_id)} · ${selectedRun.status ?? "queued"}` : "—"}</strong></div>
    <div className="oqs-context-rail-item oqs-context-rail-session"><span>Pi</span><strong className={context?.isStreaming ? "oqs-live" : "oqs-muted"}>{context?.isStreaming ? "streaming" : context?.sessionId ? "local" : "unbound"}</strong><small className="oqs-mono">{shortId(context?.sessionId)} · {shortId(variant?.variant_id)}</small></div>
  </div>;
}

function SessionFabricAside({ context, projectLabel, activityLabel, onNavigate }: { context: Context | undefined; projectLabel: string; activityLabel: string; onNavigate: (workbench: WorkbenchId) => void }) {
  return <aside className="oqs-session-fabric">
    <div className="oqs-session-fabric-head"><p className="oqs-kicker">VIBE TRADING INSPIRED</p><span className="oqs-chip">PI ONLY</span></div>
    <h2>Session fabric</h2>
    <p>Keep the research conversation attached to this Activity while evidence moves through the OQS workbenches.</p>
    <div className="oqs-session-id"><span>SESSION</span><strong className="oqs-mono">{shortId(context?.sessionId)}</strong><small>{projectLabel} / {activityLabel}</small></div>
    <div className="oqs-session-steps"><div className="is-active"><span>01</span><div><strong>Observe</strong><small>Ask Pi for bounded context</small></div></div><div><span>02</span><div><strong>Shape</strong><small>Turn the idea into strategy.py</small></div></div><div><span>03</span><div><strong>Prove</strong><small>Bind data and run formally</small></div></div></div>
    <button className="oqs-button oqs-button-primary" onClick={() => onNavigate("canvas")}>View research graph</button>
  </aside>;
}

function ForwardTestView({
  run,
  result,
  onRequest,
  busy,
}: {
  run: RunSummary | undefined;
  result: ForwardTest | undefined;
  onRequest: () => void;
  busy: boolean;
}) {
  return <section className="oqs-forward-layout">
    <div className="oqs-panel oqs-forward-action">
      <p className="oqs-kicker">LOCAL HISTORICAL REPLAY</p>
      <h2>Forward Test</h2>
      <p>Replay the selected succeeded Formal Run against progressively released historical bars. This does not connect to a broker, exchange, or live feed.</p>
      <dl className="oqs-kv oqs-kv-grid"><dt>Source Run</dt><dd className="oqs-mono">{run?.run_id ?? "—"}</dd><dt>Source status</dt><dd>{run?.status ?? "Select a Run"}</dd><dt>Candidate revision</dt><dd className="oqs-mono">{run?.candidate_revision_id ?? "—"}</dd></dl>
      <div className="oqs-action-row"><button className="oqs-button oqs-button-primary" onClick={onRequest} disabled={busy || run?.status !== "succeeded"}>Run historical replay</button></div>
    </div>
    {result ? <div className="oqs-panel oqs-forward-result" data-testid="forward-test-result">
      <div className="oqs-panel-heading"><div><p className="oqs-kicker">IMMUTABLE REPLAY RESULT</p><h2>Replay result</h2></div><span className="oqs-status">{result.status}</span></div>
      <dl className="oqs-kv oqs-kv-grid"><dt>Forward Test ID</dt><dd className="oqs-mono">{result.forward_test_id}</dd><dt>Source Run</dt><dd className="oqs-mono">{result.source_run_id}</dd><dt>Source revision</dt><dd className="oqs-mono">{result.source_revision_id}</dd><dt>Data snapshot</dt><dd className="oqs-mono">{result.data_snapshot_id}</dd><dt>Released bars</dt><dd>{result.released_bar_count}</dd><dt>Protocol</dt><dd className="oqs-mono">{result.protocol_version}</dd><dt>Result</dt><dd>{result.error_code ?? "passed"}</dd><dt>Created</dt><dd>{timestamp(result.created_at)}</dd></dl>
      <div className="oqs-detail-block"><h3>Transcript and intent tape</h3><pre>{renderValue({ transcript_artifact_id: result.transcript_artifact_id, transcript_sha256: result.transcript_sha256, intent_tape_sha256: result.intent_tape_sha256 })}</pre></div>
    </div> : <div className="oqs-panel"><EmptyState title="No Forward Test result" body="Select a succeeded Formal Run, then start its local historical replay." /></div>}
  </section>;
}

function ArchiveExportView({
  projectId,
  selectedLogs,
  onSelectedLogsChange,
  onExport,
  busy,
}: {
  projectId: string;
  selectedLogs: ArchiveLogSelection;
  onSelectedLogsChange: (value: ArchiveLogSelection) => void;
  onExport: () => void;
  busy: boolean;
}) {
  return <section className="oqs-archive-layout">
    <div className="oqs-panel oqs-archive-panel">
      <p className="oqs-kicker">PROJECT ARCHIVE</p>
      <h2>Export project</h2>
      <p>Download the selected project as an <span className="oqs-mono">.oqs.zip</span> archive with its identity-preserving project data and chosen diagnostic logs.</p>
      <dl className="oqs-kv oqs-kv-grid"><dt>Project</dt><dd className="oqs-mono">{projectId || "Select a project"}</dd></dl>
      <label className="oqs-field">Include logs<select aria-label="Archive log selection" value={selectedLogs} onChange={(event) => onSelectedLogsChange(event.target.value as ArchiveLogSelection)}><option value="full">Full logs</option><option value="warn_error">Warn and error only</option><option value="none">No logs</option></select></label>
      <div className="oqs-action-row"><button className="oqs-button oqs-button-primary" onClick={onExport} disabled={busy || !projectId}>Download project archive</button></div>
    </div>
  </section>;
}

function ArchiveImportView({
  archive,
  result,
  onArchiveChange,
  onImport,
  busy,
}: {
  archive: File | undefined;
  result: unknown;
  onArchiveChange: (file: File | undefined) => void;
  onImport: () => void;
  busy: boolean;
}) {
  return <section className="oqs-archive-layout">
    <div className="oqs-panel oqs-archive-panel">
      <p className="oqs-kicker">PROJECT ARCHIVE</p>
      <h2>Import project</h2>
      <p>Choose an <span className="oqs-mono">.oqs.zip</span> archive to restore its project, Run, Git, and artifact identities locally.</p>
      <label className="oqs-field">Project archive ZIP<input aria-label="Project archive ZIP" type="file" accept=".zip,application/zip,application/vnd.open-quant-studio.project-archive+zip" onChange={(event) => onArchiveChange(event.currentTarget.files?.[0])} /></label>
      <p className="oqs-muted">{archive ? `Ready: ${archive.name}` : "Choose a project archive to import."}</p>
      <div className="oqs-action-row"><button className="oqs-button oqs-button-primary" onClick={onImport} disabled={busy || !archive}>Import project archive</button></div>
      {result !== undefined ? <div className="oqs-detail-block"><h3>Import receipt</h3><pre>{renderValue(result)}</pre></div> : null}
    </div>
  </section>;
}

function DataImportView({
  file,
  localFiles,
  selectedLocalFile,
  preview,
  mapping,
  market,
  timezone,
  priceBasis,
  cutoff,
  executionProfile,
  corporateActionsText,
  errors,
  snapshots,
  selectedSnapshotId,
  busy,
  onFileChange,
  onPreviewUpload,
  onRefreshLocalFiles,
  onSelectedLocalFileChange,
  onPreviewLocal,
  onMappingChange,
  onMarketChange,
  onTimezoneChange,
  onPriceBasisChange,
  onCutoffChange,
  onExecutionProfileChange,
  onCorporateActionsTextChange,
  onCreateSnapshot,
  onSelectSnapshot,
}: {
  file: File | undefined;
  localFiles: LocalDataImportFile[];
  selectedLocalFile: string;
  preview: DataImportPreview | undefined;
  mapping: DataSnapshotMapping;
  market: DataSnapshotMarket;
  timezone: string;
  priceBasis: DataSnapshotPriceBasis;
  cutoff: string;
  executionProfile: DataSnapshotExecutionProfile;
  corporateActionsText: string;
  errors: DataImportRowError[];
  snapshots: DataSnapshot[];
  selectedSnapshotId: string;
  busy: boolean;
  onFileChange: (file: File | undefined) => void;
  onPreviewUpload: () => void;
  onRefreshLocalFiles: () => void;
  onSelectedLocalFileChange: (fileName: string) => void;
  onPreviewLocal: () => void;
  onMappingChange: (field: keyof DataSnapshotMapping, column: string) => void;
  onMarketChange: (market: DataSnapshotMarket) => void;
  onTimezoneChange: (timezone: string) => void;
  onPriceBasisChange: (priceBasis: DataSnapshotPriceBasis) => void;
  onCutoffChange: (cutoff: string) => void;
  onExecutionProfileChange: (profile: DataSnapshotExecutionProfile) => void;
  onCorporateActionsTextChange: (value: string) => void;
  onCreateSnapshot: () => void;
  onSelectSnapshot: (snapshotId: string) => void;
}) {
  return <section className="oqs-data-layout">
    <div className="oqs-panel oqs-data-source">
      <div className="oqs-panel-heading"><div><p className="oqs-kicker">LOCAL MARKET DATA</p><h2>CSV or Parquet source</h2></div><span className="oqs-chip">immutable on create</span></div>
      <div className="oqs-data-source-grid">
        <div>
          <h3>Upload from this browser</h3>
          <label className="oqs-field">CSV or Parquet file<input aria-label="Market data file" type="file" accept=".csv,.parquet,text/csv,application/vnd.apache.parquet" onChange={(event) => onFileChange(event.currentTarget.files?.[0])} /></label>
          <p className="oqs-muted">{file ? `Ready: ${file.name}` : "Choose one local dataset to preview."}</p>
          <button className="oqs-button oqs-button-primary" onClick={onPreviewUpload} disabled={busy || !file}>Preview upload</button>
        </div>
        <div>
          <h3>Configured imports directory</h3>
          <label className="oqs-field">Available import<select aria-label="Local imports file" value={selectedLocalFile} onChange={(event) => onSelectedLocalFileChange(event.target.value)}><option value="">Select a local import</option>{localFiles.map((item) => <option key={item.file_name} value={item.file_name}>{item.file_name} · {item.byte_size} bytes</option>)}</select></label>
          <div className="oqs-action-row"><button className="oqs-button" onClick={onRefreshLocalFiles} disabled={busy}>Refresh local imports</button><button className="oqs-button oqs-button-primary" onClick={onPreviewLocal} disabled={busy || !selectedLocalFile}>Preview local file</button></div>
        </div>
      </div>
      {errors.length > 0 ? <div className="oqs-detail-block" data-testid="data-import-errors"><h3>Row validation errors</h3><div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>Row</th><th>Field</th><th>Message</th></tr></thead><tbody>{errors.map((error) => <tr key={`${error.row_number}:${error.field}:${error.message}`}><td>{error.row_number}</td><td>{error.field}</td><td>{error.message}</td></tr>)}</tbody></table></div></div> : null}
    </div>

    <div className="oqs-panel oqs-data-preview">
      <div className="oqs-panel-heading"><div><p className="oqs-kicker">FIELD PREVIEW</p><h2>Map source columns</h2></div><span className="oqs-chip">{preview ? `${preview.total_rows} rows` : "no preview"}</span></div>
      {preview ? <>
        <dl className="oqs-kv oqs-kv-grid"><dt>File</dt><dd>{preview.file_name}</dd><dt>Format</dt><dd>{preview.source_format}</dd><dt>Source SHA-256</dt><dd className="oqs-mono">{preview.source.sha256}</dd></dl>
        <div className="oqs-mapping-grid">{DATA_MAPPING_FIELDS.map(({ key, label }) => <label className="oqs-field" key={key}>{label}<select aria-label={`${label} column`} value={mapping[key] ?? ""} onChange={(event) => onMappingChange(key, event.target.value)}>{key === "trading_status" || key === "price_limit_state" ? <option value="">Infer when possible</option> : null}{preview.columns.map((column) => <option value={column} key={column}>{column}</option>)}</select></label>)}</div>
        <div className="oqs-data-config-grid">
          <label className="oqs-field">Market<select aria-label="Snapshot market" value={market} onChange={(event) => onMarketChange(event.target.value as DataSnapshotMarket)}><option value="a_share_daily">A-share daily</option><option value="crypto_linear_perp">Crypto linear perpetual</option></select></label>
          <label className="oqs-field">Timezone<input aria-label="Snapshot timezone" value={timezone} onChange={(event) => onTimezoneChange(event.target.value)} /></label>
          <label className="oqs-field">Price basis<select aria-label="Snapshot price basis" value={priceBasis} onChange={(event) => onPriceBasisChange(event.target.value as DataSnapshotPriceBasis)}><option value="raw">Raw</option><option value="qfq">QFQ</option><option value="hfq">HFQ</option></select></label>
          <label className="oqs-field">Cutoff<input aria-label="Snapshot cutoff" value={cutoff} onChange={(event) => onCutoffChange(event.target.value)} /></label>
          <label className="oqs-field">Execution profile<select aria-label="Snapshot execution profile" value={executionProfile} onChange={(event) => onExecutionProfileChange(event.target.value as DataSnapshotExecutionProfile)}><option value="legacy">Legacy compatibility</option><option value="a-share-v3">A-share research v3</option></select></label>
          {executionProfile === "a-share-v3" ? <label className="oqs-field oqs-field-wide">Corporate actions JSON (optional)<textarea aria-label="Corporate actions JSON" value={corporateActionsText} onChange={(event) => onCorporateActionsTextChange(event.target.value)} rows={4} placeholder="[]" /></label> : null}
        </div>
        <div className="oqs-action-row"><button className="oqs-button oqs-button-primary" onClick={onCreateSnapshot} disabled={busy}>Create immutable snapshot</button></div>
        <div className="oqs-detail-block"><h3>Preview rows</h3><div className="oqs-table-wrap"><table className="oqs-table"><thead><tr>{preview.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{preview.preview_rows.map((row, index) => <tr key={index}>{preview.columns.map((column) => <td key={column}>{row[column] ?? ""}</td>)}</tr>)}</tbody></table></div></div>
      </> : <EmptyState title="Preview a dataset" body="Choose a browser file or a configured local import, then inspect its columns before creating a snapshot." />}
    </div>

    <div className="oqs-panel oqs-data-snapshots">
      <div className="oqs-panel-heading"><div><p className="oqs-kicker">IMMUTABLE DATA SNAPSHOTS</p><h2>Available snapshots</h2></div><span className="oqs-chip">{snapshots.length} total</span></div>
          {snapshots.length === 0 ? <EmptyState title="No data snapshots" body="Preview and map a dataset to create the first immutable snapshot." /> : <div className="oqs-snapshot-grid">{snapshots.map((snapshot) => <article className={`oqs-snapshot-card ${selectedSnapshotId === snapshot.snapshot_id ? "is-selected" : ""}`} key={snapshot.snapshot_id} data-testid={`snapshot-${snapshot.snapshot_id}`}><div><span className="oqs-status">{snapshot.market}</span><h3>{snapshot.symbol ?? `${snapshot.symbols.length}-symbol portfolio`}</h3></div><dl className="oqs-kv"><dt>Snapshot</dt><dd className="oqs-mono">{snapshot.snapshot_id}</dd><dt>Rows</dt><dd>{snapshot.row_count}</dd><dt>Sessions</dt><dd>{snapshot.session_count}</dd><dt>Range</dt><dd>{timestamp(snapshot.sample_start)} – {timestamp(snapshot.sample_end)}</dd><dt>Basis</dt><dd>{snapshot.price_basis}</dd><dt>SHA-256</dt><dd className="oqs-mono">{snapshot.sha256}</dd></dl><button className="oqs-button oqs-button-primary" onClick={() => onSelectSnapshot(snapshot.snapshot_id)} disabled={busy}>{selectedSnapshotId === snapshot.snapshot_id ? "Selected for Formal Run" : "Use for Formal Run"}</button></article>)}</div>}
    </div>
  </section>;
}

function LogsView({
  logs,
  filters,
  selectedRunId,
  selectedLogIds,
  pendingDeletion,
  loading,
  onFiltersChange,
  onApply,
  onRefresh,
  onSelectionChange,
  onRequestDelete,
  onCancelDelete,
  onConfirmDelete,
}: {
  logs: LogEntry[];
  filters: LogFilterControls;
  selectedRunId: string;
  selectedLogIds: string[];
  pendingDeletion: string[] | undefined;
  loading: boolean;
  onFiltersChange: (filters: LogFilterControls) => void;
  onApply: () => void;
  onRefresh: () => void;
  onSelectionChange: (logIds: string[]) => void;
  onRequestDelete: (logIds: string[]) => void;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
}) {
  const selectedIds = new Set(selectedLogIds);
  const allSelected = logs.length > 0 && logs.every((log) => selectedIds.has(log.log_id));

  return <section className="oqs-logs-layout">
    <div className="oqs-panel oqs-logs-panel">
      <div className="oqs-panel-heading"><div><p className="oqs-kicker">DIAGNOSTIC LOGS</p><h2>Logs</h2></div><span className="oqs-chip">{selectedRunId ? `Run ${shortId(selectedRunId)}` : "all runs"}</span></div>
      <form className="oqs-log-filters" onSubmit={(event) => { event.preventDefault(); onApply(); }}>
        <label className="oqs-field">Level<select aria-label="Log level" value={filters.level ?? ""} onChange={(event) => onFiltersChange({ ...filters, level: (event.target.value || undefined) as LogLevel | undefined })}><option value="">All levels</option><option value="debug">Debug</option><option value="info">Info</option><option value="warn">Warn</option><option value="error">Error</option></select></label>
        <label className="oqs-field">Priority<select aria-label="Log priority" value={filters.priority ?? ""} onChange={(event) => onFiltersChange({ ...filters, priority: (event.target.value || undefined) as LogPriority | undefined })}><option value="">All priorities</option><option value="p1">P1</option><option value="p2">P2</option><option value="p3">P3</option><option value="p4">P4</option></select></label>
        <label className="oqs-field oqs-log-search">Search<input aria-label="Search logs" value={filters.query ?? ""} onChange={(event) => onFiltersChange({ ...filters, query: event.target.value })} placeholder="Message or event code" /></label>
        <div className="oqs-action-row"><button type="submit" className="oqs-button oqs-button-primary" disabled={loading}>Apply filters</button><button type="button" className="oqs-button" onClick={onRefresh} disabled={loading}>Refresh</button><button type="button" className="oqs-button" onClick={() => onRequestDelete(selectedLogIds)} disabled={loading || selectedLogIds.length === 0}>Delete selected</button></div>
      </form>
      {pendingDeletion ? <div className="oqs-log-confirmation" role="alertdialog" aria-label="Confirm log deletion"><strong>Delete {pendingDeletion.length} selected log{pendingDeletion.length === 1 ? "" : "s"}?</strong><span>This removes the selected diagnostic log records.</span><div className="oqs-action-row"><button type="button" className="oqs-button" onClick={onCancelDelete} disabled={loading}>Cancel</button><button type="button" className="oqs-button oqs-button-primary" onClick={onConfirmDelete} disabled={loading}>Confirm deletion</button></div></div> : null}
      {logs.length === 0 ? <EmptyState title={loading ? "Loading logs" : "No logs match current filters"} body={loading ? "Loading diagnostic logs from the selected scope." : "Change the filters or refresh to inspect another log scope."} /> : <div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th><input type="checkbox" aria-label="Select all logs" checked={allSelected} onChange={(event) => onSelectionChange(event.target.checked ? logs.map((log) => log.log_id) : [])} /></th><th>Level</th><th>Priority</th><th>Event</th><th>Message</th><th>At</th><th>Action</th></tr></thead><tbody>{logs.map((log) => <tr key={logRecordKey(log)}><td><input type="checkbox" aria-label={`Select log ${log.log_id}`} checked={selectedIds.has(log.log_id)} onChange={(event) => onSelectionChange(event.target.checked ? [...selectedLogIds, log.log_id] : selectedLogIds.filter((logId) => logId !== log.log_id))} /></td><td>{log.level ?? "—"}</td><td>{log.priority ?? "—"}</td><td className="oqs-mono">{log.event_code ?? "—"}</td><td>{log.message ?? "—"}</td><td>{timestamp(log.timestamp ?? log.created_at)}</td><td><button type="button" className="oqs-button" aria-label={`Delete log ${log.log_id}`} onClick={() => onRequestDelete([log.log_id])} disabled={loading}>Delete</button></td></tr>)}</tbody></table></div>}
    </div>
  </section>;
}

function CodeView({
  strategies,
  selectedStrategyId,
  code,
  setCode,
  revision,
  onSave,
  onSelectStrategy,
  onFinalize,
  onDownload,
  onCompare,
  onCreateVariant,
  busy,
}: {
  strategies: BuiltInStrategy[];
  selectedStrategyId: string;
  code: string;
  setCode: (value: string) => void;
  revision: Revision | undefined;
  onSave: () => void;
  onSelectStrategy: (strategyId: string) => void;
  onFinalize: () => void;
  onDownload: () => void;
  onCompare: () => void;
  onCreateVariant: () => void;
  busy: boolean;
}) {
  return <section className="oqs-code-layout">
    <div className="oqs-panel oqs-code-editor">
      <div className="oqs-panel-heading"><div><p className="oqs-kicker">AUTHORITATIVE SOURCE</p><h2>strategy.py</h2></div><span className="oqs-chip">{revision ? `rev ${shortId(revision.revision_id)}` : "no revision"}</span></div>
      <div className="oqs-strategy-picker"><label className="oqs-field">Built-in strategy<select aria-label="Built-in strategy" value={selectedStrategyId} onChange={(event) => onSelectStrategy(event.target.value)}><option value="">Select one of six strategies</option>{strategies.map((strategy) => <option value={strategy.strategy_id} key={strategy.strategy_id}>{strategy.title}</option>)}</select></label><p className="oqs-muted">Selecting loads the built-in Python source into the editor. Saving and finalizing create immutable child revisions.</p></div>
      <CodeMirror value={code} height="520px" extensions={[python()]} onChange={setCode} basicSetup={{ lineNumbers: true, foldGutter: true }} />
      <div className="oqs-action-row"><button className="oqs-button oqs-button-primary" onClick={onSave} disabled={busy || !revision}>Save child revision</button><button className="oqs-button oqs-button-primary" onClick={onFinalize} disabled={busy || !revision || !selectedStrategyId}>Finalize notebook</button><button className="oqs-button" onClick={onDownload} disabled={!revision?.files.some((file) => file.path === "strategy.ipynb")}>Download notebook</button><button className="oqs-button" onClick={onCompare} disabled={!revision}>Compare</button><button className="oqs-button" onClick={onCreateVariant} disabled={busy}>Fork variant</button></div>
    </div>
    <aside className="oqs-panel oqs-side-detail"><p className="oqs-kicker">REVISION PROVENANCE</p><dl className="oqs-kv"><dt>Revision</dt><dd>{revision?.revision_id ?? "—"}</dd><dt>Tree</dt><dd>{revision?.git_tree_oid ?? "—"}</dd><dt>Commit</dt><dd>{revision?.git_commit_oid ?? "—"}</dd><dt>Files</dt><dd>{revision?.files.length ?? 0}</dd></dl><p className="oqs-muted">Saving submits a typed child-revision command. It never overwrites a concurrent head.</p></aside>
  </section>;
}

function StrategyRunReview({
  strategy,
  snapshot,
  executionProfile,
  revision,
  confirmed,
  onConfirmedChange,
}: {
  strategy: BuiltInStrategy | undefined;
  snapshot: DataSnapshot | undefined;
  executionProfile: DataSnapshotExecutionProfile;
  revision: Revision | undefined;
  confirmed: boolean;
  onConfirmedChange: (confirmed: boolean) => void;
}) {
  const isAShareV3 = executionProfile === "a-share-v3";
  return <section className="oqs-panel oqs-run-review" data-testid="strategy-run-review">
    <div className="oqs-panel-heading"><div><p className="oqs-kicker">PRE-RUN REVIEW</p><h2>Strategy, parameters and costs</h2></div><span className="oqs-chip">{isAShareV3 ? "A-share v3" : "legacy profile"}</span></div>
    <p className="oqs-muted">Review the exact strategy assumptions and market-rule profile before requesting an immutable Formal Run. The RunSpec binds these identities to the selected snapshot.</p>
    <div className="oqs-review-grid">
      <div><h3>Strategy</h3><dl className="oqs-kv"><dt>Selected</dt><dd>{strategy?.title ?? "Custom / revision source"}</dd><dt>Strategy ID</dt><dd className="oqs-mono">{strategy?.strategy_id ?? "—"}</dd><dt>Revision</dt><dd className="oqs-mono">{revision?.revision_id ?? "—"}</dd><dt>Tree</dt><dd className="oqs-mono">{revision?.git_tree_oid ?? "—"}</dd><dt>Source SHA-256</dt><dd className="oqs-mono">{revision?.files.find((file) => file.path === "strategy.py")?.sha256 ?? strategy?.source_sha256 ?? "—"}</dd></dl></div>
      <div><h3>Data binding</h3><dl className="oqs-kv"><dt>Snapshot</dt><dd className="oqs-mono">{snapshot?.snapshot_id ?? "Select one in Data"}</dd><dt>Symbols</dt><dd>{snapshot?.symbols?.join(", ") ?? "—"}</dd><dt>Price basis</dt><dd>{snapshot?.price_basis ?? "—"}</dd><dt>Sessions</dt><dd>{snapshot?.session_count ?? "—"}</dd></dl></div>
    </div>
    {strategy?.parameters?.length ? <div className="oqs-detail-block"><h3>Parameters</h3><div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>Name</th><th>Value</th><th>Meaning</th></tr></thead><tbody>{strategy.parameters.map((parameter) => <tr key={parameter.name}><td className="oqs-mono">{parameter.name}</td><td>{String(parameter.value)}</td><td>{parameter.meaning}</td></tr>)}</tbody></table></div></div> : <p className="oqs-muted">No structured strategy parameters were declared; the revision source remains the authority.</p>}
    {strategy?.assumptions?.length ? <div className="oqs-detail-block"><h3>Strategy assumptions</h3><ul>{strategy.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul></div> : null}
    <div className="oqs-detail-block"><h3>Execution cost and rule model</h3><dl className="oqs-kv oqs-kv-grid"><dt>Commission</dt><dd>{isAShareV3 ? "0.06% notional, minimum 0" : "Bound by selected legacy RunSpec"}</dd><dt>Stamp duty</dt><dd>{isAShareV3 ? "0.10% on sells" : "Bound by selected legacy RunSpec"}</dd><dt>Slippage</dt><dd>{isAShareV3 ? "10 price atoms at market open" : "Bound by selected legacy RunSpec"}</dd><dt>Participation</dt><dd>{isAShareV3 ? "10% of reported share volume, lot-aligned" : "Bound by selected legacy RunSpec"}</dd><dt>Position books</dt><dd>{isAShareV3 ? "cash_long + research_short (isolated)" : "Selected engine profile"}</dd><dt>Short rule</dt><dd>{isAShareV3 ? "100% margin, no leverage, no auto-liquidation; T+1 cover" : "Selected engine profile"}</dd><dt>Long rule</dt><dd>{isAShareV3 ? "T+1 sell eligibility; no implicit netting" : "Selected engine profile"}</dd></dl></div>
    <label className="oqs-field"><span><input type="checkbox" aria-label="I reviewed strategy, parameters and costs" checked={confirmed} disabled={!snapshot || !revision} onChange={(event) => onConfirmedChange(event.target.checked)} /> I reviewed this revision, its parameters, costs and A-share rules.</span></label>
  </section>;
}

function ComparisonView({ comparison, onMerge, busy }: { comparison: { left: Revision | undefined; right: Revision | undefined; result: RevisionComparison | undefined }; onMerge: () => void; busy: boolean }) {
  const changes = comparison.result?.changes ?? [];
  return <section className="oqs-panel"><div className="oqs-panel-heading"><div><p className="oqs-kicker">IMMUTABLE REVISION COMPARE</p><h2>Path and hash changes</h2></div><button className="oqs-button oqs-button-primary" onClick={onMerge} disabled={busy || changes.length === 0}>Create merge candidate</button></div><div className="oqs-compare-meta"><span>Left {shortId(comparison.result?.left_revision_id ?? comparison.left?.revision_id)}</span><span>Right {shortId(comparison.result?.right_revision_id ?? comparison.right?.revision_id)}</span></div>{changes.length === 0 ? <EmptyState title="No changed paths" body="Select two distinct revisions or save a child revision before comparing." /> : <div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>Path</th><th>Status</th><th>Left SHA-256</th><th>Right SHA-256</th></tr></thead><tbody>{changes.map((change) => <tr key={change.path}><td className="oqs-mono">{change.path}</td><td>{change.status ?? "changed"}</td><td className="oqs-mono">{change.left_sha256 ?? "—"}</td><td className="oqs-mono">{change.right_sha256 ?? "—"}</td></tr>)}</tbody></table></div>}</section>;
}

type EngineTableColumn = { key: string; label: string };

const ENGINE_TABLE_COLUMNS: Record<string, EngineTableColumn[]> = {
  fills: [
    { key: "fill_id", label: "Fill ID" },
    { key: "intent_id", label: "Intent" },
    { key: "symbol", label: "Symbol" },
    { key: "book", label: "Book" },
    { key: "session_seq", label: "Session" },
    { key: "side", label: "Side" },
    { key: "position_effect", label: "Effect" },
    { key: "quantity", label: "Quantity" },
    { key: "fill_price_atoms", label: "Price" },
    { key: "notional_atoms", label: "Notional" },
    { key: "fee_atoms", label: "Fee" },
    { key: "stamp_duty_atoms", label: "Stamp duty" },
    { key: "slippage_atoms", label: "Slippage" },
    { key: "remaining_quantity", label: "Remaining" },
    { key: "frozen_margin_delta_atoms", label: "Frozen margin Δ" },
    { key: "isolated_proceeds_delta_atoms", label: "Isolated proceeds Δ" },
  ],
  positions: [
    { key: "intent_id", label: "Opening intent" },
    { key: "symbol", label: "Symbol" },
    { key: "book", label: "Book" },
    { key: "session_seq", label: "Session" },
    { key: "signed_quantity", label: "Signed quantity" },
    { key: "eligible_quantity", label: "T+1 eligible" },
  ],
  cash_ledger: [
    { key: "intent_id", label: "Intent" },
    { key: "symbol", label: "Symbol" },
    { key: "book", label: "Book" },
    { key: "session_seq", label: "Session" },
    { key: "notional_delta_atoms", label: "Notional Δ" },
    { key: "fee_delta_atoms", label: "Fee Δ" },
    { key: "stamp_duty_delta_atoms", label: "Stamp duty Δ" },
    { key: "realized_pnl_delta_atoms", label: "Realized P&L Δ" },
    { key: "resulting_available_cash_atoms", label: "Available cash" },
    { key: "frozen_margin_delta_atoms", label: "Frozen margin Δ" },
    { key: "isolated_proceeds_delta_atoms", label: "Isolated proceeds Δ" },
  ],
  equity_curve: [
    { key: "session_seq", label: "Session" },
    { key: "timestamp", label: "Timestamp" },
    { key: "available_cash_atoms", label: "Available cash" },
    { key: "long_market_value_atoms", label: "Long value" },
    { key: "short_liability_atoms", label: "Short liability" },
    { key: "gross_market_value_atoms", label: "Gross exposure" },
    { key: "net_market_value_atoms", label: "Net exposure" },
    { key: "frozen_margin_atoms", label: "Frozen margin" },
    { key: "isolated_short_proceeds_atoms", label: "Isolated short proceeds" },
    { key: "equity_atoms", label: "Equity" },
  ],
  corporate_action_ledger: [
    { key: "action_id", label: "Action" },
    { key: "symbol", label: "Symbol" },
    { key: "session_seq", label: "Session" },
    { key: "action_type", label: "Type" },
    { key: "book", label: "Book" },
    { key: "quantity_before", label: "Quantity before" },
    { key: "quantity_after", label: "Quantity after" },
    { key: "available_cash_delta_atoms", label: "Cash Δ" },
    { key: "frozen_margin_delta_atoms", label: "Margin Δ" },
    { key: "isolated_proceeds_delta_atoms", label: "Proceeds Δ" },
    { key: "realized_pnl_delta_atoms", label: "Realized P&L Δ" },
  ],
};

const MAX_ENGINE_ROWS = 200;

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function displayRecordValue(value: unknown): string {
  return value === undefined || value === null || value === "" ? "—" : renderValue(value);
}

function EngineRecordTable({ label, value }: { label: string; value: unknown }) {
  if (value === undefined || value === null) return null;
  if (!Array.isArray(value)) {
    return <div className="oqs-detail-block"><h3>{label.replaceAll("_", " ")}</h3><pre>{renderValue(value)}</pre></div>;
  }
  const columns = ENGINE_TABLE_COLUMNS[label] ?? [];
  const rows = value.slice(0, MAX_ENGINE_ROWS);
  const truncated = value.length > MAX_ENGINE_ROWS;
  return <div className="oqs-detail-block" data-testid={`engine-record-${label}`}>
    <h3>{label.replaceAll("_", " ")}</h3>
    {truncated ? <p className="oqs-muted" role="status">Showing the first {MAX_ENGINE_ROWS} of {value.length} records. Remaining records stay available in the immutable engine artifact.</p> : null}
    <div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>#</th>{columns.length > 0 ? columns.map((column) => <th key={column.key}>{column.label}</th>) : <th>Record</th>}</tr></thead><tbody>{rows.map((item, index) => {
      const record = recordValue(item);
      return <tr key={`${engineRecordKey(label, item)}:${index}`}><td>{index}</td>{columns.length > 0 && record ? columns.map((column) => <td key={column.key}><pre>{displayRecordValue(record[column.key])}</pre></td>) : <td><pre>{renderValue(item)}</pre></td>}</tr>;
    })}</tbody></table></div>
  </div>;
}

function stringField(record: Record<string, unknown> | undefined, key: string): string | undefined {
  const value = record?.[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function gatesFromDetail(detail: RunDetail): Record<string, unknown> | undefined {
  const validation = recordValue(detail.validation);
  const validationGates = recordValue(validation?.gates);
  if (validationGates) return validationGates;
  return recordValue(detail.manifest?.gates);
}

function RunFailurePanel({ detail }: { detail: RunDetail }) {
  const run = recordValue(detail.run);
  const validation = recordValue(detail.validation);
  const errorCode = stringField(run, "error_code")
    ?? stringField(validation, "error_code")
    ?? stringField(detail, "error_code")
    ?? "formal_run_failed";
  const gates = gatesFromDetail(detail);
  const logs = detail.logs ?? [];
  return <div className="oqs-panel oqs-run-failure" role="alert" data-testid="run-failure-panel">
    <div className="oqs-panel-heading"><div><p className="oqs-kicker">FORMAL RUN FAILURE</p><h2>Run did not complete</h2></div><span className="oqs-status oqs-status-failed">failed</span></div>
    <div className="oqs-notice oqs-notice-error"><strong className="oqs-mono">{errorCode}</strong><span>The immutable Run has no result artifact to promote.</span></div>
    <dl className="oqs-kv oqs-kv-grid"><dt>Error code</dt><dd className="oqs-mono">{errorCode}</dd><dt>Validation outcome</dt><dd>{stringField(validation, "outcome") ?? "failed"}</dd><dt>Run ID</dt><dd className="oqs-mono">{stringField(run, "run_id") ?? "—"}</dd></dl>
    <div className="oqs-detail-block"><h3>Validation gates</h3>{gates ? <div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>Gate</th><th>Outcome</th></tr></thead><tbody>{Object.entries(gates).map(([gate, outcome]) => <tr key={gate}><td className="oqs-mono">{gate}</td><td>{displayRecordValue(outcome)}</td></tr>)}</tbody></table></div> : <EmptyState title="Validation gates unavailable" body="The API did not include gate outcomes for this failed Run." />}</div>
    <div className="oqs-detail-block"><h3>Failure logs</h3>{logs.length > 0 ? <div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>Level</th><th>Priority</th><th>Event</th><th>Message</th></tr></thead><tbody>{logs.map((log) => <tr key={logRecordKey(log)}><td>{log.level ?? "—"}</td><td>{log.priority ?? "—"}</td><td className="oqs-mono">{log.event_code ?? "—"}</td><td>{log.message ?? "—"}</td></tr>)}</tbody></table></div> : <EmptyState title="No run-scoped logs" body="No diagnostic log records were attached to this failed Run." />}</div>
  </div>;
}

function RunReportView({
  model,
  onDownload,
  busy,
}: {
  model: RunReportReadModel | undefined;
  onDownload: (format: "json" | "html") => void;
  busy: boolean;
}) {
  if (!model) return <EmptyState title="Run report unavailable" body="A report is generated when the succeeded Formal Run is ready." />;
  const { report } = model;
  const summaryEntries: Array<[string, string | number]> = [
    ["Starting equity", report.summary.starting_equity_atoms],
    ["Ending equity", report.summary.ending_equity_atoms],
    ["Net P&L", report.summary.net_pnl_atoms],
    ["Total return", report.summary.total_return_rate_atoms],
    ["Max drawdown", report.summary.max_drawdown_atoms],
    ["Drawdown rate", report.summary.max_drawdown_rate_atoms],
    ["Gross exposure", report.summary.gross_exposure_atoms],
    ["Net exposure", report.summary.net_exposure_atoms],
    ["Fees", report.summary.total_fees_atoms],
    ["Stamp duty", report.summary.total_stamp_duty_atoms],
    ["Funding", report.summary.total_funding_atoms],
    ["Slippage", report.summary.total_slippage_atoms],
    ["Orders", report.summary.order_count],
    ["Fills", report.summary.fill_count],
    ["Closed trades", report.summary.closed_trade_count],
    ["Open positions", report.summary.open_position_count],
  ];
  return <div className="oqs-panel oqs-run-report" data-testid="run-report">
    <div className="oqs-panel-heading">
      <div><p className="oqs-kicker">M9 DETERMINISTIC REPORT</p><h2>Run report</h2></div>
      <div className="oqs-heading-actions"><button className="oqs-button" onClick={() => onDownload("json")} disabled={busy}>Download JSON</button><button className="oqs-button" onClick={() => onDownload("html")} disabled={busy}>Download HTML</button></div>
    </div>
    <dl className="oqs-kv oqs-kv-grid oqs-report-period"><dt>Period start</dt><dd>{report.period.start_at ?? "—"}</dd><dt>Period end</dt><dd>{report.period.end_at ?? "—"}</dd><dt>Sessions</dt><dd>{report.period.session_count}</dd><dt>Report version</dt><dd className="oqs-mono">{report.report_version}</dd></dl>
    <div className="oqs-metric-grid">{summaryEntries.map(([label, value]) => <div className="oqs-metric" key={label} data-testid={`run-report-${label.toLowerCase().replaceAll(" ", "-")}`}><span>{label}</span><strong>{String(value)}</strong></div>)}</div>
    <div className="oqs-report-reconciliation" data-testid="run-report-reconciliation"><div className="oqs-panel-heading"><h3>Reconciliation</h3><span className={`oqs-status ${report.reconciliation.passed ? "oqs-status-passed" : "oqs-status-failed"}`}>{report.reconciliation.passed ? "passed" : "failed"}</span></div><div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>Field</th><th>Expected</th><th>Actual</th><th>Status</th></tr></thead><tbody>{report.reconciliation.checks.map((check) => <tr key={check.field}><td className="oqs-mono">{check.field}</td><td>{String(check.expected)}</td><td>{String(check.actual)}</td><td>{check.passed ? "passed" : "failed"}</td></tr>)}</tbody></table></div></div>
    <div className="oqs-detail-block"><h3>Identities and provenance</h3><dl className="oqs-kv oqs-kv-grid"><dt>Run</dt><dd className="oqs-mono">{report.run.run_id}</dd><dt>RunSpec</dt><dd className="oqs-mono">{report.run.run_spec_id}</dd><dt>Engine</dt><dd className="oqs-mono">{report.identities.engine_version}</dd><dt>Engine result</dt><dd className="oqs-mono">{report.identities.engine_result_sha256}</dd><dt>Data snapshot</dt><dd className="oqs-mono">{report.identities.data_snapshot_id}</dd><dt>Strategy tree</dt><dd className="oqs-mono">{report.identities.strategy_tree_oid}</dd><dt>Price basis</dt><dd>{report.identities.price_basis}</dd><dt>Timezone</dt><dd>{report.identities.timezone}</dd></dl></div>
    <div className="oqs-detail-block"><h3>Metric definitions</h3><div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>Field</th><th>Name</th><th>Unit</th><th>Formula</th><th>Inputs</th><th>Empty behavior</th></tr></thead><tbody>{report.definitions.map((definition) => <tr key={definition.field}><td className="oqs-mono">{definition.field}</td><td>{definition.name}</td><td>{definition.unit}</td><td>{definition.formula}</td><td>{definition.inputs.join(", ")}</td><td>{definition.empty_behavior}</td></tr>)}</tbody></table></div></div>
  </div>;
}

function RunDetailView({ detail, report, onPromote, onDownloadReport, busy }: { detail: RunDetail | undefined; report: RunReportReadModel | undefined; onPromote: () => void; onDownloadReport: (format: "json" | "html") => void; busy: boolean }) {
  const manifest = detail?.manifest;
  const runSpec = detail?.run_spec ?? (typeof manifest?.run_spec === "object" && manifest.run_spec !== null ? manifest.run_spec as Record<string, unknown> : undefined);
  const engine = detail?.engine_result ?? (typeof detail?.formal_engine_result === "object" && detail.formal_engine_result !== null ? detail.formal_engine_result as Record<string, unknown> : undefined);
  const engineVersion = typeof engine?.engine_version === "string"
    ? engine.engine_version
    : typeof runSpec?.engine_version === "string"
      ? runSpec.engine_version
      : "formal";
  const run = detail?.run;
  const runRecord = recordValue(run);
  const validation = recordValue(detail?.validation);
  const validationOutcome = stringField(validation, "outcome");
  const errorCode = stringField(runRecord, "error_code")
    ?? stringField(validation, "error_code")
    ?? stringField(detail, "error_code");
  const failed = run?.status === "failed" || validationOutcome === "failed" || errorCode !== undefined;
  const status = run?.status ?? "returned";
  if (!detail) return <EmptyState title="No Run selected" body="Run a validated candidate to inspect its immutable formal artifact." />;
  return (
    <section className="oqs-run-detail">
      <div className="oqs-panel">
        <div className="oqs-panel-heading">
          <div><p className="oqs-kicker">IMMUTABLE FORMAL ARTIFACT</p><h2>Run Detail</h2></div>
          <div className="oqs-heading-actions">
            <span className={"oqs-status" + (failed ? " oqs-status-failed" : "")}>{status}</span>
            <button className="oqs-button oqs-button-primary" onClick={onPromote} disabled={busy || run?.status !== "succeeded"}>Promote</button>
          </div>
        </div>
        <dl className="oqs-kv oqs-kv-grid">
          <dt>RunSpec</dt><dd>{runSpec ? "bound" : "—"}</dd>
          <dt>Run ID</dt><dd className="oqs-mono">{run?.run_id ?? "—"}</dd>
          <dt>Validation</dt><dd>{validationOutcome ?? "—"}</dd>
          <dt>Candidate revision</dt><dd className="oqs-mono">{run?.candidate_revision_id ?? "—"}</dd>
        </dl>
        {runSpec ? <div className="oqs-detail-block"><h3>RunSpec fields</h3><pre>{renderValue(runSpec)}</pre></div> : null}
      </div>
      {failed ? <RunFailurePanel detail={detail} /> : null}
      {run?.status === "succeeded" ? <RunReportView model={report} onDownload={onDownloadReport} busy={busy} /> : null}
      {engine ? <div className="oqs-panel">
        <div className="oqs-panel-heading">
          <div><p className="oqs-kicker">RUST ENGINE OUTPUT</p><h2>Orders, fills, positions, and metrics</h2></div>
          <span className="oqs-chip">{engineVersion}</span>
        </div>
        <div className="oqs-metric-grid">
          {typeof engine.metrics === "object" && engine.metrics !== null
            ? Object.entries(engine.metrics).map(([key, value]) => <div className="oqs-metric" key={key}><span>{key.replaceAll("_", " ")}</span><strong>{renderValue(value)}</strong></div>)
            : <EmptyState title="Metrics unavailable" body="The formal engine did not include a metrics object in this artifact." />}
        </div>
        {["orders", "fills", "trades", "positions", "cash_ledger", "funding_ledger", "equity_curve", "drawdown_curve", "corporate_action_ledger"].map((key) => <EngineRecordTable key={key} label={key} value={engine[key]} />)}
        <div className="oqs-detail-block"><h3>Costs and assumptions</h3><pre>{renderValue({ costs: engine.costs, assumptions: engine.assumptions })}</pre></div>
      </div> : failed ? null : <EmptyState title="Engine result not embedded" body="The API returned a Run envelope without an engine result artifact." />}
      {manifest ? <div className="oqs-panel">
        <div className="oqs-panel-heading"><div><p className="oqs-kicker">PROVENANCE / GATES / LOGS</p><h2>Manifest</h2></div></div>
        <pre>{renderValue({
          run_spec: runSpec,
          revision: manifest.revision,
          engine_input: manifest.engine_input,
          market_input: manifest.market_input,
          resolved_engine_input: manifest.resolved_engine_input,
          strategy_execution: manifest.strategy_execution,
          checkpoint: manifest.checkpoint,
          gates: manifest.gates,
          logs: manifest.logs,
        })}</pre>
      </div> : null}
      {detail.logs && !failed ? <div className="oqs-panel">
        <div className="oqs-panel-heading"><div><p className="oqs-kicker">RUN-SCOPED LOGS</p><h2>Logs</h2></div><span className="oqs-chip">{detail.logs.length} entries</span></div>
        <div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>Level</th><th>Priority</th><th>Event</th><th>Message</th></tr></thead><tbody>{detail.logs.map((log) => <tr key={logRecordKey(log)}><td>{log.level ?? "—"}</td><td>{log.priority ?? "—"}</td><td className="oqs-mono">{log.event_code ?? "—"}</td><td>{log.message ?? "—"}</td></tr>)}</tbody></table></div>
      </div> : null}
    </section>
  );
}

const defaultResearchApi = createResearchApi();

export function ResearchWorkbench({ api = defaultResearchApi }: ResearchWorkbenchProps) {
  const [context, setContext] = useState<Context>();
  const [projects, setProjects] = useState<Project[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [projectId, setProjectId] = useState("");
  const [activityId, setActivityId] = useState("");
  const [headRevisionId, setHeadRevisionId] = useState("");
  const [variants, setVariants] = useState<Variant[]>([]);
  const [revision, setRevision] = useState<Revision>();
  const [comparison, setComparison] = useState<{ left: Revision | undefined; right: Revision | undefined; result: RevisionComparison | undefined }>({ left: undefined, right: undefined, result: undefined });
  const candidateRevisionId = useRef("");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [runDetail, setRunDetail] = useState<RunDetail>();
  const [runReport, setRunReport] = useState<RunReportReadModel>();
  const [forwardTest, setForwardTest] = useState<ForwardTest>();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logFilters, setLogFilters] = useState<LogFilterControls>({});
  const [appliedLogFilters, setAppliedLogFilters] = useState<LogFilterControls>({});
  const [selectedLogIds, setSelectedLogIds] = useState<string[]>([]);
  const [pendingLogDeletion, setPendingLogDeletion] = useState<string[]>();
  const [logsLoading, setLogsLoading] = useState(false);
  const [archiveLogSelection, setArchiveLogSelection] = useState<ArchiveLogSelection>("warn_error");
  const [archiveFile, setArchiveFile] = useState<File>();
  const [archiveImportResult, setArchiveImportResult] = useState<unknown>();
  const [dataFile, setDataFile] = useState<File>();
  const [localDataFiles, setLocalDataFiles] = useState<LocalDataImportFile[]>([]);
  const [selectedLocalDataFile, setSelectedLocalDataFile] = useState("");
  const [dataPreview, setDataPreview] = useState<DataImportPreview>();
  const [dataMapping, setDataMapping] = useState<DataSnapshotMapping>({
    timestamp: "",
    symbol: "",
    open: "",
    high: "",
    low: "",
    close: "",
    volume: "",
    trading_status: "",
    price_limit_state: "",
  });
  const [dataMarket, setDataMarket] = useState<DataSnapshotMarket>("a_share_daily");
  const [dataTimezone, setDataTimezone] = useState("Asia/Shanghai");
  const [dataPriceBasis, setDataPriceBasis] = useState<DataSnapshotPriceBasis>("raw");
  const [dataCutoff, setDataCutoff] = useState("2026-12-31T23:59:59Z");
  const [dataExecutionProfile, setDataExecutionProfile] = useState<DataSnapshotExecutionProfile>("legacy");
  const [dataCorporateActionsText, setDataCorporateActionsText] = useState("[]");
  const [dataImportErrors, setDataImportErrors] = useState<DataImportRowError[]>([]);
  const [dataSnapshots, setDataSnapshots] = useState<DataSnapshot[]>([]);
  const [selectedDataSnapshotId, setSelectedDataSnapshotId] = useState("");
  const [builtInStrategies, setBuiltInStrategies] = useState<BuiltInStrategy[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [runReviewConfirmed, setRunReviewConfirmed] = useState(false);
  const [renderedNotebook, setRenderedNotebook] = useState<RenderedStrategyNotebook>();
  const [code, setCode] = useState("");
  const [workbench, setWorkbench] = useState<WorkbenchId>("canvas");
  const [selectedNode, setSelectedNode] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatConnected, setChatConnected] = useState(false);
  const [chatMessages, setChatMessages] = useState<Array<{
    id: string;
    role: "user" | "pi";
    text: string;
    streaming?: boolean;
  }>>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<CanvasNodeData>>(emptyNodes);
  const [edges, , onEdgesChange] = useEdgesState(canvasEdges());
  const selectedVariant = variants.find((item) => item.head_revision_id === headRevisionId) ?? variants[0];
  const selectedRun = runs.find((run) => run.run_id === selectedRunId);
  const selectedStrategy = builtInStrategies.find((item) => item.strategy_id === selectedStrategyId);
  const selectedSnapshot = dataSnapshots.find((item) => item.snapshot_id === selectedDataSnapshotId);
  const logRequest = useMemo<LogListFilters>(() => ({
    ...appliedLogFilters,
    runId: selectedRunId || undefined,
    limit: 100,
  }), [appliedLogFilters, selectedRunId]);

  const reportError = useCallback((value: unknown) => {
    if (value instanceof ResearchApiError) setError(`${value.code}: request failed`);
    else if (value instanceof Error) setError(value.message);
    else setError("Request failed");
  }, []);

  const loadLogs = useCallback(async () => {
    setLogsLoading(true);
    setError(undefined);
    try {
      const page = await api.listLogs(logRequest);
      setLogs(page.logs);
      setSelectedLogIds([]);
    } catch (value) {
      reportError(value);
    } finally {
      setLogsLoading(false);
    }
  }, [api, logRequest, reportError]);

  const loadDataCatalog = useCallback(async () => {
    if (!projectId) return;
    setBusy(true);
    setError(undefined);
    try {
      const [snapshots, localFiles] = await Promise.all([
        api.listDataSnapshots(),
        api.listLocalDataImports(),
      ]);
      setDataSnapshots(snapshots);
      setLocalDataFiles(localFiles);
      setSelectedLocalDataFile((current) =>
        localFiles.some((file) => file.file_name === current)
          ? current
          : localFiles[0]?.file_name ?? ""
      );
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [api, projectId, reportError]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getContext(), api.listProjects()]).then(([nextContext, nextProjects]) => {
      if (cancelled) return;
      setContext(nextContext);
      setProjects(nextProjects);
      setProjectId(nextContext.projectId ?? nextProjects[0]?.project_id ?? "");
      setWorkbench((nextContext.activeWorkbenchId as WorkbenchId | undefined) ?? "canvas");
    }).catch(reportError);
    return () => { cancelled = true; };
  }, [api, reportError]);

  useEffect(() => {
    let cancelled = false;
    api.listBuiltInStrategies().then((strategies) => {
      if (!cancelled) setBuiltInStrategies(strategies);
    }).catch(reportError);
    return () => { cancelled = true; };
  }, [api, reportError]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    api.listActivities(projectId).then((nextActivities) => {
      if (cancelled) return;
      setActivities(nextActivities);
      setActivityId((current) => current || context?.activityId || nextActivities[0]?.activity_id || "");
    }).catch(reportError);
    return () => { cancelled = true; };
  }, [api, projectId, context?.activityId, reportError]);

  useEffect(() => {
    if (workbench !== "logs") return;
    void loadLogs();
  }, [loadLogs, workbench]);

  useEffect(() => {
    if (workbench !== "data") return;
    void loadDataCatalog();
  }, [loadDataCatalog, workbench]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    Promise.all([api.getRevisionHead(projectId), api.listVariants(projectId), api.listRuns(projectId, activityId || undefined)]).then(([head, nextVariants, nextRuns]) => {
      if (cancelled) return;
      setHeadRevisionId(head.head_revision_id);
      setVariants(nextVariants);
      setRuns(nextRuns);
      setSelectedRunId((current) => current || nextRuns[0]?.run_id || "");
    }).catch(reportError);
    return () => { cancelled = true; };
  }, [api, projectId, activityId, reportError]);

  useEffect(() => {
    const revisionId = selectedVariant?.head_revision_id || headRevisionId;
    if (!projectId || !revisionId) {
      setRevision(undefined);
      return;
    }
    let cancelled = false;
    api.getRevision(projectId, revisionId).then((nextRevision) => {
      if (cancelled) return;
      setRevision(nextRevision);
      setCode(getCodeFromRevision(nextRevision));
    }).catch(reportError);
    return () => { cancelled = true; };
  }, [api, projectId, selectedVariant?.head_revision_id, headRevisionId, reportError]);

  useEffect(() => {
    setRunReviewConfirmed(false);
  }, [selectedDataSnapshotId, selectedStrategyId, revision?.revision_id]);

  useEffect(() => {
    candidateRevisionId.current = "";
    setRunReviewConfirmed(false);
  }, [activityId, projectId]);

  useEffect(() => {
    if (!selectedRunId) {
      setRunDetail(undefined);
      setRunReport(undefined);
      return;
    }
    let cancelled = false;
    let loading = false;
    let retry: ReturnType<typeof setInterval> | undefined;
    const stop = () => {
      if (retry !== undefined) {
        clearInterval(retry);
        retry = undefined;
      }
    };
    const load = async () => {
      if (cancelled || loading) return;
      loading = true;
      try {
        const detail = await api.getRun(selectedRunId, projectId || undefined);
        if (cancelled) return;
        const report = detail.run?.status === "succeeded"
          ? await api.getRunReport(selectedRunId, projectId || undefined)
          : undefined;
        if (cancelled) return;
        const nextRuns = await api.listRuns(projectId);
        if (cancelled) return;
        setRunDetail(detail);
        setRunReport(report);
        setRuns(nextRuns);
        if (
          detail.run?.status === "succeeded"
          || detail.run?.status === "failed"
          || detail.run?.status === "cancelled"
        ) {
          stop();
        }
      } catch (value) {
        if (
          !cancelled
          && value instanceof ResearchApiError
          && value.status === 404
          && value.code === "run_not_found"
        ) {
          return;
        }
        if (!cancelled) {
          stop();
          reportError(value);
        }
      } finally {
        loading = false;
      }
    };
    retry = setInterval(() => { void load(); }, 500);
    void load();
    return () => {
      cancelled = true;
      stop();
    };
  }, [api, projectId, selectedRunId, reportError]);

  useEffect(() => {
    const nextNodes = canvasNodes(context, selectedVariant, selectedRun, revision);
    const key = projectId && activityId ? `oqs:canvas:${projectId}:${activityId}` : "";
    let persisted: Node<CanvasNodeData>[] | undefined;
    if (key) {
      const raw = localStorage.getItem(key);
      if (raw) {
        try {
          const stored = JSON.parse(raw) as Array<{ id?: string; position?: { x: number; y: number } }>;
          persisted = nextNodes.map((node) => {
            const saved = stored.find((entry) => entry.id === node.id);
            return saved?.position ? { ...node, position: saved.position } : node;
          });
        } catch {
          persisted = undefined;
        }
      }
    }
    setNodes((current) => (persisted ?? nextNodes).map((node) => {
      const measured = current.find((entry) => entry.id === node.id);
      return measured ? { ...measured, ...node } : node;
    }));
  }, [activityId, context, projectId, revision, selectedRun, selectedVariant, setNodes]);

  useEffect(() => {
    if (!projectId || !activityId || nodes.length === 0) return;
    localStorage.setItem(`oqs:canvas:${projectId}:${activityId}`, JSON.stringify(nodes.map((node) => ({ id: node.id, position: node.position }))));
  }, [activityId, nodes, projectId]);

  useEffect(() => {
    if (workbench !== "chat" || !projectId) return;
    return api.subscribeChatEvents(projectId, (event: ChatEvent) => {
      const delta = event.delta;
      if (event.type === "assistant_text_delta" && delta) {
        setChatMessages((current) => {
          const last = current.at(-1);
          if (last?.role === "pi" && last.streaming === true) {
            return [
              ...current.slice(0, -1),
              { ...last, text: `${last.text}${delta}` },
            ];
          }
          return [...current, { id: crypto.randomUUID(), role: "pi", text: delta, streaming: true }];
        });
      }
      const messageText = event.text;
      if (event.type === "assistant_message_end" && messageText) {
        setChatMessages((current) => {
          const last = current.at(-1);
          if (last?.role === "pi" && last.streaming === true) {
            return [
              ...current.slice(0, -1),
              { ...last, text: messageText, streaming: undefined },
            ];
          }
          return [...current, { id: crypto.randomUUID(), role: "pi", text: messageText }];
        });
      }
    }, setChatConnected);
  }, [api, projectId, workbench]);

  const saveChildRevision = useCallback(async () => {
    if (!projectId || !activityId || !revision || !selectedVariant) return;
    setBusy(true);
    setError(undefined);
    try {
      const response = await api.createChildRevision({
        projectId,
        activityId,
        variantId: selectedVariant.variant_id,
        baseRevisionId: revision.revision_id,
        expectedRevisionId: revision.revision_id,
        message: "Edit strategy.py from OQS Code workbench",
        files: [{ path: "strategy.py", body: code }],
        removedPaths: revision.files.some((file) => file.path === "strategy.ipynb")
          ? ["strategy.ipynb"]
          : undefined,
      });
      const createdRevisionId = getRevisionId(response);
      setRenderedNotebook(undefined);
      setNotice(createdRevisionId ? `Child revision ${shortId(createdRevisionId)} created` : "Child revision command accepted");
      if (createdRevisionId) {
        const nextRevision = await api.getRevision(projectId, createdRevisionId);
        setRevision(nextRevision);
        setCode(getCodeFromRevision(nextRevision));
      }
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [activityId, api, code, projectId, reportError, revision, selectedVariant]);

  const selectBuiltInStrategy = useCallback((strategyId: string) => {
    setSelectedStrategyId(strategyId);
    setRenderedNotebook(undefined);
    const strategy = builtInStrategies.find((item) => item.strategy_id === strategyId);
    if (strategy) setCode(strategy.source_body);
  }, [builtInStrategies]);

  const finalizeNotebook = useCallback(async () => {
    const strategy = builtInStrategies.find((item) => item.strategy_id === selectedStrategyId);
    if (!strategy || !projectId || !activityId || !revision || !selectedVariant) return;
    setBusy(true);
    setError(undefined);
    try {
      const notebook = await api.renderStrategyNotebook(strategy.strategy_id, code);
      const files = revision.files
        .filter((file) => file.path !== "strategy.py" && file.path !== "strategy.ipynb")
        .map((file) => ({ path: file.path, body: file.body }));
      files.push({ path: "strategy.py", body: code });
      files.push({ path: "strategy.ipynb", body: notebook.body });
      const response = await api.createChildRevision({
        projectId,
        activityId,
        variantId: selectedVariant.variant_id,
        baseRevisionId: revision.revision_id,
        expectedRevisionId: revision.revision_id,
        message: `Finalize ${strategy.title} notebook from strategy.py`,
        files,
      });
      const createdRevisionId = getRevisionId(response);
      setRenderedNotebook(notebook);
      setNotice(createdRevisionId
        ? `Finalized notebook in revision ${shortId(createdRevisionId)}`
        : "Finalized notebook revision accepted");
      if (createdRevisionId) {
        const nextRevision = await api.getRevision(projectId, createdRevisionId);
        setRevision(nextRevision);
        setCode(getCodeFromRevision(nextRevision));
      }
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [activityId, api, builtInStrategies, code, projectId, reportError, revision, selectedStrategyId, selectedVariant]);

  const downloadNotebook = useCallback(() => {
    const notebookBody = revision?.files.find((file) => file.path === "strategy.ipynb")?.body
      ?? renderedNotebook?.body;
    if (!notebookBody) return;
    const strategyId = notebookStrategyId(notebookBody);
    const href = URL.createObjectURL(
      new Blob([notebookBody], { type: "application/x-ipynb+json" }),
    );
    const link = document.createElement("a");
    link.href = href;
    link.download = `${strategyId}.ipynb`;
    link.click();
    URL.revokeObjectURL(href);
  }, [renderedNotebook, revision]);

  const forkVariant = useCallback(async () => {
    if (!projectId || !activityId || !revision) return;
    setBusy(true);
    setError(undefined);
    try {
      await api.createStrategyVariant({ projectId, activityId, baseRevisionId: revision.revision_id, message: "Fork from Code workbench" });
      setNotice("Strategy variant command accepted");
      setVariants(await api.listVariants(projectId));
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [activityId, api, projectId, reportError, revision]);

  const compare = useCallback(async () => {
    if (!projectId || !revision || !headRevisionId || headRevisionId === revision.revision_id) {
      setNotice("Save a child revision or select a second head before comparing");
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      const result = await api.compareRevisions(projectId, headRevisionId, revision.revision_id);
      setComparison({ left: undefined, right: revision, result });
      setWorkbench("compare");
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [api, headRevisionId, projectId, reportError, revision]);

  const merge = useCallback(async () => {
    if (!projectId || !activityId || !selectedVariant || !revision || !comparison.result) return;
    setBusy(true);
    setError(undefined);
    try {
      const files = revision.files.map((file) => ({ path: file.path, body: file.body }));
      const response = await api.createMergeCandidate({ projectId, activityId, variantId: selectedVariant.variant_id, candidateRevisionId: revision.revision_id, message: "Merge candidate from Compare workbench", files });
      const candidate = getRevisionId(response);
      setNotice(candidate ? `Merge candidate ${shortId(candidate)} created` : "Merge candidate command accepted");
      if (candidate) {
        candidateRevisionId.current = candidate;
        const nextRevision = await api.getRevision(projectId, candidate);
        setRevision(nextRevision);
        setCode(getCodeFromRevision(nextRevision));
        setRunReviewConfirmed(false);
      }
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [activityId, api, comparison.result, projectId, reportError, revision, selectedVariant]);

  const acceptDataPreview = useCallback((preview: DataImportPreview) => {
    setDataPreview(preview);
    setDataMapping(preview.suggested_mapping);
    setDataImportErrors([]);
  }, []);

  const previewDataFile = useCallback(async () => {
    if (!dataFile) return;
    setBusy(true);
    setError(undefined);
    setDataImportErrors([]);
    try {
      acceptDataPreview(await api.previewDataImport(dataFile));
      setNotice(`Previewed ${dataFile.name}`);
    } catch (value) {
      setDataImportErrors(rowErrors(value));
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [acceptDataPreview, api, dataFile, reportError]);

  const previewLocalDataFile = useCallback(async () => {
    if (!selectedLocalDataFile) return;
    setBusy(true);
    setError(undefined);
    setDataImportErrors([]);
    try {
      acceptDataPreview(await api.previewLocalDataImport(selectedLocalDataFile));
      setNotice(`Previewed ${selectedLocalDataFile} from local imports`);
    } catch (value) {
      setDataImportErrors(rowErrors(value));
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [acceptDataPreview, api, reportError, selectedLocalDataFile]);

  const createDataSnapshot = useCallback(async () => {
    if (!dataPreview) return;
    setBusy(true);
    setError(undefined);
    try {
      let corporateActions: DataSnapshotCorporateAction[] | undefined;
      if (dataExecutionProfile === "a-share-v3") {
        const parsed: unknown = JSON.parse(dataCorporateActionsText || "[]");
        if (!Array.isArray(parsed)) throw new Error("Corporate actions JSON must be an array");
        corporateActions = parsed as DataSnapshotCorporateAction[];
      }
      const response = await api.createDataSnapshot({
        source: dataPreview.source,
        source_format: dataPreview.source_format,
        file_name: dataPreview.file_name,
        mapping: dataMapping,
        market: dataMarket,
        timezone: dataTimezone,
        price_basis: dataPriceBasis,
        cutoff: dataCutoff,
        ...(dataExecutionProfile === "legacy"
          ? {}
          : { execution_profile: dataExecutionProfile }),
        ...(corporateActions === undefined ? {} : { corporate_actions: corporateActions }),
      });
      const snapshotId = getSnapshotId(response);
      setDataSnapshots(await api.listDataSnapshots());
      setNotice(snapshotId
        ? `Immutable snapshot ${shortId(snapshotId)} created`
        : "Immutable data snapshot created");
    } catch (value) {
      setDataImportErrors(rowErrors(value));
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [api, dataCorporateActionsText, dataCutoff, dataExecutionProfile, dataMapping, dataMarket, dataPreview, dataPriceBasis, dataTimezone, reportError]);

  const formalRun = useCallback(async () => {
    const candidateRevisionIdToRun = candidateRevisionId.current || comparison.result?.right_revision_id || revision?.revision_id || selectedVariant?.head_revision_id;
    if (!candidateRevisionIdToRun || !selectedDataSnapshotId) return;
    if (!runReviewConfirmed) {
      setWorkbench("backtest");
      setNotice("Review the bound strategy revision, parameters and costs before requesting a Formal Run");
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      const selectedSnapshot = dataSnapshots.find(
        (snapshot) => snapshot.snapshot_id === selectedDataSnapshotId,
      );
      const reviewAttestation: ReviewAttestation | undefined = selectedSnapshot !== undefined
        && (selectedSnapshot.schema_version === 3 || selectedSnapshot.execution_profile === "a-share-v3")
        ? {
            status: "approved",
            candidate_revision_id: candidateRevisionIdToRun,
            strategy_tree_oid: revision?.git_tree_oid ?? "",
            data_snapshot_sha256: selectedSnapshot.sha256,
            parameters_sha256: "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
            cost_model_sha256: "1b8c04884842ebed2127ad93926c2da822c831225c76ed08361704e95aceb8e0",
            reviewer_id: "local-user",
            reviewed_at: new Date().toISOString(),
          }
        : undefined;
      const response = await api.requestFormalRun(
        candidateRevisionIdToRun,
        selectedDataSnapshotId,
        reviewAttestation,
      );
      const runId = getRunId(response);
      setNotice(runId ? `Formal Run ${shortId(runId)} queued` : "Formal Run command accepted");
      const nextRuns = await api.listRuns(projectId, activityId || undefined);
      setRuns(nextRuns);
      if (runId) setSelectedRunId(runId);
      setRunReviewConfirmed(false);
      setWorkbench("backtest");
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [activityId, api, comparison.result, dataSnapshots, projectId, reportError, revision, runReviewConfirmed, selectedDataSnapshotId, selectedVariant]);

  const confirmLogDeletion = useCallback(async () => {
    if (!pendingLogDeletion) return;
    setLogsLoading(true);
    setError(undefined);
    try {
      await api.deleteLogs(pendingLogDeletion);
      const page = await api.listLogs(logRequest);
      setLogs(page.logs);
      setSelectedLogIds([]);
      setPendingLogDeletion(undefined);
      setNotice(`${pendingLogDeletion.length} diagnostic log${pendingLogDeletion.length === 1 ? "" : "s"} deleted`);
    } catch (value) {
      reportError(value);
    } finally {
      setLogsLoading(false);
    }
  }, [api, logRequest, pendingLogDeletion, reportError]);

  const requestForwardTest = useCallback(async () => {
    if (!selectedRunId) {
      setNotice("Select a succeeded Formal Run before starting a Forward Test");
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      const receipt = await api.requestForwardTest(selectedRunId);
      const result = await api.getForwardTest(receipt.forward_test_id);
      setForwardTest(result);
      setNotice(`Forward Test ${shortId(result.forward_test_id)} ${result.status}`);
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [api, reportError, selectedRunId]);

  const exportProjectArchive = useCallback(async () => {
    if (!projectId) return;
    setBusy(true);
    setError(undefined);
    try {
      const archive = await api.downloadProjectArchive(projectId, archiveLogSelection);
      const archiveUrl = URL.createObjectURL(archive);
      const link = document.createElement("a");
      link.href = archiveUrl;
      link.download = `${projectId}.oqs.zip`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(archiveUrl);
      setNotice(`Project archive downloaded with ${archiveLogSelection} logs`);
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [api, archiveLogSelection, projectId, reportError]);

  const importProjectArchive = useCallback(async () => {
    if (!archiveFile) return;
    setBusy(true);
    setError(undefined);
    try {
      const result = await api.importProjectArchive(archiveFile);
      setArchiveImportResult(result);
      setNotice(`Project archive ${archiveFile.name} imported`);
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [api, archiveFile, reportError]);

  const promote = useCallback(async () => {
    if (!selectedRunId) return;
    setBusy(true);
    setError(undefined);
    try {
      await api.promoteRun(selectedRunId);
      setNotice(`Run ${shortId(selectedRunId)} promoted with compare-and-set`);
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [api, reportError, selectedRunId]);

  const downloadRunReport = useCallback(async (format: "json" | "html") => {
    if (!selectedRunId) return;
    setBusy(true);
    setError(undefined);
    try {
      const content = await api.downloadRunReport(selectedRunId, format);
      const contentUrl = URL.createObjectURL(content);
      const link = document.createElement("a");
      link.href = contentUrl;
      link.download = `${selectedRunId}.report.${format}`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(contentUrl);
      setNotice(`Run report ${format.toUpperCase()} downloaded`);
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [api, reportError, selectedRunId]);

  const sendChat = useCallback(async () => {
    const text = chatInput.trim();
    if (!text) return;
    setChatInput("");
    setChatMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", text }]);
    try {
      const response = await api.prompt(text);
      if (typeof response === "object" && response !== null) {
        const body = response as Record<string, unknown>;
        const message = typeof body.message === "string" ? body.message : typeof body.text === "string" ? body.text : undefined;
        if (message) setChatMessages((current) => [...current, { id: crypto.randomUUID(), role: "pi", text: message }]);
      }
    } catch (value) {
      reportError(value);
    }
  }, [api, chatInput, reportError]);

  const selectedNodeDetail = useMemo(() => nodes.find((node) => node.id === selectedNode), [nodes, selectedNode]);
  const projectLabel = projects.find((project) => project.project_id === projectId)?.name ?? shortId(projectId);
  const activityLabel = activities.find((activity) => activity.activity_id === activityId)?.name ?? shortId(activityId);

  return <div className="oqs-shell">
    <header className="oqs-topbar">
      <div className="oqs-brand">
        <span className="oqs-mark">OQ</span>
        <div><strong>Open Quant Studio</strong><span>strategy research operating system</span></div>
      </div>
      <div className="oqs-selectors">
        <label>Project<select data-testid="project-selector" value={projectId} onChange={(event) => { setProjectId(event.target.value); setActivityId(""); setSelectedDataSnapshotId(""); setDataPreview(undefined); }}><option value="">Select project</option>{projects.map((project) => <option value={project.project_id} key={project.project_id}>{project.name ?? shortId(project.project_id)}</option>)}</select></label>
        <label>Activity<select data-testid="activity-selector" value={activityId} onChange={(event) => setActivityId(event.target.value)}><option value="">Select activity</option>{activities.map((activity) => <option value={activity.activity_id} key={activity.activity_id}>{activity.name ?? shortId(activity.activity_id)}</option>)}</select></label>
      </div>
      <div className="oqs-topbar-status"><span className={context?.isStreaming ? "oqs-live" : "oqs-muted"}><span className="oqs-live-dot" />{context?.isStreaming ? "Pi streaming" : "local context"}</span><span className="oqs-topbar-divider" /><span className="oqs-mono">{shortId(context?.sessionId)}</span></div>
      <div className="oqs-context"><span>{projectLabel} / {activityLabel}</span><span className={context?.isStreaming ? "oqs-live" : "oqs-muted"}>{context?.isStreaming ? "Pi streaming" : "local context"}</span></div>
    </header>
    <div className="oqs-body">
      <aside className="oqs-sidebar">
        <div className="oqs-sidebar-intro"><div className="oqs-sidebar-title">WORKBENCH</div><span>LOCAL / SINGLE USER</span></div>
        {NAV_GROUPS.map((group) => <div className="oqs-nav-group" key={group.label}><div className="oqs-nav-group-label">{group.label}</div>{group.ids.map((id) => { const item = NAV_ITEMS.find((entry) => entry.id === id); if (!item) return null; return <button key={item.id} className={`oqs-nav-item ${workbench === item.id ? "is-active" : ""}`} aria-current={workbench === item.id ? "page" : undefined} onClick={() => setWorkbench(item.id)}><span>{item.label}</span><small>{item.description}</small></button>; })}</div>)}
        <div className="oqs-sidebar-footer"><span className="oqs-dot" />Research-only mode<span className="oqs-sidebar-footer-note">no order submission</span></div>
      </aside>
      <main className="oqs-main">
        <div className="oqs-main-heading"><div><p className="oqs-kicker">{projectLabel} · {activityLabel}</p><h1>{NAV_ITEMS.find((item) => item.id === workbench)?.label}</h1></div><div className="oqs-heading-actions">{selectedRunId ? <button className="oqs-button" onClick={() => setWorkbench("run-detail")}>Open Run {shortId(selectedRunId)}</button> : null}<button className="oqs-button" onClick={formalRun} disabled={busy || !revision || !selectedDataSnapshotId}>{runReviewConfirmed ? "Run formal" : "Review formal Run"}</button></div></div>
        <ContextRail projectLabel={projectLabel} activityLabel={activityLabel} context={context} variant={selectedVariant} revision={revision} snapshot={selectedSnapshot} selectedRun={selectedRun} />
        <ErrorNotice error={error} />
        {notice ? <div className="oqs-notice" role="status">{notice}<button onClick={() => setNotice(undefined)} aria-label="Dismiss notice">×</button></div> : null}
        {workbench === "canvas" ? <><ResearchOverview projectLabel={projectLabel} activityLabel={activityLabel} context={context} variant={selectedVariant} revision={revision} selectedStrategy={selectedStrategy} snapshot={selectedSnapshot} runs={runs} selectedRun={selectedRun} onNavigate={setWorkbench} /><section className="oqs-canvas-layout"><div className="oqs-panel oqs-canvas"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onNodeClick={(_, node) => setSelectedNode(node.id)} onNodeDragStop={() => { if (projectId && activityId) localStorage.setItem(`oqs:canvas:${projectId}:${activityId}`, JSON.stringify(nodes.map((node) => ({ id: node.id, position: node.position })))); }} proOptions={{ hideAttribution: true }}><Controls /><Background gap={20} size={1} /></ReactFlow></div><aside className="oqs-panel oqs-node-detail"><p className="oqs-kicker">SELECTED GRAPH NODE</p>{selectedNodeDetail ? <><span className="oqs-chip">{selectedNodeDetail.data.kind}</span><h2>{selectedNodeDetail.data.title}</h2><p>{selectedNodeDetail.data.detail}</p><dl className="oqs-kv"><dt>Node ID</dt><dd className="oqs-mono">{selectedNodeDetail.id}</dd><dt>Position</dt><dd>{Math.round(selectedNodeDetail.position.x)}, {Math.round(selectedNodeDetail.position.y)}</dd></dl></> : <EmptyState title="Select a node" body="Drag nodes to shape the project graph. Layout is persisted per project and activity." />}</aside></section></> : null}
        {workbench === "chat" ? <section className="oqs-chat-layout"><section className="oqs-panel oqs-chat"><div className="oqs-panel-heading"><div><p className="oqs-kicker">LOCAL PI SESSION</p><h2>Pi Chat</h2></div><span className="oqs-chip">{chatConnected ? "Pi connected" : "connecting…"}</span></div><div className="oqs-chat-history">{chatMessages.length === 0 ? <EmptyState title="Ask about this Activity" body="Prompt responses and Pi session events appear here." /> : chatMessages.map((message) => <div key={message.id} className={`oqs-chat-message ${message.role}`}><span>{message.role === "user" ? "You" : "Pi"}</span><p>{message.text}</p></div>)}</div><form className="oqs-chat-form" onSubmit={(event) => { event.preventDefault(); void sendChat(); }}><input value={chatInput} onChange={(event) => setChatInput(event.target.value)} placeholder="Ask Pi about this research context…" aria-label="Chat prompt" /><button type="submit" className="oqs-button oqs-button-primary" disabled={!chatConnected || !chatInput.trim()}>Send</button></form></section><SessionFabricAside context={context} projectLabel={projectLabel} activityLabel={activityLabel} onNavigate={setWorkbench} /></section> : null}
        {workbench === "code" ? <CodeView strategies={builtInStrategies} selectedStrategyId={selectedStrategyId} code={code} setCode={setCode} revision={revision} onSelectStrategy={selectBuiltInStrategy} onSave={() => { void saveChildRevision(); }} onFinalize={() => { void finalizeNotebook(); }} onDownload={downloadNotebook} onCompare={() => { void compare(); }} onCreateVariant={() => { void forkVariant(); }} busy={busy} /> : null}
        {workbench === "compare" ? <ComparisonView comparison={comparison} onMerge={() => { void merge(); }} busy={busy} /> : null}
        {workbench === "backtest" ? <><StrategyRunReview strategy={selectedStrategy} snapshot={selectedSnapshot} executionProfile={selectedSnapshot?.execution_profile ?? dataExecutionProfile} revision={revision} confirmed={runReviewConfirmed} onConfirmedChange={setRunReviewConfirmed} /><section className="oqs-backtest-layout"><div className="oqs-panel"><p className="oqs-kicker">QUANTBT-STYLE FORMAL LEDGER</p><h2>Backtest</h2><p>Runs are created from the explicitly selected immutable DataSnapshot by the Python domain and Rust formal engine. Review the bound strategy, costs, and market rules before you queue evidence.</p><dl className="oqs-kv"><dt>Data snapshot</dt><dd className="oqs-mono">{selectedDataSnapshotId || "Select one in Data"}</dd></dl><div className="oqs-action-row"><button className="oqs-button oqs-button-primary" onClick={() => { void formalRun(); }} disabled={busy || !revision || !selectedDataSnapshotId || !runReviewConfirmed}>Request formal Run</button>{selectedRunId ? <button className="oqs-button" onClick={() => setWorkbench("run-detail")}>View Run Detail</button> : null}</div></div><div className="oqs-panel"><div className="oqs-panel-heading"><div><p className="oqs-kicker">RUN QUEUE</p><h2>Activity Runs</h2></div><span className="oqs-chip">{runs.length} total</span></div>{runs.length === 0 ? <EmptyState title="No formal Runs" body="Select an immutable snapshot, save or merge a candidate, then request a formal Run." /> : <div className="oqs-run-list">{runs.map((run) => <button key={run.run_id} className={`oqs-run-row ${selectedRunId === run.run_id ? "is-active" : ""}`} onClick={() => setSelectedRunId(run.run_id)}><span className="oqs-mono">{shortId(run.run_id)}</span><span>{run.status ?? "unknown"}</span><span>{timestamp(run.finished_at ?? run.created_at)}</span></button>)}</div>}</div></section></> : null}
        {workbench === "run-detail" ? <RunDetailView detail={runDetail} report={runReport} onPromote={() => { void promote(); }} onDownloadReport={(format) => { void downloadRunReport(format); }} busy={busy} /> : null}
        {workbench === "forward-test" ? <ForwardTestView run={selectedRun} result={forwardTest} onRequest={() => { void requestForwardTest(); }} busy={busy} /> : null}
        {workbench === "data" ? <><DataImportView file={dataFile} localFiles={localDataFiles} selectedLocalFile={selectedLocalDataFile} preview={dataPreview} mapping={dataMapping} market={dataMarket} timezone={dataTimezone} priceBasis={dataPriceBasis} cutoff={dataCutoff} executionProfile={dataExecutionProfile} corporateActionsText={dataCorporateActionsText} errors={dataImportErrors} snapshots={dataSnapshots} selectedSnapshotId={selectedDataSnapshotId} busy={busy} onFileChange={(file) => { setDataFile(file); setDataPreview(undefined); setDataImportErrors([]); }} onPreviewUpload={() => { void previewDataFile(); }} onRefreshLocalFiles={() => { void loadDataCatalog(); }} onSelectedLocalFileChange={setSelectedLocalDataFile} onPreviewLocal={() => { void previewLocalDataFile(); }} onMappingChange={(field, column) => setDataMapping((current) => ({ ...current, [field]: column }))} onMarketChange={setDataMarket} onTimezoneChange={setDataTimezone} onPriceBasisChange={setDataPriceBasis} onCutoffChange={setDataCutoff} onExecutionProfileChange={setDataExecutionProfile} onCorporateActionsTextChange={setDataCorporateActionsText} onCreateSnapshot={() => { void createDataSnapshot(); }} onSelectSnapshot={(snapshotId) => { setSelectedDataSnapshotId(snapshotId); setNotice(`Snapshot ${shortId(snapshotId)} selected for Formal Run`); }} /><ArchiveImportView archive={archiveFile} result={archiveImportResult} onArchiveChange={(file) => { setArchiveFile(file); setArchiveImportResult(undefined); }} onImport={() => { void importProjectArchive(); }} busy={busy} /></> : null}
        {workbench === "settings" ? <ArchiveExportView projectId={projectId} selectedLogs={archiveLogSelection} onSelectedLogsChange={setArchiveLogSelection} onExport={() => { void exportProjectArchive(); }} busy={busy} /> : null}
        {workbench === "logs" ? <LogsView logs={logs} filters={logFilters} selectedRunId={selectedRunId} selectedLogIds={selectedLogIds} pendingDeletion={pendingLogDeletion} loading={logsLoading} onFiltersChange={setLogFilters} onApply={() => setAppliedLogFilters({ ...logFilters })} onRefresh={() => { void loadLogs(); }} onSelectionChange={setSelectedLogIds} onRequestDelete={(logIds) => setPendingLogDeletion(logIds)} onCancelDelete={() => setPendingLogDeletion(undefined)} onConfirmDelete={() => { void confirmLogDeletion(); }} /> : null}
      </main>
    </div>
  </div>;
}
