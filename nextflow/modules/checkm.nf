process CHECKM {
    tag "$sample_id"
    label 'process_high'

    container 'quay.io/biocontainers/checkm-genome:1.2.2--pyhdfd78af_1'

    publishDir "${params.outdir}/05_quality/${binner_name}", mode: 'copy', pattern: "*_checkm_results"
    publishDir "${params.outdir}/05_quality/${binner_name}", mode: 'copy', pattern: "*_checkm_summary.tsv"
    publishDir "${params.outdir}/05_quality/${binner_name}", mode: 'copy', pattern: "*.checkm.log"

    input:
    tuple val(sample_id), path(bins)
    val binner_name

    output:
    tuple val(sample_id), path("${sample_id}_${binner_name}_checkm_results/"), emit: results
    tuple val(sample_id), path("${sample_id}_${binner_name}_checkm_summary.tsv"), emit: summary
    tuple val(sample_id), path("${sample_id}_${binner_name}.checkm.log"), emit: log
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args = task.ext.args ?: ''
    def extension = params.checkm_extension ?: 'fa'
    def threads = task.cpus ?: 1
    def pplacer_threads = params.checkm_pplacer_threads ?: Math.max(1, (threads / 2).intValue())
    def mode = params.checkm_mode ?: 'taxonomy_wf'  // taxonomy_wf (fast) or lineage_wf (slow)
    def reduced_tree = params.checkm_reduced_tree ? '--reduced_tree' : ''
    def domain = params.checkm_domain ?: 'bacteria'  // bacteria or archaea
    
    """
    echo "Starting CheckM quality assessment for ${sample_id} (${binner_name} bins)" | tee ${sample_id}_${binner_name}.checkm.log
    echo "Input bins: ${bins}" | tee -a ${sample_id}_${binner_name}.checkm.log
    echo "Extension: ${extension}" | tee -a ${sample_id}_${binner_name}.checkm.log
    echo "Threads: ${threads}" | tee -a ${sample_id}_${binner_name}.checkm.log
    echo "Started: \$(date)" | tee -a ${sample_id}_${binner_name}.checkm.log
    
    # Create bins directory and copy bins
    mkdir -p ${sample_id}_${binner_name}_bins_input
    
    # Check if we have actual bin files or just a directory
    if [ -d "${bins}" ]; then
        echo "Copying bins from directory..." | tee -a ${sample_id}_${binner_name}.checkm.log
        cp ${bins}/*.${extension} ${sample_id}_${binner_name}_bins_input/ 2>/dev/null || echo "No .${extension} files found in directory" | tee -a ${sample_id}_${binner_name}.checkm.log
    else
        echo "Copying individual bin files..." | tee -a ${sample_id}_${binner_name}.checkm.log
        for bin_file in ${bins}; do
            if [ -f "\$bin_file" ] && [ -s "\$bin_file" ]; then
                cp "\$bin_file" ${sample_id}_${binner_name}_bins_input/
            fi
        done
    fi
    
    # Count bins
    BIN_COUNT=\$(ls ${sample_id}_${binner_name}_bins_input/*.${extension} 2>/dev/null | wc -l)
    echo "Number of bins to analyze: \$BIN_COUNT" | tee -a ${sample_id}_${binner_name}.checkm.log
    
    # Create output directory
    mkdir -p ${sample_id}_${binner_name}_checkm_results
    
    if [ \$BIN_COUNT -gt 0 ]; then
        # Run CheckM workflow (optimized mode)
        if [ "${mode}" = "taxonomy_wf" ]; then
            echo "Running CheckM taxonomy workflow (optimized, 40-60% faster)..." | tee -a ${sample_id}_${binner_name}.checkm.log
            echo "Domain: ${domain}" | tee -a ${sample_id}_${binner_name}.checkm.log
            
            checkm taxonomy_wf \\
                domain ${domain} \\
                -t ${threads} \\
                -x ${extension} \\
                --tab_table \\
                --file ${sample_id}_${binner_name}_checkm_summary.tsv \\
                ${args} \\
                ${sample_id}_${binner_name}_bins_input \\
                ${sample_id}_${binner_name}_checkm_results 2>&1 | tee -a ${sample_id}_${binner_name}.checkm.log
        else
            echo "Running CheckM lineage workflow (comprehensive but slow)..." | tee -a ${sample_id}_${binner_name}.checkm.log
            
            checkm lineage_wf \\
                -t ${threads} \\
                --pplacer_threads ${pplacer_threads} \\
                -x ${extension} \\
                --tab_table \\
                --file ${sample_id}_${binner_name}_checkm_summary.tsv \\
                ${reduced_tree} \\
                ${args} \\
                ${sample_id}_${binner_name}_bins_input \\
                ${sample_id}_${binner_name}_checkm_results 2>&1 | tee -a ${sample_id}_${binner_name}.checkm.log
        fi
        
        echo "CheckM analysis completed: \$(date)" | tee -a ${sample_id}_${binner_name}.checkm.log
        
        # Parse and report summary statistics
        if [ -f "${sample_id}_${binner_name}_checkm_summary.tsv" ]; then
            echo "=== CheckM Summary Statistics ===" | tee -a ${sample_id}_${binner_name}.checkm.log
            echo "High quality bins (>90% complete, <5% contamination):" | tee -a ${sample_id}_${binner_name}.checkm.log
            awk 'NR>1 && \$12>90 && \$13<5 {count++} END {print count+0}' ${sample_id}_${binner_name}_checkm_summary.tsv | tee -a ${sample_id}_${binner_name}.checkm.log
            
            echo "Medium quality bins (>50% complete, <10% contamination):" | tee -a ${sample_id}_${binner_name}.checkm.log
            awk 'NR>1 && \$12>50 && \$13<10 {count++} END {print count+0}' ${sample_id}_${binner_name}_checkm_summary.tsv | tee -a ${sample_id}_${binner_name}.checkm.log
            
            echo "Average completeness:" | tee -a ${sample_id}_${binner_name}.checkm.log
            awk 'NR>1 {sum+=\$12; count++} END {if(count>0) print sum/count; else print 0}' ${sample_id}_${binner_name}_checkm_summary.tsv | tee -a ${sample_id}_${binner_name}.checkm.log
            
            echo "Average contamination:" | tee -a ${sample_id}_${binner_name}.checkm.log
            awk 'NR>1 {sum+=\$13; count++} END {if(count>0) print sum/count; else print 0}' ${sample_id}_${binner_name}_checkm_summary.tsv | tee -a ${sample_id}_${binner_name}.checkm.log
        fi
    else
        echo "No bins found for CheckM analysis" | tee -a ${sample_id}_${binner_name}.checkm.log
        # Create empty output files
        touch ${sample_id}_${binner_name}_checkm_summary.tsv
        echo -e "Bin Id\\tMarker lineage\\t# genomes\\t# markers\\t# marker sets\\t0\\t1\\t2\\t3\\t4\\t5+\\tCompleteness\\tContamination\\tStrain heterogeneity" > ${sample_id}_${binner_name}_checkm_summary.tsv
    fi

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        checkm: \$(checkm 2>&1 | grep -o 'CheckM v[0-9.]*' | sed 's/CheckM v//')
    END_VERSIONS
    """
}