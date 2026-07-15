#!/bin/bash
# archive_old_data.sh
# Archive old/processed SRR samples to compressed archives or S3 Glacier
# Run: ./archive_old_data.sh [--dry-run] [--s3] [--sample SRR12345]

set -e

PROJECT_DIR="/home/nicolaedrabcinski/upgrade"
ARCHIVE_DIR="$PROJECT_DIR/archives"
DATA_DIR="$PROJECT_DIR/data"
RESULTS_DIR="$PROJECT_DIR/results"
LOG_FILE="$PROJECT_DIR/logs/archive_$(date +%Y%m%d_%H%M%S).log"

DRY_RUN=false
USE_S3=false
SPECIFIC_SAMPLE=""
S3_BUCKET="upgrade-archives"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --s3) USE_S3=true; shift ;;
        --sample) SPECIFIC_SAMPLE="$2"; shift 2 ;;
        --bucket) S3_BUCKET="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--s3] [--sample SRR12345] [--bucket bucket-name]"
            echo ""
            echo "Options:"
            echo "  --dry-run    Show what would be archived without making changes"
            echo "  --s3         Upload archives to S3 Glacier (requires AWS CLI)"
            echo "  --sample     Archive specific sample only"
            echo "  --bucket     S3 bucket name (default: upgrade-archives)"
            exit 0
            ;;
        *) shift ;;
    esac
done

# Create directories
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$ARCHIVE_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}" | tee -a "$LOG_FILE"
}

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}❌ $1${NC}" | tee -a "$LOG_FILE"
}

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║          UPGRADE Data Archival Script                     ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

log "=== UPGRADE Data Archival Started ==="
log "Dry run: $DRY_RUN"
log "Use S3: $USE_S3"
[ -n "$SPECIFIC_SAMPLE" ] && log "Specific sample: $SPECIFIC_SAMPLE"

# Check AWS CLI if S3 mode
if [ "$USE_S3" == "true" ]; then
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI not found. Install with: pip install awscli"
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Run: aws configure"
        exit 1
    fi
    
    log_success "AWS CLI configured and authenticated"
fi

# Find samples with completed results (processed samples)
get_processed_samples() {
    # Get all SRR directories from results
    local processed=()
    
    for result_dir in "$RESULTS_DIR"/SRR* "$RESULTS_DIR"/sample_SRR*; do
        if [ -d "$result_dir" ]; then
            local sample_name=$(basename "$result_dir" | sed 's/sample_//')
            # Check if corresponding data directory exists
            if [ -d "$DATA_DIR/$sample_name" ]; then
                processed+=("$sample_name")
            fi
        fi
    done
    
    echo "${processed[@]}" | tr ' ' '\n' | sort -u
}

# Archive a single sample
archive_sample() {
    local sample="$1"
    local sample_dir="$DATA_DIR/$sample"
    
    if [ ! -d "$sample_dir" ]; then
        log_warning "Sample directory not found: $sample_dir"
        return 1
    fi
    
    local size=$(du -sh "$sample_dir" 2>/dev/null | cut -f1)
    local file_count=$(find "$sample_dir" -type f 2>/dev/null | wc -l)
    
    log_info "Processing: $sample ($size, $file_count files)"
    
    if [ "$DRY_RUN" == "true" ]; then
        log_warning "Would create: $ARCHIVE_DIR/${sample}.tar.gz"
        [ "$USE_S3" == "true" ] && log_warning "Would upload to: s3://$S3_BUCKET/data/${sample}.tar.gz"
        return 0
    fi
    
    # Create compressed archive
    log "Creating archive: ${sample}.tar.gz"
    local archive_path="$ARCHIVE_DIR/${sample}.tar.gz"
    
    tar -czf "$archive_path" -C "$DATA_DIR" "$sample" 2>/dev/null
    
    local archive_size=$(du -sh "$archive_path" 2>/dev/null | cut -f1)
    log_success "Archive created: $archive_size (compressed from $size)"
    
    if [ "$USE_S3" == "true" ]; then
        log "Uploading to S3 Glacier..."
        
        if aws s3 cp "$archive_path" \
            "s3://$S3_BUCKET/data/${sample}.tar.gz" \
            --storage-class GLACIER \
            --quiet; then
            
            log_success "Uploaded to S3: s3://$S3_BUCKET/data/${sample}.tar.gz"
            
            # Remove local archive after successful S3 upload
            rm "$archive_path"
            log "Local archive removed (stored in S3)"
        else
            log_error "S3 upload failed for $sample"
            return 1
        fi
    fi
    
    # Remove original directory after archival
    rm -rf "$sample_dir"
    log_success "Archived and removed: $sample ($size freed)"
    
    return 0
}

# Main execution
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "Finding samples to archive..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

INITIAL_DATA_SIZE=$(du -sh "$DATA_DIR" 2>/dev/null | cut -f1)
log "Initial data/ size: $INITIAL_DATA_SIZE"

# Determine which samples to archive
if [ -n "$SPECIFIC_SAMPLE" ]; then
    SAMPLES="$SPECIFIC_SAMPLE"
    SAMPLE_COUNT=1
else
    SAMPLES=$(get_processed_samples)
    SAMPLE_COUNT=$(echo "$SAMPLES" | grep -c "SRR" 2>/dev/null || echo "0")
fi

if [ "$SAMPLE_COUNT" -eq 0 ] || [ -z "$SAMPLES" ]; then
    log_warning "No processed samples found to archive"
    exit 0
fi

log "Found $SAMPLE_COUNT processed sample(s) to archive"
echo ""

# Archive each sample
SUCCESS_COUNT=0
FAIL_COUNT=0

for sample in $SAMPLES; do
    [ -z "$sample" ] && continue
    
    if archive_sample "$sample"; then
        ((SUCCESS_COUNT++))
    else
        ((FAIL_COUNT++))
    fi
    
    echo ""
done

# Summary
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                  ARCHIVAL SUMMARY                         ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

if [ "$DRY_RUN" == "false" ]; then
    FINAL_DATA_SIZE=$(du -sh "$DATA_DIR" 2>/dev/null | cut -f1)
    ARCHIVE_TOTAL=$(du -sh "$ARCHIVE_DIR" 2>/dev/null | cut -f1)
    
    log_success "Samples archived: $SUCCESS_COUNT"
    [ "$FAIL_COUNT" -gt 0 ] && log_error "Failed: $FAIL_COUNT"
    echo ""
    log "Data directory: $INITIAL_DATA_SIZE → $FINAL_DATA_SIZE"
    [ "$USE_S3" == "false" ] && log "Local archives: $ARCHIVE_TOTAL"
    [ "$USE_S3" == "true" ] && log "Archives stored in: s3://$S3_BUCKET/data/"
    echo ""
    log_success "Archival completed!"
else
    echo -e "${YELLOW}🔍 Dry run completed.${NC}"
    echo ""
    echo "Samples that would be archived: $SAMPLE_COUNT"
    echo ""
    echo "To execute archival:"
    echo "  $0                    # Archive to local"
    echo "  $0 --s3               # Archive to S3 Glacier"
    echo "  $0 --sample SRR12345  # Archive specific sample"
fi

log "=== UPGRADE Data Archival Finished ==="
