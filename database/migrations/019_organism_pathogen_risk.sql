-- Migration: Pathogen risk of detected organisms
-- Date: 2026-10-16
-- Description: detected_organisms rows are now the run's genera with their share
-- of the assembled bases (services/run_results.py). The map's "Pathogens" count
-- needs to know which of them are (opportunistic) pathogens, as the results page
-- shows; store the same classification next to each row.
-- Idempotent: safe to run more than once.

BEGIN;

ALTER TABLE detected_organisms ADD COLUMN IF NOT EXISTS risk_level VARCHAR(10);
ALTER TABLE detected_organisms ADD COLUMN IF NOT EXISTS pathogenicity VARCHAR(20);

COMMENT ON COLUMN detected_organisms.risk_level IS 'high | medium | low, from services/run_results.py KNOWN_PATHOGENS';
COMMENT ON COLUMN detected_organisms.pathogenicity IS 'pathogen | opportunistic | commensal | environmental';

COMMIT;
