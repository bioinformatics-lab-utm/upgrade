#!/bin/bash
# Script to download and setup GTDB-Tk database
# Database size: ~60GB (compressed), ~83GB (extracted)
# Time to download: ~30-60 minutes (depends on connection speed)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== GTDB-Tk Database Setup ===${NC}"
echo ""

# Default installation directory
DEFAULT_DIR="/opt/gtdbtk_data"
DB_DIR="${GTDBTK_DATA_PATH:-$DEFAULT_DIR}"

echo "Database will be installed to: $DB_DIR"
echo ""

# Check if database already exists
if [ -d "$DB_DIR" ] && [ -f "$DB_DIR/metadata/metadata.txt" ]; then
    echo -e "${YELLOW}GTDB-Tk database already exists at $DB_DIR${NC}"
    echo "Current version:"
    cat "$DB_DIR/metadata/metadata.txt" 2>/dev/null || echo "Unknown version"
    echo ""
    read -p "Do you want to re-download and overwrite? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping download. Exiting."
        exit 0
    fi
fi

# Create directory
echo "Creating directory: $DB_DIR"
sudo mkdir -p "$DB_DIR"
sudo chown $USER:$USER "$DB_DIR"

# Change to directory
cd "$DB_DIR"

# Get latest release information
echo ""
echo -e "${GREEN}Fetching latest GTDB-Tk release information...${NC}"
LATEST_RELEASE="https://data.gtdb.ecogenomic.org/releases/latest/"

# Download the latest database
echo ""
echo -e "${GREEN}Downloading GTDB-Tk database (this will take 30-60 minutes)...${NC}"
echo "Database size: ~60GB compressed, ~83GB extracted"
echo ""

# Use aria2c if available (faster parallel downloads), otherwise wget
if command -v aria2c &> /dev/null; then
    echo "Using aria2c for faster download..."
    aria2c -x 16 -s 16 -k 1M "${LATEST_RELEASE}gtdbtk_package/full_package/gtdbtk_r220_data.tar.gz"
elif command -v wget &> /dev/null; then
    echo "Using wget for download..."
    wget -c "${LATEST_RELEASE}gtdbtk_package/full_package/gtdbtk_r220_data.tar.gz"
else
    echo -e "${RED}ERROR: Neither aria2c nor wget is available. Please install one of them.${NC}"
    exit 1
fi

# Extract the database
echo ""
echo -e "${GREEN}Extracting database (this will take 10-20 minutes)...${NC}"
tar -xzf gtdbtk_r220_data.tar.gz

# Clean up compressed file
echo ""
read -p "Remove compressed file to save space? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm gtdbtk_r220_data.tar.gz
    echo "Compressed file removed"
fi

# Set environment variable
echo ""
echo -e "${GREEN}Database installation complete!${NC}"
echo ""
echo "Add this to your ~/.bashrc or ~/.zshrc:"
echo -e "${YELLOW}export GTDBTK_DATA_PATH=\"$DB_DIR/release220\"${NC}"
echo ""
echo "Or for Nextflow, add to nextflow.config:"
echo -e "${YELLOW}params.gtdbtk_db = \"$DB_DIR/release220\"${NC}"
echo ""
echo "For Docker/Singularity, mount the database:"
echo -e "${YELLOW}docker run -v $DB_DIR:/refdata ecogenomics/gtdbtk:2.3.2${NC}"
echo ""

# Verify installation
echo "Verifying installation..."
if [ -d "$DB_DIR/release220" ] && [ -f "$DB_DIR/release220/metadata/metadata.txt" ]; then
    echo -e "${GREEN}✓ Installation verified${NC}"
    echo "Database version:"
    cat "$DB_DIR/release220/metadata/metadata.txt"
    echo ""
    echo "Database size:"
    du -sh "$DB_DIR/release220"
else
    echo -e "${RED}✗ Installation verification failed${NC}"
    exit 1
fi

# Create convenience symlink
if [ ! -L "$DB_DIR/current" ]; then
    ln -s "$DB_DIR/release220" "$DB_DIR/current"
    echo "Created symlink: $DB_DIR/current -> $DB_DIR/release220"
fi

echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Set GTDBTK_DATA_PATH environment variable (see above)"
echo "2. Update nextflow.config with --gtdbtk_db parameter"
echo "3. Run pipeline: nextflow run main.nf --gtdbtk_db $DB_DIR/release220"
echo ""
