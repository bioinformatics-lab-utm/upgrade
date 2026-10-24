-- Migration: Runs that never received input are failed, not completed
-- Date: 2026-10-16
-- Description: When the worker found no input FASTQ for a run in the Bronze layer
-- (it downloads only files registered for that pipeline_id), Nextflow ran on an
-- empty folder, exited 0 and the run was marked 'completed'. Those runs have no
-- result files, yet were listed as completed analyses with zero findings.
-- The worker now fails such runs; this marks the existing ones. A run is
-- affected when it is 'completed' and none of its attempts downloaded a file.
--
-- The run ids are kept in migration_020_failed_runs. To undo:
--   UPDATE pipeline_runs SET status = 'completed', error_message = NULL
--   WHERE pipeline_id IN (SELECT pipeline_id FROM migration_020_failed_runs);
-- No notifications or emails are sent for these status changes.
-- Idempotent: safe to run more than once.

BEGIN;

CREATE TABLE IF NOT EXISTS migration_020_failed_runs (
    pipeline_id INTEGER PRIMARY KEY,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO migration_020_failed_runs (pipeline_id)
SELECT pr.pipeline_id
FROM pipeline_runs pr
WHERE pr.status = 'completed'
  AND EXISTS (SELECT 1 FROM pipeline_progress_events e
              WHERE e.pipeline_id = pr.pipeline_id AND e.stage = 'bronze_download'
                AND e.step = 'Downloaded 0 files')
  AND NOT EXISTS (SELECT 1 FROM pipeline_progress_events e
                  WHERE e.pipeline_id = pr.pipeline_id AND e.stage = 'bronze_download'
                    AND e.step LIKE 'Downloaded % files' AND e.step <> 'Downloaded 0 files')
ON CONFLICT DO NOTHING;

ALTER TABLE pipeline_runs DISABLE TRIGGER trg_pipeline_status_notification;

UPDATE pipeline_runs
SET status = 'failed',
    error_message = 'No input FASTQ files reached the pipeline (0 files downloaded from Bronze), so no analysis was done.'
WHERE status = 'completed'
  AND pipeline_id IN (SELECT pipeline_id FROM migration_020_failed_runs);

ALTER TABLE pipeline_runs ENABLE TRIGGER trg_pipeline_status_notification;

COMMIT;
