process BWA_MAPPING {
    tag "$sample_id"
    label 'process_high'

    // Using biocontainers mulled image with both bwa and samtools
    container 'quay.io/biocontainers/mulled-v2-fe8faa35dbf6dc65a0f7f5d4ea12e31a79f73e40:219b6c272b25e7e642ae3ff0bf0c5c81a5135ab4-0'

    publishDir "${params.outdir}/03_assembly/mapping", mode: 'copy', pattern: "*_depth.txt"
    publishDir "${params.outdir}/03_assembly/mapping", mode: 'copy', pattern: "*_depth.txt"

    input:
    tuple val(sample_id), path(assembly), path(reads)

    output:
    tuple val(sample_id), path("${sample_id}_sorted.bam"), path("${sample_id}_sorted.bam.bai"), emit: bam

    script:
    """
    echo "Creating BWA index for ${sample_id}..."
    bwa index ${assembly}
    
    echo "Mapping reads to assembly..."
    bwa mem -t ${task.cpus} ${assembly} ${reads} > ${sample_id}_mapped.sam
    
    echo "Converting SAM to sorted BAM..."
    samtools view -bS ${sample_id}_mapped.sam | samtools sort -@ ${task.cpus} -o ${sample_id}_sorted.bam
    
    echo "Indexing BAM file..."
    samtools index ${sample_id}_sorted.bam
    
    echo "Mapping completed for ${sample_id}"
    """
}
