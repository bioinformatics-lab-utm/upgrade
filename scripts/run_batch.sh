#!/bin/bash
# Wrapper to run batch processor with proper env vars

export POSTGRES_HOST=postgres
export POSTGRES_PORT=5432
export POSTGRES_DB=upgrade_db
export POSTGRES_USER=upgrade
export POSTGRES_PASSWORD="dWfpKj6quDnyxKwbGcOHkMfl1yy+NhioOiauiUrxsTE="

echo "Starting SRA Batch Processor..."
echo "Database: ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
echo "User: ${POSTGRES_USER}"
echo ""

python3 /app/sra_batch_processor.py "$@"
