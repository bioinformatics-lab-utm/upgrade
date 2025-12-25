-- Migration: Add Geolocation Support
-- Date: 2025-01-16
-- Purpose: Add geographic coordinates and location information to samples for map visualization

-- Add geolocation columns to samples table
ALTER TABLE samples 
  ADD COLUMN IF NOT EXISTS latitude DECIMAL(10, 8),
  ADD COLUMN IF NOT EXISTS longitude DECIMAL(11, 8),
  ADD COLUMN IF NOT EXISTS location_name VARCHAR(255),
  ADD COLUMN IF NOT EXISTS city VARCHAR(100),
  ADD COLUMN IF NOT EXISTS country VARCHAR(100) DEFAULT 'Romania';

-- Add indexes for faster geospatial queries
CREATE INDEX IF NOT EXISTS idx_samples_coordinates 
  ON samples(latitude, longitude) 
  WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_samples_city 
  ON samples(city);

CREATE INDEX IF NOT EXISTS idx_samples_country 
  ON samples(country);

-- Add comment
COMMENT ON COLUMN samples.latitude IS 'Geographic latitude (WGS84)';
COMMENT ON COLUMN samples.longitude IS 'Geographic longitude (WGS84)';
COMMENT ON COLUMN samples.location_name IS 'Human-readable location name';

-- Insert example locations for Romania
-- These can be used for demo purposes

-- Example 1: Bucharest City Center
-- UPDATE samples 
-- SET 
--   latitude = 44.4268,
--   longitude = 26.1025,
--   location_name = 'Bucharest City Center - Environmental Station',
--   city = 'Bucharest',
--   country = 'Romania'
-- WHERE sample_code = 'YOUR_SAMPLE_CODE_1';

-- Example 2: Cluj-Napoca
-- UPDATE samples 
-- SET 
--   latitude = 46.7712,
--   longitude = 23.6236,
--   location_name = 'Cluj-Napoca - University Hospital',
--   city = 'Cluj-Napoca',
--   country = 'Romania'
-- WHERE sample_code = 'YOUR_SAMPLE_CODE_2';

-- Example 3: Timișoara
-- UPDATE samples 
-- SET 
--   latitude = 45.7489,
--   longitude = 21.2087,
--   location_name = 'Timișoara - Wastewater Treatment Plant',
--   city = 'Timișoara',
--   country = 'Romania'
-- WHERE sample_code = 'YOUR_SAMPLE_CODE_3';

-- Example 4: Iași
-- UPDATE samples 
-- SET 
--   latitude = 47.1585,
--   longitude = 27.6014,
--   location_name = 'Iași - Infectious Disease Hospital',
--   city = 'Iași',
--   country = 'Romania'
-- WHERE sample_code = 'YOUR_SAMPLE_CODE_4';

-- Example 5: Constanța (Black Sea Coast)
-- UPDATE samples 
-- SET 
--   latitude = 44.1598,
--   longitude = 28.6348,
--   location_name = 'Constanța - Port Area',
--   city = 'Constanța',
--   country = 'Romania'
-- WHERE sample_code = 'YOUR_SAMPLE_CODE_5';

-- Create a view for samples with complete geolocation data
CREATE OR REPLACE VIEW samples_geolocated AS
SELECT 
  s.*,
  COUNT(ar.gene_name) as amr_genes_count,
  COUNT(DISTINCT ar.gene_name) as unique_amr_genes,
  COUNT(DISTINCT tr.species) as pathogens_count
FROM samples s
LEFT JOIN amr_results ar ON s.sample_id = ar.sample_id
LEFT JOIN taxonomy_results tr ON s.sample_id = tr.sample_id
WHERE s.latitude IS NOT NULL 
  AND s.longitude IS NOT NULL
GROUP BY s.sample_id;

-- Grant permissions
GRANT SELECT ON samples_geolocated TO upgrade_user;

-- Success message
DO $$
BEGIN
  RAISE NOTICE '✅ Geolocation support added to samples table';
  RAISE NOTICE '📍 Ready for map visualization';
  RAISE NOTICE '🗺️ Run UPDATE queries above to add coordinates to your samples';
END $$;
