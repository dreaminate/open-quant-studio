# Third-party provenance

No donor source is imported at repository bootstrap.

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

PSM/byteowlz material may not be copied from the reviewed unlicensed snapshots. MCP Agent Mail may not be copied, run, tested, or integrated because of its restrictive license rider. See `docs/06_MIGRATION_MAP.md`.
