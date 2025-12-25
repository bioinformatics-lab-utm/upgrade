-- Migration 007: Pipeline Progress Tracking System
-- Adds real-time progress tracking for lakehouse pipeline stages

-- Create pipeline_progress_events table
CREATE TABLE IF NOT EXISTS pipeline_progress_events (
    event_id SERIAL PRIMARY KEY,
    pipeline_id INTEGER NOT NULL REFERENCES pipeline_runs(pipeline_id) ON DELETE CASCADE,
    stage VARCHAR(100) NOT NULL,  -- bronze_upload, bronze_download, nextflow_start, silver_upload, gold_curation, cleanup
    step VARCHAR(200) NOT NULL,   -- Detailed step description
    status VARCHAR(50) NOT NULL,  -- started, in_progress, completed, failed
    progress_percent INTEGER DEFAULT 0,  -- 0-100
    details JSONB DEFAULT '{}',   -- Additional context (file names, sizes, counts)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for fast querying
CREATE INDEX idx_pipeline_progress_pipeline ON pipeline_progress_events(pipeline_id, created_at DESC);
CREATE INDEX idx_pipeline_progress_stage ON pipeline_progress_events(stage, status);

-- Create view for latest progress per pipeline
CREATE OR REPLACE VIEW v_pipeline_latest_progress AS
SELECT DISTINCT ON (pipeline_id)
    pipeline_id,
    stage,
    step,
    status,
    progress_percent,
    details,
    created_at
FROM pipeline_progress_events
ORDER BY pipeline_id, created_at DESC;

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON pipeline_progress_events TO upgrade;
GRANT USAGE, SELECT ON SEQUENCE pipeline_progress_events_event_id_seq TO upgrade;
GRANT SELECT ON v_pipeline_latest_progress TO upgrade;

COMMENT ON TABLE pipeline_progress_events IS 'Real-time progress tracking for pipeline execution stages';
COMMENT ON COLUMN pipeline_progress_events.stage IS 'High-level stage: bronze_upload, nextflow_exec, silver_upload, gold_curation';
COMMENT ON COLUMN pipeline_progress_events.step IS 'Detailed step within stage, e.g., "Compressing FASTQ", "Uploading to MinIO"';
COMMENT ON COLUMN pipeline_progress_events.progress_percent IS 'Overall progress percentage for this stage';
COMMENT ON COLUMN pipeline_progress_events.details IS 'JSON details: file names, sizes, process names, etc.';
