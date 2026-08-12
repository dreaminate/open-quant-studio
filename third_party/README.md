# Third-party provenance

No donor source is imported at repository bootstrap.

Open Quant Studio's own source is released under the root MIT `LICENSE`. That
license does not change any donor boundary. Exact third-party notices remain
under this directory and are shipped with distributions that include the
corresponding dependency.

Before adding a migrated file or vendored dependency, record:

- upstream name and canonical URL
- exact commit or reviewed source snapshot
- license file and applicable notices
- original paths and destination paths
- whether the source snapshot was clean
- local modifications
- behavior or differential tests used as an oracle

M0's no-copy decisions and registry dependency licenses are recorded in
`M0_IMPORT_DECISIONS.md`.

M1's cleanroom HTTP/SSE dependency boundary and resolved runtime licenses are
recorded in `M1_DEPENDENCY_DECISIONS.md`.

M2's exact Pi release identity, registry integrities, retained MIT notice, and
resolved-license audit are recorded in `M2_DEPENDENCY_DECISIONS.md`.

M3 uses an OQS-owned cleanroom engine. Its exact Rust/PyO3 dependencies,
build-only Maturin boundary, license evidence, behavior oracles, and independent
Decimal reconciliation are recorded in `M3_DEPENDENCY_DECISIONS.md`.

M4's single-SPA React/Vite boundary, React Flow projection, CodeMirror editor,
Playwright browser oracle, exact versions, and licenses are recorded in
`M4_DEPENDENCY_DECISIONS.md`.

PSM/byteowlz material may not be copied from the reviewed unlicensed snapshots. MCP Agent Mail may not be copied, run, tested, or integrated because of its restrictive license rider. See `docs/06_MIGRATION_MAP.md`.
