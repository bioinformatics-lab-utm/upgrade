#!/bin/bash
# retention_cron.sh
# Run retention policy cleanup daily at 3 AM
# Install: crontab -e, add:
# 0 3 * * * /home/nicolaedrabcinski/upgrade/scripts/cron/retention_cron.sh >> /var/log/upgrade_retention.log 2>&1

set -e

PROJECT_DIR="/home/nicolaedrabcinski/upgrade"
VENV_DIR="$PROJECT_DIR/web-dashboard/backend/.venv"
LOG_FILE="/var/log/upgrade_retention_$(date +%Y%m%d).log"

echo "=================================================="
echo "UPGRADE Retention Policy Cleanup"
echo "Started: $(date)"
echo "=================================================="

# Activate virtual environment if exists
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
fi

# Load environment variables
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

# Run retention policy with 180-day retention (dry-run first week, then actual)
cd "$PROJECT_DIR"

# Check if first run this week (dry-run mode)
DAY_OF_WEEK=$(date +%u)
if [ "$DAY_OF_WEEK" -eq "1" ]; then
    echo "[DRY-RUN MODE] Monday check - showing what would be deleted"
    python scripts/retention_policy.py --days 180 --dry-run
else
    echo "[LIVE MODE] Running retention cleanup"
    python scripts/retention_policy.py --days 180
fi

echo ""
echo "=================================================="
echo "Completed: $(date)"
echo "=================================================="
