-- Migration 001: Initial UPGRADE Project Schema
-- UPGRADE Weather & Genomic Surveillance System
-- Project: Urban Pathogen Genomic Surveillance Network
-- Version: 1.0.0
-- Applied: 2025-01-01

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "postgis" CASCADE;

-- Create custom types
CREATE TYPE weather_source AS ENUM ('open_meteo', 'manual', 'sensor', 'station');
CREATE TYPE alert_severity AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE data_quality AS ENUM ('excellent', 'good', 'fair', 'poor');
CREATE TYPE sample_status AS ENUM ('collected', 'processing', 'sequenced', 'analyzed', 'archived');
CREATE TYPE collaboration_type AS ENUM ('training', 'data_analysis', 'sample_processing', 'research_visit', 'publication');

-- =========================
-- Reference Data Tables
-- =========================

CREATE TABLE institutions (
    institution_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    country VARCHAR(100) NOT NULL,
    city VARCHAR(100),
    type VARCHAR(100), -- University, Research Institute, Hospital
    address TEXT,
    website VARCHAR(255),
    contact_email VARCHAR(150),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE researchers (
    researcher_id SERIAL PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    role VARCHAR(100), -- PI, Co-PI, Postdoc, PhD student, Researcher
    email VARCHAR(150),
    orcid VARCHAR(50),
    institution_id INT REFERENCES institutions(institution_id),
    specialization VARCHAR(200),
    active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE locations (
    location_id SERIAL PRIMARY KEY,
    location_name VARCHAR(255) NOT NULL,
    country VARCHAR(100) NOT NULL,
    region VARCHAR(100),
    city VARCHAR(100),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    elevation INTEGER,
    timezone VARCHAR(50) DEFAULT 'UTC',
    -- University campus specific fields
    campus_area VARCHAR(100), -- university_restaurant, cafe, lab, library, dormitory, outdoor
    building_name VARCHAR(150),
    floor_level INTEGER,
    room_number VARCHAR(50),
    traffic_density VARCHAR(50), -- high, medium, low, very_high
    surface_material VARCHAR(100), -- metal, plastic, wood, glass, ceramic
    cleaning_frequency VARCHAR(50), -- daily, twice_daily, weekly, as_needed
    access_type VARCHAR(50), -- public, restricted, staff_only
    -- Environmental characteristics
    indoor_outdoor VARCHAR(20) DEFAULT 'indoor', -- indoor, outdoor, semi_outdoor
    ventilation_type VARCHAR(50), -- natural, mechanical, mixed, none
    lighting_type VARCHAR(50), -- natural, artificial, mixed
    occupancy_pattern VARCHAR(100), -- continuous, peak_hours, seasonal, irregular
    -- Metadata
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT valid_latitude CHECK (latitude >= -90 AND latitude <= 90),
    CONSTRAINT valid_longitude CHECK (longitude >= -180 AND longitude <= 180),
    CONSTRAINT valid_traffic_density CHECK (traffic_density IN ('low', 'medium', 'high', 'very_high')),
    CONSTRAINT valid_indoor_outdoor CHECK (indoor_outdoor IN ('indoor', 'outdoor', 'semi_outdoor'))
);

CREATE TABLE pathogen_reference (
    pathogen_id SERIAL PRIMARY KEY,
    pathogen_name VARCHAR(255) NOT NULL,
    scientific_name VARCHAR(255),
    taxonomy_id VARCHAR(50),
    genome_accession VARCHAR(100),
    pathogen_type VARCHAR(50), -- bacteria, virus, fungus, parasite
    gram_stain VARCHAR(20), -- positive, negative, not_applicable
    virulence_level VARCHAR(50), -- low, medium, high, unknown
    who_priority VARCHAR(50), -- critical, high, medium, not_listed
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE databases_reference (
    database_id SERIAL PRIMARY KEY,
    database_name VARCHAR(150) NOT NULL,
    version VARCHAR(50),
    description TEXT,
    source_url VARCHAR(255),
    database_type VARCHAR(100), -- ARG, virulence, taxonomy, genome
    last_updated DATE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE gene_families (
    gene_family_id SERIAL PRIMARY KEY,
    family_name VARCHAR(100) NOT NULL,
    description TEXT,
    mechanism_of_action TEXT,
    target_antibiotic_class VARCHAR(150),
    prevalence VARCHAR(50), -- common, rare, emerging
    clinical_significance VARCHAR(100),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE antibiotic_reference (
    antibiotic_id SERIAL PRIMARY KEY,
    antibiotic_name VARCHAR(150) NOT NULL,
    class_name VARCHAR(100),
    mechanism VARCHAR(200),
    clinical_use VARCHAR(200),
    who_classification VARCHAR(100), -- critically_important, highly_important, important
    resistance_patterns TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- Weather Data Tables (Open-Meteo Integration)
-- =========================

CREATE TABLE weather_measurements (
    weather_id SERIAL PRIMARY KEY,
    location_id INT REFERENCES locations(location_id) ON DELETE CASCADE,
    source weather_source DEFAULT 'open_meteo',
    
    -- Core measurements
    measurement_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    temperature DECIMAL(5,2),
    humidity DECIMAL(5,2),
    apparent_temperature DECIMAL(5,2),
    rainfall DECIMAL(6,2),
    windspeed DECIMAL(5,2),
    wind_direction INTEGER,
    wind_gusts DECIMAL(5,2),
    
    -- Extended weather data
    pressure_msl DECIMAL(7,2),
    surface_pressure DECIMAL(7,2),
    cloud_cover INTEGER,
    visibility DECIMAL(8,2),
    uv_index DECIMAL(4,2),
    weather_code INTEGER,
    is_day BOOLEAN,
    
    -- Data quality
    weather_api_source VARCHAR(50),
    quality_score DECIMAL(3,2) DEFAULT 1.00,
    data_quality data_quality DEFAULT 'good',
    raw_data_path VARCHAR(512),
    
    -- Metadata
    api_response_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT valid_humidity CHECK (humidity >= 0 AND humidity <= 100),
    CONSTRAINT valid_cloud_cover CHECK (cloud_cover >= 0 AND cloud_cover <= 100),
    CONSTRAINT valid_wind_direction CHECK (wind_direction >= 0 AND wind_direction < 360),
    CONSTRAINT valid_quality_score CHECK (quality_score >= 0 AND quality_score <= 1)
);

-- =========================
-- Sampling Campaigns & Biobank
-- =========================

CREATE TABLE sampling_campaigns (
    campaign_id SERIAL PRIMARY KEY,
    campaign_name VARCHAR(200) NOT NULL,
    project_code VARCHAR(50), -- UPGRADE-2024-01, etc.
    start_date DATE NOT NULL,
    end_date DATE,
    responsible_id INT REFERENCES researchers(researcher_id),
    co_responsible_id INT REFERENCES researchers(researcher_id),
    institution_id INT REFERENCES institutions(institution_id),
    
    -- Campaign details
    campaign_type VARCHAR(100), -- routine_surveillance, outbreak_investigation, research_study
    sampling_frequency VARCHAR(100), -- weekly, bi_weekly, monthly, event_driven
    target_pathogens TEXT[], -- array of target pathogen names
    target_locations INTEGER[], -- array of location IDs
    
    -- Collaboration info
    romanian_partner BOOLEAN DEFAULT false,
    moldovan_partner BOOLEAN DEFAULT false,
    cross_border_study BOOLEAN DEFAULT false,
    
    description TEXT,
    objectives TEXT,
    methodology TEXT,
    expected_samples INTEGER,
    budget_allocated DECIMAL(10,2),
    funding_source VARCHAR(200),
    ethical_approval_number VARCHAR(100),
    
    -- Status tracking
    status VARCHAR(50) DEFAULT 'planned', -- planned, active, completed, cancelled
    completion_percentage DECIMAL(5,2) DEFAULT 0.00,
    
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE samples (
    sample_id SERIAL PRIMARY KEY,
    sample_code VARCHAR(100) UNIQUE NOT NULL,
    collection_date DATE NOT NULL,
    collection_time TIME,
    location_id INT REFERENCES locations(location_id),
    pathogen_id INT REFERENCES pathogen_reference(pathogen_id),
    campaign_id INT REFERENCES sampling_campaigns(campaign_id),
    collector_id INT REFERENCES researchers(researcher_id),
    
    -- Sample characteristics
    sample_type VARCHAR(100), -- surface_swab, air_sample, water_sample, soil_sample
    sample_volume_ml DECIMAL(8,2),
    collection_method VARCHAR(150),
    storage_conditions VARCHAR(100),
    transport_conditions VARCHAR(100),
    
    -- Sequencing information
    sequencing_platform VARCHAR(150), -- MinION, GridION, PromethION
    sequencing_kit VARCHAR(100), -- SQK-LSK109, SQK-RBK004, etc.
    flowcell_type VARCHAR(50), -- R9.4.1, R10.4.1
    read_length_avg INTEGER,
    sequencing_depth DECIMAL(10,2),
    coverage DECIMAL(10,2),
    quality_score DECIMAL(5,2),
    
    -- Processing status
    status sample_status DEFAULT 'collected',
    processing_priority INTEGER DEFAULT 1, -- 1=highest, 5=lowest
    expected_results_date DATE,
    
    -- Project tracking
    project_id VARCHAR(100),
    batch_id VARCHAR(100),
    barcode VARCHAR(50),
    
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sample_metadata (
    metadata_id SERIAL PRIMARY KEY,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    
    -- Environmental conditions at collection
    surface_type VARCHAR(150),  -- door_handle, desk_surface, handrail, bench, etc.
    surface_material_detail VARCHAR(100), -- stainless_steel, painted_metal, wood_varnished
    surface_area_cm2 DECIMAL(8,2), -- actual surface area sampled
    contact_frequency VARCHAR(50), -- very_high, high, medium, low (how often touched)
    
    -- Temporal context
    season VARCHAR(50), -- spring, summer, autumn, winter
    day_of_week VARCHAR(20),
    time_category VARCHAR(50), -- morning, afternoon, evening, night
    academic_period VARCHAR(50), -- semester, exam_period, vacation, conference
    
    -- Human activity context
    human_density INTEGER, -- estimated people in area during sampling
    student_density_nearby INTEGER,
    staff_density_nearby INTEGER,
    visitor_density_nearby INTEGER,
    activity_level VARCHAR(50), -- low, medium, high, very_high
    
    -- Environmental factors
    light_exposure VARCHAR(50), -- direct_sunlight, indirect_light, artificial_light, dark
    air_circulation VARCHAR(50), -- good, moderate, poor, stagnant
    proximity_to_food_service BOOLEAN DEFAULT false,
    proximity_to_restroom BOOLEAN DEFAULT false,
    proximity_to_entrance BOOLEAN DEFAULT false,
    
    -- Maintenance and hygiene
    cleaning_time_since_last INTEGER, -- hours since last cleaning
    sanitization_event BOOLEAN DEFAULT false,
    sanitization_type VARCHAR(100), -- alcohol_wipe, bleach_solution, UV_light, etc.
    sanitization_time_before INTEGER, -- minutes before sampling
    
    -- Weather correlation
    weather_id INT REFERENCES weather_measurements(weather_id),
    indoor_temperature DECIMAL(5,2),
    indoor_humidity DECIMAL(5,2),
    outdoor_conditions_impact VARCHAR(100),
    
    -- Additional observations
    visible_contamination BOOLEAN DEFAULT false,
    unusual_conditions TEXT,
    photographer_id INT REFERENCES researchers(researcher_id),
    photo_paths TEXT[], -- array of photo file paths
    
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE biobank (
    biobank_id SERIAL PRIMARY KEY,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    
    -- Storage details
    storage_location VARCHAR(100), -- Freezer ID / Box / Position
    storage_facility VARCHAR(150), -- USV Biobank, TUM Biobank
    storage_temperature DECIMAL(5,2), -- -80°C, -20°C, 4°C, room temperature
    storage_conditions VARCHAR(200),
    container_type VARCHAR(100), -- cryovial, eppendorf_tube, falcon_tube
    container_volume_ml DECIMAL(6,2),
    
    -- Tracking
    archived_date DATE,
    retrieved_date DATE,
    retrieval_reason VARCHAR(200),
    retrieved_by INT REFERENCES researchers(researcher_id),
    remaining_volume_ml DECIMAL(6,2),
    
    -- Quality control
    integrity_check_date DATE,
    integrity_status VARCHAR(50), -- good, degraded, compromised
    viability_tested BOOLEAN DEFAULT false,
    viability_result VARCHAR(100),
    
    -- Access control
    access_restrictions TEXT,
    consent_status VARCHAR(100),
    ethics_approval VARCHAR(100),
    
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- One Health Hosts
-- =========================

CREATE TABLE hosts (
    host_id SERIAL PRIMARY KEY,
    host_type VARCHAR(50) NOT NULL, -- human, animal, environment, surface
    species VARCHAR(150), -- homo_sapiens, rattus_norvegicus, etc.
    subspecies VARCHAR(150),
    age_group VARCHAR(50), -- infant, child, adolescent, adult, elderly
    sex VARCHAR(20), -- male, female, unknown, not_applicable
    health_status VARCHAR(100), -- healthy, symptomatic, chronic_condition, immunocompromised
    occupation VARCHAR(150), -- student, faculty, staff, visitor, maintenance
    
    -- Risk factors
    antibiotic_exposure_recent BOOLEAN DEFAULT false,
    antibiotic_exposure_details TEXT,
    hospital_contact_recent BOOLEAN DEFAULT false,
    travel_history_recent BOOLEAN DEFAULT false,
    travel_destinations TEXT,
    
    -- Demographics (anonymized)
    demographic_group VARCHAR(100),
    lifestyle_factors TEXT,
    
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Link samples to hosts
ALTER TABLE samples ADD COLUMN host_id INT REFERENCES hosts(host_id);

-- =========================
-- Cross-Border Collaboration Tracking
-- =========================

CREATE TABLE collaboration_activities (
    activity_id SERIAL PRIMARY KEY,
    activity_name VARCHAR(200) NOT NULL,
    activity_type collaboration_type NOT NULL,
    
    -- Participants
    romanian_researcher_id INT REFERENCES researchers(researcher_id),
    moldovan_researcher_id INT REFERENCES researchers(researcher_id),
    romanian_institution_id INT REFERENCES institutions(institution_id),
    moldovan_institution_id INT REFERENCES institutions(institution_id),
    
    -- Additional participants (JSON array of researcher IDs)
    other_participants JSONB DEFAULT '[]',
    
    -- Timing
    start_date DATE NOT NULL,
    end_date DATE,
    duration_days INTEGER,
    
    -- Details
    description TEXT,
    objectives TEXT,
    deliverables TEXT,
    outcomes TEXT,
    success_metrics TEXT,
    
    -- Resources
    budget_allocated DECIMAL(10,2),
    budget_spent DECIMAL(10,2),
    currency VARCHAR(10) DEFAULT 'EUR',
    
    -- Associated data/samples
    related_samples INTEGER[], -- array of sample IDs
    related_campaigns INTEGER[], -- array of campaign IDs
    
    -- Status and evaluation
    status VARCHAR(50) DEFAULT 'planned', -- planned, ongoing, completed, cancelled
    evaluation_score INTEGER, -- 1-5 scale
    lessons_learned TEXT,
    recommendations TEXT,
    
    -- Documentation
    report_path VARCHAR(255),
    publication_dois TEXT[], -- array of DOI strings
    presentation_files TEXT[], -- array of file paths
    
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_evaluation_score CHECK (evaluation_score >= 1 AND evaluation_score <= 5)
);

-- Migration tracking table
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    checksum TEXT,
    migration_file VARCHAR(255)
);

-- Insert initial migration record
INSERT INTO schema_migrations (version, description, checksum, migration_file) VALUES 
(1, 'Initial UPGRADE project schema with weather integration', 'upgrade_initial_v1', '001_initial_upgrade_schema.sql');

-- =========================
-- Triggers for updated_at timestamps
-- =========================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers to relevant tables
CREATE TRIGGER update_institutions_updated_at BEFORE UPDATE ON institutions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_researchers_updated_at BEFORE UPDATE ON researchers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_locations_updated_at BEFORE UPDATE ON locations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sampling_campaigns_updated_at BEFORE UPDATE ON sampling_campaigns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_samples_updated_at BEFORE UPDATE ON samples
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_biobank_updated_at BEFORE UPDATE ON biobank
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_collaboration_activities_updated_at BEFORE UPDATE ON collaboration_activities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =========================
-- Basic Indexes for Performance
-- =========================

-- Locations indexes
CREATE INDEX idx_locations_coordinates ON locations (latitude, longitude);
CREATE INDEX idx_locations_country_region ON locations (country, region);
CREATE INDEX idx_locations_active ON locations (is_active) WHERE is_active = true;
CREATE INDEX idx_locations_campus_area ON locations (campus_area) WHERE campus_area IS NOT NULL;
CREATE INDEX idx_locations_traffic_density ON locations (traffic_density);

-- Weather measurements indexes
CREATE INDEX idx_weather_location_datetime ON weather_measurements (location_id, measurement_datetime DESC);
CREATE INDEX idx_weather_datetime ON weather_measurements (measurement_datetime DESC);
CREATE INDEX idx_weather_source ON weather_measurements (source);
CREATE INDEX idx_weather_quality ON weather_measurements (data_quality);

-- Samples indexes
CREATE INDEX idx_samples_code ON samples (sample_code);
CREATE INDEX idx_samples_location_date ON samples (location_id, collection_date DESC);
CREATE INDEX idx_samples_campaign ON samples (campaign_id);
CREATE INDEX idx_samples_status ON samples (status);
CREATE INDEX idx_samples_collector ON samples (collector_id);

-- Sample metadata indexes
CREATE INDEX idx_sample_metadata_sample ON sample_metadata (sample_id);
CREATE INDEX idx_sample_metadata_surface_type ON sample_metadata (surface_type);
CREATE INDEX idx_sample_metadata_season ON sample_metadata (season);

-- Collaboration activities indexes
CREATE INDEX idx_collaboration_type ON collaboration_activities (activity_type);
CREATE INDEX idx_collaboration_status ON collaboration_activities (status);
CREATE INDEX idx_collaboration_dates ON collaboration_activities (start_date, end_date);

-- =========================
-- Comments for Documentation
-- =========================

COMMENT ON TABLE institutions IS 'Research institutions participating in UPGRADE project';
COMMENT ON TABLE researchers IS 'Researchers involved in the UPGRADE project';
COMMENT ON TABLE locations IS 'Sampling locations with university campus-specific details';
COMMENT ON TABLE weather_measurements IS 'Weather data from Open-Meteo API and other sources';
COMMENT ON TABLE sampling_campaigns IS 'Organized sampling campaigns across Romanian and Moldovan sites';
COMMENT ON TABLE samples IS 'Individual samples collected during campaigns';
COMMENT ON TABLE sample_metadata IS 'Detailed environmental and contextual metadata for samples';
COMMENT ON TABLE collaboration_activities IS 'Cross-border collaboration tracking between Romanian and Moldovan teams';
COMMENT ON TABLE biobank IS 'Sample storage and biobanking information';

-- Grant permissions for upgrade_user
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'upgrade_user') THEN
        GRANT USAGE ON SCHEMA public TO upgrade_user;
        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO upgrade_user;
        GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO upgrade_user;
        GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO upgrade_user;
    END IF;
END
$$;