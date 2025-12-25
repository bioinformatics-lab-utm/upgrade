// Comparative Genomics Tools
// FastANI, Roary, Panaroo for pangenome analysis

process FASTANI {
    tag "${sample1_id}_vs_${sample2_id}"
    container 'staphb/fastani:1.33'
    
    publishDir "${params.outdir}/comparative/${sample1_id}_vs_${sample2_id}", mode: 'copy'
    
    input:
    tuple val(sample1_id), path(assembly1), val(sample2_id), path(assembly2)
    
    output:
    tuple val(sample1_id), val(sample2_id), path("${sample1_id}_vs_${sample2_id}.ani"), emit: results
    path "versions.yml", emit: versions
    
    script:
    """
    # Calculate Average Nucleotide Identity (ANI)
    fastANI \\
        -q ${assembly1} \\
        -r ${assembly2} \\
        -o ${sample1_id}_vs_${sample2_id}.ani \\
        --fragLen ${params.fastani_fraglen} \\
        --minFraction ${params.fastani_minfraction}
    
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        fastani: \$(fastANI --version 2>&1 | sed 's/version //')
    END_VERSIONS
    """
}

// Roary - Pan genome pipeline
process ROARY {
    tag "pangenome_${samples.size()}_samples"
    container 'staphb/roary:3.13.0'
    
    publishDir "${params.outdir}/comparative/roary", mode: 'copy'
    
    input:
    path gff_files // Multiple GFF files from Prokka
    
    output:
    path "roary_output/*", emit: results
    path "roary_output/summary_statistics.txt", emit: summary
    path "roary_output/gene_presence_absence.csv", emit: gene_matrix
    path "versions.yml", emit: versions
    
    script:
    """
    # Run Roary pangenome analysis
    roary \\
        -e \\
        -n \\
        -v \\
        -p ${task.cpus} \\
        -f roary_output \\
        -i ${params.roary_min_identity} \\
        -cd ${params.roary_core_definition} \\
        ${gff_files}
    
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        roary: \$(roary --version 2>&1 | head -n1)
    END_VERSIONS
    """
}

// Panaroo - Pangenome pipeline with graph-based clustering
process PANAROO {
    tag "pangenome_${gffs.size()}_samples"
    container 'staphb/panaroo:1.3.2'
    
    publishDir "${params.outdir}/comparative/panaroo", mode: 'copy'
    
    input:
    path gffs // Multiple GFF files
    
    output:
    path "panaroo_output/*", emit: results
    path "panaroo_output/summary_statistics.txt", emit: summary
    path "panaroo_output/gene_presence_absence.csv", emit: gene_matrix
    path "versions.yml", emit: versions
    
    script:
    """
    panaroo \\
        -i ${gffs} \\
        -o panaroo_output \\
        --clean-mode ${params.panaroo_clean_mode} \\
        --threshold ${params.panaroo_threshold} \\
        -t ${task.cpus} \\
        --alignment core \\
        --core_threshold ${params.panaroo_core_threshold}
    
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        panaroo: \$(panaroo --version 2>&1)
    END_VERSIONS
    """
}

// OrthoFinder - Phylogenetic orthology inference
process ORTHOFINDER {
    tag "orthology_${proteomes.size()}_samples"
    container 'davidemms/orthofinder:2.5.5'
    
    publishDir "${params.outdir}/comparative/orthofinder", mode: 'copy'
    
    input:
    path proteomes // Multiple protein FASTA files
    
    output:
    path "orthofinder_output/*", emit: results
    path "versions.yml", emit: versions
    
    script:
    """
    mkdir -p proteomes_dir
    cp ${proteomes} proteomes_dir/
    
    orthofinder \\
        -f proteomes_dir \\
        -t ${task.cpus} \\
        -a ${task.cpus} \\
        -o orthofinder_output
    
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        orthofinder: \$(orthofinder -h | grep "OrthoFinder version" | sed 's/OrthoFinder version //')
    END_VERSIONS
    """
}
