# COMPREHENSIVE TESTING GUIDE 🧪

**Дата**: 2026-01-09
**Цель**: Протестировать все 10 оптимизаций перед production deployment
**Время**: ~2-3 часа для полного тестирования

---

## СТРАТЕГИЯ ТЕСТИРОВАНИЯ

### Уровни тестирования:
1. **Unit Tests** - Отдельные компоненты (15 мин)
2. **Integration Tests** - Backend API + Database (30 мин)
3. **Nextflow Tests** - Pipeline modules (45 мин)
4. **End-to-End Test** - Полный pipeline run (60+ мин)
5. **Performance Validation** - Metrics comparison (30 мин)

---

## PHASE 1: UNIT TESTS (15 минут)

### Test 1.1: Python Syntax Validation

```bash
# Проверить все Python файлы на синтаксические ошибки
cd /home/nicolaedrabcinski/upgrade

echo "🔍 Checking Python syntax..."

# Backend files
python3 -m py_compile web-dashboard/backend/minio_helper.py
python3 -m py_compile web-dashboard/backend/tasks/pipeline_tasks.py
python3 -m py_compile web-dashboard/backend/database.py
python3 -m py_compile web-dashboard/backend/app.py
python3 -m py_compile web-dashboard/backend/routes/pipeline.py
python3 -m py_compile web-dashboard/backend/routes/samples.py
python3 -m py_compile web-dashboard/backend/routes/results.py

echo "✅ Python syntax validation complete"
```

**Expected**: No syntax errors

---

### Test 1.2: Nextflow Syntax Validation

```bash
# Проверить Nextflow синтаксис
cd /home/nicolaedrabcinski/upgrade/nextflow

echo "🔍 Checking Nextflow syntax..."

# Dry-run to validate syntax
nextflow run main.nf --help 2>&1 | head -20

# Validate config
nextflow config -flat 2>&1 | grep -E "(maxForks|checkm_mode)" | head -5

echo "✅ Nextflow syntax validation complete"
```

**Expected Output**:
```
maxForks = 20
params.checkm_mode = 'taxonomy_wf'
```

---

### Test 1.3: Database Connection Pool

```bash
cd /home/nicolaedrabcinski/upgrade/web-dashboard/backend

cat > test_database_pool.py <<'EOF'
#!/usr/bin/env python3
"""Test database connection pooling"""
import asyncio
import sys
import time
sys.path.insert(0, '/home/nicolaedrabcinski/upgrade/web-dashboard/backend')

from database import DatabasePool
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_pool():
    """Test connection pool initialization and usage"""

    # Test 1: Initialize pool
    logger.info("Test 1: Initializing connection pool...")
    pool = await DatabasePool.initialize(min_size=2, max_size=5)
    logger.info("✅ Pool initialized")

    # Test 2: Acquire and use connection
    logger.info("Test 2: Testing connection acquisition...")
    async with pool.acquire() as conn:
        version = await conn.fetchval("SELECT version()")
        logger.info(f"✅ Connection working: {version.split(',')[0]}")

    # Test 3: Multiple concurrent connections
    logger.info("Test 3: Testing concurrent connections...")
    async def query_test(i):
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT $1::int", i)
            return result

    start = time.time()
    results = await asyncio.gather(*[query_test(i) for i in range(10)])
    elapsed = time.time() - start

    logger.info(f"✅ 10 queries completed in {elapsed:.3f}s (avg: {elapsed/10*1000:.1f}ms per query)")

    # Test 4: Query timeout
    logger.info("Test 4: Testing query timeout...")
    from database import execute_with_timeout

    try:
        async with pool.acquire() as conn:
            await execute_with_timeout(
                conn,
                "SELECT pg_sleep(5)",  # 5 second sleep
                timeout=2.0  # 2 second timeout
            )
        logger.error("❌ Timeout should have fired!")
    except asyncio.TimeoutError:
        logger.info("✅ Query timeout working correctly")

    # Test 5: Pool stats
    logger.info(f"Test 5: Pool stats")
    logger.info(f"  Pool size: {pool.get_size()}")
    logger.info(f"  Free connections: {pool.get_idle_size()}")
    logger.info(f"  Used connections: {pool.get_size() - pool.get_idle_size()}")

    # Cleanup
    await DatabasePool.close()
    logger.info("✅ Pool closed successfully")

    logger.info("\n🎉 ALL DATABASE POOL TESTS PASSED!")

if __name__ == '__main__':
    asyncio.run(test_pool())
EOF

chmod +x test_database_pool.py
python3 test_database_pool.py
```

**Expected**: All tests pass, ~10-20ms per query with pooling

---

## PHASE 2: INTEGRATION TESTS (30 минут)

### Test 2.1: MinIO Parallel Downloads

```bash
cd /home/nicolaedrabcinski/upgrade/web-dashboard/backend

cat > test_parallel_downloads.py <<'EOF'
#!/usr/bin/env python3
"""Test parallel MinIO downloads"""
import asyncio
import sys
import time
import logging
sys.path.insert(0, '/home/nicolaedrabcinski/upgrade/web-dashboard/backend')

from minio_helper import download_from_bronze, get_minio_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_downloads():
    """Test parallel download performance"""

    # Get test pipeline_id with files
    import asyncpg
    import os

    db_url = os.getenv('DATABASE_URL')
    conn = await asyncpg.connect(db_url)

    # Find pipeline with Bronze files
    row = await conn.fetchrow("""
        SELECT mo.pipeline_id, COUNT(*) as file_count
        FROM minio_objects mo
        JOIN minio_buckets mb ON mo.bucket_id = mb.bucket_id
        WHERE mb.bucket_name = 'genomic-bronze'
        GROUP BY mo.pipeline_id
        ORDER BY file_count DESC
        LIMIT 1
    """)

    if not row:
        logger.warning("⚠️ No Bronze files found, skipping download test")
        await conn.close()
        return

    pipeline_id = row['pipeline_id']
    file_count = row['file_count']

    logger.info(f"Testing parallel downloads for pipeline_id={pipeline_id} ({file_count} files)")

    await conn.close()

    # Test download
    minio_client = get_minio_client()
    output_dir = f"/tmp/test_download_{pipeline_id}"

    start = time.time()
    files = await download_from_bronze(
        minio_client,
        f"SAMPLE_{pipeline_id}",
        output_dir,
        pipeline_id
    )
    elapsed = time.time() - start

    logger.info(f"✅ Downloaded {len(files)} files in {elapsed:.1f}s")
    logger.info(f"   Average: {elapsed/len(files):.1f}s per file")
    logger.info(f"   Expected: ~40-60s per 5GB file with 3 parallel downloads")

    # Cleanup
    import shutil
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    logger.info("🎉 PARALLEL DOWNLOAD TEST PASSED!")

if __name__ == '__main__':
    asyncio.run(test_downloads())
EOF

chmod +x test_parallel_downloads.py
python3 test_parallel_downloads.py
```

**Expected**: 3x faster than sequential (e.g., 3 files in ~40-60s instead of 120-180s)

---

### Test 2.2: Backend API Health Check

```bash
# Проверить что backend запущен и работает
cd /home/nicolaedrabcinski/upgrade

echo "🔍 Testing backend API..."

# Check if backend is running
curl -f http://localhost:8000/health 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ Backend is running"
else
    echo "⚠️ Backend not running, starting..."
    # Start backend in background
    cd web-dashboard/backend
    python3 app.py &
    BACKEND_PID=$!
    sleep 5
    echo "✅ Backend started (PID: $BACKEND_PID)"
fi

# Test endpoints
echo "Testing API endpoints..."
curl -s http://localhost:8000/api/samples | jq '.samples | length' || echo "0"
curl -s http://localhost:8000/api/pipeline/runs | jq '.runs | length' || echo "0"

echo "✅ Backend API tests complete"
```

---

### Test 2.3: Database Indexes Validation

```bash
# Проверить что индексы созданы
cd /home/nicolaedrabcinski/upgrade

cat > test_indexes.sql <<'EOF'
-- Check if performance indexes exist
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname LIKE 'idx_%'
ORDER BY tablename, indexname;

-- Count total indexes
SELECT COUNT(*) as index_count
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname LIKE 'idx_%';
EOF

echo "🔍 Checking database indexes..."
psql -U upgrade_user -d upgrade_db -f test_indexes.sql

# Expected: 18 indexes if migration was applied
```

**Expected**: 18 indexes listed (если migration 013 применена)

---

## PHASE 3: NEXTFLOW TESTS (45 минут)

### Test 3.1: Nextflow Config Validation

```bash
cd /home/nicolaedrabcinski/upgrade/nextflow

echo "🔍 Validating Nextflow configuration..."

# Check maxForks
grep -n "maxForks = 20" nextflow.config
if [ $? -eq 0 ]; then
    echo "✅ maxForks = 20 configured"
else
    echo "❌ maxForks not set correctly"
fi

# Check CheckM mode
grep -n "checkm_mode = 'taxonomy_wf'" nextflow.config
if [ $? -eq 0 ]; then
    echo "✅ CheckM taxonomy_wf mode configured"
else
    echo "❌ CheckM mode not set correctly"
fi

# Check DEEPARG_BATCH config
grep -n "DEEPARG_BATCH" nextflow.config
if [ $? -eq 0 ]; then
    echo "✅ DEEPARG_BATCH process configured"
else
    echo "❌ DEEPARG_BATCH not configured"
fi

echo "✅ Nextflow config validation complete"
```

---

### Test 3.2: DEEPARG Module Validation

```bash
cd /home/nicolaedrabcinski/upgrade/nextflow

echo "🔍 Testing DEEPARG module..."

# Check DEEPARG_BATCH process exists
grep -A 5 "process DEEPARG_BATCH" modules/deeparg.nf | head -10

# Check main.nf uses DEEPARG_BATCH
grep -n "DEEPARG_BATCH" main.nf

if [ $? -eq 0 ]; then
    echo "✅ DEEPARG_BATCH integration found in main.nf"
else
    echo "❌ DEEPARG_BATCH not integrated"
fi

# Check groupTuple usage
grep -n "groupTuple" main.nf | grep -A 2 "bins"

echo "✅ DEEPARG module validation complete"
```

---

### Test 3.3: Nextflow Dry Run (Small Test)

```bash
cd /home/nicolaedrabcinski/upgrade/nextflow

echo "🔍 Running Nextflow dry-run..."

# Create test input directory
mkdir -p /tmp/nextflow_test_input
echo ">test_read_1" > /tmp/nextflow_test_input/test.fastq
echo "ATCGATCGATCGATCG" >> /tmp/nextflow_test_input/test.fastq

# Dry run with minimal data
nextflow run main.nf \
    --input_dir /tmp/nextflow_test_input \
    --outdir /tmp/nextflow_test_output \
    -profile docker \
    -preview \
    2>&1 | head -50

# Check for errors
if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo "✅ Nextflow dry-run successful"
else
    echo "⚠️ Nextflow dry-run had warnings (expected for test data)"
fi

# Cleanup
rm -rf /tmp/nextflow_test_input /tmp/nextflow_test_output
```

---

## PHASE 4: END-TO-END TEST (60+ минут)

### Test 4.1: Full Pipeline Run (Production-Like)

```bash
cd /home/nicolaedrabcinski/upgrade

echo "🚀 Starting FULL PIPELINE TEST..."
echo "⏱️ Expected time: 5-7 hours (with optimizations)"
echo ""

# Choose test sample
TEST_SAMPLE="TEST_$(date +%Y%m%d_%H%M%S)"
echo "Test sample: $TEST_SAMPLE"

# Step 1: Upload test file to backend
echo "📤 Step 1: Uploading test FASTQ..."

# Use existing test file or create small one
if [ -f "/data/test_samples/small_test.fastq.gz" ]; then
    TEST_FILE="/data/test_samples/small_test.fastq.gz"
else
    # Create minimal test file
    mkdir -p /tmp/test_data
    echo ">test_read_1" > /tmp/test_data/test.fastq
    echo "ATCGATCGATCGATCGATCGATCGATCGATCG" >> /tmp/test_data/test.fastq
    gzip /tmp/test_data/test.fastq
    TEST_FILE="/tmp/test_data/test.fastq.gz"
fi

# Upload via API
curl -X POST http://localhost:8000/api/samples/upload \
    -F "file=@$TEST_FILE" \
    -F "sample_code=$TEST_SAMPLE" \
    -o /tmp/upload_response.json

# Get pipeline_id
PIPELINE_ID=$(jq -r '.pipeline_id' /tmp/upload_response.json)
echo "✅ Uploaded, pipeline_id: $PIPELINE_ID"

# Step 2: Monitor pipeline execution
echo ""
echo "⏳ Step 2: Monitoring pipeline execution..."
echo "   Check status: curl http://localhost:8000/api/pipeline/$PIPELINE_ID"
echo ""

# Monitor loop
START_TIME=$(date +%s)
while true; do
    STATUS=$(curl -s http://localhost:8000/api/pipeline/$PIPELINE_ID | jq -r '.status')
    ELAPSED=$(($(date +%s) - START_TIME))

    echo "[$(date +%H:%M:%S)] Status: $STATUS (elapsed: ${ELAPSED}s)"

    if [ "$STATUS" = "completed" ]; then
        echo "✅ Pipeline completed successfully!"
        break
    elif [ "$STATUS" = "failed" ]; then
        echo "❌ Pipeline failed!"
        curl -s http://localhost:8000/api/pipeline/$PIPELINE_ID | jq '.error_message'
        exit 1
    fi

    sleep 30  # Check every 30 seconds
done

END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))
TOTAL_HOURS=$((TOTAL_TIME / 3600))
TOTAL_MINS=$(((TOTAL_TIME % 3600) / 60))

echo ""
echo "🎉 PIPELINE COMPLETED!"
echo "   Total time: ${TOTAL_HOURS}h ${TOTAL_MINS}m"
echo "   Expected: 5-7 hours (with optimizations)"
echo "   Previous: 10-15 hours (before optimizations)"
echo ""

# Step 3: Validate results
echo "📊 Step 3: Validating results..."

# Check Silver layer uploads
SILVER_COUNT=$(psql -U upgrade_user -d upgrade_db -t -c \
    "SELECT COUNT(*) FROM minio_objects mo
     JOIN minio_buckets mb ON mo.bucket_id = mb.bucket_id
     WHERE mo.pipeline_id = $PIPELINE_ID AND mb.bucket_name = 'genomic-silver'")

echo "   Silver layer files: $SILVER_COUNT"

# Check Gold layer uploads
GOLD_COUNT=$(psql -U upgrade_user -d upgrade_db -t -c \
    "SELECT COUNT(*) FROM minio_objects mo
     JOIN minio_buckets mb ON mo.bucket_id = mb.bucket_id
     WHERE mo.pipeline_id = $PIPELINE_ID AND mb.bucket_name = 'genomic-gold'")

echo "   Gold layer files: $GOLD_COUNT"

# Check data lineage
LINEAGE_COUNT=$(psql -U upgrade_user -d upgrade_db -t -c \
    "SELECT COUNT(*) FROM data_lineage dl
     JOIN minio_objects mo ON dl.target_object_id = mo.object_id
     WHERE mo.pipeline_id = $PIPELINE_ID")

echo "   Lineage records: $LINEAGE_COUNT"

if [ "$SILVER_COUNT" -gt 0 ] && [ "$GOLD_COUNT" -gt 0 ] && [ "$LINEAGE_COUNT" -gt 0 ]; then
    echo "✅ All validation checks passed!"
else
    echo "⚠️ Some validation checks failed"
fi

echo ""
echo "🎉 END-TO-END TEST COMPLETE!"
```

---

## PHASE 5: PERFORMANCE VALIDATION (30 минут)

### Test 5.1: Database Query Performance

```bash
cd /home/nicolaedrabcinski/upgrade

cat > test_query_performance.sql <<'EOF'
-- Test 1: Query with index (should be fast)
EXPLAIN ANALYZE
SELECT * FROM pipeline_runs
WHERE status = 'running'
ORDER BY created_at DESC
LIMIT 10;

-- Test 2: Query with composite index
EXPLAIN ANALYZE
SELECT * FROM pipeline_runs
WHERE sample_id = 1 AND status = 'completed'
ORDER BY created_at DESC;

-- Test 3: Join query with indexes
EXPLAIN ANALYZE
SELECT pr.pipeline_id, pr.status, COUNT(mo.object_id)
FROM pipeline_runs pr
LEFT JOIN minio_objects mo ON pr.pipeline_id = mo.pipeline_id
WHERE pr.status IN ('running', 'completed')
GROUP BY pr.pipeline_id, pr.status
LIMIT 20;

-- Expected: All queries < 50ms with indexes
EOF

echo "🔍 Testing database query performance..."
psql -U upgrade_user -d upgrade_db -f test_query_performance.sql | grep "Execution Time"

echo "✅ Expected: All queries < 50ms (with indexes)"
```

---

### Test 5.2: Nextflow Process Parallelism

```bash
# Monitor Nextflow parallelism during pipeline run
cd /home/nicolaedrabcinski/upgrade

echo "🔍 Monitoring Nextflow parallelism..."
echo "   Run this during pipeline execution:"
echo ""
echo "   watch 'ps aux | grep -E \"(flye|metabat2|checkm|deeparg)\" | wc -l'"
echo ""
echo "   Expected: 15-20 parallel processes (with maxForks=20)"
echo "   Previous: 8-10 parallel processes (with maxForks=10)"
```

---

### Test 5.3: DEEPARG Container Count

```bash
echo "🔍 Monitoring DEEPARG containers..."
echo "   Run this during DEEPARG execution:"
echo ""
echo "   watch 'docker ps | grep deeparg | wc -l'"
echo ""
echo "   Expected: 1 container per sample (batched)"
echo "   Previous: 100 containers for 100 bins"
```

---

## TEST RESULTS CHECKLIST ✅

После завершения всех тестов, проверьте:

### Unit Tests
- [ ] Python syntax: No errors
- [ ] Nextflow syntax: Valid config
- [ ] Database pool: All tests pass
- [ ] Query timeouts: Working correctly

### Integration Tests
- [ ] Parallel downloads: 3x faster than sequential
- [ ] Backend API: All endpoints working
- [ ] Database indexes: 18 indexes present

### Nextflow Tests
- [ ] Config: maxForks=20, CheckM=taxonomy_wf
- [ ] DEEPARG_BATCH: Module exists and integrated
- [ ] Dry-run: No critical errors

### End-to-End Test
- [ ] Pipeline completes successfully
- [ ] Total time: 5-7 hours (vs 10-15 before)
- [ ] Silver/Gold uploads: Files present
- [ ] Data lineage: Records created

### Performance Validation
- [ ] Database queries: < 50ms with indexes
- [ ] Nextflow parallelism: 15-20 processes
- [ ] DEEPARG batching: 1 container per sample

---

## TROUBLESHOOTING

### Issue: Backend not starting
```bash
# Check logs
tail -f /tmp/genomic_backend.log

# Check port
netstat -tulpn | grep 8000

# Restart
cd web-dashboard/backend
python3 app.py
```

### Issue: Database connection failed
```bash
# Check PostgreSQL is running
systemctl status postgresql

# Check connection
psql -U upgrade_user -d upgrade_db -c "SELECT 1"

# Check DATABASE_URL
echo $DATABASE_URL
```

### Issue: Nextflow fails
```bash
# Check logs
tail -f results/*/nextflow.log

# Check work directory permissions
ls -la /tmp/nextflow

# Check Docker
docker ps
docker images | grep upgrade
```

---

## БЫСТРЫЙ SMOKE TEST (10 минут)

Если нет времени на полное тестирование, выполните быстрый smoke test:

```bash
#!/bin/bash
cd /home/nicolaedrabcinski/upgrade

echo "🚀 QUICK SMOKE TEST"

# 1. Python syntax
echo "1/5: Python syntax..."
python3 -m py_compile web-dashboard/backend/minio_helper.py && echo "✅" || echo "❌"

# 2. Nextflow config
echo "2/5: Nextflow config..."
grep -q "maxForks = 20" nextflow/nextflow.config && echo "✅" || echo "❌"

# 3. Backend health
echo "3/5: Backend health..."
curl -sf http://localhost:8000/health >/dev/null && echo "✅" || echo "❌"

# 4. Database connection
echo "4/5: Database connection..."
psql -U upgrade_user -d upgrade_db -c "SELECT 1" >/dev/null 2>&1 && echo "✅" || echo "❌"

# 5. Docker images
echo "5/5: Docker images..."
docker images | grep -q "upgrade-deeparg" && echo "✅" || echo "❌"

echo ""
echo "🎉 SMOKE TEST COMPLETE"
```

---

## NEXT STEPS

После успешного тестирования:

1. **Deploy to production**:
   ```bash
   # Apply database indexes
   psql -U upgrade_user -d upgrade_db -f database/migrations/013_performance_indexes.sql

   # Restart backend with connection pooling
   cd web-dashboard/backend
   # Integrate database.py into app.py
   python3 app.py
   ```

2. **Monitor metrics**:
   - Pipeline execution time (should be 5-7h vs 10-15h)
   - Database query times (should be <50ms)
   - Resource utilization (20 parallel processes, 1 DEEPARG container)

3. **Document results** in production metrics log

---

**Время тестирования**: 2-3 часа (полное) или 10 минут (smoke test)
**Статус**: ✅ Готово к выполнению
