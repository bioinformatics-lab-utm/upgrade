-- ============================================
-- Migration 006: Lakehouse Architecture
-- ============================================
-- Extends existing schema for Bronze/Silver/Gold layers
-- Adds process-level tracking and artifact management
-- Author: AI Assistant
-- Date: 2025-11-17

-- ==================== EXTEND MINIO_OBJECTS ====================
-- Add columns to track which process created each object

ALTER TABLE minio_objects 
ADD COLUMN IF NOT EXISTS process_name VARCHAR(50),
ADD COLUMN IF NOT EXISTS tool_version VARCHAR(20),
ADD COLUMN IF NOT EXISTS execution_id INT REFERENCES nextflow_executions(execution_id) ON DELETE CASCADE,
ADD COLUMN IF NOT EXISTS layer_stage VARCHAR(20);

COMMENT ON COLUMN minio_objects.process_name IS 'Nextflow process that created this object (NANOPLOT, FILTLONG, FLYE, etc.)';
COMMENT ON COLUMN minio_objects.tool_version IS 'Tool/container version (e.g., 1.0.0, staphb/nanoplot:1.2.0)';
COMMENT ON COLUMN minio_objects.execution_id IS 'Link to specific Nextflow execution that generated this object';
COMMENT ON COLUMN minio_objects.layer_stage IS 'Pipeline stage: qc, filtered, assembly, binning, quality, taxonomy, abundance';

-- Create index for faster queries by process
CREATE INDEX IF NOT EXISTS idx_minio_objects_process ON minio_objects(process_name);
CREATE INDEX IF NOT EXISTS idx_minio_objects_execution ON minio_objects(execution_id);
CREATE INDEX IF NOT EXISTS idx_minio_objects_layer_stage ON minio_objects(layer_stage);

-- ==================== EXTEND PIPELINE_RUNS ====================
-- Add MinIO paths for each lakehouse layer

ALTER TABLE pipeline_runs
ADD COLUMN IF NOT EXISTS bronze_path VARCHAR(500),
ADD COLUMN IF NOT EXISTS silver_path VARCHAR(500),
ADD COLUMN IF NOT EXISTS gold_path VARCHAR(500);

COMMENT ON COLUMN pipeline_runs.bronze_path IS 'MinIO path to raw uploaded files: genomic-bronze/{sample_code}/raw/';
COMMENT ON COLUMN pipeline_runs.silver_path IS 'MinIO path to intermediate results: genomic-silver/{sample_code}/{run_id}/';
COMMENT ON COLUMN pipeline_runs.gold_path IS 'MinIO path to final curated results: genomic-gold/{sample_code}/';

-- ==================== CREATE PIPELINE_ARTIFACTS ====================
-- Track specific artifacts (assemblies, bins, reports) with quality tiers

CREATE TABLE IF NOT EXISTS pipeline_artifacts (
    artifact_id SERIAL PRIMARY KEY,
    pipeline_id INT NOT NULL REFERENCES pipeline_runs(pipeline_id) ON DELETE CASCADE,
    
    -- Artifact identification
    artifact_type VARCHAR(50) NOT NULL, -- 'assembly', 'bin', 'qc_report', 'taxonomy_report', etc.
    artifact_name VARCHAR(255) NOT NULL,
    artifact_description TEXT,
    
    -- Storage reference
    minio_object_id INT REFERENCES minio_objects(object_id) ON DELETE SET NULL,
    file_path VARCHAR(500), -- MinIO path or local path
    
    -- Quality metrics
    quality_tier VARCHAR(20), -- 'high', 'medium', 'low', 'failed'
    quality_score DECIMAL(5,2), -- 0-100 score (e.g., completeness %)
    
    -- Metadata
    metadata JSONB, -- Flexible storage for tool-specific metrics
    
    -- Processing info
    process_name VARCHAR(50), -- Which Nextflow process created this
    created_by VARCHAR(100), -- Tool name (e.g., 'Flye v2.9', 'CheckM v1.2.0')
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT valid_artifact_type CHECK (
        artifact_type IN (
            'assembly', 'bin', 'qc_report', 'filtering_log', 
            'taxonomy_report', 'abundance_report', 'quality_report',
            'assembly_graph', 'assembly_stats', 'trace_file',
            'timeline_html', 'execution_report'
        )
    ),
    CONSTRAINT valid_quality_tier CHECK (
        quality_tier IN ('high', 'medium', 'low', 'failed', 'unknown')
    )
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_artifacts_pipeline ON pipeline_artifacts(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON pipeline_artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifacts_quality ON pipeline_artifacts(quality_tier);
CREATE INDEX IF NOT EXISTS idx_artifacts_minio_object ON pipeline_artifacts(minio_object_id);

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_artifacts_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_pipeline_artifacts_timestamp
    BEFORE UPDATE ON pipeline_artifacts
    FOR EACH ROW
    EXECUTE FUNCTION update_artifacts_timestamp();

-- Comments
COMMENT ON TABLE pipeline_artifacts IS 'Tracks specific pipeline outputs (assemblies, bins, reports) with quality metrics';
COMMENT ON COLUMN pipeline_artifacts.artifact_type IS 'Type of artifact: assembly, bin, report, etc.';
COMMENT ON COLUMN pipeline_artifacts.quality_tier IS 'Quality classification: high (>90%), medium (50-90%), low (<50%)';
COMMENT ON COLUMN pipeline_artifacts.metadata IS 'JSON storage for tool-specific metrics (N50, completeness, contamination, etc.)';

-- ==================== SAMPLE DATA FOR TESTING ====================
-- Create the three lakehouse buckets if they don't exist

INSERT INTO minio_buckets (bucket_name, layer_type, description, retention_policy, encryption_enabled, versioning_enabled)
VALUES 
    ('genomic-bronze', 'bronze', 'Raw uploaded FASTQ files - permanent storage for audit trail and re-processing', 'permanent', true, true),
    ('genomic-silver', 'silver', 'Intermediate processed results from each pipeline tool - 1 year retention', 'archive_1year', true, true),
    ('genomic-gold', 'gold', 'Final curated results ready for analysis - permanent storage', 'permanent', true, true)
ON CONFLICT (bucket_name) DO NOTHING;

-- ==================== HELPER VIEWS ====================

-- View for high-quality bins ready for downstream analysis
CREATE OR REPLACE VIEW v_high_quality_bins AS
SELECT 
    pa.artifact_id,
    pa.pipeline_id,
    pr.sample_id,
    s.sample_code,
    pa.artifact_name,
    pa.quality_score AS completeness,
    pa.metadata->>'contamination' AS contamination,
    pa.metadata->>'taxonomy' AS taxonomy,
    pa.file_path AS minio_path,
    pa.created_at,
    pr.pipeline_name,
    pr.status AS pipeline_status
FROM pipeline_artifacts pa
JOIN pipeline_runs pr ON pa.pipeline_id = pr.pipeline_id
JOIN samples s ON pr.sample_id = s.sample_id
WHERE pa.artifact_type = 'bin'
  AND pa.quality_tier = 'high'
  AND pa.quality_score >= 90.0
  AND COALESCE((pa.metadata->>'contamination')::DECIMAL, 100) < 5.0
ORDER BY pa.quality_score DESC, s.sample_code, pa.artifact_name;

COMMENT ON VIEW v_high_quality_bins IS 'High-quality MAGs (>90% complete, <5% contamination) ready for publication';

-- View for pipeline results summary
CREATE OR REPLACE VIEW v_pipeline_results_summary AS
SELECT 
    pr.pipeline_id,
    pr.pipeline_name,
    s.sample_code,
    pr.status,
    pr.bronze_path,
    pr.silver_path,
    pr.gold_path,
    COUNT(DISTINCT CASE WHEN pa.artifact_type = 'assembly' THEN pa.artifact_id END) AS assembly_count,
    COUNT(DISTINCT CASE WHEN pa.artifact_type = 'bin' THEN pa.artifact_id END) AS total_bins,
    COUNT(DISTINCT CASE WHEN pa.artifact_type = 'bin' AND pa.quality_tier = 'high' THEN pa.artifact_id END) AS high_quality_bins,
    COUNT(DISTINCT CASE WHEN pa.artifact_type = 'bin' AND pa.quality_tier = 'medium' THEN pa.artifact_id END) AS medium_quality_bins,
    COUNT(DISTINCT CASE WHEN pa.artifact_type = 'bin' AND pa.quality_tier = 'low' THEN pa.artifact_id END) AS low_quality_bins,
    pr.created_at,
    pr.completed_at
FROM pipeline_runs pr
JOIN samples s ON pr.sample_id = s.sample_id
LEFT JOIN pipeline_artifacts pa ON pr.pipeline_id = pa.pipeline_id
GROUP BY pr.pipeline_id, pr.pipeline_name, s.sample_code, pr.status, 
         pr.bronze_path, pr.silver_path, pr.gold_path, pr.created_at, pr.completed_at
ORDER BY pr.created_at DESC;

COMMENT ON VIEW v_pipeline_results_summary IS 'Summary of pipeline results with artifact counts by quality tier';

-- ==================== GRANTS ====================
-- Ensure application can read/write all new tables and views

GRANT SELECT, INSERT, UPDATE, DELETE ON pipeline_artifacts TO upgrade_user;
GRANT USAGE, SELECT ON SEQUENCE pipeline_artifacts_artifact_id_seq TO upgrade_user;
GRANT SELECT ON v_high_quality_bins TO upgrade_user;
GRANT SELECT ON v_pipeline_results_summary TO upgrade_user;

-- ==================== COMPLETION MESSAGE ====================

DO $$
BEGIN
    RAISE NOTICE '✓ Migration 006: Lakehouse Architecture completed successfully';
    RAISE NOTICE '';
    RAISE NOTICE 'Changes applied:';
    RAISE NOTICE '  • Extended minio_objects with process tracking';
    RAISE NOTICE '  • Extended pipeline_runs with lakehouse paths';
    RAISE NOTICE '  • Created pipeline_artifacts table';
    RAISE NOTICE '  • Created helper views for high-quality bins';
    RAISE NOTICE '  • Added bronze/silver/gold buckets';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '  1. Update backend to upload files directly to MinIO bronze layer';
    RAISE NOTICE '  2. Implement per-process upload to silver layer';
    RAISE NOTICE '  3. Create gold layer curation logic';
END $$;
