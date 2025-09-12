#!/usr/bin/env nextflow

nextflow.enable.dsl=2

// Print pipeline info
log.info """
    NANOPLOT QC PIPELINE
    ====================
    input_dir    : ${params.input_dir}
    outdir       : ${params.outdir}
    threads      : ${params.threads}
    """

// Import only NanoPlot module
include { NANOPLOT } from './modules/nanoplot.nf'

workflow {
    // ONT single-end reads
    reads_ch = Channel
        .fromPath("${params.input_dir}/*.fastq.gz", checkIfExists: true)
        .map { file -> [file.baseName.replaceAll(/\.fastq$/, ""), file] }
        .ifEmpty { error "No ONT FASTQ files found in ${params.input_dir}/" }
    
    // Print found ONT files
    reads_ch.view { sample_id, file -> 
        "Found ONT sample: $sample_id with file: $file" 
    }
    
    // Run NanoPlot for ONT QC
    NANOPLOT(reads_ch)
}

workflow.onComplete {
    log.info """
    Pipeline completed successfully!
    NanoPlot QC results available in: ${params.outdir}/01_QC/nanoplot/
    """
}