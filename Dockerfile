FROM rust:1.89-bookworm AS rust-toolchain

FROM ghcr.io/astral-sh/uv:0.11.23 AS uv-toolchain

FROM node:24-bookworm

COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup
COPY --from=uv-toolchain /uv /uvx /bin/

ENV CARGO_HOME=/usr/local/cargo
ENV RUSTUP_HOME=/usr/local/rustup
ENV PATH=/usr/local/cargo/bin:${PATH}

RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && corepack enable \
    && corepack install --global pnpm@11.21.0 \
    && uv python install 3.13

WORKDIR /app

COPY . .

RUN pnpm config set --location global strictDepBuilds false \
    && pnpm install --frozen-lockfile \
    && uv sync --project services/quant-domain --frozen \
    && pnpm run build \
    && pnpm run prepare:engine-pyo3

ENV OQS_DATA_ROOT=var/m10-compose
ENV OQS_PORT=4173
ENV OQS_DOMAIN_PORT=8765
ENV OQS_HOST=0.0.0.0

EXPOSE 4173

ENTRYPOINT ["node", "scripts/run-m4-local.mjs"]
