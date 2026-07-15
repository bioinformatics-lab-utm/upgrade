-- ============================================
-- Data Lineage Testing & Verification Queries
-- ============================================
-- Purpose: Verify that data lineage is being tracked correctly
-- Date: 2026-01-09

-- ==================== CHECK LINEAGE POPULATION ====================

-- 1. Count total lineage records (should be > 0 after pipeline run)
SELECT
    COUNT(*) as total_lineage_records,
    COUNT(DISTINCT source_object_id) as unique_sources,
    COUNT(DISTINCT target_object_id) as unique_targets
FROM data_lineage;

-- 2. Lineage by transformation type
SELECT
    transformation_type,
    transformation_process,
    COUNT(*) as record_count,
    MIN(transformation_time) as first_transformation,
    MAX(transformation_time) as last_transformation
FROM data_lineage
GROUP BY transformation_type, transformation_process
ORDER BY transformation_type, record_count DESC;

-- ==================== BRONZE → SILVER LINEAGE ====================

-- 3. Trace Bronze → Silver transformations
SELECT
    dl.transformation_process,
    mb_source.bucket_name as source_bucket,
    mo_source.object_key as source_file,
    mb_target.bucket_name as target_bucket,
    mo_target.object_key as target_file,
    mo_target.layer_stage,
    dl.transformation_time,
    dl.transformation_metadata
FROM data_lineage dl
JOIN minio_objects mo_source ON dl.source_object_id = mo_source.object_id
JOIN minio_objects mo_target ON dl.target_object_id = mo_target.object_id
JOIN minio_buckets mb_source ON mo_source.bucket_id = mb_source.bucket_id
JOIN minio_buckets mb_target ON mo_target.bucket_id = mb_target.bucket_id
WHERE mb_source.bucket_name = 'genomic-bronze'
  AND mb_target.bucket_name = 'genomic-silver'
ORDER BY dl.transformation_time DESC
LIMIT 20;

-- ==================== SILVER → GOLD LINEAGE ====================

-- 4. Trace Silver → Gold curation
SELECT
    dl.transformation_process,
    mo_source.process_name as source_process,
    mo_source.object_key as silver_file,
    mo_target.object_key as gold_file,
    pa.artifact_type,
    pa.quality_tier,
    pa.quality_score,
    dl.transformation_metadata,
    dl.transformation_time
FROM data_lineage dl
JOIN minio_objects mo_source ON dl.source_object_id = mo_source.object_id
JOIN minio_objects mo_target ON dl.target_object_id = mo_target.object_id
JOIN minio_buckets mb_source ON mo_source.bucket_id = mb_source.bucket_id
JOIN minio_buckets mb_target ON mo_target.bucket_id = mb_target.bucket_id
LEFT JOIN pipeline_artifacts pa ON mo_target.object_id = pa.minio_object_id
WHERE mb_source.bucket_name = 'genomic-silver'
  AND mb_target.bucket_name = 'genomic-gold'
ORDER BY dl.transformation_time DESC
LIMIT 20;

-- ==================== COMPLETE LINEAGE CHAIN ====================

-- 5. Full lineage chain: Bronze → Silver → Gold (recursive)
WITH RECURSIVE lineage_chain AS (
    -- Start with Bronze files
    SELECT
        mo.object_id,
        mo.object_key,
        mb.bucket_name,
        mo.process_name,
        1 as depth,
        ARRAY[mo.object_id] as path,
        mo.object_key::text as chain
    FROM minio_objects mo
    JOIN minio_buckets mb ON mo.bucket_id = mb.bucket_id
    WHERE mb.bucket_name = 'genomic-bronze'

    UNION ALL

    -- Follow lineage to Silver and Gold
    SELECT
        mo_target.object_id,
        mo_target.object_key,
        mb_target.bucket_name,
        mo_target.process_name,
        lc.depth + 1,
        lc.path || mo_target.object_id,
        lc.chain || ' → ' || mo_target.object_key
    FROM lineage_chain lc
    JOIN data_lineage dl ON dl.source_object_id = lc.object_id
    JOIN minio_objects mo_target ON dl.target_object_id = mo_target.object_id
    JOIN minio_buckets mb_target ON mo_target.bucket_id = mb_target.bucket_id
    WHERE lc.depth < 10  -- Prevent infinite loops
)
SELECT
    bucket_name,
    depth,
    chain as full_lineage_chain
FROM lineage_chain
WHERE depth > 1  -- Only show chains with transformations
ORDER BY depth DESC, chain
LIMIT 50;

-- ==================== LINEAGE GAPS ====================

-- 6. Find Silver objects without source lineage (potential gaps)
SELECT
    mo.object_id,
    mo.object_key,
    mo.process_name,
    mo.layer_stage,
    mo.created_at,
    'Missing Bronze source' as issue
FROM minio_objects mo
JOIN minio_buckets mb ON mo.bucket_id = mb.bucket_id
WHERE mb.bucket_name = 'genomic-silver'
  AND NOT EXISTS (
      SELECT 1 FROM data_lineage dl
      WHERE dl.target_object_id = mo.object_id
  )
ORDER BY mo.created_at DESC
LIMIT 20;

-- 7. Find Gold objects without source lineage (potential gaps)
SELECT
    mo.object_id,
    mo.object_key,
    pa.artifact_type,
    pa.quality_tier,
    mo.created_at,
    'Missing Silver source' as issue
FROM minio_objects mo
JOIN minio_buckets mb ON mo.bucket_id = mb.bucket_id
LEFT JOIN pipeline_artifacts pa ON mo.object_id = pa.minio_object_id
WHERE mb.bucket_name = 'genomic-gold'
  AND NOT EXISTS (
      SELECT 1 FROM data_lineage dl
      WHERE dl.target_object_id = mo.object_id
  )
ORDER BY mo.created_at DESC
LIMIT 20;

-- ==================== LINEAGE STATISTICS ====================

-- 8. Lineage coverage by layer
SELECT
    mb.bucket_name,
    COUNT(DISTINCT mo.object_id) as total_objects,
    COUNT(DISTINCT dl.target_object_id) as objects_with_lineage,
    ROUND(100.0 * COUNT(DISTINCT dl.target_object_id) / COUNT(DISTINCT mo.object_id), 2) as coverage_percent
FROM minio_objects mo
JOIN minio_buckets mb ON mo.bucket_id = mb.bucket_id
LEFT JOIN data_lineage dl ON mo.object_id = dl.target_object_id
WHERE mb.bucket_name IN ('genomic-bronze', 'genomic-silver', 'genomic-gold')
GROUP BY mb.bucket_name
ORDER BY mb.bucket_name;

-- 9. Average transformation chain length
SELECT
    AVG(chain_length) as avg_chain_length,
    MAX(chain_length) as max_chain_length,
    MIN(chain_length) as min_chain_length
FROM (
    SELECT target_object_id, COUNT(*) as chain_length
    FROM data_lineage
    GROUP BY target_object_id
) as chains;

-- ==================== HIGH-QUALITY MAG LINEAGE ====================

-- 10. Trace lineage for high-quality MAGs (completeness >= 90%)
SELECT
    s.sample_code,
    pa.artifact_name,
    pa.quality_score as completeness,
    pa.metadata->>'contamination' as contamination,
    -- Bronze source
    mo_bronze.object_key as bronze_file,
    -- Silver intermediate
    mo_silver.object_key as silver_file,
    mo_silver.process_name as silver_process,
    -- Gold final
    mo_gold.object_key as gold_file,
    pa.created_at as curated_at
FROM pipeline_artifacts pa
JOIN pipeline_runs pr ON pa.pipeline_id = pr.pipeline_id
JOIN samples s ON pr.sample_id = s.sample_id
JOIN minio_objects mo_gold ON pa.minio_object_id = mo_gold.object_id
-- Gold → Silver lineage
LEFT JOIN data_lineage dl_gold_silver ON mo_gold.object_id = dl_gold_silver.target_object_id
LEFT JOIN minio_objects mo_silver ON dl_gold_silver.source_object_id = mo_silver.object_id
-- Silver → Bronze lineage
LEFT JOIN data_lineage dl_silver_bronze ON mo_silver.object_id = dl_silver_bronze.target_object_id
LEFT JOIN minio_objects mo_bronze ON dl_silver_bronze.source_object_id = mo_bronze.object_id
WHERE pa.artifact_type = 'bin'
  AND pa.quality_tier = 'high'
  AND pa.quality_score >= 90
ORDER BY pa.quality_score DESC, pa.created_at DESC
LIMIT 20;

-- ==================== VERIFICATION SUMMARY ====================

-- 11. Overall lineage health check
SELECT
    'Data Lineage Populated' as check_name,
    CASE
        WHEN COUNT(*) > 0 THEN '✅ PASS'
        ELSE '❌ FAIL'
    END as status,
    COUNT(*) as record_count
FROM data_lineage

UNION ALL

SELECT
    'Bronze → Silver Tracking',
    CASE
        WHEN COUNT(*) > 0 THEN '✅ PASS'
        ELSE '❌ FAIL'
    END,
    COUNT(*)
FROM data_lineage dl
JOIN minio_objects mo_target ON dl.target_object_id = mo_target.object_id
JOIN minio_buckets mb_target ON mo_target.bucket_id = mb_target.bucket_id
WHERE mb_target.bucket_name = 'genomic-silver'

UNION ALL

SELECT
    'Silver → Gold Tracking',
    CASE
        WHEN COUNT(*) > 0 THEN '✅ PASS'
        ELSE '❌ FAIL'
    END,
    COUNT(*)
FROM data_lineage dl
JOIN minio_objects mo_target ON dl.target_object_id = mo_target.object_id
JOIN minio_buckets mb_target ON mo_target.bucket_id = mb_target.bucket_id
WHERE mb_target.bucket_name = 'genomic-gold';

-- ==================== USAGE EXAMPLES ====================

-- Example 1: Find all downstream results from a specific Bronze file
-- SELECT * FROM get_downstream_lineage(123);  -- Replace 123 with Bronze object_id

-- Example 2: Find the original Bronze source for a Gold MAG
-- SELECT * FROM get_upstream_lineage(456);  -- Replace 456 with Gold object_id

-- Example 3: Check lineage for specific pipeline run
-- SELECT * FROM data_lineage dl
-- JOIN minio_objects mo ON dl.target_object_id = mo.object_id
-- WHERE mo.pipeline_id = 789;  -- Replace with your pipeline_id
