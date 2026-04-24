FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей и Nextflow
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    default-jre-headless \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    pigz \
    && rm -rf /var/lib/apt/lists/*

# Установка Docker CLI (для запуска контейнеров через Docker socket)
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

# Установка Nextflow
RUN curl -s https://get.nextflow.io | bash && \
    chmod +x nextflow && \
    mv nextflow /usr/local/bin/ && \
    mkdir -p /home/sanic/.nextflow && \
    chmod -R 777 /home/sanic/.nextflow

# Копирование зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY . .

# ✅ ДОБАВИТЬ СЮДА - копирование и права для entrypoint.sh
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Создание непривилегированного пользователя и добавление в docker группу
RUN useradd -m -u 1000 sanic && \
    groupadd -f -g 999 docker && \
    usermod -aG docker sanic && \
    mkdir -p /home/sanic/.nextflow /tmp/nextflow && \
    chown -R sanic:sanic /app /home/sanic /tmp/nextflow
USER sanic

# Environment variables for Nextflow
ENV NXF_HOME=/home/sanic/.nextflow
ENV TMPDIR=/tmp/nextflow

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["--single-process"]