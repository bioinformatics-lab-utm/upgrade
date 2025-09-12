FROM python:3.11-slim

# Установить системные зависимости
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Создать пользователя
RUN useradd --create-home --shell /bin/bash streamlit

# Установить рабочую директорию
WORKDIR /app

# Скопировать requirements и установить зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Скопировать код приложения
COPY . .

# Создать директории для данных
RUN mkdir -p /data /results && chown -R streamlit:streamlit /app /data /results

# Создать Streamlit config
RUN mkdir -p /home/streamlit/.streamlit
COPY config.toml /home/streamlit/.streamlit/config.toml
RUN chown -R streamlit:streamlit /home/streamlit/.streamlit

# Переключиться на пользователя streamlit
USER streamlit

# Установить переменные окружения
ENV PYTHONPATH=/app
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Открыть порт
EXPOSE 8501

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8501/healthz || exit 1

# Команда запуска
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]