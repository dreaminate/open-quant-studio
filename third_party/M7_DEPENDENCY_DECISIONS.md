# M7 dependency decisions

Evidence refreshed: 2026-08-12, Asia/Shanghai.

## Product boundary

M7 adds local CSV and Parquet import under `services/quant-domain/`. PyArrow
owns file decoding and Arrow table conversion through its public Python APIs.
OQS-owned code owns field mapping, row-numbered validation, canonical market
input construction, immutable DataSnapshot identity, CAS persistence, and the
Formal Run handoff.

No donor data-loader source is copied. M7 does not add an online market-data
provider or a second data-processing service.

## Exact direct dependency

| Package | Exact version | License | Boundary |
|---|---:|---|---|
| `pyarrow` | `25.0.0` | Apache-2.0 | Local CSV/Parquet decoding and schema-aware table conversion |

`services/quant-domain/pyproject.toml` pins the exact version and
`services/quant-domain/uv.lock` freezes the source archive and platform wheels.
The CPython 3.13 wheel hashes used by the required development and CI platforms
include:

- macOS arm64: `8831a3ba52fa7cdb78d368d968b1dcd06171e6dff5461e16d90de91d371e47bc`
- Linux aarch64: `59516c822d5fd8e544aaa0dfe72f36fed5d4c24ea8390aab1bcd31d7e959c6be`
- Linux x86_64: `6f9dbd83e91c239a1f5ee7ce13f108b5f6c0efbe40a4375260d8f08b43ad05e9`

The installed package metadata reports `License-Expression: Apache-2.0` and
ships its applicable license and notice files inside the wheel. No dependency
source is vendored in this repository.

## Upstream implementation check

- Apache Arrow CSV reader: https://arrow.apache.org/docs/python/csv.html
- Apache Arrow Parquet `read_table`: https://arrow.apache.org/docs/python/generated/pyarrow.parquet.read_table.html
- Apache Arrow Python installation and platform support: https://arrow.apache.org/docs/python/install.html
- Apache Arrow source repository: https://github.com/apache/arrow

The selected APIs support the two required local formats without introducing a
second dataframe runtime or a handwritten parser. OQS converts their table
output into one canonical row model before applying the same validation and
snapshot identity logic to both formats.

## Validation oracle

M7 validation must cover identical CSV and Parquet rows producing the same
normalized snapshot identity, row-numbered mapping errors, A-share and crypto
sample imports, local `imports/` discovery, and immediate use of the created
snapshot by the Rust/PyO3 Formal Run path.

A PyArrow version change requires a lockfile diff review, refreshed package
metadata/license evidence, CSV/Parquet parity tests, and the M7 browser vertical
on macOS and Ubuntu CI.
