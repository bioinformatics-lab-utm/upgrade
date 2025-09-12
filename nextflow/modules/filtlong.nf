process FILTLONG {
    tag "$sample_id"
    publishDir "${params.outdir}/02_filtered", mode: 'copy'
    
    container 'staphb/filtlong:0.2.1'
    
    input:
    tuple val(sample_id), path(reads)
    
    output:
    tuple val(sample_id), path("${sample_id}_filtered.fastq.gz"), emit: reads
    path "${sample_id}_filtlong_log.txt", emit: log
    
    script:
    """
    # Create log file
    echo "Filtlong filtering for ${sample_id}" > ${sample_id}_filtlong_log.txt
    echo "Started: \$(date)" >> ${sample_id}_filtlong_log.txt
    echo "Input file: ${reads}" >> ${sample_id}_filtlong_log.txt
    echo "Threads: ${task.cpus}" >> ${sample_id}_filtlong_log.txt
    
    # Count input reads
    input_reads=\$(zcat ${reads} | wc -l | awk '{print \$1/4}')
    echo "Input reads: \$input_reads" >> ${sample_id}_filtlong_log.txt
    
    # Run Filtlong with pigz
    filtlong \\
        --min_length ${params.filtlong_min_length} \\
        --keep_percent ${params.filtlong_keep_percent} \\
        --min_mean_q ${params.filtlong_min_quality} \\
        --verbose \\
        ${reads} | pigz -p ${task.cpus} > ${sample_id}_filtered.fastq.gz
    
    # Count output reads
    output_reads=\$(zcat ${sample_id}_filtered.fastq.gz | wc -l | awk '{print \$1/4}')
    echo "Output reads: \$output_reads" >> ${sample_id}_filtlong_log.txt
    
    echo "Completed: \$(date)" >> ${sample_id}_filtlong_log.txt
    
    # Log final file size
    echo "Output file size: \$(du -sh ${sample_id}_filtered.fastq.gz | cut -f1)" >> ${sample_id}_filtlong_log.txt
    """
}