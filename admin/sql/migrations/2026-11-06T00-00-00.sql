
CREATE TABLE run_status_events (
	event_id UUID NOT NULL, 
	run_id UUID NOT NULL, 
	status runstatus NOT NULL, 
	message VARCHAR(1024), 
	details JSONB, 
	received_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (event_id), 
	FOREIGN KEY(run_id) REFERENCES runs (run_id)
)

;

CREATE INDEX ix_run_status_events_run_id ON run_status_events (run_id);
