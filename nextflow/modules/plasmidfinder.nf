#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

/*
 * PLASMIDFINDER - Plasmid identification in bacterial genomes
 * Identifies plasmid sequences carrying AMR genes
 * Critical for tracking horizontal gene transfer and mobile resistance
 */

process PLASMIDFINDER {
    tag "${sample_id}"
    
    input:
    tuple val(sample_id), path(assembly)
    
    output:
    tuple val(sample_id), path("${sample_id}_plasmidfinder/"), emit: results
    tuple val(sample_id), path("${sample_id}_plasmidfinder/results_tab.tsv"), emit: table, optional: true
    tuple val(sample_id), path("${sample_id}_plasmidfinder/Hit_in_genome_seq.fsa"), emit: plasmid_seqs, optional: true
    tuple val(sample_id), path("${sample_id}_plasmidfinder.log"), emit: log
    
    script:
    """
    # Get number of threads
    THREADS=${task.cpus}
    
    echo "Starting PlasmidFinder analysis for ${sample_id}"
    echo "Assembly: ${assembly}"
    echo "Database: ${params.plasmidfinder_db}"
    echo "Min identity: ${params.plasmidfinder_min_identity}%"
    echo "Min coverage: ${params.plasmidfinder_min_coverage}%"
    
    # Decompress assembly if needed
    if [[ ${assembly} == *.gz ]]; then
        echo "Decompressing assembly..."
        gunzip -c ${assembly} > assembly.fasta
    else
        cp ${assembly} assembly.fasta
    fi
    
    # Run PlasmidFinder
    echo "Running PlasmidFinder..."
    plasmidfinder.py \\
        -i assembly.fasta \\
        -o ${sample_id}_plasmidfinder \\
        -p ${params.plasmidfinder_db} \\
        -mp blastn \\
        -x \\
        -q \\
        -l ${params.plasmidfinder_min_coverage} \\
        -t ${params.plasmidfinder_min_identity} \\
        > ${sample_id}_plasmidfinder.log 2>&1
    
    # Check if PlasmidFinder succeeded
    if [ -d ${sample_id}_plasmidfinder ]; then
        echo "PlasmidFinder analysis completed"
        
        # Count plasmids found
        if [ -f ${sample_id}_plasmidfinder/results_tab.tsv ]; then
            PLASMID_COUNT=\$(tail -n +2 ${sample_id}_plasmidfinder/results_tab.tsv | wc -l)
            echo "Plasmid sequences identified: \${PLASMID_COUNT}" | tee -a ${sample_id}_plasmidfinder.log
            
            if [ \${PLASMID_COUNT} -gt 0 ]; then
                echo "" >> ${sample_id}_plasmidfinder.log
                echo "PlasmidFinder Summary:" >> ${sample_id}_plasmidfinder.log
                echo "=====================" >> ${sample_id}_plasmidfinder.log
                
                # Show plasmid types
                echo "Identified plasmids:" >> ${sample_id}_plasmidfinder.log
                tail -n +2 ${sample_id}_plasmidfinder/results_tab.tsv | \\
                    awk -F'\\t' '{printf "  %s (identity: %.1f%%, coverage: %.1f%%)\\n", \$6, \$4, \$5}' >> ${sample_id}_plasmidfinder.log
                
                # Count by plasmid replicon type
                echo "" >> ${sample_id}_plasmidfinder.log
                echo "Plasmids by replicon type:" >> ${sample_id}_plasmidfinder.log
                tail -n +2 ${sample_id}_plasmidfinder/results_tab.tsv | \\
                    awk -F'\\t' '{print \$6}' | \\
                    sed 's/_[0-9]*\$//' | sort | uniq -c | \\
                    awk '{printf "  %s: %d\\n", \$2, \$1}' >> ${sample_id}_plasmidfinder.log
            fi
        else
            echo "No plasmid sequences identified above threshold" | tee -a ${sample_id}_plasmidfinder.log
        fi
    else
        echo "WARNING: PlasmidFinder analysis failed" | tee -a ${sample_id}_plasmidfinder.log
        mkdir -p ${sample_id}_plasmidfinder
        echo "No plasmids found" > ${sample_id}_plasmidfinder/no_plasmids.txt
    fi
    
    # Cleanup
    rm -f assembly.fasta
    """
}

/*
 * MOBSUITE - MOB-suite for comprehensive plasmid analysis
 * Reconstructs plasmids and predicts mobility
 */
process MOBSUITE {
    tag "${sample_id}"
    
    input:
    tuple val(sample_id), path(assembly)
    
    output:
    tuple val(sample_id), path("${sample_id}_mobsuite/"), emit: results
    tuple val(sample_id), path("${sample_id}_mobsuite/contig_report.txt"), emit: report, optional: true
    tuple val(sample_id), path("${sample_id}_mobsuite/plasmid_*.fasta"), emit: plasmids, optional: true
    tuple val(sample_id), path("${sample_id}_mobsuite.log"), emit: log
    
    script:
    """
    # Get number of threads
    THREADS=${task.cpus}
    
    echo "Starting MOB-suite analysis for ${sample_id}"
    echo "Assembly: ${assembly}"
    echo "Threads: \${THREADS}"
    
    # Decompress assembly if needed
    if [[ ${assembly} == *.gz ]]; then
        echo "Decompressing assembly..."
        gunzip -c ${assembly} > assembly.fasta
    else
        cp ${assembly} assembly.fasta
    fi
    
    # Run MOB-recon for plasmid reconstruction
    echo "Running MOB-recon..."
    mob_recon \\
        --infile assembly.fasta \\
        --outdir ${sample_id}_mobsuite \\
        --num_threads \${THREADS} \\
        --run_typer \\
        --keep_tmp \\
        > ${sample_id}_mobsuite.log 2>&1
    
    # Check if MOB-suite succeeded
    if [ -f ${sample_id}_mobsuite/contig_report.txt ]; then
        echo "MOB-suite analysis completed successfully"
        
        # Count reconstructed plasmids
        PLASMID_COUNT=\$(ls ${sample_id}_mobsuite/plasmid_*.fasta 2>/dev/null | wc -l)
        CHROMOSOME_COUNT=\$(ls ${sample_id}_mobsuite/chromosome*.fasta 2>/dev/null | wc -l)
        
        echo "Reconstructed plasmids: \${PLASMID_COUNT}" | tee -a ${sample_id}_mobsuite.log
        echo "Chromosome contigs: \${CHROMOSOME_COUNT}" | tee -a ${sample_id}_mobsuite.log
        
        if [ \${PLASMID_COUNT} -gt 0 ]; then
            echo "" >> ${sample_id}_mobsuite.log
            echo "MOB-suite Plasmid Summary:" >> ${sample_id}_mobsuite.log
            echo "==========================" >> ${sample_id}_mobsuite.log
            
            # Parse contig report
            if [ -f ${sample_id}_mobsuite/contig_report.txt ]; then
                echo "Plasmid characteristics:" >> ${sample_id}_mobsuite.log
                grep "plasmid" ${sample_id}_mobsuite/contig_report.txt | \\
                    awk -F'\\t' '{printf "  %s: size=%s, GC=%.1f%%, rep_type=%s\\n", \$1, \$2, \$6*100, \$9}' >> ${sample_id}_mobsuite.log
                
                # Count mobile elements
                echo "" >> ${sample_id}_mobsuite.log
                echo "Mobility analysis:" >> ${sample_id}_mobsuite.log
                
                MOBILIZABLE=\$(grep "plasmid" ${sample_id}_mobsuite/contig_report.txt | grep -c "mob_cluster" || true)
                CONJUGATIVE=\$(grep "plasmid" ${sample_id}_mobsuite/contig_report.txt | grep -c "mpf_type" || true)
                
                echo "  Mobilizable plasmids: \${MOBILIZABLE}" >> ${sample_id}_mobsuite.log
                echo "  Conjugative plasmids: \${CONJUGATIVE}" >> ${sample_id}_mobsuite.log
            fi
        fi
    else
        echo "WARNING: MOB-suite analysis completed but no plasmids reconstructed" | tee -a ${sample_id}_mobsuite.log
        mkdir -p ${sample_id}_mobsuite
        echo "No plasmids reconstructed" > ${sample_id}_mobsuite/no_plasmids.txt
    fi
    
    # Cleanup
    rm -f assembly.fasta
    """
}

/*
 * PLASMID_SUMMARY - Combined summary for plasmid detection
 */
process PLASMID_SUMMARY {
    tag "${sample_id}"
    
    input:
    tuple val(sample_id), path(plasmidfinder_dir), path(mobsuite_dir)
    
    output:
    tuple val(sample_id), path("${sample_id}_plasmid_combined_summary.txt"), emit: summary
    
    script:
    """
    echo "Combined Plasmid Analysis Summary for ${sample_id}" > ${sample_id}_plasmid_combined_summary.txt
    echo "===================================================" >> ${sample_id}_plasmid_combined_summary.txt
    echo "" >> ${sample_id}_plasmid_combined_summary.txt
    
    # PlasmidFinder results
    echo "=== PlasmidFinder Results ===" >> ${sample_id}_plasmid_combined_summary.txt
    if [ -f ${plasmidfinder_dir}/results_tab.tsv ]; then
        PFINDER_COUNT=\$(tail -n +2 ${plasmidfinder_dir}/results_tab.tsv | wc -l)
        echo "Plasmid replicons identified: \${PFINDER_COUNT}" >> ${sample_id}_plasmid_combined_summary.txt
        
        if [ \${PFINDER_COUNT} -gt 0 ]; then
            echo "" >> ${sample_id}_plasmid_combined_summary.txt
            echo "Top matches:" >> ${sample_id}_plasmid_combined_summary.txt
            tail -n +2 ${plasmidfinder_dir}/results_tab.tsv | \\
                sort -t\$'\\t' -k4 -rn | head -5 | \\
                awk -F'\\t' '{printf "  - %s: %.1f%% identity, %.1f%% coverage\\n", \$6, \$4, \$5}' >> ${sample_id}_plasmid_combined_summary.txt
        fi
    else
        echo "No plasmids detected" >> ${sample_id}_plasmid_combined_summary.txt
    fi
    
    echo "" >> ${sample_id}_plasmid_combined_summary.txt
    
    # MOB-suite results
    echo "=== MOB-suite Results ===" >> ${sample_id}_plasmid_combined_summary.txt
    if [ -f ${mobsuite_dir}/contig_report.txt ]; then
        MOBSUITE_COUNT=\$(grep -c "plasmid" ${mobsuite_dir}/contig_report.txt || echo "0")
        echo "Reconstructed plasmids: \${MOBSUITE_COUNT}" >> ${sample_id}_plasmid_combined_summary.txt
        
        if [ \${MOBSUITE_COUNT} -gt 0 ]; then
            echo "" >> ${sample_id}_plasmid_combined_summary.txt
            echo "Plasmid details:" >> ${sample_id}_plasmid_combined_summary.txt
            grep "plasmid" ${mobsuite_dir}/contig_report.txt | \\
                awk -F'\\t' '{printf "  - %s: %s bp (rep: %s)\\n", \$1, \$2, \$9}' >> ${sample_id}_plasmid_combined_summary.txt
        fi
    else
        echo "No plasmids reconstructed" >> ${sample_id}_plasmid_combined_summary.txt
    fi
    
    echo "" >> ${sample_id}_plasmid_combined_summary.txt
    echo "=== Recommendation ===" >> ${sample_id}_plasmid_combined_summary.txt
    echo "- Check plasmid sequences for AMR genes (Abricate/DeepARG)" >> ${sample_id}_plasmid_combined_summary.txt
    echo "- Investigate mobile plasmids for horizontal gene transfer" >> ${sample_id}_plasmid_combined_summary.txt
    echo "- Verify plasmid-chromosome boundaries if needed" >> ${sample_id}_plasmid_combined_summary.txt
    
    echo "" >> ${sample_id}_plasmid_combined_summary.txt
    echo "Analysis completed: \$(date)" >> ${sample_id}_plasmid_combined_summary.txt
    
    cat ${sample_id}_plasmid_combined_summary.txt
    """
}
