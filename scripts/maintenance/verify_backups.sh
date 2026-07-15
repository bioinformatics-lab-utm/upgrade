#!/bin/bash
# Verify PostgreSQL and MinIO Backups
# Run this daily to ensure backups are working correctly

set -e

echo "🔍 UPGRADE Platform Backup Verification"
echo "========================================"
echo ""
date
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

# ========================================
# CHECK 1: PostgreSQL Backups
# ========================================
echo "📊 CHECK 1: PostgreSQL Backups"
echo "--------------------------------"

BACKUP_DIR="/backups/postgres"

if [ -d "$BACKUP_DIR" ]; then
    echo "✅ Backup directory exists: $BACKUP_DIR"
    
    # Check for recent daily backup
    LATEST_DAILY=$(ls -t $BACKUP_DIR/daily/*.sql.gz 2>/dev/null | head -1)
    if [ -n "$LATEST_DAILY" ]; then
        AGE_HOURS=$(( ($(date +%s) - $(stat -c %Y "$LATEST_DAILY")) / 3600 ))
        SIZE=$(du -h "$LATEST_DAILY" | cut -f1)
        
        if [ $AGE_HOURS -lt 48 ]; then
            echo -e "${GREEN}✅${NC} Latest daily backup: $(basename $LATEST_DAILY)"
            echo "   Age: ${AGE_HOURS} hours | Size: ${SIZE}"
        else
            echo -e "${RED}❌${NC} Latest daily backup is too old: ${AGE_HOURS} hours"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo -e "${RED}❌${NC} No daily backups found!"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Count backups by type
    DAILY_COUNT=$(ls -1 $BACKUP_DIR/daily/*.sql.gz 2>/dev/null | wc -l)
    WEEKLY_COUNT=$(ls -1 $BACKUP_DIR/weekly/*.sql.gz 2>/dev/null | wc -l)
    MONTHLY_COUNT=$(ls -1 $BACKUP_DIR/monthly/*.sql.gz 2>/dev/null | wc -l)
    
    echo "   Daily backups: ${DAILY_COUNT}"
    echo "   Weekly backups: ${WEEKLY_COUNT}"
    echo "   Monthly backups: ${MONTHLY_COUNT}"
    
    if [ $DAILY_COUNT -lt 3 ]; then
        echo -e "${YELLOW}⚠️${NC}  Warning: Less than 3 daily backups"
        WARNINGS=$((WARNINGS + 1))
    fi
    
else
    echo -e "${RED}❌${NC} Backup directory not found: $BACKUP_DIR"
    echo "   Is postgres-backup container running?"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# ========================================
# CHECK 2: MinIO Versioning
# ========================================
echo "📦 CHECK 2: MinIO Versioning"
echo "----------------------------"

if docker ps | grep -q "upgrade_minio"; then
    echo "✅ MinIO container is running"
    
    # Check versioning status for critical buckets
    BUCKETS=("genomic-bronze" "genomic-gold" "weather-data")
    
    for bucket in "${BUCKETS[@]}"; do
        VERSION_STATUS=$(docker exec upgrade_minio mc version info myminio/$bucket 2>&1 || echo "error")
        
        if echo "$VERSION_STATUS" | grep -q "enabled\|Enabled"; then
            echo -e "${GREEN}✅${NC} $bucket: Versioning enabled"
        elif echo "$VERSION_STATUS" | grep -q "suspended\|Suspended"; then
            echo -e "${YELLOW}⚠️${NC}  $bucket: Versioning suspended"
            WARNINGS=$((WARNINGS + 1))
        else
            echo -e "${RED}❌${NC} $bucket: Versioning status unknown"
            ERRORS=$((ERRORS + 1))
        fi
    done
else
    echo -e "${RED}❌${NC} MinIO container is not running"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# ========================================
# CHECK 3: Disk Space
# ========================================
echo "💾 CHECK 3: Disk Space"
echo "----------------------"

# Check backup directory space
if [ -d "$BACKUP_DIR" ]; then
    BACKUP_SIZE=$(du -sh $BACKUP_DIR 2>/dev/null | cut -f1)
    echo "📊 Backup directory size: ${BACKUP_SIZE}"
fi

# Check available disk space
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
DISK_AVAIL=$(df -h / | tail -1 | awk '{print $4}')

if [ $DISK_USAGE -lt 85 ]; then
    echo -e "${GREEN}✅${NC} Disk usage: ${DISK_USAGE}% (${DISK_AVAIL} available)"
elif [ $DISK_USAGE -lt 95 ]; then
    echo -e "${YELLOW}⚠️${NC}  Disk usage: ${DISK_USAGE}% (${DISK_AVAIL} available) - Consider cleanup"
    WARNINGS=$((WARNINGS + 1))
else
    echo -e "${RED}❌${NC} Disk usage: ${DISK_USAGE}% (${DISK_AVAIL} available) - CRITICAL!"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# ========================================
# CHECK 4: Test PostgreSQL Backup Integrity
# ========================================
echo "🧪 CHECK 4: Backup Integrity Test"
echo "----------------------------------"

if [ -n "$LATEST_DAILY" ]; then
    echo "Testing latest backup file integrity..."
    
    # Test gzip integrity
    if gunzip -t "$LATEST_DAILY" 2>/dev/null; then
        echo -e "${GREEN}✅${NC} Backup file is valid (gzip test passed)"
        
        # Check if file contains SQL
        if gunzip -c "$LATEST_DAILY" | head -20 | grep -q "PostgreSQL"; then
            echo -e "${GREEN}✅${NC} Backup contains PostgreSQL data"
        else
            echo -e "${YELLOW}⚠️${NC}  Warning: Backup may not contain valid PostgreSQL data"
            WARNINGS=$((WARNINGS + 1))
        fi
    else
        echo -e "${RED}❌${NC} Backup file is corrupted!"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${YELLOW}⚠️${NC}  Skipping integrity test - no backup found"
fi

echo ""

# ========================================
# CHECK 5: Backup Container Status
# ========================================
echo "🐳 CHECK 5: Backup Services Status"
echo "-----------------------------------"

# Check postgres-backup container
if docker ps | grep -q "postgres_backup"; then
    BACKUP_STATUS=$(docker ps --filter "name=postgres_backup" --format "{{.Status}}")
    echo -e "${GREEN}✅${NC} postgres-backup container: Running ($BACKUP_STATUS)"
else
    echo -e "${RED}❌${NC} postgres-backup container: Not running"
    echo "   Start with: docker compose up -d postgres-backup"
    ERRORS=$((ERRORS + 1))
fi

# Check postgres container
if docker ps | grep -q "upgrade_postgres"; then
    POSTGRES_STATUS=$(docker ps --filter "name=upgrade_postgres" --format "{{.Status}}")
    echo -e "${GREEN}✅${NC} postgres container: Running ($POSTGRES_STATUS)"
else
    echo -e "${RED}❌${NC} postgres container: Not running"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# ========================================
# SUMMARY
# ========================================
echo "========================================"
echo "📊 VERIFICATION SUMMARY"
echo "========================================"
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED${NC}"
    echo "   Backups are healthy and up to date"
    EXIT_CODE=0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠️  ${WARNINGS} WARNING(S)${NC}"
    echo "   Backups are working but need attention"
    EXIT_CODE=1
else
    echo -e "${RED}❌ ${ERRORS} ERROR(S), ${WARNINGS} WARNING(S)${NC}"
    echo "   CRITICAL: Backup system needs immediate attention!"
    EXIT_CODE=2
fi

echo ""
echo "Next steps:"
if [ $ERRORS -gt 0 ]; then
    echo "  1. Check logs: docker logs upgrade_postgres_backup"
    echo "  2. Verify backup schedule in docker-compose.yml"
    echo "  3. Check disk space and permissions"
fi
if [ $WARNINGS -gt 0 ]; then
    echo "  1. Review warnings above"
    echo "  2. Consider cleanup of old backups"
    echo "  3. Monitor disk usage"
fi
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo "  No action required - backups are healthy! ✅"
fi

echo ""
echo "Last verification: $(date)"

exit $EXIT_CODE
