#!/bin/bash
set -e

echo "=== RQ Worker: Чтение секретов ==="
export POSTGRES_PASSWORD=$(cat /run/secrets/postgres_password)
export REDIS_PASSWORD=$(cat /run/secrets/redis_password)
export MINIO_ROOT_PASSWORD=$(cat /run/secrets/minio_root_password)

echo "POSTGRES_PASSWORD установлен: ${POSTGRES_PASSWORD:0:10}..."
echo "REDIS_PASSWORD установлен: ${REDIS_PASSWORD:0:10}..."
echo "MINIO_ROOT_PASSWORD установлен: ${MINIO_ROOT_PASSWORD:0:10}..."

# Экспортируем переменные для дочерних процессов
export POSTGRES_PASSWORD
export REDIS_PASSWORD
export MINIO_ROOT_PASSWORD

echo "=== Запуск RQ Worker ==="
exec python3 /app/worker_init.py
