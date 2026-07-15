#!/bin/bash
# Check batch processing status
# Shows which samples are completed, in progress, or pending

RESULTS_DIR="/home/nicolaedrabcinski/upgrade/results"
DATA_DIR="/home/nicolaedrabcinski/upgrade/data"

echo "================================================================================"
echo "  📊 BATCH PROCESSING STATUS"
echo "================================================================================"
echo ""

# Count total FASTQ files
total_samples=$(find "$DATA_DIR" -type f \( -name "*.fastq" -o -name "*.fastq.gz" \) | \
    grep -oP '(SRR|ERR|DRR)\d+' | sort -u | wc -l)

# Count completed (have pipeline_summary.txt)
completed=$(find "$RESULTS_DIR" -name "pipeline_summary.txt" 2>/dev/null | wc -l)

# Count with results directory but no summary
in_progress=$(find "$RESULTS_DIR" -maxdepth 1 -type d -name "SRR*" -o -name "ERR*" -o -name "DRR*" 2>/dev/null | \
    while read dir; do
        if [[ ! -f "$dir/00_summary/pipeline_summary.txt" ]]; then
            echo "$dir"
        fi
    done | wc -l)

# Calculate pending
pending=$((total_samples - completed - in_progress))

echo "  Total samples:      $total_samples"
echo "  ✓ Completed:        $completed"
echo "  ⏳ In progress:     $in_progress"
echo "  ⏸️  Pending:         $pending"
echo ""

# Show progress percentage
if [[ $total_samples -gt 0 ]]; then
    percent=$((completed * 100 / total_samples))
    echo "  Progress: $percent% ($completed/$total_samples)"
fi

echo ""
echo "================================================================================"
echo ""

# Show recent completions
echo "📋 Recently completed (last 10):"
echo ""
find "$RESULTS_DIR" -name "pipeline_summary.txt" -printf '%T@ %p\n' 2>/dev/null | \
    sort -rn | head -10 | \
    while read timestamp path; do
        sample=$(echo "$path" | grep -oP '(SRR|ERR|DRR)\d+')
        date=$(date -d "@$timestamp" '+%Y-%m-%d %H:%M')
        echo "  $date  $sample"
    done

echo ""

# Show currently running (if any)
echo "🏃 Currently running:"
echo ""
running_pids=$(pgrep -f "nextflow run.*main.nf")
if [[ -n "$running_pids" ]]; then
    for pid in $running_pids; do
        cmd=$(ps -p "$pid" -o args= | grep -oP 'sample_name \K(SRR|ERR|DRR)\d+' || echo "unknown")
        echo "  PID $pid: $cmd"
    done
else
    echo "  (none)"
fi

echo ""
echo "================================================================================"

# Optional: Show disk usage
if [[ "$1" == "--disk" ]]; then
    echo ""
    echo "💾 Disk usage:"
    echo ""
    du -sh "$RESULTS_DIR" 2>/dev/null
    echo ""
    df -h "$RESULTS_DIR" | tail -1
    echo ""
    echo "================================================================================"
fi

# Optional: List pending samples
if [[ "$1" == "--pending" ]]; then
    echo ""
    echo "⏸️  Pending samples:"
    echo ""
    
    # Get all sample codes
    all_samples=($(find "$DATA_DIR" -type f \( -name "*.fastq" -o -name "*.fastq.gz" \) | \
        grep -oP '(SRR|ERR|DRR)\d+' | sort -u))
    
    # Check each one
    for sample in "${all_samples[@]}"; do
        if [[ ! -f "$RESULTS_DIR/$sample/00_summary/pipeline_summary.txt" ]]; then
            size=$(du -sh "$DATA_DIR/$sample" 2>/dev/null | cut -f1)
            echo "  $sample ($size)"
        fi
    done
    
    echo ""
    echo "================================================================================"
fi

# Optional: Show failed samples (have logs but no summary)
if [[ "$1" == "--failed" ]]; then
    echo ""
    echo "❌ Failed samples (have logs but no summary):"
    echo ""
    
    find "$RESULTS_DIR" -maxdepth 1 -type d \( -name "SRR*" -o -name "ERR*" -o -name "DRR*" \) 2>/dev/null | \
        while read dir; do
            sample=$(basename "$dir")
            if [[ -f "$dir/nextflow.log" ]] && [[ ! -f "$dir/00_summary/pipeline_summary.txt" ]]; then
                # Check if currently running
                if ! pgrep -f "sample_name $sample" > /dev/null; then
                    last_line=$(tail -1 "$dir/nextflow.log" 2>/dev/null)
                    echo "  $sample"
                    echo "    Last log: $last_line"
                fi
            fi
        done
    
    echo ""
    echo "================================================================================"
fi
