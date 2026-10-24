-- Migration: Fix swapped ABRicate identity / coverage in resistance_genes
-- Date: 2026-10-16
-- Description: nextflow/bin/generate_summary.py read ABRicate's %COVERAGE column
-- as identity and %IDENTITY as coverage, and judged the risk on coverage. Every
-- row it produced has detection_tool = 'card'. Swap the two values back,
-- recompute what was derived from them, and mark the rows with the
-- detection_tool the fixed script now writes ('ABRicate/card'), which also
-- makes this migration safe to run more than once.
--
-- predicted_resistance of these rows holds ABRicate's PRODUCT text instead of
-- the antibiotic class; it is not shown anywhere and cannot be rebuilt here.

BEGIN;

UPDATE resistance_genes
SET coverage         = identity,
    identity         = coverage,
    quality_score    = coverage,          -- the real identity (generate_summary stored identity here)
    confidence_level = CASE WHEN coverage >= 90 THEN 'high' ELSE 'moderate' END,
    detection_tool   = 'ABRicate/card'
WHERE detection_tool = 'card';

COMMIT;
