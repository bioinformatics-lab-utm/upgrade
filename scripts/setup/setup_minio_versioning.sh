#!/bin/bash
# Setup MinIO Versioning for Critical Buckets
# This enables versioning for Bronze and Gold layers (permanent data)

set -e

echo "🗄️  Setting up MinIO versioning for critical buckets..."
echo ""

# Check if MinIO is running
if ! docker ps | grep -q "upgrade_minio"; then
    echo "❌ ERROR: MinIO container is not running"
    echo "   Start it with: docker compose up -d minio"
    exit 1
fi

echo "✅ MinIO is running"
echo ""

# Configure mc (MinIO Client) alias
echo "📡 Configuring MinIO client..."
docker exec upgrade_minio mc alias set myminio http://localhost:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD} 2>/dev/null || true

# Enable versioning for critical buckets
echo ""
echo "🔐 Enabling versioning for critical buckets..."
echo ""

# Bronze layer - Raw FASTQ files (PERMANENT)
echo "📦 genomic-bronze (Raw data - permanent retention)"
if docker exec upgrade_minio mc version enable myminio/genomic-bronze 2>&1 | grep -q "already enabled\|successfully enabled"; then
    echo "   ✅ Versioning enabled"
else
    echo "   ⚠️  Versioning may already be enabled or bucket doesn't exist"
fi

# Gold layer - Curated results (PERMANENT)
echo "📦 genomic-gold (Curated results - permanent retention)"
if docker exec upgrade_minio mc version enable myminio/genomic-gold 2>&1 | grep -q "already enabled\|successfully enabled"; then
    echo "   ✅ Versioning enabled"
else
    echo "   ⚠️  Versioning may already be enabled or bucket doesn't exist"
fi

# Weather data bucket (7 days retention)
echo "📦 weather-data (Weather station data - 7 days)"
if docker exec upgrade_minio mc version enable myminio/weather-data 2>&1 | grep -q "already enabled\|successfully enabled"; then
    echo "   ✅ Versioning enabled"
else
    echo "   ⚠️  Versioning may already be enabled or bucket doesn't exist"
fi

echo ""
echo "═══════════════════════════════════════════"
echo "📊 VERSIONING STATUS"
echo "═══════════════════════════════════════════"
echo ""

# Check versioning status
docker exec upgrade_minio mc version info myminio/genomic-bronze 2>/dev/null || echo "genomic-bronze: Status unknown"
docker exec upgrade_minio mc version info myminio/genomic-gold 2>/dev/null || echo "genomic-gold: Status unknown"
docker exec upgrade_minio mc version info myminio/weather-data 2>/dev/null || echo "weather-data: Status unknown"

echo ""
echo "═══════════════════════════════════════════"
echo "💡 WHAT THIS MEANS"
echo "═══════════════════════════════════════════"
echo ""
echo "✅ File overwrites will keep previous versions"
echo "✅ Accidental deletions are recoverable"
echo "✅ Point-in-time recovery is possible"
echo ""
echo "🔍 View versions:"
echo "   docker exec upgrade_minio mc ls --versions myminio/genomic-bronze/"
echo ""
echo "↩️  Restore deleted file:"
echo "   docker exec upgrade_minio mc undo myminio/genomic-bronze/path/to/file"
echo ""
echo "📈 Storage impact: ~10-20% increase (only changed files)"
echo ""
echo "✅ MinIO versioning setup complete!"
