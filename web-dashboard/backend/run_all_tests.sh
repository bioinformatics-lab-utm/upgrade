#!/bin/bash
#
# Run all pytest tests for UPGRADE project
# Usage: ./run_all_tests.sh [options]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== UPGRADE Test Suite ===${NC}\n"

# Change to script directory
cd "$(dirname "$0")"

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest is not installed${NC}"
    echo "Install with: pip install -r requirements.txt"
    exit 1
fi

# Parse command line arguments
TEST_TYPE="${1:-all}"
COVERAGE="${COVERAGE:-true}"

case "$TEST_TYPE" in
    unit)
        echo -e "${YELLOW}Running unit tests only...${NC}\n"
        MARKERS="-m unit"
        ;;
    integration)
        echo -e "${YELLOW}Running integration tests only...${NC}\n"
        MARKERS="-m integration"
        ;;
    fast)
        echo -e "${YELLOW}Running fast tests (excluding slow)...${NC}\n"
        MARKERS="-m 'not slow'"
        ;;
    slow)
        echo -e "${YELLOW}Running slow tests only...${NC}\n"
        MARKERS="-m slow"
        ;;
    db)
        echo -e "${YELLOW}Running database tests only...${NC}\n"
        MARKERS="-m requires_db"
        ;;
    all)
        echo -e "${YELLOW}Running all tests...${NC}\n"
        MARKERS=""
        ;;
    *)
        echo -e "${RED}Unknown test type: $TEST_TYPE${NC}"
        echo "Usage: $0 [unit|integration|fast|slow|db|all]"
        exit 1
        ;;
esac

# Build pytest command
PYTEST_CMD="pytest tests/"

if [ "$COVERAGE" = "true" ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=. --cov-report=html --cov-report=term-missing"
fi

if [ -n "$MARKERS" ]; then
    PYTEST_CMD="$PYTEST_CMD $MARKERS"
fi

# Add verbosity
PYTEST_CMD="$PYTEST_CMD -v"

# Run tests
echo -e "${GREEN}Executing: $PYTEST_CMD${NC}\n"
eval $PYTEST_CMD

# Check exit code
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✓ All tests passed!${NC}"
    
    if [ "$COVERAGE" = "true" ]; then
        echo -e "${GREEN}✓ Coverage report generated in htmlcov/index.html${NC}"
    fi
    
    exit 0
else
    echo -e "\n${RED}✗ Some tests failed${NC}"
    exit 1
fi
