# UPGRADE Platform — Architecture Diagram

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#1a1a2e',
    'primaryTextColor': '#e0e0e0',
    'primaryBorderColor': '#16213e',
    'lineColor': '#7f8fa6',
    'secondaryColor': '#0f3460',
    'tertiaryColor': '#533483',
    'background': '#0d1117',
    'mainBkg': '#161b22',
    'nodeBorder': '#30363d',
    'clusterBkg': '#0d1117',
    'clusterBorder': '#30363d',
    'titleColor': '#58a6ff',
    'edgeLabelBackground': '#161b22'
  }
}}%%

flowchart TB

  %% ═══════════════════════════════════════════
  %% CLIENTS
  %% ═══════════════════════════════════════════
  subgraph CLIENTS["🖥️ Clients"]
    direction LR
    BROWSER["<b>Web Browser</b><br/>React 18 + Leaflet + Plotly<br/>Pipeline UI · Results · Map"]
    ADMIN["<b>Admin Tools</b><br/>pgAdmin · Kafka UI<br/>MinIO Console · Grafana"]
  end

  %% ═══════════════════════════════════════════
  %% GATEWAY
  %% ═══════════════════════════════════════════
  subgraph GATEWAY["🔒 Gateway — Nginx"]
    direction LR
    NGINX["<b>Nginx</b><br/>SSL/TLS · Rate Limiting<br/>30 req/s API · 5 req/min Login<br/>10 GB upload · WebSocket"]
  end

  %% ═══════════════════════════════════════════
  %% APPLICATION LAYER
  %% ═══════════════════════════════════════════
  subgraph APP["⚙️ Application Layer"]
    direction LR

    subgraph BACKEND["Python Backend"]
      SANIC["<b>Sanic API</b> :8000<br/>Async Python<br/>JWT Auth · CORS"]
      ROUTES["<b>Routes</b><br/>/api/auth · /api/pipeline<br/>/api/samples · /api/results<br/>/api/monitoring · /metrics"]
    end

    subgraph FRONTEND["React Frontend"]
      REACT["<b>React SPA</b> :3000<br/>PipelineDashboard<br/>ResultsViewer · GenomicsMap<br/>WeatherDashboard"]
    end
  end

  %% ═══════════════════════════════════════════
  %% TASK EXECUTION
  %% ═══════════════════════════════════════════
  subgraph TASKS["🔄 Task Execution"]
    direction LR
    REDIS_Q["<b>Redis 7</b> :6379<br/>Job Queue (RQ)<br/>Session Cache<br/>Rate Limit Store"]
    RQ_WORKER["<b>RQ Worker</b><br/>Pipeline Executor<br/>Timeout: 12h<br/>Async DB + MinIO"]
  end

  %% ═══════════════════════════════════════════
  %% NEXTFLOW PIPELINE
  %% ═══════════════════════════════════════════
  subgraph PIPELINE["🧬 Nextflow Bioinformatics Pipeline — 24 Processes"]
    direction LR

    subgraph QC["01 — QC"]
      NANOPLOT["NanoPlot"]
      FILTLONG["Filtlong"]
    end

    subgraph ASSEMBLY["02 — Assembly"]
      FLYE["Flye"]
      MEDAKA["Medaka"]
      STATS["Assembly Stats"]
    end

    subgraph BINNING["03 — Binning"]
      METABAT2["MetaBAT2"]
      CONCOCT["CONCOCT"]
      CHECKM["CheckM"]
      DREP["dRep"]
    end

    subgraph TAXONOMY["04 — Taxonomy"]
      KRAKEN2["Kraken2"]
      GTDBTK["GTDB-Tk"]
      BRACKEN["Bracken"]
    end

    subgraph FUNCTIONAL["05 — Functional"]
      PROKKA["Prokka"]
      ABRICATE["ABRicate"]
      DEEPARG["DeepARG"]
    end

    subgraph MOBILE["06 — Mobile Elements"]
      VIRSORTER["VirSorter2"]
      PLASMIDFINDER["PlasmidFinder"]
      MOBSUITE["MOB-suite"]
    end
  end

  %% ═══════════════════════════════════════════
  %% DATA LAKEHOUSE
  %% ═══════════════════════════════════════════
  subgraph LAKEHOUSE["🏛️ Data Lakehouse — MinIO S3"]
    direction LR

    BRONZE["<b>🥉 Bronze</b><br/>Raw FASTQ uploads<br/>Weather JSON<br/>Unprocessed data"]

    SILVER["<b>🥈 Silver</b><br/>01_QC/ · 02_filtered/<br/>03_assembly/ · 04_binning/<br/>05_quality/ · 06_kraken2/<br/>07_amr/ · Lineage tracked"]

    GOLD["<b>🥇 Gold</b><br/>Quality-scored MAGs<br/>Curated assemblies<br/>Final reports<br/>CheckM filtered"]

    BRONZE -->|"upload_to_silver()<br/>per Nextflow process"| SILVER
    SILVER -->|"curate_gold_layer()<br/>quality scoring"| GOLD
  end

  %% ═══════════════════════════════════════════
  %% DATA STORES
  %% ═══════════════════════════════════════════
  subgraph DATA["💾 Data Stores"]
    direction LR
    POSTGRES["<b>PostgreSQL 15</b> :5432<br/>PostGIS · asyncpg<br/>samples · pipeline_runs<br/>minio_objects · data_lineage<br/>users · locations"]
    VAULT_S["<b>Vault</b> :8200<br/>HashiCorp<br/>DB passwords · JWT key<br/>API keys · MinIO creds"]
  end

  %% ═══════════════════════════════════════════
  %% STREAMING
  %% ═══════════════════════════════════════════
  subgraph STREAMING["📡 Event Streaming"]
    direction LR
    KAFKA["<b>Kafka</b> :9092<br/>Topic: weather-data<br/>7-day retention"]
    ZK["<b>Zookeeper</b> :2181"]
    WEATHER_P["<b>Weather Producer</b><br/>Open-Meteo API<br/>30 min interval<br/>RO + MD cities"]
    WEATHER_C["<b>Weather Consumer</b><br/>Kafka → PostgreSQL<br/>Kafka → MinIO Bronze"]
  end

  %% ═══════════════════════════════════════════
  %% MONITORING
  %% ═══════════════════════════════════════════
  subgraph MONITORING["📊 Observability"]
    direction LR
    PROMETHEUS["<b>Prometheus</b> :9090<br/>30-day retention<br/>15s scrape interval"]
    GRAFANA["<b>Grafana</b> :3001<br/>Dashboards<br/>Alerts"]
    LOKI["<b>Loki</b> :3100<br/>Log aggregation"]
    PROMTAIL["<b>Promtail</b><br/>Log shipper"]
    ALERTMGR["<b>AlertManager</b> :9093<br/>Email · Severity routing"]
    NODE_EXP["Node\nExporter"]
    PG_EXP["Postgres\nExporter"]
    REDIS_EXP["Redis\nExporter"]
  end

  %% ═══════════════════════════════════════════
  %% CONNECTIONS
  %% ═══════════════════════════════════════════

  %% Client → Gateway → App
  BROWSER -->|HTTPS| NGINX
  ADMIN -->|HTTPS| NGINX
  NGINX -->|proxy /api| SANIC
  NGINX -->|proxy /| REACT
  NGINX -->|proxy /grafana| GRAFANA
  NGINX -->|proxy /minio| LAKEHOUSE

  %% App internals
  SANIC --- ROUTES
  SANIC -->|"asyncpg pool<br/>10-100 conn"| POSTGRES
  SANIC -->|"enqueue job"| REDIS_Q
  SANIC -->|"presigned URLs"| LAKEHOUSE
  SANIC -->|"secrets"| VAULT_S

  %% Task flow
  REDIS_Q -->|"dequeue"| RQ_WORKER
  RQ_WORKER -->|"nextflow run"| PIPELINE
  RQ_WORKER -->|"upload results"| LAKEHOUSE
  RQ_WORKER -->|"update status"| POSTGRES

  %% Pipeline → Lakehouse
  PIPELINE -->|"Docker containers<br/>62 CPUs · 120 GB RAM"| LAKEHOUSE

  %% Streaming
  WEATHER_P -->|produce| KAFKA
  KAFKA --- ZK
  KAFKA -->|consume| WEATHER_C
  WEATHER_C -->|"weather_measurements"| POSTGRES
  WEATHER_C -->|"archive JSON"| BRONZE

  %% Monitoring
  NODE_EXP --> PROMETHEUS
  PG_EXP --> PROMETHEUS
  REDIS_EXP --> PROMETHEUS
  SANIC -.->|"/metrics"| PROMETHEUS
  PROMETHEUS --> GRAFANA
  PROMETHEUS --> ALERTMGR
  PROMTAIL --> LOKI
  LOKI --> GRAFANA

  %% ═══════════════════════════════════════════
  %% STYLES
  %% ═══════════════════════════════════════════
  classDef bronze fill:#cd7f32,stroke:#8b5a2b,color:#fff,stroke-width:2px
  classDef silver fill:#708090,stroke:#4a5568,color:#fff,stroke-width:2px
  classDef gold fill:#daa520,stroke:#b8860b,color:#fff,stroke-width:2px
  classDef pipeline fill:#2d5016,stroke:#4a7c23,color:#e0e0e0,stroke-width:1px
  classDef api fill:#1e3a5f,stroke:#2980b9,color:#e0e0e0,stroke-width:2px
  classDef storage fill:#4a1942,stroke:#7b2d8e,color:#e0e0e0,stroke-width:2px
  classDef monitor fill:#1a3c40,stroke:#2e8b57,color:#e0e0e0,stroke-width:1px
  classDef stream fill:#3d1c02,stroke:#d35400,color:#e0e0e0,stroke-width:1px
  classDef gateway fill:#8b0000,stroke:#dc143c,color:#fff,stroke-width:2px

  class BRONZE bronze
  class SILVER silver
  class GOLD gold
  class NANOPLOT,FILTLONG,FLYE,MEDAKA,STATS,METABAT2,CONCOCT,CHECKM,DREP,KRAKEN2,GTDBTK,BRACKEN,PROKKA,ABRICATE,DEEPARG,VIRSORTER,PLASMIDFINDER,MOBSUITE pipeline
  class SANIC,ROUTES,REACT api
  class POSTGRES,VAULT_S storage
  class PROMETHEUS,GRAFANA,LOKI,PROMTAIL,ALERTMGR,NODE_EXP,PG_EXP,REDIS_EXP monitor
  class KAFKA,ZK,WEATHER_P,WEATHER_C stream
  class NGINX gateway
```

## Component Summary

| Layer | Components | Purpose |
|-------|-----------|---------|
| **Gateway** | Nginx (SSL, rate limiting) | Single entry point, security |
| **Frontend** | React 18 + Leaflet + Plotly | Pipeline UI, maps, results |
| **API** | Sanic (async Python) | REST API, JWT auth, routing |
| **Queue** | Redis 7 + RQ Worker | Async pipeline job execution |
| **Pipeline** | Nextflow DSL2 (24 processes) | Metagenomic analysis |
| **Lakehouse** | MinIO (Bronze → Silver → Gold) | Data lifecycle with lineage |
| **Database** | PostgreSQL 15 + PostGIS | Metadata, samples, lineage |
| **Streaming** | Kafka + Zookeeper | Weather data ingestion |
| **Secrets** | HashiCorp Vault | Credential management |
| **Observability** | Prometheus + Grafana + Loki | Metrics, dashboards, logs |

## Port Map

| Service | Port | Access |
|---------|------|--------|
| Nginx | 80, 443 | Public |
| React Frontend | 3000 | Via Nginx |
| Sanic Backend | 8000 | Via Nginx |
| PostgreSQL | 5432 | Internal |
| Redis | 6379 | Internal |
| MinIO API | 9000 | Internal |
| MinIO Console | 9001 | Admin |
| Kafka | 9092 | Internal |
| Kafka UI | 8080 | Admin |
| Prometheus | 9090 | Admin |
| Grafana | 3001 | Via Nginx |
| Vault | 8200 | Admin |
| pgAdmin | 5050 | Admin |
