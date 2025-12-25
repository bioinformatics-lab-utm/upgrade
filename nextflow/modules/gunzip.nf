// GUNZIP - Decompress FASTA files for tools that don't handle .gz

process GUNZIP {
    tag "${sample_id}"
    container 'ubuntu:22.04'
    publishDir "${params.outdir}/03_assembly", mode: 'copy', pattern: "*.fasta"
    
    input:
    tuple val(sample_id), path(fasta_gz)
    
    output:
    tuple val(sample_id), path("${sample_id}.fasta"), emit: fasta
    
    script:
    """
    # Copy instead of symlink to avoid Docker mount issues
    gunzip -c ${fasta_gz} > ${sample_id}.fasta
    """
}
