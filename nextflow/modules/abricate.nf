// Abricate - AMR gene detection using multiple databases
// Databases: CARD, NCBI, ResFinder, ARG-ANNOT, etc.

process ABRICATE {
    tag "${sample_id}"
    container 'staphb/abricate:1.0.0'

    publishDir "${params.outdir}/07_amr/abricate/${sample_id}", mode: 'copy', pattern: "*.{tab,txt}"
    
    input:
    tuple val(sample_id), path(assembly)
    val(database) // card, ncbi, resfinder, argannot, etc.
    
    output:
    tuple val(sample_id), path("${sample_id}_abricate_${database}.tab"), emit: results
    tuple val(sample_id), path("${sample_id}_abricate_${database}_summary.txt"), emit: summary
    path "versions.yml", emit: versions
    
    script:
    def db_arg = database ? "--db ${database}" : "--db card"
    """
    # Run Abricate
    abricate \\
        ${db_arg} \\
        --minid ${params.abricate_min_identity} \\
        --mincov ${params.abricate_min_coverage} \\
        --threads ${task.cpus} \\
        ${assembly} \\
        > ${sample_id}_abricate_${database}.tab
    
    # Generate summary
    abricate --summary ${sample_id}_abricate_${database}.tab \\
        > ${sample_id}_abricate_${database}_summary.txt
    
    # Version info
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        abricate: \$(abricate --version 2>&1 | sed 's/abricate //')
        database: ${database}
    END_VERSIONS
    """
}

// Multi-database Abricate scan
process ABRICATE_MULTI {
    tag "${sample_id}"
    container 'staphb/abricate:1.0.0'
    
    publishDir "${params.outdir}/07_amr/abricate_multi", mode: 'copy'
    
    input:
    tuple val(sample_id), path(assembly)
    
    output:
    tuple val(sample_id), path("${sample_id}_abricate_*.tab"), emit: results
    tuple val(sample_id), path("${sample_id}_abricate_combined.tab"), emit: combined
    path "versions.yml", emit: versions
    
    script:
    """
    # Run Abricate on multiple databases
    for db in card ncbi resfinder argannot; do
        abricate \\
            --db \$db \\
            --minid ${params.abricate_min_identity} \\
            --mincov ${params.abricate_min_coverage} \\
            --threads ${task.cpus} \\
            ${assembly} \\
            > ${sample_id}_abricate_\${db}.tab
    done
    
    # Combine all results
    cat ${sample_id}_abricate_*.tab | grep -v "^#FILE" | sort -u \\
        > ${sample_id}_abricate_combined.tab
    
    # Version info
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        abricate: \$(abricate --version 2>&1 | sed 's/abricate //')
    END_VERSIONS
    """
}
