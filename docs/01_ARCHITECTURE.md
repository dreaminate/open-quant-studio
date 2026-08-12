# Architecture

## Runtime shape

```mermaid
flowchart LR
  UI["React/Vite unified SPA"] -->|"HTTP commands"| CP["TypeScript control plane"]
  CP -->|"Pi SDK"| PI["Pi AgentSession"]
  CP -->|"versioned HTTP commands"| PY["Python quant-domain service"]
  PY -->|"SSE domain events"| CP
  PY -->|"PyO3"| RS["OQS cleanroom Rust engine"]
  PY --> DB["SQLite WAL"]
  PY --> CAS["Content-addressed artifacts"]
  CP --> PJ["Pi session JSONL"]
  UI -->|"SSE projection"| CP
```

## Capability authority

| Capability | Authority |
|---|---|
| LLM turn, branch, compaction, steer/follow-up | Pi through the TypeScript adapter |
| Active sessions, workbench binding, live routing | TypeScript control plane |
| Project, task, context, inbox/outbox, revision, variant, run metadata | Python domain service |
| Formal backtest calculations | OQS-owned cleanroom Rust/PyO3 engine |
| Relationship and lineage truth | Research Project Graph in the domain service |
| Visual projection and interaction | One React/Vite SPA |
| Raw conversation tree | Pi JSONL |
| Large immutable output | Content-addressed artifact store |

## Process rules

- No iframe, microfrontend, duplicated SPA, Redis, gRPC, or second message bus in the POC.
- No always-on supervisor LLM.
- No second workflow executor inside the infinite canvas.
- Active live routing is in-process. Durable coordination is persisted through the Python service.
- Large payloads cross process boundaries by artifact reference.
- Python invokes the formal engine and durably records its typed result; neither TypeScript nor the SPA writes formal business state.
- Pi built-in shell/filesystem/edit/write are disabled by default.
- Shell output is diagnostic until a typed domain command validates and registers it. It cannot become a Run, metric, or Canonical Context by itself.
- The POC runs at most one Formal Run concurrently and proves at most two active Pi sessions; no distributed scheduler is part of this architecture.

## Recovery

After restart, the control plane reconstructs active state from Pi JSONL, the durable session catalog, inbox/outbox, task/job state, and the event ledger. In-memory handles are never treated as durable proof.
