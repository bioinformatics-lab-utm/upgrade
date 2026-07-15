-- ============================================================
-- UPGRADE Platform — Complete Database Schema
-- Generated: 2026-03-17
-- Tables: 16 (active only, all legacy/unused tables removed)
-- ============================================================

--
-- PostgreSQL database dump
--

-- Dumped from database version 15.4 (Debian 15.4-1.pgdg110+1)
-- Dumped by pg_dump version 15.4 (Debian 15.4-1.pgdg110+1)

--
-- Name: btree_gin; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gin WITH SCHEMA public;


--
-- Name: EXTENSION btree_gin; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION btree_gin IS 'support for indexing common datatypes in GIN';


--
-- Name: pg_stat_statements; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;


--
-- Name: EXTENSION pg_stat_statements; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_stat_statements IS 'track planning and execution statistics of all SQL statements executed';


--
-- Name: postgis; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;


--
-- Name: EXTENSION postgis; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION postgis IS 'PostGIS geometry and geography spatial types and functions';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: data_quality; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.data_quality AS ENUM (
    'excellent',
    'good',
    'fair',
    'poor'
);


--
-- Name: sample_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.sample_status AS ENUM (
    'collected',
    'processing',
    'sequenced',
    'analyzed',
    'archived'
);


--
-- Name: weather_source; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.weather_source AS ENUM (
    'open_meteo',
    'manual',
    'sensor',
    'station'
);


--
-- Name: update_artifacts_timestamp(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_artifacts_timestamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: update_bucket_stats(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_bucket_stats() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
$$;


--
-- Name: update_pipeline_runs_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_pipeline_runs_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: update_worker_node_stats(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_worker_node_stats() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
$$;


--
-- Name: assemblies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assemblies (
    assembly_id integer NOT NULL,
    sample_id integer,
    pipeline_run_id integer,
    assembler character varying(100),
    assembler_version character varying(50),
    assembly_type character varying(50),
    total_contigs integer,
    total_length bigint,
    n50_contig integer,
    n90_contig integer,
    longest_contig integer,
    gc_content numeric(5,2),
    assembly_score numeric(5,2),
    completeness numeric(5,2),
    contamination numeric(5,2),
    assembly_fasta_path character varying(255),
    assembly_graph_path character varying(255),
    assembly_info_path character varying(255),
    quality_grade character varying(20),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE assemblies; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.assemblies IS 'Genome/metagenome assembly results and statistics';


--
-- Name: assemblies_assembly_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.assemblies_assembly_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: assemblies_assembly_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.assemblies_assembly_id_seq OWNED BY public.assemblies.assembly_id;


--
-- Name: data_lineage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_lineage (
    lineage_id integer NOT NULL,
    source_object_id integer NOT NULL,
    target_object_id integer NOT NULL,
    transformation_type character varying(100) NOT NULL,
    transformation_process character varying(200),
    process_id integer,
    transformation_time timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    processing_duration interval,
    transformation_metadata jsonb DEFAULT '{}'::jsonb,
    quality_metrics jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT no_self_reference CHECK ((source_object_id <> target_object_id))
);


--
-- Name: TABLE data_lineage; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.data_lineage IS 'Tracks data transformation lineage across MinIO objects';


--
-- Name: data_lineage_lineage_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.data_lineage_lineage_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: data_lineage_lineage_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.data_lineage_lineage_id_seq OWNED BY public.data_lineage.lineage_id;


--
-- Name: detected_organisms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.detected_organisms (
    detection_id integer NOT NULL,
    sample_id integer,
    pipeline_run_id integer,
    organism_name character varying(200) NOT NULL,
    scientific_name character varying(200),
    taxonomy_id character varying(50),
    taxonomy_rank character varying(50),
    classification_tool character varying(100),
    read_count integer,
    abundance numeric(10,6),
    abundance_rpm numeric(10,2),
    confidence_score numeric(5,2),
    coverage numeric(10,2),
    identity numeric(5,2),
    alignment_length integer,
    unique_reads integer,
    shared_reads integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    nextflow_process_id integer
);


--
-- Name: TABLE detected_organisms; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.detected_organisms IS 'Organisms detected through metagenomic analysis';


--
-- Name: detected_organisms_detection_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.detected_organisms_detection_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: detected_organisms_detection_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.detected_organisms_detection_id_seq OWNED BY public.detected_organisms.detection_id;


--
-- Name: locations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.locations (
    location_id integer NOT NULL,
    location_name character varying(255) NOT NULL,
    country character varying(100) NOT NULL,
    region character varying(100),
    city character varying(100),
    latitude numeric(10,8),
    longitude numeric(11,8),
    elevation integer,
    timezone character varying(50) DEFAULT 'UTC'::character varying,
    campus_area character varying(100),
    building_name character varying(150),
    floor_level integer,
    room_number character varying(50),
    traffic_density character varying(50),
    surface_material character varying(100),
    cleaning_frequency character varying(50),
    access_type character varying(50),
    indoor_outdoor character varying(20) DEFAULT 'indoor'::character varying,
    ventilation_type character varying(50),
    lighting_type character varying(50),
    occupancy_pattern character varying(100),
    is_active boolean DEFAULT true,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_indoor_outdoor CHECK (((indoor_outdoor)::text = ANY ((ARRAY['indoor'::character varying, 'outdoor'::character varying, 'semi_outdoor'::character varying])::text[]))),
    CONSTRAINT valid_latitude CHECK (((latitude >= ('-90'::integer)::numeric) AND (latitude <= (90)::numeric))),
    CONSTRAINT valid_longitude CHECK (((longitude >= ('-180'::integer)::numeric) AND (longitude <= (180)::numeric))),
    CONSTRAINT valid_traffic_density CHECK (((traffic_density)::text = ANY ((ARRAY['low'::character varying, 'medium'::character varying, 'high'::character varying, 'very_high'::character varying])::text[])))
);


--
-- Name: TABLE locations; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.locations IS 'Sampling locations with university campus-specific details';


--
-- Name: locations_location_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.locations_location_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: locations_location_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.locations_location_id_seq OWNED BY public.locations.location_id;


--
-- Name: minio_buckets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.minio_buckets (
    bucket_id integer NOT NULL,
    bucket_name character varying(100) NOT NULL,
    layer_type character varying(20) NOT NULL,
    description text,
    retention_policy character varying(100),
    auto_transition_enabled boolean DEFAULT false,
    transition_days integer,
    encryption_enabled boolean DEFAULT true,
    public_read boolean DEFAULT false,
    versioning_enabled boolean DEFAULT true,
    object_count bigint DEFAULT 0,
    total_size_bytes bigint DEFAULT 0,
    last_accessed timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_layer_type CHECK (((layer_type)::text = ANY ((ARRAY['raw'::character varying, 'bronze'::character varying, 'silver'::character varying, 'gold'::character varying])::text[])))
);


--
-- Name: TABLE minio_buckets; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.minio_buckets IS 'MinIO buckets organized by data lake layers (raw/bronze/silver/gold)';


--
-- Name: minio_buckets_bucket_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.minio_buckets_bucket_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: minio_buckets_bucket_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.minio_buckets_bucket_id_seq OWNED BY public.minio_buckets.bucket_id;


--
-- Name: minio_objects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.minio_objects (
    object_id integer NOT NULL,
    bucket_id integer NOT NULL,
    object_key character varying(500) NOT NULL,
    object_name character varying(255) NOT NULL,
    object_size_bytes bigint NOT NULL,
    content_type character varying(100),
    etag character varying(100),
    md5_hash character varying(32),
    sha256_hash character varying(64),
    last_modified timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    storage_class character varying(50) DEFAULT 'STANDARD'::character varying,
    version_id character varying(100),
    is_latest_version boolean DEFAULT true,
    access_count integer DEFAULT 0,
    last_accessed timestamp with time zone,
    sample_id integer,
    execution_id integer,
    metadata jsonb DEFAULT '{}'::jsonb,
    tags jsonb DEFAULT '{}'::jsonb,
    process_name character varying(50),
    tool_version character varying(20),
    layer_stage character varying(20),
    pipeline_id integer
);


--
-- Name: COLUMN minio_objects.execution_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.minio_objects.execution_id IS 'Link to specific Nextflow execution that generated this object';


--
-- Name: COLUMN minio_objects.process_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.minio_objects.process_name IS 'Nextflow process that created this object (NANOPLOT, FILTLONG, FLYE, etc.)';


--
-- Name: COLUMN minio_objects.tool_version; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.minio_objects.tool_version IS 'Tool/container version (e.g., 1.0.0, staphb/nanoplot:1.2.0)';


--
-- Name: COLUMN minio_objects.layer_stage; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.minio_objects.layer_stage IS 'Pipeline stage: qc, filtered, assembly, binning, quality, taxonomy, abundance';


--
-- Name: COLUMN minio_objects.pipeline_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.minio_objects.pipeline_id IS 'References pipeline_runs.pipeline_id - identifies which pipeline run uploaded this file';


--
-- Name: minio_objects_object_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.minio_objects_object_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: minio_objects_object_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.minio_objects_object_id_seq OWNED BY public.minio_objects.object_id;


--
-- Name: weather_measurements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.weather_measurements (
    weather_id integer NOT NULL,
    location_id integer,
    source public.weather_source DEFAULT 'open_meteo'::public.weather_source,
    measurement_datetime timestamp with time zone NOT NULL,
    temperature numeric(5,2),
    humidity numeric(5,2),
    apparent_temperature numeric(5,2),
    rainfall numeric(6,2),
    windspeed numeric(5,2),
    wind_direction integer,
    wind_gusts numeric(5,2),
    pressure_msl numeric(7,2),
    surface_pressure numeric(7,2),
    cloud_cover integer,
    visibility numeric(8,2),
    uv_index numeric(4,2),
    weather_code integer,
    is_day boolean,
    weather_api_source character varying(50),
    quality_score numeric(3,2) DEFAULT 1.00,
    data_quality public.data_quality DEFAULT 'good'::public.data_quality,
    raw_data_path character varying(512),
    api_response_time_ms integer,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_cloud_cover CHECK (((cloud_cover >= 0) AND (cloud_cover <= 100))),
    CONSTRAINT valid_humidity CHECK (((humidity >= (0)::numeric) AND (humidity <= (100)::numeric))),
    CONSTRAINT valid_quality_score CHECK (((quality_score >= (0)::numeric) AND (quality_score <= (1)::numeric))),
    CONSTRAINT valid_wind_direction CHECK (((wind_direction >= 0) AND (wind_direction < 360)))
);


--
-- Name: TABLE weather_measurements; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.weather_measurements IS 'Weather data from Open-Meteo API and other sources';


--
-- Name: mv_latest_weather_conditions; Type: MATERIALIZED VIEW; Schema: public; Owner: -
--

CREATE MATERIALIZED VIEW public.mv_latest_weather_conditions AS
 SELECT DISTINCT ON (l.location_id) l.location_id,
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
    (EXTRACT(epoch FROM (CURRENT_TIMESTAMP - wm.measurement_datetime)) / (3600)::numeric) AS hours_since_measurement,
        CASE
            WHEN (wm.rainfall > (10)::numeric) THEN 'heavy_rain'::text
            WHEN (wm.rainfall > (2)::numeric) THEN 'rain'::text
            WHEN (wm.windspeed > (15)::numeric) THEN 'windy'::text
            WHEN (wm.temperature > (30)::numeric) THEN 'hot'::text
            WHEN (wm.temperature < (0)::numeric) THEN 'freezing'::text
            ELSE 'normal'::text
        END AS weather_category
   FROM (public.locations l
     LEFT JOIN public.weather_measurements wm ON ((l.location_id = wm.location_id)))
  WHERE (l.is_active = true)
  ORDER BY l.location_id, wm.measurement_datetime DESC NULLS LAST
  WITH NO DATA;


--
-- Name: nextflow_executions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nextflow_executions (
    execution_id integer NOT NULL,
    workflow_id integer NOT NULL,
    airflow_run_id integer,
    execution_name character varying(200) NOT NULL,
    nextflow_run_name character varying(200),
    work_directory character varying(500),
    publish_directory character varying(500),
    trace_file_path character varying(500),
    report_file_path character varying(500),
    timeline_file_path character varying(500),
    dag_file_path character varying(500),
    status character varying(50) NOT NULL,
    start_time timestamp with time zone,
    complete_time timestamp with time zone,
    duration interval,
    success boolean,
    exit_status integer,
    error_message text,
    total_cpu_hours numeric(10,2),
    peak_memory_gb numeric(8,2),
    total_disk_gb numeric(10,2),
    params jsonb DEFAULT '{}'::jsonb,
    nextflow_config jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_nextflow_status CHECK (((status)::text = ANY ((ARRAY['submitted'::character varying, 'running'::character varying, 'succeeded'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: nextflow_executions_execution_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nextflow_executions_execution_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nextflow_executions_execution_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nextflow_executions_execution_id_seq OWNED BY public.nextflow_executions.execution_id;


--
-- Name: nextflow_workflows; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nextflow_workflows (
    workflow_id integer NOT NULL,
    workflow_name character varying(200) NOT NULL,
    workflow_version character varying(50),
    nextflow_version character varying(50),
    workflow_script_path character varying(500),
    config_file_path character varying(500),
    params_file_path character varying(500),
    workflow_type character varying(100),
    container_registry character varying(200),
    is_active boolean DEFAULT true,
    description text,
    author character varying(200),
    default_cpu integer DEFAULT 1,
    default_memory_gb integer DEFAULT 4,
    default_disk_gb integer DEFAULT 20,
    max_runtime_hours integer DEFAULT 24,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE nextflow_workflows; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.nextflow_workflows IS 'NextFlow workflow definitions for bioinformatics pipelines';


--
-- Name: nextflow_workflows_workflow_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nextflow_workflows_workflow_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nextflow_workflows_workflow_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nextflow_workflows_workflow_id_seq OWNED BY public.nextflow_workflows.workflow_id;


--
-- Name: pipeline_artifacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_artifacts (
    artifact_id integer NOT NULL,
    pipeline_id integer NOT NULL,
    artifact_type character varying(50) NOT NULL,
    artifact_name character varying(255) NOT NULL,
    artifact_description text,
    minio_object_id integer,
    file_path character varying(500),
    quality_tier character varying(20),
    quality_score numeric(5,2),
    metadata jsonb,
    process_name character varying(50),
    created_by character varying(100),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_artifact_type CHECK (((artifact_type)::text = ANY ((ARRAY['assembly'::character varying, 'bin'::character varying, 'qc_report'::character varying, 'filtering_log'::character varying, 'taxonomy_report'::character varying, 'abundance_report'::character varying, 'quality_report'::character varying, 'assembly_graph'::character varying, 'assembly_stats'::character varying, 'trace_file'::character varying, 'timeline_html'::character varying, 'execution_report'::character varying, 'gold_summary'::character varying])::text[]))),
    CONSTRAINT valid_quality_tier CHECK (((quality_tier)::text = ANY ((ARRAY['high'::character varying, 'medium'::character varying, 'low'::character varying, 'failed'::character varying, 'unknown'::character varying])::text[])))
);


--
-- Name: TABLE pipeline_artifacts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pipeline_artifacts IS 'Tracks specific pipeline outputs (assemblies, bins, reports) with quality metrics';


--
-- Name: COLUMN pipeline_artifacts.artifact_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_artifacts.artifact_type IS 'Type of artifact: assembly, bin, report, etc.';


--
-- Name: COLUMN pipeline_artifacts.quality_tier; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_artifacts.quality_tier IS 'Quality classification: high (>90%), medium (50-90%), low (<50%)';


--
-- Name: COLUMN pipeline_artifacts.metadata; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_artifacts.metadata IS 'JSON storage for tool-specific metrics (N50, completeness, contamination, etc.)';


--
-- Name: pipeline_artifacts_artifact_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pipeline_artifacts_artifact_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pipeline_artifacts_artifact_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pipeline_artifacts_artifact_id_seq OWNED BY public.pipeline_artifacts.artifact_id;


--
-- Name: pipeline_progress_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_progress_events (
    event_id integer NOT NULL,
    pipeline_id integer NOT NULL,
    stage character varying(100) NOT NULL,
    step character varying(200) NOT NULL,
    status character varying(50) NOT NULL,
    progress_percent integer DEFAULT 0,
    details jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE pipeline_progress_events; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pipeline_progress_events IS 'Real-time progress tracking for pipeline execution stages';


--
-- Name: COLUMN pipeline_progress_events.stage; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_progress_events.stage IS 'High-level stage: bronze_upload, nextflow_exec, silver_upload, gold_curation';


--
-- Name: COLUMN pipeline_progress_events.step; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_progress_events.step IS 'Detailed step within stage, e.g., "Compressing FASTQ", "Uploading to MinIO"';


--
-- Name: COLUMN pipeline_progress_events.progress_percent; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_progress_events.progress_percent IS 'Overall progress percentage for this stage';


--
-- Name: COLUMN pipeline_progress_events.details; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_progress_events.details IS 'JSON details: file names, sizes, process names, etc.';


--
-- Name: pipeline_progress_events_event_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pipeline_progress_events_event_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pipeline_progress_events_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pipeline_progress_events_event_id_seq OWNED BY public.pipeline_progress_events.event_id;


--
-- Name: pipeline_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_runs (
    pipeline_id integer NOT NULL,
    sample_id integer,
    pipeline_name character varying(150) NOT NULL,
    pipeline_version character varying(50),
    software_name character varying(150),
    software_version character varying(50),
    parameters text,
    reference_database character varying(150),
    reference_db_version character varying(100),
    cpu_cores integer,
    memory_gb integer,
    runtime_minutes integer,
    results_path character varying(255),
    log_file_path character varying(255),
    status character varying(50) DEFAULT 'queued'::character varying,
    exit_code integer,
    error_message text,
    queued_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    nextflow_execution_id integer,
    sample_name character varying(255),
    sample_type character varying(50) DEFAULT 'nanopore'::character varying,
    location character varying(255),
    collection_date date,
    fastq_paths text[],
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    bronze_path character varying(500),
    silver_path character varying(500),
    gold_path character varying(500),
    job_id character varying(100),
    quality_score numeric(5,2),
    amr_risk_score numeric(5,2),
    summary_json jsonb,
    results_parsed_at timestamp without time zone
);


--
-- Name: TABLE pipeline_runs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pipeline_runs IS 'Stores genomic pipeline execution runs';


--
-- Name: COLUMN pipeline_runs.pipeline_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.pipeline_id IS 'Unique pipeline run identifier';


--
-- Name: COLUMN pipeline_runs.sample_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.sample_id IS 'Reference to samples table';


--
-- Name: COLUMN pipeline_runs.parameters; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.parameters IS 'JSON object with pipeline parameters';


--
-- Name: COLUMN pipeline_runs.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.status IS 'Pipeline status: pending, running, completed, or failed';


--
-- Name: COLUMN pipeline_runs.sample_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.sample_name IS 'Convenient sample name copy for queries';


--
-- Name: COLUMN pipeline_runs.sample_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.sample_type IS 'Sequencing platform: nanopore, illumina, or pacbio';


--
-- Name: COLUMN pipeline_runs.fastq_paths; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.fastq_paths IS 'Array of paths to input FASTQ files';


--
-- Name: COLUMN pipeline_runs.bronze_path; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.bronze_path IS 'MinIO path to raw uploaded files: genomic-bronze/{sample_code}/raw/';


--
-- Name: COLUMN pipeline_runs.silver_path; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.silver_path IS 'MinIO path to intermediate results: genomic-silver/{sample_code}/{run_id}/';


--
-- Name: COLUMN pipeline_runs.gold_path; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.gold_path IS 'MinIO path to final curated results: genomic-gold/{sample_code}/';


--
-- Name: COLUMN pipeline_runs.job_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.job_id IS 'RQ job ID - used to track async pipeline execution in Redis Queue';


--
-- Name: pipeline_runs_pipeline_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pipeline_runs_pipeline_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pipeline_runs_pipeline_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pipeline_runs_pipeline_id_seq OWNED BY public.pipeline_runs.pipeline_id;


--
-- Name: quality_control_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quality_control_results (
    qc_id integer NOT NULL,
    sample_id integer,
    sequencing_run_id integer,
    total_reads bigint NOT NULL,
    passed_reads bigint NOT NULL,
    failed_reads bigint NOT NULL,
    pass_rate numeric(5,2),
    mean_quality_score numeric(5,2),
    median_quality_score numeric(5,2),
    q25_quality_score numeric(5,2),
    q75_quality_score numeric(5,2),
    mean_read_length integer,
    median_read_length integer,
    n50_read_length integer,
    min_read_length integer,
    max_read_length integer,
    gc_content numeric(5,2),
    at_content numeric(5,2),
    n_content numeric(5,2),
    contamination_rate numeric(5,2),
    human_contamination_rate numeric(5,2),
    adapter_contamination_rate numeric(5,2),
    is_passed boolean NOT NULL,
    failure_reasons text[],
    qc_tool character varying(100),
    qc_version character varying(50),
    qc_report_path character varying(255),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    nextflow_process_id integer
);


--
-- Name: TABLE quality_control_results; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.quality_control_results IS 'Quality control metrics for sequencing data';


--
-- Name: quality_control_results_qc_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.quality_control_results_qc_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: quality_control_results_qc_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.quality_control_results_qc_id_seq OWNED BY public.quality_control_results.qc_id;


--
-- Name: resistance_genes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resistance_genes (
    rg_id integer NOT NULL,
    sample_id integer,
    pipeline_run_id integer,
    gene_name character varying(200) NOT NULL,
    gene_symbol character varying(50),
    accession character varying(100),
    detection_tool character varying(100),
    coverage numeric(10,2) NOT NULL,
    identity numeric(5,2) NOT NULL,
    alignment_length integer,
    gene_length integer,
    query_start integer,
    query_end integer,
    subject_start integer,
    subject_end integer,
    read_count integer,
    depth_coverage numeric(8,2),
    surrounding_context text,
    predicted_resistance text[],
    resistance_mechanism character varying(200),
    confidence_level character varying(50),
    quality_score numeric(5,2),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    nextflow_process_id integer
);


--
-- Name: TABLE resistance_genes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.resistance_genes IS 'Antimicrobial resistance genes identified in samples (CORE UPGRADE FOCUS)';


--
-- Name: resistance_genes_rg_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.resistance_genes_rg_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: resistance_genes_rg_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.resistance_genes_rg_id_seq OWNED BY public.resistance_genes.rg_id;


--
-- Name: samples; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.samples (
    sample_id integer NOT NULL,
    sample_code character varying(100) NOT NULL,
    collection_date date NOT NULL,
    collection_time time without time zone,
    location_id integer,
    sample_type character varying(100),
    sample_volume_ml numeric(8,2),
    collection_method character varying(150),
    storage_conditions character varying(100),
    transport_conditions character varying(100),
    sequencing_platform character varying(150),
    sequencing_kit character varying(100),
    flowcell_type character varying(50),
    read_length_avg integer,
    sequencing_depth numeric(10,2),
    coverage numeric(10,2),
    quality_score numeric(5,2),
    status public.sample_status DEFAULT 'collected'::public.sample_status,
    processing_priority integer DEFAULT 1,
    expected_results_date date,
    project_id character varying(100),
    batch_id character varying(100),
    barcode character varying(50),
    notes text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE samples; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.samples IS 'Individual samples collected during campaigns';


--
-- Name: samples_sample_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.samples_sample_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: samples_sample_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.samples_sample_id_seq OWNED BY public.samples.sample_id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    user_id integer NOT NULL,
    username character varying(100) NOT NULL,
    email character varying(150) NOT NULL,
    user_type character varying(50) NOT NULL,
    password_hash character varying(255) NOT NULL,
    first_name character varying(100),
    last_name character varying(100),
    is_active boolean DEFAULT true,
    last_login timestamp with time zone,
    password_changed_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_user_type CHECK (((user_type)::text = ANY ((ARRAY['lab_technician'::character varying, 'public_health_official'::character varying, 'researcher'::character varying, 'admin'::character varying])::text[])))
);


--
-- Name: TABLE users; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.users IS 'System users: lab technicians, public health officials, researchers';


--
-- Name: users_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_user_id_seq OWNED BY public.users.user_id;


--
-- Name: v_high_quality_bins; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_high_quality_bins AS
 SELECT pa.artifact_id,
    pa.pipeline_id,
    pr.sample_id,
    s.sample_code,
    pa.artifact_name,
    pa.quality_score AS completeness,
    (pa.metadata ->> 'contamination'::text) AS contamination,
    (pa.metadata ->> 'taxonomy'::text) AS taxonomy,
    pa.file_path AS minio_path,
    pa.created_at,
    pr.pipeline_name,
    pr.status AS pipeline_status
   FROM ((public.pipeline_artifacts pa
     JOIN public.pipeline_runs pr ON ((pa.pipeline_id = pr.pipeline_id)))
     JOIN public.samples s ON ((pr.sample_id = s.sample_id)))
  WHERE (((pa.artifact_type)::text = 'bin'::text) AND ((pa.quality_tier)::text = 'high'::text) AND (pa.quality_score >= 90.0) AND (COALESCE(((pa.metadata ->> 'contamination'::text))::numeric, (100)::numeric) < 5.0))
  ORDER BY pa.quality_score DESC, s.sample_code, pa.artifact_name;


--
-- Name: VIEW v_high_quality_bins; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_high_quality_bins IS 'High-quality MAGs (>90% complete, <5% contamination) ready for publication';


--
-- Name: v_pipeline_latest_progress; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_pipeline_latest_progress AS
 SELECT DISTINCT ON (pipeline_progress_events.pipeline_id) pipeline_progress_events.pipeline_id,
    pipeline_progress_events.stage,
    pipeline_progress_events.step,
    pipeline_progress_events.status,
    pipeline_progress_events.progress_percent,
    pipeline_progress_events.details,
    pipeline_progress_events.created_at
   FROM public.pipeline_progress_events
  ORDER BY pipeline_progress_events.pipeline_id, pipeline_progress_events.created_at DESC;


--
-- Name: v_pipeline_results_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_pipeline_results_summary AS
 SELECT pr.pipeline_id,
    pr.pipeline_name,
    s.sample_code,
    pr.status,
    pr.bronze_path,
    pr.silver_path,
    pr.gold_path,
    count(DISTINCT
        CASE
            WHEN ((pa.artifact_type)::text = 'assembly'::text) THEN pa.artifact_id
            ELSE NULL::integer
        END) AS assembly_count,
    count(DISTINCT
        CASE
            WHEN ((pa.artifact_type)::text = 'bin'::text) THEN pa.artifact_id
            ELSE NULL::integer
        END) AS total_bins,
    count(DISTINCT
        CASE
            WHEN (((pa.artifact_type)::text = 'bin'::text) AND ((pa.quality_tier)::text = 'high'::text)) THEN pa.artifact_id
            ELSE NULL::integer
        END) AS high_quality_bins,
    count(DISTINCT
        CASE
            WHEN (((pa.artifact_type)::text = 'bin'::text) AND ((pa.quality_tier)::text = 'medium'::text)) THEN pa.artifact_id
            ELSE NULL::integer
        END) AS medium_quality_bins,
    count(DISTINCT
        CASE
            WHEN (((pa.artifact_type)::text = 'bin'::text) AND ((pa.quality_tier)::text = 'low'::text)) THEN pa.artifact_id
            ELSE NULL::integer
        END) AS low_quality_bins,
    pr.created_at,
    pr.completed_at
   FROM ((public.pipeline_runs pr
     JOIN public.samples s ON ((pr.sample_id = s.sample_id)))
     LEFT JOIN public.pipeline_artifacts pa ON ((pr.pipeline_id = pa.pipeline_id)))
  GROUP BY pr.pipeline_id, pr.pipeline_name, s.sample_code, pr.status, pr.bronze_path, pr.silver_path, pr.gold_path, pr.created_at, pr.completed_at
  ORDER BY pr.created_at DESC;


--
-- Name: VIEW v_pipeline_results_summary; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_pipeline_results_summary IS 'Summary of pipeline results with artifact counts by quality tier';


--
-- Name: weather_measurements_weather_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.weather_measurements_weather_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: weather_measurements_weather_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.weather_measurements_weather_id_seq OWNED BY public.weather_measurements.weather_id;


--
-- Name: assemblies assembly_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assemblies ALTER COLUMN assembly_id SET DEFAULT nextval('public.assemblies_assembly_id_seq'::regclass);


--
-- Name: data_lineage lineage_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_lineage ALTER COLUMN lineage_id SET DEFAULT nextval('public.data_lineage_lineage_id_seq'::regclass);


--
-- Name: detected_organisms detection_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detected_organisms ALTER COLUMN detection_id SET DEFAULT nextval('public.detected_organisms_detection_id_seq'::regclass);


--
-- Name: locations location_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.locations ALTER COLUMN location_id SET DEFAULT nextval('public.locations_location_id_seq'::regclass);


--
-- Name: minio_buckets bucket_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.minio_buckets ALTER COLUMN bucket_id SET DEFAULT nextval('public.minio_buckets_bucket_id_seq'::regclass);


--
-- Name: minio_objects object_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.minio_objects ALTER COLUMN object_id SET DEFAULT nextval('public.minio_objects_object_id_seq'::regclass);


--
-- Name: nextflow_executions execution_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nextflow_executions ALTER COLUMN execution_id SET DEFAULT nextval('public.nextflow_executions_execution_id_seq'::regclass);


--
-- Name: nextflow_workflows workflow_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nextflow_workflows ALTER COLUMN workflow_id SET DEFAULT nextval('public.nextflow_workflows_workflow_id_seq'::regclass);


--
-- Name: pipeline_artifacts artifact_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_artifacts ALTER COLUMN artifact_id SET DEFAULT nextval('public.pipeline_artifacts_artifact_id_seq'::regclass);


--
-- Name: pipeline_progress_events event_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_progress_events ALTER COLUMN event_id SET DEFAULT nextval('public.pipeline_progress_events_event_id_seq'::regclass);


--
-- Name: pipeline_runs pipeline_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_runs ALTER COLUMN pipeline_id SET DEFAULT nextval('public.pipeline_runs_pipeline_id_seq'::regclass);


--
-- Name: quality_control_results qc_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quality_control_results ALTER COLUMN qc_id SET DEFAULT nextval('public.quality_control_results_qc_id_seq'::regclass);


--
-- Name: resistance_genes rg_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resistance_genes ALTER COLUMN rg_id SET DEFAULT nextval('public.resistance_genes_rg_id_seq'::regclass);


--
-- Name: samples sample_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.samples ALTER COLUMN sample_id SET DEFAULT nextval('public.samples_sample_id_seq'::regclass);


--
-- Name: users user_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN user_id SET DEFAULT nextval('public.users_user_id_seq'::regclass);


--
-- Name: weather_measurements weather_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.weather_measurements ALTER COLUMN weather_id SET DEFAULT nextval('public.weather_measurements_weather_id_seq'::regclass);


--
-- Name: assemblies assemblies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assemblies
    ADD CONSTRAINT assemblies_pkey PRIMARY KEY (assembly_id);


--
-- Name: data_lineage data_lineage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_lineage
    ADD CONSTRAINT data_lineage_pkey PRIMARY KEY (lineage_id);


--
-- Name: detected_organisms detected_organisms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detected_organisms
    ADD CONSTRAINT detected_organisms_pkey PRIMARY KEY (detection_id);


--
-- Name: locations locations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.locations
    ADD CONSTRAINT locations_pkey PRIMARY KEY (location_id);


--
-- Name: minio_buckets minio_buckets_bucket_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.minio_buckets
    ADD CONSTRAINT minio_buckets_bucket_name_key UNIQUE (bucket_name);


--
-- Name: minio_buckets minio_buckets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.minio_buckets
    ADD CONSTRAINT minio_buckets_pkey PRIMARY KEY (bucket_id);


--
-- Name: minio_objects minio_objects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.minio_objects
    ADD CONSTRAINT minio_objects_pkey PRIMARY KEY (object_id);


--
-- Name: nextflow_executions nextflow_executions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nextflow_executions
    ADD CONSTRAINT nextflow_executions_pkey PRIMARY KEY (execution_id);


--
-- Name: nextflow_workflows nextflow_workflows_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nextflow_workflows
    ADD CONSTRAINT nextflow_workflows_pkey PRIMARY KEY (workflow_id);


--
-- Name: pipeline_artifacts pipeline_artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_artifacts
    ADD CONSTRAINT pipeline_artifacts_pkey PRIMARY KEY (artifact_id);


--
-- Name: pipeline_progress_events pipeline_progress_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_progress_events
    ADD CONSTRAINT pipeline_progress_events_pkey PRIMARY KEY (event_id);


--
-- Name: pipeline_runs pipeline_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_runs
    ADD CONSTRAINT pipeline_runs_pkey PRIMARY KEY (pipeline_id);


--
-- Name: quality_control_results quality_control_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quality_control_results
    ADD CONSTRAINT quality_control_results_pkey PRIMARY KEY (qc_id);


--
-- Name: resistance_genes resistance_genes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resistance_genes
    ADD CONSTRAINT resistance_genes_pkey PRIMARY KEY (rg_id);


--
-- Name: samples samples_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.samples
    ADD CONSTRAINT samples_pkey PRIMARY KEY (sample_id);


--
-- Name: samples samples_sample_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.samples
    ADD CONSTRAINT samples_sample_code_key UNIQUE (sample_code);


--
-- Name: minio_objects unique_bucket_object; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.minio_objects
    ADD CONSTRAINT unique_bucket_object UNIQUE (bucket_id, object_key, version_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: weather_measurements weather_measurements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.weather_measurements
    ADD CONSTRAINT weather_measurements_pkey PRIMARY KEY (weather_id);


--
-- Name: idx_artifacts_minio_object; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_minio_object ON public.pipeline_artifacts USING btree (minio_object_id);


--
-- Name: idx_artifacts_pipeline; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_pipeline ON public.pipeline_artifacts USING btree (pipeline_id);


--
-- Name: idx_artifacts_quality; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_quality ON public.pipeline_artifacts USING btree (quality_tier);


--
-- Name: idx_artifacts_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artifacts_type ON public.pipeline_artifacts USING btree (artifact_type);


--
-- Name: idx_assemblies_pipeline; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_assemblies_pipeline ON public.assemblies USING btree (pipeline_run_id);


--
-- Name: idx_assemblies_quality; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_assemblies_quality ON public.assemblies USING btree (quality_grade);


--
-- Name: idx_assemblies_sample; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_assemblies_sample ON public.assemblies USING btree (sample_id);


--
-- Name: idx_data_lineage_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_data_lineage_source ON public.data_lineage USING btree (source_object_id);


--
-- Name: idx_data_lineage_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_data_lineage_target ON public.data_lineage USING btree (target_object_id);


--
-- Name: idx_detected_organisms_abundance; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_detected_organisms_abundance ON public.detected_organisms USING btree (abundance DESC);


--
-- Name: idx_detected_organisms_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_detected_organisms_name ON public.detected_organisms USING btree (organism_name);


--
-- Name: idx_detected_organisms_pipeline; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_detected_organisms_pipeline ON public.detected_organisms USING btree (pipeline_run_id);


--
-- Name: idx_detected_organisms_sample; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_detected_organisms_sample ON public.detected_organisms USING btree (sample_id);


--
-- Name: idx_locations_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_locations_active ON public.locations USING btree (is_active) WHERE (is_active = true);


--
-- Name: idx_locations_campus_area; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_locations_campus_area ON public.locations USING btree (campus_area) WHERE (campus_area IS NOT NULL);


--
-- Name: idx_locations_coordinates; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_locations_coordinates ON public.locations USING btree (latitude, longitude);


--
-- Name: idx_locations_country_region; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_locations_country_region ON public.locations USING btree (country, region);


--
-- Name: idx_locations_traffic_density; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_locations_traffic_density ON public.locations USING btree (traffic_density);


--
-- Name: idx_minio_objects_bucket_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_minio_objects_bucket_key ON public.minio_objects USING btree (bucket_id, object_key);


--
-- Name: idx_minio_objects_execution; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_minio_objects_execution ON public.minio_objects USING btree (execution_id);


--
-- Name: idx_minio_objects_layer_stage; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_minio_objects_layer_stage ON public.minio_objects USING btree (layer_stage);


--
-- Name: idx_minio_objects_pipeline; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_minio_objects_pipeline ON public.minio_objects USING btree (pipeline_id);


--
-- Name: idx_minio_objects_process; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_minio_objects_process ON public.minio_objects USING btree (process_name);


--
-- Name: idx_minio_objects_sample; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_minio_objects_sample ON public.minio_objects USING btree (sample_id, created_at DESC);


--
-- Name: idx_mv_latest_weather_location; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_mv_latest_weather_location ON public.mv_latest_weather_conditions USING btree (location_id);


--
-- Name: idx_mv_latest_weather_measurement; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mv_latest_weather_measurement ON public.mv_latest_weather_conditions USING btree (measurement_datetime DESC);


--
-- Name: idx_nextflow_executions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nextflow_executions_status ON public.nextflow_executions USING btree (status, start_time DESC);


--
-- Name: idx_nextflow_executions_workflow; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nextflow_executions_workflow ON public.nextflow_executions USING btree (workflow_id, start_time DESC);


--
-- Name: idx_pipeline_progress_pipeline; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_progress_pipeline ON public.pipeline_progress_events USING btree (pipeline_id, created_at DESC);


--
-- Name: idx_pipeline_progress_stage; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_progress_stage ON public.pipeline_progress_events USING btree (stage, status);


--
-- Name: idx_pipeline_runs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_runs_created_at ON public.pipeline_runs USING btree (created_at DESC);


--
-- Name: idx_pipeline_runs_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_runs_job_id ON public.pipeline_runs USING btree (job_id);


--
-- Name: idx_pipeline_runs_sample; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_runs_sample ON public.pipeline_runs USING btree (sample_id);


--
-- Name: idx_pipeline_runs_sample_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_runs_sample_name ON public.pipeline_runs USING btree (sample_name);


--
-- Name: idx_pipeline_runs_started; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_runs_started ON public.pipeline_runs USING btree (started_at DESC);


--
-- Name: idx_pipeline_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_runs_status ON public.pipeline_runs USING btree (status);


--
-- Name: idx_qc_passed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qc_passed ON public.quality_control_results USING btree (is_passed);


--
-- Name: idx_qc_sample; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qc_sample ON public.quality_control_results USING btree (sample_id);


--
-- Name: idx_qc_sequencing_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qc_sequencing_run ON public.quality_control_results USING btree (sequencing_run_id);


--
-- Name: idx_resistance_genes_coverage; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_resistance_genes_coverage ON public.resistance_genes USING btree (coverage DESC, identity DESC);


--
-- Name: idx_resistance_genes_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_resistance_genes_name ON public.resistance_genes USING btree (gene_name);


--
-- Name: idx_resistance_genes_pipeline; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_resistance_genes_pipeline ON public.resistance_genes USING btree (pipeline_run_id);


--
-- Name: idx_resistance_genes_sample; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_resistance_genes_sample ON public.resistance_genes USING btree (sample_id);


--
-- Name: idx_samples_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_samples_code ON public.samples USING btree (sample_code);


--
-- Name: idx_samples_location_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_samples_location_date ON public.samples USING btree (location_id, collection_date DESC);


--
-- Name: idx_samples_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_samples_status ON public.samples USING btree (status);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_email ON public.users USING btree (email);


--
-- Name: idx_users_type_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_type_active ON public.users USING btree (user_type, is_active) WHERE (is_active = true);


--
-- Name: idx_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_username ON public.users USING btree (username);


--
-- Name: idx_weather_datetime; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_weather_datetime ON public.weather_measurements USING btree (measurement_datetime DESC);


--
-- Name: idx_weather_location_datetime; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_weather_location_datetime ON public.weather_measurements USING btree (location_id, measurement_datetime DESC);


--
-- Name: idx_weather_quality; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_weather_quality ON public.weather_measurements USING btree (data_quality);


--
-- Name: idx_weather_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_weather_source ON public.weather_measurements USING btree (source);


--
-- Name: minio_objects update_bucket_stats_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_bucket_stats_trigger AFTER INSERT OR DELETE OR UPDATE ON public.minio_objects FOR EACH ROW EXECUTE FUNCTION public.update_bucket_stats();


--
-- Name: locations update_locations_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_locations_updated_at BEFORE UPDATE ON public.locations FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: pipeline_artifacts update_pipeline_artifacts_timestamp; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_pipeline_artifacts_timestamp BEFORE UPDATE ON public.pipeline_artifacts FOR EACH ROW EXECUTE FUNCTION public.update_artifacts_timestamp();


--
-- Name: pipeline_runs update_pipeline_runs_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_pipeline_runs_updated_at BEFORE UPDATE ON public.pipeline_runs FOR EACH ROW EXECUTE FUNCTION public.update_pipeline_runs_updated_at();


--
-- Name: samples update_samples_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_samples_updated_at BEFORE UPDATE ON public.samples FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: assemblies assemblies_pipeline_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assemblies
    ADD CONSTRAINT assemblies_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(pipeline_id);


--
-- Name: assemblies assemblies_sample_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assemblies
    ADD CONSTRAINT assemblies_sample_id_fkey FOREIGN KEY (sample_id) REFERENCES public.samples(sample_id) ON DELETE CASCADE;


--
-- Name: data_lineage data_lineage_source_object_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_lineage
    ADD CONSTRAINT data_lineage_source_object_id_fkey FOREIGN KEY (source_object_id) REFERENCES public.minio_objects(object_id);


--
-- Name: data_lineage data_lineage_target_object_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_lineage
    ADD CONSTRAINT data_lineage_target_object_id_fkey FOREIGN KEY (target_object_id) REFERENCES public.minio_objects(object_id);


--
-- Name: detected_organisms detected_organisms_pipeline_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detected_organisms
    ADD CONSTRAINT detected_organisms_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(pipeline_id);


--
-- Name: detected_organisms detected_organisms_sample_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detected_organisms
    ADD CONSTRAINT detected_organisms_sample_id_fkey FOREIGN KEY (sample_id) REFERENCES public.samples(sample_id) ON DELETE CASCADE;


--
-- Name: minio_objects minio_objects_bucket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.minio_objects
    ADD CONSTRAINT minio_objects_bucket_id_fkey FOREIGN KEY (bucket_id) REFERENCES public.minio_buckets(bucket_id) ON DELETE CASCADE;


--
-- Name: minio_objects minio_objects_execution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.minio_objects
    ADD CONSTRAINT minio_objects_execution_id_fkey FOREIGN KEY (execution_id) REFERENCES public.nextflow_executions(execution_id);


--
-- Name: minio_objects minio_objects_pipeline_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.minio_objects
    ADD CONSTRAINT minio_objects_pipeline_id_fkey FOREIGN KEY (pipeline_id) REFERENCES public.pipeline_runs(pipeline_id);


--
-- Name: minio_objects minio_objects_sample_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.minio_objects
    ADD CONSTRAINT minio_objects_sample_id_fkey FOREIGN KEY (sample_id) REFERENCES public.samples(sample_id);


--
-- Name: nextflow_executions nextflow_executions_workflow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nextflow_executions
    ADD CONSTRAINT nextflow_executions_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.nextflow_workflows(workflow_id);


--
-- Name: pipeline_artifacts pipeline_artifacts_minio_object_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_artifacts
    ADD CONSTRAINT pipeline_artifacts_minio_object_id_fkey FOREIGN KEY (minio_object_id) REFERENCES public.minio_objects(object_id) ON DELETE SET NULL;


--
-- Name: pipeline_artifacts pipeline_artifacts_pipeline_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_artifacts
    ADD CONSTRAINT pipeline_artifacts_pipeline_id_fkey FOREIGN KEY (pipeline_id) REFERENCES public.pipeline_runs(pipeline_id) ON DELETE CASCADE;


--
-- Name: pipeline_progress_events pipeline_progress_events_pipeline_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_progress_events
    ADD CONSTRAINT pipeline_progress_events_pipeline_id_fkey FOREIGN KEY (pipeline_id) REFERENCES public.pipeline_runs(pipeline_id) ON DELETE CASCADE;


--
-- Name: pipeline_runs pipeline_runs_nextflow_execution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_runs
    ADD CONSTRAINT pipeline_runs_nextflow_execution_id_fkey FOREIGN KEY (nextflow_execution_id) REFERENCES public.nextflow_executions(execution_id);


--
-- Name: pipeline_runs pipeline_runs_sample_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_runs
    ADD CONSTRAINT pipeline_runs_sample_id_fkey FOREIGN KEY (sample_id) REFERENCES public.samples(sample_id) ON DELETE CASCADE;


--
-- Name: quality_control_results quality_control_results_sample_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quality_control_results
    ADD CONSTRAINT quality_control_results_sample_id_fkey FOREIGN KEY (sample_id) REFERENCES public.samples(sample_id) ON DELETE CASCADE;


--
-- Name: resistance_genes resistance_genes_pipeline_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resistance_genes
    ADD CONSTRAINT resistance_genes_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(pipeline_id);


--
-- Name: resistance_genes resistance_genes_sample_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resistance_genes
    ADD CONSTRAINT resistance_genes_sample_id_fkey FOREIGN KEY (sample_id) REFERENCES public.samples(sample_id) ON DELETE CASCADE;


--
-- Name: samples samples_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.samples
    ADD CONSTRAINT samples_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.locations(location_id);


--
-- Name: weather_measurements weather_measurements_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.weather_measurements
    ADD CONSTRAINT weather_measurements_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.locations(location_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--
