#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

params.input = null
params.outdir = './results'

workflow {
    if (!params.input) {
        error "Please specify input with --input"
    }
    
    log.info """
    UPGRADE Pipeline Test
    ====================
    input  : ${params.input}
    outdir : ${params.outdir}
    """
    
    Channel.fromPath(params.input)
        .view { "Processing: $it" }
}