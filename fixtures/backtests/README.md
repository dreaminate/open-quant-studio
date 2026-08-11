# M0 golden backtest specification

`m0-long-short-v1.json` is an executable accounting oracle over the synthetic
CSV in `../market/`. It freezes one closed long and one closed short round trip,
including the `0.0006` fee on every entry and exit side.

This fixture is not a formal Run, donor output, market claim, or integrated
engine result. The Rust/PyO3 authority remains absent in M0. A future formal
engine integration passes this oracle only when its fills, signed positions,
cash, equity, fees, and summary match the frozen expectations.
