process MINIMAP2_MAPPING {
    tag "$sample_id"
    label 'process_high'

    // minimap2 + samtools — minimap2 is 10-50x faster than BWA MEM for ONT long reads
    container 'quay.io/biocontainers/mulled-v2-66534bcbb7031a148b13e2ad42583020b9cd25c4:e1ea28074233d7265a5dc2111d6e55130dff5653-2'

    publishDir "${params.outdir}/03_assembly/mapping", mode: 'copy', pattern: "*_sorted.bam"
    publishDir "${params.outdir}/03_assembly/mapping", mode: 'copy', pattern: "*_sorted.bam.bai"
    publishDir "${params.outdir}/03_assembly/mapping", mode: 'copy', pattern: "*_depth.txt"

    input:
    tuple val(sample_id), path(assembly), path(reads)

    output:
    tuple val(sample_id), path("${sample_id}_sorted.bam"), path("${sample_id}_sorted.bam.bai"), emit: bam

    script:
    """
    set -euo pipefail

    echo "Mapping ONT reads to assembly with minimap2 (map-ont preset)..."

    # minimap2 with map-ont preset: optimised for ONT long reads
    # -a: SAM output  -t: threads  map-ont: ONT-specific scoring
    minimap2 -a -t ${task.cpus} -x map-ont ${assembly} ${reads} \
        | samtools sort -@ ${task.cpus} -o ${sample_id}_sorted.bam

    echo "Indexing BAM file..."
    samtools index ${sample_id}_sorted.bam

    echo "Mapping completed for ${sample_id}"
    """
}
