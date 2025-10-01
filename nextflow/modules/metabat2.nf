process METABAT2 {
    tag "$sample_id"
    label 'process_medium'
    
    container 'metabat/metabat:2.15'

    input:
    tuple val(sample_id), path(assembly)
    tuple val(sample_id), path(reads)

    output:
    tuple val(sample_id), path("${sample_id}_bins/*.fa"), emit: bins
    tuple val(sample_id), path("${sample_id}.metabat2.log"), emit: log
    tuple val(sample_id), path("${sample_id}_depth.txt"), emit: depth
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args = task.ext.args ?: ''
    def min_contig_length = params.metabat2_min_contig ?: 2500
    def min_bin_size = params.metabat2_min_bin ?: 200000
    
    """
    # Install missing dependencies
    apt-get update -qq && apt-get install -y -qq bwa samtools || echo "Dependencies may already be installed"
    
    echo "Starting MetaBAT2 binning for ${sample_id}" | tee ${sample_id}.metabat2.log
    echo "Assembly: ${assembly}" | tee -a ${sample_id}.metabat2.log
    echo "Reads: ${reads}" | tee -a ${sample_id}.metabat2.log
    echo "Min contig length: ${min_contig_length}" | tee -a ${sample_id}.metabat2.log
    echo "Min bin size: ${min_bin_size}" | tee -a ${sample_id}.metabat2.log
    echo "Started: \$(date)" | tee -a ${sample_id}.metabat2.log
    
    # Create output directory
    mkdir -p ${sample_id}_bins
    
    # Decompress assembly if it's gzipped
    if [[ ${assembly} == *.gz ]]; then
        echo "Decompressing assembly..." | tee -a ${sample_id}.metabat2.log
        gunzip -c ${assembly} > ${sample_id}_assembly.fasta
        ASSEMBLY_FILE=${sample_id}_assembly.fasta
    else
        ASSEMBLY_FILE=${assembly}
    fi
    
    # Step 1: Create mapping index and map reads
    echo "Creating BWA index..." | tee -a ${sample_id}.metabat2.log
    bwa index \$ASSEMBLY_FILE 2>&1 | tee -a ${sample_id}.metabat2.log
    
    echo "Mapping reads to assembly..." | tee -a ${sample_id}.metabat2.log
    bwa mem -t ${task.cpus} \$ASSEMBLY_FILE ${reads} | samtools view -bS - | samtools sort -@ ${task.cpus} -o ${sample_id}_sorted.bam 2>&1 | tee -a ${sample_id}.metabat2.log
    
    # Index the BAM file
    samtools index ${sample_id}_sorted.bam 2>&1 | tee -a ${sample_id}.metabat2.log
    
    # Step 2: Calculate depth
    echo "Calculating contig depths..." | tee -a ${sample_id}.metabat2.log
    jgi_summarize_bam_contig_depths --outputDepth ${sample_id}_depth.txt ${sample_id}_sorted.bam 2>&1 | tee -a ${sample_id}.metabat2.log
    
    # Step 3: Run MetaBAT2 binning
    echo "Running MetaBAT2 binning..." | tee -a ${sample_id}.metabat2.log
    metabat2 \\
        -i \$ASSEMBLY_FILE \\
        -a ${sample_id}_depth.txt \\
        -o ${sample_id}_bins/${sample_id}_bin \\
        -t ${task.cpus} \\
        -m ${min_contig_length} \\
        -s ${min_bin_size} \\
        --saveCls \\
        --unbinned \\
        ${args} 2>&1 | tee -a ${sample_id}.metabat2.log
    
    echo "MetaBAT2 completed: \$(date)" | tee -a ${sample_id}.metabat2.log
    
    # Count number of bins
    BIN_COUNT=\$(ls ${sample_id}_bins/*.fa 2>/dev/null | wc -l)
    echo "Number of bins generated: \$BIN_COUNT" | tee -a ${sample_id}.metabat2.log
    
    # If no bins were generated, create an empty file to avoid pipeline failure
    if [ \$BIN_COUNT -eq 0 ]; then
        echo "No bins generated - creating empty bin file" | tee -a ${sample_id}.metabat2.log
        touch ${sample_id}_bins/${sample_id}_bin.unbinned.fa
    fi

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        metabat2: \$(metabat2 --help 2>&1 | grep -o 'version [0-9.]*' | cut -d' ' -f2)
        bwa: \$(bwa 2>&1 | grep -e '^Version' | sed 's/Version: //')
        samtools: \$(samtools --version | head -n1 | cut -d' ' -f2)
    END_VERSIONS
    """
}