# UPGRADE — Urban Pathogen Genomic Surveillance Network

A web platform for automated metagenomic analysis of Oxford Nanopore sequencing data:
QC → assembly → binning → MAG quality assessment → taxonomy → AMR detection.

---

## Requirements

| Tool | Version |
|------|---------|
| Docker | 24+ |
| Docker Compose | 2.20+ |
| Nextflow | 23+ |
| Java | 11+ (for Nextflow) |
| RAM | 16 GB minimum, 32 GB recommended |
| Disk | 50 GB free (per ~20 samples) |

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/bioinformatics-lab-utm/upgrade.git
cd upgrade

cp .env.example .env
```

Edit `.env` — replace every `change_me_*` value:

```bash
# Generate a strong JWT secret
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# Paste the output as JWT_SECRET in .env

# Set your absolute path to the repo root
UPGRADE_BASE_DIR=/absolute/path/to/upgrade
```

### 2. Start all services

```bash
docker compose up -d
```

This starts: PostgreSQL, Redis, MinIO, Kafka, backend (Sanic), frontend (React), RQ worker.

Wait ~30 seconds, then verify everything is healthy:

```bash
docker compose ps
curl http://localhost:8000/api/health
```

### 3. Run database migrations

```bash
docker exec -i upgrade_postgres psql -U upgrade -d upgrade_db \
  < database/migrations/001_initial_schema.sql
```

### 4. Create your first user

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "YourPassword123!",
    "full_name": "Your Name"
  }'
```

### 5. Open the dashboard

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| API | http://localhost:8000 |
| MinIO Console | http://localhost:9001 |
| pgAdmin | http://localhost:5050 |

---

## Running a Pipeline

### Option A — via the web UI

1. Log in at `http://localhost:3000`
2. Go to **Submit Sample**
3. Upload a `.fastq.gz` file from Oxford Nanopore
4. Click **Start Pipeline** — results appear in the dashboard when complete (~14 min per sample)

### Option B — batch submission (CLI)

```bash
# Dry run first
python3 scripts/batch/batch_submit_sra.py --count 5 --dry-run

# Submit 20 samples with 30s delay between jobs
python3 scripts/batch/batch_submit_sra.py --count 20 --delay 30
```

Edit `SRA_DIR`, `USERNAME`, and `PASSWORD` at the top of the script to match your setup.

---

## Architecture

```
Browser → Nginx → React frontend  (port 3000)
                → Sanic backend   (port 8000)
                       ↓
                 PostgreSQL  — metadata, results
                 Redis / RQ  — job queue
                 MinIO       — raw reads, results, artifacts
                       ↓
                 RQ Worker → Nextflow pipeline
```

**MinIO buckets:**
- `genomic-bronze` — raw uploaded reads
- `genomic-silver` — all pipeline outputs (trace, logs, summary JSON)
- `genomic-gold` — curated high-quality artifacts

**Pipeline modules:** NanoPlot → Filtlong → Flye → Medaka → MetaBat2 → CheckM2 → Kraken2 → Abricate (CARD)

---

## Nextflow Setup

The RQ worker runs Nextflow. Before submitting your first sample:

```bash
# Verify Nextflow is accessible inside the worker container
docker exec upgrade_rq_worker nextflow -version

# Pull all pipeline containers (first run only, ~10 min)
bash nextflow/pull_all_containers.sh
```

Make sure `UPGRADE_BASE_DIR` in `.env` is the absolute path to the repo root — Nextflow uses it to locate the pipeline scripts.

---

## Stopping / Resetting

```bash
# Stop services, keep data
docker compose down

# Full reset — deletes all volumes and data
docker compose down -v
```

---

## Troubleshooting

**Backend returns 500 on login**
The PostgreSQL password in `.env` was changed after the container started. Restart the backend:
```bash
docker compose up -d --no-deps web-backend
```

**Pipeline stays in `queued`**
Check the RQ worker logs:
```bash
docker logs upgrade_rq_worker --tail 50
```

**MinIO upload fails**
Buckets are created automatically on first run. If missing, create them manually at `http://localhost:9001` (`genomic-bronze`, `genomic-silver`, `genomic-gold`).

---

## License

[LICENSE](LICENSE)
