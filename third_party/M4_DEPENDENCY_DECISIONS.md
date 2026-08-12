# M4 dependency decisions

Evidence refreshed: 2026-08-12, Asia/Shanghai.

## Product boundary

M4 introduces the single desktop-first browser SPA under `apps/web/` and the
presentation-only workbench component package under `packages/research-ui/`.
The browser does not embed Pi, write SQLite, execute the formal engine, or
calculate formal Run results. TypeScript control-plane HTTP/SSE endpoints
mediate browser actions, Python remains the durable business writer, and the
Rust/PyO3 artifact remains the only formal calculation result.

No donor UI source is copied. React, Vite, React Flow, CodeMirror, and
Playwright are registry dependencies used through their public APIs.

## Exact direct dependencies

| Package | Exact version | License | Boundary |
|---|---:|---|---|
| `react` | `19.2.8` | MIT | Single SPA component runtime |
| `react-dom` | `19.2.8` | MIT | Single browser renderer |
| `vite` | `8.2.1` | MIT | Development server and production SPA bundler |
| `@vitejs/plugin-react` | `6.0.5` | MIT | Vite React transform integration |
| `@xyflow/react` | `12.11.2` | MIT | Canvas pan, zoom, nodes, edges, and controlled layout |
| `@uiw/react-codemirror` | `4.25.11` | MIT | Controlled strategy source editor component |
| `@codemirror/lang-python` | `6.2.1` | MIT | Python syntax support for the strategy editor |
| `@playwright/test` | `1.62.1` | Apache-2.0 | Real-browser M4 behavior and accessibility oracle |
| `@types/react` | `19.2.18` | MIT | TypeScript build-only React declarations |
| `@types/react-dom` | `19.2.4` | MIT | TypeScript build-only DOM renderer declarations |

The manifests pin every direct version exactly and `pnpm-lock.yaml` freezes the
resolved graph. Vite 8.2.1 and its React plugin require Node `^20.19.0` or
`>=22.12.0`; Playwright 1.62.1 requires Node `>=20`. The repository already
requires Node `>=24.0.0`, so no engine relaxation is introduced.

After the frozen workspace install, `pnpm licenses list --json` succeeded with
202 package records: MIT 109, Apache-2.0 52, BSD-3-Clause 16, ISC 17,
BlueOak-1.0.0 5, MPL-2.0 2, and 0BSD 1. No unknown or unlicensed group was
reported.

## Upstream implementation check

- React installation guidance: https://react.dev/learn/installation
- Vite guide and React templates: https://vite.dev/guide/
- React Flow quick start: https://reactflow.dev/learn
- CodeMirror project documentation: https://codemirror.net/
- Playwright installation and test runner: https://playwright.dev/docs/intro
- Registry metadata and release tarballs: https://www.npmjs.com/

React Flow owns only the editable visual projection. Business relationships
remain derived from the Research Project Graph. CodeMirror owns only the local
draft editor. Saving creates a child WorkspaceRevision through a typed command.
Playwright owns only browser automation and is not shipped in the runtime
bundle.

## Validation oracle

M4 validation combines public Python and Node HTTP behavior tests, TypeScript
builds, a Vite production build, and a Playwright Chromium flow that exercises
Project/Activity selection, immutable strategy edit, merge, Formal Run, Run
Detail, compare, and gated Promote. Browser assertions consume persisted Run
artifacts and deliberately do not recompute metrics.

A dependency version change requires refreshed upstream/license review, a
lockfile diff review, production builds for both UI importers, and the browser
flow on macOS and Ubuntu CI.
