#!/bin/bash
# Find FASTQ files with reads longer than 1000bp (Nanopore long reads)

DATA_DIR="/home/nicolaedrabcinski/upgrade/data"
MIN_LENGTH=1000

echo "Scanning for long-read FASTQ files (reads > ${MIN_LENGTH}bp)..."
echo ""

count=0
for dir in "$DATA_DIR"/SRR*/raw/ "$DATA_DIR"/ERR*/raw/ "$DATA_DIR"/DRR*/raw/; do
    [ -d "$dir" ] || continue
    
    for fastq in "$dir"/*.fastq "$dir"/*.fastq.gz; do
        [ -f "$fastq" ] || continue
        
        sample=$(basename $(dirname $(dirname "$fastq")))
        
        # Get first read length
        if [[ $fastq == *.gz ]]; then
            read_len=$(zcat "$fastq" 2>/dev/null | head -4 | tail -2 | head -1 | wc -c)
        else
            read_len=$(head -4 "$fastq" 2>/dev/null | tail -2 | head -1 | wc -c)
        fi
        
        if [ "$read_len" -gt "$MIN_LENGTH" ]; then
            size=$(du -h "$fastq" | cut -f1)
            printf "%-15s %8s  read_len=%-6d  %s\n" "$sample" "$size" "$read_len" "$fastq"
            ((count++))
        fi
    done
done

echo ""
echo "Found $count long-read samples"
