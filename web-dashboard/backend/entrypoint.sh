#!/bin/bash
set -e

echo "=== Чтение секретов ==="

# Read Docker secrets if available, otherwise keep existing env vars
if [ -f /run/secrets/postgres_password ]; then
    export POSTGRES_PASSWORD=$(cat /run/secrets/postgres_password)
fi
if [ -f /run/secrets/redis_password ]; then
    export REDIS_PASSWORD=$(cat /run/secrets/redis_password)
fi
if [ -f /run/secrets/minio_root_password ]; then
    export MINIO_ROOT_PASSWORD=$(cat /run/secrets/minio_root_password)
fi

echo "POSTGRES_PASSWORD установлен: ${POSTGRES_PASSWORD:+yes}"
echo "REDIS_PASSWORD установлен: ${REDIS_PASSWORD:+yes}"
echo "MINIO_ROOT_PASSWORD установлен: ${MINIO_ROOT_PASSWORD:+yes}"

echo "=== Запуск приложения ==="
exec python app.py "$@"
