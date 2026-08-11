# M3 dependency and oracle decisions

Evidence refreshed: 2026-08-12, Asia/Shanghai.

## Cleanroom boundary

The formal backtest engine under `crates/quant-engine/` is OQS-owned code. No
QuantBT, quant-assistant, or VibeTrading source is copied, linked as a runtime
dependency, or embedded in the formal artifact. Python calls the single Rust
`run_engine_v1(bytes) -> bytes` seam through PyO3 and does not calculate or
publish a competing formal result.

## Exact direct dependencies

| Package | Exact version | License | Boundary |
|---|---:|---|---|
| `pyo3` | `0.28.3` | MIT OR Apache-2.0 | Optional Rust feature that exposes the byte-identical CPython extension seam |
| `serde` | `1.0.228` | MIT OR Apache-2.0 | Rust input/output serialization with derive support |
| `serde_json` | `1.0.145` | MIT OR Apache-2.0 | Canonical compact JSON byte protocol |
| `maturin` | `1.14.1` | MIT OR Apache-2.0 | Python build/development tool only; not imported by the product runtime |

`Cargo.toml`, `pyproject.toml`, and the Python development dependency group pin
these versions exactly. `Cargo.lock` freezes the Rust transitive graph and
`services/quant-domain/uv.lock` freezes Maturin. At this evidence point their
SHA-256 values are:

- `Cargo.lock`: `8ecb9f2b85bef01dc81f7e40629fe0c0d8c6a67646467681213214a7c5108795`
- `uv.lock`: `8ed546934760df2b873e099d4c42a5f687651c6eae4767da273514d84be3d50d`

The package declares Rust `1.89` as its minimum because the selected Maturin
release requires Rust 1.89. Local engine and PyO3 validation used Rust/Cargo
1.95.0, CPython 3.13, and Maturin 1.14.1. Ubuntu and macOS CI remain separate
required evidence.

## Behavior and rules oracles

- QuantConnect Lean `EquityFillModel.cs` at commit
  `c6cc3b743ed7b65d5e0b9fa2bfc18b7d3ac2aea0` is an Apache-2.0 behavior oracle
  for favorable Limit gaps and adverse Stop gaps. No Lean source is copied.
- The Shanghai Stock Exchange 2026 trading rules are the external rules source
  for the daily A-share 100-share lot, price tick, and T+1 research constraints.
- Python standard-library `Decimal` is an independent test oracle that
  reconciles the M3 synthetic fixture's fills, fees, sell stamp duty, slippage,
  cash, signed positions, equity, and totals. It never becomes a formal writer.

## Distribution and review

The direct Rust packages and Maturin are permissively dual-licensed. Their
upstream manifests and the frozen package metadata are the license evidence;
no dependency source is vendored here. A distributable bundle must retain the
applicable dependency license texts and pass the resolved-license audit. A
future version change requires a fresh upstream implementation/license review,
lock refresh, PyO3 ABI test, Rust contract suite, and Decimal differential test.
