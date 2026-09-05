FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential ca-certificates tar \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /matraix
COPY pyproject.toml README.md /matraix/
COPY src /matraix/src
COPY environment /matraix/environment
COPY packages /matraix/packages
COPY application /matraix/application
COPY persona /matraix/persona

RUN uv pip install --system --compile-bytecode -e '.[gke]'

ENV PYTHONPATH=/matraix:/matraix/src:/matraix/environment/runtime:/matraix/environment/agents:/matraix/packages/playground/src:/matraix/application/playground
ENV MATRIX_REPO_ROOT=/matraix
