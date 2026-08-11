# Backtest specifications

## M0 non-formal accounting oracle

`m0-long-short-v1.json` is an executable accounting oracle over the synthetic
CSV in `../market/`. It freezes one closed long and one closed short round trip,
including the `0.0006` fee on every entry and exit side.

This fixture is not a formal Run, donor output, market claim, or integrated
engine result. The Rust/PyO3 authority remains absent in M0. A future formal
engine integration passes this oracle only when its fills, signed positions,
cash, equity, fees, and summary match the frozen expectations.

## M3 formal engine contract

`m3-a-share-long-short-v1.json` is an OQS-owned synthetic contract fixture for
the real cleanroom Rust/PyO3 engine. It freezes one daily A-share long round
trip and one explicitly hypothetical `research_short` round trip with T+1,
100-share lots, commission, sell stamp duty, fixed adverse slippage, cash,
equity, and summary metrics. It is a deterministic product test, not a market
performance claim or evidence of ordinary cash-account shorting capability.
