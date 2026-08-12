import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Background, Controls, ReactFlow, useEdgesState, useNodesState, type Edge, type Node } from "@xyflow/react";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import "@xyflow/react/dist/style.css";
import { createResearchApi, ResearchApiError, type ResearchApi } from "./api.js";
import type {
  Activity,
  ChatEvent,
  ComparisonChange,
  Context,
  LogEntry,
  Project,
  Revision,
  RevisionComparison,
  RunDetail,
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

const NAV_ITEMS: Array<{ id: WorkbenchId; label: string; description: string }> = [
  { id: "canvas", label: "Canvas", description: "Project graph" },
  { id: "chat", label: "Pi Chat", description: "Bounded session" },
  { id: "code", label: "Code", description: "Strategy.py" },
  { id: "compare", label: "Compare", description: "Revision diff" },
  { id: "backtest", label: "Backtest", description: "Formal action" },
  { id: "forward-test", label: "Forward Test", description: "M4 boundary" },
  { id: "run-detail", label: "Run Detail", description: "Immutable artifact" },
  { id: "data", label: "Data", description: "M4 boundary" },
  { id: "logs", label: "Logs", description: "Run-scoped logs" },
  { id: "settings", label: "Settings", description: "M4 boundary" },
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
  const record = value as Record<string, unknown>;
  const identity = record.trade_id
    ?? record.event_id
    ?? (record.intent_id === undefined ? undefined : `${record.intent_id}:${record.session_seq ?? ""}`)
    ?? (record.session_seq === undefined ? undefined : record.session_seq);
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

function getCodeFromRevision(revision: Revision | undefined): string {
  const file = revision?.files.find((entry) => entry.path === "strategy.py") ?? revision?.files[0];
  return file?.body ?? "";
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

function BoundaryView({ title, body }: { title: string; body: string }) {
  return <section className="oqs-panel oqs-boundary"><p className="oqs-kicker">CURRENT M4 BOUNDARY</p><h2>{title}</h2><p>{body}</p><p className="oqs-muted">The surface is intentionally explicit until its durable contract lands.</p></section>;
}

function CodeView({
  code,
  setCode,
  revision,
  onSave,
  onCompare,
  onCreateVariant,
  busy,
}: {
  code: string;
  setCode: (value: string) => void;
  revision: Revision | undefined;
  onSave: () => void;
  onCompare: () => void;
  onCreateVariant: () => void;
  busy: boolean;
}) {
  return <section className="oqs-code-layout">
    <div className="oqs-panel oqs-code-editor">
      <div className="oqs-panel-heading"><div><p className="oqs-kicker">AUTHORITATIVE SOURCE</p><h2>strategy.py</h2></div><span className="oqs-chip">{revision ? `rev ${shortId(revision.revision_id)}` : "no revision"}</span></div>
      <CodeMirror value={code} height="520px" extensions={[python()]} onChange={setCode} basicSetup={{ lineNumbers: true, foldGutter: true }} />
      <div className="oqs-action-row"><button className="oqs-button oqs-button-primary" onClick={onSave} disabled={busy || !revision}>Save child revision</button><button className="oqs-button" onClick={onCompare} disabled={!revision}>Compare</button><button className="oqs-button" onClick={onCreateVariant} disabled={busy}>Fork variant</button></div>
    </div>
    <aside className="oqs-panel oqs-side-detail"><p className="oqs-kicker">REVISION PROVENANCE</p><dl className="oqs-kv"><dt>Revision</dt><dd>{revision?.revision_id ?? "—"}</dd><dt>Tree</dt><dd>{revision?.git_tree_oid ?? "—"}</dd><dt>Commit</dt><dd>{revision?.git_commit_oid ?? "—"}</dd><dt>Files</dt><dd>{revision?.files.length ?? 0}</dd></dl><p className="oqs-muted">Saving submits a typed child-revision command. It never overwrites a concurrent head.</p></aside>
  </section>;
}

function ComparisonView({ comparison, onMerge, busy }: { comparison: { left: Revision | undefined; right: Revision | undefined; result: RevisionComparison | undefined }; onMerge: () => void; busy: boolean }) {
  const changes = comparison.result?.changes ?? [];
  return <section className="oqs-panel"><div className="oqs-panel-heading"><div><p className="oqs-kicker">IMMUTABLE REVISION COMPARE</p><h2>Path and hash changes</h2></div><button className="oqs-button oqs-button-primary" onClick={onMerge} disabled={busy || changes.length === 0}>Create merge candidate</button></div><div className="oqs-compare-meta"><span>Left {shortId(comparison.result?.left_revision_id ?? comparison.left?.revision_id)}</span><span>Right {shortId(comparison.result?.right_revision_id ?? comparison.right?.revision_id)}</span></div>{changes.length === 0 ? <EmptyState title="No changed paths" body="Select two distinct revisions or save a child revision before comparing." /> : <div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>Path</th><th>Status</th><th>Left SHA-256</th><th>Right SHA-256</th></tr></thead><tbody>{changes.map((change) => <tr key={change.path}><td className="oqs-mono">{change.path}</td><td>{change.status ?? "changed"}</td><td className="oqs-mono">{change.left_sha256 ?? "—"}</td><td className="oqs-mono">{change.right_sha256 ?? "—"}</td></tr>)}</tbody></table></div>}</section>;
}

function EngineRecordTable({ label, value }: { label: string; value: unknown }) {
  if (!Array.isArray(value)) return null;
  return <div className="oqs-detail-block"><h3>{label.replaceAll("_", " ")}</h3><div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>#</th><th>Record</th></tr></thead><tbody>{value.slice(0, 200).map((item, index) => <tr key={engineRecordKey(label, item)}><td>{index}</td><td><pre>{renderValue(item)}</pre></td></tr>)}</tbody></table></div></div>;
}

function RunDetailView({ detail, onPromote, busy }: { detail: RunDetail | undefined; onPromote: () => void; busy: boolean }) {
  const manifest = detail?.manifest;
  const runSpec = detail?.run_spec ?? (typeof manifest?.run_spec === "object" && manifest.run_spec !== null ? manifest.run_spec as Record<string, unknown> : undefined);
  const engine = detail?.engine_result ?? (typeof detail?.formal_engine_result === "object" && detail.formal_engine_result !== null ? detail.formal_engine_result as Record<string, unknown> : undefined);
  const run = detail?.run;
  if (!detail) return <EmptyState title="No Run selected" body="Run a validated candidate to inspect its immutable formal artifact." />;
  return <section className="oqs-run-detail"><div className="oqs-panel"><div className="oqs-panel-heading"><div><p className="oqs-kicker">IMMUTABLE FORMAL ARTIFACT</p><h2>Run Detail</h2></div><div className="oqs-heading-actions"><span className="oqs-status">{run?.status ?? "returned"}</span><button className="oqs-button oqs-button-primary" onClick={onPromote} disabled={busy || run?.status !== "succeeded"}>Promote</button></div></div><dl className="oqs-kv oqs-kv-grid"><dt>RunSpec</dt><dd>{runSpec ? "bound" : "—"}</dd><dt>Run ID</dt><dd className="oqs-mono">{run?.run_id ?? "—"}</dd><dt>Validation</dt><dd>{typeof detail.validation?.outcome === "string" ? detail.validation.outcome : "—"}</dd><dt>Candidate revision</dt><dd className="oqs-mono">{run?.candidate_revision_id ?? "—"}</dd></dl>{runSpec ? <div className="oqs-detail-block"><h3>RunSpec fields</h3><pre>{renderValue(runSpec)}</pre></div> : null}</div>{engine ? <div className="oqs-panel"><div className="oqs-panel-heading"><div><p className="oqs-kicker">RUST ENGINE OUTPUT</p><h2>Orders, trades, positions, and metrics</h2></div><span className="oqs-chip">{typeof engine.engine_version === "string" ? engine.engine_version : "formal"}</span></div><div className="oqs-metric-grid">{typeof engine.metrics === "object" && engine.metrics !== null ? Object.entries(engine.metrics).map(([key, value]) => <div className="oqs-metric" key={key}><span>{key.replaceAll("_", " ")}</span><strong>{renderValue(value)}</strong></div>) : <EmptyState title="Metrics unavailable" body="The formal engine did not include a metrics object in this artifact." />}</div>{["orders", "trades", "positions", "cash_ledger", "funding_ledger", "equity_curve", "drawdown_curve"].map((key) => <EngineRecordTable key={key} label={key} value={engine[key]} />)}<div className="oqs-detail-block"><h3>Costs and assumptions</h3><pre>{renderValue({ costs: engine.costs, assumptions: engine.assumptions })}</pre></div></div> : <EmptyState title="Engine result not embedded" body="The API returned a Run envelope without an engine result artifact." />}{manifest ? <div className="oqs-panel"><div className="oqs-panel-heading"><div><p className="oqs-kicker">PROVENANCE / GATES / LOGS</p><h2>Manifest</h2></div></div><pre>{renderValue({ run_spec: runSpec, revision: manifest.revision, engine_input: manifest.engine_input, strategy_execution: manifest.strategy_execution, gates: manifest.gates, logs: manifest.logs })}</pre></div> : null}{detail.logs ? <div className="oqs-panel"><div className="oqs-panel-heading"><div><p className="oqs-kicker">RUN-SCOPED LOGS</p><h2>Logs</h2></div><span className="oqs-chip">{detail.logs.length} entries</span></div><div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>Level</th><th>Priority</th><th>Event</th><th>Message</th></tr></thead><tbody>{detail.logs.map((log) => <tr key={logRecordKey(log)}><td>{log.level ?? "—"}</td><td>{log.priority ?? "—"}</td><td className="oqs-mono">{log.event_code ?? "—"}</td><td>{log.message ?? "—"}</td></tr>)}</tbody></table></div></div> : null}</section>;
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
  const [logs, setLogs] = useState<LogEntry[]>([]);
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

  const reportError = useCallback((value: unknown) => {
    if (value instanceof ResearchApiError) setError(`${value.code}: request failed`);
    else if (value instanceof Error) setError(value.message);
    else setError("Request failed");
  }, []);

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
    if (!selectedRunId) {
      setRunDetail(undefined);
      setLogs([]);
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
        const nextRuns = await api.listRuns(projectId);
        if (cancelled) return;
        setRunDetail(detail);
        setLogs(detail.logs ?? []);
        setRuns(nextRuns);
        stop();
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
      const files = revision.files.map((file) => ({
        path: file.path,
        body: file.path === "strategy.py" ? code : file.body,
      }));
      const response = await api.createChildRevision({ projectId, activityId, variantId: selectedVariant.variant_id, baseRevisionId: revision.revision_id, expectedRevisionId: revision.revision_id, message: "Edit strategy.py from OQS Code workbench", files });
      const createdRevisionId = getRevisionId(response);
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
      if (candidate) candidateRevisionId.current = candidate;
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [activityId, api, comparison.result, projectId, reportError, revision, selectedVariant]);

  const formalRun = useCallback(async () => {
    const candidateRevisionIdToRun = candidateRevisionId.current || comparison.result?.right_revision_id || revision?.revision_id || selectedVariant?.head_revision_id;
    if (!candidateRevisionIdToRun) return;
    setBusy(true);
    setError(undefined);
    try {
      const response = await api.requestFormalRun(candidateRevisionIdToRun);
      const runId = getRunId(response);
      setNotice(runId ? `Formal Run ${shortId(runId)} queued` : "Formal Run command accepted");
      const nextRuns = await api.listRuns(projectId, activityId || undefined);
      setRuns(nextRuns);
      if (runId) setSelectedRunId(runId);
      setWorkbench("backtest");
    } catch (value) {
      reportError(value);
    } finally {
      setBusy(false);
    }
  }, [activityId, api, comparison.result, projectId, reportError, revision, selectedVariant]);

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
    <header className="oqs-topbar"><div className="oqs-brand"><span className="oqs-mark">OQ</span><div><strong>Open Quant Studio</strong><span>local research workstation</span></div></div><div className="oqs-selectors"><label>Project<select data-testid="project-selector" value={projectId} onChange={(event) => { setProjectId(event.target.value); setActivityId(""); }}><option value="">Select project</option>{projects.map((project) => <option value={project.project_id} key={project.project_id}>{project.name ?? shortId(project.project_id)}</option>)}</select></label><label>Activity<select data-testid="activity-selector" value={activityId} onChange={(event) => setActivityId(event.target.value)}><option value="">Select activity</option>{activities.map((activity) => <option value={activity.activity_id} key={activity.activity_id}>{activity.name ?? shortId(activity.activity_id)}</option>)}</select></label></div><div className="oqs-context"><span>{projectLabel} / {activityLabel}</span><span className={context?.isStreaming ? "oqs-live" : "oqs-muted"}>{context?.isStreaming ? "Pi streaming" : "local context"}</span></div></header>
    <div className="oqs-body"><aside className="oqs-sidebar"><div className="oqs-sidebar-title">WORKBENCH</div>{NAV_ITEMS.map((item) => <button key={item.id} className={`oqs-nav-item ${workbench === item.id ? "is-active" : ""}`} onClick={() => setWorkbench(item.id)}><span>{item.label}</span><small>{item.description}</small></button>)}<div className="oqs-sidebar-footer"><span className="oqs-dot" />Research-only mode</div></aside>
      <main className="oqs-main"><div className="oqs-main-heading"><div><p className="oqs-kicker">{projectLabel} · {activityLabel}</p><h1>{NAV_ITEMS.find((item) => item.id === workbench)?.label}</h1></div><div className="oqs-heading-actions">{selectedRunId ? <button className="oqs-button" onClick={() => setWorkbench("run-detail")}>Open Run {shortId(selectedRunId)}</button> : null}<button className="oqs-button" onClick={formalRun} disabled={busy || !revision}>Run formal</button></div></div><ErrorNotice error={error} />{notice ? <div className="oqs-notice" role="status">{notice}<button onClick={() => setNotice(undefined)} aria-label="Dismiss notice">×</button></div> : null}
        {workbench === "canvas" ? <section className="oqs-canvas-layout"><div className="oqs-panel oqs-canvas"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onNodeClick={(_, node) => setSelectedNode(node.id)} onNodeDragStop={() => { if (projectId && activityId) localStorage.setItem(`oqs:canvas:${projectId}:${activityId}`, JSON.stringify(nodes.map((node) => ({ id: node.id, position: node.position })))); }} proOptions={{ hideAttribution: true }}><Controls /><Background gap={20} size={1} /></ReactFlow></div><aside className="oqs-panel oqs-node-detail"><p className="oqs-kicker">SELECTED GRAPH NODE</p>{selectedNodeDetail ? <><span className="oqs-chip">{selectedNodeDetail.data.kind}</span><h2>{selectedNodeDetail.data.title}</h2><p>{selectedNodeDetail.data.detail}</p><dl className="oqs-kv"><dt>Node ID</dt><dd className="oqs-mono">{selectedNodeDetail.id}</dd><dt>Position</dt><dd>{Math.round(selectedNodeDetail.position.x)}, {Math.round(selectedNodeDetail.position.y)}</dd></dl></> : <EmptyState title="Select a node" body="Drag nodes to shape the project graph. Layout is persisted per project and activity." />}</aside></section> : null}
        {workbench === "chat" ? <section className="oqs-panel oqs-chat"><div className="oqs-panel-heading"><div><p className="oqs-kicker">SAFE PI SURFACE</p><h2>Pi Chat</h2></div><span className="oqs-chip">{chatConnected ? "Pi connected" : "connecting…"}</span></div><div className="oqs-chat-history">{chatMessages.length === 0 ? <EmptyState title="Ask about this Activity" body="Only bounded prompt responses and safe SSE events are shown here." /> : chatMessages.map((message) => <div key={message.id} className={`oqs-chat-message ${message.role}`}><span>{message.role === "user" ? "You" : "Pi"}</span><p>{message.text}</p></div>)}</div><form className="oqs-chat-form" onSubmit={(event) => { event.preventDefault(); void sendChat(); }}><input value={chatInput} onChange={(event) => setChatInput(event.target.value)} placeholder="Ask Pi about this research context…" aria-label="Chat prompt" /><button type="submit" className="oqs-button oqs-button-primary" disabled={!chatConnected || !chatInput.trim()}>Send</button></form></section> : null}
        {workbench === "code" ? <CodeView code={code} setCode={setCode} revision={revision} onSave={() => { void saveChildRevision(); }} onCompare={() => { void compare(); }} onCreateVariant={() => { void forkVariant(); }} busy={busy} /> : null}
        {workbench === "compare" ? <ComparisonView comparison={comparison} onMerge={() => { void merge(); }} busy={busy} /> : null}
        {workbench === "backtest" ? <section className="oqs-backtest-layout"><div className="oqs-panel"><p className="oqs-kicker">FORMAL ENGINE ACTION</p><h2>Backtest</h2><p>Runs are created by the Python domain and Rust formal engine. This surface only submits the typed request and reports returned status.</p><div className="oqs-action-row"><button className="oqs-button oqs-button-primary" onClick={() => { void formalRun(); }} disabled={busy || !revision}>Request formal Run</button>{selectedRunId ? <button className="oqs-button" onClick={() => setWorkbench("run-detail")}>View Run Detail</button> : null}</div></div><div className="oqs-panel"><div className="oqs-panel-heading"><div><p className="oqs-kicker">RUN QUEUE</p><h2>Activity Runs</h2></div><span className="oqs-chip">{runs.length} total</span></div>{runs.length === 0 ? <EmptyState title="No formal Runs" body="Save or merge a candidate, then request a formal Run." /> : <div className="oqs-run-list">{runs.map((run) => <button key={run.run_id} className={`oqs-run-row ${selectedRunId === run.run_id ? "is-active" : ""}`} onClick={() => setSelectedRunId(run.run_id)}><span className="oqs-mono">{shortId(run.run_id)}</span><span>{run.status ?? "unknown"}</span><span>{timestamp(run.finished_at ?? run.created_at)}</span></button>)}</div>}</div></section> : null}
        {workbench === "run-detail" ? <RunDetailView detail={runDetail} onPromote={() => { void promote(); }} busy={busy} /> : null}
        {workbench === "forward-test" ? <BoundaryView title="Forward Test" body="M4 exposes the navigation surface only. Historical walk-forward/replay, checkpointing, and restart recovery are scheduled for the M5 durable lifecycle slice." /> : null}
        {workbench === "data" ? <BoundaryView title="Data" body="M4 reads the selected project/activity and immutable Run artifacts. CSV/Parquet import and DataSnapshot creation are an M7 boundary." /> : null}
        {workbench === "settings" ? <BoundaryView title="Settings" body="M4 keeps local context and API base same-origin. Provider, model, and trusted-local settings remain owned by the Pi adapter and control plane." /> : null}
        {workbench === "logs" ? <section className="oqs-panel"><div className="oqs-panel-heading"><div><p className="oqs-kicker">RUN-SCOPED ONLY</p><h2>Logs</h2></div><span className="oqs-chip">{selectedRunId ? `Run ${shortId(selectedRunId)}` : "no Run"}</span></div>{!selectedRunId ? <EmptyState title="Select a Run" body="Logs are intentionally scoped to the selected immutable Run." /> : logs.length === 0 ? <EmptyState title="No Run logs returned" body="The API returned no selected-Run log entries." /> : <div className="oqs-table-wrap"><table className="oqs-table"><thead><tr><th>Level</th><th>Priority</th><th>Event</th><th>Message</th><th>At</th></tr></thead><tbody>{logs.map((log) => <tr key={logRecordKey(log)}><td>{log.level ?? "—"}</td><td>{log.priority ?? "—"}</td><td className="oqs-mono">{log.event_code ?? "—"}</td><td>{log.message ?? "—"}</td><td>{timestamp(log.timestamp ?? log.created_at)}</td></tr>)}</tbody></table></div>}</section> : null}
      </main>
    </div>
  </div>;
}
