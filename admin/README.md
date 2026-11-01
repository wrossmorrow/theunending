# Unending Admin API

HTTP API for The Unending, a business application for relentless generative
image creation.

It makes "sets", makes "set drafts", commits a draft as the set, and stores and
surfaces data through the API over which an interactive webpage can later be
built.

## Toolchain

- python 3.14+
- uv for venv/package management
- fastapi for the HTTP server
- pydantic/pydantic-settings for data models and env-var-driven settings
- sqlmodel for database models
- httpx for external job system calls
- containerized with docker; database is relational (SQLite for tests/local, Postgres presumed for prod)

## Local development

- `just install` — install dependencies
- `just format` — format code (ruff)
- `just lint` — lint code (ruff)
- `just typecheck` — type check (mypy)
- `just test` — run unit tests
- `just run` — run the local server (uvicorn; override host/port as needed)

## API

- Health: `GET /health/alive`, `GET /health/ready`
- Sets: `POST/GET/PATCH/DELETE /api/v0/sets...`
- Drafts: `GET/POST /api/v0/sets/{set_id}/drafts...`, commit at
  `POST /api/v0/sets/{set_id}/drafts/{draft_id}/commit`
- Runs: `GET/POST /api/v0/runs...`, status at `PUT /api/v0/runs/{run_id}/status`

See `admin/DESIGN.md` for the design doc and status-code policy.
