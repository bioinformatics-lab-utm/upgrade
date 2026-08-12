-- Migration: MetaSUB protocol metadata fields
-- Date: 2026-08-12
-- Purpose: bring samples/locations schema in line with MetaSUB's official surface-
--          sampling metadata protocol (KoBoToolbox survey, PDF page 2 + pages 11-18).
--
-- Scope: schema only. Not touching models/sample.py, repositories/sample_repository.py,
-- or any route/frontend code in this pass -- follow-up needed before these columns are
-- writable through the live API.
--
-- samples.sample_type is intentionally NOT touched: it is hard-validated as sequencing
-- platform in services/pipeline_service.py:346-349, and separately repurposed by 6+
-- batch/import scripts as an informal sample-category field. This migration adds a new,
-- differently-named column (sample_role) for MetaSUB's control/experiment concept.
--
-- All new columns are nullable, no defaults: multiple live batch scripts
-- (sra_batch_processor.py, ena_batch_processor.py, run_download_queue.py,
-- queue_large_samples.py, queue_ncbi_env_50.py, download_and_queue_env_metagenomes.py)
-- do explicit-column-list INSERTs into samples/locations and must keep working
-- unmodified.
--
-- NOTE ON schema_migrations: deliberately not inserting a tracking row here. The table's
-- existing entries (versions 1-4, then 17-18) do not correspond to this repo's
-- 001-012 migration files (e.g. tracked "001_initial_upgrade_schema.sql" vs. actual
-- "001_initial_schema.sql"), and migrations 011/012 were verified NOT applied to this
-- live database (011's samples_geolocated view and 012's new tables do not exist here).
-- Adding a row would fabricate continuity that doesn't exist. This file's own
-- IF NOT EXISTS guards are the source of truth for whether it has been applied.

-- ============================================================
-- 1. locations: site-level MetaSUB fields.
--    Confirmed real reuse: sra_batch_processor.py / ena_batch_processor.py dedupe
--    locations by GPS proximity (<0.01 deg) before creating a new row, so these
--    values are shared across every sample taken at the same physical site.
-- ============================================================
ALTER TABLE locations
  ADD COLUMN IF NOT EXISTS location_type VARCHAR(100),
  ADD COLUMN IF NOT EXISTS transit_line VARCHAR(150),
  ADD COLUMN IF NOT EXISTS sublocation VARCHAR(150),
  ADD COLUMN IF NOT EXISTS setting VARCHAR(20)
      CONSTRAINT valid_setting CHECK (setting IS NULL OR setting IN ('urban','suburban','rural')),
  ADD COLUMN IF NOT EXISTS ground_level VARCHAR(30)
      CONSTRAINT valid_ground_level CHECK (ground_level IS NULL OR ground_level IN (
        'underground','aboveground_open','aboveground_closed','aboveground_mixed'));

COMMENT ON COLUMN locations.location_type IS 'MetaSUB protocol "Location Type" -- open list, values defined per-city sampling plan (e.g. Subway/Train station, Airport, Laboratory). Free text by design, not a closed CHECK.';
COMMENT ON COLUMN locations.transit_line   IS 'MetaSUB protocol "Line" -- transit route/line, for transit locations.';
COMMENT ON COLUMN locations.sublocation    IS 'MetaSUB protocol "Sublocation" -- additional location detail within the site.';
COMMENT ON COLUMN locations.setting        IS 'MetaSUB protocol "Setting": urban / suburban / rural.';
COMMENT ON COLUMN locations.ground_level   IS 'MetaSUB protocol "Ground level": underground(/underwater), aboveground open/closed/mixed area.';
COMMENT ON COLUMN locations.surface_material IS 'LEGACY/UNUSED -- confirmed 0 non-NULL rows, no app code reads/writes this. Unrelated to samples.surface_material_sampled (added 013_metasub_metadata.sql). Do not repurpose.';
COMMENT ON COLUMN locations.traffic_density  IS 'LEGACY/UNUSED -- confirmed 0 non-NULL rows. Subjective site-level rating, unrelated to samples.traffic_count (added 013_metasub_metadata.sql), which is MetaSUB''s per-visit measured people-count bucket. Do not repurpose.';

-- ============================================================
-- 2. samples: per-swab MetaSUB fields -- can differ between two samples taken at the
--    same location_id (different visit, different object, different conditions).
-- ============================================================
ALTER TABLE samples
  ADD COLUMN IF NOT EXISTS sample_role VARCHAR(20)
      CONSTRAINT valid_sample_role CHECK (sample_role IS NULL OR sample_role IN (
        'experiment','negative_control','positive_control')),
  ADD COLUMN IF NOT EXISTS object_sampled VARCHAR(100),
  ADD COLUMN IF NOT EXISTS surface_material_sampled VARCHAR(50)
      CONSTRAINT valid_surface_material_sampled CHECK (surface_material_sampled IS NULL OR surface_material_sampled IN (
        'concrete','ceramic','formica_resin','glass','metal','painted_metal','plastic',
        'pvc','rubber','stone','wood','natural_fabric','synthetic_fabric','other')),
  ADD COLUMN IF NOT EXISTS traffic_count VARCHAR(10)
      CONSTRAINT valid_traffic_count CHECK (traffic_count IS NULL OR traffic_count IN (
        '0','1-10','11-20','21-30','31-40','41-50','50+')),
  ADD COLUMN IF NOT EXISTS temperature_measured BOOLEAN,
  ADD COLUMN IF NOT EXISTS temperature_celsius NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS humidity_measured BOOLEAN,
  ADD COLUMN IF NOT EXISTS humidity_percent NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS gps_accuracy_m NUMERIC(6,2);

COMMENT ON COLUMN samples.sample_role IS 'MetaSUB protocol "Sample Type" (QC role): experiment / negative_control / positive_control. Deliberately NOT named sample_type -- that column already means sequencing platform (pipeline_service.py) in the one hard-validated write path, and a 3rd, environmental-category meaning in several batch import scripts.';
COMMENT ON COLUMN samples.object_sampled IS 'MetaSUB protocol "Object type/Sampling place" -- open list (Door, Escalator handrail, Floor, Turnstile, ... "not limited to"). Free text by design.';
COMMENT ON COLUMN samples.surface_material_sampled IS 'MetaSUB protocol "Surface material" -- closed list. Distinct from legacy/unused locations.surface_material.';
COMMENT ON COLUMN samples.traffic_count IS 'MetaSUB protocol "Traffic" -- bucketed people-count at time of sampling, matches protocol bucket boundaries exactly (not a raw integer). Distinct from legacy/unused locations.traffic_density.';
COMMENT ON COLUMN samples.temperature_celsius IS 'On-site temperature at time of sampling, meaningful only when temperature_measured = true. Distinct from weather_measurements.temperature (ambient Open-Meteo API data, per-location/per-timestamp).';
COMMENT ON COLUMN samples.humidity_percent IS 'On-site humidity at time of sampling, meaningful only when humidity_measured = true. Distinct from weather_measurements.humidity (ambient Open-Meteo API data).';
COMMENT ON COLUMN samples.gps_accuracy_m IS 'MetaSUB protocol geolocation "accuracy (m)" for this specific sampling visit''s GPS reading. Kept on samples, not locations, because accuracy is a property of the individual GPS fix taken that visit (device/signal dependent), not of the physical site -- unlike lat/long/elevation, which live on locations and are reused across visits.';

-- ============================================================
-- 3. samples.barcode: enforce MetaSUB's "must be exactly 10 digits" format.
--    Verified safe: live data has 0 non-NULL barcodes (checked 2026-08-12), so this
--    cannot fail against existing rows. Column itself stays VARCHAR(50)/nullable --
--    only the format is enforced, and only when a value is present, since non-MetaSUB
--    samples (NCBI/ENA imports) will likely never populate it.
--    No "ADD CONSTRAINT IF NOT EXISTS" in Postgres -- guarded manually.
-- ============================================================
DO $$
BEGIN
    ALTER TABLE samples
      ADD CONSTRAINT valid_barcode_format
      CHECK (barcode IS NULL OR barcode ~ '^[0-9]{10}$');
EXCEPTION
    WHEN duplicate_object THEN
        NULL; -- constraint already exists; re-running this file is a no-op here
END $$;
