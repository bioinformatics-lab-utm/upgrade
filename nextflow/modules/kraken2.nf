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
    
    # Check if Kraken2 database exists
    if [ ! -d "${params.kraken2_db}" ]; then
        echo "WARNING: Kraken2 database not found at ${params.kraken2_db}"
        echo "Skipping Kraken2 analysis for ${bin_type} bins"
        echo -e "no_bins\\tDatabase not found\\t0\\t0\\t0" >> ${bin_type}_kraken2_summary.tsv
        exit 0
    fi
    
    # Process each bin file
    bin_count=0
    for bin_file in ${bins}; do
        if [ -f "\$bin_file" ]; then
            bin_count=\$((bin_count + 1))
            bin_name=\$(basename "\$bin_file" | sed 's/\\.[^.]*\$//')
            echo "Processing bin: \$bin_name"
            
            # Run Kraken2 on the bin
            kraken2 \\
                --db ${params.kraken2_db} \\
                --threads ${task.cpus} \\
                --memory-mapping \\
                --output ${bin_type}_kraken2_results/\${bin_name}_kraken2_output.txt \\
                --report ${bin_type}_kraken2_results/\${bin_name}_kraken2_report.txt \\
                "\$bin_file"
                
            if [ \$? -eq 0 ]; then
                
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
    
    # If no bins were processed successfully, consider this a failure
    if [ \$bin_count -eq 0 ]; then
        exit 1
    fi
    """
}