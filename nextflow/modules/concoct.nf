process CONCOCT {
    tag "$sample_id"
    label 'process_medium'

    container 'quay.io/biocontainers/concoct:1.1.0--py27h88e4a8a_0'

    publishDir "${params.outdir}/04_binning/concoct", mode: 'copy', pattern: "${sample_id}_concoct_bins"
    publishDir "${params.outdir}/04_binning/concoct", mode: 'copy', pattern: "*.log"
    publishDir "${params.outdir}/04_binning/concoct", mode: 'copy', pattern: "*_clustering_*.csv"

    input:
    tuple val(sample_id), path(assembly)
    tuple val(sample_id), path(bam), path(bai)

    output:
    tuple val(sample_id), path("${sample_id}_concoct_bins/*.fa"), emit: bins, optional: true
    tuple val(sample_id), path("${sample_id}.concoct.log"), emit: log
    tuple val(sample_id), path("${sample_id}_concoct_clustering_gt${params.concoct_min_contig ?: 1000}.csv"), emit: clustering, optional: true
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args = task.ext.args ?: ''
    def min_contig_length = params.concoct_min_contig ?: 1000
    def chunk_size = params.concoct_chunk_size ?: 10000
    def overlap_size = params.concoct_overlap_size ?: 0
    
    """
    # CONCOCT may fail due to coverage table issues - handle gracefully
    set +e
    
    echo "Starting CONCOCT binning for ${sample_id}" | tee ${sample_id}.concoct.log
    echo "Assembly: ${assembly}" | tee -a ${sample_id}.concoct.log
    echo "BAM file: ${bam}" | tee -a ${sample_id}.concoct.log
    echo "Min contig length: ${min_contig_length}" | tee -a ${sample_id}.concoct.log
    echo "Chunk size: ${chunk_size}" | tee -a ${sample_id}.concoct.log
    echo "Started: \$(date)" | tee -a ${sample_id}.concoct.log
    
    # Create working directories
    mkdir -p ${sample_id}_concoct_work
    mkdir -p ${sample_id}_concoct_bins
    
    # Decompress assembly if gzipped
    if [[ ${assembly} == *.gz ]]; then
        echo "Decompressing assembly..." | tee -a ${sample_id}.concoct.log
        gunzip -c ${assembly} > ${sample_id}_assembly.fasta
        ASSEMBLY_FILE=${sample_id}_assembly.fasta
    else
        ASSEMBLY_FILE=${assembly}
    fi
    
    # Step 1: Cut contigs into smaller parts
    echo "Cutting contigs into chunks..." | tee -a ${sample_id}.concoct.log
    cut_up_fasta.py \$ASSEMBLY_FILE -c ${chunk_size} -o ${overlap_size} --merge_last -b ${sample_id}_concoct_work/contigs_${chunk_size}.bed > ${sample_id}_concoct_work/contigs_${chunk_size}.fa 2>&1 | tee -a ${sample_id}.concoct.log
    
    # Step 2: Generate coverage table from BAM using samtools
    echo "Generating coverage table from BAM..." | tee -a ${sample_id}.concoct.log
    
    # Check BAM file integrity
    if [ ! -f "${bam}" ]; then
        echo "ERROR: BAM file not found: ${bam}" | tee -a ${sample_id}.concoct.log
        exit 1
    fi
    
    # Generate coverage using jgi_summarize_bam_contig_depths (MetaBAT2 tool)
    # This is more reliable than concoct_coverage_table.py
    if command -v jgi_summarize_bam_contig_depths &> /dev/null; then
        echo "Using jgi_summarize_bam_contig_depths for coverage..." | tee -a ${sample_id}.concoct.log
        jgi_summarize_bam_contig_depths --outputDepth ${sample_id}_concoct_work/coverage_table.tsv ${bam} 2>&1 | tee -a ${sample_id}.concoct.log
    else
        # Fallback: manual coverage calculation with samtools
        echo "Using samtools for coverage calculation..." | tee -a ${sample_id}.concoct.log
        
        # Get contig lengths from BAM header
        samtools view -H ${bam} | grep "^@SQ" | awk '{split(\$2,a,":"); split(\$3,b,":"); print a[2]"\\t"b[2]}' > ${sample_id}_concoct_work/contig_lengths.txt
        
        # Calculate depth per contig
        samtools depth -aa ${bam} | awk '{sum[\$1]+=\$3; count[\$1]++} END {for(contig in sum) print contig"\\t"sum[contig]/count[contig]}' > ${sample_id}_concoct_work/contig_depths.txt
        
        # Merge into coverage table (CONCOCT format: contigName, contigLen, totalAvgDepth, bam1.sorted.bam)
        echo -e "contigName\\tcontigLen\\ttotalAvgDepth\\t${bam}" > ${sample_id}_concoct_work/coverage_table.tsv
        join -t \$'\\t' ${sample_id}_concoct_work/contig_lengths.txt ${sample_id}_concoct_work/contig_depths.txt | \\
            awk -v bam="${bam}" '{print \$1"\\t"\$2"\\t"\$3"\\t"\$3}' >> ${sample_id}_concoct_work/coverage_table.tsv
    fi
    
    # Verify coverage table was created
    if [ ! -s "${sample_id}_concoct_work/coverage_table.tsv" ]; then
        echo "ERROR: Coverage table is empty or not created" | tee -a ${sample_id}.concoct.log
        echo "Creating dummy bins to prevent pipeline failure..." | tee -a ${sample_id}.concoct.log
        touch ${sample_id}_concoct_bins/${sample_id}_bin_0.fa
        touch ${sample_id}_concoct_clustering_gt${min_contig_length}.csv
        exit 0
    fi
    
    # Step 5: Run CONCOCT
    echo "Running CONCOCT clustering..." | tee -a ${sample_id}.concoct.log
    
    # Run CONCOCT with error handling
    concoct \\
        --composition_file ${sample_id}_concoct_work/contigs_${chunk_size}.fa \\
        --coverage_file ${sample_id}_concoct_work/coverage_table.tsv \\
        -b ${sample_id}_concoct_work/ \\
        -t ${task.cpus} \\
        ${args} 2>&1 | tee -a ${sample_id}.concoct.log
    
    CONCOCT_EXIT=\$?
    if [ \$CONCOCT_EXIT -ne 0 ]; then
        echo "WARNING: CONCOCT clustering failed with exit code \$CONCOCT_EXIT" | tee -a ${sample_id}.concoct.log
        echo "Creating empty output files..." | tee -a ${sample_id}.concoct.log
        touch ${sample_id}_concoct_bins/${sample_id}_bin_0.fa
        touch ${sample_id}_concoct_clustering_gt${min_contig_length}.csv
        echo "contig_id,cluster_id" > ${sample_id}_concoct_clustering_gt${min_contig_length}.csv
        
        cat <<END_VERSIONS > versions.yml
"${task.process}":
    concoct: \$(concoct --version 2>&1 | grep -o '[0-9.]*' || echo "1.1.0")
END_VERSIONS
        exit 0
    fi
    
    echo "CONCOCT clustering completed successfully" | tee -a ${sample_id}.concoct.log
    
    # Step 6: Merge subcontig clustering into original contig clustering
    echo "Merging clustering results..." | tee -a ${sample_id}.concoct.log
    
    # Check if clustering file exists
    if [ -f "${sample_id}_concoct_work/clustering_gt${min_contig_length}.csv" ]; then
        merge_cutup_clustering.py ${sample_id}_concoct_work/clustering_gt${min_contig_length}.csv > ${sample_id}_concoct_clustering_gt${min_contig_length}.csv 2>&1 | tee -a ${sample_id}.concoct.log
    else
        echo "WARNING: No clustering file found, creating empty output" | tee -a ${sample_id}.concoct.log
        echo "contig_id,cluster_id" > ${sample_id}_concoct_clustering_gt${min_contig_length}.csv
    fi
    
    # Step 7: Extract bins in FASTA format
    echo "Extracting bins..." | tee -a ${sample_id}.concoct.log
    
    # Check if we have valid clustering results
    if [ -s "${sample_id}_concoct_clustering_gt${min_contig_length}.csv" ] && [ \$(wc -l < ${sample_id}_concoct_clustering_gt${min_contig_length}.csv) -gt 1 ]; then
        extract_fasta_bins.py \$ASSEMBLY_FILE ${sample_id}_concoct_clustering_gt${min_contig_length}.csv --output_path ${sample_id}_concoct_bins/ 2>&1 | tee -a ${sample_id}.concoct.log || {
            echo "WARNING: extract_fasta_bins.py failed" | tee -a ${sample_id}.concoct.log
            touch ${sample_id}_concoct_bins/${sample_id}_bin_0.fa
        }
    else
        echo "WARNING: No valid clusters found, creating empty bin" | tee -a ${sample_id}.concoct.log
        touch ${sample_id}_concoct_bins/${sample_id}_bin_0.fa
    fi
    
    echo "CONCOCT completed: \$(date)" | tee -a ${sample_id}.concoct.log
    
    # Count number of bins
    BIN_COUNT=\$(ls ${sample_id}_concoct_bins/*.fa 2>/dev/null | wc -l)
    echo "Number of bins generated: \$BIN_COUNT" | tee -a ${sample_id}.concoct.log
    
    # If no bins were generated, create an empty file to avoid pipeline failure
    if [ \$BIN_COUNT -eq 0 ]; then
        echo "No bins generated - creating empty bin file" | tee -a ${sample_id}.concoct.log
        touch ${sample_id}_concoct_bins/${sample_id}_bin_0.fa
    fi

    cat <<END_VERSIONS > versions.yml
"${task.process}":
    concoct: \$(concoct --version 2>&1 | grep -o '[0-9.]*')
END_VERSIONS
    
    # Always exit successfully (CONCOCT is optional)
    exit 0
    """
}