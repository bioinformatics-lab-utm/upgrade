#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

/*
 * VIRSORTER2 - Viral sequence identification in metagenomes
 * Identifies viral contigs and prophages in assembled contigs
 * Critical for environmental surveillance and mobile AMR detection
 */

process VIRSORTER2 {
    tag "${sample_id}"
    
    input:
    tuple val(sample_id), path(assembly)
    
    output:
    tuple val(sample_id), path("${sample_id}_virsorter2/"), emit: results
    tuple val(sample_id), path("${sample_id}_virsorter2/final-viral-combined.fa"), emit: viral_seqs, optional: true
    tuple val(sample_id), path("${sample_id}_virsorter2/final-viral-score.tsv"), emit: scores, optional: true
    tuple val(sample_id), path("${sample_id}_virsorter2.log"), emit: log
    
    script:
    """
    # Get number of threads
    THREADS=${task.cpus}
    
    echo "Starting VirSorter2 analysis for ${sample_id}"
    echo "Assembly: ${assembly}"
    echo "Threads: \${THREADS}"
    echo "Min score: ${params.virsorter2_min_score}"
    echo "Min length: ${params.virsorter2_min_length}"
    
    # Decompress assembly if needed
    if [[ ${assembly} == *.gz ]]; then
        echo "Decompressing assembly..."
        gunzip -c ${assembly} > assembly.fasta
    else
        cp ${assembly} assembly.fasta
    fi
    
    # Run VirSorter2
    echo "Running VirSorter2..."
    virsorter run \\
        --seqfile assembly.fasta \\
        --working-dir ${sample_id}_virsorter2 \\
        --include-groups "dsDNAphage,ssDNA,RNA,NCLDV,lavidaviridae" \\
        --min-length ${params.virsorter2_min_length} \\
        --min-score ${params.virsorter2_min_score} \\
        --jobs \${THREADS} \\
        --db-dir ${params.virsorter2_db} \\
        --keep-original-seq \\
        > ${sample_id}_virsorter2.log 2>&1
    
    # Check if VirSorter2 succeeded
    if [ -f ${sample_id}_virsorter2/final-viral-score.tsv ]; then
        echo "VirSorter2 analysis completed successfully"
        
        # Count viral sequences
        VIRAL_COUNT=\$(tail -n +2 ${sample_id}_virsorter2/final-viral-score.tsv | wc -l)
        echo "Viral sequences identified: \${VIRAL_COUNT}" | tee -a ${sample_id}_virsorter2.log
        
        # Create summary
        echo "" >> ${sample_id}_virsorter2.log
        echo "VirSorter2 Summary:" >> ${sample_id}_virsorter2.log
        echo "==================" >> ${sample_id}_virsorter2.log
        
        # Count by category
        if [ \${VIRAL_COUNT} -gt 0 ]; then
            echo "Sequences by viral group:" >> ${sample_id}_virsorter2.log
            tail -n +2 ${sample_id}_virsorter2/final-viral-score.tsv | \\
                awk -F'\\t' '{print \$4}' | sort | uniq -c | \\
                awk '{printf "  %s: %d\\n", \$2, \$1}' >> ${sample_id}_virsorter2.log
            
            echo "" >> ${sample_id}_virsorter2.log
            echo "Max score statistics:" >> ${sample_id}_virsorter2.log
            tail -n +2 ${sample_id}_virsorter2/final-viral-score.tsv | \\
                awk -F'\\t' '{print \$3}' | \\
                awk 'BEGIN {sum=0; count=0; min=999; max=0} 
                     {sum+=\$1; count++; if(\$1<min) min=\$1; if(\$1>max) max=\$1} 
                     END {printf "  Mean: %.2f\\n  Min: %.2f\\n  Max: %.2f\\n", sum/count, min, max}' >> ${sample_id}_virsorter2.log
        else
            echo "No viral sequences identified above threshold" >> ${sample_id}_virsorter2.log
        fi
    else
        echo "WARNING: VirSorter2 analysis completed but no viral sequences found" | tee -a ${sample_id}_virsorter2.log
        mkdir -p ${sample_id}_virsorter2
        echo "No viral sequences identified" > ${sample_id}_virsorter2/no_viruses.txt
    fi
    
    # Cleanup
    rm -f assembly.fasta
    """
}

/*
 * VIRSORTER2_SUMMARY - Create summary report for viral sequences
 */
process VIRSORTER2_SUMMARY {
    tag "${sample_id}"
    
    input:
    tuple val(sample_id), path(virsorter_dir)
    
    output:
    tuple val(sample_id), path("${sample_id}_viral_summary.txt"), emit: summary
    tuple val(sample_id), path("${sample_id}_high_confidence_viruses.tsv"), emit: high_conf, optional: true
    
    script:
    """
    echo "VirSorter2 Viral Sequence Summary for ${sample_id}" > ${sample_id}_viral_summary.txt
    echo "=================================================" >> ${sample_id}_viral_summary.txt
    echo "" >> ${sample_id}_viral_summary.txt
    
    # Check if results exist
    if [ -f ${virsorter_dir}/final-viral-score.tsv ]; then
        # Count total viral sequences
        TOTAL=\$(tail -n +2 ${virsorter_dir}/final-viral-score.tsv | wc -l)
        echo "Total viral sequences identified: \${TOTAL}" >> ${sample_id}_viral_summary.txt
        echo "" >> ${sample_id}_viral_summary.txt
        
        if [ \${TOTAL} -gt 0 ]; then
            # High confidence viruses (max_score >= 0.9)
            echo "High confidence viruses (score >= 0.9):" >> ${sample_id}_viral_summary.txt
            tail -n +2 ${virsorter_dir}/final-viral-score.tsv | \\
                awk -F'\\t' '\$3 >= 0.9 {print \$0}' > ${sample_id}_high_confidence_viruses.tsv
            
            HIGH_CONF=\$(wc -l < ${sample_id}_high_confidence_viruses.tsv)
            echo "  Count: \${HIGH_CONF}" >> ${sample_id}_viral_summary.txt
            
            if [ \${HIGH_CONF} -gt 0 ]; then
                echo "  Top 5 by score:" >> ${sample_id}_viral_summary.txt
                head -1 ${virsorter_dir}/final-viral-score.tsv > header.tmp
                cat header.tmp ${sample_id}_high_confidence_viruses.tsv | \\
                    sort -t\$'\\t' -k3 -rn | head -6 | tail -5 | \\
                    awk -F'\\t' '{printf "    %s (score: %.3f, group: %s)\\n", \$1, \$3, \$4}' >> ${sample_id}_viral_summary.txt
            fi
            
            echo "" >> ${sample_id}_viral_summary.txt
            
            # Distribution by viral group
            echo "Distribution by viral group:" >> ${sample_id}_viral_summary.txt
            tail -n +2 ${virsorter_dir}/final-viral-score.tsv | \\
                awk -F'\\t' '{print \$4}' | sort | uniq -c | sort -rn | \\
                awk '{printf "  %s: %d\\n", \$2, \$1}' >> ${sample_id}_viral_summary.txt
            
            echo "" >> ${sample_id}_viral_summary.txt
            
            # Hallmark genes statistics
            echo "Hallmark genes statistics:" >> ${sample_id}_viral_summary.txt
            tail -n +2 ${virsorter_dir}/final-viral-score.tsv | \\
                awk -F'\\t' '{print \$5}' | \\
                awk 'BEGIN {sum=0; count=0} {sum+=\$1; count++} END {printf "  Mean: %.1f\\n  Total: %d\\n", sum/count, sum}' >> ${sample_id}_viral_summary.txt
        fi
    else
        echo "No viral sequences were identified" >> ${sample_id}_viral_summary.txt
        echo "This could indicate:" >> ${sample_id}_viral_summary.txt
        echo "  - No viruses present in the sample" >> ${sample_id}_viral_summary.txt
        echo "  - Viral sequences below detection threshold" >> ${sample_id}_viral_summary.txt
        echo "  - Contigs too short for reliable detection" >> ${sample_id}_viral_summary.txt
    fi
    
    echo "" >> ${sample_id}_viral_summary.txt
    echo "Analysis completed: \$(date)" >> ${sample_id}_viral_summary.txt
    
    cat ${sample_id}_viral_summary.txt
    """
}
