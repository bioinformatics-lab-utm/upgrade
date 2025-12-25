# ENA Batch Processor

Автоматическая система для обработки 5000 семплов с геокоординатами из ENA.

## Описание

Скрипт выполняет полный цикл обработки:

1. **Discovery**: Находит семплы с координатами в ENA (METAGENOMIC + lat/lon)
2. **Download**: Скачивает FASTQ через fasterq-dump
3. **Processing**: Запускает Nextflow pipeline
4. **Publishing**: Размещает результаты на GeoDashboard

## Архитектура

```
┌─────────────────┐
│  ENA Database   │
│  (5000+ samples)│
└────────┬────────┘
         │ Query: METAGENOMIC + lat + lon
         │ Sort by file_size ASC
         ▼
┌─────────────────────────┐
│  sample_queue Table     │
│  - accession            │
│  - latitude, longitude  │
│  - file_size            │
│  - status               │
└────────┬────────────────┘
         │ Sequential processing
         ▼
┌─────────────────────────┐
│  Download (fasterq-dump)│
│  /data/{accession}/raw/ │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Nextflow Pipeline      │
│  main.nf with modules   │
│  - NANOPLOT             │
│  - FILTLONG             │
│  - FLYE                 │
│  - CHECKM               │
│  - METABAT2/CONCOCT     │
│  - KRAKEN2/BRACKEN      │
│  - PIPELINE_SUMMARY     │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  GeoDashboard           │
│  - locations table      │
│  - samples table        │
│  - Map visualization    │
└─────────────────────────┘
```

## База данных

### Таблица: sample_queue

```sql
CREATE TABLE sample_queue (
    id SERIAL PRIMARY KEY,
    accession VARCHAR(50) UNIQUE,
    latitude FLOAT,
    longitude FLOAT,
    file_size BIGINT,
    country VARCHAR(100),
    collection_date DATE,
    library_strategy VARCHAR(100),
    platform VARCHAR(100),
    
    -- Processing status
    status VARCHAR(20) DEFAULT 'pending',
    -- pending, downloading, processing, completed, failed
    
    -- Progress tracking
    download_started_at TIMESTAMP,
    download_completed_at TIMESTAMP,
    pipeline_started_at TIMESTAMP,
    pipeline_completed_at TIMESTAMP,
    
    -- Results
    quality_score FLOAT,
    amr_risk_score FLOAT,
    summary_json_path TEXT,
    
    -- Error handling
    error_message TEXT,
    retry_count INT DEFAULT 0,
    last_attempt_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Использование

### 1. Запуск в Docker контейнере

```bash
# Запуск с дефолтным лимитом (5000 семплов)
docker exec upgrade_rq_worker python3 /scripts/ena_batch_processor.py

# Запуск с кастомным лимитом (например 100)
docker exec upgrade_rq_worker python3 /scripts/ena_batch_processor.py 100
```

### 2. Мониторинг прогресса

```sql
-- Статистика по статусам
SELECT status, COUNT(*) 
FROM sample_queue 
GROUP BY status;

-- Последние обработанные семплы
SELECT accession, status, quality_score, amr_risk_score
FROM sample_queue
WHERE status = 'completed'
ORDER BY pipeline_completed_at DESC
LIMIT 10;

-- Ошибки
SELECT accession, error_message, retry_count
FROM sample_queue
WHERE status = 'failed'
ORDER BY last_attempt_at DESC;

-- Прогресс обработки
SELECT 
    COUNT(*) FILTER (WHERE status = 'pending') as pending,
    COUNT(*) FILTER (WHERE status = 'downloading') as downloading,
    COUNT(*) FILTER (WHERE status = 'processing') as processing,
    COUNT(*) FILTER (WHERE status = 'completed') as completed,
    COUNT(*) FILTER (WHERE status = 'failed') as failed,
    ROUND(AVG(CASE WHEN status = 'completed' THEN quality_score END), 2) as avg_quality
FROM sample_queue;
```

### 3. Логи

```bash
# Реал-тайм логи
docker exec upgrade_rq_worker tail -f /logs/ena_batch_processor.log

# Последние 100 строк
docker exec upgrade_rq_worker tail -100 /logs/ena_batch_processor.log

# Поиск ошибок
docker exec upgrade_rq_worker grep -i error /logs/ena_batch_processor.log
```

### 4. Ручное управление

```sql
-- Сбросить failed семплы для повторной попытки
UPDATE sample_queue
SET status = 'pending', retry_count = 0, error_message = NULL
WHERE status = 'failed' AND retry_count < 3;

-- Пропустить проблемные семплы
UPDATE sample_queue
SET status = 'skipped'
WHERE accession IN ('ERR123456', 'SRR789012');

-- Очистить очередь
TRUNCATE sample_queue;
```

## Особенности

### Обработка от меньших к большим

Семплы сортируются по размеру файла (smallest first):

```sql
ORDER BY file_size ASC
```

Это позволяет:
- Быстрее получить первые результаты
- Протестировать pipeline на маленьких файлах
- Избежать блокировки на больших файлах

### Последовательная обработка

Семплы обрабатываются **строго по одному**:

```python
for accession, file_size in pending_samples:
    process_one_sample(accession)  # Blocking call
    time.sleep(5)  # Delay between samples
```

Причины:
- Nextflow использует значительные ресурсы
- Избегаем конфликтов по диску/памяти
- Лучший контроль за прогрессом

### Автоматическое создание locations

Если координаты новые (±0.1°), создаётся новая точка:

```sql
INSERT INTO locations (location_name, country, latitude, longitude)
VALUES ('ENA_SRR12345', 'Romania', 45.5, 25.5)
```

### Checkpoint/Resume

Если процесс прервётся, можно продолжить:

```python
# Все pending семплы продолжат обработку
SELECT * FROM sample_queue WHERE status = 'pending'
```

## Производительность

### Времени обработки (ориентировочно)

- **Download**: 5-60 минут (зависит от размера)
- **Pipeline**: 1-3 часа (зависит от сложности)
- **Post to Dashboard**: <1 минута

**Итого**: ~2-4 часа на 1 семпл

### Оценка времени для 5000 семплов

- **Оптимистично** (маленькие файлы): 2 часа × 5000 = 10,000 часов = **417 дней**
- **Реалистично** (средние файлы): 3 часа × 5000 = 15,000 часов = **625 дней**
- **Пессимистично** (большие файлы): 4 часа × 5000 = 20,000 часов = **833 дня**

### Рекомендации

**Для 5000 семплов нужна параллелизация или кластер!**

Варианты оптимизации:

1. **Параллельная обработка**: 10 семплов одновременно → **62 дня**
2. **Кластер** (100 нод): → **6 дней**
3. **Фильтрация**: Только маленькие файлы (<100MB) → **меньше семплов, быстрее**

## ENA Query Details

### Используемые фильтры

```python
query = 'library_strategy="METAGENOMIC" AND lat IS NOT NULL AND lon IS NOT NULL'
sortfields = 'fastq_bytes'
sortdir = 'asc'
```

### Возвращаемые поля

- `run_accession`: SRR/ERR номер
- `lat`, `lon`: Географические координаты
- `fastq_bytes`: Размер файла
- `country`: Страна
- `collection_date`: Дата сбора
- `library_strategy`: METAGENOMIC
- `instrument_platform`: ILLUMINA/OXFORD_NANOPORE

## Troubleshooting

### fasterq-dump fails

```bash
# Проверить доступность ENA
curl -I https://ftp.sra.ebi.ac.uk/

# Проверить конкретный accession
docker exec upgrade_rq_worker \
  fasterq-dump --help
```

### Pipeline fails

```bash
# Проверить Nextflow логи
ls -la /results/{accession}/.nextflow.log

# Проверить работу модулей
docker exec upgrade_nextflow \
  nextflow run /nextflow/main.nf --help
```

### Database connection

```bash
# Проверить PostgreSQL
docker exec upgrade_postgres psql -U upgrade -d upgrade_db -c "SELECT 1;"

# Проверить переменные окружения
docker exec upgrade_rq_worker env | grep POSTGRES
```

## Integration с GeoDashboard

После успешной обработки семпл появится на карте:

1. **Location**: Точка на карте с координатами
2. **Sample**: Запись в таблице samples с метаданными
3. **Quality Score**: Отображение качества (0-100)
4. **AMR Risk**: Оценка риска антибиотикорезистентности
5. **Summary JSON**: Полные результаты анализа

## Следующие шаги

1. **Тест на 10 семплах**: Проверить весь pipeline
2. **Оптимизация**: Добавить параллелизацию
3. **Мониторинг**: Grafana dashboards
4. **Alerts**: Уведомления о проблемах
