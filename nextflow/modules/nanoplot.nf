process NANOPLOT {
    tag "$sample_id"
    publishDir "${params.outdir}/01_QC/nanoplot", mode: 'copy'

    input:
    tuple val(sample_id), path(reads)

    output:
    path "${sample_id}_nanoplot", emit: report
    
    script:
    """
    echo "[NanoPlot] Starting analysis for ${sample_id}"
    echo "[NanoPlot] Input file: ${reads}"
    echo "[NanoPlot] File size: \$(du -h ${reads} | cut -f1)"
    echo "[NanoPlot] Timestamp: \$(date)"
    
    mkdir -p ${sample_id}_nanoplot
    
    NanoPlot \
        --fastq ${reads} \
        --outdir ${sample_id}_nanoplot \
        --prefix ${sample_id}_ \
        --threads ${task.cpus} \
        --plots dot kde \
        --format png
    
    echo "[NanoPlot] Completed for ${sample_id} at \$(date)"
    """
}

// process NANOPLOT {
//     tag "$sample_id"
    
//     input:
//     tuple val(sample_id), path(reads)
    
//     output:
//     path "${sample_id}_nanoplot/"
//     path "${sample_id}_nanoplot/*.html"
//     path "${sample_id}_nanoplot/*.png"
    
//     script:
//     """
//     mkdir -p ${sample_id}_nanoplot
    
//     NanoPlot \\
//         --fastq ${reads} \\
//         --outdir ${sample_id}_nanoplot \\
//         --prefix ${sample_id}_ \\
//         --threads ${task.cpus} \\
//         --plots dot kde \\
//         --format png
//     """
// }