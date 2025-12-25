-- Migration 008: Add job_id column for Redis Queue integration
-- Date: 2024-12-16
-- Purpose: Track RQ job IDs for async pipeline execution

-- Add job_id column to pipeline_runs
ALTER TABLE pipeline_runs
ADD COLUMN IF NOT EXISTS job_id VARCHAR(100);

-- Create index for fast job_id lookups
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_job_id ON pipeline_runs(job_id);

-- Add comment
COMMENT ON COLUMN pipeline_runs.job_id IS 'Redis Queue (RQ) job ID for async pipeline execution';

-- Grant permissions
GRANT SELECT, UPDATE ON pipeline_runs TO upgrade;

COMMENT ON COLUMN pipeline_runs.job_id IS 'RQ job ID - used to track async pipeline execution in Redis Queue';
