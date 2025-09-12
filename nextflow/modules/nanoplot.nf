process NANOPLOT {
    tag "$sample_id"
    
    input:
    tuple val(sample_id), path(reads)
    
    output:
    path "${sample_id}_nanoplot/"
    path "${sample_id}_nanoplot/*.html"
    path "${sample_id}_nanoplot/*.png"
    
    script:
    """
    mkdir -p ${sample_id}_nanoplot
    
    NanoPlot \\
        --fastq ${reads} \\
        --outdir ${sample_id}_nanoplot \\
        --prefix ${sample_id}_ \\
        --threads ${task.cpus} \\
        --plots dot kde \\
        --format png
    """
}