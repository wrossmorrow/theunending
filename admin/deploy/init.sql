
---

CREATE TYPE setstatus AS ENUM ('DRAFT', 'ABANDONED', 'COMMITTED', 'COMPLETED', 'FAILED');

CREATE TABLE sets (
	set_id UUID NOT NULL PRIMARY KEY, 
	model VARCHAR NOT NULL, 
	slug VARCHAR UNIQUE, 
	name VARCHAR(64),
	prompt VARCHAR,
	model_prompt_hash VARCHAR UNIQUE,
	post_date VARCHAR, 
	status setstatus NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	committed_at TIMESTAMP WITH TIME ZONE, 
	abandoned_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX ix_sets_model ON sets (model);
-- slug indexed by UNIQUE
CREATE INDEX ix_sets_name ON sets (name);
CREATE INDEX ix_sets_status ON sets (status);

---

CREATE TYPE draftstatus AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED');

CREATE TABLE drafts (
	draft_id UUID NOT NULL PRIMARY KEY, 
	set_id UUID NOT NULL REFERENCES sets (set_id_), 
	prompt VARCHAR(1024) NOT NULL, 
	model_prompt_hash VARCHAR NOT NULL UNIQUE, 
	status draftstatus NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX ix_drafts_set_id ON drafts (set_id);

---

CREATE TYPE runtype AS ENUM ('EVALUATION', 'BATCH');
CREATE TYPE draftstatus AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED');

CREATE TABLE runs (
	run_id UUID NOT NULL PRIMARY KEY, 
	external_run_id VARCHAR NOT NULL,
	set_id UUID NOT NULL REFERENCES sets (set_id), 
	draft_id UUID NOT NULL REFERENCES drafts (draft_id), 
	type runtype NOT NULL, 
	status runstatus NOT NULL, 
	details VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	finished_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX ix_runs_set_id ON runs (set_id);
CREATE INDEX ix_runs_draft_id ON runs (draft_id);
