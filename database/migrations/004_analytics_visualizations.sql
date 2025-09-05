-- Migration 004: Analytics, Visualization & Advanced Features
-- UPGRADE Project - Metabase Integration, REST API, Views, and Performance Optimization
-- Version: 1.0.0

-- =========================
-- RISK MANAGEMENT & ALERTS
-- =========================

CREATE TABLE IF NOT EXISTS risk_logs (
    risk_id SERIAL PRIMARY KEY,
    sample_id INT REFERENCES samples(sample_id),
    detection_type VARCHAR(100), -- new_arg, outbreak_signal, contamination, quality_issue
    
    -- Risk details
    risk_level VARCHAR(50) NOT NULL, -- low, medium, high, critical
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    
    -- Risk assessment
    probability DECIMAL(5,2), -- 0-100% probability
    impact_score INTEGER, -- 1-10 scale
    urgency VARCHAR(50), -- immediate, high, medium, low
    
    -- Mitigation
    mitigation_plan TEXT,
    mitigation_status VARCHAR(50), -- planned, in_progress, completed
    responsible_researcher_id INT REFERENCES researchers(researcher_id),
    
    -- Associated findings
    related_resistance_genes INTEGER[], -- array of rg_ids
    related_organisms INTEGER[], -- array of detection_ids
    related_samples INTEGER[], -- array of sample_ids
    
    -- Follow-up
    requires_notification BOOLEAN DEFAULT false,
    notification_sent BOOLEAN DEFAULT false,
    follow_up_required BOOLEAN DEFAULT false,
    follow_up_deadline DATE,
    
    -- Status tracking
    status VARCHAR(50) DEFAULT 'open', -- open, investigating, resolved, closed
    resolution_notes TEXT,
    resolved_at TIMESTAMP,
    resolved_by INT REFERENCES researchers(researcher_id),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alert_notifications (
    notification_id SERIAL PRIMARY KEY,
    risk_id INT NOT NULL REFERENCES risk_logs(risk_id),
    notification_type VARCHAR(100) NOT NULL, -- 'email', 'sms', 'dashboard', 'api_webhook'
    
    -- Recipients
    recipient_user_id INT REFERENCES users(user_id),
    recipient_email VARCHAR(150),
    recipient_phone VARCHAR(20),
    
    -- Notification content
    subject VARCHAR(500),
    message TEXT,
    notification_data JSONB DEFAULT '{}',
    
    -- Delivery tracking
    sent_at TIMESTAMP WITH TIME ZONE,
    delivery_status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'sent', 'delivered', 'failed'
    delivery_attempts INT DEFAULT 0,
    last_attempt_at TIMESTAMP WITH TIME ZONE,
    delivery_error TEXT,
    
    -- Response tracking
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    acknowledged_by INT REFERENCES users(user_id),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_delivery_status CHECK (delivery_status IN ('pending', 'sent', 'delivered', 'failed'))
);

-- =========================
-- ANALYTICS & VISUALIZATION INFRASTRUCTURE
-- =========================

CREATE TABLE IF NOT EXISTS metabase_datasets (
    dataset_id SERIAL PRIMARY KEY,
    dataset_name VARCHAR(200) NOT NULL,
    dataset_type VARCHAR(100) NOT NULL, -- 'pathogen_maps', 'amr_analysis', 'weather_correlation', 'real_time_monitoring'
    description TEXT,
    
    -- Metabase integration
    metabase_table_id INT, -- Metabase internal table ID
    metabase_database_id INT, -- Metabase database connection ID
    
    -- Data sources and dependencies
    source_tables TEXT[] NOT NULL, -- Array of source table names
    dependent_views TEXT[], -- Array of dependent view names
    data_sources TEXT[] NOT NULL, -- ['weather_facts', 'amr_facts', 'organism_facts']
    
    -- Refresh configuration
    refresh_frequency VARCHAR(50) NOT NULL, -- 'real_time', 'hourly', 'daily', 'weekly', 'manual'
    auto_refresh_enabled BOOLEAN DEFAULT true,
    last_refresh_time TIMESTAMP WITH TIME ZONE,
    next_refresh_time TIMESTAMP WITH TIME ZONE,
    
    -- Data quality and monitoring
    row_count BIGINT DEFAULT 0,
    data_freshness_hours INT, -- How fresh the data should be
    quality_threshold DECIMAL(3,2) DEFAULT 0.95, -- Minimum quality score (0-1)
    
    -- Access control
    is_public BOOLEAN DEFAULT false,
    allowed_user_types TEXT[], -- Array of user types that can access
    created_by INT REFERENCES users(user_id),
    
    -- Metadata
    tags TEXT[], -- Array of tags for categorization
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_refresh_frequency CHECK (refresh_frequency IN ('real_time', 'hourly', 'daily', 'weekly', 'manual'))
);

CREATE TABLE IF NOT EXISTS dashboard_feeds (
    feed_id SERIAL PRIMARY KEY,
    dataset_id INT NOT NULL REFERENCES metabase_datasets(dataset_id) ON DELETE CASCADE,
    
    -- Feed configuration
    feed_name VARCHAR(200) NOT NULL,
    feed_type VARCHAR(100) NOT NULL, -- 'chart_data', 'map_data', 'alert_feed', 'summary_stats'
    target_dashboard VARCHAR(200), -- Dashboard name/ID in Metabase
    target_chart VARCHAR(200), -- Specific chart/visualization
    
    -- Data transformation
    query_template TEXT, -- SQL template for data extraction
    data_transformation JSONB DEFAULT '{}', -- Transformation rules
    aggregation_rules JSONB DEFAULT '{}', -- How to aggregate data
    
    -- Update configuration
    update_trigger VARCHAR(100) DEFAULT 'scheduled', -- 'scheduled', 'event_driven', 'manual'
    update_interval_minutes INT DEFAULT 60,
    last_update TIMESTAMP WITH TIME ZONE,
    next_update TIMESTAMP WITH TIME ZONE,
    
    -- Status and performance
    refresh_status VARCHAR(50) DEFAULT 'active', -- 'active', 'paused', 'error', 'disabled'
    last_error_message TEXT,
    last_error_time TIMESTAMP WITH TIME ZONE,
    average_refresh_time_ms INT,
    
    -- Performance metrics
    performance_metrics JSONB DEFAULT '{}', -- Query time, row count, etc.
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_feed_type CHECK (feed_type IN ('chart_data', 'map_data', 'alert_feed', 'summary_stats')),
    CONSTRAINT valid_refresh_status CHECK (refresh_status IN ('active', 'paused', 'error', 'disabled'))
);

-- =========================
-- REST API MANAGEMENT
-- =========================

CREATE TABLE IF NOT EXISTS api_endpoints (
    endpoint_id SERIAL PRIMARY KEY,
    endpoint_path VARCHAR(500) NOT NULL UNIQUE, -- '/api/v1/samples', '/api/v1/weather/{location_id}'
    http_method VARCHAR(10) NOT NULL, -- 'GET', 'POST', 'PUT', 'DELETE'
    endpoint_name VARCHAR(200),
    description TEXT,
    
    -- Data sources
    primary_table VARCHAR(100), -- Main table this endpoint queries
    data_sources TEXT[], -- Additional tables/views used
    
    -- Access control
    authentication_required BOOLEAN DEFAULT true,
    required_permissions TEXT[], -- Array of required permissions
    rate_limit_per_hour INT DEFAULT 1000,
    rate_limit_per_minute INT DEFAULT 100,
    
    -- Response configuration
    default_limit INT DEFAULT 100,
    max_limit INT DEFAULT 1000,
    supported_formats TEXT[] DEFAULT ARRAY['json'], -- ['json', 'csv', 'xml']
    
    -- Caching
    cache_enabled BOOLEAN DEFAULT true,
    cache_ttl_seconds INT DEFAULT 300, -- 5 minutes default
    
    -- API versioning
    api_version VARCHAR(10) DEFAULT 'v1',
    is_deprecated BOOLEAN DEFAULT false,
    deprecation_date DATE,
    replacement_endpoint VARCHAR(500),
    
    -- Documentation
    request_schema JSONB, -- JSON schema for request validation
    response_schema JSONB, -- JSON schema for response format
    example_request JSONB,
    example_response JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_http_method CHECK (http_method IN ('GET', 'POST', 'PUT', 'DELETE', 'PATCH'))
);

CREATE TABLE IF NOT EXISTS api_requests (
    request_id SERIAL PRIMARY KEY,
    endpoint_id INT NOT NULL REFERENCES api_endpoints(endpoint_id),
    user_id INT REFERENCES users(user_id),
    
    -- Request details
    request_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ip_address INET,
    user_agent VARCHAR(500),
    
    -- Request data
    query_parameters JSONB DEFAULT '{}',
    request_body JSONB,
    request_headers JSONB DEFAULT '{}',
    
    -- Response data
    status_code INT NOT NULL,
    response_time_ms INT NOT NULL,
    request_size_bytes INT,
    response_size_bytes INT,
    
    -- Results
    rows_returned INT,
    cache_hit BOOLEAN DEFAULT false,
    
    -- Error tracking
    error_message TEXT,
    error_code VARCHAR(50),
    
    -- Rate limiting
    rate_limit_remaining INT,
    
    CONSTRAINT valid_status_code CHECK (status_code >= 100 AND status_code < 600)
);

-- =========================
-- MATERIALIZED VIEWS FOR ANALYTICS
-- =========================

-- Latest weather conditions with quality metrics
CREATE MATERIALIZED VIEW mv_latest_weather_conditions AS
SELECT DISTINCT ON (l.location_id)
    l.location_id,
    l.location_name,
    l.country,
    l.region,
    l.campus_area,
    l.latitude,
    l.longitude,
    wm.weather_id,
    wm.measurement_datetime,
    wm.temperature,
    wm.humidity,
    wm.rainfall,
    wm.windspeed,
    wm.pressure_msl,
    wm.weather_code,
    wm.quality_score,
    wm.data_quality,
    -- Time since last measurement
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - wm.measurement_datetime))/3600 as hours_since_measurement,
    -- Weather categorization
    CASE 
        WHEN wm.rainfall > 10 THEN 'heavy_rain'
        WHEN wm.rainfall > 2 THEN 'rain'
        WHEN wm.windspeed > 15 THEN 'windy'
        WHEN wm.temperature > 30 THEN 'hot'
        WHEN wm.temperature < 0 THEN 'freezing'
        ELSE 'normal'
    END as weather_category
FROM locations l
LEFT JOIN weather_measurements wm ON l.location_id = wm.location_id
WHERE l.is_active = true
ORDER BY l.location_id, wm.measurement_datetime DESC NULLS LAST;

CREATE UNIQUE INDEX idx_mv_latest_weather_location ON mv_latest_weather_conditions (location_id);

-- AMR detection summary with temporal trends
CREATE MATERIALIZED VIEW mv_amr_detection_summary AS
SELECT 
    l.location_id,
    l.location_name,
    l.country,
    l.region,
    l.campus_area,
    
    -- Sample counts
    COUNT(DISTINCT s.sample_id) as total_samples,
    COUNT(DISTINCT CASE WHEN s.collection_date >= CURRENT_DATE - INTERVAL '30 days' THEN s.sample_id END) as samples_last_30_days,
    
    -- AMR gene detections
    COUNT(DISTINCT rg.rg_id) as total_amr_genes,
    COUNT(DISTINCT rg.gene_name) as unique_amr_genes,
    COUNT(DISTINCT CASE WHEN rg.created_at >= CURRENT_DATE - INTERVAL '30 days' THEN rg.rg_id END) as amr_genes_last_30_days,
    
    -- High-confidence detections
    COUNT(DISTINCT CASE WHEN rg.confidence_level = 'high' THEN rg.rg_id END) as high_confidence_amr,
    COUNT(DISTINCT CASE WHEN rg.coverage >= 90 AND rg.identity >= 95 THEN rg.rg_id END) as high_quality_amr,
    
    -- Most recent detection
    MAX(rg.created_at) as last_amr_detection,
    
    -- Risk assessment
    COUNT(DISTINCT CASE WHEN rl.risk_level IN ('high', 'critical') THEN rl.risk_id END) as high_risk_alerts,
    COUNT(DISTINCT CASE WHEN rl.status = 'open' THEN rl.risk_id END) as open_risk_alerts,
    
    -- Organism diversity
    COUNT(DISTINCT det_org.organism_name) as unique_organisms_detected,
    
    -- Data quality metrics
    AVG(s.quality_score) as avg_sample_quality,
    COUNT(DISTINCT CASE WHEN qc.is_passed = true THEN qc.qc_id END)::DECIMAL / NULLIF(COUNT(DISTINCT qc.qc_id), 0) as qc_pass_rate

FROM locations l
LEFT JOIN samples s ON l.location_id = s.location_id
LEFT JOIN resistance_genes rg ON s.sample_id = rg.sample_id
LEFT JOIN risk_logs rl ON s.sample_id = rl.sample_id
LEFT JOIN detected_organisms det_org ON s.sample_id = det_org.sample_id
LEFT JOIN quality_control_results qc ON s.sample_id = qc.sample_id
WHERE l.is_active = true
GROUP BY l.location_id, l.location_name, l.country, l.region, l.campus_area;

CREATE UNIQUE INDEX idx_mv_amr_summary_location ON mv_amr_detection_summary (location_id);

-- Weather-pathogen correlation analysis
CREATE MATERIALIZED VIEW mv_weather_pathogen_correlation AS
SELECT 
    l.location_id,
    l.location_name,
    l.country,
    DATE_TRUNC('week', s.collection_date) as collection_week,
    
    -- Weather conditions during sampling
    AVG(wm.temperature) as avg_temperature,
    AVG(wm.humidity) as avg_humidity,
    SUM(wm.rainfall) as total_rainfall,
    AVG(wm.pressure_msl) as avg_pressure,
    
    -- Weather categories
    COUNT(CASE WHEN wm.temperature > 25 THEN 1 END) as hot_days,
    COUNT(CASE WHEN wm.humidity > 80 THEN 1 END) as humid_days,
    COUNT(CASE WHEN wm.rainfall > 0 THEN 1 END) as rainy_days,
    
    -- Sample and detection counts
    COUNT(DISTINCT s.sample_id) as samples_collected,
    COUNT(DISTINCT rg.rg_id) as amr_genes_detected,
    COUNT(DISTINCT det_org.organism_name) as unique_organisms,
    
    -- Detection rates
    COUNT(DISTINCT rg.rg_id)::DECIMAL / NULLIF(COUNT(DISTINCT s.sample_id), 0) as amr_detection_rate,
    COUNT(DISTINCT det_org.detection_id)::DECIMAL / NULLIF(COUNT(DISTINCT s.sample_id), 0) as organism_detection_rate,
    
    -- Quality metrics
    AVG(CASE WHEN rg.rg_id IS NOT NULL THEN rg.quality_score END) as avg_amr_quality,
    AVG(wm.quality_score) as avg_weather_quality

FROM locations l
JOIN samples s ON l.location_id = s.location_id
LEFT JOIN sample_metadata sm ON s.sample_id = sm.sample_id
LEFT JOIN weather_measurements wm ON sm.weather_id = wm.weather_id
LEFT JOIN resistance_genes rg ON s.sample_id = rg.sample_id
LEFT JOIN detected_organisms det_org ON s.sample_id = det_org.sample_id
WHERE l.is_active = true 
  AND s.collection_date >= CURRENT_DATE - INTERVAL '1 year'
GROUP BY l.location_id, l.location_name, l.country, DATE_TRUNC('week', s.collection_date)
HAVING COUNT(DISTINCT s.sample_id) > 0;

CREATE INDEX idx_mv_weather_pathogen_location_week ON mv_weather_pathogen_correlation (location_id, collection_week DESC);

-- Real-time processing status dashboard
CREATE MATERIALIZED VIEW mv_processing_status_dashboard AS
SELECT 
    -- Processing queue summary
    COUNT(CASE WHEN pq.queue_status = 'queued' THEN 1 END) as queued_jobs,
    COUNT(CASE WHEN pq.queue_status = 'running' THEN 1 END) as running_jobs,
    COUNT(CASE WHEN pq.queue_status = 'completed' THEN 1 END) as completed_jobs_today,
    COUNT(CASE WHEN pq.queue_status = 'failed' THEN 1 END) as failed_jobs_today,
    
    -- Worker node status
    COUNT(DISTINCT CASE WHEN wn.status = 'active' THEN wn.node_id END) as active_nodes,
    COUNT(DISTINCT CASE WHEN wn.status = 'offline' THEN wn.node_id END) as offline_nodes,
    SUM(CASE WHEN wn.status = 'active' THEN wn.current_jobs ELSE 0 END) as total_active_jobs,
    SUM(CASE WHEN wn.status = 'active' THEN wn.max_jobs ELSE 0 END) as total_capacity,
    
    -- Resource utilization
    AVG(CASE WHEN wn.status = 'active' THEN wn.cpu_utilization END) as avg_cpu_utilization,
    AVG(CASE WHEN wn.status = 'active' THEN wn.memory_utilization END) as avg_memory_utilization,
    
    -- Recent performance metrics
    AVG(CASE WHEN pq.completed_at >= CURRENT_DATE THEN pq.actual_runtime_minutes END) as avg_runtime_today,
    COUNT(CASE WHEN ne.complete_time >= CURRENT_TIMESTAMP - INTERVAL '1 hour' THEN 1 END) as workflows_completed_last_hour,
    COUNT(CASE WHEN ne.status = 'failed' AND ne.complete_time >= CURRENT_DATE THEN 1 END) as failed_workflows_today,
    
    -- Data freshness
    MAX(wm.measurement_datetime) as latest_weather_data,
    MAX(s.created_at) as latest_sample,
    MAX(rg.created_at) as latest_amr_detection,
    
    -- System health indicators
    COUNT(CASE WHEN rl.risk_level = 'critical' AND rl.status = 'open' THEN 1 END) as critical_alerts,
    COUNT(CASE WHEN ar.status_code >= 500 AND ar.request_timestamp >= CURRENT_TIMESTAMP - INTERVAL '1 hour' THEN 1 END) as api_errors_last_hour

FROM processing_queue pq
CROSS JOIN worker_nodes wn
LEFT JOIN nextflow_executions ne ON ne.complete_time >= CURRENT_DATE
LEFT JOIN weather_measurements wm ON wm.measurement_datetime >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
LEFT JOIN samples s ON s.created_at >= CURRENT_DATE
LEFT JOIN resistance_genes rg ON rg.created_at >= CURRENT_DATE  
LEFT JOIN risk_logs rl ON rl.created_at >= CURRENT_DATE
LEFT JOIN api_requests ar ON ar.request_timestamp >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
WHERE pq.queued_at >= CURRENT_DATE;

-- =========================
-- DATA QUALITY MONITORING
-- =========================

CREATE TABLE IF NOT EXISTS data_quality_checks (
    check_id SERIAL PRIMARY KEY,
    check_name VARCHAR(200) NOT NULL,
    check_type VARCHAR(100) NOT NULL, -- 'completeness', 'accuracy', 'consistency', 'timeliness'
    target_table VARCHAR(100) NOT NULL,
    check_query TEXT NOT NULL, -- SQL query that returns quality score (0-1)
    expected_threshold DECIMAL(3,2) DEFAULT 0.95, -- Minimum acceptable quality score
    
    -- Scheduling
    check_frequency VARCHAR(50) DEFAULT 'daily', -- 'hourly', 'daily', 'weekly'
    is_active BOOLEAN DEFAULT true,
    
    -- Alerting
    alert_threshold DECIMAL(3,2) DEFAULT 0.90, -- Threshold below which to alert
    alert_enabled BOOLEAN DEFAULT true,
    notification_emails TEXT[],
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS data_quality_results (
    result_id SERIAL PRIMARY KEY,
    check_id INT NOT NULL REFERENCES data_quality_checks(check_id),
    
    -- Results
    check_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    quality_score DECIMAL(5,4) NOT NULL, -- 0.0000 to 1.0000
    records_checked BIGINT,
    records_passed BIGINT,
    records_failed BIGINT,
    
    -- Status
    check_status VARCHAR(50) NOT NULL, -- 'passed', 'warning', 'failed', 'error'
    issue_description TEXT,
    
    -- Performance
    execution_time_ms INT,
    
    -- Metadata
    metadata JSONB DEFAULT '{}'
);

-- =========================
-- PERFORMANCE INDEXES
-- =========================

-- Analytics tables
CREATE INDEX idx_metabase_datasets_type ON metabase_datasets (dataset_type);
CREATE INDEX idx_metabase_datasets_refresh ON metabase_datasets (refresh_frequency, next_refresh_time);
CREATE INDEX idx_dashboard_feeds_status ON dashboard_feeds (refresh_status, next_update);

-- API management
CREATE INDEX idx_api_endpoints_path_method ON api_endpoints (endpoint_path, http_method);
CREATE INDEX idx_api_requests_endpoint_timestamp ON api_requests (endpoint_id, request_timestamp DESC);
CREATE INDEX idx_api_requests_user_timestamp ON api_requests (user_id, request_timestamp DESC);
CREATE INDEX idx_api_requests_performance ON api_requests (response_time_ms, request_timestamp DESC);
CREATE INDEX idx_api_requests_errors ON api_requests (status_code, request_timestamp DESC) WHERE status_code >= 400;

-- Data quality
CREATE INDEX idx_data_quality_checks_active ON data_quality_checks (is_active, check_frequency);
CREATE INDEX idx_data_quality_results_check_timestamp ON data_quality_results (check_id, check_timestamp DESC);
CREATE INDEX idx_data_quality_results_status ON data_quality_results (check_status, check_timestamp DESC);

-- Materialized view refresh tracking
CREATE INDEX idx_mv_latest_weather_measurement ON mv_latest_weather_conditions (measurement_datetime DESC);
CREATE INDEX idx_mv_amr_summary_risk ON mv_amr_detection_summary (high_risk_alerts DESC, open_risk_alerts DESC);
CREATE INDEX idx_mv_weather_pathogen_week ON mv_weather_pathogen_correlation (collection_week DESC);

-- =========================
-- UPDATE MIGRATION RECORD
-- =========================

INSERT INTO schema_migrations (version, description) VALUES 
(4, 'Analytics and visualization infrastructure, API management, materialized views, and data quality monitoring');