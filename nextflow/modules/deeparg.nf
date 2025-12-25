// DeepARG - Deep Learning based ARG prediction
// Uses neural networks for AMR gene prediction

process DEEPARG {
    tag "${sample_id}"
    container 'upgrade-deeparg:latest'

    publishDir "${params.outdir}/07_amr/deeparg/${sample_id}", mode: 'copy'
    
    input:
    tuple val(sample_id), path(assembly)
    
    output:
    tuple val(sample_id), path("${sample_id}.deeparg.mapping.ARG"), emit: results
    tuple val(sample_id), path("${sample_id}.deeparg.mapping.potential.ARG"), emit: potential
    path "versions.yml", emit: versions
    
    script:
    """
    # Run DeepARG with mounted database
    deeparg predict \\
        --model ${params.deeparg_model} \\
        --type nucl \\
        --input ${assembly} \\
        --out ${sample_id}.deeparg \\
        --data-path /deeparg_db \\
        --arg-alignment-identity ${params.deeparg_identity} \\
        --arg-alignment-evalue ${params.deeparg_evalue} \\
        --arg-num-alignments-per-entry ${params.deeparg_alignments}
    
    # Version info
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        deeparg: \$(deeparg --version 2>&1 | head -n1)
        model: ${params.deeparg_model}
    END_VERSIONS
    """
}

// DeepARG short reads mode (for unassembled reads)
process DEEPARG_SHORT {
    tag "${sample_id}"
    container 'gaarangoa/deeparg:latest'
    
    publishDir "${params.outdir}/07_amr/deeparg_multi", mode: 'copy'
    
    input:
    tuple val(sample_id), path(reads)
    
    output:
    tuple val(sample_id), path("${sample_id}.deeparg.short.ARG"), emit: results
    path "versions.yml", emit: versions
    
    script:
    """
    # Run DeepARG on short reads
    deeparg short_reads_pipeline \\
        --forward_pe_file ${reads[0]} \\
        --reverse_pe_file ${reads[1]} \\
        --output ${sample_id}.deeparg.short \\
        --deeparg_identity ${params.deeparg_identity} \\
        --deeparg_probability ${params.deeparg_probability} \\
        --deeparg_evalue ${params.deeparg_evalue}
    
    # Version info
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        deeparg: \$(deeparg --version 2>&1 | head -n1)
    END_VERSIONS
    """
}
