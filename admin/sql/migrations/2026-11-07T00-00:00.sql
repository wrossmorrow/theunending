
CREATE TYPE runstatuseventsource AS ENUM ('EXTERNAL', 'INTERNAL');

ALTER TABLE run_status_events ADD COLUMN IF NOT EXISTS source runstatuseventsource NOT NULL DEFAULT 'EXTERNAL';

