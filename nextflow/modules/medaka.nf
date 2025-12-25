#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

/*
 * MEDAKA - ONT-specific polishing for assembled contigs
 * Corrects errors in Flye assembly using original ONT reads
 * Critical for improving gene prediction accuracy
 */

process MEDAKA {
    tag "${sample_id}"
    
    input:
    tuple val(sample_id), path(assembly), path(reads)
    
    output:
    tuple val(sample_id), path("${sample_id}_polished.fasta.gz"), emit: polished_assembly
    tuple val(sample_id), path("${sample_id}_medaka.log"), emit: log
    tuple val(sample_id), path("${sample_id}_consensus_probs.hdf"), emit: hdf, optional: true
    
    script:
    """
    # Get number of threads
    THREADS=${task.cpus}
    
    echo "Starting Medaka polishing for ${sample_id}"
    echo "Assembly: ${assembly}"
    echo "Reads: ${reads}"
    echo "Threads: \${THREADS}"
    echo "Model: ${params.medaka_model}"
    
    # Decompress assembly if needed
    if [[ ${assembly} == *.gz ]]; then
        echo "Decompressing assembly..."
        gunzip -c ${assembly} > assembly.fasta
    else
        cp ${assembly} assembly.fasta
    fi
    
    # Decompress reads if needed
    if [[ ${reads} == *.gz ]]; then
        echo "Decompressing reads..."
        gunzip -c ${reads} > reads.fastq
    else
        cp ${reads} reads.fastq
    fi
    
    # Run Medaka consensus
    echo "Running Medaka consensus polishing..."
    medaka_consensus \\
        -i reads.fastq \\
        -d assembly.fasta \\
        -o medaka_output \\
        -t \${THREADS} \\
        -m ${params.medaka_model} \\
        > ${sample_id}_medaka.log 2>&1
    
    # Check if polishing succeeded
    if [ -f medaka_output/consensus.fasta ]; then
        echo "Medaka polishing completed successfully"
        
        # Calculate statistics
        CONTIGS_IN=\$(grep -c "^>" assembly.fasta || true)
        CONTIGS_OUT=\$(grep -c "^>" medaka_output/consensus.fasta || true)
        
        echo "Input contigs: \${CONTIGS_IN}" | tee -a ${sample_id}_medaka.log
        echo "Output contigs: \${CONTIGS_OUT}" | tee -a ${sample_id}_medaka.log
        
        # Compress output
        gzip -c medaka_output/consensus.fasta > ${sample_id}_polished.fasta.gz
        
        # Copy HDF file if exists
        if [ -f medaka_output/consensus_probs.hdf ]; then
            cp medaka_output/consensus_probs.hdf ${sample_id}_consensus_probs.hdf
        fi
        
        echo "Polished assembly saved to ${sample_id}_polished.fasta.gz"
    else
        echo "ERROR: Medaka polishing failed!" | tee -a ${sample_id}_medaka.log
        exit 1
    fi
    
    # Cleanup
    rm -f assembly.fasta reads.fastq
    """
}

/*
 * MEDAKA_STATS - Generate statistics for polished assembly
 */
process MEDAKA_STATS {
    tag "${sample_id}"
    
    input:
    tuple val(sample_id), path(original), path(polished)
    
    output:
    tuple val(sample_id), path("${sample_id}_medaka_stats.txt"), emit: stats
    
    script:
    """
    echo "Medaka Polishing Statistics for ${sample_id}" > ${sample_id}_medaka_stats.txt
    echo "==========================================" >> ${sample_id}_medaka_stats.txt
    echo "" >> ${sample_id}_medaka_stats.txt
    
    # Decompress files
    if [[ ${original} == *.gz ]]; then
        gunzip -c ${original} > original.fasta
    else
        cp ${original} original.fasta
    fi
    
    if [[ ${polished} == *.gz ]]; then
        gunzip -c ${polished} > polished.fasta
    else
        cp ${polished} polished.fasta
    fi
    
    # Calculate stats for original
    echo "ORIGINAL ASSEMBLY:" >> ${sample_id}_medaka_stats.txt
    awk '/^>/ {if (seqlen) print seqlen; seqlen=0; next} {seqlen+=length(\$0)} END {if (seqlen) print seqlen}' original.fasta | \\
    sort -rn > /tmp/lengths_orig.txt
    
    awk 'BEGIN {sum=0; count=0; min=999999999; max=0} 
         {sum+=\$1; count++; if(\$1<min) min=\$1; if(\$1>max) max=\$1} 
         END {
            printf "  Contigs: %d\\n", count;
            printf "  Total length: %d bp\\n", sum;
            printf "  Mean length: %.0f bp\\n", sum/count;
            printf "  Min length: %d bp\\n", min;
            printf "  Max length: %d bp\\n", max;
            print sum > "/tmp/total_orig.txt"
         }' /tmp/lengths_orig.txt >> ${sample_id}_medaka_stats.txt
    
    # Calculate N50
    awk 'BEGIN {sum=0} {lengths[NR]=\$1; sum+=\$1} END {target=int(sum/2); cumsum=0; for(i=1; i<=NR; i++) {cumsum+=lengths[i]; if(cumsum>=target) {print "  N50: " lengths[i] " bp"; exit}}}' /tmp/lengths_orig.txt >> ${sample_id}_medaka_stats.txt
    
    echo "" >> ${sample_id}_medaka_stats.txt
    
    # Calculate stats for polished
    echo "POLISHED ASSEMBLY:" >> ${sample_id}_medaka_stats.txt
    awk '/^>/ {if (seqlen) print seqlen; seqlen=0; next} {seqlen+=length(\$0)} END {if (seqlen) print seqlen}' polished.fasta | \\
    sort -rn > /tmp/lengths_pol.txt
    
    awk 'BEGIN {sum=0; count=0; min=999999999; max=0} 
         {sum+=\$1; count++; if(\$1<min) min=\$1; if(\$1>max) max=\$1} 
         END {
            printf "  Contigs: %d\\n", count;
            printf "  Total length: %d bp\\n", sum;
            printf "  Mean length: %.0f bp\\n", sum/count;
            printf "  Min length: %d bp\\n", min;
            printf "  Max length: %d bp\\n", max;
            print sum > "/tmp/total_pol.txt"
         }' /tmp/lengths_pol.txt >> ${sample_id}_medaka_stats.txt
    
    # Calculate N50
    awk 'BEGIN {sum=0} {lengths[NR]=\$1; sum+=\$1} END {target=int(sum/2); cumsum=0; for(i=1; i<=NR; i++) {cumsum+=lengths[i]; if(cumsum>=target) {print "  N50: " lengths[i] " bp"; exit}}}' /tmp/lengths_pol.txt >> ${sample_id}_medaka_stats.txt
    
    echo "" >> ${sample_id}_medaka_stats.txt
    echo "Polishing completed: \$(date)" >> ${sample_id}_medaka_stats.txt
    
    # Cleanup
    rm -f original.fasta polished.fasta
    
    cat ${sample_id}_medaka_stats.txt
    """
}
