process KRAKEN2 {
    tag "$sample_id"
    publishDir "${params.outdir}/06_kraken2", mode: 'copy'
    
    input:
        tuple val(sample_id), path(bins)
        val(bin_type)
    
    output:
        tuple val(sample_id), path("${bin_type}_kraken2_results/"), emit: results, optional: true
        tuple val(sample_id), path("${bin_type}_kraken2_summary.tsv"), emit: summary, optional: true
        tuple val(bin_type), path("${bin_type}_kraken2_results/*_kraken2_report.txt"), emit: kraken_reports, optional: true
    
    script:
    """
    # Create output directory
    mkdir -p ${bin_type}_kraken2_results
    
    # Create summary header
    echo -e "bin_id\\ttaxonomy\\tconfidence\\tnum_reads\\tnum_reads_clade" > ${bin_type}_kraken2_summary.tsv
    
    # Check if Kraken2 database exists — fail if missing (required resource)
    if [ ! -d "${params.kraken2_db}" ]; then
        echo "ERROR: Kraken2 database not found at ${params.kraken2_db}" >&2
        echo "Set params.kraken2_db to a valid Kraken2 database path" >&2
        exit 1
    fi
    
    # Count bins and determine parallelism
    bin_files=(\$(ls -1 ${bins} 2>/dev/null || true))
    bin_count=\${#bin_files[@]}

    if [ \$bin_count -eq 0 ]; then
        echo "WARNING: No bin files found for ${bin_type}"
        echo -e "no_bins\\tNo bins found\\t0\\t0\\t0" >> ${bin_type}_kraken2_summary.tsv
        exit 1
    fi

    echo "Found \$bin_count bins to process"

    # OPTIMIZATION: Calculate threads per bin for parallel processing
    # Use parallel jobs with fewer threads each instead of sequential with all threads
    total_cpus=${task.cpus}
    parallel_jobs=\$(( bin_count < total_cpus ? bin_count : total_cpus ))
    threads_per_bin=\$(( total_cpus / parallel_jobs ))
    threads_per_bin=\$(( threads_per_bin < 1 ? 1 : threads_per_bin ))

    echo "Running \$parallel_jobs parallel jobs with \$threads_per_bin threads each"

    # Create a function to process single bin (for parallel execution)
    process_bin() {
        bin_file="\$1"
        bin_name=\$(basename "\$bin_file" | sed 's/\\.[^.]*\$//')
        threads="\$2"

        echo "Processing bin: \$bin_name with \$threads threads"

        kraken2 \\
            --db ${params.kraken2_db} \\
            --threads \$threads \\
            --memory-mapping \\
            --output ${bin_type}_kraken2_results/\${bin_name}_kraken2_output.txt \\
            --report ${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt \\
            "\$bin_file" 2>/dev/null

        if [ \$? -eq 0 ] && [ -f "${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt" ] && [ -s "${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt" ]; then
            top_assignment=\$(head -n 1 ${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt | awk '{print \$6}' | sed 's/^[[:space:]]*//')
            confidence=\$(head -n 1 ${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt | awk '{print \$1}')
            num_reads=\$(head -n 1 ${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt | awk '{print \$2}')
            num_reads_clade=\$(head -n 1 ${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt | awk '{print \$3}')
            echo -e "\${bin_name}\\t\${top_assignment}\\t\${confidence}\\t\${num_reads}\\t\${num_reads_clade}"
        else
            echo -e "\${bin_name}\\tClassification failed\\t0\\t0\\t0"
        fi
    }
    export -f process_bin

    # Run bins in parallel using GNU parallel (if available) or xargs
    if command -v parallel > /dev/null 2>&1; then
        echo "Using GNU parallel for \$bin_count bins"
        printf '%s\\n' "\${bin_files[@]}" | parallel -j \$parallel_jobs process_bin {} \$threads_per_bin >> ${bin_type}_kraken2_summary.tsv
    else
        echo "GNU parallel not found, using xargs for parallelization"
        printf '%s\\n' "\${bin_files[@]}" | xargs -P \$parallel_jobs -I {} bash -c "process_bin '{}' \$threads_per_bin" >> ${bin_type}_kraken2_summary.tsv
    fi

    echo "Kraken2 analysis completed for ${bin_type} bins (processed \$bin_count bins in parallel)"
    """
}