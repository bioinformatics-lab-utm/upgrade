#!/bin/bash
# cleanup_master.sh
# Master cleanup script - runs all cleanup phases
# Run: ./cleanup_master.sh [--dry-run] [--phase N]

set -e

PROJECT_DIR="/home/nicolaedrabcinski/upgrade"
SCRIPTS_DIR="$PROJECT_DIR/scripts/cleanup"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

DRY_RUN=""
PHASE=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN="--dry-run"; shift ;;
        --phase) PHASE="$2"; shift 2 ;;
        -h|--help)
            echo "UPGRADE Project Master Cleanup Script"
            echo ""
            echo "Usage: $0 [--dry-run] [--phase N]"
            echo ""
            echo "Options:"
            echo "  --dry-run    Preview changes without executing"
            echo "  --phase N    Run specific phase only (1, 2, or 3)"
            echo ""
            echo "Phases:"
            echo "  1 - Safe cleanup (cache, test results, coverage)"
            echo "  2 - Documentation organization"
            echo "  3 - Data archival (requires approval)"
            exit 0
            ;;
        *) shift ;;
    esac
done

show_banner() {
    echo ""
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════════════╗"
    echo "║                                                                   ║"
    echo "║     ██╗   ██╗██████╗  ██████╗ ██████╗  █████╗ ██████╗ ███████╗    ║"
    echo "║     ██║   ██║██╔══██╗██╔════╝ ██╔══██╗██╔══██╗██╔══██╗██╔════╝    ║"
    echo "║     ██║   ██║██████╔╝██║  ███╗██████╔╝███████║██║  ██║█████╗      ║"
    echo "║     ██║   ██║██╔═══╝ ██║   ██║██╔══██╗██╔══██║██║  ██║██╔══╝      ║"
    echo "║     ╚██████╔╝██║     ╚██████╔╝██║  ██║██║  ██║██████╔╝███████╗    ║"
    echo "║      ╚═════╝ ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝    ║"
    echo "║                                                                   ║"
    echo "║                    Project Cleanup Suite                          ║"
    echo "║                                                                   ║"
    echo "╚═══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

show_status() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}                     PROJECT STATUS                          ${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    local total_size=$(du -sh "$PROJECT_DIR" 2>/dev/null | cut -f1)
    local data_size=$(du -sh "$PROJECT_DIR/data" 2>/dev/null | cut -f1)
    local work_size=$(du -sh "$PROJECT_DIR/work" 2>/dev/null | cut -f1 || echo "0")
    local results_size=$(du -sh "$PROJECT_DIR/results" 2>/dev/null | cut -f1)
    local md_count=$(ls "$PROJECT_DIR"/*.md 2>/dev/null | wc -l || echo "0")
    local script_count=$(ls "$PROJECT_DIR"/*.sh "$PROJECT_DIR"/*.py 2>/dev/null | wc -l || echo "0")
    
    echo -e "  📁 Total project size:    ${YELLOW}$total_size${NC}"
    echo -e "  📁 data/ directory:       ${YELLOW}$data_size${NC}"
    echo -e "  📁 work/ directory:       ${YELLOW}$work_size${NC}"
    echo -e "  📁 results/ directory:    ${YELLOW}$results_size${NC}"
    echo -e "  📄 Root MD files:         ${YELLOW}$md_count${NC}"
    echo -e "  📜 Root scripts:          ${YELLOW}$script_count${NC}"
    echo ""
}

run_phase1() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  PHASE 1: Safe Cleanup (Cache, Test Results, Coverage)        ${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    
    if [ -f "$SCRIPTS_DIR/cleanup_phase1_safe.sh" ]; then
        bash "$SCRIPTS_DIR/cleanup_phase1_safe.sh" $DRY_RUN
    else
        echo -e "${RED}Error: cleanup_phase1_safe.sh not found${NC}"
        return 1
    fi
}

run_phase2() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  PHASE 2: Documentation Organization                          ${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    
    if [ -f "$SCRIPTS_DIR/organize_docs.sh" ]; then
        bash "$SCRIPTS_DIR/organize_docs.sh" $DRY_RUN
    else
        echo -e "${RED}Error: organize_docs.sh not found${NC}"
        return 1
    fi
}

run_phase3() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  PHASE 3: Data Archival (Requires Approval)                   ${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    
    if [ -z "$DRY_RUN" ]; then
        echo ""
        echo -e "${YELLOW}⚠️  WARNING: Phase 3 will archive and remove SRR sample data.${NC}"
        echo -e "${YELLOW}   This action requires explicit approval.${NC}"
        echo ""
        read -p "Do you want to proceed with data archival? (yes/no): " confirm
        
        if [ "$confirm" != "yes" ]; then
            echo -e "${BLUE}Phase 3 skipped.${NC}"
            return 0
        fi
    fi
    
    if [ -f "$SCRIPTS_DIR/archive_old_data.sh" ]; then
        bash "$SCRIPTS_DIR/archive_old_data.sh" $DRY_RUN
    else
        echo -e "${RED}Error: archive_old_data.sh not found${NC}"
        return 1
    fi
}

# Main execution
show_banner
show_status

[ -n "$DRY_RUN" ] && echo -e "${YELLOW}🔍 DRY RUN MODE - No changes will be made${NC}"

# Run phases
case $PHASE in
    0)
        # Run all phases
        run_phase1
        run_phase2
        echo ""
        echo -e "${BLUE}Phase 3 (Data Archival) is not run automatically.${NC}"
        echo -e "${BLUE}To run Phase 3: $0 --phase 3${NC}"
        ;;
    1)
        run_phase1
        ;;
    2)
        run_phase2
        ;;
    3)
        run_phase3
        ;;
    *)
        echo -e "${RED}Invalid phase: $PHASE${NC}"
        exit 1
        ;;
esac

# Final status
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}                     CLEANUP COMPLETE                          ${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"

if [ -z "$DRY_RUN" ]; then
    show_status
fi

echo ""
echo "For full audit report, see: AUDIT_CLEANUP_PLAN.md"
echo ""
