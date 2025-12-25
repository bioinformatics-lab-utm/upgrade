process DREP {
    tag "$sample_id"
    label 'process_high'

    container 'quay.io/biocontainers/drep:3.4.5--pyhdfd78af_0'

    publishDir "${params.outdir}/05_drep", mode: 'copy', pattern: "${sample_id}_drep"
    publishDir "${params.outdir}/05_drep", mode: 'copy', pattern: "*.log"

    input:
    tuple val(sample_id), path(bins, stageAs: 'bins/*')

    output:
    tuple val(sample_id), path("${sample_id}_drep/dereplicated_genomes/*.fa"), emit: dereplicated_bins
    tuple val(sample_id), path("${sample_id}_drep/data_tables/*.csv"), emit: data_tables
    tuple val(sample_id), path("${sample_id}_drep/figures/*.pdf"), emit: figures, optional: true
    tuple val(sample_id), path("${sample_id}_drep.log"), emit: log
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args = task.ext.args ?: ''
    def threads = task.cpus ?: 1
    def ani_threshold = params.drep_ani ?: 0.95
    def min_completeness = params.drep_completeness ?: 50
    def max_contamination = params.drep_contamination ?: 10
    def length_weight = params.drep_length_weight ?: 0
    def n50_weight = params.drep_n50_weight ?: 0.5
    def completeness_weight = params.drep_completeness_weight ?: 1
    def contamination_weight = params.drep_contamination_weight ?: 5
    def strain_heterogeneity_weight = params.drep_strain_heterogeneity_weight ?: 1
    
    """
    echo "Starting dRep dereplication for ${sample_id}" | tee ${sample_id}_drep.log
    echo "ANI threshold: ${ani_threshold}" | tee -a ${sample_id}_drep.log
    echo "Min completeness: ${min_completeness}%" | tee -a ${sample_id}_drep.log
    echo "Max contamination: ${max_contamination}%" | tee -a ${sample_id}_drep.log
    echo "Threads: ${threads}" | tee -a ${sample_id}_drep.log
    echo "Started: \$(date)" | tee -a ${sample_id}_drep.log
    
    # Create input directory with all bins (already staged in bins/ directory)
    mkdir -p ${sample_id}_all_bins
    
    # Copy all bins from staged directory
    echo "Copying bins..." | tee -a ${sample_id}_drep.log
    cp bins/*.fa ${sample_id}_all_bins/ 2>/dev/null || cp bins/*.fasta ${sample_id}_all_bins/ 2>/dev/null || true
    
    # Count total bins
    TOTAL_BINS=\$(ls ${sample_id}_all_bins/*.fa 2>/dev/null | wc -l)
    echo "Total bins to dereplicate: \$TOTAL_BINS" | tee -a ${sample_id}_drep.log
    
    if [ \$TOTAL_BINS -eq 0 ]; then
        echo "ERROR: No bins found for dereplication" | tee -a ${sample_id}_drep.log
        # Create empty output directories
        mkdir -p ${sample_id}_drep/dereplicated_genomes
        mkdir -p ${sample_id}_drep/data_tables
        mkdir -p ${sample_id}_drep/figures
        touch ${sample_id}_drep/dereplicated_genomes/.no_bins
        touch ${sample_id}_drep/data_tables/empty.csv
        exit 0
    fi
    
    # Run dRep dereplicate workflow
    echo "Running dRep dereplicate..." | tee -a ${sample_id}_drep.log
    
    dRep dereplicate \\
        ${sample_id}_drep \\
        -g ${sample_id}_all_bins/*.fa \\
        -p ${threads} \\
        -comp ${min_completeness} \\
        -con ${max_contamination} \\
        -sa ${ani_threshold} \\
        --N50_weight ${n50_weight} \\
        --completeness_weight ${completeness_weight} \\
        --contamination_weight ${contamination_weight} \\
        --strain_heterogeneity_weight ${strain_heterogeneity_weight} \\
        --ignoreGenomeQuality \\
        ${args} \\
        2>&1 | tee -a ${sample_id}_drep.log
    
    echo "dRep analysis completed: \$(date)" | tee -a ${sample_id}_drep.log
    
    # Count dereplicated bins
    if [ -d "${sample_id}_drep/dereplicated_genomes" ]; then
        DEREP_BINS=\$(ls ${sample_id}_drep/dereplicated_genomes/*.fa 2>/dev/null | wc -l)
        echo "Dereplicated bins (representatives): \$DEREP_BINS" | tee -a ${sample_id}_drep.log
        echo "Reduction: \$((\$TOTAL_BINS - \$DEREP_BINS)) bins removed (\$((100 - \$DEREP_BINS * 100 / \$TOTAL_BINS))% reduction)" | tee -a ${sample_id}_drep.log
    fi
    
    # Parse and report clustering results
    if [ -f "${sample_id}_drep/data_tables/Cdb.csv" ]; then
        echo "" | tee -a ${sample_id}_drep.log
        echo "=== Clustering Summary ===" | tee -a ${sample_id}_drep.log
        
        # Count primary clusters (secondary_cluster == False)
        PRIMARY=\$(awk -F',' 'NR>1 && \$2=="False" {count++} END {print count+0}' ${sample_id}_drep/data_tables/Cdb.csv)
        echo "Primary clusters: \$PRIMARY" | tee -a ${sample_id}_drep.log
        
        # Count secondary clusters
        SECONDARY=\$(awk -F',' 'NR>1 && \$2=="True" {count++} END {print count+0}' ${sample_id}_drep/data_tables/Cdb.csv)
        echo "Secondary clusters: \$SECONDARY" | tee -a ${sample_id}_drep.log
        
        echo "" | tee -a ${sample_id}_drep.log
        echo "Cluster representatives selected based on weighted scoring:" | tee -a ${sample_id}_drep.log
        echo "  - Completeness weight: ${completeness_weight}" | tee -a ${sample_id}_drep.log
        echo "  - Contamination weight: ${contamination_weight} (penalty)" | tee -a ${sample_id}_drep.log
        echo "  - N50 weight: ${n50_weight}" | tee -a ${sample_id}_drep.log
        echo "  - Length weight: ${length_weight}" | tee -a ${sample_id}_drep.log
        echo "  - Strain heterogeneity weight: ${strain_heterogeneity_weight}" | tee -a ${sample_id}_drep.log
    fi
    
    # Report winner genomes
    if [ -f "${sample_id}_drep/data_tables/Widb.csv" ]; then
        echo "" | tee -a ${sample_id}_drep.log
        echo "=== Representative Genomes (Winners) ===" | tee -a ${sample_id}_drep.log
        awk -F',' 'NR>1 {print \$1}' ${sample_id}_drep/data_tables/Widb.csv | tee -a ${sample_id}_drep.log
    fi
    
    # Create placeholder if no bins after dereplication (unlikely but possible)
    if [ ! -d "${sample_id}_drep/dereplicated_genomes" ] || [ \$(ls ${sample_id}_drep/dereplicated_genomes/*.fa 2>/dev/null | wc -l) -eq 0 ]; then
        mkdir -p ${sample_id}_drep/dereplicated_genomes
        touch ${sample_id}_drep/dereplicated_genomes/.no_dereplicated_bins
        echo "WARNING: No dereplicated bins generated" | tee -a ${sample_id}_drep.log
    fi
    
    # Ensure data_tables directory exists
    if [ ! -d "${sample_id}_drep/data_tables" ]; then
        mkdir -p ${sample_id}_drep/data_tables
        touch ${sample_id}_drep/data_tables/empty.csv
    fi

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        drep: \$(dRep --version 2>&1 | grep -o 'dRep v[0-9.]*' | sed 's/dRep v//' || echo "3.4.5")
    END_VERSIONS
    """
}
