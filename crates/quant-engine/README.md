# crates/quant-engine

This package owns the OQS cleanroom Rust/PyO3 formal backtest engine. Donor
engine source is excluded. The engine accepts one versioned JSON byte protocol
and Rust remains authoritative for fills, orders, signed positions, cash or
wallet accounting, fees, stamp duty, funding, slippage, equity, drawdown, and
metrics.

The current M3 slice supports daily A-share cash research with 100-share lots,
T+1, tradability flags, Market/Limit/Stop, DAY/GTC, conservative OCO
`stop-first`, long and labelled `research_short`; and T+0 1x linear-perpetual
crypto research with long/short, maker/taker fees, slippage, and typed funding.
It uses checked `i128` atoms and does not force final liquidation.

Validation entrypoints:

```bash
cargo test --manifest-path crates/quant-engine/Cargo.toml
uv run --project services/quant-domain --frozen maturin develop --manifest-path crates/quant-engine/Cargo.toml
uv run --project services/quant-domain --frozen python crates/quant-engine/tests/test_python_binding.py
```

Exact dependency, license, cleanroom, and oracle decisions are recorded in
`third_party/M3_DEPENDENCY_DECISIONS.md`. The Python domain wraps the byte-exact
engine result in immutable RunSpec/Run, intent-tape, result, manifest, gate, and
validation records; typed two-parent merge and CAS Promote remain outside this
crate and are verified by the M3 domain/control-plane gate.
