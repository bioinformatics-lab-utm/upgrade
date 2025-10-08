process KRAKEN2 {
    tag "$sample_id"
    publishDir "${params.outdir}/06_kraken2", mode: 'copy'
    errorStrategy 'ignore'
    
    input:
        tuple val(sample_id), path(bins)
        val(bin_type)
    
    output:
        tuple val(sample_id), path("${bin_type}_kraken2_results/"), emit: results, optional: true
        tuple val(sample_id), path("${bin_type}_kraken2_summary.tsv"), emit: summary, optional: true
    
    script:
    """
    set +e  # Don't exit on error
    
    # Create output directory
    mkdir -p ${bin_type}_kraken2_results
    
    # Create summary header
    echo -e "bin_id\\ttaxonomy\\tconfidence\\tnum_reads\\tnum_reads_clade" > ${bin_type}_kraken2_summary.tsv
    
    # Check if Kraken2 database exists
    if [ ! -d "${params.kraken2_db}" ]; then
        echo "WARNING: Kraken2 database not found at ${params.kraken2_db}"
        echo "Skipping Kraken2 analysis for ${bin_type} bins"
        echo -e "no_bins\\tDatabase not found\\t0\\t0\\t0" >> ${bin_type}_kraken2_summary.tsv
        exit 0
    fi
    
    # Process each bin file
    bin_count=0
    for bin_file in ${bins}/*.{fa,fasta}; do
        if [ -f "\$bin_file" ]; then
            bin_count=\$((bin_count + 1))
            bin_name=\$(basename "\$bin_file" | sed 's/\\.[^.]*\$//')
            echo "Processing bin: \$bin_name"
            
            # Run Kraken2 on the bin with error handling
            if kraken2 \\
                --db ${params.kraken2_db} \\
                --threads ${task.cpus} \\
                --output ${bin_type}_kraken2_results/\${bin_name}_kraken2_output.txt \\
                --report ${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt \\
                --confidence 0.1 \\
                "\$bin_file" 2>/dev/null; then
                
                # Extract top taxonomy assignment
                if [ -f "${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt" ] && [ -s "${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt" ]; then
                    top_assignment=\$(head -n 1 ${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt | awk '{print \$6}' | sed 's/^[[:space:]]*//')
                    confidence=\$(head -n 1 ${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt | awk '{print \$1}')
                    num_reads=\$(head -n 1 ${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt | awk '{print \$2}')
                    num_reads_clade=\$(head -n 1 ${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt | awk '{print \$3}')
                    
                    echo -e "\${bin_name}\\t\${top_assignment}\\t\${confidence}\\t\${num_reads}\\t\${num_reads_clade}" >> ${bin_type}_kraken2_summary.tsv
                else
                    echo -e "\${bin_name}\\tNo classification\\t0\\t0\\t0" >> ${bin_type}_kraken2_summary.tsv
                fi
            else
                echo "WARNING: Kraken2 failed for bin \$bin_name, skipping..."
                echo -e "\${bin_name}\\tClassification failed\\t0\\t0\\t0" >> ${bin_type}_kraken2_summary.tsv
            fi
        fi
    done
    
    if [ \$bin_count -eq 0 ]; then
        echo "WARNING: No bin files found for ${bin_type}"
        echo -e "no_bins\\tNo bins found\\t0\\t0\\t0" >> ${bin_type}_kraken2_summary.tsv
    fi
    
    echo "Kraken2 analysis completed for ${bin_type} bins (processed \$bin_count bins)"
    exit 0
    """
}
