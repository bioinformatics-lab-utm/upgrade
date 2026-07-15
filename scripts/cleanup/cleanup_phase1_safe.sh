#!/bin/bash
# cleanup_phase1_safe.sh
# Safe cleanup: Nextflow cache, test results, coverage reports
# Run: ./cleanup_phase1_safe.sh [--dry-run]

set -e

PROJECT_DIR="/home/nicolaedrabcinski/upgrade"
BACKUP_DIR="$PROJECT_DIR/backups/cleanup_$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$PROJECT_DIR/logs/cleanup_phase1_$(date +%Y%m%d).log"
DRY_RUN=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
if [ "$1" == "--dry-run" ]; then
    DRY_RUN=true
    echo -e "${YELLOW}🔍 DRY RUN MODE - No files will be deleted${NC}"
fi

# Create directories
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$BACKUP_DIR"

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

# Calculate size
get_size() {
    du -sh "$1" 2>/dev/null | cut -f1 || echo "0"
}

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║          UPGRADE Phase 1 Safe Cleanup Script              ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

log "=== UPGRADE Phase 1 Cleanup Started ==="
log "Project directory: $PROJECT_DIR"
log "Backup directory: $BACKUP_DIR"
log "Dry run: $DRY_RUN"

# Record initial size
INITIAL_SIZE=$(du -sh "$PROJECT_DIR" 2>/dev/null | cut -f1)
log "Initial project size: $INITIAL_SIZE"

# Track total recovered
TOTAL_RECOVERED_MB=0

# 1. Clean Nextflow work directory
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "Cleaning Nextflow work directory..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "$PROJECT_DIR/work" ]; then
    WORK_SIZE=$(get_size "$PROJECT_DIR/work")
    WORK_COUNT=$(find "$PROJECT_DIR/work" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
    log "Current work/ size: $WORK_SIZE ($WORK_COUNT directories)"
    
    if [ "$DRY_RUN" == "true" ]; then
        log_warning "Would delete: $PROJECT_DIR/work/* ($WORK_SIZE)"
    else
        # Backup directory listing
        ls -la "$PROJECT_DIR/work" > "$BACKUP_DIR/work_contents.txt" 2>/dev/null || true
        
        rm -rf "$PROJECT_DIR/work"/*
        log_success "Nextflow cache cleaned: $WORK_SIZE freed"
    fi
else
    log_info "No work/ directory found"
fi

# 2. Clean test result directories
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "Cleaning test result directories..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "$PROJECT_DIR/results" ]; then
    TEST_RESULTS=$(find "$PROJECT_DIR/results" -maxdepth 1 -type d -name "test_*" 2>/dev/null || true)
    TEST_COUNT=$(echo "$TEST_RESULTS" | grep -c "test_" 2>/dev/null || echo "0")
    
    if [ "$TEST_COUNT" -gt 0 ]; then
        TEST_SIZE=$(du -sch $PROJECT_DIR/results/test_* 2>/dev/null | tail -1 | cut -f1 || echo "0")
        log "Test directories found: $TEST_COUNT"
        log "Total test results size: $TEST_SIZE"
        
        if [ "$DRY_RUN" == "true" ]; then
            log_warning "Would delete $TEST_COUNT directories ($TEST_SIZE):"
            echo "$TEST_RESULTS" | head -10
            [ "$TEST_COUNT" -gt 10 ] && log "... and $(($TEST_COUNT - 10)) more"
        else
            # Backup directory listing
            echo "$TEST_RESULTS" > "$BACKUP_DIR/deleted_test_dirs.txt"
            
            echo "$TEST_RESULTS" | xargs rm -rf 2>/dev/null || true
            log_success "Test results cleaned: $TEST_SIZE freed ($TEST_COUNT directories)"
        fi
    else
        log_info "No test result directories found"
    fi
else
    log_info "No results/ directory found"
fi

# 3. Clean htmlcov directory
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "Cleaning coverage reports..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "$PROJECT_DIR/htmlcov" ]; then
    HTMLCOV_SIZE=$(get_size "$PROJECT_DIR/htmlcov")
    HTMLCOV_COUNT=$(find "$PROJECT_DIR/htmlcov" -type f 2>/dev/null | wc -l)
    log "Coverage reports: $HTMLCOV_SIZE ($HTMLCOV_COUNT files)"
    
    if [ "$DRY_RUN" == "true" ]; then
        log_warning "Would delete: $PROJECT_DIR/htmlcov/* ($HTMLCOV_SIZE)"
    else
        rm -rf "$PROJECT_DIR/htmlcov"/*
        log_success "Coverage reports cleaned: $HTMLCOV_SIZE freed"
    fi
else
    log_info "No htmlcov/ directory found"
fi

# 4. Clean __pycache__ directories
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "Cleaning Python cache..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

PYCACHE_LIST=$(find "$PROJECT_DIR" -type d -name "__pycache__" 2>/dev/null || true)
PYCACHE_COUNT=$(echo "$PYCACHE_LIST" | grep -c "__pycache__" 2>/dev/null || echo "0")

if [ "$PYCACHE_COUNT" -gt 0 ]; then
    PYCACHE_SIZE=$(du -sch $PYCACHE_LIST 2>/dev/null | tail -1 | cut -f1 || echo "0")
    log "Python cache directories: $PYCACHE_COUNT ($PYCACHE_SIZE)"
    
    if [ "$DRY_RUN" == "true" ]; then
        log_warning "Would delete: $PYCACHE_COUNT __pycache__ directories ($PYCACHE_SIZE)"
    else
        find "$PROJECT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        log_success "Python cache cleaned: $PYCACHE_SIZE freed ($PYCACHE_COUNT directories)"
    fi
else
    log_info "No __pycache__ directories found"
fi

# 5. Clean .pyc files
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "Cleaning compiled Python files..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

PYC_COUNT=$(find "$PROJECT_DIR" -name "*.pyc" 2>/dev/null | wc -l)
if [ "$PYC_COUNT" -gt 0 ]; then
    log "Compiled Python files: $PYC_COUNT"
    
    if [ "$DRY_RUN" == "true" ]; then
        log_warning "Would delete: $PYC_COUNT .pyc files"
    else
        find "$PROJECT_DIR" -name "*.pyc" -delete 2>/dev/null || true
        log_success "Compiled Python files cleaned ($PYC_COUNT files)"
    fi
else
    log_info "No .pyc files found"
fi

# 6. Clean .nextflow directory (logs)
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "Cleaning Nextflow logs..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "$PROJECT_DIR/.nextflow" ]; then
    NF_LOG_SIZE=$(get_size "$PROJECT_DIR/.nextflow")
    log "Nextflow logs size: $NF_LOG_SIZE"
    
    if [ "$DRY_RUN" == "true" ]; then
        log_warning "Would delete: $PROJECT_DIR/.nextflow/* ($NF_LOG_SIZE)"
    else
        # Keep the directory structure
        find "$PROJECT_DIR/.nextflow" -type f -delete 2>/dev/null || true
        log_success "Nextflow logs cleaned: $NF_LOG_SIZE freed"
    fi
else
    log_info "No .nextflow/ directory found"
fi

# 7. Clean coverage.xml and other temp files
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "Cleaning temporary files..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

TEMP_FILES=(
    "$PROJECT_DIR/coverage.xml"
    "$PROJECT_DIR/.coverage"
    "$PROJECT_DIR/.pytest_cache"
)

for temp_file in "${TEMP_FILES[@]}"; do
    if [ -e "$temp_file" ]; then
        TEMP_SIZE=$(get_size "$temp_file")
        log "Found: $temp_file ($TEMP_SIZE)"
        
        if [ "$DRY_RUN" == "true" ]; then
            log_warning "Would delete: $temp_file"
        else
            rm -rf "$temp_file"
            log_success "Deleted: $temp_file"
        fi
    fi
done

# Summary
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                    CLEANUP SUMMARY                        ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

if [ "$DRY_RUN" == "false" ]; then
    FINAL_SIZE=$(du -sh "$PROJECT_DIR" 2>/dev/null | cut -f1)
    log_success "Initial size: $INITIAL_SIZE"
    log_success "Final size:   $FINAL_SIZE"
    log_success "Cleanup completed successfully!"
    log ""
    log "Backup location: $BACKUP_DIR"
    log "Log file: $LOG_FILE"
else
    echo -e "${YELLOW}🔍 Dry run completed. Run without --dry-run to execute cleanup.${NC}"
    echo ""
    echo "To execute cleanup:"
    echo "  $0"
fi

echo ""
log "=== UPGRADE Phase 1 Cleanup Finished ==="
