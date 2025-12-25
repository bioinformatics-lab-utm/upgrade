process FLYE {
    tag "$sample_id"
    label 'process_high'
    
    container 'staphb/flye:2.9.2'
    
    publishDir "${params.outdir}/03_assembly", mode: 'copy', pattern: "*.{fasta.gz,gfa.gz,info.txt,flye.log}"

    input:
    tuple val(sample_id), path(reads)
    val mode

    output:
    tuple val(sample_id), path("${sample_id}.fasta.gz"), emit: fasta
    tuple val(sample_id), path("${sample_id}.gfa.gz") , emit: gfa
    tuple val(sample_id), path("${sample_id}.info.txt"), emit: txt
    tuple val(sample_id), path("${sample_id}.flye.log"), emit: log
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args = task.ext.args ?: ''
    def valid_mode = [
        '--pacbio-raw', '--pacbio-corr', '--pacbio-hifi',
        '--nano-raw', '--nano-corr', '--nano-hq'
    ]
    if ( !valid_mode.contains(mode) )  { error "Unrecognised mode to run Flye. Options: ${valid_mode.join(', ')}" }
    
    def genome_size_param = params.flye_genome_size ? "--genome-size ${params.flye_genome_size}" : ""
    def iterations_param = params.flye_iterations ? "--iterations ${params.flye_iterations}" : ""
    def meta_param = params.flye_meta ? "--meta" : ""
    
    """
    echo "Starting Flye assembly for ${sample_id}" | tee ${sample_id}.flye.log
    echo "Mode: ${mode}" | tee -a ${sample_id}.flye.log
    echo "Genome size: ${params.flye_genome_size}" | tee -a ${sample_id}.flye.log
    echo "Threads: ${task.cpus}" | tee -a ${sample_id}.flye.log
    echo "Input reads: ${reads}" | tee -a ${sample_id}.flye.log
    echo "Started: \$(date)" | tee -a ${sample_id}.flye.log
    
    flye \\
        ${mode} \\
        ${reads} \\
        --out-dir flye_output \\
        --threads ${task.cpus} \\
        ${genome_size_param} \\
        ${iterations_param} \\
        ${meta_param} \\
        ${args} 2>&1 | tee -a ${sample_id}.flye.log

    echo "Flye completed: \$(date)" | tee -a ${sample_id}.flye.log
    
    # Move and compress output files (using pigz if available, fallback to gzip)
    if [ -f flye_output/assembly.fasta ]; then
        if command -v pigz > /dev/null 2>&1; then
            pigz -p ${task.cpus} -n flye_output/assembly.fasta
        else
            gzip -n flye_output/assembly.fasta
        fi
        mv flye_output/assembly.fasta.gz ${sample_id}.fasta.gz
        if command -v pigz > /dev/null 2>&1; then
            echo "Assembly size: \$(pigz -dc ${sample_id}.fasta.gz | grep -v '^>' | wc -c) bp" | tee -a ${sample_id}.flye.log
        else
            echo "Assembly size: \$(zcat ${sample_id}.fasta.gz | grep -v '^>' | wc -c) bp" | tee -a ${sample_id}.flye.log
        fi
    else
        echo "ERROR: Assembly failed - no assembly.fasta produced" | tee -a ${sample_id}.flye.log
        touch ${sample_id}.fasta.gz
    fi
    
    if [ -f flye_output/assembly_graph.gfa ]; then
        if command -v pigz > /dev/null 2>&1; then
            pigz -p ${task.cpus} -n flye_output/assembly_graph.gfa
        else
            gzip -n flye_output/assembly_graph.gfa
        fi
        mv flye_output/assembly_graph.gfa.gz ${sample_id}.gfa.gz
    else
        touch ${sample_id}.gfa.gz
    fi
    
    if [ -f flye_output/assembly_info.txt ]; then
        mv flye_output/assembly_info.txt ${sample_id}.info.txt
    else
        echo "No assembly info available" > ${sample_id}.info.txt
    fi

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        flye: \$(flye --version 2>&1 | sed 's/^.*Flye //; s/ .*\$//')
    END_VERSIONS
    """
}