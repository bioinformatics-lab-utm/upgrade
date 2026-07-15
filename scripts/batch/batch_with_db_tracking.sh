#!/bin/bash
# Batch runner with database tracking
# Creates pipeline_run records in web platform database

# Note: no 'set -e' to allow processing to continue after pipeline failures

# Configuration
DATA_DIR="/home/nicolaedrabcinski/upgrade/data"
RESULTS_BASE="/home/nicolaedrabcinski/upgrade/results"
WORK_BASE="/tmp/nextflow/work"
NEXTFLOW_SCRIPT="/home/nicolaedrabcinski/upgrade/nextflow/main.nf"
NEXTFLOW_CONFIG="/home/nicolaedrabcinski/upgrade/nextflow/nextflow.config"
DB_CONTAINER="upgrade_postgres"
DB_USER="upgrade"
DB_NAME="upgrade_db"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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
echo "  🚀 BATCH NEXTFLOW WITH DATABASE TRACKING"
echo "================================================================================"
echo ""

# Find all FASTQ files
echo "📂 Scanning for FASTQ files in $DATA_DIR..."
FASTQ_FILES=()

while IFS= read -r -d '' fastq_file; do
    sample_dir=$(dirname "$fastq_file")
    sample_dir=$(dirname "$sample_dir")
    sample_code=$(basename "$sample_dir")
    
    if [[ $sample_code =~ ^(SRR|ERR|DRR)[0-9]+ ]]; then
        # Get file size in bytes for sorting
        file_size=$(stat -c%s "$fastq_file" 2>/dev/null || echo 0)
        FASTQ_FILES+=("$file_size:$sample_code:$fastq_file")
    fi
done < <(find "$DATA_DIR" -type f \( -name "*.fastq" -o -name "*.fastq.gz" \) -print0 2>/dev/null)

# Sort by file size (first field) numerically, then remove size prefix
mapfile -t SORTED_FILES < <(printf '%s\n' "${FASTQ_FILES[@]}" | sort -t: -k1 -n -u | sed 's/^[0-9]*://')

echo -e "${GREEN}✓ Found ${#SORTED_FILES[@]} FASTQ files${NC}"
echo ""

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

# Helper function: create sample in database
create_sample_if_not_exists() {
    local sample_code="$1"
    local fastq_path="$2"
    
    # Check if sample exists
    local exists=$(docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT COUNT(*) FROM samples WHERE sample_code = '$sample_code';")
    
    if [[ $(echo "$exists" | tr -d ' ') -eq 0 ]]; then
        # Create sample
        docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
            "INSERT INTO samples (sample_code, sample_type, collection_date, notes, created_at)
             VALUES ('$sample_code', 'metagenomic', CURRENT_DATE, 'Batch imported from $fastq_path', NOW())
             ON CONFLICT (sample_code) DO NOTHING;" > /dev/null 2>&1
        echo -e "  ${GREEN}✓ Created sample record${NC}" >&2
    fi
    
    # Get sample_id
    docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT sample_id FROM samples WHERE sample_code = '$sample_code';" | tr -d ' '
}

# Helper function: create pipeline_run in database
create_pipeline_run() {
    local sample_id="$1"
    local sample_code="$2"
    local results_path="$3"
    local log_path="$4"
    
    local job_id="batch_${sample_code}_$(date +%Y%m%d_%H%M%S)"
    
    local pipeline_id=$(docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
        "INSERT INTO pipeline_runs 
         (sample_id, sample_name, pipeline_name, parameters, status, job_id, results_path, log_file_path, created_at, started_at)
         VALUES 
         ($sample_id, '$sample_code', 'nextflow_pipeline', '{}'::jsonb, 'running', '$job_id', '$results_path', '$log_path', NOW(), NOW())
         RETURNING pipeline_id;" | tr -d ' ')
    
    echo "$pipeline_id"
}

# Helper function: update pipeline status
update_pipeline_status() {
    local pipeline_id="$1"
    local status="$2"
    local error_msg="$3"
    
    if [[ -n "$error_msg" ]]; then
        # Escape single quotes in error message
        error_msg="${error_msg//\'/\'\'}"
        docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
            "UPDATE pipeline_runs SET status = '$status', error_message = '$error_msg', completed_at = NOW() WHERE pipeline_id = $pipeline_id;"
    else
        docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
            "UPDATE pipeline_runs SET status = '$status', completed_at = NOW() WHERE pipeline_id = $pipeline_id;"
    fi
}

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
    
    # Check if already completed
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
    
    input_dir=$(dirname "$fastq_path")
    log_path="$results_dir/nextflow.log"
    
    echo "  Input:   $input_dir"
    echo "  Output:  $results_dir"
    echo "  Work:    $work_dir"
    echo ""
    
    # Create database records
    echo -e "  ${BLUE}→ Creating database records...${NC}"
    sample_id=$(create_sample_if_not_exists "$sample_code" "$fastq_path")
    
    if [[ -z "$sample_id" ]]; then
        echo -e "  ${RED}✗ Failed to create sample record${NC}"
        ((STATS_FAILED++))
        ((idx++))
        continue
    fi
    
    pipeline_id=$(create_pipeline_run "$sample_id" "$sample_code" "$results_dir" "$log_path")
    
    if [[ -z "$pipeline_id" ]]; then
        echo -e "  ${RED}✗ Failed to create pipeline record${NC}"
        ((STATS_FAILED++))
        ((idx++))
        continue
    fi
    
    echo -e "  ${GREEN}✓ Pipeline record created (ID: $pipeline_id)${NC}"
    echo ""
    
    # Clean work directory to prevent cache collisions
    if [[ -d "$work_dir" ]]; then
        echo -e "  ${YELLOW}→ Cleaning work directory...${NC}"
        rm -rf "$work_dir"
    fi
    
    # Run Nextflow
    start_time=$(date +%s)
    
    echo -e "  ${BLUE}→ Starting Nextflow pipeline...${NC}"
    
    # Run nextflow synchronously
    nextflow run "$NEXTFLOW_SCRIPT" \
        -c "$NEXTFLOW_CONFIG" \
        --input_dir "$input_dir" \
        --outdir "$results_dir" \
        --sample_name "$sample_code" \
        -work-dir "$work_dir" \
        -profile docker \
        -resume \
        > "$log_path" 2>&1
    
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        hours=$((duration / 3600))
        minutes=$(((duration % 3600) / 60))
        
        echo -e "  ${GREEN}✓ Pipeline completed successfully${NC}"
        echo "  Duration: ${hours}h ${minutes}m"
        
        # Update database
        update_pipeline_status "$pipeline_id" "completed" ""
        
        ((STATS_COMPLETED++))
    else
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        
        echo -e "  ${RED}✗ Pipeline failed${NC}"
        echo "  Duration: ${duration}s"
        echo "  Check log: $log_path"
        
        # Update database
        error_msg=$(tail -20 "$log_path" 2>/dev/null | tr '\n' ' ' | head -c 200)
        update_pipeline_status "$pipeline_id" "failed" "$error_msg"
        
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
echo ""
echo "View results on web platform: http://100.72.39.49:3000/pipeline"
