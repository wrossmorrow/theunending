
# Introduction

We're going to work on an HTTP API we'll run in AWS to
* make "sets"
* make "set drafts"
* commit a "draft" as "the" "set"
* store and surface data through the API we can build an interactive webpage over

**Goal:** This is to be a deployed API a team of maintainers will depend on working reliably for as long as a project lasts. We are not scripting, we are building a business application.

# Toolchain

We're going to use :
* python 3.14+ (if you need a toolchain update, I can do that)
* use uv for venv/package management
* fastapi for the HTTP server
* pydantic for data models
* pydantic-settings for data-modeled env vars
* httpx (not requests) for any HTTP client needs
    * note we will need to be concious of timeouts with httpx
* application will be containerized with docker
* a database, presumably a relational database but we can discuss
    * we can test with SQLite and presume postgres is running
    * reasons: 
        * the maintainer is used to RDBMS
        * there are transcational data updates, immutable stores will not work
        * there are obvious "relations" between the resources
    * assuming that, lets use SQLModel with an async engine
        * tests: SQLite via aiosqlite
        * presume postgres via asyncpg

# General

* _no_ .env files will used by the code, just env vars
* there _can_ be yaml config files if helpful
* the API code will be run in AWS, with an AWS IAM role with scoped permissions to AWS services; no keys
* the API will be an HTTP (HTTP/1.1) service
* the API does _not_ need to be gated by authentication, every request to it will be valid
* the API code needs to implement a generic error handler and through that always return valid JSON response bodies
* POST/PUT/PATCH requests must have request bodies defined in clear pydantic classes
* API responses cannot be lists, every response must be an object; if a list is returned that should be in a field like "items" or similar
* API errors must all respond with a details field that described the reason for the error
* all status code references should use enums (fastapi.status works)
* in fact, avoid "magic numbers" everywhere in the code, use settings
* we will not use "plain dicts", we should type all data with pydantic classes
* all code written must be formatted/linted by ruff (uv add --dev)
* all code written must be type-annotated and will be checked with mypy (uv add --dev)
* use modern python type annotations, like `int | None` not `Optional[int]`
* the project folder must have a justfile implementing important shell/terminal calls; e.g.:
    * installing
    * formatting/linting
    * running type checks
    * running a local version of the server
    * running unit tests
* we will write unit tests for the API, but not necessarily first
* Use HTTP status codes:
    * 201 on a POST for resource creation that has succeeded. 
    * 200 on any other request that has succeeded.
    * Do _not_ use 204 for any response, all responses valid JSON
    * 404 when a top-level, path referenced resource was not found
    * 422 when a payload sent in a request body cannot be parsed correctly
    * 400 when a request is accepted but fails other constraints not validatable by the JSON alone
        * e.g., the failure is after a database lookup given the request
    * 501 when an endpoint is available but has no implementation yet
    * NOTE: if specific examples below seem to deviate from this, prefer these rules
* timestamps should all be no-timezone UTC timestamps.
    * client applications are responsible for timezoning correctly, if needed
    * `post_date` is an exception, it's a literal string used for other purposes
* When write HTTP endpoint specs like `METHOD /path/{param:type}` we mean we validate the type
    * specifically, `METHOD /path/{param:uuidv7}` means the implementation validates the UUID
* the API must expose top-level `GET /health/alive` and `GET /health/ready` endpoints
* every other functional API endpoint should be prefixed `/api/v0` (or other vX number later)
* Do not pass a database _session_ to an API route handler
    * pass a _session factory_ not a session
    * the route handler will have to decide on session management
    * the session factory yields an async session (async_sessionmaker[AsyncSession]) and handlers manage it via `async with`
* When writing tests avoid mocks at all costs.
    * Mocking makes tests complex, brittle and it is easy to test trivialities
    * One exception here may be a mock response from an external job system with an external_job_id

# File layout

This is the preferred file layout:
```
admin/
    .gitignore
    justfile
    pyproject.toml
    uv.lock
    README.md
    Dockerfile (install non-dev uv dependencies, copy source code, set entrypoint)
    compose.yaml (for running locally with dependencies; sqlite or postgres, a mock for external job system)
    api/
        main.py (primary entrypoint with app definition, import and "add" routers)
        settings.py (configuration, define and instantiate a single settings object)
        health.py (definition of health endpoints, and a router to attach for them)
        utils/
            ... shared functions, standalone, don't use any other local imports
        v0/
            schema/
                ... API request/response schemas as needed
            handlers/
                ... request handlers: health, sets, drafts, runs
            routers/
                ... use routers, instead of flat route definitions; these go here
                    organized by prefix (e.g., `/sets*` in `sets.py`)
            router.py (aggregated `/api/v0*` prefixed router)
        database/
            .. database utilities, table models
    mocks/
        ... any simpler, single-file apps we need to run local E2E tests; e.g. maybe jobs/ test server
    tests/
        conftest.py (pytest sertup and fixtures)
        ...
```

# API

## sets 

### Resource

* "sets":
    * set_id (PK, uuidv7)
    * model (required, has specific choices, likely CHECK constraint)
    * slug (optional, string/text)
    * name (optional, string/text)
    * prompt (nullable, string/text, set when committed)
    * model_prompt_hash (generated when prompt is set, defined as sha256(model::prompt))
    * post_date (nullable string/text, set when committed; YYYY-MM-DD style string in LA/Pacific TZ)
    * status (DRAFT, ABANDONED, COMMITTED, COMPLETED, FAILED)
    * created_at (generated on creation, UTC timestamp)
    * updated_at (set to the latest update, UTC timestamp)
    * committed_at (UTC timestamp)
    * abandoned_at (UTC timestamp)

### HTTP calls

* POST /api/v0/sets
    - create a set (in DRAFT status), returning a server-generated set_id (uuidv7)
* GET /api/v0/sets
    - list sets, with query parameter filters (status, post_date, slug, name)
* GET /api/v0/sets/{set_id:uuidv7}
    - get one set (or 404)
* PATCH /api/v0/sets/{set_id:uuidv7}
    - update set fields
* DELETE /api/v0/sets/{set_id:uuidv7}
    - mark ABANDONED

### Details

* a model is required to create a set and there are specific choices
    * "black-forest-labs/FLUX.2-klein-4B" (default)
    * "black-forest-labs/FLUX.1-schnell"
    * should be configurable
* set slugs must be globally unique, but do not have to be chosen at create time
    * must match the regex ^[a-z][a-z0-9-]{1,126}[a-z]$
    * that is:
        * lowercase letters digits and hyphens only
        * starting and ending with a lowercase letter
        * having at least 3 characters and at most 128
* set names should be:
    * Title Case
    * have no more than 3 words (space-separated)
    * have no more than 64 total characters
    * does not have to be chosen at create time, but have to be set before commit
* prompts must be checked to be strings less than 1024 characters in length
* Every created set starts in status: DRAFT, and creation returns a uuidv7 set_id
* Creation requires a model in the payload, and _can_ have slug and name but does not have to
* Only sets in DRAFT state can be updated with PATCH; others return a 400 BadRequest
* Only slug and name can be changed by PATCH /api/v0/sets/{set_id}
* To make a set COMMITTED it must have a slug and a name stored
* A set in status COMMITTED, COMPLETED, or FAILED cannot be changed via a PATCH call
* A set can only be marked ABANDONED (DELETE call) while in DRAFT status
* The DELETE implementation will be _soft_: mark ABANDONED, leave in database
* set "COMPLETION" will happen based on the result on an external job and handled with run updates described below
* set semantics: a set is a named container for many images (thousands); COMMITTED means "ready to execute the creation of thousands", COMPLETED means "we've done it, we have all our images". A set has one commit and should be immutable after that, up to reconciling batch job failures that change state. A COMPLETED set can be a new entry on a webpage, but that is not being discussed yet.
* set status flow:
    * DRAFT -> COMMITTED (when a draft is committed, see below)
    * DRAFT -> ABANDONED (when DELETE /api/v0/sets/{set_id} called)
    * COMMITTED -> COMPLETED (when external type: BATCH job finishes successfully)
    * COMMITTED -> FAILED (when external type: BATCH job finishes unsuccessfully)
    * FAILED -> COMPLETED (when a re-run external job finished successfully)

## drafts

### Resource

* "drafts":
    * draft_id (PK, uuidv7)
    * set_id (FK, uuidv7)
    * prompt (required, string/text)
    * model_prompt_hash (generated on creation, defined as sha256(sets[set_id].model::prompt))
    * status (PENDING, IN_PROGRESS, FAILED, COMPLETED)
    * created_at (generated on creation, UTC timestamp)

### HTTP calls

* POST /api/v0/sets/{set_id:uuidv7}/drafts
    - create a set draft, returning a server-generated draft_id (uuidv7)
* GET /api/v0/sets/{set_id:uuidv7}/drafts
    - get all set drafts, ordered by create time descending
* GET /api/v0/sets/{set_id:uuidv7}/drafts/{draft_id}
    - get a specific set draft
* POST /api/v0/sets/{set_id:uuidv7}/drafts/{draft_id}/commit
    - "commit" a draft set

### Details

* To create a draft the set_id referenced in the path must exist, and be in status: DRAFT
* To create a draft we have to submit a prompt and get back a uuidv7 draft_id
* prompts must be checked to be strings less than 1024 characters in length
* drafts are otherwise immutable except for system-updatable status field
* The system creates the model_prompt_hash from the prompt in the create request
* model_prompt_hashes must be globally unique over all drafts
* The valid draft status transitions are:
    * PENDING -> IN_PROGRESS (external job started)
    * PENDING -> FAILED (external job created, but failed to start)
    * IN_PROGRESS -> COMPLETED | FAILED (external job finished, with success or error)
    * FAILED -> COMPLETED (a re-run of the external job finished successfully)
    * implement any X -> X state transition (same state as current) as a no-op success
* drafts are the way to evaluate options before committing a set; drafts associated with a set are the "drafting" phase. Holding "commit" at the draft level lets the user pick the draft that works best, and "commit" the set with that draft's prompt, model_prompt_hash, and the commit "post_date".
* There is no "direct" way to update a draft status, the system will do this as described elsewhere
* when we create a draft _and_ successfully trigger the external job
    * we create a run for this set/draft storing:
        * the set_id/draft_id FK's
        * and the external_run_id returned from the job creation
    * run created of type: EVALUATION
    * run created in status: PENDING
    * on failure to create a job in the external system, the draft creation should fail with no database changes
* when a draft's status is moved from IN_PROGRESS -> COMPLETED
    * we will need to copy S3 assets from one bucket to another (owned by the same account)
    * "job" bucket /job prefix -> "site" bucket / site prefix
    * probably one file, but we should implement generally
    * the job and site prefixes are likely to involve the model_prompt_hash like {prefix}/{model_prompt_hash}
* "committing" (with the /commit endpoint) is how sets are COMMITTED
    * the set referenced by the path must be in status: DRAFT (not committed in particular)
    * the set referenced by the path must have both a slug and name stored
    * the draft referenced must be in status: COMPLETED
    * the commit must be implemented as a single transaction covering the set update and the run creation.
    * the commit must be idempotent; re-issuing must not create a second BATCH run or overwrite committed state.
    * the single transaction covers the set update and the run creation, but the outbound HTTP call to create the external job must not run inside the database transaction; it is issued outside/after the transaction.
    * if so, the commit call assigns:
        * set[set_id].prompt <- draft.prompt
        * set[set_id].post_date <- current date in YYYY-MM-DD format for Los Angeles/Pacific TZ
        * set[set_id].committed_at <- current UTC timestamp
        * set[set_id].status <- COMMITTED
        * runs an external job
            * we create a run for this set/draft storing:
                * the set_id/draft_id FK's
                * and the external_run_id returned from the job system
            * run created of type: BATCH
            * run created in status: PENDING
            * on failure to create the job, reject all changes and return with error details

## runs

### Resource

* "runs"
    * run_id (PK, uuidv7)
    * external_run_id (required, string/text, from job system response)
    * set_id (FK, uuidv7)
    * draft_id (FK, uuidv7)
    * type (EVALUATION, BATCH)
    * status (PENDING, IN_PROGRESS, FAILED, COMPLETED)
    * details (optional, not sure, maybe string/text, maybe JSON)
    * created_at (generated on creation, UTC timestamp)
    * updated_at (set to the latest update, UTC timestamp)
    * finished_at (set when finished, UTC timestamp)

### HTTP calls

* GET /api/v0/runs
    - list runs with query param filters (set, draft, status, ...)
* GET /api/v0/runs/{run_id:uuidv7}
    - return a specific run by it's id alone or 404
* POST /api/v0/runs/{run_id:uuidv7}
    - create a new run by "redoing" an existing run (for it's set and draft)
* PUT /api/v0/runs/{run_id:uuidv7}/status
    - update a run status (system call)

### Details

* run_id should be server-generated (uuidv7) and unique per external job
* external_run_id is returned from the job system and used to correlate the external job with its run.
* run objects should only be created by the code, from draft creation, set committing, and internally for "redos"
* runs are immutable except timestamps and status
* run statuses are linear: PENDING -> IN_PROGRESS -> COMPLETED | FAILED are the only valid changes
    * PENDING -> IN_PROGRESS (we are signalled an external job we created has started)
    * IN_PROGRESS -> COMPLETED | FAILED (we are signalled an external job we created has finished)
    * we will assume we do not "restart" external jobs, we can "resubmit them" under new records if failed
    * if that changes (external jobs restart) we can revisit this status flow
* "redoing" a run requires the run referenced by id to be in a FAILED status
* "redoing" a run _creates a distinct run object_ linked to the same set and draft
* when updating a run status, we should match the status of the linked DRAFT
    * note that we can't redo a run for the same draft without a run having failed
    * run updates are job specific, and probably have little row-level concurrency concerns
    * when drafts only get status updates through run updates, then, a draft has little row-level concurrency concerns
    * if we set draft.status = FAILED, we need to potentially be able to update to COMPLETED if a re-run succeeds

# System Flow

Some sketches:

user -> create set (POST /api/v0/sets)
    <- 201 if request OK, 400 if invalid model

user -> create draft (POST /api/v0/sets/{set_id}/drafts)
    -> create/store a type: EVALUATION run object
    -> kick off external EVALUATION job (HTTP POST request)  creating a run
    <- 201 if created, 400 if invalid set, 500 if creating job fails, ...
    ("in the background")
        <- external job starts, calls PUT /api/v0/runs/{run_id}/status ("IN_PROGRESS")
        <- external job fails, calls PUT /api/v0/runs/{run_id}/status ("FAILED")
        <- external job completes, calls PUT /api/v0/runs/{run_id}/status ("COMPLETED")
        on COMPLETED, set the draft.status to COMPLETED, on FAILED, set the draft.status to FAILED

user -> create draft (POST /api/v0/sets/{set_id}/drafts)
    -> kick off external EVALUATION job (HTTP POST request) creating a run
    ... same

user -> commit set (POST /api/v0/sets/{set_id}/drafts/{draft_id}/commit)
    <- 400, set invalid: slug/name not set yet

user -> update set (PATCH /api/v0/sets/{set_id}) with slug/name
    <- 200 if ok, 400/422 if validation fails, 404 not found

user -> commit set (POST /api/v0/sets/{set_id}/drafts/{draft_id}/commit)
    -> do checks on draft and set status
        -> "commit" the set, described above
            -> create/store a new type: BATCH run object
            -> trigger a BATCH external job (via HTTP call) with a run_id
            ("in the background", long time)
                <- external job starts, calls PUT /api/v0/runs/{run_id}/status ("IN_PROGRESS")
                <- external job fails, calls PUT /api/v0/runs/{run_id}/status ("FAILED")
                <- external job completes, calls PUT /api/v0/runs/{run_id}/status ("COMPLETED")
                on COMPLETED, set the set.status to COMPLETED, on FAILED, set the set.status to FAILED
    <- 200, 400, etc

user -> create draft (POST /api/v0/sets/{set_id}/drafts)
    <- 400 BadRequest, set already COMMITTED

user -> update set (PATCH /api/v0/sets/{set_id}) with slug/name
    <- 400, set already COMMITTED

Notes:
* the "external jobs" referenced below are triggerable by a plain HTTP call. We will need to align on the payloads through working on the design, but triggering them won't be any more complicated than this.
* a successfully drafted, commited, and completed set will require other actions we can consider later.

# API Implementation Plan

Derived from the resolved design decisions in this document.

## Scope

* Deliver an HTTP API (FastAPI, containerized with Docker, IAM role, no auth, HTTP/1.1, env vars, no `.env`) in AWS that makes sets, makes set drafts, commits a draft as the set, and stores/surfaces data through the API over which an interactive webpage can later be built.

## Phases

### Phase 1 — Data model and sets

* SQLModel entities for Set, Draft, Run (async engine; Postgres; SQLite for tests; UUIDs as uuidv7).
* Sets: create (DRAFT, model required, optional slug/name), list (filters), get, patch (DRAFT only, slug/name), delete (soft → ABANDONED).
* Commit path: single transaction over set update + run creation; idempotent; external job call outside transaction; failure → reject/no changes.

### Phase 2 — Drafts and commit flow

* Draft create (set must exist and be DRAFT; prompt required; hash = sha256(sets[set_id].model::prompt)); trigger EVALUATION job; run created (EVALUATION, PENDING).
* Draft status transitions; on COMPLETED copy S3 assets; on FAILED draft status FAILED.
* Commit (DRAFT set + COMPLETED draft; slug/name set) → assign set fields; trigger BATCH job; run created (BATCH, PENDING); status updates; set COMPLETED/FAILED.

### Phase 3 — Runs and orchestration

* Runs endpoints; redo (FAILED → new run); status updates (match draft status); `external_run_id` from job system response.

### Phase 4 — Tooling, errors, tests, deploy

* FastAPI/Pydantic/etc.; status codes policy; timestamps; prompt hash; error handler; ruff/mypy; justfile; unit tests; Docker/IAM/HTTP.

## Open items carried forward

* None of the top-10 design questions remain open; implementation planning can proceed against the resolved decisions.

# Abbreviations 

* PK: primary key
* FK: foreign key
