--
-- Delete a set and dependent objects. Call like 
-- 
--   psql -d theunending \
--     -v ON_ERROR_STOP=1 \
--     -v target_set_id=... \
--     -f delete.sql
-- 

-- Fail immediately if the variable wasn't passed on the command line
\if :{?target_set_id}
\else
  \warn 'Error: target_set_id is required. Run with -v target_set_id=...'
  \quit
\endif

-- Delete chain from runs, to drafts, to sets

BEGIN;

DELETE FROM run_status_events
WHERE run_id IN (
    SELECT run_id
    FROM runs
    WHERE set_id = :'target_set_id'
    OR draft_id IN (
        SELECT draft_id 
        FROM drafts 
        WHERE set_id = :'target_set_id'
    )
);

DELETE FROM runs
WHERE set_id = :'target_set_id'
OR draft_id IN (
    SELECT draft_id 
    FROM drafts 
    WHERE set_id = :'target_set_id'
);

DELETE FROM drafts 
WHERE set_id = :'target_set_id';

DELETE FROM sets 
WHERE set_id = :'target_set_id';

COMMIT;
