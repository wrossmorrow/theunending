ARG PYTHON_VERSION=3.12-slim
FROM python:${PYTHON_VERSION} AS base

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-urw-base35 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_NO_DEV=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock README.md ./

ARG UV_GROUP=publish
ENV APP_MODULE=${UV_GROUP}
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group ${UV_GROUP} --no-install-project

COPY src/${UV_GROUP} src/${UV_GROUP}

ENV PYTHONPATH=/app/src
ENTRYPOINT ["python", "-m"]
