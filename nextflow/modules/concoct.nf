process CONCOCT {
    tag "$sample_id"
    label 'process_medium'
    
    container 'quay.io/biocontainers/concoct:1.1.0--py27h88e4a8a_0'

    input:
    tuple val(sample_id), path(assembly)
    tuple val(sample_id), path(reads)

    output:
    tuple val(sample_id), path("${sample_id}_concoct_bins/*.fa"), emit: bins
    tuple val(sample_id), path("${sample_id}.concoct.log"), emit: log
    tuple val(sample_id), path("${sample_id}_concoct_clustering_gt${params.concoct_min_contig ?: 1000}.csv"), emit: clustering
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args = task.ext.args ?: ''
    def min_contig_length = params.concoct_min_contig ?: 1000
    def chunk_size = params.concoct_chunk_size ?: 10000
    def overlap_size = params.concoct_overlap_size ?: 0
    
    """
    echo "Starting CONCOCT binning for ${sample_id}" | tee ${sample_id}.concoct.log
    echo "Assembly: ${assembly}" | tee -a ${sample_id}.concoct.log
    echo "Reads: ${reads}" | tee -a ${sample_id}.concoct.log
    echo "Min contig length: ${min_contig_length}" | tee -a ${sample_id}.concoct.log
    echo "Chunk size: ${chunk_size}" | tee -a ${sample_id}.concoct.log
    echo "Started: \$(date)" | tee -a ${sample_id}.concoct.log
    
    # Create working directories
    mkdir -p ${sample_id}_concoct_work
    mkdir -p ${sample_id}_concoct_bins
    
    # Step 1: Cut contigs into smaller parts
    echo "Cutting contigs into chunks..." | tee -a ${sample_id}.concoct.log
    cut_up_fasta.py ${assembly} -c ${chunk_size} -o ${overlap_size} --merge_last -b ${sample_id}_concoct_work/contigs_${chunk_size}.bed > ${sample_id}_concoct_work/contigs_${chunk_size}.fa 2>&1 | tee -a ${sample_id}.concoct.log
    
    # Step 2: Map reads to assembly
    echo "Creating BWA index..." | tee -a ${sample_id}.concoct.log
    bwa index ${sample_id}_concoct_work/contigs_${chunk_size}.fa 2>&1 | tee -a ${sample_id}.concoct.log
    
    echo "Mapping reads to chunked contigs..." | tee -a ${sample_id}.concoct.log
    bwa mem -t ${task.cpus} ${sample_id}_concoct_work/contigs_${chunk_size}.fa ${reads} > ${sample_id}_concoct_work/map.sam 2>&1 | tee -a ${sample_id}.concoct.log
    
    # Step 3: Convert to sorted BAM
    echo "Converting and sorting BAM..." | tee -a ${sample_id}.concoct.log
    samtools view -bS ${sample_id}_concoct_work/map.sam | samtools sort -@ ${task.cpus} -o ${sample_id}_concoct_work/map_sorted.bam 2>&1 | tee -a ${sample_id}.concoct.log
    samtools index ${sample_id}_concoct_work/map_sorted.bam 2>&1 | tee -a ${sample_id}.concoct.log
    
    # Step 4: Generate coverage table
    echo "Generating coverage table..." | tee -a ${sample_id}.concoct.log
    concoct_coverage_table.py ${sample_id}_concoct_work/contigs_${chunk_size}.bed ${sample_id}_concoct_work/map_sorted.bam > ${sample_id}_concoct_work/coverage_table.tsv 2>&1 | tee -a ${sample_id}.concoct.log
    
    # Step 5: Run CONCOCT
    echo "Running CONCOCT clustering..." | tee -a ${sample_id}.concoct.log
    concoct \\
        --composition_file ${sample_id}_concoct_work/contigs_${chunk_size}.fa \\
        --coverage_file ${sample_id}_concoct_work/coverage_table.tsv \\
        -b ${sample_id}_concoct_work/ \\
        -t ${task.cpus} \\
        ${args} 2>&1 | tee -a ${sample_id}.concoct.log
    
    # Step 6: Merge subcontig clustering into original contig clustering
    echo "Merging clustering results..." | tee -a ${sample_id}.concoct.log
    merge_cutup_clustering.py ${sample_id}_concoct_work/clustering_gt${min_contig_length}.csv > ${sample_id}_concoct_clustering_gt${min_contig_length}.csv 2>&1 | tee -a ${sample_id}.concoct.log
    
    # Step 7: Extract bins in FASTA format
    echo "Extracting bins..." | tee -a ${sample_id}.concoct.log
    extract_fasta_bins.py ${assembly} ${sample_id}_concoct_clustering_gt${min_contig_length}.csv --output_path ${sample_id}_concoct_bins/ 2>&1 | tee -a ${sample_id}.concoct.log
    
    echo "CONCOCT completed: \$(date)" | tee -a ${sample_id}.concoct.log
    
    # Count number of bins
    BIN_COUNT=\$(ls ${sample_id}_concoct_bins/*.fa 2>/dev/null | wc -l)
    echo "Number of bins generated: \$BIN_COUNT" | tee -a ${sample_id}.concoct.log
    
    # If no bins were generated, create an empty file to avoid pipeline failure
    if [ \$BIN_COUNT -eq 0 ]; then
        echo "No bins generated - creating empty bin file" | tee -a ${sample_id}.concoct.log
        touch ${sample_id}_concoct_bins/${sample_id}_bin_0.fa
    fi

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        concoct: \$(concoct --version 2>&1 | grep -o '[0-9.]*')
        bwa: \$(bwa 2>&1 | grep -e '^Version' | sed 's/Version: //')
        samtools: \$(samtools --version | head -n1 | cut -d' ' -f2)
    END_VERSIONS
    """
}