// Prokka - Rapid prokaryotic genome annotation
// Produces GFF, GBK, FAA, FFN files

process PROKKA {
    tag "${sample_id}_${bin_name}"
    container 'staphb/prokka:1.14.6'

    publishDir "${params.outdir}/06_annotation/prokka/${bin_name}", mode: 'copy'
    
    input:
    tuple val(sample_id), val(bin_name), path(assembly)
    
    output:
    tuple val(sample_id), val(bin_name), path("${bin_name}/${bin_name}.gff"), emit: gff
    tuple val(sample_id), val(bin_name), path("${bin_name}/${bin_name}.gbk"), emit: gbk
    tuple val(sample_id), val(bin_name), path("${bin_name}/${bin_name}.faa"), emit: faa
    tuple val(sample_id), val(bin_name), path("${bin_name}/${bin_name}.ffn"), emit: ffn
    tuple val(sample_id), val(bin_name), path("${bin_name}/${bin_name}.tsv"), emit: tsv
    tuple val(sample_id), val(bin_name), path("${bin_name}/${bin_name}.txt"), emit: txt
    path "${bin_name}/*", emit: all_results
    path "versions.yml", emit: versions
    
    script:
    def kingdom = params.prokka_kingdom ?: 'Bacteria'
    def genus = params.prokka_genus ?: ''
    def species = params.prokka_species ?: ''
    def genus_opt = genus ? "--genus ${genus}" : ''
    def species_opt = species ? "--species ${species}" : ''
    // Sanitize locustag: replace dots/special chars with underscores, truncate to 10 chars
    // (--compliant mode: contig IDs must be <= 37 chars, prefix uses locustag)
    def safe_locustag = bin_name.replaceAll('[^A-Za-z0-9_]', '_').take(10)
    """
    export LOGNAME=upgrade
    prokka \\
        --outdir ${bin_name} \\
        --prefix ${bin_name} \\
        --kingdom ${kingdom} \\
        ${genus_opt} \\
        ${species_opt} \\
        --cpus ${task.cpus} \\
        --force \\
        --addgenes \\
        --compliant \\
        --centre UPGRADE \\
        --locustag ${safe_locustag} \\
        ${assembly}
    
    # Version info
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        prokka: \$(prokka --version 2>&1 | sed 's/prokka //')
    END_VERSIONS
    """
}

// Prokka with custom database
process PROKKA_CUSTOM {
    tag "${sample_id}"
    container 'staphb/prokka:1.14.6'
    
    publishDir "${params.outdir}/06_annotation/prokka_custom", mode: 'copy'
    
    input:
    tuple val(sample_id), path(assembly)
    path proteins_db
    
    output:
    tuple val(sample_id), path("${sample_id}/*"), emit: results
    path "versions.yml", emit: versions
    
    script:
    """
    prokka \\
        --outdir ${sample_id} \\
        --prefix ${sample_id} \\
        --proteins ${proteins_db} \\
        --cpus ${task.cpus} \\
        --force \\
        ${assembly}
    
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        prokka: \$(prokka --version 2>&1 | sed 's/prokka //')
    END_VERSIONS
    """
}
