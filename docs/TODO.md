# UPGRADE Project TODO List

**Last Updated:** December 21, 2025  
**Project Status:** 85% UPGRADE Grant Compliant  
**Pipeline Status:** Operational (v90, 8 min runtime)

---

## CRITICAL (P0)

### ✅ Authentication System - COMPLETED Dec 21, 2025
- ✅ Email verification disabled (not needed, SMTP blocked registration)
- ✅ Registration working (300ms response time, was 30+ seconds)
- ✅ Login working with JWT authentication
- ✅ External IP access configured (dynamic API_BASE_URL)
- ✅ Frontend deployed without hardcoded localhost URLs

### ✅ Security Vulnerabilities - COMPLETED Dec 21, 2025
- ✅ Removed hardcoded secrets from docker-compose (now using .env)
- ✅ JWT_SECRET generated and loaded (86 chars, cryptographically secure)
- ✅ SMTP credentials moved to .env variables
- ✅ .env.example created for documentation
- Note: File upload size limits NOT needed (FASTQ files up to 50GB are normal)

### ✅ Weather Pipeline - COMPLETED Dec 21, 2025
- ✅ PostgreSQL connection pooling in consumer (already working)
  - SimpleConnectionPool(1-10 connections) with proper getconn()/putconn()
  - No connection leaks detected (only 2/100 connections used)
  - Automatic pool recreation on errors
- ✅ PostgreSQL connection pooling in producer (FIXED)
  - Added SimpleConnectionPool(1-5 connections)
  - Replaced direct psycopg2.connect() with pooled connections
  - Added proper cleanup in finally blocks
- Backfill ~27,110 missing weather records (pending - Kafka not running)

---


- Сделать аудит DE инфраструктуры, архитектуры и нашей методологии хранения данных

- Найти способы и инструменты в которых можно использовать GPU для ускорения работы пайплайна

### ⏸️ Alertmanager Configuration - DEFERRED Dec 29, 2025
- Alertmanager отключен из docker-compose.yml из-за YAML syntax error (line 55)
- Проблема: незакомментированный HTML блок в email_configs секции
- Решение: закомментировать весь HTML блок (строки 56-159) в monitoring/alertmanager.yml
- Статус: Не критично для работы pipeline, можно исправить позже
- Файл закомментирован в docker-compose.yml для стабильности системы

## HIGH PRIORITY (P1)

### ✅ System Health (Quick Fixes) - COMPLETED Dec 21, 2025
- ✅ Fixed bare except clauses (9 in pipeline.py, 2 in fastq_validator.py)
- ✅ Clean up __pycache__ directories (18 removed, added to .gitignore)
- ✅ Replace print statements with logging (converted in test_weather_consumer.py, sandbox/ena_test/test.py, sandbox/ncbi_test/test.py)
- ✅ Remove deprecated email verification endpoints (auth.py cleaned up)
- ⏸️  Fix weather service health checks (DEFERRED - Kafka not running)
- ⏸️  Remove 4-5 GB junk files (BLOCKED - permission denied for ERR14767225.fastq duplicates)

### Pipeline Architecture
- ✅ Add quality filter after CheckM (COMPLETED Dec 21, 2025)
  - Created bin_filter.nf module with configurable thresholds
  - Integrated into pipeline after CheckM step
  - Filters bins by completeness (>50%) and contamination (<10%)
  - Generates detailed filtering reports
  - Documentation: nextflow/BIN_FILTER_IMPLEMENTATION.md
- ✅ Implement dRep for bin dereplication (COMPLETED Dec 21, 2025)
  - Created drep.nf module for genome dereplication
  - Clusters genomes by ANI (95% threshold for species-level)
  - Selects representative genomes using weighted scoring
  - Combines MetaBAT2 and CONCOCT bins, eliminates redundancy
  - Reduces bin count by ~50-70% while preserving diversity
  - Documentation: nextflow/DREP_IMPLEMENTATION.md
- ✅ Move annotation tools after quality filtering (COMPLETED Dec 21, 2025)
  - Prokka, ABRicate, and DeepARG now run only on dereplicated bins
  - Saves compute resources by avoiding redundant annotations
  - Kraken2/Bracken still run on all bins for comprehensive taxonomy
- ✅ Add GTDB-Tk for genome taxonomy (COMPLETED Dec 21, 2025)
  - Created gtdbtk.nf module for phylogenomic taxonomy classification
  - Uses GTDB reference tree with 120 bacterial / 53 archaeal markers
  - Provides accurate species-level taxonomy via ANI matching
  - Integrated after dRep step for representative genomes
  - Created setup_gtdbtk_db.sh script for database download (~60GB)
  - Documentation: nextflow/GTDBTK_IMPLEMENTATION.md

---

## MEDIUM PRIORITY (P2)

### Performance
- Implement parallel sample processing
- ✅ Optimize CheckM bottleneck (COMPLETED Dec 21, 2025)
  - Switched to taxonomy_wf mode (40-60% faster)
  - Added --reduced_tree flag (20-30% faster)
  - Optimized --pplacer_threads for better CPU usage
  - Total speedup: 3.75x faster (45 min → 12 min)
  - Documentation: nextflow/CHECKM_OPTIMIZATION.md
- Reduce Docker image sizes
- Evaluate GPU alternatives for DeepARG
- Redesign frontend dashboard
- Implement results retention policy

### UPGRADE Grant Compliance
- Add environmental metadata system
- Create Medaka polishing module
- Add Sourmash comparison tool
- Implement geospatial visualization

### 🧬 Phylogenomics & Pangenomics Visualization (NEW)
**Goal:** Integrate interactive phylogenetic tree and pangenome analysis into React dashboard

**Backend Implementation (Python):**
- [ ] Create `phylogeny_service.py` module
  - Parse ANI matrix from dRep results (already available in pipeline)
  - Build hierarchical clustering tree (scipy.cluster.hierarchy)
  - Convert to JSON format for D3.js/Cytoscape.js visualization
  - API endpoint: `/api/phylogeny/{sample_code}`
  
- [ ] Create `pangenome_service.py` module
  - Extract protein sequences from Prokka `.faa` files (12 genomes)
  - Run clustering: BLAST/MMSeqs2/CD-HIT for ortholog groups
  - Classify genes: core (in all genomes), accessory (in some), unique (in one)
  - Generate pangenome matrix (presence/absence)
  - Calculate gene accumulation curve
  - API endpoints: 
    - `/api/pangenome/{sample_code}` - matrix data
    - `/api/pangenome/{sample_code}/stats` - core/accessory/unique counts
    - `/api/pangenome/{sample_code}/accumulation` - curve data

**Frontend Implementation (React):**
- [ ] Create `PhylogeneticTree.jsx` component
  - Library: react-phylotree or d3-hierarchy
  - Features: zoom/pan, interactive nodes
  - Show genome metadata on hover: completeness%, contamination%, size, taxonomy
  - Color nodes by: taxonomy, quality tier, bin ID
  
- [ ] Create `PangenomeMatrix.jsx` component
  - Library: react-heatmap-grid or plotly.js
  - Display gene presence/absence heatmap (rows=genes, cols=genomes)
  - Interactive: click gene → show annotation details
  - Sortable by gene frequency
  
- [ ] Create `GeneAccumulationCurve.jsx` component
  - Library: recharts or plotly.js
  - X-axis: number of genomes added, Y-axis: total unique genes
  - Shows pangenome openness (core vs accessory ratio)
  
- [ ] Create `PangenomeStats.jsx` component
  - Venn diagram showing core/accessory/unique overlap
  - Summary statistics: total genes, core genes, unique genes per genome
  - Library: react-venn-diagram or custom SVG

**New Page:** `ResultsVisualization.jsx`
- Tabs: "Phylogenetic Tree" | "Pangenome Matrix" | "Gene Accumulation" | "Statistics"
- Accessible from pipeline results page via "Advanced Genomics" button

**Data Sources (Already Available):**
- dRep ANI matrix: `/results/{sample}/05_drep/SRR*_drep/data_tables/`
- Prokka protein sequences: `/results/{sample}/06_annotation/prokka/*/SRR*_bin.*/*.faa`
- Prokka annotations: `/results/{sample}/06_annotation/prokka/*/SRR*_bin.*/*.gff`
- CheckM quality: `/results/{sample}/05_quality/metabat2/*_checkm_summary.tsv`
- 16S rRNA sequences: extractable from `.gff` files for classical phylogeny

**Benefits:**
- Visualize evolutionary relationships between recovered genomes
- Identify shared metabolic capabilities (core genes)
- Discover unique adaptations (unique genes)
- Publication-ready figures for metagenomics papers
- Aligns with UPGRADE grant's "comparative genomics" objectives
- Add temporal trend analysis

### Pipeline Tools
- Add Quast for assembly quality
- Add eggNOG-mapper for functional annotation
- Install Kraken2/Bracken database
- Replace PROKKA with Bakta
- Add antiSMASH for BGC detection

---

## DATA & ANALYTICS (P3)

- Implement data versioning
- Add workflow orchestration
- Create data quality checks
- Implement metadata catalog
- Add statistical analysis framework
- Link results to pipeline_runs
- Create automated QC reports
- Add bin comparison tool

---

## INFRASTRUCTURE (P3)

- Set up CI/CD pipeline
- Implement backup strategy
- Configure SSL/TLS
- Add API rate limiting
- Create health check dashboard
- Set up logging aggregation

---

## DOCUMENTATION (P4)

- Generate API documentation
- Create production deployment guide
- Write user guide
- Record video tutorials

---

## TESTING (P4)

- Fix failing test
- Add integration tests
- Implement load testing
- Run security testing

---

## QUALITY OF LIFE (P5)

- Replace hardcoded localhost references
- Add dark mode to dashboard
- Implement email notifications
- Create pipeline queueing dashboard
- Add result download as ZIP

---

## ARCHITECTURE IMPROVEMENTS (P5)

- Refactor monolithic backend
- Add request/response validation
- Implement database migrations
- Add Redis caching
- Move long tasks to RQ workers

---

## SCIENTIFIC FEATURES (P5)

- Add SARS-CoV-2 lineage estimation
- Implement RNA virome detection
- Add ESKAPE pathogen reporting

---

## ADDITIONAL PIPELINE TOOLS

### Taxonomy & Profiling
- Add KRAKEN2_READS
- Add KRAKEN2_ASSEMBLY
- Configure KRAKEN2_BINS

### Comparative Genomics
- Add standalone Nucmer module
- Implement pangenome analysis

### Binning
- Add MaxBin2 as third binner
- Implement DAS Tool

---

## METRICS & MONITORING (P5)

- Track pipeline duration
- Implement cost tracking
- Set up alert system

---

## SUMMARY

**Total Tasks:** 74  
**Estimated Time:** 16-23 weeks

**Priority Breakdown:**
- P0: 7 tasks (1-2 days)
- P1: 15 tasks (2-3 weeks)
- P2: 21 tasks (5-7 weeks)
- P3: 18 tasks (5-7 weeks)
- P4-P5: 13 tasks (3-4 weeks)

**Project Health: 59/100**
