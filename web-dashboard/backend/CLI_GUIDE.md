# UPGRADE CLI - Command Line Interface

Полноценный CLI инструмент для управления геномными пайплайнами UPGRADE через командную строку.

## 🚀 Установка

```bash
cd /home/nicolaedrabcinski/upgrade/web-dashboard/backend

# Создать виртуальное окружение (если еще не создано)
uv venv .venv

# Активировать
source .venv/bin/activate

# Установить зависимости
uv pip install -r requirements.txt

# Сделать скрипт исполняемым
chmod +x cli.py upgrade-cli
```

## 🔧 Конфигурация

Установите переменные окружения:

```bash
export POSTGRES_HOST=100.72.39.49
export POSTGRES_PASSWORD=$(cat /home/nicolaedrabcinski/upgrade/secrets/postgres_password.txt)
export PYTHONPATH=/home/nicolaedrabcinski/upgrade/web-dashboard/backend:$PYTHONPATH
```

Или создайте файл `.env`:

```bash
POSTGRES_HOST=100.72.39.49
POSTGRES_PORT=5432
POSTGRES_DB=upgrade_db
POSTGRES_USER=upgrade
POSTGRES_PASSWORD=<your_password>
UPGRADE_API_URL=http://100.72.39.49:8000
```

## 📚 Команды

### Общая помощь

```bash
./upgrade-cli --help
```

### 📋 Samples (Образцы)

#### Список всех образцов

```bash
./upgrade-cli samples list

# С ограничением количества
./upgrade-cli samples list --limit 10

# Фильтр по статусу
./upgrade-cli samples list --status completed
```

#### Детали конкретного образца

```bash
./upgrade-cli samples get SAMPLE001
```

### 🔬 Pipelines (Пайплайны)

#### Список пайплайнов

```bash
# Все пайплайны
./upgrade-cli pipelines list

# Последние 10
./upgrade-cli pipelines list --limit 10

# Только завершенные
./upgrade-cli pipelines list --status completed

# По образцу
./upgrade-cli pipelines list --sample SAMPLE001

# По диапазону дат
./upgrade-cli pipelines list --date-from 2025-12-01 --date-to 2025-12-31
```

**Пример вывода:**
```
                                   🔬 Pipeline Runs (5)
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Pipeline   ┃ Sample       ┃ Status       ┃ Version  ┃ Started      ┃ Run Name     ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ 102        │ sample_name  │ ✅ completed │ 2.0.0    │ 2025-12-24   │ pipeline_001 │
│ 101        │ sample_name  │ ✅ completed │ 2.0.0    │ 2025-12-24   │ pipeline_002 │
└────────────┴──────────────┴──────────────┴──────────┴──────────────┴──────────────┘
```

#### Детали пайплайна

```bash
./upgrade-cli pipelines get 42
```

**Вывод:**
```
╭──────────────────── 🔬 Pipeline Run: 42 ────────────────────╮
│ ▶️  Pipeline ID: 42                                         │
│ Sample: SAMPLE001 (ID: 15)                                  │
│ Status: completed                                           │
│ Pipeline: nextflow_pipeline                                 │
│ Version: 2.0.0                                              │
│ Started: 2025-12-24 10:30:15                               │
│ Completed: 2025-12-24 12:45:30                             │
│ Runtime: 135.3 min                                          │
│ Job ID: rq:job:abc123                                      │
│ Results Path: /results/sample_001                          │
│ Bronze Path: bronze/sample_001                             │
│ Silver Path: silver/sample_001                             │
│ Gold Path: gold/sample_001                                 │
╰─────────────────────────────────────────────────────────────╯
```

#### Прогресс пайплайна

```bash
./upgrade-cli pipelines progress 42
```

**Вывод:**
```
Pipeline 42 Progress
├── bronze_upload
│   ├── 🔵 Uploading FASTQ files (10%) - 10:30:15
│   └── ✅ Upload complete (100%) - 10:32:45
├── nextflow_exec
│   ├── 🔵 Starting Nextflow (0%) - 10:33:00
│   ├── ⏳ QC with NanoPlot (25%) - 10:35:00
│   ├── ⏳ Assembly with Flye (50%) - 10:50:00
│   └── ✅ Nextflow complete (100%) - 12:15:00
├── silver_upload
│   └── ✅ Results uploaded (100%) - 12:20:00
└── gold_curation
    └── ✅ Curation complete (100%) - 12:45:00
```

#### Запуск нового пайплайна

```bash
./upgrade-cli pipelines start SAMPLE001 /path/to/file1.fastq /path/to/file2.fastq

# С опциями
./upgrade-cli pipelines start SAMPLE001 file.fastq --skip-qc --skip-assembly
```

#### Отмена пайплайна

```bash
./upgrade-cli pipelines cancel 42
```

### 📊 Results (Результаты)

#### Просмотр результатов

```bash
# Форматированный вывод
./upgrade-cli results get 42

# JSON формат
./upgrade-cli results get 42 --format json
```

**Форматированный вывод:**
```
╭────────────────── 📊 Pipeline Results ──────────────────╮
│ Pipeline ID: 42                                         │
│ Sample: SAMPLE001                                       │
│ Version: 2.0.0                                          │
╰─────────────────────────────────────────────────────────╯

📈 QC Metrics
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Metric            ┃ Value        ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ Total Reads       │ 1,250,000    │
│ Total Bases       │ 5,250,000,000│
│ Mean Quality      │ 12.5         │
│ Mean Read Length  │ 4,200.5      │
└───────────────────┴──────────────┘

🧬 Assembly Metrics
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Metric           ┃ Value       ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ Total Length     │ 4,250,000 bp│
│ Number of Contigs│ 145         │
│ N50              │ 45,000 bp   │
│ L50              │ 28          │
└──────────────────┴─────────────┘

🦠 Top Taxa
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┓
┃ Species                   ┃ Reads  ┃ %      ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━┩
│ Escherichia coli          │ 15,000 │ 45.25% │
│ Klebsiella pneumoniae     │ 8,500  │ 25.75% │
│ Pseudomonas aeruginosa    │ 5,200  │ 15.75% │
└───────────────────────────┴────────┴────────┘

💊 AMR Genes Found: 12
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Gene         ┃ Resistance        ┃ Identity ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ blaNDM-1     │ Carbapenem        │ 99.8%    │
│ blaCTX-M-15  │ Beta-lactam       │ 98.5%    │
│ aac(6')-Ib-cr│ Aminoglycoside    │ 97.2%    │
└──────────────┴───────────────────┴──────────┘

⚠️ Pathogens Detected: 2
  • Klebsiella pneumoniae - Risk: high
  • Escherichia coli O157:H7 - Risk: high
```

#### Экспорт результатов

```bash
# Экспорт в JSON файл
./upgrade-cli results export 42 /path/to/output.json
```

### 📊 Statistics (Статистика)

#### Общая статистика системы

```bash
./upgrade-cli stats
```

**Вывод:**
```
╭────────────────── 📊 System Statistics ──────────────────╮
│ Total Samples: 156                                       │
│ Total Pipeline Runs: 102                                 │
│ Completed: 89                                            │
│ Average Runtime: 125.3 min                               │
╰──────────────────────────────────────────────────────────╯

        Pipeline Status Distribution
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Status               ┃ Count     ┃ Percentage ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ completed            │ 89        │ 87.3%      │
│ running              │ 8         │ 7.8%       │
│ failed               │ 3         │ 2.9%       │
│ queued               │ 2         │ 2.0%       │
└──────────────────────┴───────────┴────────────┘
```

## 🔄 Примеры использования

### Мониторинг активных пайплайнов

```bash
# Показать все running пайплайны
./upgrade-cli pipelines list --status running

# Проверить прогресс конкретного
./upgrade-cli pipelines progress 42
```

### Batch анализ результатов

```bash
#!/bin/bash
# Экспорт всех результатов в JSON

for id in $(seq 1 102); do
    ./upgrade-cli results export $id "results_$id.json" 2>/dev/null
done
```

### Отслеживание завершенных за день

```bash
./upgrade-cli pipelines list \
  --status completed \
  --date-from 2025-12-24 \
  --date-to 2025-12-24
```

## 🐳 Использование в Docker

Если хотите запускать CLI из Docker контейнера:

```bash
docker exec -it upgrade_web_backend bash
cd /app
source .venv/bin/activate
python3 cli.py pipelines list --limit 10
```

## 🌐 API интеграция

CLI также может работать через HTTP API (для удаленных серверов):

```bash
# Установить URL API
export UPGRADE_API_URL=http://100.72.39.49:8000

# Запускать команды как обычно
./upgrade-cli pipelines list
```

## ⚡ Быстрые команды

Создайте алиасы в `~/.bashrc`:

```bash
# Добавьте в ~/.bashrc
alias upgrade='cd /home/nicolaedrabcinski/upgrade/web-dashboard/backend && source .venv/bin/activate && export PYTHONPATH=$(pwd):$PYTHONPATH && export POSTGRES_HOST=100.72.39.49 && export POSTGRES_PASSWORD=$(cat /home/nicolaedrabcinski/upgrade/secrets/postgres_password.txt) && python3 cli.py'

# Использование
upgrade pipelines list
upgrade stats
upgrade pipelines get 42
```

## 🔍 Отладка

### Подробный вывод

```bash
# Включить отладочный режим
export LOG_LEVEL=DEBUG
./upgrade-cli pipelines list
```

### Проверка подключения

```bash
# Проверить подключение к БД
./upgrade-cli stats
```

### Проблемы с подключением

```bash
# Проверить переменные окружения
env | grep POSTGRES

# Проверить доступность PostgreSQL
nc -zv 100.72.39.49 5432

# Проверить пароль
cat /home/nicolaedrabcinski/upgrade/secrets/postgres_password.txt
```

## 📝 Примечания

- CLI использует те же конфигурации, что и backend приложение
- Результаты читаются из `/home/nicolaedrabcinski/upgrade/results/`
- База данных: PostgreSQL на `100.72.39.49:5432`
- Красивый вывод обеспечивается библиотекой `rich`

## 🎨 Цветовая схема

- 🔵 **Синий** - в процессе (running, in_progress)
- ⏳ **Желтый** - в очереди (queued)
- ✅ **Зеленый** - завершено (completed)
- ❌ **Красный** - ошибка (failed)
- 🚫 **Оранжевый** - отменено (cancelled)

## 🚀 Следующие шаги

1. Добавить поддержку batch операций
2. Реализовать watch mode для мониторинга
3. Добавить экспорт в CSV/Excel
4. Интеграция с Grafana для метрик
5. WebSocket поддержка для real-time обновлений

## 📚 Дополнительная информация

- Backend API: [app.py](/home/nicolaedrabcinski/upgrade/web-dashboard/backend/app.py)
- Database Schema: [database/migrations](/home/nicolaedrabcinski/upgrade/database/migrations)
- Tests: [tests/](/home/nicolaedrabcinski/upgrade/web-dashboard/backend/tests)
