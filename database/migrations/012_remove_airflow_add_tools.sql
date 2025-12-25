-- Migration 010: Remove Airflow tables and add new bioinformatics tools
-- Remove unused Airflow orchestrator tables
-- Add support for: Abricate, DeepARG, Prokka, Nucmer, Assembly Stats, Bayesian Analysis

-- ==========================================
-- 1. DROP AIRFLOW TABLES (not used)
-- ==========================================

DROP TABLE IF EXISTS airflow_tasks CASCADE;
DROP TABLE IF EXISTS airflow_runs CASCADE;
DROP TABLE IF EXISTS airflow_dags CASCADE;

-- ==========================================
-- 2. AMR DETECTION TABLES (Abricate + DeepARG)
-- ==========================================

-- Abricate results (CARD, NCBI, ResFinder, ARG-ANNOT databases)
CREATE TABLE IF NOT EXISTS abricate_results (
    result_id SERIAL PRIMARY KEY,
    pipeline_id INT REFERENCES pipeline_runs(pipeline_id) ON DELETE CASCADE,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    
    -- Input details
    sequence_file VARCHAR(255),
    sequence_id VARCHAR(255), -- Contig/scaffold ID
    
    -- Match details
    start_pos INT,
    end_pos INT,
    strand VARCHAR(1), -- '+' or '-'
    gene_name VARCHAR(255),
    coverage DECIMAL(5,2), -- % coverage
    identity DECIMAL(5,2), -- % identity
    
    -- Database reference
    database_name VARCHAR(50), -- card, ncbi, resfinder, argannot
    accession VARCHAR(100),
    product TEXT, -- Gene product/description
    
    -- Resistance information
    resistance_class VARCHAR(255), -- beta-lactam, aminoglycoside, etc.
    resistance_mechanism TEXT,
    
    -- E-value and score
    evalue DECIMAL(10,8),
    bitscore DECIMAL(10,2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_abricate_pipeline ON abricate_results(pipeline_id);
CREATE INDEX idx_abricate_sample ON abricate_results(sample_id);
CREATE INDEX idx_abricate_gene ON abricate_results(gene_name);
CREATE INDEX idx_abricate_class ON abricate_results(resistance_class);

-- DeepARG results (ML-based AMR prediction)
CREATE TABLE IF NOT EXISTS deeparg_results (
    result_id SERIAL PRIMARY KEY,
    pipeline_id INT REFERENCES pipeline_runs(pipeline_id) ON DELETE CASCADE,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    
    -- Sequence details
    sequence_id VARCHAR(255),
    orf_id VARCHAR(255), -- Open reading frame ID
    
    -- Prediction details
    predicted_arg VARCHAR(255), -- Predicted ARG category
    probability DECIMAL(5,4), -- Prediction confidence (0-1)
    identity DECIMAL(5,2), -- % identity to reference
    
    -- ARG classification
    arg_category VARCHAR(255), -- beta-lactam, multidrug, etc.
    arg_mechanism TEXT,
    best_hit VARCHAR(255),
    best_hit_bitscore DECIMAL(10,2),
    best_hit_evalue DECIMAL(10,8),
    
    -- Model information
    model_version VARCHAR(50),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_deeparg_pipeline ON deeparg_results(pipeline_id);
CREATE INDEX idx_deeparg_sample ON deeparg_results(sample_id);
CREATE INDEX idx_deeparg_category ON deeparg_results(arg_category);

-- ==========================================
-- 3. FUNCTIONAL ANNOTATION (Prokka)
-- ==========================================

CREATE TABLE IF NOT EXISTS prokka_results (
    result_id SERIAL PRIMARY KEY,
    pipeline_id INT REFERENCES pipeline_runs(pipeline_id) ON DELETE CASCADE,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    bin_id INT REFERENCES assemblies(assembly_id),
    
    -- Sequence details
    sequence_id VARCHAR(255), -- Contig ID
    feature_type VARCHAR(50), -- CDS, rRNA, tRNA, tmRNA
    start_pos INT,
    end_pos INT,
    strand VARCHAR(1),
    
    -- Gene details
    locus_tag VARCHAR(255),
    gene_name VARCHAR(255),
    product TEXT,
    protein_id VARCHAR(255),
    translation TEXT, -- Amino acid sequence
    
    -- Annotation confidence
    inference TEXT, -- ab initio prediction, similarity
    ec_number VARCHAR(100), -- Enzyme commission number
    gene_ontology TEXT, -- GO terms (comma-separated)
    
    -- COG/KEGG annotation
    cog_category VARCHAR(10),
    kegg_id VARCHAR(50),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_prokka_pipeline ON prokka_results(pipeline_id);
CREATE INDEX idx_prokka_sample ON prokka_results(sample_id);
CREATE INDEX idx_prokka_feature ON prokka_results(feature_type);
CREATE INDEX idx_prokka_gene ON prokka_results(gene_name);

-- ==========================================
-- 4. HORIZONTAL GENE TRANSFER (Nucmer)
-- ==========================================

CREATE TABLE IF NOT EXISTS nucmer_results (
    result_id SERIAL PRIMARY KEY,
    pipeline_id INT REFERENCES pipeline_runs(pipeline_id) ON DELETE CASCADE,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    
    -- Reference and query sequences
    ref_sequence VARCHAR(255),
    query_sequence VARCHAR(255),
    
    -- Alignment details
    ref_start INT,
    ref_end INT,
    query_start INT,
    query_end INT,
    ref_align_len INT,
    query_align_len INT,
    
    -- Similarity metrics
    percent_identity DECIMAL(5,2),
    percent_similarity DECIMAL(5,2),
    
    -- Alignment statistics
    num_matches INT,
    num_mismatches INT,
    num_gaps INT,
    
    -- Potential HGT flag
    potential_hgt BOOLEAN DEFAULT false,
    hgt_confidence VARCHAR(20), -- high, medium, low
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nucmer_pipeline ON nucmer_results(pipeline_id);
CREATE INDEX idx_nucmer_sample ON nucmer_results(sample_id);
CREATE INDEX idx_nucmer_hgt ON nucmer_results(potential_hgt);

-- ==========================================
-- 5. ASSEMBLY STATISTICS
-- ==========================================

CREATE TABLE IF NOT EXISTS assembly_statistics (
    stat_id SERIAL PRIMARY KEY,
    pipeline_id INT REFERENCES pipeline_runs(pipeline_id) ON DELETE CASCADE,
    sample_id INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    assembly_id INT REFERENCES assemblies(assembly_id),
    
    -- Basic statistics
    total_length BIGINT,
    num_contigs INT,
    num_scaffolds INT,
    
    -- N-statistics
    n50 INT,
    n75 INT,
    n90 INT,
    l50 INT,
    l75 INT,
    l90 INT,
    
    -- Length statistics
    longest_contig INT,
    shortest_contig INT,
    mean_contig_length DECIMAL(10,2),
    median_contig_length INT,
    
    -- GC content
    gc_content DECIMAL(5,2),
    
    -- Quality metrics
    num_gaps INT,
    num_n_bases BIGINT,
    percent_n_bases DECIMAL(5,2),
    
    -- Coverage statistics
    mean_coverage DECIMAL(10,2),
    median_coverage DECIMAL(10,2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_assembly_stats_pipeline ON assembly_statistics(pipeline_id);
CREATE INDEX idx_assembly_stats_sample ON assembly_statistics(sample_id);

-- ==========================================
-- 6. COMPARATIVE GENOMICS
-- ==========================================

CREATE TABLE IF NOT EXISTS comparative_genomics (
    comparison_id SERIAL PRIMARY KEY,
    
    -- Samples being compared
    sample_id_1 INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    sample_id_2 INT REFERENCES samples(sample_id) ON DELETE CASCADE,
    
    -- Analysis details
    comparison_type VARCHAR(50), -- pairwise, multiple, pangenome
    tool_used VARCHAR(100), -- roary, panaroo, orthoagogue, etc.
    
    -- Results
    core_genes INT,
    accessory_genes INT,
    unique_genes_sample1 INT,
    unique_genes_sample2 INT,
    shared_genes INT,
    
    -- Pangenome statistics
    pangenome_size INT,
    core_genome_size INT,
    
    -- ANI (Average Nucleotide Identity)
    ani_score DECIMAL(5,2),
    ani_coverage DECIMAL(5,2),
    
    -- Results files
    results_path TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_comparative_sample1 ON comparative_genomics(sample_id_1);
CREATE INDEX idx_comparative_sample2 ON comparative_genomics(sample_id_2);

-- ==========================================
-- 7. BAYESIAN ANALYSIS (brms models)
-- ==========================================

CREATE TABLE IF NOT EXISTS bayesian_models (
    model_id SERIAL PRIMARY KEY,
    
    -- Model details
    model_name VARCHAR(255) NOT NULL,
    model_type VARCHAR(100), -- binomial, poisson, gaussian, etc.
    response_variable VARCHAR(255),
    predictor_variables TEXT, -- JSON array
    
    -- Model formula
    formula TEXT,
    
    -- Prior specifications
    priors TEXT, -- JSON
    
    -- MCMC settings
    chains INT DEFAULT 4,
    iterations INT DEFAULT 2000,
    warmup INT DEFAULT 1000,
    thin INT DEFAULT 1,
    
    -- Model fit statistics
    waic DECIMAL(10,4), -- Watanabe-Akaike Information Criterion
    loo DECIMAL(10,4), -- Leave-One-Out Cross-Validation
    r_squared DECIMAL(5,4),
    
    -- Convergence diagnostics
    rhat_max DECIMAL(5,4), -- Should be < 1.01
    ess_bulk_min INT, -- Effective sample size
    ess_tail_min INT,
    converged BOOLEAN,
    
    -- Results
    results_path TEXT, -- Path to RDS file with brmsfit object
    summary_statistics TEXT, -- JSON
    
    -- Metadata
    description TEXT,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_bayesian_model_name ON bayesian_models(model_name);
CREATE INDEX idx_bayesian_converged ON bayesian_models(converged);

-- Bayesian model predictions
CREATE TABLE IF NOT EXISTS bayesian_predictions (
    prediction_id SERIAL PRIMARY KEY,
    model_id INT REFERENCES bayesian_models(model_id) ON DELETE CASCADE,
    sample_id INT REFERENCES samples(sample_id),
    
    -- Prediction details
    predicted_value DECIMAL(10,4),
    lower_ci DECIMAL(10,4), -- 95% credible interval lower bound
    upper_ci DECIMAL(10,4), -- 95% credible interval upper bound
    
    -- Posterior distribution summary
    mean_estimate DECIMAL(10,4),
    median_estimate DECIMAL(10,4),
    sd_estimate DECIMAL(10,4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_bayesian_pred_model ON bayesian_predictions(model_id);
CREATE INDEX idx_bayesian_pred_sample ON bayesian_predictions(sample_id);

-- ==========================================
-- 8. UPDATE EXISTING TABLES
-- ==========================================

-- Add columns to pipeline_runs for new tools
ALTER TABLE pipeline_runs 
ADD COLUMN IF NOT EXISTS abricate_completed BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS deeparg_completed BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS prokka_completed BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS nucmer_completed BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS assembly_stats_completed BOOLEAN DEFAULT false;

-- Add comparative genomics tracking
ALTER TABLE samples
ADD COLUMN IF NOT EXISTS compared_with_samples INT[] DEFAULT ARRAY[]::INT[];

COMMENT ON TABLE abricate_results IS 'AMR gene detection using Abricate with multiple databases (CARD, NCBI, ResFinder)';
COMMENT ON TABLE deeparg_results IS 'ML-based AMR prediction using DeepARG';
COMMENT ON TABLE prokka_results IS 'Functional annotation results from Prokka';
COMMENT ON TABLE nucmer_results IS 'Whole genome alignment and HGT detection using Nucmer';
COMMENT ON TABLE assembly_statistics IS 'Comprehensive assembly quality metrics';
COMMENT ON TABLE comparative_genomics IS 'Comparative genomics analysis between samples';
COMMENT ON TABLE bayesian_models IS 'Bayesian statistical models using brms (R)';
COMMENT ON TABLE bayesian_predictions IS 'Predictions from fitted Bayesian models';
