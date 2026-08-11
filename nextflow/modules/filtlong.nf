process FILTLONG {
    tag "$sample_id"
    publishDir "${params.outdir}/02_filtered", mode: 'copy'
    
    container 'staphb/filtlong:0.2.1'
    
    input:
    tuple val(sample_id), path(reads)
    
    output:
    tuple val(sample_id), path("${sample_id}_filtered.fastq.gz"), emit: reads
    tuple val(sample_id), path("${sample_id}_bases.txt"), emit: bases
    path "${sample_id}_filtlong_log.txt", emit: log
    
    script:
    """
    # Create log file
    echo "Filtlong filtering for ${sample_id}" > ${sample_id}_filtlong_log.txt
    echo "Started: \$(date)" >> ${sample_id}_filtlong_log.txt
    echo "Input file: ${reads}" >> ${sample_id}_filtlong_log.txt
    echo "Threads: ${task.cpus}" >> ${sample_id}_filtlong_log.txt
    
    # Count input reads (handle both gzipped and uncompressed files)
    if [[ ${reads} == *.gz ]]; then
        if command -v pigz > /dev/null 2>&1; then
            input_reads=\$(pigz -dc ${reads} | wc -l | awk '{print \$1/4}')
        else
            input_reads=\$(zcat ${reads} | wc -l | awk '{print \$1/4}')
        fi
    else
        input_reads=\$(cat ${reads} | wc -l | awk '{print \$1/4}')
    fi
    echo "Input reads: \$input_reads" >> ${sample_id}_filtlong_log.txt
    
    # Run Filtlong with pigz (filtlong handles both gzipped and uncompressed input)
    filtlong \\
        --min_length ${params.filtlong_min_length} \\
        --keep_percent ${params.filtlong_keep_percent} \\
        --min_mean_q ${params.filtlong_min_quality} \\
        --verbose \\
        ${reads} | pigz -p ${task.cpus} > ${sample_id}_filtered.fastq.gz
    
    # Count output reads
    if command -v pigz > /dev/null 2>&1; then
        output_reads=\$(pigz -dc ${sample_id}_filtered.fastq.gz | wc -l | awk '{print \$1/4}')
    else
        output_reads=\$(zcat ${sample_id}_filtered.fastq.gz | wc -l | awk '{print \$1/4}')
    fi
    echo "Output reads: \$output_reads" >> ${sample_id}_filtlong_log.txt

    # Count output bases (used to estimate coverage before attempting assembly).
    # printf "%.0f" (not print) - awk's default OFMT (%.6g) switches large sums
    # to scientific notation (e.g. "4.46655e+09") once they exceed awk's native
    # integer range, which Groovy's .toLong() can't parse downstream.
    if command -v pigz > /dev/null 2>&1; then
        total_bases=\$(pigz -dc ${sample_id}_filtered.fastq.gz | awk 'BEGIN{b=0} NR%4==2{b+=length(\$0)} END{printf "%.0f", b}')
    else
        total_bases=\$(zcat ${sample_id}_filtered.fastq.gz | awk 'BEGIN{b=0} NR%4==2{b+=length(\$0)} END{printf "%.0f", b}')
    fi
    echo -n "\$total_bases" > ${sample_id}_bases.txt
    echo "Output bases: \$total_bases" >> ${sample_id}_filtlong_log.txt

    echo "Completed: \$(date)" >> ${sample_id}_filtlong_log.txt
    
    # Log final file size
    echo "Output file size: \$(du -sh ${sample_id}_filtered.fastq.gz | cut -f1)" >> ${sample_id}_filtlong_log.txt
    """
}