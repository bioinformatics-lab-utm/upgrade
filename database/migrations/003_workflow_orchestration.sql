-- Migration 003: Workflow Orchestration & Storage Management
-- UPGRADE Project - Airflow, NextFlow, User Management, and MinIO Data Lake
-- Version: 1.0.0

-- =========================
-- USER MANAGEMENT SYSTEM
-- =========================

CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    user_type VARCHAR(50) NOT NULL, -- 'lab_technician', 'public_health_official', 'researcher', 'admin'
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    institution_id INT REFERENCES institutions(institution_id),
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMP WITH TIME ZONE,
    password_changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_user_type CHECK (user_type IN ('lab_technician', 'public_health_official', 'researcher', 'admin'))
);

CREATE TABLE IF NOT EXISTS user_sessions (
    session_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    ip_address INET,
    user_agent VARCHAR(500),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_active BOOLEAN DEFAULT true,
    
    CONSTRAINT valid_session_duration CHECK (expires_at > started_at)
);

CREATE TABLE IF NOT EXISTS user_permissions (
    permission_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    resource_type VARCHAR(100) NOT NULL, -- 'samples', 'weather_data', 'analysis_results', 'admin_panel'
    permission_level VARCHAR(50) NOT NULL, -- 'read', 'write', 'admin', 'owner'
    resource_id INT, -- Optional: specific resource ID for fine-grained permissions
    granted_by INT REFERENCES users(user_id),
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    
    CONSTRAINT valid_permission_level CHECK (permission_level IN ('read', 'write', 'admin', 'owner'))
);

-- =========================
-- AIRFLOW ORCHESTRATION
-- =========================

CREATE TABLE IF NOT EXISTS airflow_dags (
    dag_id VARCHAR(150) PRIMARY KEY,
    dag_name VARCHAR(255) NOT NULL,
    description TEXT,
    schedule_interval VARCHAR(100), -- '@daily', '0 */6 * * *', etc.
    start_date DATE,
    end_date DATE,
    is_active BOOLEAN DEFAULT true,
    is_paused BOOLEAN DEFAULT false,
    owner VARCHAR(100),
    tags TEXT[], -- Array of tags
    dag_file_path VARCHAR(500),
    max_active_runs INT DEFAULT 1,
    catchup BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS airflow_runs (
    run_id SERIAL PRIMARY KEY,
    dag_id VARCHAR(150) NOT NULL REFERENCES airflow_dags(dag_id) ON DELETE CASCADE,
    airflow_run_id VARCHAR(200) UNIQUE NOT NULL, -- Airflow's unique run identifier
    execution_date TIMESTAMP WITH TIME ZONE NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    state VARCHAR(50) NOT NULL, -- 'running', 'success', 'failed', 'up_for_retry', 'skipped'
    external_trigger BOOLEAN DEFAULT false,
    triggered_by VARCHAR(100), -- 'scheduler', 'manual', 'api'
    conf JSONB DEFAULT '{}', -- DAG run configuration
    data_interval_start TIMESTAMP WITH TIME ZONE,
    data_interval_end TIMESTAMP WITH TIME ZONE,
    
    -- Linked resources
    sample_ids INTEGER[], -- Array of samples processed in this run
    location_ids INTEGER[], -- Array of locations processed
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_airflow_state CHECK (state IN ('running', 'success', 'failed', 'up_for_retry', 'skipped', 'queued'))
);

CREATE TABLE IF NOT EXISTS airflow_tasks (
    task_id SERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES airflow_runs(run_id) ON DELETE CASCADE,
    task_name VARCHAR(200) NOT NULL,
    operator VARCHAR(100), -- 'BashOperator', 'PythonOperator', 'KubernetesPodOperator'
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    duration INTERVAL,
    state VARCHAR(50) NOT NULL,
    try_number INT DEFAULT 1,
    max_tries INT DEFAULT 1,
    hostname VARCHAR(255),
    unixname VARCHAR(100),
    job_id VARCHAR(100),
    pool VARCHAR(100),
    queue VARCHAR(100),
    priority_weight INT DEFAULT 1,
    log_url VARCHAR(500),
    task_instance_note TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_task_state CHECK (state IN ('running', 'success', 'failed', 'up_for_retry', 'skipped', 'upstream_failed'))
);

-- =========================
-- NEXTFLOW PIPELINE MANAGEMENT
-- =========================

CREATE TABLE IF NOT EXISTS nextflow_workflows (
    workflow_id SERIAL PRIMARY KEY,
    workflow_name VARCHAR(200) NOT NULL,
    workflow_version VARCHAR(50),
    nextflow_version VARCHAR(50),
    workflow_script_path VARCHAR(500),
    config_file_path VARCHAR(500),
    params_file_path VARCHAR(500),
    workflow_type VARCHAR(100), -- 'quality_control', 'assembly', 'annotation', 'amr_detection'
    container_registry VARCHAR(200), -- Docker/Singularity registry
    is_active BOOLEAN DEFAULT true,
    description TEXT,
    author VARCHAR(200),
    
    -- Resource requirements
    default_cpu INT DEFAULT 1,
    default_memory_gb INT DEFAULT 4,
    default_disk_gb INT DEFAULT 20,
    max_runtime_hours INT DEFAULT 24,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nextflow_executions (
    execution_id SERIAL PRIMARY KEY,
    workflow_id INT NOT NULL REFERENCES nextflow_workflows(workflow_id),
    airflow_run_id INT REFERENCES airflow_runs(run_id),
    execution_name VARCHAR(200) NOT NULL,
    nextflow_run_name VARCHAR(200), -- NextFlow's run identifier
    
    -- Execution paths
    work_directory VARCHAR(500),
    publish_directory VARCHAR(500),
    trace_file_path VARCHAR(500),
    report_file_path VARCHAR(500),
    timeline_file_path VARCHAR(500),
    dag_file_path VARCHAR(500),
    
    -- Execution status
    status VARCHAR(50) NOT NULL, -- 'submitted', 'running', 'succeeded', 'failed', 'cancelled'
    start_time TIMESTAMP WITH TIME ZONE,
    complete_time TIMESTAMP WITH TIME ZONE,
    duration INTERVAL,
    success BOOLEAN,
    exit_status INT,
    error_message TEXT,
    
    -- Resource usage summary
    total_cpu_hours DECIMAL(10,2),
    peak_memory_gb DECIMAL(8,2),
    total_disk_gb DECIMAL(10,2),
    
    -- Configuration
    params JSONB DEFAULT '{}',
    nextflow_config JSONB DEFAULT '{}',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_nextflow_status CHECK (status IN ('submitted', 'running', 'succeeded', 'failed', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS nextflow_processes (
    process_id SERIAL PRIMARY KEY,
    execution_id INT NOT NULL REFERENCES nextflow_executions(execution_id) ON DELETE CASCADE,
    process_name VARCHAR(200) NOT NULL, -- 'TRIMMOMATIC', 'FLYE_ASSEMBLY', 'KRAKEN2_CLASSIFY'
    task_id VARCHAR(200), -- NextFlow task hash/ID
    process_index INT,
    
    -- Process execution details
    status VARCHAR(50) NOT NULL,
    exit_code INT,
    start_time TIMESTAMP WITH TIME ZONE,
    complete_time TIMESTAMP WITH TIME ZONE,
    duration INTERVAL,
    
    -- Resource usage
    cpu_usage DECIMAL(8,2), -- CPU hours
    peak_memory_mb BIGINT,
    peak_vmem_mb BIGINT,
    disk_read_mb BIGINT,
    disk_write_mb BIGINT,
    
    -- Container and execution environment
    container_image VARCHAR(300),
    container_hash VARCHAR(100),
    work_directory VARCHAR(500),
    script_file_path VARCHAR(500),
    
    -- Input/Output tracking
    input_files TEXT[], -- Array of input file paths
    output_files TEXT[], -- Array of output file paths
    
    -- Error tracking
    error_action VARCHAR(50), -- 'retry', 'ignore', 'terminate'
    attempt INT DEFAULT 1,
    max_retries INT DEFAULT 1,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_process_status CHECK (status IN ('submitted', 'running', 'completed', 'failed', 'aborted', 'cached'))
);

-- =========================
-- PROCESSING QUEUE MANAGEMENT
-- =========================

CREATE TABLE IF NOT EXISTS worker_nodes (
    node_id SERIAL PRIMARY KEY,
    node_name VARCHAR(100) UNIQUE NOT NULL,
    node_type VARCHAR(50) NOT NULL, -- 'compute', 'gpu', 'high_memory', 'storage'
    hostname VARCHAR(255),
    ip_address INET,
    
    -- Hardware specifications
    cpu_cores INT NOT NULL,
    memory_gb INT NOT NULL,
    disk_gb INT NOT NULL,
    gpu_count INT DEFAULT 0,
    gpu_type VARCHAR(100),
    
    -- Status and capacity
    status VARCHAR(50) DEFAULT 'active', -- 'active', 'maintenance', 'offline', 'retired'
    current_jobs INT DEFAULT 0,
    max_jobs INT NOT NULL,
    cpu_utilization DECIMAL(5,2) DEFAULT 0.0,
    memory_utilization DECIMAL(5,2) DEFAULT 0.0,
    disk_utilization DECIMAL(5,2) DEFAULT 0.0,
    
    -- Monitoring
    last_heartbeat TIMESTAMP WITH TIME ZONE,
    uptime_hours DECIMAL(10,2),
    
    -- Configuration
    supported_workflows TEXT[], -- Array of workflow types this node can handle
    node_labels JSONB DEFAULT '{}', -- Key-value labels for scheduling
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_node_status CHECK (status IN ('active', 'maintenance', 'offline', 'retired')),
    CONSTRAINT valid_utilization CHECK (
        cpu_utilization >= 0 AND cpu_utilization <= 100 AND
        memory_utilization >= 0 AND memory_utilization <= 100 AND
        disk_utilization >= 0 AND disk_utilization <= 100
    )
);-- Migration 003: Workflow Orchestration & Extended Pipeline Support
-- UPGRADE Project - Airflow, NextFlow, User Management, and MinIO Integration
-- Version: 1.0.0

-- =========================
-- USER MANAGEMENT SYSTEM
-- =========================

CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    user_type VARCHAR(50) NOT NULL, -- 'lab_technician', 'public_health_official', 'researcher', 'admin'
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    institution_id INT REFERENCES institutions(institution_id),
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMP WITH TIME ZONE,
    password_changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_user_type CHECK (user_type IN ('lab_technician', 'public_health_official', 'researcher', 'admin'))
);

CREATE TABLE IF NOT EXISTS user_sessions (
    session_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    ip_address INET,
    user_agent VARCHAR(500),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_active BOOLEAN DEFAULT true,
    
    CONSTRAINT valid_session_duration CHECK (expires_at > started_at)
);

CREATE TABLE IF NOT EXISTS user_permissions (
    permission_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    resource_type VARCHAR(100) NOT NULL, -- 'samples', 'weather_data', 'analysis_results', 'admin_panel'
    permission_level VARCHAR(50) NOT NULL, -- 'read', 'write', 'admin', 'owner'
    resource_id INT, -- Optional: specific resource ID for fine-grained permissions
    granted_by INT REFERENCES users(user_id),
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    
    CONSTRAINT valid_permission_level CHECK (permission_level IN ('read', 'write', 'admin', 'owner'))
);

-- =========================
-- AIRFLOW ORCHESTRATION
-- =========================

CREATE TABLE IF NOT EXISTS airflow_dags (
    dag_id VARCHAR(150) PRIMARY KEY,
    dag_name VARCHAR(255) NOT NULL,
    description TEXT,
    schedule_interval VARCHAR(100), -- '@daily', '0 */6 * * *', etc.
    start_date DATE,
    end_date DATE,
    is_active BOOLEAN DEFAULT true,
    is_paused BOOLEAN DEFAULT false,
    owner VARCHAR(100),
    tags TEXT[], -- Array of tags
    dag_file_path VARCHAR(500),
    max_active_runs INT DEFAULT 1,
    catchup BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS airflow_runs (
    run_id SERIAL PRIMARY KEY,
    dag_id VARCHAR(150) NOT NULL REFERENCES airflow_dags(dag_id) ON DELETE CASCADE,
    airflow_run_id VARCHAR(200) UNIQUE NOT NULL, -- Airflow's unique run identifier
    execution_date TIMESTAMP WITH TIME ZONE NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    state VARCHAR(50) NOT NULL, -- 'running', 'success', 'failed', 'up_for_retry', 'skipped'
    external_trigger BOOLEAN DEFAULT false,
    triggered_by VARCHAR(100), -- 'scheduler', 'manual', 'api'
    conf JSONB DEFAULT '{}', -- DAG run configuration
    data_interval_start TIMESTAMP WITH TIME ZONE,
    data_interval_end TIMESTAMP WITH TIME ZONE,
    
    -- Linked resources
    sample_ids INTEGER[], -- Array of samples processed in this run
    location_ids INTEGER[], -- Array of locations processed
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_airflow_state CHECK (state IN ('running', 'success', 'failed', 'up_for_retry', 'skipped', 'queued'))
);

CREATE TABLE IF NOT EXISTS airflow_tasks (
    task_id SERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES airflow_runs(run_id) ON DELETE CASCADE,
    task_name VARCHAR(200) NOT NULL,
    operator VARCHAR(100), -- 'BashOperator', 'PythonOperator', 'KubernetesPodOperator'
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    duration INTERVAL,
    state VARCHAR(50) NOT NULL,
    try_number INT DEFAULT 1,
    max_tries INT DEFAULT 1,
    hostname VARCHAR(255),
    unixname VARCHAR(100),
    job_id VARCHAR(100),
    pool VARCHAR(100),
    queue VARCHAR(100),
    priority_weight INT DEFAULT 1,
    log_url VARCHAR(500),
    task_instance_note TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_task_state CHECK (state IN ('running', 'success', 'failed', 'up_for_retry', 'skipped', 'upstream_failed'))
);

-- =========================
-- NEXTFLOW PIPELINE MANAGEMENT
-- =========================

CREATE TABLE IF NOT EXISTS nextflow_workflows (
    workflow_id SERIAL PRIMARY KEY,
    workflow_name VARCHAR(200) NOT NULL,
    workflow_version VARCHAR(50),
    nextflow_version VARCHAR(50),
    workflow_script_path VARCHAR(500),
    config_file_path VARCHAR(500),
    params_file_path VARCHAR(500),
    workflow_type VARCHAR(100), -- 'quality_control', 'assembly', 'annotation', 'amr_detection'
    container_registry VARCHAR(200), -- Docker/Singularity registry
    is_active BOOLEAN DEFAULT true,
    description TEXT,
    author VARCHAR(200),
    
    -- Resource requirements
    default_cpu INT DEFAULT 1,
    default_memory_gb INT DEFAULT 4,
    default_disk_gb INT DEFAULT 20,
    max_runtime_hours INT DEFAULT 24,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nextflow_executions (
    execution_id SERIAL PRIMARY KEY,
    workflow_id INT NOT NULL REFERENCES nextflow_workflows(workflow_id),
    airflow_run_id INT REFERENCES airflow_runs(run_id),
    execution_name VARCHAR(200) NOT NULL,
    nextflow_run_name VARCHAR(200), -- NextFlow's run identifier
    
    -- Execution paths
    work_directory VARCHAR(500),
    publish_directory VARCHAR(500),
    trace_file_path VARCHAR(500),
    report_file_path VARCHAR(500),
    timeline_file_path VARCHAR(500),
    dag_file_path VARCHAR(500),
    
    -- Execution status
    status VARCHAR(50) NOT NULL, -- 'submitted', 'running', 'succeeded', 'failed', 'cancelled'
    start_time TIMESTAMP WITH TIME ZONE,
    complete_time TIMESTAMP WITH TIME ZONE,
    duration INTERVAL,
    success BOOLEAN,
    exit_status INT,
    error_message TEXT,
    
    -- Resource usage summary
    total_cpu_hours DECIMAL(10,2),
    peak_memory_gb DECIMAL(8,2),
    total_disk_gb DECIMAL(10,2),
    
    -- Configuration
    params JSONB DEFAULT '{}',
    nextflow_config JSONB DEFAULT '{}',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_nextflow_status CHECK (status IN ('submitted', 'running', 'succeeded', 'failed', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS nextflow_processes (
    process_id SERIAL PRIMARY KEY,
    execution_id INT NOT NULL REFERENCES nextflow_executions(execution_id) ON DELETE CASCADE,
    process_name VARCHAR(200) NOT NULL, -- 'TRIMMOMATIC', 'FLYE_ASSEMBLY', 'KRAKEN2_CLASSIFY'
    task_id VARCHAR(200), -- NextFlow task hash/ID
    process_index INT,
    
    -- Process execution details
    status VARCHAR(50) NOT NULL,
    exit_code INT,
    start_time TIMESTAMP WITH TIME ZONE,
    complete_time TIMESTAMP WITH TIME ZONE,
    duration INTERVAL,
    
    -- Resource usage
    cpu_usage DECIMAL(8,2), -- CPU hours
    peak_memory_mb BIGINT,
    peak_vmem_mb BIGINT,
    disk_read_mb BIGINT,
    disk_write_mb BIGINT,
    
    -- Container and execution environment
    container_image VARCHAR(300),
    container_hash VARCHAR(100),
    work_directory VARCHAR(500),
    script_file_path VARCHAR(500),
    
    -- Input/Output tracking
    input_files TEXT[], -- Array of input file paths
    output_files TEXT[], -- Array of output file paths
    
    -- Error tracking
    error_action VARCHAR(50), -- 'retry', 'ignore', 'terminate'
    attempt INT DEFAULT 1,
    max_retries INT DEFAULT 1,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_process_status CHECK (status IN ('submitted', 'running', 'completed', 'failed', 'aborted', 'cached'))
);

-- =========================
-- PROCESSING QUEUE MANAGEMENT
-- =========================

CREATE TABLE IF NOT EXISTS worker_nodes (
    node_id SERIAL PRIMARY KEY,
    node_name VARCHAR(100) UNIQUE NOT NULL,
    node_type VARCHAR(50) NOT NULL, -- 'compute', 'gpu', 'high_memory', 'storage'
    hostname VARCHAR(255),
    ip_address INET,
    
    -- Hardware specifications
    cpu_cores INT NOT NULL,
    memory_gb INT NOT NULL,
    disk_gb INT NOT NULL,
    gpu_count INT DEFAULT 0,
    gpu_type VARCHAR(100),
    
    -- Status and capacity
    status VARCHAR(50) DEFAULT 'active', -- 'active', 'maintenance', 'offline', 'retired'
    current_jobs INT DEFAULT 0,
    max_jobs INT NOT NULL,
    cpu_utilization DECIMAL(5,2) DEFAULT 0.0,
    memory_utilization DECIMAL(5,2) DEFAULT 0.0,
    disk_utilization DECIMAL(5,2) DEFAULT 0.0,
    
    -- Monitoring
    last_heartbeat TIMESTAMP WITH TIME ZONE,
    uptime_hours DECIMAL(10,2),
    
    -- Configuration
    supported_workflows TEXT[], -- Array of workflow types this node can handle
    node_labels JSONB DEFAULT '{}', -- Key-value labels for scheduling
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_node_status CHECK (status IN ('active', 'maintenance', 'offline', 'retired')),
    CONSTRAINT valid_utilization CHECK (
        cpu_utilization >= 0 AND cpu_utilization <= 100 AND
        memory_utilization >= 0 AND memory_utilization <= 100 AND
        disk_utilization >= 0 AND disk_utilization <= 100
    )
);

CREATE TABLE IF NOT EXISTS processing_queue (
    queue_id SERIAL PRIMARY KEY,
    sample_id INT NOT NULL REFERENCES samples(sample_id),
    workflow_id INT REFERENCES nextflow_workflows(workflow_id),
    
    -- Queue details
    pipeline_type VARCHAR(100) NOT NULL, -- 'quality_control', 'assembly', 'annotation', 'amr_detection'
    priority INT DEFAULT 5, -- 1=highest, 10=lowest
    queue_status VARCHAR(50) DEFAULT 'queued', -- 'queued', 'assigned', 'running', 'completed', 'failed', 'cancelled'
    
    -- Resource requirements
    required_cpu INT DEFAULT 1,
    required_memory_gb INT DEFAULT 4,
    required_disk_gb INT DEFAULT 10,
    estimated_runtime_minutes INT,
    
    -- Assignment and execution
    assigned_node_id INT REFERENCES worker_nodes(node_id),
    execution_id INT REFERENCES nextflow_executions(execution_id),
    
    -- Timing
    queued_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    assigned_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    actual_runtime_minutes INT,
    
    -- Retry logic
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,
    retry_delay_minutes INT DEFAULT 15,
    
    -- Error handling
    error_message TEXT,
    error_category VARCHAR(100), -- 'resource_limit', 'data_corruption', 'pipeline_failure'
    
    -- Dependencies
    depends_on INTEGER[], -- Array of queue_ids that must complete first
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_queue_status CHECK (queue_status IN ('queued', 'assigned', 'running', 'completed', 'failed', 'cancelled')),
    CONSTRAINT valid_priority CHECK (priority >= 1 AND priority <= 10)
);

-- =========================
-- MINIO DATA LAKE MANAGEMENT
-- =========================

CREATE TABLE IF NOT EXISTS minio_buckets (
    bucket_id SERIAL PRIMARY KEY,
    bucket_name VARCHAR(100) UNIQUE NOT NULL,
    layer_type VARCHAR(20) NOT NULL, -- 'raw', 'bronze', 'silver', 'gold'
    description TEXT,
    
    -- Lifecycle management
    retention_policy VARCHAR(100), -- 'permanent', 'archive_1year', 'delete_6months'
    auto_transition_enabled BOOLEAN DEFAULT false,
    transition_days INT,
    
    -- Security and access
    encryption_enabled BOOLEAN DEFAULT true,
    public_read BOOLEAN DEFAULT false,
    versioning_enabled BOOLEAN DEFAULT true,
    
    -- Monitoring
    object_count BIGINT DEFAULT 0,
    total_size_bytes BIGINT DEFAULT 0,
    last_accessed TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_layer_type CHECK (layer_type IN ('raw', 'bronze', 'silver', 'gold'))
);

CREATE TABLE IF NOT EXISTS minio_objects (
    object_id SERIAL PRIMARY KEY,
    bucket_id INT NOT NULL REFERENCES minio_buckets(bucket_id) ON DELETE CASCADE,
    object_key VARCHAR(500) NOT NULL, -- Full path within bucket
    object_name VARCHAR(255) NOT NULL, -- Just filename
    
    -- Object metadata
    object_size_bytes BIGINT NOT NULL,
    content_type VARCHAR(100),
    etag VARCHAR(100), -- MinIO ETag
    md5_hash VARCHAR(32),
    sha256_hash VARCHAR(64),
    
    -- Timestamps
    last_modified TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Storage details
    storage_class VARCHAR(50) DEFAULT 'STANDARD', -- 'STANDARD', 'REDUCED_REDUNDANCY', 'GLACIER'
    version_id VARCHAR(100),
    is_latest_version BOOLEAN DEFAULT true,
    
    -- Access tracking
    access_count INT DEFAULT 0,
    last_accessed TIMESTAMP WITH TIME ZONE,
    
    -- Relationships
    sample_id INT REFERENCES samples(sample_id),
    execution_id INT REFERENCES nextflow_executions(execution_id),
    process_id INT REFERENCES nextflow_processes(process_id),
    
    -- Custom metadata
    metadata JSONB DEFAULT '{}',
    tags JSONB DEFAULT '{}',
    
    CONSTRAINT unique_bucket_object UNIQUE (bucket_id, object_key, version_id)
);

CREATE TABLE IF NOT EXISTS data_lineage (
    lineage_id SERIAL PRIMARY KEY,
    source_object_id INT NOT NULL REFERENCES minio_objects(object_id),
    target_object_id INT NOT NULL REFERENCES minio_objects(object_id),
    
    -- Transformation details
    transformation_type VARCHAR(100) NOT NULL, -- 'processing', 'aggregation', 'filtering', 'format_conversion'
    transformation_process VARCHAR(200), -- Name of the process that created this relationship
    process_id INT REFERENCES nextflow_processes(process_id),
    
    -- Timing
    transformation_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processing_duration INTERVAL,
    
    -- Metadata
    transformation_metadata JSONB DEFAULT '{}',
    quality_metrics JSONB DEFAULT '{}',
    
    CONSTRAINT no_self_reference CHECK (source_object_id != target_object_id)
);

CREATE TABLE IF NOT EXISTS layer_transitions (
    transition_id SERIAL PRIMARY KEY,
    sample_id INT NOT NULL REFERENCES samples(sample_id),
    source_object_id INT NOT NULL REFERENCES minio_objects(object_id),
    target_object_id INT NOT NULL REFERENCES minio_objects(object_id),
    
    -- Layer information
    source_layer VARCHAR(20) NOT NULL,
    target_layer VARCHAR(20) NOT NULL,
    transition_type VARCHAR(100) NOT NULL, -- 'validation', 'processing', 'aggregation', 'integration'
    
    -- Processing details
    processing_pipeline VARCHAR(200),
    processing_time INTERVAL,
    
    -- Quality and validation
    validation_status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'passed', 'failed', 'warning'
    quality_score DECIMAL(5,2),
    validation_rules JSONB DEFAULT '{}',
    validation_results JSONB DEFAULT '{}',
    
    -- Metadata
    transition_metadata JSONB DEFAULT '{}',
    
    -- Timing
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    
    CONSTRAINT valid_layer_transition CHECK (
        (source_layer = 'raw' AND target_layer = 'bronze') OR
        (source_layer = 'bronze' AND target_layer = 'silver') OR
        (source_layer = 'silver' AND target_layer = 'gold') OR
        (source_layer = target_layer) -- Same layer transitions for updates
    ),
    CONSTRAINT valid_validation_status CHECK (validation_status IN ('pending', 'passed', 'failed', 'warning'))
);

-- =========================
-- EXTENDED PIPELINE RESULTS
-- =========================

-- Update existing pipeline_runs to link with NextFlow
ALTER TABLE pipeline_runs ADD COLUMN nextflow_execution_id INT REFERENCES nextflow_executions(execution_id);
ALTER TABLE pipeline_runs ADD COLUMN nextflow_process_id INT REFERENCES nextflow_processes(process_id);

-- Link existing results tables to NextFlow processes
ALTER TABLE quality_control_results ADD COLUMN nextflow_process_id INT REFERENCES nextflow_processes(process_id);
ALTER TABLE detected_organisms ADD COLUMN nextflow_process_id INT REFERENCES nextflow_processes(process_id);
ALTER TABLE resistance_genes ADD COLUMN nextflow_process_id INT REFERENCES nextflow_processes(process_id);
ALTER TABLE virulence_factors ADD COLUMN nextflow_process_id INT REFERENCES nextflow_processes(process_id);

-- =========================
-- UPDATE MIGRATION RECORD
-- =========================

INSERT INTO schema_migrations (version, description) VALUES 
(3, 'Workflow orchestration, user management, and MinIO data lake integration');

-- =========================
-- INDEXES FOR PERFORMANCE
-- =========================

-- User management indexes
CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_username ON users (username);
CREATE INDEX idx_users_type_active ON users (user_type, is_active) WHERE is_active = true;
CREATE INDEX idx_user_sessions_token ON user_sessions (session_token);
CREATE INDEX idx_user_sessions_active ON user_sessions (user_id, is_active) WHERE is_active = true;
CREATE INDEX idx_user_permissions_user_resource ON user_permissions (user_id, resource_type);

-- Airflow indexes
CREATE INDEX idx_airflow_runs_dag_execution ON airflow_runs (dag_id, execution_date DESC);
CREATE INDEX idx_airflow_runs_state ON airflow_runs (state, start_date DESC);
CREATE INDEX idx_airflow_tasks_run_state ON airflow_tasks (run_id, state);

-- NextFlow indexes
CREATE INDEX idx_nextflow_executions_workflow ON nextflow_executions (workflow_id, start_time DESC);
CREATE INDEX idx_nextflow_executions_status ON nextflow_executions (status, start_time DESC);
CREATE INDEX idx_nextflow_processes_execution ON nextflow_processes (execution_id, process_name);
CREATE INDEX idx_nextflow_processes_status ON nextflow_processes (status, start_time DESC);

-- Processing queue indexes
CREATE INDEX idx_processing_queue_status_priority ON processing_queue (queue_status, priority, queued_at);
CREATE INDEX idx_processing_queue_sample ON processing_queue (sample_id, pipeline_type);
CREATE INDEX idx_processing_queue_node ON processing_queue (assigned_node_id, queue_status);
CREATE INDEX idx_worker_nodes_status ON worker_nodes (status, current_jobs);

-- MinIO indexes
CREATE INDEX idx_minio_objects_bucket_key ON minio_objects (bucket_id, object_key);
CREATE INDEX idx_minio_objects_sample ON minio_objects (sample_id, created_at DESC);
CREATE INDEX idx_minio_objects_execution ON minio_objects (execution_id);
CREATE INDEX idx_data_lineage_source ON data_lineage (source_object_id);
CREATE INDEX idx_data_lineage_target ON data_lineage (target_object_id);
CREATE INDEX idx_layer_transitions_sample ON layer_transitions (sample_id, source_layer, target_layer);

-- =========================
-- TRIGGERS FOR AUTOMATION
-- =========================

-- Update worker node statistics
CREATE OR REPLACE FUNCTION update_worker_node_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
        UPDATE worker_nodes 
        SET current_jobs = (
            SELECT COUNT(*) 
            FROM processing_queue 
            WHERE assigned_node_id = NEW.assigned_node_id 
            AND queue_status IN ('assigned', 'running')
        ),
        updated_at = CURRENT_TIMESTAMP
        WHERE node_id = NEW.assigned_node_id;
    END IF;
    
    IF TG_OP = 'DELETE' OR TG_OP = 'UPDATE' THEN
        UPDATE worker_nodes 
        SET current_jobs = (
            SELECT COUNT(*) 
            FROM processing_queue 
            WHERE assigned_node_id = OLD.assigned_node_id 
            AND queue_status IN ('assigned', 'running')
        ),
        updated_at = CURRENT_TIMESTAMP
        WHERE node_id = OLD.assigned_node_id;
    END IF;
    
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_worker_stats_trigger
    AFTER INSERT OR UPDATE OR DELETE ON processing_queue
    FOR EACH ROW EXECUTE FUNCTION update_worker_node_stats();

-- Update bucket statistics
CREATE OR REPLACE FUNCTION update_bucket_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE minio_buckets 
        SET object_count = object_count + 1,
            total_size_bytes = total_size_bytes + NEW.object_size_bytes,
            updated_at = CURRENT_TIMESTAMP
        WHERE bucket_id = NEW.bucket_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE minio_buckets 
        SET object_count = object_count - 1,
            total_size_bytes = total_size_bytes - OLD.object_size_bytes,
            updated_at = CURRENT_TIMESTAMP
        WHERE bucket_id = OLD.bucket_id;
    ELSIF TG_OP = 'UPDATE' THEN
        UPDATE minio_buckets 
        SET total_size_bytes = total_size_bytes - OLD.object_size_bytes + NEW.object_size_bytes,
            updated_at = CURRENT_TIMESTAMP
        WHERE bucket_id = NEW.bucket_id;
    END IF;
    
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_bucket_stats_trigger
    AFTER INSERT OR UPDATE OR DELETE ON minio_objects
    FOR EACH ROW EXECUTE FUNCTION update_bucket_stats();

-- =========================
-- COMMENTS FOR DOCUMENTATION
-- =========================

COMMENT ON TABLE users IS 'System users: lab technicians, public health officials, researchers';
COMMENT ON TABLE airflow_dags IS 'Airflow DAG definitions for workflow orchestration';
COMMENT ON TABLE nextflow_workflows IS 'NextFlow workflow definitions for bioinformatics pipelines';
COMMENT ON TABLE nextflow_processes IS 'Individual NextFlow process executions with resource tracking';
COMMENT ON TABLE processing_queue IS 'Job queue for managing pipeline execution across worker nodes';
COMMENT ON TABLE worker_nodes IS 'Compute nodes available for processing jobs';
COMMENT ON TABLE minio_buckets IS 'MinIO buckets organized by data lake layers (raw/bronze/silver/gold)';
COMMENT ON TABLE data_lineage IS 'Tracks data transformation lineage across MinIO objects';
COMMENT ON TABLE layer_transitions IS 'Manages transitions between data lake layers';