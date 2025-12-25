// Pipeline Summary Module
// Aggregates all results into JSON for frontend consumption

process PIPELINE_SUMMARY {
    tag "${sample_id}"
    label 'process_low'
    container 'python:3.11'
    
    publishDir "${params.outdir}/00_summary", mode: 'copy'
    
    input:
    tuple val(sample_id), path(results_dir)
    
    output:
    path "${sample_id}_summary.json", emit: json
    path "${sample_id}.summary.log", emit: log
    
    script:
    """
    # Packages already installed in upgrade-python-summary image
    echo "Starting pipeline summary generation" > ${sample_id}.summary.log
    
    # Copy generate_summary.py script into container
    cp /nextflow/scripts/generate_summary.py . || echo "Warning: generate_summary.py not found in /nextflow/scripts/"
    
    # Generate summary JSON
    if [ -f generate_summary.py ]; then
        python3 generate_summary.py \\
            ${results_dir} \\
            ${sample_id} \\
            2>&1 | tee -a ${sample_id}.summary.log
    else
        echo "ERROR: generate_summary.py not found" | tee -a ${sample_id}.summary.log
        # Create minimal summary as fallback
        echo '{"sample_id": "${sample_id}", "status": "error", "message": "generate_summary.py not found"}' > ${sample_id}_summary.json
    fi
    
    echo "Pipeline summary generation completed" >> ${sample_id}.summary.log
    """
}

process GENERATE_HTML_REPORT {
    tag "${sample_id}"
    label 'process_low'
    container 'python:3.11-slim'
    
    publishDir "${params.outdir}/00_summary", mode: 'copy'
    
    input:
    tuple val(sample_id), path(summary_json)
    
    output:
    path "${sample_id}_report.html", emit: html
    path "${sample_id}.report.log"
    
    script:
    """
    pip install jinja2 matplotlib seaborn plotly 2>&1 | tee ${sample_id}.report.log
    
    python3 /scripts/generate_html_report.py \\
        ${summary_json} \\
        ${sample_id}_report.html \\
        2>&1 | tee -a ${sample_id}.report.log
    """
}

process DIVERSITY_ANALYSIS {
    tag "${sample_id}"
    label 'process_medium'
    container 'python:3.11-slim'
    
    publishDir "${params.outdir}/12_diversity", mode: 'copy'
    
    input:
    tuple val(sample_id), path(abundance_table), path(taxonomy)
    
    output:
    path "${sample_id}_diversity.json", emit: json
    path "${sample_id}_diversity_plots/", emit: plots
    path "${sample_id}.diversity.log"
    
    script:
    """
    pip install pandas numpy scipy scikit-learn matplotlib seaborn 2>&1 | tee ${sample_id}.diversity.log
    
    python3 /scripts/calculate_diversity.py \\
        --abundance ${abundance_table} \\
        --taxonomy ${taxonomy} \\
        --output ${sample_id}_diversity.json \\
        --plots ${sample_id}_diversity_plots \\
        2>&1 | tee -a ${sample_id}.diversity.log
    """
}

process FUNCTIONAL_ENRICHMENT {
    tag "${bin_name}"
    label 'process_medium'
    container 'python:3.11-slim'
    
    publishDir "${params.outdir}/13_enrichment/${bin_name}", mode: 'copy'
    
    input:
    tuple val(bin_name), path(eggnog_annotations), path(kegg_annotations)
    
    output:
    path "${bin_name}_enrichment.json", emit: json
    path "${bin_name}_pathways.html", emit: html
    path "${bin_name}.enrichment.log"
    
    script:
    """
    pip install pandas numpy scipy matplotlib seaborn 2>&1 | tee ${bin_name}.enrichment.log
    
    python3 /scripts/functional_enrichment.py \\
        --eggnog ${eggnog_annotations} \\
        --kegg ${kegg_annotations} \\
        --bin ${bin_name} \\
        --output ${bin_name}_enrichment.json \\
        2>&1 | tee -a ${bin_name}.enrichment.log
    """
}

process AMR_RISK_ASSESSMENT {
    tag "${sample_id}"
    label 'process_low'
    container 'python:3.11-slim'
    
    publishDir "${params.outdir}/14_amr_risk", mode: 'copy'
    
    input:
    tuple val(sample_id), path(abricate_results), path(deeparg_results), path(plasmid_results)
    
    output:
    path "${sample_id}_amr_risk.json", emit: json
    path "${sample_id}_amr_report.html", emit: html
    path "${sample_id}.amr_risk.log"
    
    script:
    """
    pip install pandas numpy scikit-learn matplotlib seaborn plotly 2>&1 | tee ${sample_id}.amr_risk.log
    
    python3 /scripts/amr_risk_assessment.py \\
        --abricate ${abricate_results} \\
        --deeparg ${deeparg_results} \\
        --plasmids ${plasmid_results} \\
        --sample ${sample_id} \\
        --output ${sample_id}_amr_risk.json \\
        2>&1 | tee -a ${sample_id}.amr_risk.log
    """
}

process CLINICAL_REPORT {
    tag "${sample_id}"
    label 'process_low'
    container 'python:3.11-slim'
    
    publishDir "${params.outdir}/15_clinical_report", mode: 'copy'
    
    input:
    tuple val(sample_id), path(summary_json), path(amr_risk_json), path(taxonomy_results)
    
    output:
    path "${sample_id}_clinical_report.pdf", emit: pdf
    path "${sample_id}_clinical_report.html", emit: html
    path "${sample_id}.clinical.log"
    
    script:
    """
    pip install pandas reportlab jinja2 matplotlib seaborn 2>&1 | tee ${sample_id}.clinical.log
    
    python3 /scripts/generate_clinical_report.py \\
        --summary ${summary_json} \\
        --amr ${amr_risk_json} \\
        --taxonomy ${taxonomy_results} \\
        --sample ${sample_id} \\
        --output-pdf ${sample_id}_clinical_report.pdf \\
        --output-html ${sample_id}_clinical_report.html \\
        2>&1 | tee -a ${sample_id}.clinical.log
    """
}

workflow SUMMARY_AND_REPORTING {
    take:
    sample_id
    results_dir
    
    main:
    // Generate main summary
    PIPELINE_SUMMARY(sample_id, results_dir)
    
    // Generate HTML report
    GENERATE_HTML_REPORT(sample_id, PIPELINE_SUMMARY.out.json)
    
    emit:
    json = PIPELINE_SUMMARY.out.json
    html = GENERATE_HTML_REPORT.out.html
}
