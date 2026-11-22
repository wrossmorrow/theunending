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
- `just mock-jobs` — run the mock external job system server (uvicorn; default port 8080)
- `just test-integration` — run integration tests against a live server

## External job system

- The API enqueues job submissions (`JobRequest`: run id, job type, job params, attempts)
  onto a local async queue; a worker submits the job via
  `POST {job_base_url}/evaluate` or `POST {job_base_url}/batch` (based on the run type)
  and stores the returned `external_run_id` on the run (run status: `SUBMITTED`).
  Job submission calls carry a machine JWT (minted per request from
  `GOOGLE_SERVICE_ACCOUNT_KEY_JSON`, audience `https://admin.theunending.ai`) and a payload
  with `prompt`, `s3_bucket`, `s3_prefix`, `status_update_url`, and `status_update_admin_run_id`.
  When the key is absent, the request is sent without auth (local mock deployments only).
- Inbound job status updates carry the same machine JWT in the `Authorization` header;
  the gateway (Envoy) verifies them against the static machine JWKS, and the Modal public
  endpoint verifies them the same way (`GOOGLE_MACHINE_JWKS` + `GOOGLE_SERVICE_ACCOUNT_EMAIL`).
- Locally, `just up` (docker compose) brings up the mock external job system
  (`mock-jobs`, base URL `http://mock-jobs:8080`) alongside the api and database; the
  api is configured with `JOB_BASE_URL=http://mock-jobs:8080`,
  `ADMIN_BASE_URL=http://api:8000`, and (optionally) `GOOGLE_SERVICE_ACCOUNT_KEY_JSON`.
- For running the server without docker, use `just mock-jobs` and point the api at it via
  the `JOB_BASE_URL` env var (default `http://localhost:8080`).

## Deployment (gateway / Envoy)

The admin stack is fronted by Envoy (see `deploy/envoy.yaml`). Two auth paths are
supported at the gateway:

- **Webpage (cookie, Google OIDC)** — the OAuth2 filter exchanges Google sign-in for a
  signed `IdToken` cookie; `jwt_authn` verifies it and RBAC limits access to the admin
  email. Any request carrying an `Authorization` header bypasses the OAuth2 filter
  (`pass_through_matcher`).
- **Machine (static JWKS)** — requests carrying an `Authorization: Bearer` machine JWT
  are verified against the static public JWKS in the same filter (`machine_jwt` provider,
  audience `https://admin.theunending.ai`) and authorized by RBAC against the service
  account email. The OAuth2 filter is bypassed for these requests.

`admin/deploy/envoy.yaml` ships with placeholders (`__MACHINE_JWKS__`,
`__MACHINE_SA_EMAIL__`). To render it on the host before starting the stack:

```sh
set -a && source .env && set +a
./make-machine-secret.sh   # needs GOOGLE_SERVICE_ACCOUNT_KEY_JSON in .env
```

This is re-runnable only against a pristine copy (restored from git); the script fails
loudly if placeholders are already substituted. The same script also anchors the RBAC
policy for the machine path.

## API

- Health: `GET /health/alive`, `GET /health/ready`
- Models: `GET /api/v0/models` (supported models; first entry is the default)
- Sets: `POST/GET/PATCH/DELETE /api/v0/sets...`, publish at
  `POST /api/v0/sets/{set_id}/publish` (may carry optional `extra_details`, max 512 chars,
  stored on the publish run, forwarded to the publish task, and written to the post draft
  via the `extra` front matter)
- Drafts: `GET/POST /api/v0/sets/{set_id}/drafts...`, commit at
  `POST /api/v0/sets/{set_id}/drafts/{draft_id}/commit`
- Runs: `GET/POST /api/v0/runs...`, status at `PUT /api/v0/runs/{run_id}/status`, cancel at
  `POST /api/v0/runs/{run_id}/cancel` (run must be `SUBMITTED`/`IN_PROGRESS` with an `external_run_id`)

See `admin/DESIGN.md` for the design doc and status-code policy.
