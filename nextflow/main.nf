#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

// Print help message
if (params.help) {
    log.info """
    UPGRADE - Environmental Genomic Surveillance Pipeline
    ================================================
    
    Usage:
    nextflow run main.nf [options]
    
    Input options:
    --input_dir    Path to directory containing ONT FASTQ files (default: test_data/ont_data)
    --outdir       Output directory (default: results)
    
    QC options:
    --nanoplot_format                Format for NanoPlot outputs (default: png)
    
    Filtering options:
    --filtlong_min_length           Minimum read length in bp (default: 1000)
    --filtlong_keep_percent         Percentage of best reads to keep (default: 90)
    --filtlong_min_quality          Minimum mean quality score (default: 10)
    
    Assembly options:
    --flye_mode                     Sequencing technology (default: --nano-raw)
                                    Options: --nano-raw, --nano-hq, --nano-corr,
                                            --pacbio-raw, --pacbio-hifi, --pacbio-corr
    --flye_genome_size              Estimated genome size (default: 5m)
                                    Examples: 5m (5 megabases), 2.6g (2.6 gigabases)
    --flye_iterations               Number of polishing iterations (default: 1)
    --flye_meta                     Enable metagenome mode (default: false)
    
    Binning options:
    --metabat2_min_contig           Minimum contig length for MetaBAT2 (default: 2500)
    --metabat2_min_bin              Minimum bin size for MetaBAT2 (default: 200000)
    --concoct_min_contig            Minimum contig length for CONCOCT (default: 1000)
    --concoct_chunk_size            Chunk size for CONCOCT (default: 10000)
    --concoct_overlap_size          Overlap size for CONCOCT (default: 0)
    
    Quality assessment options:
    --checkm_extension              File extension for CheckM (default: fa)
    
    Taxonomic classification options:
    --kraken2_db                    Path to Kraken2 database (default: kraken2_db)
    
    Resource options:
    --threads      Number of threads (default: 30)
    --memory       Memory allocation (default: 8 GB)
    
    Other options:
    --help         Print this help message
    
    Examples:
    nextflow run main.nf -profile docker --input_dir data/ont_reads --filtlong_min_length 1500
    nextflow run main.nf -profile docker --flye_mode '--nano-hq' --flye_genome_size '10m'
    nextflow run main.nf -profile docker --flye_meta true  # For metagenome assembly
    nextflow run main.nf -profile docker --metabat2_min_contig 3000 --concoct_min_contig 1500
    """
    exit 0
}

// Print pipeline info
log.info """
    UPGRADE PIPELINE - Environmental Genomic Surveillance
    =====================================================
    input_dir              : ${params.input_dir}
    outdir                 : ${params.outdir}
    threads                : ${params.threads}
    
    Filtlong parameters:
    min_length             : ${params.filtlong_min_length} bp
    keep_percent           : ${params.filtlong_keep_percent}%
    min_quality            : ${params.filtlong_min_quality}
    
    Flye parameters:
    mode                   : ${params.flye_mode}
    genome_size            : ${params.flye_genome_size}
    iterations             : ${params.flye_iterations}
    meta_mode              : ${params.flye_meta}
    
    Binning parameters:
    MetaBAT2 min contig    : ${params.metabat2_min_contig ?: 2500} bp
    MetaBAT2 min bin       : ${params.metabat2_min_bin ?: 200000} bp
    CONCOCT min contig     : ${params.concoct_min_contig ?: 1000} bp
    CONCOCT chunk size     : ${params.concoct_chunk_size ?: 10000} bp
    
    CheckM extension       : ${params.checkm_extension ?: 'fa'}
    
    Kraken2 database       : ${params.kraken2_db ?: 'kraken2_db'}
"""

// Import modules
include { NANOPLOT } from './modules/nanoplot.nf'
include { FILTLONG } from './modules/filtlong.nf'
include { FLYE } from './modules/flye.nf'
include { METABAT2 } from './modules/metabat2.nf'
include { CONCOCT } from './modules/concoct.nf'
include { CHECKM } from './modules/checkm.nf'
include { CHECKM as CHECKM_METABAT2 } from './modules/checkm.nf'
include { CHECKM as CHECKM_CONCOCT } from './modules/checkm.nf'
include { KRAKEN2 } from './modules/kraken2.nf'
include { KRAKEN2 as KRAKEN2_METABAT2 } from './modules/kraken2.nf'
include { KRAKEN2 as KRAKEN2_CONCOCT } from './modules/kraken2.nf'

workflow {
    
    // Create input channel (search for FASTQ files in directory and subdirectories)
    ont_reads_ch = Channel
        .fromPath(["${params.input_dir}/*.fastq.gz", "${params.input_dir}/**/*.fastq.gz"])
        .map { file ->
            def sample_id = file.getBaseName().replaceAll(/\.fastq\.gz$/, '')
            println "Found ONT sample: ${sample_id} with file: ${file}"
            return [sample_id, file]
        }
    // Check if we have any input files
    ont_reads_ch.ifEmpty {
        error "No FASTQ files found in ${params.input_dir}. Please check the input directory."
    }
    
    // Stage 1: Quality Control with NanoPlot
    NANOPLOT(ont_reads_ch)
    
    // Stage 2: Read Filtering with Filtlong
    FILTLONG(ont_reads_ch)
    
    // Stage 3: De novo Assembly with Flye (using filtered reads)
    FLYE(FILTLONG.out.reads, params.flye_mode)
    
    // Stage 4: Genome Binning with MetaBAT2
    METABAT2(FLYE.out.fasta, FILTLONG.out.reads)
    
    // Stage 5: Genome Binning with CONCOCT
    CONCOCT(FLYE.out.fasta, FILTLONG.out.reads)
    
    // Stage 6: Quality Assessment with CheckM
    // Run CheckM on MetaBAT2 bins
    CHECKM_METABAT2(METABAT2.out.bins, "metabat2")
    
    // Run CheckM on CONCOCT bins  
    CHECKM_CONCOCT(CONCOCT.out.bins, "concoct")
    
    // Stage 7: Taxonomic Classification with Kraken2
    // Run Kraken2 on MetaBAT2 bins after CheckM
    KRAKEN2_METABAT2(METABAT2.out.bins, "metabat2")
    
    // Run Kraken2 on CONCOCT bins after CheckM
    KRAKEN2_CONCOCT(CONCOCT.out.bins, "concoct")
    
    // Print completion message
    // Print completion message
    // Print completion message
    // Print completion message
    workflow.onComplete {
        def success = workflow?.success ?: false
        def exitStatus = workflow?.exitStatus ?: 0
        def failed = workflow?.stats?.failedCount ?: 0
        def outdir = params?.outdir ?: 'results'
        
        // Считаем успешным если нет failed процессов
        if (failed == 0) {
            log.info """
            Pipeline completed successfully!
            
            Results structure:
            ${outdir}/
            ├── 01_QC/nanoplot/          # Quality control reports
            ├── 02_filtered/             # Filtered FASTQ files and logs
            ├── 03_assembly/             # Flye assembly results
            ├── 04_binning/metabat2/     # MetaBAT2 binning results
            ├── 04_binning/concoct/      # CONCOCT binning results
            ├── 05_quality/metabat2/     # CheckM quality assessment (MetaBAT2 bins)
            ├── 05_quality/concoct/      # CheckM quality assessment (CONCOCT bins)
            ├── 06_kraken2/metabat2/     # Kraken2 taxonomic classification (MetaBAT2 bins)
            └── 06_kraken2/concoct/      # Kraken2 taxonomic classification (CONCOCT bins)
            
            Assembly outputs:
            - ${outdir}/03_assembly/*.fasta.gz    # Final assembly
            - ${outdir}/03_assembly/*.gfa.gz      # Assembly graph
            - ${outdir}/03_assembly/*.info.txt    # Assembly statistics
            - ${outdir}/03_assembly/*.flye.log    # Assembly log
            
            Binning outputs:
            - ${outdir}/04_binning/metabat2/*_bins/    # MetaBAT2 bins
            - ${outdir}/04_binning/concoct/*_bins/     # CONCOCT bins
            
            Quality assessment outputs:
            - ${outdir}/05_quality/*/checkm_summary.tsv    # Bin quality summaries
            - ${outdir}/05_quality/*/checkm_results/       # Detailed CheckM results
            
            Taxonomic classification outputs:
            - ${outdir}/06_kraken2/*/metabat2_kraken2_summary.tsv    # MetaBAT2 bins taxonomy summary
            - ${outdir}/06_kraken2/*/concoct_kraken2_summary.tsv     # CONCOCT bins taxonomy summary
            - ${outdir}/06_kraken2/*/metabat2_kraken2_results/       # Detailed Kraken2 results (MetaBAT2)
            - ${outdir}/06_kraken2/*/concoct_kraken2_results/        # Detailed Kraken2 results (CONCOCT)
            
            Next steps:
            - Review QC reports in ${outdir}/01_QC/nanoplot/
            - Check filtering logs in ${outdir}/02_filtered/
            - Examine assembly statistics in ${outdir}/03_assembly/*.info.txt
            - Analyze bin quality in ${outdir}/05_quality/*/checkm_summary.tsv
            - Review taxonomic assignments in ${outdir}/06_kraken2/*_kraken2_summary.tsv
            - High-quality bins (>90% complete, <5% contamination) are ready for further analysis
            """
        } else {
            log.error "Pipeline failed. Check the error messages above."
        }
    }
}