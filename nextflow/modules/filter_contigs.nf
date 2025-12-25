process FILTER_CONTIGS {
    tag "$sample_id"
    label 'process_low'
    
    container 'quay.io/biocontainers/seqkit:2.12.0--he881be0_1'
    
    publishDir "${params.outdir}/03_assembly/filtered", mode: 'copy', pattern: "*_filter_stats.txt"

    input:
    tuple val(sample_id), path(assembly)

    output:
    tuple val(sample_id), path("${sample_id}_filtered.fasta.gz"), emit: filtered_assembly
    tuple val(sample_id), path("${sample_id}_filter_stats.txt"), emit: stats
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def min_length = params.contig_min_length ?: 1000
    
    """
    echo "Filtering contigs for ${sample_id}" | tee ${sample_id}_filter_stats.txt
    echo "" | tee -a ${sample_id}_filter_stats.txt
    echo "=== Input Assembly Stats ===" | tee -a ${sample_id}_filter_stats.txt
    seqkit stats ${assembly} | tee -a ${sample_id}_filter_stats.txt
    echo "" | tee -a ${sample_id}_filter_stats.txt

    # Filter contigs by minimum length
    echo "Filtering contigs with length >= ${min_length} bp..." | tee -a ${sample_id}_filter_stats.txt
    seqkit seq \\
        --min-len ${min_length} \\
        --out-file ${sample_id}_filtered.fasta.gz \\
        ${assembly}

    echo "" | tee -a ${sample_id}_filter_stats.txt
    echo "=== Filtered Assembly Stats ===" | tee -a ${sample_id}_filter_stats.txt
    seqkit stats ${sample_id}_filtered.fasta.gz | tee -a ${sample_id}_filter_stats.txt

    # Calculate filtering summary
    INPUT_CONTIGS=\$(seqkit stats -T ${assembly} | tail -n1 | cut -f4)
    OUTPUT_CONTIGS=\$(seqkit stats -T ${sample_id}_filtered.fasta.gz | tail -n1 | cut -f4)
    REMOVED_CONTIGS=\$((INPUT_CONTIGS - OUTPUT_CONTIGS))

    echo "" | tee -a ${sample_id}_filter_stats.txt
    echo "=== Filtering Summary ===" | tee -a ${sample_id}_filter_stats.txt
    echo "Input contigs: \$INPUT_CONTIGS" | tee -a ${sample_id}_filter_stats.txt
    echo "Filtered contigs: \$OUTPUT_CONTIGS" | tee -a ${sample_id}_filter_stats.txt
    echo "Removed contigs: \$REMOVED_CONTIGS" | tee -a ${sample_id}_filter_stats.txt
    if [ \$INPUT_CONTIGS -gt 0 ]; then
        PERCENT_KEPT=\$(awk "BEGIN {printf \\"%.1f\\", \$OUTPUT_CONTIGS * 100 / \$INPUT_CONTIGS}")
        echo "Retention rate: \${PERCENT_KEPT}%" | tee -a ${sample_id}_filter_stats.txt
    fi

    echo "" | tee -a ${sample_id}_filter_stats.txt
    echo "Completed: \$(date)" | tee -a ${sample_id}_filter_stats.txt
    
    cat > versions.yml << END_VERSIONS
"${task.process}":
    seqkit: \$(seqkit version | cut -d' ' -f2)
END_VERSIONS
    """
}
