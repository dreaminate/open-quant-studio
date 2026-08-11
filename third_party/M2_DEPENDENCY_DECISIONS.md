# M2 dependency decisions

Evidence refreshed: 2026-08-11 21:20 CST, Asia/Shanghai.

## Source boundary

M2 copies no source from QuantBT, quant-assistant, VibeTrading, or Session
Fabric prior-art repositories. Open Quant Studio owns the adapter, typed HTTP
client, routing, recall, and inbox glue added in this repository. Pi is consumed
only as an exact registry dependency and remains the sole AgentLoop.

## Pi release identity

| Evidence | Verified value |
|---|---|
| Canonical repository | `https://github.com/earendil-works/pi.git` |
| Release | tag `v0.84.1` |
| Tag commit and npm `gitHead` | `53fa77ccd8a279eb87e92294ef3687b03ff80112` |
| License | MIT; the exact tag's MIT legal text and attribution are retained at `third_party/licenses/PI_MIT.txt` |
| Node requirement | Pi requires `>=22.19.0`; the OQS control-plane requires Node `>=24.0.0` |
| Point-in-time mutable `main` | `b6557f43ec3cc93b5808a073e44a7c2ded75978d` when queried; not used as the dependency identity |

The published coding-agent tarball declares MIT and the repository above but
does not contain a license file in its installed package directory. The tag's
MIT legal text and attribution are therefore retained explicitly. A future distribution
must include third-party notices rather than assuming registry metadata alone
is sufficient.

## Direct registry packages

| Package | Version | Integrity | License | Purpose |
|---|---:|---|---|---|
| `@earendil-works/pi-coding-agent` | `0.84.1` | `sha512-ncAqFrG+iybuPGOhMiZoEHkEzTpJgz3guYD32pD+M7ucc0WeHmauP6wa7qwP8V/KWvsZDVNa5XGsdZ7fkC7w7A==` | MIT | Production Pi `AgentSession`, session manager, resource boundary, and typed tools |
| `@earendil-works/pi-agent-core` | `0.84.1` | `sha512-evyzXYWCLQGmcaBYHlmSku02r8qoN4SGI60GZABo6iV+H+nqX+P9ud8fEZ4GmRq9mUSREvvfX+w9dA9ThF9C6w==` | MIT | Explicit test dependency for the official runtime seam |
| `@earendil-works/pi-ai` | `0.84.1` | `sha512-wMsAdJMxuNri08vLqTyYVI201DQQezGhPSTkzYsHdw5dYX3rCNwEmSvpaAwhi7ELKI/2tE/CEgSWg/6iRxSgdQ==` | MIT | Official faux provider used by no-key tests |
| `typebox` | `1.3.7` | `sha512-meKuifc33Pccx0O6PdIzYMq3Og8zvP4TIi/a+Bw3AEMZMxOD0+RHGQvpglEe6Zdy3wZ8nqn/j95h8LUZLk/6Hg==` | MIT | Pi custom-tool parameter schemas |

All versions are exact in `apps/control-plane/package.json`; `pnpm-lock.yaml`
freezes the resolved graph and repeats the registry integrities.

## Resolved-license audit

`pnpm licenses list --json` succeeded against the installed frozen workspace.
It reported 136 package records in these license groups: MIT 60, Apache-2.0 48,
BSD-3-Clause 14, BlueOak-1.0.0 5, ISC 8, and 0BSD 1. No unknown,
proprietary, copyleft, or restrictive license group was reported.

The Pi coding-agent graph includes `@silvia-odwyer/photon-node` and the optional
`@mariozechner/clipboard` platform packages. They are dependency artifacts, not
OQS tools: the adapter disables Pi's built-in read/bash/edit/write surface and
loads only the named OQS custom tools. The current installed workspace occupies
204 MiB under `node_modules`; nothing was installed globally.

This is local macOS evidence. CI on other platforms and future package versions
require their own frozen install and license audit.
