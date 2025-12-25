#!/bin/bash
# Direct Pipeline Runner (bypasses API and MinIO)
# Usage: ./direct_pipeline_run.sh <fastq_file_or_dir> [sample_code]

set -e

INPUT_PATH=${1:-"/home/nicolaedrabcinski/upgrade/data/sample_16122025"}
SAMPLE_CODE=${2:-"direct_$(date +%s)"}

# Check input exists
if [ ! -e "$INPUT_PATH" ]; then
    echo "Error: Input not found: $INPUT_PATH"
    exit 1
fi

# Determine if input is file or directory
if [ -f "$INPUT_PATH" ]; then
    INPUT_DIR=$(dirname "$INPUT_PATH")
    FILE_NAME=$(basename "$INPUT_PATH")
elif [ -d "$INPUT_PATH" ]; then
    INPUT_DIR="$INPUT_PATH"
    FILE_NAME=$(ls "$INPUT_PATH"/*.fastq "$INPUT_PATH"/*.fastq.gz 2>/dev/null | head -1 | xargs basename)
else
    echo "Error: Input must be a file or directory"
    exit 1
fi

echo "==================================="
echo "Direct Pipeline Runner"
echo "==================================="
echo "Input: $INPUT_PATH"
echo "Input Dir: $INPUT_DIR"
echo "Sample: $SAMPLE_CODE"
echo "==================================="

# Run Nextflow directly in RQ worker container
echo -e "\nStarting Nextflow pipeline..."
docker exec upgrade_rq_worker bash -c "
    set -e
    
    # Create results directory
    RESULTS_DIR=\"/results/\${SAMPLE_CODE}\"
    mkdir -p \"\$RESULTS_DIR\"
    
    # Run Nextflow
    cd /tmp/nextflow-work
    nextflow run /nextflow/main.nf \\
        -profile docker \\
        --input_dir \"$INPUT_DIR\" \\
        --outdir \"\$RESULTS_DIR\" \\
        -work-dir /tmp/nextflow-work \\
        -with-report \"\$RESULTS_DIR/nextflow_report.html\" \\
        -with-timeline \"\$RESULTS_DIR/nextflow_timeline.html\" \\
        -with-trace \"\$RESULTS_DIR/nextflow_trace.txt\" \\
        -resume
"

EXIT_CODE=$?

echo ""
echo "==================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Pipeline completed successfully"
else
    echo "✗ Pipeline failed with exit code: $EXIT_CODE"
fi
echo "==================================="
echo "Results: /home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/"
echo ""
echo "View reports:"
echo "  firefox /home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/nextflow_report.html"
echo ""
echo "Check trace:"
echo "  cat /home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/nextflow_trace.txt"
echo "==================================="

exit $EXIT_CODE
