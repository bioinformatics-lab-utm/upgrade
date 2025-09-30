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
    --input_file_path  Path to single FASTQ file (local or s3://)
    --input_dir        Path to directory containing FASTQ files (default: test_data/ont_data)
    --sample_id        Sample identifier (auto-detected if not provided)
    --outdir           Output directory (default: results)
    
    QC options:
    --nanoplot_format  Format for NanoPlot outputs (default: png)
    
    Filtering options:
    --filtlong_min_length    Minimum read length in bp (default: 1000)
    --filtlong_keep_percent  Percentage of best reads to keep (default: 90)
    --filtlong_min_quality   Minimum mean quality score (default: 10)
    
    Resource options:
    --threads  Number of threads (default: 30)
    --memory   Memory allocation (default: 60.GB)
    
    Example:
    nextflow run main.nf -profile docker --input_dir test_data/ont_data
    nextflow run main.nf -profile docker --input_file_path s3://raw/sample.fastq.gz --sample_id sample1
    """
    exit 0
}

// Print pipeline info
log.info """
    UPGRADE PIPELINE - Environmental Genomic Surveillance
    =====================================================
    outdir                 : ${params.outdir}
    threads                : ${params.threads}
    
    Filtlong parameters:
    min_length             : ${params.filtlong_min_length} bp
    keep_percent           : ${params.filtlong_keep_percent}%
    min_quality            : ${params.filtlong_min_quality}
"""

// Import modules
include { NANOPLOT } from './modules/nanoplot.nf'
include { FILTLONG } from './modules/filtlong.nf'

workflow {
    
    // Determine input source
    if (params.input_file_path) {
        // Single file input (S3 or local)
        ont_reads_ch = Channel
            .fromPath(params.input_file_path)
            .map { file ->
                def sample_id = params.sample_id ?: file.getBaseName().replaceAll(/\.fastq(\.gz)?$/, '')
                return [sample_id, file]
            }
    } else if (params.input_dir) {
        // Directory input
        ont_reads_ch = Channel
            .fromPath("${params.input_dir}/*.fastq.gz")
            .map { file ->
                def sample_id = file.getBaseName().replaceAll(/\.fastq(\.gz)?$/, '')
                return [sample_id, file]
            }
    } else {
        error "Please specify either --input_file_path or --input_dir"
    }
    
    // Check if we have any input files
    ont_reads_ch.ifEmpty { 
        error "No FASTQ files found"
    }
    
    // Stage 1: Quality Control with NanoPlot
    NANOPLOT(ont_reads_ch)
    
    // Stage 2: Read Filtering with Filtlong
    FILTLONG(ont_reads_ch)
    
    // Print completion message
    // workflow.onComplete {
    //     if (workflow.stats.failedCount == 0) {
    //         log.info """
    //         Pipeline completed successfully!
    //         Results: ${params.outdir}
    //         """
    //     }
    // }

    // workflow.onComplete {
    // if (workflow.success) {  // Используйте workflow.success вместо проверки failedCount
    //     log.info """
    //     Pipeline completed successfully!
    //     Results: ${params.outdir}
    //     """
    // }
}