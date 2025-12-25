-- Migration 005: Update pipeline_runs table for simplified genomic pipeline management
-- Date: 2025-11-15
-- Purpose: Add convenient columns for pipeline tracking (compatible with migration 002)

-- Note: pipeline_runs table is created in migration 002 with full structure
-- This migration only adds columns if they don't exist

-- Add simplified tracking columns if they don't exist
DO $$
BEGIN
    -- Add sample_name if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='pipeline_runs' AND column_name='sample_name') THEN
        ALTER TABLE pipeline_runs ADD COLUMN sample_name VARCHAR(255);
    END IF;

    -- Add sample_type if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='pipeline_runs' AND column_name='sample_type') THEN
        ALTER TABLE pipeline_runs ADD COLUMN sample_type VARCHAR(50) DEFAULT 'nanopore';
    END IF;

    -- Add location if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='pipeline_runs' AND column_name='location') THEN
        ALTER TABLE pipeline_runs ADD COLUMN location VARCHAR(255);
    END IF;

    -- Add collection_date if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='pipeline_runs' AND column_name='collection_date') THEN
        ALTER TABLE pipeline_runs ADD COLUMN collection_date DATE;
    END IF;

    -- Add fastq_paths if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='pipeline_runs' AND column_name='fastq_paths') THEN
        ALTER TABLE pipeline_runs ADD COLUMN fastq_paths TEXT[];
    END IF;

    -- Add error_message if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='pipeline_runs' AND column_name='error_message') THEN
        ALTER TABLE pipeline_runs ADD COLUMN error_message TEXT;
    END IF;

    -- Add updated_at if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='pipeline_runs' AND column_name='updated_at') THEN
        ALTER TABLE pipeline_runs ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
    END IF;
END $$;

-- Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_created_at ON pipeline_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_sample_name ON pipeline_runs(sample_name);

-- Create or replace updated_at trigger
CREATE OR REPLACE FUNCTION update_pipeline_runs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_pipeline_runs_updated_at ON pipeline_runs;
CREATE TRIGGER update_pipeline_runs_updated_at
    BEFORE UPDATE ON pipeline_runs
    FOR EACH ROW
    EXECUTE FUNCTION update_pipeline_runs_updated_at();

-- Add comments
COMMENT ON TABLE pipeline_runs IS 'Stores genomic pipeline execution runs';
COMMENT ON COLUMN pipeline_runs.pipeline_id IS 'Unique pipeline run identifier';
COMMENT ON COLUMN pipeline_runs.sample_id IS 'Reference to samples table';
COMMENT ON COLUMN pipeline_runs.sample_name IS 'Convenient sample name copy for queries';
COMMENT ON COLUMN pipeline_runs.sample_type IS 'Sequencing platform: nanopore, illumina, or pacbio';
COMMENT ON COLUMN pipeline_runs.status IS 'Pipeline status: pending, running, completed, or failed';
COMMENT ON COLUMN pipeline_runs.parameters IS 'JSON object with pipeline parameters';
COMMENT ON COLUMN pipeline_runs.fastq_paths IS 'Array of paths to input FASTQ files';
