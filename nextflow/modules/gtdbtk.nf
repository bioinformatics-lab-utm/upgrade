process GTDBTK_CLASSIFY {
    tag "$sample_id"
    label 'process_high'
    
    container 'ecogenomic/gtdbtk:latest'

    input:
    tuple val(sample_id), path(bins)

    output:
    tuple val(sample_id), path("${sample_id}_gtdbtk/"), emit: results
    tuple val(sample_id), path("${sample_id}_gtdbtk/gtdbtk.*.summary.tsv"), emit: summary, optional: true
    tuple val(sample_id), path("${sample_id}_gtdbtk.log"), emit: log
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args = task.ext.args ?: ''
    def threads = task.cpus ?: 1
    def extension = params.gtdbtk_extension ?: 'fa'
    def min_perc_aa = params.gtdbtk_min_perc_aa ?: 10
    def pplacer_cpus = params.gtdbtk_pplacer_cpus ?: Math.max(1, (threads / 2).toInteger())
    
    """
    echo "Starting GTDB-Tk classification for ${sample_id}" | tee ${sample_id}_gtdbtk.log
    echo "Database path: \${GTDBTK_DATA_PATH}" | tee -a ${sample_id}_gtdbtk.log
    echo "Extension: ${extension}" | tee -a ${sample_id}_gtdbtk.log
    echo "Threads: ${threads}" | tee -a ${sample_id}_gtdbtk.log
    echo "Pplacer threads: ${pplacer_cpus}" | tee -a ${sample_id}_gtdbtk.log
    echo "Min AA percent: ${min_perc_aa}%" | tee -a ${sample_id}_gtdbtk.log
    echo "Started: \$(date)" | tee -a ${sample_id}_gtdbtk.log
    
    # Check if GTDBTK database is available — fail if missing (required resource)
    if [ -z "\${GTDBTK_DATA_PATH}" ] || [ ! -d "\${GTDBTK_DATA_PATH}" ]; then
        echo "ERROR: GTDBTK_DATA_PATH not set or directory not found" | tee -a ${sample_id}_gtdbtk.log >&2
        echo "Please download GTDB-Tk database and set GTDBTK_DATA_PATH" | tee -a ${sample_id}_gtdbtk.log >&2
        echo "Download: https://data.gtdb.ecogenomic.org/releases/latest/" | tee -a ${sample_id}_gtdbtk.log >&2
        exit 1
    fi
    
    # Create bins directory and copy bins
    mkdir -p ${sample_id}_bins_input
    
    # Check if we have actual bin files or just a directory
    if [ -d "${bins}" ]; then
        echo "Copying bins from directory..." | tee -a ${sample_id}_gtdbtk.log
        cp ${bins}/*.${extension} ${sample_id}_bins_input/ 2>/dev/null || echo "No .${extension} files found" | tee -a ${sample_id}_gtdbtk.log
    else
        echo "Copying individual bin files..." | tee -a ${sample_id}_gtdbtk.log
        for bin_file in ${bins}; do
            if [ -f "\$bin_file" ] && [ -s "\$bin_file" ]; then
                cp "\$bin_file" ${sample_id}_bins_input/
            fi
        done
    fi
    
    # Count bins
    BIN_COUNT=\$(ls ${sample_id}_bins_input/*.${extension} 2>/dev/null | wc -l)
    echo "Number of bins to classify: \$BIN_COUNT" | tee -a ${sample_id}_gtdbtk.log
    
    if [ \$BIN_COUNT -eq 0 ]; then
        echo "WARNING: No bins found for GTDB-Tk classification" | tee -a ${sample_id}_gtdbtk.log
        # Create empty output directory
        mkdir -p ${sample_id}_gtdbtk
        touch ${sample_id}_gtdbtk/.no_bins
        
        cat <<-END_VERSIONS > versions.yml
        "${task.process}":
            gtdbtk: \$(gtdbtk --version 2>&1 | grep -o 'gtdbtk: version [0-9.]*' | sed 's/gtdbtk: version //' || echo "2.3.2")
        END_VERSIONS
        
        exit 0
    fi
    
    # Set scratch directory for pplacer (needs lots of temp space)
    export TMPDIR=\${PWD}/gtdbtk_tmp
    mkdir -p \${TMPDIR}
    
    # Run GTDB-Tk classify_wf (combined identify, align, classify)
    echo "Running GTDB-Tk classify workflow..." | tee -a ${sample_id}_gtdbtk.log
    
    gtdbtk classify_wf \\
        --genome_dir ${sample_id}_bins_input \\
        --out_dir ${sample_id}_gtdbtk \\
        --extension ${extension} \\
        --cpus ${threads} \\
        --pplacer_cpus ${pplacer_cpus} \\
        --min_perc_aa ${min_perc_aa} \\
        --skip_ani_screen \\
        ${args} \\
        2>&1 | tee -a ${sample_id}_gtdbtk.log
    
    echo "GTDB-Tk classification completed: \$(date)" | tee -a ${sample_id}_gtdbtk.log
    
    # Parse and report summary statistics
    if [ -f "${sample_id}_gtdbtk/gtdbtk.bac120.summary.tsv" ]; then
        echo "" | tee -a ${sample_id}_gtdbtk.log
        echo "=== Bacterial Classification Summary ===" | tee -a ${sample_id}_gtdbtk.log
        BACTERIA_COUNT=\$(tail -n +2 ${sample_id}_gtdbtk/gtdbtk.bac120.summary.tsv | wc -l)
        echo "Bacterial genomes classified: \$BACTERIA_COUNT" | tee -a ${sample_id}_gtdbtk.log
        
        # Count by phylum
        echo "Top bacterial phyla:" | tee -a ${sample_id}_gtdbtk.log
        tail -n +2 ${sample_id}_gtdbtk/gtdbtk.bac120.summary.tsv | \\
            cut -f2 | \\
            sed 's/.*;p__\\([^;]*\\).*/\\1/' | \\
            sort | uniq -c | sort -rn | head -5 | tee -a ${sample_id}_gtdbtk.log
    fi
    
    if [ -f "${sample_id}_gtdbtk/gtdbtk.ar53.summary.tsv" ]; then
        echo "" | tee -a ${sample_id}_gtdbtk.log
        echo "=== Archaeal Classification Summary ===" | tee -a ${sample_id}_gtdbtk.log
        ARCHAEA_COUNT=\$(tail -n +2 ${sample_id}_gtdbtk/gtdbtk.ar53.summary.tsv | wc -l)
        echo "Archaeal genomes classified: \$ARCHAEA_COUNT" | tee -a ${sample_id}_gtdbtk.log
        
        # Count by phylum
        echo "Top archaeal phyla:" | tee -a ${sample_id}_gtdbtk.log
        tail -n +2 ${sample_id}_gtdbtk/gtdbtk.ar53.summary.tsv | \\
            cut -f2 | \\
            sed 's/.*;p__\\([^;]*\\).*/\\1/' | \\
            sort | uniq -c | sort -rn | head -5 | tee -a ${sample_id}_gtdbtk.log
    fi
    
    # Report ANI and classification confidence
    if [ -f "${sample_id}_gtdbtk/gtdbtk.bac120.summary.tsv" ]; then
        echo "" | tee -a ${sample_id}_gtdbtk.log
        echo "=== Classification Quality ===" | tee -a ${sample_id}_gtdbtk.log
        echo "High confidence (ANI >95%):" | tee -a ${sample_id}_gtdbtk.log
        awk -F'\\t' 'NR>1 && \$17>95 {count++} END {print count+0}' ${sample_id}_gtdbtk/gtdbtk.bac120.summary.tsv | tee -a ${sample_id}_gtdbtk.log
        
        echo "Medium confidence (ANI 90-95%):" | tee -a ${sample_id}_gtdbtk.log
        awk -F'\\t' 'NR>1 && \$17>=90 && \$17<=95 {count++} END {print count+0}' ${sample_id}_gtdbtk/gtdbtk.bac120.summary.tsv | tee -a ${sample_id}_gtdbtk.log
        
        echo "Low confidence (ANI <90%):" | tee -a ${sample_id}_gtdbtk.log
        awk -F'\\t' 'NR>1 && \$17<90 {count++} END {print count+0}' ${sample_id}_gtdbtk/gtdbtk.bac120.summary.tsv | tee -a ${sample_id}_gtdbtk.log
    fi
    
    # Clean up temp directory
    rm -rf \${TMPDIR}
    
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        gtdbtk: \$(gtdbtk --version 2>&1 | grep -o 'gtdbtk: version [0-9.]*' | sed 's/gtdbtk: version //' || echo "2.3.2")
    END_VERSIONS
    """
}
