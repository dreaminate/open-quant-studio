# M1 dependency decisions

Evidence date: 2026-08-11, Asia/Shanghai.

M1 contains cleanroom application code only. No QuantBT, quant-assistant,
VibeTrading, Pi, or other donor source was copied. Python standard-library
`sqlite3` owns the database boundary, and Node's built-in `fetch` owns the
TypeScript SSE transport boundary.

The installed wheel metadata and bundled license files under the ignored local
`.venv` were checked after resolution. `uv.lock` freezes the complete graph.

| Package | Version | Relationship | Registry/source | License | M1 purpose |
|---|---:|---|---|---|---|
| `starlette` | `1.6.0` | direct | https://pypi.org/project/starlette/ | BSD-3-Clause | Small ASGI routing/response boundary, including generator-backed SSE |
| `uvicorn` | `0.52.1` | direct | https://pypi.org/project/uvicorn/ | BSD-3-Clause | Loopback ASGI server used by the real HTTP integration test and local service |
| `anyio` | `4.14.2` | Starlette transitive | https://pypi.org/project/anyio/ | MIT | Starlette concurrency substrate |
| `click` | `8.4.2` | Uvicorn transitive | https://pypi.org/project/click/ | BSD-3-Clause | Uvicorn CLI |
| `h11` | `0.16.0` | Uvicorn transitive | https://pypi.org/project/h11/ | MIT | Uvicorn HTTP/1.1 protocol implementation |
| `idna` | `3.18` | AnyIO transitive | https://pypi.org/project/idna/ | BSD-3-Clause | AnyIO hostname handling dependency |

No package source is vendored under `third_party/`. M1 adds no TypeScript
runtime dependency: `FetchDomainEventStreamClient` uses the Node 24 web-stream
and fetch APIs already required by the workspace.
