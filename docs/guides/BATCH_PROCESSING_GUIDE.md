# Batch FASTQ Processing Guide

## Overview

This guide explains how to run all FASTQ files from the `data/` directory through the pipeline sequentially so they appear on the web platform.

## Available Scripts

### 1. **batch_run_all.sh** (Recommended - Simple & Reliable)

Direct Nextflow execution via command line. No dependencies on web platform.

**Features:**
- ✅ Direct Nextflow CLI execution
- ✅ No Python/API dependencies
- ✅ Sequential processing (one at a time)
- ✅ Automatic skip if results exist
- ✅ Colored output with progress tracking
- ✅ Resume support for interrupted runs

**Usage:**

```bash
# Dry run - see what will be processed
./batch_run_all.sh --dry-run

# Dry run with limit
./batch_run_all.sh --dry-run --limit 30

# Process first 5 samples
./batch_run_all.sh --limit 5

# Process all samples (166 found)
./batch_run_all.sh
```

**Output:**
- Results: `/results/<SAMPLE_CODE>/`
- Logs: `/results/<SAMPLE_CODE>/nextflow.log`
- Work: `/tmp/nextflow/work/<SAMPLE_CODE>/`

### 2. **batch_submit_fastq.py** (API-based)

Submits samples via web platform API. Requires web platform running.

**Features:**
- ✅ Uses web platform API
- ✅ Creates sample records in database
- ✅ Queues jobs via RQ workers
- ✅ Tracks status in web dashboard

**Requirements:**
```bash
pip install requests asyncpg
```

**Usage:**

```bash
# Make sure web platform is running
docker-compose up -d

# Dry run
python3 batch_submit_fastq.py --dry-run

# Submit with 5s wait between
python3 batch_submit_fastq.py --wait 5

# Submit and wait for each to complete
python3 batch_submit_fastq.py --wait-completion

# Custom API URL
python3 batch_submit_fastq.py --api-url http://biovm.local:8000
```

### 3. **batch_direct_runner.py** (Direct Database)

Bypasses API, directly creates database records and queues jobs.

**Features:**
- ✅ Direct database access
- ✅ Bypasses API layer
- ✅ Faster submission
- ✅ Requires Python dependencies

**Requirements:**
```bash
pip install asyncpg redis rq
```

**Usage:**

```bash
# Dry run
python3 batch_direct_runner.py --dry-run

# Process all
python3 batch_direct_runner.py

# Process first 10
python3 batch_direct_runner.py --limit 10
```

## Sample Discovery

The scripts automatically find FASTQ files in:
```
data/
├── SRR11836760/raw/SRR11836760.fastq
├── SRR11836777/raw/SRR11836777.fastq
├── SRR11836799/raw/SRR11836799.fastq
└── ...
```

**Pattern:** `data/<SAMPLE_CODE>/raw/<SAMPLE_CODE>.fastq[.gz]`

**Currently found:** 166 FASTQ files (172 total including duplicates)

## Pipeline Configuration

All scripts use the same pipeline parameters:

```
contig_min_length: 1500
metabat2_min_contig: 1500
concoct_min_contig: 1000
skip_bin_quality_filter: false
bin_filter_completeness: 20
bin_filter_contamination: 20
flye_genome_size: 50m
flye_meta: true
threads: 60
flye_mode: --nano-raw
run_medaka: true
```

## Results Structure

Each sample produces:
```
results/<SAMPLE_CODE>/
├── 00_summary/
│   ├── pipeline_summary.txt
│   └── quality_summary.json
├── 01_qc/
├── 02_assembly/
├── 03_binning/
├── 04_quality/
├── 05_dereplication/
├── 06_annotation/
├── 07_taxonomy/
├── 08_amr/
└── 09_plasmids/
```

## Web Platform Integration

### How Results Appear on Web Platform

1. **bash script**: Results in `/results/` are automatically picked up by web dashboard
2. **API scripts**: Creates database records, jobs show in pipeline monitoring

### Check Status

Via CLI:
```bash
# Check running pipelines
docker-compose exec backend python cli.py list-pipelines --status running

# Check completed
docker-compose exec backend python cli.py list-pipelines --status completed
```

Via API:
```bash
curl http://localhost:8000/api/v2/pipeline/runs?status=running
```

Via Web Dashboard:
```
http://localhost:3000/pipelines
```

## Monitoring Progress

### Real-time Monitoring

**Option 1: Watch directory**
```bash
watch -n 5 'find results/ -name "pipeline_summary.txt" | wc -l'
```

**Option 2: Check logs**
```bash
# Latest pipeline log
ls -ltr results/*/nextflow.log | tail -1

# Follow latest
tail -f $(ls -tr results/*/nextflow.log | tail -1)
```

**Option 3: Database query**
```bash
docker-compose exec postgres psql -U upgrade_user upgrade_db -c \
  "SELECT status, COUNT(*) FROM pipeline_runs GROUP BY status;"
```

## Estimated Timeline

With 166 samples:

| Mode | Time per Sample | Total Time |
|------|----------------|------------|
| Sequential | ~4-6 hours | ~664-996 hours (27-41 days) |
| Parallel (10x) | ~4-6 hours | ~66-99 hours (2.7-4.1 days) |

**Recommended:** Start with `--limit 5` to validate, then scale up.

## Troubleshooting

### Issue: "Pipeline already exists"
**Solution:** Skip existing samples (default behavior) or delete old runs:
```bash
docker-compose exec postgres psql -U upgrade_user upgrade_db -c \
  "DELETE FROM pipeline_runs WHERE sample_name = 'SRR11836760';"
```

### Issue: "Permission denied"
**Solution:**
```bash
chmod +x batch_run_all.sh
chmod +x batch_submit_fastq.py
chmod +x batch_direct_runner.py
```

### Issue: "Module not found"
**Solution:**
```bash
pip install asyncpg redis rq requests
```

### Issue: Script hangs
**Solution:** Pipeline takes 4-6 hours per sample. Use `--limit` for testing.

## Parallel Processing (Advanced)

To run multiple samples in parallel, use GNU Parallel:

```bash
# Generate sample list
find data -name "*.fastq" | grep -oP 'SRR\d+' | sort -u > samples.txt

# Run 10 at a time
cat samples.txt | parallel -j 10 \
  'nextflow run nextflow/main.nf \
    --input_dir data/{}/raw \
    --output_dir results/{} \
    --sample_name {} \
    -work-dir /tmp/nextflow/work/{} \
    -profile docker -resume'
```

**Warning:** Ensure sufficient resources (600 GB RAM, 600 CPU cores for 10 parallel).

## Best Practices

1. **Start small**: Test with `--limit 5` first
2. **Monitor resources**: Check disk space, RAM, CPU
3. **Use resume**: Nextflow `-resume` flag continues interrupted runs
4. **Check logs**: Always review `nextflow.log` for errors
5. **Backup results**: Copy completed results to safe storage
6. **Web platform**: Keep web platform running if using API scripts

## Summary

**Quick Start (Recommended):**

```bash
# 1. Test with dry run
./batch_run_all.sh --dry-run --limit 10

# 2. Run first 5 samples
./batch_run_all.sh --limit 5

# 3. Monitor progress
watch -n 30 'ls -ld results/SRR*/00_summary 2>/dev/null | wc -l'

# 4. After validation, run all
./batch_run_all.sh
```

**Expected Output:**
- 166 samples processed sequentially
- Each produces complete results in `/results/<SAMPLE_CODE>/`
- Automatically visible on web platform
- Total time: ~27-41 days for all samples sequentially

## Next Steps

After batch processing completes:
1. Verify results in web dashboard
2. Export summary statistics
3. Perform comparative analysis
4. Generate reports
