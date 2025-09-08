FROM python:3.11-slim

WORKDIR /app

# Установить зависимости
RUN pip install --no-cache-dir \
    kafka-python==2.0.2 \
    aiohttp==3.9.1 \
    redis==5.0.1 \
    schedule==1.2.0 \
    psycopg2-binary==2.9.7

# Создать папки
RUN mkdir -p /app/logs

# Скопировать код
COPY weather_producer.py .

# Запустить producer
CMD ["python", "weather_producer.py"]