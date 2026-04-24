// Nucmer - Fast alignment of large sequences
// Part of MUMmer package for comparative genomics and HGT detection

process NUCMER {
    tag "${sample_id}"
    container 'staphb/mummer:latest'
    
    publishDir "${params.outdir}/08_comparative/nucmer", mode: 'copy'
    
    input:
    tuple val(sample_id), path(reference), path(query)
    
    output:
    tuple val(sample_id), path("${sample_id}.delta"), emit: delta
    tuple val(sample_id), path("${sample_id}.coords"), emit: coords
    tuple val(sample_id), path("${sample_id}.snps"), emit: snps, optional: true
    path "versions.yml", emit: versions
    
    script:
    """
    set -euo pipefail

    # Run nucmer alignment
    nucmer \\
        --maxgap=${params.nucmer_maxgap} \\
        --mincluster=${params.nucmer_mincluster} \\
        --minmatch=${params.nucmer_minmatch} \\
        --threads=${task.cpus} \\
        --prefix=${sample_id} \\
        ${reference} \\
        ${query}
    
    # Generate coordinates file
    show-coords -rcl ${sample_id}.delta > ${sample_id}.coords
    
    # Generate SNPs if requested
    if [ "${params.nucmer_snps}" = "true" ]; then
        show-snps -Clr ${sample_id}.delta > ${sample_id}.snps
    fi
    
    # Version info
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        nucmer: \$(nucmer --version 2>&1 | head -n1 | sed 's/nucmer //')
    END_VERSIONS
    """
}

// Nucmer with filtering and visualization
process NUCMER_PLOT {
    tag "${sample_id}"
    container 'staphb/mummer:latest'
    
    publishDir "${params.outdir}/08_comparative/nucmer_plots", mode: 'copy'
    
    input:
    tuple val(sample_id), path(reference), path(query)
    
    output:
    tuple val(sample_id), path("${sample_id}.delta"), emit: delta
    tuple val(sample_id), path("${sample_id}.filtered.delta"), emit: filtered_delta
    tuple val(sample_id), path("${sample_id}.coords"), emit: coords
    tuple val(sample_id), path("${sample_id}.png"), emit: plot
    path "versions.yml", emit: versions
    
    script:
    """
    set -euo pipefail

    # Run nucmer
    nucmer \\
        --maxgap=${params.nucmer_maxgap} \\
        --mincluster=${params.nucmer_mincluster} \\
        --minmatch=${params.nucmer_minmatch} \\
        --threads=${task.cpus} \\
        --prefix=${sample_id} \\
        ${reference} \\
        ${query}

    # Filter delta file (1-to-1 alignments, min 90% identity)
    delta-filter -1 -i ${params.nucmer_min_identity} ${sample_id}.delta > ${sample_id}.filtered.delta
    
    # Generate coordinates
    show-coords -rcl ${sample_id}.filtered.delta > ${sample_id}.coords
    
    # Generate dotplot
    mummerplot \\
        --png \\
        --prefix=${sample_id} \\
        --large \\
        ${sample_id}.filtered.delta
    
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        nucmer: \$(nucmer --version 2>&1 | head -n1 | sed 's/nucmer //')
    END_VERSIONS
    """
}

// Detect potential Horizontal Gene Transfer events
process NUCMER_HGT {
    tag "${sample_id}"
    container 'staphb/mummer:latest'
    
    publishDir "${params.outdir}/08_comparative/nucmer_hgt", mode: 'copy'
    
    input:
    tuple val(sample_id), path(reference), path(query)
    
    output:
    tuple val(sample_id), path("${sample_id}.hgt_candidates.txt"), emit: hgt_candidates
    path "versions.yml", emit: versions
    
    script:
    """
    set -euo pipefail

    # Run nucmer
    nucmer --prefix=${sample_id} ${reference} ${query}
    
    # Filter and identify HGT candidates
    # (High identity regions between distant organisms)
    delta-filter -1 -i 95 ${sample_id}.delta > ${sample_id}.filtered.delta
    show-coords -rcl ${sample_id}.filtered.delta | \\
        awk '\$7 > 95 && \$10 > 1000 {print}' > ${sample_id}.hgt_candidates.txt
    
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        nucmer: \$(nucmer --version 2>&1 | head -n1)
    END_VERSIONS
    """
}
