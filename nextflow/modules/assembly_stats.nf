// Assembly Statistics - Comprehensive quality metrics
// Calculate N50, L50, GC content, coverage, etc.

process ASSEMBLY_STATS {
    tag "${sample_id}"
    container 'quay.io/biocontainers/biopython:1.78'
    
    publishDir "${params.outdir}/03_assembly/stats", mode: 'copy'
    
    input:
    tuple val(sample_id), path(assembly)
    
    output:
    tuple val(sample_id), path("${sample_id}_assembly_stats.txt"), emit: stats
    tuple val(sample_id), path("${sample_id}_assembly_stats.json"), emit: json
    path "versions.yml", emit: versions
    
    script:
    """
    #!/usr/bin/env python3
    import json
    import gzip
    from Bio import SeqIO
    import statistics
    
    # Read assembly (handle both gzipped and uncompressed)
    if "${assembly}".endswith('.gz'):
        with gzip.open("${assembly}", "rt") as handle:
            sequences = list(SeqIO.parse(handle, "fasta"))
    else:
        sequences = list(SeqIO.parse("${assembly}", "fasta"))
    
    if not sequences:
        print("No sequences found in assembly")
        exit(1)
    
    # Calculate basic statistics
    lengths = [len(seq) for seq in sequences]
    total_length = sum(lengths)
    num_contigs = len(sequences)
    
    # Sort lengths for N50/L50 calculation
    sorted_lengths = sorted(lengths, reverse=True)
    
    # Calculate N50, N75, N90
    def calculate_nx(lengths_sorted, target_percent):
        target_length = sum(lengths_sorted) * (target_percent / 100)
        cumsum = 0
        nx = 0
        lx = 0
        for i, length in enumerate(lengths_sorted):
            cumsum += length
            if cumsum >= target_length:
                nx = length
                lx = i + 1
                break
        return nx, lx
    
    n50, l50 = calculate_nx(sorted_lengths, 50)
    n75, l75 = calculate_nx(sorted_lengths, 75)
    n90, l90 = calculate_nx(sorted_lengths, 90)
    
    # GC content
    total_gc = sum(seq.seq.count('G') + seq.seq.count('C') for seq in sequences)
    total_at = sum(seq.seq.count('A') + seq.seq.count('T') for seq in sequences)
    total_n = sum(seq.seq.count('N') for seq in sequences)
    gc_content = (total_gc / (total_gc + total_at)) * 100 if (total_gc + total_at) > 0 else 0
    
    # Calculate gaps
    num_gaps = sum(str(seq.seq).count('N') + str(seq.seq).count('n') for seq in sequences)
    
    # Statistics
    stats = {
        'sample_id': '${sample_id}',
        'total_length': total_length,
        'num_contigs': num_contigs,
        'num_scaffolds': num_contigs,  # Same for most assemblers
        'n50': n50,
        'n75': n75,
        'n90': n90,
        'l50': l50,
        'l75': l75,
        'l90': l90,
        'longest_contig': max(lengths),
        'shortest_contig': min(lengths),
        'mean_contig_length': statistics.mean(lengths),
        'median_contig_length': statistics.median(lengths),
        'gc_content': round(gc_content, 2),
        'num_gaps': num_gaps,
        'num_n_bases': total_n,
        'percent_n_bases': round((total_n / total_length) * 100, 2) if total_length > 0 else 0
    }
    
    # Write text report
    with open("${sample_id}_assembly_stats.txt", "w") as f:
        f.write("Assembly Statistics for ${sample_id}\\n")
        f.write("=" * 50 + "\\n\\n")
        f.write(f"Total Length: {stats['total_length']:,} bp\\n")
        f.write(f"Number of Contigs: {stats['num_contigs']:,}\\n")
        f.write(f"\\nN-Statistics:\\n")
        f.write(f"  N50: {stats['n50']:,} bp (L50: {stats['l50']})\\n")
        f.write(f"  N75: {stats['n75']:,} bp (L75: {stats['l75']})\\n")
        f.write(f"  N90: {stats['n90']:,} bp (L90: {stats['l90']})\\n")
        f.write(f"\\nLength Statistics:\\n")
        f.write(f"  Longest Contig: {stats['longest_contig']:,} bp\\n")
        f.write(f"  Shortest Contig: {stats['shortest_contig']:,} bp\\n")
        f.write(f"  Mean Length: {stats['mean_contig_length']:,.2f} bp\\n")
        f.write(f"  Median Length: {stats['median_contig_length']:,} bp\\n")
        f.write(f"\\nComposition:\\n")
        f.write(f"  GC Content: {stats['gc_content']}%\\n")
        f.write(f"  Number of Gaps: {stats['num_gaps']:,}\\n")
        f.write(f"  N bases: {stats['num_n_bases']:,} ({stats['percent_n_bases']}%)\\n")
    
    # Write JSON
    with open("${sample_id}_assembly_stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    
    print("Assembly statistics calculated successfully")
    
    # Create versions file
    with open("versions.yml", "w") as f:
        f.write('"${task.process}":\\n')
        f.write('    biopython: "1.78"\\n')
    """
    
    stub:
    """
    touch ${sample_id}_assembly_stats.txt
    echo '{}' > ${sample_id}_assembly_stats.json
    touch versions.yml
    """
}

// QUAST - Quality Assessment Tool for Genome Assemblies
process QUAST {
    tag "${sample_id}"
    container 'staphb/quast:5.2.0'
    
    publishDir "${params.outdir}/03_assembly/quast", mode: 'copy'
    
    input:
    tuple val(sample_id), path(assembly)
    
    output:
    tuple val(sample_id), path("${sample_id}_quast/*"), emit: results
    tuple val(sample_id), path("${sample_id}_quast/report.tsv"), emit: report
    path "versions.yml", emit: versions
    
    script:
    def reference = params.quast_reference ? "-r ${params.quast_reference}" : ""
    """
    quast.py \\
        ${assembly} \\
        ${reference} \\
        -o ${sample_id}_quast \\
        --threads ${task.cpus} \\
        --min-contig ${params.quast_min_contig} \\
        --labels ${sample_id}
    
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        quast: \$(quast.py --version 2>&1 | sed 's/QUAST v//')
    END_VERSIONS
    """
}
