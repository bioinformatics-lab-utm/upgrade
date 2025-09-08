FROM python:3.11-slim

WORKDIR /app

# Установить системные зависимости
RUN apt-get update && apt-get install -y \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Установить Python зависимости
RUN pip install --no-cache-dir \
    kafka-python==2.0.2 \
    psycopg2-binary==2.9.9 \
    minio==7.2.0 \
    pandas==2.1.4 \
    pyarrow==14.0.1

# Создать папки
RUN mkdir -p /app/logs

# Скопировать код
COPY weather_consumer.py .

# Запустить consumer
CMD ["python", "weather_consumer.py"]