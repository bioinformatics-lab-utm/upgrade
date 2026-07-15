#!/bin/bash
# setup_minio_lifecycle.sh
# Configure MinIO lifecycle policies for automatic data retention

set -e

echo "🗓️  Setting up MinIO lifecycle policies..."
echo ""

# Check if MinIO is running
if ! docker ps | grep -q "upgrade_minio"; then
    echo "❌ ERROR: MinIO container is not running"
    echo "   Start it with: docker compose up -d minio"
    exit 1
fi

echo "✅ MinIO is running"
echo ""

# Configure mc alias
echo "📡 Configuring MinIO client..."
docker exec upgrade_minio mc alias set myminio http://localhost:9000 ${MINIO_ROOT_USER:-minioadmin} ${MINIO_ROOT_PASSWORD:-minioadmin} 2>/dev/null || true

# Create lifecycle policies
echo ""
echo "🗓️  Applying lifecycle policies..."

# Bronze layer - 90 days for raw data (to save space, raw is huge)
echo ""
echo "📦 genomic-bronze (Raw FASTQ - 90 days retention)"
cat > /tmp/bronze_lifecycle.json << 'EOF'
{
    "Rules": [
        {
            "ID": "raw-fastq-cleanup",
            "Status": "Enabled",
            "Filter": {
                "Prefix": ""
            },
            "Expiration": {
                "Days": 90
            }
        }
    ]
}
EOF

docker cp /tmp/bronze_lifecycle.json upgrade_minio:/tmp/bronze_lifecycle.json
if docker exec upgrade_minio mc ilm import myminio/genomic-bronze < /tmp/bronze_lifecycle.json 2>/dev/null; then
    echo "   ✅ Lifecycle policy applied (90 days)"
else
    echo "   ⚠️  Could not apply lifecycle policy (may need mc update)"
fi

# Silver layer - 180 days for processed results
echo ""
echo "📦 genomic-silver (Processed results - 180 days retention)"
cat > /tmp/silver_lifecycle.json << 'EOF'
{
    "Rules": [
        {
            "ID": "processed-cleanup",
            "Status": "Enabled",
            "Filter": {
                "Prefix": ""
            },
            "Expiration": {
                "Days": 180
            }
        }
    ]
}
EOF

docker cp /tmp/silver_lifecycle.json upgrade_minio:/tmp/silver_lifecycle.json
if docker exec upgrade_minio mc ilm import myminio/genomic-silver < /tmp/silver_lifecycle.json 2>/dev/null; then
    echo "   ✅ Lifecycle policy applied (180 days)"
else
    echo "   ⚠️  Could not apply lifecycle policy"
fi

# Gold layer - NO expiration (permanent, curated data)
echo ""
echo "📦 genomic-gold (Curated reports - permanent retention)"
echo "   ✅ No expiration policy (permanent storage)"

# Weather data - 7 days
echo ""
echo "📦 weather-data (Temporary weather data - 7 days)"
cat > /tmp/weather_lifecycle.json << 'EOF'
{
    "Rules": [
        {
            "ID": "weather-cleanup",
            "Status": "Enabled",
            "Filter": {
                "Prefix": ""
            },
            "Expiration": {
                "Days": 7
            }
        }
    ]
}
EOF

docker cp /tmp/weather_lifecycle.json upgrade_minio:/tmp/weather_lifecycle.json
if docker exec upgrade_minio mc ilm import myminio/weather-data < /tmp/weather_lifecycle.json 2>/dev/null; then
    echo "   ✅ Lifecycle policy applied (7 days)"
else
    echo "   ⚠️  Could not apply lifecycle policy"
fi

# Cleanup temp files
rm -f /tmp/*_lifecycle.json

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║              LIFECYCLE POLICY SUMMARY                         ║"
echo "╠═══════════════════════════════════════════════════════════════╣"
echo "║  genomic-bronze  │ 90 days  │ Raw FASTQ files                 ║"
echo "║  genomic-silver  │ 180 days │ Processed pipeline results      ║"
echo "║  genomic-gold    │ ∞        │ Curated reports (permanent)     ║"
echo "║  weather-data    │ 7 days   │ Temporary weather data          ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "✅ MinIO lifecycle policies configured"
echo ""
echo "To view current policies:"
echo "  docker exec upgrade_minio mc ilm ls myminio/genomic-bronze"
