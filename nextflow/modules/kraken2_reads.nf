process KRAKEN2_READS {
    tag "$sample_id"
    publishDir "${params.outdir}/06_kraken2_reads", mode: 'copy'

    input:
        tuple val(sample_id), path(reads)

    output:
        tuple val(sample_id), path("${sample_id}_reads_kraken2_report.txt"), emit: report, optional: true
        tuple val(sample_id), path("${sample_id}_reads_kraken2_summary.tsv"), emit: summary, optional: true

    script:
    """
    echo -e "sample_id\\ttop_taxonomy\\tconfidence\\tnum_reads\\tnum_reads_clade" > ${sample_id}_reads_kraken2_summary.tsv

    if [ ! -d "${params.kraken2_db}" ]; then
        echo "ERROR: Kraken2 database not found at ${params.kraken2_db}" >&2
        echo -e "${sample_id}\\tKraken2 DB missing\\t0\\t0\\t0" >> ${sample_id}_reads_kraken2_summary.tsv
        exit 1
    fi

    kraken2 \\
        --db ${params.kraken2_db} \\
        --threads ${task.cpus} \\
        --confidence ${params.kraken2_confidence} \\
        --memory-mapping \\
        --output ${sample_id}_reads_kraken2_output.txt \\
        --report ${sample_id}_reads_kraken2_report.txt \\
        ${reads}

    if [ -s ${sample_id}_reads_kraken2_report.txt ]; then
        top_line=\$(sort -t\$'\\t' -k1,1 -rn ${sample_id}_reads_kraken2_report.txt | awk -F'\\t' '\$4!="U" && \$4!="R" {print; exit}')
        if [ -n "\$top_line" ]; then
            top_taxonomy=\$(echo "\$top_line" | awk -F'\\t' '{print \$6}' | sed 's/^[[:space:]]*//')
            confidence=\$(echo "\$top_line" | awk -F'\\t' '{print \$1}')
            num_reads=\$(echo "\$top_line" | awk -F'\\t' '{print \$2}')
            num_reads_clade=\$(echo "\$top_line" | awk -F'\\t' '{print \$3}')
            echo -e "${sample_id}\\t\${top_taxonomy}\\t\${confidence}\\t\${num_reads}\\t\${num_reads_clade}" >> ${sample_id}_reads_kraken2_summary.tsv
        else
            echo -e "${sample_id}\\tNo classified reads\\t0\\t0\\t0" >> ${sample_id}_reads_kraken2_summary.tsv
        fi
    else
        echo -e "${sample_id}\\tClassification failed\\t0\\t0\\t0" >> ${sample_id}_reads_kraken2_summary.tsv
    fi
    """
}

process SKIP_ASSEMBLY_MARKER {
    tag "$sample_id"
    publishDir "${params.outdir}/03_assembly", mode: 'copy'

    input:
        tuple val(sample_id), path(reads), val(coverage)

    output:
        tuple val(sample_id), path("${sample_id}.assembly_skipped.txt"), emit: marker

    script:
    """
    cat > ${sample_id}.assembly_skipped.txt << EOF
reason=low_coverage
estimated_coverage=${coverage}
min_coverage_for_assembly=${params.min_coverage_for_assembly}
flye_genome_size=${params.flye_genome_size}
EOF
    """
}
