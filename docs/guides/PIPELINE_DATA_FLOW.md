# Complete Pipeline Data Flow

**Last Updated:** January 18, 2026  
**Pipeline Version:** v86  
**Average Runtime:** 7-8 minutes per sample

---

## Overview

This document describes the complete data flow from sample upload through pipeline execution to results visualization.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           UPGRADE Pipeline Flow                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [User] → [Frontend] → [Backend] → [MinIO] → [Nextflow] → [Results]         │
│                           ↓                       ↓                          │
│                      [PostgreSQL]            [16 Modules]                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Step 1: Sample Upload (Frontend → Backend)

1. User drags FASTQ file to `SampleUpload.tsx`
2. React uploads via `POST /api/pipeline/submit` with multipart/form-data
3. Backend receives file in `routes/pipeline.py`
4. Validates file:
   - Extension: `.fastq`, `.fq`, `.gz`
   - Size: < 10 GB
   - Format: Valid FASTQ structure
5. Generates unique sample ID: `SRR36492107_20260118_143022`

**Rate Limits:**
- 20 uploads per hour per IP
- 10 files maximum per request

---

## Step 2: Storage (Backend → MinIO)

1. `storage_service.upload()` connects to MinIO
2. Creates bucket if not exists: `upgrade-samples`
3. Uploads file to Bronze layer:
   ```
   s3://upgrade-samples/bronze/user_123/SRR36492107_20260118_143022.fastq.gz
   ```
4. Returns S3 path for database storage

**MinIO Bucket Structure:**
```
upgrade-samples/
├── bronze/          # Raw uploaded files
│   └── user_{id}/
├── silver/          # Processed/cleaned data
│   └── run_{id}/
└── gold/            # Analysis results
    └── run_{id}/
```

---

## Step 3: Database Record (Backend → PostgreSQL)

1. `sample_service.create()` inserts into `samples` table:
```sql
INSERT INTO samples (sample_name, user_id, s3_path, metadata, created_at)
VALUES ('SRR36492107', 123, 's3://...', '{"location": "Chisinau"}', NOW())
RETURNING sample_id;
```

2. Creates `pipeline_runs` record:
```sql
INSERT INTO pipeline_runs (sample_id, status, started_at)
VALUES (456, 'queued', NOW())
RETURNING run_id;
```

**Database Tables Involved:**
- `samples` - Sample metadata
- `pipeline_runs` - Pipeline execution tracking
- `pipeline_progress_events` - Real-time progress
- `minio_objects` - S3 object tracking

---

## Step 4: Pipeline Submission (Backend → Nextflow)

1. `pipeline_service.submit()` downloads FASTQ from MinIO to local disk:
   ```bash
   /tmp/upgrade/samples/SRR36492107_20260118_143022.fastq.gz
   ```

2. Launches Nextflow via Redis Queue (RQ):
   ```bash
   nextflow run nextflow/main.nf \
     --input /tmp/upgrade/samples/SRR36492107_20260118_143022.fastq.gz \
     --outdir results/run_789 \
     --sample_id SRR36492107 \
     -resume \
     -with-trace results/run_789/trace.txt \
     -with-report results/run_789/report.html
   ```

3. Updates database: `status = 'running'`

---

## Step 5: Pipeline Execution (Nextflow → 16 Modules)

### Module Execution Sequence

```
INPUT: SRR36492107.fastq.gz (2.1 GB, 500K reads)
```

### Stage 1: Quality Control & Preprocessing

| # | Module | Time | Description | Output |
|---|--------|------|-------------|--------|
| 1 | **NANOPLOT** | 30s | Generate QC plots: read length, quality scores | `01_QC/nanoplot_report.html` |
| 2 | **FILTLONG** | 45s | Filter low-quality reads (<Q7) and short reads (<500bp) | `02_filtered/SRR36492107_filtered.fastq.gz` |

### Stage 2: Assembly

| # | Module | Time | Description | Output |
|---|--------|------|-------------|--------|
| 3 | **FLYE** | 90s | De novo metagenomic assembly, 5 iterations | `03_assembly/assembly.fasta` |
| 4 | **ASSEMBLY_STATS** | 5s | Calculate N50, L50, GC content | `03_assembly/stats.txt` |
| 5 | **QUAST** | 20s | Assembly quality metrics | `03_assembly/quast_report.html` |

### Stage 3: Binning & Validation

| # | Module | Time | Description | Output |
|---|--------|------|-------------|--------|
| 6 | **METABAT2** | 60s | Genome binning using coverage + tetranucleotide frequency | `04_binning/bin.*.fa` |
| 7 | **BWA** | 30s | Map reads back to bins for per-bin coverage | `04_binning/bin.*.bam` |
| 8 | **CHECKM** | 240s | Assess bin quality (completeness, contamination) | `05_quality/checkm_results.txt` |

> ⚠️ **CHECKM is the bottleneck** - Takes ~4 minutes (55% of total time)

### Stage 4: Taxonomic Profiling

| # | Module | Time | Description | Output |
|---|--------|------|-------------|--------|
| 9 | **KRAKEN2** | 45s | Taxonomic classification of contigs | `06_taxonomy/kraken_report.txt` |
| 10 | **BRACKEN** | 15s | Abundance re-estimation at species level | `06_taxonomy/bracken_species.txt` |

### Stage 5: AMR Detection

| # | Module | Time | Description | Output |
|---|--------|------|-------------|--------|
| 11 | **ABRICATE** | 30s | AMR gene detection using CARD database | `07_amr/abricate_card.tsv` |
| 12 | **DEEPARG** | 90s | Deep learning AMR prediction | `07_amr/deeparg_predictions.tsv` |

### Stage 6: Functional Analysis

| # | Module | Time | Description | Output |
|---|--------|------|-------------|--------|
| 13 | **PROKKA** | 960s | Functional annotation (120s × 8 bins) | `08_annotation/bin.*.gff` |
| 14 | **NUCMER** | 45s | Horizontal gene transfer analysis | `08_annotation/hgt_candidates.txt` |

### Stage 7: Comparative Genomics

| # | Module | Time | Description | Output |
|---|--------|------|-------------|--------|
| 15 | **FASTANI** | 20s | Average nucleotide identity between bins | `09_comparative/ani_matrix.tsv` |
| 16 | **COMPARATIVE_GENOMICS** | 60s | Pangenome analysis (Roary/Panaroo), Orthology (OrthoFinder) | `09_comparative/pangenome.csv` |

### Timing Summary

```
TOTAL RUNTIME: 7m 45s

Breakdown:
├── QC & Preprocessing:   1m 15s (16%)
├── Assembly:             1m 55s (25%)
├── Binning & Validation: 5m 30s (71%) ← CHECKM dominates
├── Taxonomy:             1m 00s (13%)
├── AMR Detection:        2m 00s (26%)
├── Annotation:           16m 45s (parallel)
└── Comparative:          1m 20s (17%)
```

---

## Step 6: Results Storage (Nextflow → MinIO + PostgreSQL)

### MinIO Upload (automatic via `minio_helper.py`):

```bash
# Upload all result directories to Silver layer
upload_to_silver(run_id=789, local_path="results/run_789/")

# Curate to Gold layer (aggregated results)
curate_gold_layer(run_id=789)
```

### Final Structure in MinIO:

```
upgrade-results/
└── run_789/
    ├── 01_QC/
    │   └── nanoplot_report.html
    ├── 02_filtered/
    │   └── SRR36492107_filtered.fastq.gz
    ├── 03_assembly/
    │   ├── assembly.fasta
    │   ├── stats.txt
    │   └── quast_report.html
    ├── 04_binning/
    │   ├── bin.1.fa ... bin.12.fa
    │   └── bin.1.bam ... bin.12.bam
    ├── 05_quality/
    │   └── checkm_results.txt
    ├── 06_taxonomy/
    │   ├── kraken_report.txt
    │   └── bracken_species.txt
    ├── 07_amr/
    │   ├── abricate_card.tsv
    │   └── deeparg_predictions.tsv
    ├── 08_annotation/
    │   ├── bin.*.gff
    │   ├── bin.*.faa
    │   └── hgt_candidates.txt
    ├── 09_comparative/
    │   ├── ani_matrix.tsv
    │   └── pangenome.csv
    ├── trace.txt
    ├── report.html
    └── timeline.html
```

### Database Updates:

```sql
-- Update pipeline status
UPDATE pipeline_runs 
SET status = 'completed', 
    completed_at = NOW(),
    results_path = 's3://upgrade-results/run_789/'
WHERE run_id = 789;

-- Insert result summaries
INSERT INTO pipeline_results (run_id, result_type, data)
VALUES 
  (789, 'taxonomy', '{"species": [...], "genera": [...]}'),
  (789, 'amr', '{"genes": [...], "count": 23}'),
  (789, 'assembly', '{"contigs": 5432, "n50": 45000}');
```

---

## Step 7: Results Display (PostgreSQL + MinIO → Frontend)

### API Endpoints:

```
GET /api/pipeline/status/{run_id}     → Pipeline status, progress %
GET /api/results/{run_id}             → All results summary
GET /api/results/{run_id}/taxonomy    → Kraken2/Bracken results
GET /api/results/{run_id}/amr         → AMR gene list
GET /api/results/{run_id}/assembly    → Assembly statistics
GET /api/results/{run_id}/files       → List of downloadable files
GET /api/results/{run_id}/download/{file_path}  → Download specific file
```

### Frontend Components:

```
ResultsDashboard.tsx
├── PipelineStatus.tsx      → Progress bar, runtime
├── AssemblyStats.tsx       → N50, contigs, GC%
├── TaxonomyChart.tsx       → Krona plot, species table
├── AMRTable.tsx            → Resistance genes, antibiotics
├── BinQuality.tsx          → CheckM completeness chart
├── GeospatialMap.tsx       → Sample location on map
└── DownloadPanel.tsx       → Export results (CSV, JSON, PDF)
```

---

## Step 8: Cleanup (Automatic)

After successful completion:

1. **Local temp files deleted:**
   ```bash
   rm -rf /tmp/upgrade/samples/SRR36492107_*
   rm -rf results/run_789/work/  # Nextflow work directory
   ```

2. **Nextflow cache pruned** (configurable retention):
   ```bash
   nextflow clean -f -before 7d  # Remove runs older than 7 days
   ```

3. **MinIO lifecycle policy** (Bronze layer):
   ```json
   {
     "Rules": [{
       "ID": "DeleteOldBronze",
       "Status": "Enabled",
       "Filter": {"Prefix": "bronze/"},
       "Expiration": {"Days": 30}
     }]
   }
   ```

---

## Error Handling

### Pipeline Failures:

```sql
-- On failure, update status with error details
UPDATE pipeline_runs 
SET status = 'failed',
    error_message = 'CHECKM failed: insufficient memory',
    failed_at = NOW()
WHERE run_id = 789;
```

### Retry Logic:

```python
# In tasks.py
@job('pipeline-queue', timeout=43200, retry=Retry(max=3, interval=60))
def run_pipeline(run_id, sample_path, params):
    ...
```

### User Notifications:

- Email notification on completion/failure (if email verified)
- WebSocket updates for real-time progress (planned)

---

## Performance Optimization

### Current Bottlenecks:

| Module | Time | % of Total | Optimization |
|--------|------|------------|--------------|
| CHECKM | 4m | 55% | Switch to CheckM2 (2x faster) |
| PROKKA | 16m | - | Already parallelized per bin |
| DEEPARG | 90s | 12% | GPU acceleration (blocked) |

### Parallelization:

```nextflow
// In nextflow.config
process {
    withName: 'PROKKA' {
        cpus = 8
        memory = '16 GB'
    }
    withName: 'CHECKM' {
        cpus = 16
        memory = '32 GB'
    }
}

executor {
    name = 'local'
    cpus = 62
    memory = '120 GB'
}
```

---

## Monitoring

### Grafana Dashboards (planned):

- Pipeline throughput (samples/hour)
- Module execution times
- Error rates by module
- Storage utilization
- Queue depth

### Prometheus Metrics:

```
upgrade_pipeline_runs_total{status="completed"}
upgrade_pipeline_duration_seconds{module="CHECKM"}
upgrade_storage_bytes{layer="bronze|silver|gold"}
upgrade_queue_depth{queue="pipeline-queue"}
```

---

## Related Documentation

- [BATCH_PROCESSING_GUIDE.md](BATCH_PROCESSING_GUIDE.md) - Running multiple samples
- [TESTING_GUIDE.md](TESTING_GUIDE.md) - Pipeline testing
- [DEEPARG_BATCHING_GUIDE.md](DEEPARG_BATCHING_GUIDE.md) - DeepARG optimization
- [../reports/PERFORMANCE_BOTTLENECKS_REPORT.md](../reports/PERFORMANCE_BOTTLENECKS_REPORT.md) - Detailed performance analysis
