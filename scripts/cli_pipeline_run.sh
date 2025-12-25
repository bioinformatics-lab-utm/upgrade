#!/bin/bash
# CLI Pipeline Runner
# Usage: ./cli_pipeline_run.sh <fastq_file> <sample_code>

set -e

FILE_PATH=${1:-"/home/nicolaedrabcinski/upgrade/data/19122025/ERR14767225.fastq"}
SAMPLE_CODE=${2:-"cli_test_$(date +%s)"}
API_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"

# Check file exists
if [ ! -f "$FILE_PATH" ]; then
    echo "Error: File not found: $FILE_PATH"
    exit 1
fi

FILE_NAME=$(basename "$FILE_PATH")
FILE_SIZE=$(stat -c%s "$FILE_PATH")

echo "==================================="
echo "CLI Pipeline Runner"
echo "==================================="
echo "File: $FILE_PATH"
echo "Size: $(echo "scale=1; $FILE_SIZE/1024/1024" | bc) MB"
echo "Sample: $SAMPLE_CODE"
echo "==================================="

# Step 1: Get presigned URL
echo -e "\n[1/3] Creating sample and getting upload URL..."
RESPONSE=$(curl -s -X POST "$API_URL/api/pipeline/presigned-upload" \
  -H "Content-Type: application/json" \
  -d "{
    \"sample_code\": \"$SAMPLE_CODE\",
    \"sample_type\": \"nanopore\",
    \"collection_date\": \"$(date +%Y-%m-%d)\",
    \"files\": [{\"name\": \"$FILE_NAME\", \"size\": $FILE_SIZE}],
    \"pipeline_name\": \"nextflow_pipeline\",
    \"parameters\": {}
  }")

# Parse response
SAMPLE_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('sample_id', 'ERROR'))")
PIPELINE_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('pipeline_id', 'N/A'))")
PRESIGNED_URL=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('upload_urls', [{}])[0].get('presigned_url', 'ERROR'))")

if [ "$SAMPLE_ID" = "ERROR" ] || [ "$PRESIGNED_URL" = "ERROR" ]; then
    echo "Error creating sample:"
    echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    exit 1
fi

echo "✓ Sample created: ID=$SAMPLE_ID"
echo "✓ Pipeline ready: ID=$PIPELINE_ID"

# Step 2: Upload file
echo -e "\n[2/3] Uploading file to MinIO..."
START_TIME=$(date +%s)

UPLOAD_RESULT=$(curl -X PUT "${FRONTEND_URL}${PRESIGNED_URL}" \
  --data-binary @"$FILE_PATH" \
  -w "\nHTTP:%{http_code}\nTime:%{time_total}\nSpeed:%{speed_upload}" \
  -s -o /dev/null 2>&1)

HTTP_CODE=$(echo "$UPLOAD_RESULT" | grep "HTTP:" | cut -d: -f2)
UPLOAD_TIME=$(echo "$UPLOAD_RESULT" | grep "Time:" | cut -d: -f2)
UPLOAD_SPEED=$(echo "$UPLOAD_RESULT" | grep "Speed:" | cut -d: -f2)
UPLOAD_SPEED_MB=$(echo "scale=2; $UPLOAD_SPEED / 1024 / 1024" | bc)

if [ "$HTTP_CODE" = "200" ]; then
    echo "✓ Upload successful: ${UPLOAD_TIME}s @ ${UPLOAD_SPEED_MB} MB/s"
else
    echo "✗ Upload failed: HTTP $HTTP_CODE"
    exit 1
fi

# Step 3: Confirm upload and start pipeline
echo -e "\n[3/3] Confirming upload and starting pipeline..."

CONFIRM_RESPONSE=$(curl -s -X POST "$API_URL/api/pipeline/confirm-upload" \
  -H "Content-Type: application/json" \
  -d "{
    \"pipeline_id\": $PIPELINE_ID,
    \"sample_id\": $SAMPLE_ID,
    \"sample_code\": \"$SAMPLE_CODE\",
    \"uploaded_files\": [{
      \"filename\": \"$FILE_NAME\",
      \"size\": $FILE_SIZE,
      \"object_path\": \"$SAMPLE_CODE/raw/$FILE_NAME\"
    }],
    \"parameters\": {}
  }")

JOB_ID=$(echo "$CONFIRM_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', 'ERROR'))" 2>/dev/null)

if [ "$JOB_ID" = "ERROR" ]; then
    echo "✗ Pipeline start failed:"
    echo "$CONFIRM_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$CONFIRM_RESPONSE"
    exit 1
fi

echo "✓ Pipeline started!"
echo ""
echo "==================================="
echo "Pipeline Execution Details:"
echo "==================================="
echo "Pipeline ID: $PIPELINE_ID"
echo "Sample ID: $SAMPLE_ID"
echo "Job ID: $JOB_ID"
echo "Sample Code: $SAMPLE_CODE"
echo ""
echo "Monitor progress:"
echo "  docker logs -f upgrade_rq_worker | grep 'Pipeline $PIPELINE_ID'"
echo ""
echo "Check status:"
echo "  docker exec upgrade_postgres psql -U upgrade -d upgrade_db -c \"SELECT pipeline_id, status, started_at FROM pipeline_runs WHERE pipeline_id = $PIPELINE_ID;\""
echo ""
echo "View results:"
echo "  ls -lh /home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/"
echo "==================================="
