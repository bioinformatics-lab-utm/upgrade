# UPGRADE Platform — Entity Relationship Diagram

> **19 active tables** after schema cleanup (was 53).
> Grouped by domain. Generated 2026-03-17.

```mermaid
erDiagram

    %% ═══════════════════════════════════════════
    %% AUTH
    %% ═══════════════════════════════════════════

    users {
        int     user_id         PK
        varchar username
        varchar email
        varchar user_type
        varchar password_hash
        varchar first_name
        varchar last_name
        bool    is_active
        ts      last_login
        ts      created_at
    }

    user_sessions {
        int     session_id      PK
        int     user_id         FK
        varchar session_token
        inet    ip_address
        ts      expires_at
        bool    is_active
    }

    user_permissions {
        int     permission_id   PK
        int     user_id         FK
        int     granted_by      FK
        varchar resource_type
        varchar permission_level
        int     resource_id
        bool    is_active
    }

    %% ═══════════════════════════════════════════
    %% GEOGRAPHY
    %% ═══════════════════════════════════════════

    locations {
        int     location_id     PK
        varchar location_name
        varchar country
        varchar city
        numeric latitude
        numeric longitude
        varchar indoor_outdoor
        varchar campus_area
        jsonb   metadata
    }

    weather_measurements {
        int     weather_id           PK
        int     location_id          FK
        ts      measurement_datetime
        numeric temperature
        numeric humidity
        numeric rainfall
        numeric windspeed
        int     weather_code
        varchar weather_api_source
    }

    %% ═══════════════════════════════════════════
    %% SAMPLES
    %% ═══════════════════════════════════════════

    samples {
        int     sample_id           PK
        int     location_id         FK
        varchar sample_code
        date    collection_date
        varchar sample_type
        varchar sequencing_platform
        varchar sequencing_kit
        varchar flowcell_type
        numeric sequencing_depth
        varchar status
        varchar batch_id
        jsonb   metadata
    }

    %% ═══════════════════════════════════════════
    %% NEXTFLOW ORCHESTRATION
    %% ═══════════════════════════════════════════

    nextflow_workflows {
        int     workflow_id          PK
        varchar workflow_name
        varchar workflow_version
        varchar nextflow_version
        varchar workflow_script_path
        bool    is_active
        int     default_cpu
        int     default_memory_gb
    }

    nextflow_executions {
        int      execution_id       PK
        int      workflow_id        FK
        varchar  execution_name
        varchar  nextflow_run_name
        varchar  status
        ts       start_time
        ts       complete_time
        interval duration
        numeric  total_cpu_hours
        numeric  peak_memory_gb
        jsonb    params
    }

    %% ═══════════════════════════════════════════
    %% PIPELINE RUNS (CORE)
    %% ═══════════════════════════════════════════

    pipeline_runs {
        int     pipeline_id              PK
        int     sample_id                FK
        int     nextflow_execution_id    FK
        varchar pipeline_name
        varchar pipeline_version
        varchar status
        varchar job_id
        int     cpu_cores
        int     memory_gb
        int     runtime_minutes
        varchar results_path
        varchar bronze_path
        varchar silver_path
        varchar gold_path
        numeric quality_score
        numeric amr_risk_score
        jsonb   summary_json
        ts      queued_at
        ts      started_at
        ts      completed_at
    }

    pipeline_progress_events {
        int     event_id        PK
        int     pipeline_id     FK
        varchar stage
        varchar step
        varchar status
        int     progress_percent
        jsonb   details
        ts      created_at
    }

    pipeline_artifacts {
        int     artifact_id     PK
        int     pipeline_id     FK
        int     minio_object_id FK
        varchar artifact_type
        varchar artifact_name
        varchar quality_tier
        numeric quality_score
        varchar process_name
        jsonb   metadata
    }

    %% ═══════════════════════════════════════════
    %% STORAGE — LAKEHOUSE (Bronze / Silver / Gold)
    %% ═══════════════════════════════════════════

    minio_buckets {
        int     bucket_id           PK
        varchar bucket_name
        varchar layer_type
        varchar retention_policy
        bool    versioning_enabled
        bool    encryption_enabled
        bigint  object_count
        bigint  total_size_bytes
    }

    minio_objects {
        int     object_id       PK
        int     bucket_id       FK
        int     sample_id       FK
        int     pipeline_id     FK
        int     execution_id    FK
        varchar object_key
        varchar object_name
        bigint  object_size_bytes
        varchar content_type
        varchar layer_stage
        varchar process_name
        jsonb   metadata
        jsonb   tags
    }

    data_lineage {
        int      lineage_id             PK
        int      source_object_id       FK
        int      target_object_id       FK
        varchar  transformation_type
        varchar  transformation_process
        interval processing_duration
        jsonb    quality_metrics
    }

    %% ═══════════════════════════════════════════
    %% ANALYSIS RESULTS
    %% ═══════════════════════════════════════════

    assemblies {
        int     assembly_id         PK
        int     sample_id           FK
        int     pipeline_run_id     FK
        varchar assembler
        varchar assembly_type
        int     total_contigs
        bigint  total_length
        int     n50_contig
        numeric gc_content
        numeric completeness
        numeric contamination
        varchar quality_grade
        varchar assembly_fasta_path
    }

    quality_control_results {
        int     qc_id               PK
        int     sample_id           FK
        bigint  total_reads
        bigint  passed_reads
        numeric pass_rate
        numeric mean_quality_score
        int     n50_read_length
        numeric gc_content
        numeric contamination_rate
        bool    is_passed
        varchar qc_tool
        varchar qc_report_path
    }

    detected_organisms {
        int     detection_id        PK
        int     sample_id           FK
        int     pipeline_run_id     FK
        varchar organism_name
        varchar taxonomy_rank
        varchar classification_tool
        int     read_count
        numeric abundance
        numeric confidence_score
        ts      created_at
    }

    resistance_genes {
        int     rg_id               PK
        int     sample_id           FK
        int     pipeline_run_id     FK
        varchar gene_name
        varchar gene_symbol
        varchar detection_tool
        numeric coverage
        numeric identity
        varchar resistance_mechanism
        array   predicted_resistance
        numeric quality_score
        ts      created_at
    }

    virulence_factors {
        int     vf_id               PK
        int     sample_id           FK
        int     pipeline_run_id     FK
        varchar gene_name
        varchar vf_category
        varchar detection_tool
        numeric coverage
        numeric identity
        varchar clinical_significance
        ts      created_at
    }

    %% ═══════════════════════════════════════════
    %% RELATIONSHIPS
    %% ═══════════════════════════════════════════

    %% Auth
    users              ||--o{ user_sessions            : "has sessions"
    users              ||--o{ user_permissions         : "has permissions"
    users              ||--o{ user_permissions         : "grants"

    %% Geography
    locations          ||--o{ weather_measurements     : "measured at"
    locations          ||--o{ samples                  : "collected at"

    %% Nextflow orchestration
    nextflow_workflows ||--o{ nextflow_executions      : "executed as"
    nextflow_executions ||--o{ pipeline_runs           : "tracks"
    nextflow_executions ||--o{ minio_objects           : "produces"

    %% Pipeline core
    samples            ||--o{ pipeline_runs            : "processed in"
    pipeline_runs      ||--o{ pipeline_progress_events : "emits events"
    pipeline_runs      ||--o{ pipeline_artifacts       : "produces artifacts"

    %% Storage — Lakehouse
    minio_buckets      ||--o{ minio_objects            : "contains"
    pipeline_runs      ||--o{ minio_objects            : "writes to"
    samples            ||--o{ minio_objects            : "stored as"
    minio_objects      ||--o{ pipeline_artifacts       : "referenced by"
    minio_objects      ||--o{ data_lineage             : "source"
    minio_objects      ||--o{ data_lineage             : "target"

    %% Analysis results
    samples            ||--o{ assemblies               : "has assemblies"
    pipeline_runs      ||--o{ assemblies               : "generates"
    samples            ||--o{ quality_control_results  : "has QC"
    samples            ||--o{ detected_organisms       : "has organisms"
    pipeline_runs      ||--o{ detected_organisms       : "detects"
    samples            ||--o{ resistance_genes         : "has AMR genes"
    pipeline_runs      ||--o{ resistance_genes         : "finds"
    samples            ||--o{ virulence_factors        : "has VFs"
    pipeline_runs      ||--o{ virulence_factors        : "identifies"
```

---

## Domain map

| Domain | Tables | Purpose |
|--------|--------|---------|
| **Auth** | `users`, `user_sessions`, `user_permissions` | Login, RBAC, session management |
| **Geography** | `locations`, `weather_measurements` | Sampling sites + Open-Meteo weather data |
| **Samples** | `samples` | Core biological sample registry (787 samples) |
| **Nextflow** | `nextflow_workflows`, `nextflow_executions` | Pipeline orchestration metadata |
| **Pipeline core** | `pipeline_runs`, `pipeline_progress_events`, `pipeline_artifacts` | RQ job tracking, progress events, lakehouse artifacts |
| **Lakehouse** | `minio_buckets`, `minio_objects`, `data_lineage` | Bronze→Silver→Gold object store + transformation lineage |
| **Analysis** | `assemblies`, `quality_control_results`, `detected_organisms`, `resistance_genes`, `virulence_factors` | Bioinformatics pipeline outputs |

---

## Tables to watch

| Table | Rows | Issue |
|-------|------|-------|
| `data_lineage` | 12 958 | 3 MB — populated but no frontend API endpoint |
| `nextflow_executions` | 597 | Populated but not surfaced on frontend |
| `detected_organisms` | 0 | Kraken2/Bracken results not stored here yet |
| `virulence_factors` | 0 | DeepARG VF results not stored here yet |
| `quality_control_results` | 38 | Populated but not shown on frontend |
