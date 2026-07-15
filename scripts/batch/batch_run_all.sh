#!/bin/bash
# Simple bash script to run all FASTQ files through Nextflow sequentially
# Usage: ./batch_run_all.sh [--limit N] [--dry-run]

set -e

# Configuration
DATA_DIR="/home/nicolaedrabcinski/upgrade/data"
RESULTS_BASE="/home/nicolaedrabcinski/upgrade/results"
WORK_BASE="/tmp/nextflow/work"
NEXTFLOW_SCRIPT="/home/nicolaedrabcinski/upgrade/nextflow/main.nf"
NEXTFLOW_CONFIG="/home/nicolaedrabcinski/upgrade/nextflow/nextflow.config"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
DRY_RUN=false
LIMIT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dry-run] [--limit N]"
            exit 1
            ;;
    esac
done

echo "================================================================================"
echo "  🚀 BATCH NEXTFLOW PIPELINE RUNNER"
echo "================================================================================"
echo ""

# Find all FASTQ files
echo "📂 Scanning for FASTQ files in $DATA_DIR..."
FASTQ_FILES=()

while IFS= read -r -d '' fastq_file; do
    # Extract sample code from path
    # Pattern: /data/SRRXXXXXXX/raw/SRRXXXXXXX.fastq
    sample_dir=$(dirname "$fastq_file")
    sample_dir=$(dirname "$sample_dir")  # Go up one more level
    sample_code=$(basename "$sample_dir")
    
    # Only process SRR/ERR/DRR accessions
    if [[ $sample_code =~ ^(SRR|ERR|DRR)[0-9]+ ]]; then
        FASTQ_FILES+=("$sample_code:$fastq_file")
    fi
done < <(find "$DATA_DIR" -type f \( -name "*.fastq" -o -name "*.fastq.gz" \) -print0 2>/dev/null)

# Sort unique sample codes
mapfile -t SORTED_FILES < <(printf '%s\n' "${FASTQ_FILES[@]}" | sort -u)

echo -e "${GREEN}✓ Found ${#SORTED_FILES[@]} FASTQ files${NC}"
echo ""

# Apply limit if specified
if [[ -n "$LIMIT" ]]; then
    SORTED_FILES=("${SORTED_FILES[@]:0:$LIMIT}")
    echo -e "${YELLOW}⚠ Limited to first $LIMIT samples${NC}"
    echo ""
fi

# Dry run mode
if [[ "$DRY_RUN" == "true" ]]; then
    echo "🔍 DRY RUN MODE - Files to be processed:"
    echo ""
    idx=1
    for entry in "${SORTED_FILES[@]}"; do
        IFS=':' read -r sample_code fastq_path <<< "$entry"
        size=$(du -h "$fastq_path" 2>/dev/null | cut -f1)
        printf "%3d. %-20s %8s  %s\n" "$idx" "$sample_code" "$size" "$fastq_path"
        ((idx++))
    done
    echo ""
    echo "Total: ${#SORTED_FILES[@]} samples"
    exit 0
fi

# Process each sample
echo "📊 Processing ${#SORTED_FILES[@]} samples sequentially"
echo ""

STATS_TOTAL=${#SORTED_FILES[@]}
STATS_COMPLETED=0
STATS_FAILED=0
STATS_SKIPPED=0

idx=1
for entry in "${SORTED_FILES[@]}"; do
    IFS=':' read -r sample_code fastq_path <<< "$entry"
    
    echo "================================================================================"
    echo -e "  [$idx/$STATS_TOTAL] ${BLUE}$sample_code${NC}"
    echo "================================================================================"
    echo "  FASTQ: $fastq_path"
    
    # Check if results already exist
    results_dir="$RESULTS_BASE/$sample_code"
    if [[ -d "$results_dir" ]] && [[ -f "$results_dir/00_summary/pipeline_summary.txt" ]]; then
        echo -e "  ${YELLOW}⊘ Results already exist, skipping${NC}"
        ((STATS_SKIPPED++))
        ((idx++))
        echo ""
        continue
    fi
    
    # Prepare directories
    work_dir="$WORK_BASE/$sample_code"
    mkdir -p "$results_dir"
    mkdir -p "$work_dir"
    
    # Determine input directory
    input_dir=$(dirname "$fastq_path")
    
    echo "  Input:   $input_dir"
    echo "  Output:  $results_dir"
    echo "  Work:    $work_dir"
    echo ""
    
    # Run Nextflow
    start_time=$(date +%s)
    
    echo -e "  ${BLUE}→ Starting Nextflow pipeline...${NC}"
    
    if nextflow run "$NEXTFLOW_SCRIPT" \
        -c "$NEXTFLOW_CONFIG" \
        --input_dir "$input_dir" \
        --output_dir "$results_dir" \
        --sample_name "$sample_code" \
        -work-dir "$work_dir" \
        -profile docker \
        -resume \
        > "$results_dir/nextflow.log" 2>&1; then
        
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        hours=$((duration / 3600))
        minutes=$(((duration % 3600) / 60))
        
        echo -e "  ${GREEN}✓ Pipeline completed successfully${NC}"
        echo "  Duration: ${hours}h ${minutes}m"
        ((STATS_COMPLETED++))
    else
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        
        echo -e "  ${RED}✗ Pipeline failed${NC}"
        echo "  Duration: ${duration}s"
        echo "  Check log: $results_dir/nextflow.log"
        ((STATS_FAILED++))
    fi
    
    echo ""
    ((idx++))
done

# Final summary
echo "================================================================================"
echo "  📊 BATCH PROCESSING COMPLETE"
echo "================================================================================"
echo "  Total samples:      $STATS_TOTAL"
echo -e "  ${GREEN}✓ Completed:        $STATS_COMPLETED${NC}"
echo -e "  ${RED}✗ Failed:           $STATS_FAILED${NC}"
echo -e "  ${YELLOW}⊘ Skipped:          $STATS_SKIPPED${NC}"
echo "================================================================================"
