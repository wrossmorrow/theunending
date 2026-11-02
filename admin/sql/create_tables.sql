
CREATE TABLE sets (
	set_id UUID NOT NULL, 
	model VARCHAR NOT NULL, 
	slug VARCHAR, 
	name VARCHAR(64), 
	prompt VARCHAR, 
	model_prompt_hash VARCHAR, 
	post_date VARCHAR, 
	status setstatus NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	committed_at TIMESTAMP WITH TIME ZONE, 
	abandoned_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (set_id)
)

;


CREATE TABLE drafts (
	draft_id UUID NOT NULL, 
	set_id UUID NOT NULL, 
	prompt VARCHAR(1023) NOT NULL, 
	model_prompt_hash VARCHAR NOT NULL, 
	status draftstatus NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (draft_id), 
	FOREIGN KEY(set_id) REFERENCES sets (set_id)
)

;


CREATE TABLE runs (
	run_id UUID NOT NULL, 
	external_run_id VARCHAR NOT NULL, 
	set_id UUID NOT NULL, 
	draft_id UUID NOT NULL, 
	type runtype NOT NULL, 
	status runstatus NOT NULL, 
	details VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (run_id), 
	FOREIGN KEY(set_id) REFERENCES sets (set_id), 
	FOREIGN KEY(draft_id) REFERENCES drafts (draft_id)
)

;
