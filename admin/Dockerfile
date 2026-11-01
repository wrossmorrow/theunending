FROM python:3.14-slim

WORKDIR /app

COPY admin/pyproject.toml admin/uv.lock ./
COPY admin/ ./

RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "api.main:api", "--host", "0.0.0.0", "--port", "8000"]
