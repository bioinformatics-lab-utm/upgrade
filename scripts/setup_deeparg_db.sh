#!/bin/bash
# Setup DeepARG Database
# This script downloads the DeepARG database once to a persistent location

set -e

DEEPARG_DB_DIR="/home/nicolaedrabcinski/upgrade/data/deeparg_db"
DOWNLOAD_LOG="/tmp/deeparg_download.log"

echo "==================================="
echo "DeepARG Database Setup"
echo "==================================="
echo "Target directory: $DEEPARG_DB_DIR"
echo "Expected size: ~4 GB"
echo ""

# Create directory
mkdir -p "$DEEPARG_DB_DIR"

# Check if already downloaded
if [ -d "$DEEPARG_DB_DIR/database" ] && [ -d "$DEEPARG_DB_DIR/model" ]; then
    echo "✓ DeepARG database already exists!"
    echo ""
    du -sh "$DEEPARG_DB_DIR"
    ls -lh "$DEEPARG_DB_DIR"
    echo ""
    echo "To redownload, delete: rm -rf $DEEPARG_DB_DIR"
    exit 0
fi

echo "Downloading DeepARG database (this will take 10-20 minutes)..."
echo "Progress log: tail -f $DOWNLOAD_LOG"
echo ""

# Download database
docker run --rm \
  -v "$DEEPARG_DB_DIR:/deeparg_db" \
  gaarangoa/deeparg:latest \
  deeparg download_data -o /deeparg_db 2>&1 | tee "$DOWNLOAD_LOG"

echo ""
echo "==================================="
echo "Download Complete!"
echo "==================================="
du -sh "$DEEPARG_DB_DIR"
ls -lh "$DEEPARG_DB_DIR"
echo ""
echo "Next steps:"
echo "1. Update nextflow.config to mount this directory"
echo "2. Restart pipeline"
echo "==================================="
