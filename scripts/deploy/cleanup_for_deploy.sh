#!/bin/bash
# cleanup_for_deploy.sh
# Очистка проекта перед деплоем в production
# Запуск: ./scripts/deploy/cleanup_for_deploy.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "========================================"
echo "UPGRADE Project - Pre-Deploy Cleanup"
echo "========================================"
echo "Project root: $PROJECT_ROOT"
echo ""

cd "$PROJECT_ROOT"

# 1. Удалить coverage артефакты
echo "[1/7] Removing coverage artifacts..."
rm -rf htmlcov/ .coverage coverage.xml .pytest_cache/
echo "  ✓ Coverage files removed"

# 2. Удалить логи Nextflow
echo "[2/7] Removing Nextflow logs..."
rm -f .nextflow.log* nextflow_run.log
echo "  ✓ Nextflow logs removed"

# 3. Очистить Python cache
echo "[3/7] Cleaning Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
echo "  ✓ Python cache cleaned"

# 4. Удалить дубликаты скриптов
echo "[4/7] Removing duplicate scripts..."
if [ -f "scripts/create_technical_architecture_backup.py" ]; then
    rm -f scripts/create_technical_architecture_backup.py
    echo "  ✓ Removed create_technical_architecture_backup.py"
else
    echo "  - No duplicates found"
fi

# 5. Очистить временные файлы
echo "[5/7] Removing temporary files..."
find . -name "*.tmp" -delete 2>/dev/null || true
find . -name "*~" -delete 2>/dev/null || true
find . -name ".DS_Store" -delete 2>/dev/null || true
find . -name "Thumbs.db" -delete 2>/dev/null || true
echo "  ✓ Temporary files removed"

# 6. Проверить что секреты не попадут в деплой
echo "[6/7] Checking secrets..."
if [ -f ".env" ] || [ -f ".env.secrets" ]; then
    echo "  ⚠️  WARNING: .env or .env.secrets exist!"
    echo "     Make sure they are in .gitignore and .dockerignore"
fi

# 7. Вывести статистику
echo "[7/7] Calculating sizes..."
echo ""
echo "========================================"
echo "Directory sizes (should NOT be deployed):"
echo "========================================"
du -sh data/ results/ backups/ .venv/ web-dashboard/frontend/node_modules/ 2>/dev/null || true
echo ""
echo "========================================"
echo "Cleanup complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Review docs/NON_PRODUCTION_FILES_REPORT.md"
echo "2. Ensure .dockerignore is correct"
echo "3. Run: docker-compose -f docker-compose.prod.yml build"
