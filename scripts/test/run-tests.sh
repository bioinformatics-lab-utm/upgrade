#!/bin/bash

# Test Runner Script for Genomic Pipeline Platform
# This script sets up a virtual environment and runs tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
VENV_DIR="$PROJECT_ROOT/.venv"

echo "🧪 Genomic Pipeline Test Suite"
echo "================================"
echo ""

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip (suppress warnings for externally-managed environments)
echo "⬆️  Upgrading pip..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip --quiet 2>/dev/null || true

# Install dependencies
echo "📥 Installing test dependencies..."
"$VENV_DIR/bin/python" -m pip install -r "$PROJECT_ROOT/tests/requirements.txt" --quiet

echo "✅ Dependencies installed"
echo ""

# Parse command line arguments
TEST_PATH="${1:-tests/}"
TEST_MARKERS="${2:-}"
COVERAGE="${3:-yes}"


# Set test DB host for Docker Compose network
export TEST_DB_HOST=postgres

# Run tests
echo "🚀 Running tests from: $TEST_PATH"
echo ""

if [ "$COVERAGE" == "yes" ]; then
    if [ -n "$TEST_MARKERS" ]; then
        "$VENV_DIR/bin/pytest" "$TEST_PATH" -v -m "$TEST_MARKERS" --cov=. --cov-report=html --cov-report=term
    else
        "$VENV_DIR/bin/pytest" "$TEST_PATH" -v --cov=. --cov-report=html --cov-report=term
    fi
    
    echo ""
    echo "📊 Coverage report generated in htmlcov/index.html"
else
    if [ -n "$TEST_MARKERS" ]; then
        "$VENV_DIR/bin/pytest" "$TEST_PATH" -v -m "$TEST_MARKERS"
    else
        "$VENV_DIR/bin/pytest" "$TEST_PATH" -v
    fi
fi

echo ""
echo "✅ Tests completed!"

# Deactivate virtual environment
deactivate
