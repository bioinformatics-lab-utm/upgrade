#!/bin/bash
# organize_docs.sh
# Organize markdown files and scripts from root directory
# Run: ./organize_docs.sh [--dry-run]

set -e

PROJECT_DIR="/home/nicolaedrabcinski/upgrade"
DRY_RUN=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
if [ "$1" == "--dry-run" ]; then
    DRY_RUN=true
    echo -e "${YELLOW}🔍 DRY RUN MODE - No files will be moved${NC}"
fi

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Counters
DIRS_CREATED=0
DOCS_MOVED=0
SCRIPTS_MOVED=0

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║        UPGRADE Documentation Organization Script          ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Create directory structure
create_dirs() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Creating directory structure..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    local dirs=(
        "$PROJECT_DIR/docs/guides"
        "$PROJECT_DIR/docs/reports"
        "$PROJECT_DIR/docs/audits"
        "$PROJECT_DIR/docs/archive"
        "$PROJECT_DIR/docs/api"
        "$PROJECT_DIR/scripts/batch"
        "$PROJECT_DIR/scripts/pipeline"
        "$PROJECT_DIR/scripts/deploy"
        "$PROJECT_DIR/scripts/utils"
        "$PROJECT_DIR/scripts/cleanup"
    )
    
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            if [ "$DRY_RUN" == "true" ]; then
                log_warning "Would create: $dir"
            else
                mkdir -p "$dir"
                log_success "Created: $dir"
                ((DIRS_CREATED++))
            fi
        fi
    done
}

# Move file helper
move_file() {
    local src="$1"
    local dest_dir="$2"
    
    if [ -f "$src" ]; then
        local filename=$(basename "$src")
        if [ "$DRY_RUN" == "true" ]; then
            log_warning "Would move: $filename → $dest_dir/"
        else
            mv "$src" "$dest_dir/"
            log_success "Moved: $filename → $dest_dir/"
        fi
        return 0
    fi
    return 1
}

# Move markdown files to appropriate directories
move_docs() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Moving documentation files..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Guides - HOW TO documents
    echo ""
    echo "📚 Guides:"
    for file in "$PROJECT_DIR"/*GUIDE*.md "$PROJECT_DIR"/*_STEPS*.md "$PROJECT_DIR"/BATCH_*.md; do
        if move_file "$file" "$PROJECT_DIR/docs/guides"; then
            ((DOCS_MOVED++))
        fi
    done 2>/dev/null || true
    
    # Reports - status and technical reports
    echo ""
    echo "📊 Reports:"
    for file in "$PROJECT_DIR"/*REPORT*.md "$PROJECT_DIR"/*BOTTLENECK*.md "$PROJECT_DIR"/*OPTIMIZATION*.md; do
        # Skip audit reports (they go to audits folder)
        case "$file" in
            *AUDIT*) continue ;;
        esac
        if move_file "$file" "$PROJECT_DIR/docs/reports"; then
            ((DOCS_MOVED++))
        fi
    done 2>/dev/null || true
    
    # Archive - old versions and fix logs
    echo ""
    echo "🗄️ Archive:"
    for file in "$PROJECT_DIR"/*_OLD*.md "$PROJECT_DIR"/*FIX*.md "$PROJECT_DIR"/*SUCCESS*.md "$PROJECT_DIR"/*RESULTS*.md; do
        # Keep critical documents
        case "$file" in
            *README*|*TODO*|*CHANGELOG*) continue ;;
        esac
        if move_file "$file" "$PROJECT_DIR/docs/archive"; then
            ((DOCS_MOVED++))
        fi
    done 2>/dev/null || true
    
    # Audits - audit and implementation documents
    echo ""
    echo "🔍 Audits:"
    for file in "$PROJECT_DIR"/*AUDIT*.md "$PROJECT_DIR"/*IMPLEMENTATION*.md "$PROJECT_DIR"/*GAPS*.md "$PROJECT_DIR"/*ROADMAP*.md "$PROJECT_DIR"/*PLAN*.md; do
        if move_file "$file" "$PROJECT_DIR/docs/audits"; then
            ((DOCS_MOVED++))
        fi
    done 2>/dev/null || true
}

# Move scripts from root to scripts subdirectories
move_scripts() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Moving scripts from root..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Batch processing scripts
    echo ""
    echo "📦 Batch scripts:"
    for file in "$PROJECT_DIR"/batch*.py "$PROJECT_DIR"/batch*.sh "$PROJECT_DIR"/*_batch*.sh "$PROJECT_DIR"/check_batch*.sh "$PROJECT_DIR"/monitor_batch*.sh "$PROJECT_DIR"/start_batch*.sh; do
        if move_file "$file" "$PROJECT_DIR/scripts/batch"; then
            ((SCRIPTS_MOVED++))
        fi
    done 2>/dev/null || true
    
    # Pipeline scripts
    echo ""
    echo "🔄 Pipeline scripts:"
    for file in "$PROJECT_DIR"/launch_pipeline*.py "$PROJECT_DIR"/run_pipeline*.py "$PROJECT_DIR"/submit_pipeline*.py "$PROJECT_DIR"/submit_via_api*.py "$PROJECT_DIR"/restart_pipeline*.py "$PROJECT_DIR"/api_pipeline*.sh "$PROJECT_DIR"/*_pipeline*.sh "$PROJECT_DIR"/test_pipeline*.sh; do
        if move_file "$file" "$PROJECT_DIR/scripts/pipeline"; then
            ((SCRIPTS_MOVED++))
        fi
    done 2>/dev/null || true
    
    # Deploy scripts
    echo ""
    echo "🚀 Deploy scripts:"
    for file in "$PROJECT_DIR"/deploy*.sh "$PROJECT_DIR"/download*.sh "$PROJECT_DIR"/organize*.sh; do
        if move_file "$file" "$PROJECT_DIR/scripts/deploy"; then
            ((SCRIPTS_MOVED++))
        fi
    done 2>/dev/null || true
    
    # Utility scripts
    echo ""
    echo "🔧 Utility scripts:"
    for file in "$PROJECT_DIR"/quick_smoke_test*.sh "$PROJECT_DIR"/run-tests*.sh "$PROJECT_DIR"/filter*.sh; do
        if move_file "$file" "$PROJECT_DIR/scripts/utils"; then
            ((SCRIPTS_MOVED++))
        fi
    done 2>/dev/null || true
}

# Update references in README
update_readme() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Updating README.md..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if [ "$DRY_RUN" == "true" ]; then
        log_warning "Would update README.md with new documentation structure"
    else
        # Append documentation structure note to README
        if ! grep -q "## Documentation Structure" "$PROJECT_DIR/README.md" 2>/dev/null; then
            cat >> "$PROJECT_DIR/README.md" << 'EOF'

## Documentation Structure

Documentation has been organized into the following structure:

```
docs/
├── guides/     # How-to guides (setup, batch processing, testing)
├── reports/    # Technical and performance reports
├── audits/     # Audit reports and compliance documentation
├── archive/    # Historical fix logs and old versions
└── api/        # API documentation
```

Scripts have been organized into:

```
scripts/
├── batch/      # Batch processing scripts
├── pipeline/   # Pipeline execution scripts
├── deploy/     # Deployment and setup scripts
├── utils/      # Utility scripts
└── cleanup/    # Cleanup and maintenance scripts
```
EOF
            log_success "Updated README.md with documentation structure"
        fi
    fi
}

# Summary
show_summary() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║                 ORGANIZATION SUMMARY                      ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""
    
    if [ "$DRY_RUN" == "false" ]; then
        log_success "Directories created: $DIRS_CREATED"
        log_success "Documents moved: $DOCS_MOVED"
        log_success "Scripts moved: $SCRIPTS_MOVED"
        echo ""
        
        # Show remaining files in root
        echo "Files remaining in root:"
        ls -la "$PROJECT_DIR"/*.md 2>/dev/null | grep -E "README|TODO|CHANGELOG|CONTRIBUTING|AUDIT_CLEANUP" | awk '{print "  ✅ " $NF}'
        
        echo ""
        log_success "Organization completed successfully!"
    else
        echo -e "${YELLOW}🔍 Dry run completed.${NC}"
        echo ""
        echo "To execute organization:"
        echo "  $0"
    fi
}

# Main execution
create_dirs
move_docs
move_scripts
update_readme
show_summary
