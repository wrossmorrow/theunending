# Top Design Questions — Ranked by Production Risk

Follow-up to `design-ambiguities.md` (the full read of `admin/DESIGN.md` from PR #3, "docs: draft inital design plan"). After re-reading the design doc and reviewing the earlier question list, here are the **top 10 questions**, ranked by the likelihood that a wrong guess causes bugs or data inconsistency in production. For each: the failure we should address immediately in the design.

## Ranked list

### 1. Draft status on completion: `READY` vs `COMPLETED`

- **Question**: The System Flow says, on COMPLETED, "set the draft.status to READY"; the drafts resource enum lists `PENDING, IN_PROGRESS, FAILED, COMPLETED` — no `READY`. The commit endpoint requires the draft to be in `COMPLETED` status.
- **Production failure**: If implemented as written, the commit precondition can never be satisfied (or an invalid `READY` status gets persisted), so the core production flow (draft → evaluate → commit) cannot complete. If `READY` is added to the enum, the design carries a contradictory status and the commit path must special-case it. Invalid status writes are also possible if the status update endpoint is not strict.
- **Address immediately in design**: Decide whether `READY` is a real status or a typo for `COMPLETED`, and resolve before implementing the status-update or commit endpoints.

### 2. What a "set" is

- **Question**: The doc uses "set" ambiguously — one generation (one image), the committed final asset, an evaluation batch, or a logical collection?
- **Production failure**: Wrong semantics cascade into every resource rule (FKs, statuses, commit checks, prompt/post_date handling). Production data would be internally consistent but wrong relative to intent (e.g., committing an evaluation as a final set).
- **Address immediately in design**: Pin down set semantics before designing resources.

### 3. Commit atomicity / idempotency

- **Question**: Is the commit a single transaction, and is it idempotent?
- **Production failure**: Without atomicity, partial commits (prompt set, status not) or double commits (two BATCH runs, `committed_at` clobbered) → inconsistent production data. Without idempotency, retries duplicate batches.
- **Address immediately in design**: Define transaction scope and idempotency for commit.

### 4. Prompt hash contents

- **Question**: Does the prompt hash include the model, and over what exactly? Is it global across drafts/sets?
- **Production failure**: If the hash is prompt-only and the same prompt is evaluated under two models, the hash collides → S3 asset collision / wrong image reused → production data corruption. Also whether the set's `prompt_hash` should just mirror the draft's.
- **Address immediately in design**: Define hash inputs and uniqueness scope; validate at commit.

### 5. Status transition enforcement

- **Question**: Which status transitions are valid, is `FAILED` terminal, can a committed set be `FAILED`, does run status drive set status?
- **Production failure**: Invalid transitions accepted (e.g., commit an ABANDONED set, commit twice, mark FAILED improperly) → impossible production states.
- **Address immediately in design**: Define full state machine for sets and drafts; decide run-status-driven set status.

### 6. Create-set error code: 400 vs 422

- **Question**: Create-set errors: design says 400, FastAPI defaults to 422.
- **Production failure**: Client contract bug; error handling in production breaks depending on which is chosen.
- **Address immediately in design**: Standardize on one code.

### 7. DELETE semantics

- **Question**: Is DELETE a soft mark (`ABANDONED`) or a hard delete?
- **Production failure**: Hard delete loses set/draft/run history irreversibly; if DELETE is intended as abandon and implemented as hard delete, production data is lost.
- **Address immediately in design**: Decide soft vs hard, and cascade behavior for related drafts/runs.

### 8. Post date semantics

- **Question**: What is `post_date` (generation/publication/acquisition), timezone (LA/Pacific vs IANA), format?
- **Production failure**: Wrong date recorded → wrong production data.
- **Address immediately in design**: Decide semantics and source of truth.

### 9. External run ID semantics

- **Question**: Is `external_run_id` caller-supplied or server-generated; idempotency?
- **Production failure**: Can't trace/redo runs correctly; duplicate external jobs or broken redo links in production.
- **Address immediately in design**: Decide generation and idempotency semantics.

### 10. Timestamp semantics

- **Question**: Naive vs aware UTC; `updated_at` on status changes; `finished_at` for which statuses; `committed_at`/`abandoned_at` semantics.
- **Production failure**: Naive/aware comparison bugs; `updated_at` not updated on status transitions → inconsistent data; `finished_at` not set → can't tell completion. Production data inconsistencies.
- **Address immediately in design**: Define timestamp semantics per status.

## How to use this list

These are the highest-risk unknowns from the design. Before implementing, resolve them in order (1 → 10) and record decisions back into the design doc or this file. Resolving them early prevents production bugs and data inconsistencies that would be costly to retrofit later.
