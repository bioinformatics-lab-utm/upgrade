-- Migration 002: Analysis Results & Processing
-- UPGRADE Project - Sequencing, Processing, and Bioinformatics Analysis Results
-- Version: 1.0.0

-- =========================
-- Sequencing & Processing Tables
-- =========================

CREATE TABLE IF NOT EXISTS sequencing_runs (
    run_id SERIAL PRIMARY KEY,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    
    -- Sequencing details
    platform VARCHAR(100) NOT NULL, -- MinION, GridION, PromethION
    flowcell_id VARCHAR(100),
    flowcell_type VARCHAR(50), -- R9.4.1, R10.4.1, R10.5
    sequencing_kit VARCHAR(100), -- SQK-LSK109, SQK-RBK004, SQK-LSK114
    run_date DATE NOT NULL,
    run_start_time TIMESTAMP,
    run_end_time TIMESTAMP,
    
    -- Data paths (temporary until MinIO integration in 003)
    fast5_path VARCHAR(255),
    fastq_path VARCHAR(255),
    summary_file_path VARCHAR(255),
    
    -- Run statistics
    total_reads BIGINT,
    passed_reads BIGINT,
    failed_reads BIGINT,
    avg_read_length INTEGER,
    median_read_length INTEGER,
    n50_read_length INTEGER,
    total_bases_passed BIGINT,
    
    -- Quality metrics
    avg_quality_score DECIMAL(5,2),
    median_quality_score DECIMAL(5,2),
    gc_content DECIMAL(5,2),
    
    -- Technical details
    basecalling_model VARCHAR(100), -- dna_r9.4.1_e8_hac, dna_r10.4.1_e8.2_400bps_hac
    basecalling_version VARCHAR(50),
    real_time_analysis BOOLEAN DEFAULT false,
    
    -- Status and quality
    status VARCHAR(50) DEFAULT 'running', -- running, completed, failed, stopped
    quality_passed BOOLEAN,
    notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    pipeline_id SERIAL PRIMARY KEY,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    sequencing_run_id INT REFERENCES sequencing_runs(run_id),
    
    -- Pipeline details
    pipeline_name VARCHAR(150) NOT NULL, -- "UPGRADE-AMR-Pipeline", "Pathogen-Detection-Pipeline"
    pipeline_version VARCHAR(50),
    software_name VARCHAR(150), -- "Flye+Medaka", "Kraken2+Bracken", "Abricate"
    software_version VARCHAR(50),
    
    -- Analysis parameters
    parameters TEXT, -- JSON string with all parameters
    reference_database VARCHAR(150), -- CARD, VFDB, RefSeq
    reference_db_version VARCHAR(100),
    
    -- Computational resources
    cpu_cores INTEGER,
    memory_gb INTEGER,
    runtime_minutes INTEGER,
    
    -- Results (paths will be updated to MinIO in migration 003)
    results_path VARCHAR(255),
    log_file_path VARCHAR(255),
    
    -- Status
    status VARCHAR(50) DEFAULT 'queued', -- queued, running, completed, failed, cancelled
    exit_code INTEGER,
    error_message TEXT,
    
    -- Timing
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id SERIAL PRIMARY KEY,
    sample_id INT REFERENCES samples(sample_id),
    pipeline_run_id INT REFERENCES pipeline_runs(pipeline_id),
    
    -- Job details
    job_type VARCHAR(100) NOT NULL, -- assembly, annotation, classification, resistance_detection
    job_name VARCHAR(200),
    command_line TEXT,
    working_directory VARCHAR(255),
    
    -- Resource usage
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    runtime_seconds INTEGER,
    cpu_usage DECIMAL(6,2), -- percentage
    memory_usage DECIMAL(10,2), -- MB
    memory_peak DECIMAL(10,2), -- MB peak usage
    disk_io DECIMAL(10,2), -- MB
    
    -- Status and results
    status VARCHAR(50) NOT NULL, -- pending, running, completed, failed, killed
    exit_code INTEGER,
    stdout_path VARCHAR(255),
    stderr_path VARCHAR(255),
    error_log TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- Quality Control Results
-- =========================

CREATE TABLE IF NOT EXISTS quality_control_results (
    qc_id SERIAL PRIMARY KEY,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    sequencing_run_id INT REFERENCES sequencing_runs(run_id),
    
    -- Read statistics
    total_reads BIGINT NOT NULL,
    passed_reads BIGINT NOT NULL,
    failed_reads BIGINT NOT NULL,
    pass_rate DECIMAL(5,2), -- percentage
    
    -- Quality scores
    mean_quality_score DECIMAL(5,2),
    median_quality_score DECIMAL(5,2),
    q25_quality_score DECIMAL(5,2),
    q75_quality_score DECIMAL(5,2),
    
    -- Read length statistics
    mean_read_length INTEGER,
    median_read_length INTEGER,
    n50_read_length INTEGER,
    min_read_length INTEGER,
    max_read_length INTEGER,
    
    -- Sequence composition
    gc_content DECIMAL(5,2),
    at_content DECIMAL(5,2),
    n_content DECIMAL(5,2), -- undefined nucleotides
    
    -- Contamination and quality flags
    contamination_rate DECIMAL(5,2),
    human_contamination_rate DECIMAL(5,2),
    adapter_contamination_rate DECIMAL(5,2),
    
    -- Quality assessment
    is_passed BOOLEAN NOT NULL,
    failure_reasons TEXT[], -- array of failure reasons
    
    -- QC tool information
    qc_tool VARCHAR(100), -- NanoPlot, FastQC, MultiQC
    qc_version VARCHAR(50),
    qc_report_path VARCHAR(255), -- Will be updated to MinIO in migration 003
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- Reference Databases
-- =========================

CREATE TABLE IF NOT EXISTS databases_reference (
    database_id SERIAL PRIMARY KEY,
    database_name VARCHAR(150) NOT NULL,
    version VARCHAR(50),
    description TEXT,
    source_url VARCHAR(255),
    database_type VARCHAR(100), -- ARG, virulence, taxonomy, genome, plasmid
    last_updated DATE,
    download_date DATE,
    file_path VARCHAR(255), -- Will be updated to MinIO in migration 003
    checksum VARCHAR(100), -- MD5 or SHA256
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- Bioinformatics Analysis Results
-- =========================

CREATE TABLE IF NOT EXISTS detected_organisms (
    detection_id SERIAL PRIMARY KEY,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    pipeline_run_id INT REFERENCES pipeline_runs(pipeline_id),
    
    -- Organism identification
    organism_name VARCHAR(200) NOT NULL,
    scientific_name VARCHAR(200),
    taxonomy_id VARCHAR(50), -- NCBI Taxonomy ID
    taxonomy_rank VARCHAR(50), -- species, genus, family, etc.
    
    -- Classification details
    classification_tool VARCHAR(100), -- Kraken2, Centrifuge, Minimap2
    database_id INT REFERENCES databases_reference(database_id),
    
    -- Abundance and confidence
    read_count INTEGER,
    abundance DECIMAL(10,6), -- relative abundance
    abundance_rpm DECIMAL(10,2), -- reads per million
    confidence_score DECIMAL(5,2),
    
    -- Sequence similarity
    coverage DECIMAL(10,2), -- percentage coverage
    identity DECIMAL(5,2), -- percentage identity
    alignment_length INTEGER,
    
    -- Additional metrics
    unique_reads INTEGER, -- reads uniquely assigned to this organism
    shared_reads INTEGER, -- reads shared with other organisms
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resistance_genes (
    rg_id SERIAL PRIMARY KEY,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    pipeline_run_id INT REFERENCES pipeline_runs(pipeline_id),
    
    -- Gene identification
    gene_name VARCHAR(200) NOT NULL,
    gene_symbol VARCHAR(50),
    accession VARCHAR(100), -- GenBank/RefSeq accession
    gene_family_id INT REFERENCES gene_families(gene_family_id),
    
    -- Detection details
    detection_tool VARCHAR(100), -- Abricate, RGI, AMRFinderPlus
    database_id INT REFERENCES databases_reference(database_id),
    
    -- Sequence alignment
    coverage DECIMAL(10,2) NOT NULL,
    identity DECIMAL(5,2) NOT NULL,
    alignment_length INTEGER,
    gene_length INTEGER,
    query_start INTEGER,
    query_end INTEGER,
    subject_start INTEGER,
    subject_end INTEGER,
    
    -- Expression and context
    read_count INTEGER,
    depth_coverage DECIMAL(8,2), -- sequencing depth at gene location
    surrounding_context TEXT, -- genetic context around the gene
    
    -- Resistance prediction
    predicted_resistance TEXT[], -- array of antibiotics
    resistance_mechanism VARCHAR(200),
    
    -- Quality and confidence
    confidence_level VARCHAR(50), -- high, medium, low
    quality_score DECIMAL(5,2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS virulence_factors (
    vf_id SERIAL PRIMARY KEY,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    pipeline_run_id INT REFERENCES pipeline_runs(pipeline_id),
    
    -- Virulence factor identification
    gene_name VARCHAR(200) NOT NULL,
    gene_symbol VARCHAR(50),
    accession VARCHAR(100),
    vf_category VARCHAR(150), -- adhesin, toxin, invasion, immune_evasion
    
    -- Detection details
    detection_tool VARCHAR(100), -- VFDB, VirulenceFinder
    database_id INT REFERENCES databases_reference(database_id),
    
    -- Sequence alignment
    coverage DECIMAL(10,2) NOT NULL,
    identity DECIMAL(5,2) NOT NULL,
    alignment_length INTEGER,
    
    -- Functional annotation
    function_description TEXT,
    pathogenicity_role TEXT,
    host_interaction VARCHAR(200),
    
    -- Clinical relevance
    clinical_significance VARCHAR(100), -- high, medium, low, unknown
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- Gene-Antibiotic Associations
-- =========================

CREATE TABLE IF NOT EXISTS gene_antibiotic_associations (
    association_id SERIAL PRIMARY KEY,
    resistance_gene_id INT REFERENCES resistance_genes(rg_id) ON DELETE CASCADE,
    antibiotic_id INT REFERENCES antibiotic_reference(antibiotic_id),
    
    -- Association details
    resistance_type VARCHAR(100), -- intrinsic, acquired, adaptive
    effectiveness DECIMAL(5,2), -- MIC fold-change or effectiveness score
    clinical_relevance VARCHAR(100), -- confirmed, predicted, experimental
    
    -- Supporting evidence
    literature_pmid VARCHAR(20), -- PubMed ID
    experimental_evidence TEXT,
    computational_prediction TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- Assembly and Annotation Results
-- =========================

CREATE TABLE IF NOT EXISTS assemblies (
    assembly_id SERIAL PRIMARY KEY,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    pipeline_run_id INT REFERENCES pipeline_runs(pipeline_id),
    
    -- Assembly details
    assembler VARCHAR(100), -- Flye, Canu, Unicycler
    assembler_version VARCHAR(50),
    assembly_type VARCHAR(50), -- metagenomic, isolate, plasmid
    
    -- Assembly statistics
    total_contigs INTEGER,
    total_length BIGINT,
    n50_contig INTEGER,
    n90_contig INTEGER,
    longest_contig INTEGER,
    gc_content DECIMAL(5,2),
    
    -- Quality metrics
    assembly_score DECIMAL(5,2),
    completeness DECIMAL(5,2), -- based on BUSCO or similar
    contamination DECIMAL(5,2),
    
    -- File paths (will be updated to MinIO in migration 003)
    assembly_fasta_path VARCHAR(255),
    assembly_graph_path VARCHAR(255),
    assembly_info_path VARCHAR(255),
    
    -- Quality assessment
    quality_grade VARCHAR(20), -- excellent, good, fair, poor
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS functional_annotations (
    annotation_id SERIAL PRIMARY KEY,
    assembly_id INT REFERENCES assemblies(assembly_id) ON DELETE CASCADE,
    pipeline_run_id INT REFERENCES pipeline_runs(pipeline_id),
    
    -- Annotation details
    annotator VARCHAR(100), -- Prokka, RAST, DFAST
    annotator_version VARCHAR(50),
    annotation_type VARCHAR(50), -- functional, structural, comparative
    
    -- Annotation statistics
    total_genes INTEGER,
    coding_sequences INTEGER,
    rrna_genes INTEGER,
    trna_genes INTEGER,
    hypothetical_proteins INTEGER,
    
    -- Functional categories
    cog_categories JSONB, -- COG functional categories
    go_terms JSONB, -- Gene Ontology terms
    ec_numbers JSONB, -- Enzyme Commission numbers
    kegg_pathways JSONB, -- KEGG pathway annotations
    
    -- File paths (will be updated to MinIO in migration 003)
    annotation_gff_path VARCHAR(255),
    annotation_faa_path VARCHAR(255),
    annotation_gbk_path VARCHAR(255),
    annotation_tsv_path VARCHAR(255),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- External Data Integration
-- =========================

CREATE TABLE IF NOT EXISTS external_links (
    link_id SERIAL PRIMARY KEY,
    sample_id INT REFERENCES samples(sample_id),
    sequencing_run_id INT REFERENCES sequencing_runs(run_id),
    assembly_id INT REFERENCES assemblies(assembly_id),
    
    -- Repository details
    repository VARCHAR(100), -- ENA, SRA, GEO, NCBI, EMBL
    accession_number VARCHAR(100) NOT NULL,
    submission_id VARCHAR(100),
    
    -- Data details
    data_type VARCHAR(100), -- raw_reads, assembly, annotation, metadata
    url VARCHAR(255),
    embargo_date DATE, -- when data becomes public
    
    -- Submission tracking
    submission_date DATE,
    release_date DATE,
    submission_status VARCHAR(50), -- submitted, processing, public, private
    submitted_by INT REFERENCES researchers(researcher_id),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- Placeholder for NextFlow Integration (will be linked in migration 003)
-- =========================

-- These columns will be added in migration 003 when NextFlow tables are created:
-- ALTER TABLE pipeline_runs ADD COLUMN nextflow_execution_id INT;
-- ALTER TABLE quality_control_results ADD COLUMN nextflow_process_id INT;
-- ALTER TABLE detected_organisms ADD COLUMN nextflow_process_id INT;
-- ALTER TABLE resistance_genes ADD COLUMN nextflow_process_id INT;
-- ALTER TABLE virulence_factors ADD COLUMN nextflow_process_id INT;

-- =========================
-- Update Migration Record
-- =========================

INSERT INTO schema_migrations (version, description) VALUES 
(2, 'Analysis results and bioinformatics processing pipeline results');

-- =========================
-- Indexes for Performance
-- =========================

-- Sequencing runs
CREATE INDEX idx_sequencing_runs_sample ON sequencing_runs (sample_id);
CREATE INDEX idx_sequencing_runs_date ON sequencing_runs (run_date DESC);
CREATE INDEX idx_sequencing_runs_platform ON sequencing_runs (platform);
CREATE INDEX idx_sequencing_runs_status ON sequencing_runs (status);

-- Pipeline runs
CREATE INDEX idx_pipeline_runs_sample ON pipeline_runs (sample_id);
CREATE INDEX idx_pipeline_runs_sequencing_run ON pipeline_runs (sequencing_run_id);
CREATE INDEX idx_pipeline_runs_status ON pipeline_runs (status);
CREATE INDEX idx_pipeline_runs_started ON pipeline_runs (started_at DESC);

-- Quality control
CREATE INDEX idx_qc_sample ON quality_control_results (sample_id);
CREATE INDEX idx_qc_sequencing_run ON quality_control_results (sequencing_run_id);
CREATE INDEX idx_qc_passed ON quality_control_results (is_passed);

-- Analysis results
CREATE INDEX idx_detected_organisms_sample ON detected_organisms (sample_id);
CREATE INDEX idx_detected_organisms_pipeline ON detected_organisms (pipeline_run_id);
CREATE INDEX idx_detected_organisms_name ON detected_organisms (organism_name);
CREATE INDEX idx_detected_organisms_abundance ON detected_organisms (abundance DESC);

CREATE INDEX idx_resistance_genes_sample ON resistance_genes (sample_id);
CREATE INDEX idx_resistance_genes_pipeline ON resistance_genes (pipeline_run_id);
CREATE INDEX idx_resistance_genes_name ON resistance_genes (gene_name);
CREATE INDEX idx_resistance_genes_family ON resistance_genes (gene_family_id);
CREATE INDEX idx_resistance_genes_coverage ON resistance_genes (coverage DESC, identity DESC);

CREATE INDEX idx_virulence_factors_sample ON virulence_factors (sample_id);
CREATE INDEX idx_virulence_factors_pipeline ON virulence_factors (pipeline_run_id);
CREATE INDEX idx_virulence_factors_category ON virulence_factors (vf_category);

-- Assemblies and annotations
CREATE INDEX idx_assemblies_sample ON assemblies (sample_id);
CREATE INDEX idx_assemblies_pipeline ON assemblies (pipeline_run_id);
CREATE INDEX idx_assemblies_quality ON assemblies (quality_grade);

CREATE INDEX idx_functional_annotations_assembly ON functional_annotations (assembly_id);
CREATE INDEX idx_functional_annotations_pipeline ON functional_annotations (pipeline_run_id);

-- External links
CREATE INDEX idx_external_links_sample ON external_links (sample_id);
CREATE INDEX idx_external_links_repository ON external_links (repository, accession_number);
CREATE INDEX idx_external_links_status ON external_links (submission_status);

-- Associations
CREATE INDEX idx_gene_antibiotic_assoc_gene ON gene_antibiotic_associations (resistance_gene_id);
CREATE INDEX idx_gene_antibiotic_assoc_antibiotic ON gene_antibiotic_associations (antibiotic_id);

-- =========================
-- Comments for Documentation
-- =========================

COMMENT ON TABLE sequencing_runs IS 'Oxford Nanopore sequencing run details and statistics';
COMMENT ON TABLE pipeline_runs IS 'Bioinformatics pipeline executions for sample analysis';
COMMENT ON TABLE quality_control_results IS 'Quality control metrics for sequencing data';
COMMENT ON TABLE detected_organisms IS 'Organisms detected through metagenomic analysis';
COMMENT ON TABLE resistance_genes IS 'Antimicrobial resistance genes identified in samples (CORE UPGRADE FOCUS)';
COMMENT ON TABLE virulence_factors IS 'Virulence factors detected in pathogenic organisms';
COMMENT ON TABLE assemblies IS 'Genome/metagenome assembly results and statistics';
COMMENT ON TABLE functional_annotations IS 'Functional annotation results from assembled genomes';
COMMENT ON TABLE external_links IS 'Links to external databases and repositories';
COMMENT ON TABLE gene_antibiotic_associations IS 'Resistance gene to antibiotic associations';