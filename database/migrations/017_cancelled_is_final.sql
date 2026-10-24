-- Migration: A cancelled pipeline run stays cancelled
-- Date: 2026-10-16
-- Description: When a user stops a run, the API marks it 'cancelled' and the RQ
-- worker then stops Nextflow. Whatever the worker (or any other writer) reports
-- afterwards - 'running' from a job that was already being picked up, 'failed'
-- from the killed Nextflow, 'completed' from a run that finished in the same
-- second - must not overwrite the user's decision. The only way out of
-- 'cancelled' is a rerun, which puts the run back to 'queued'.
-- Idempotent: safe to run more than once.

BEGIN;

CREATE OR REPLACE FUNCTION keep_pipeline_cancelled() RETURNS trigger AS $$
BEGIN
    IF OLD.status = 'cancelled' AND NEW.status IN ('running', 'completed', 'failed') THEN
        NEW.status        := OLD.status;
        NEW.error_message := OLD.error_message;
        NEW.completed_at  := OLD.completed_at;
        NEW.started_at    := OLD.started_at;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_keep_pipeline_cancelled ON pipeline_runs;
CREATE TRIGGER trg_keep_pipeline_cancelled
    BEFORE UPDATE OF status ON pipeline_runs
    FOR EACH ROW
    WHEN (OLD.status = 'cancelled')
    EXECUTE FUNCTION keep_pipeline_cancelled();

COMMIT;
