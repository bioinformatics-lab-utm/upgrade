process BRACKEN {
    tag "${bin_id}"
    publishDir "${params.outdir}/07_bracken/${method}", mode: 'copy'

    input:
    tuple val(method), val(bin_id), path(kraken_report)

    output:
    tuple val(method), val(bin_id), path("${bin_id}_bracken_output.txt"), emit: bracken_output
    tuple val(method), val(bin_id), path("${bin_id}_bracken_report.txt"), emit: bracken_report

    script:
    """
    # Run Bracken for species-level abundance estimation
    bracken \\
        -d \${BRACKEN_DB:-/kraken2_db} \\
        -i ${kraken_report} \\
        -o ${bin_id}_bracken_output.txt \\
        -w ${bin_id}_bracken_report.txt \\
        -r ${params.bracken_read_len} \\
        -l ${params.bracken_level} \\
        -t ${params.bracken_threshold}

    # If Bracken fails (no reads classified), create empty files to avoid pipeline failure
    if [ ! -f "${bin_id}_bracken_output.txt" ]; then
        echo "# No reads classified at ${params.bracken_level} level for ${bin_id}" > ${bin_id}_bracken_output.txt
        echo "# No Bracken report generated for ${bin_id}" > ${bin_id}_bracken_report.txt
    fi
    """
}

process BRACKEN_COMBINED_REPORT {
    tag "${method}"
    publishDir "${params.outdir}/07_bracken", mode: 'copy'

    input:
    tuple val(method), path(bracken_outputs)

    output:
    tuple val(method), path("${method}_bracken_combined_report.txt"), emit: combined_report

    script:
    """
    #!/usr/bin/env python3
    
    import glob
    import os

    # Find all Bracken output files
    bracken_files = glob.glob("*_bracken_output.txt")
    
    combined_data = []
    header_written = False
    
    with open("${method}_bracken_combined_report.txt", "w") as outfile:
        for file in bracken_files:
            bin_id = file.replace("_bracken_output.txt", "")
            
            try:
                with open(file, 'r') as infile:
                    lines = infile.readlines()
                    
                if not lines:
                    continue
                    
                # Skip comment lines
                data_lines = [line for line in lines if not line.startswith('#')]
                
                if not data_lines:
                    continue
                
                # Write header only once
                if not header_written and data_lines:
                    header = data_lines[0].strip() + "\\tbin_id\\n"
                    outfile.write(header)
                    header_written = True
                
                # Write data lines with bin_id
                for line in data_lines[1:]:  # Skip header line
                    if line.strip():
                        outfile.write(line.strip() + "\\t" + bin_id + "\\n")
                        
            except Exception as e:
                print(f"Warning: Could not process {file}: {e}")
    
    # Check if any data was written
    if header_written:
        print(f"Combined Bracken report created for ${method}")
    else:
        # Create empty file if no data
        with open("${method}_bracken_combined_report.txt", "w") as f:
            f.write("# No Bracken data available for ${method}\\n")
        print(f"No Bracken data found for ${method}")
    """
}