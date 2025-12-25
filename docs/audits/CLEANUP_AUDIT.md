# UPGRADE Project - Audit Report: Лишние файлы и компоненты

**Дата анализа**: 25 декабря 2025  
**Анализатор**: AI Assistant

---

## 📊 Общая статистика проекта

- **Общий размер**: ~195 GB
- **Размер результатов**: 29 GB
- **Размер данных**: 165 GB
- **Размер кода**: ~1.1 GB
- **Остановленных Docker контейнеров**: 22 (Nextflow)

---

## 🗑️ ЛИШНИЕ КОМПОНЕНТЫ

### 1. ❌ AIRFLOW (Полностью удален, но остались упоминания)

**Статус**: Удален, но структура осталась в памяти проекта

**Действия**:
- ✅ Airflow удален из системы
- ⚠️ Проверить остатки конфигураций

---

### 2. 🗂️ ДУБЛИРУЮЩИЕСЯ/БЭКАП ФАЙЛЫ

#### Backend

```bash
/home/nicolaedrabcinski/upgrade/web-dashboard/backend/
├── app.py.backup              # 14KB - УДАЛИТЬ
├── run_tests.sh               # Заменен на run_all_tests.sh
├── run_tests_uv.sh            # Заменен на upgrade-cli
└── run_batch.sh               # 440B - проверить актуальность
```

**Рекомендация**: 
```bash
rm app.py.backup run_tests.sh run_tests_uv.sh
# Проверить использование run_batch.sh перед удалением
```

---

### 3. 🧪 SANDBOX & ТЕСТОВЫЕ ДИРЕКТОРИИ

```bash
/home/nicolaedrabcinski/upgrade/sandbox/     # 92KB
├── openmeteo_test_results.json
├── test_2.py, test_3.py, test_4.py, test_5.py
├── test.py
├── weather_kafka_producer.py
├── ena_test/
├── ncbi_test/
└── weather_data/
```

**Статус**: Тестовые файлы для разработки

**Рекомендация**:
- ✅ **ОСТАВИТЬ** если используется для тестирования
- ❌ **УДАЛИТЬ** если тесты завершены и не нужны
- 📦 **АРХИВИРОВАТЬ** если нужно сохранить для истории

```bash
# Если не нужно:
rm -rf /home/nicolaedrabcinski/upgrade/sandbox/ena_test
rm -rf /home/nicolaedrabcinski/upgrade/sandbox/ncbi_test
rm /home/nicolaedrabcinski/upgrade/sandbox/test_*.py
```

---

### 4. 🧹 PYTHON CACHE & COMPILED FILES

```bash
# Найдено множество __pycache__ и .pyc файлов
__pycache__/
.pytest_cache/
*.pyc
```

**Рекомендация**: Очистить регулярно
```bash
# Очистить все кэши Python
find /home/nicolaedrabcinski/upgrade -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find /home/nicolaedrabcinski/upgrade -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null
find /home/nicolaedrabcinski/upgrade -type f -name "*.pyc" -delete

# Очистить coverage файлы (после проверки отчетов)
find /home/nicolaedrabcinski/upgrade -name "coverage.xml" -delete
find /home/nicolaedrabcinski/upgrade -name ".coverage" -delete
find /home/nicolaedrabcinski/upgrade -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null
```

---

### 5. 🐳 ОСТАНОВЛЕННЫЕ DOCKER КОНТЕЙНЕРЫ

**Найдено**: 22 остановленных Nextflow контейнера

```
nxf-J6bDh3mB25DvJ87CPA0D35BL   Exited (0) 41 hours ago
nxf-wqKaLkDCTsoxHw5RAZd3wxZp   Exited (0) 42 hours ago
nxf-QfcUQE0MdIpoALpoIwshb5lA   Exited (0) 43 hours ago
... (еще 19 контейнеров)
```

**Рекомендация**: Очистить
```bash
# Удалить все остановленные контейнеры
docker container prune -f

# Или только Nextflow контейнеры
docker ps -a --filter "name=nxf-" --filter "status=exited" -q | xargs docker rm

# Очистить неиспользуемые образы
docker image prune -a -f
```

**Экономия места**: ~500MB-2GB

---

### 6. 📝 ВРЕМЕННЫЕ/ИМПОРТ ФАЙЛЫ

```bash
/home/nicolaedrabcinski/upgrade/
├── import_old_results.py          # Скрипт импорта (одноразовый)
├── import_valid_results.py        # Скрипт импорта (одноразовый)
├── valid_runs_for_import.json     # 20KB - результаты импорта
└── check_pipeline_versions.py     # Если есть
```

**Статус**: Одноразовые скрипты импорта

**Рекомендация**:
```bash
# Переместить в архив
mkdir -p /home/nicolaedrabcinski/upgrade/scripts/archive
mv import_old_results.py scripts/archive/
mv import_valid_results.py scripts/archive/
mv valid_runs_for_import.json scripts/archive/

# Или удалить если импорт завершен успешно
# rm import_old_results.py import_valid_results.py valid_runs_for_import.json
```

---

### 7. 📊 ДУБЛИРУЮЩИЕСЯ ТЕСТЫ

```bash
/home/nicolaedrabcinski/upgrade/tests/          # Корневые тесты
├── test_modules.py
├── test_pipeline_integration.py
└── test_pipeline.py

/home/nicolaedrabcinski/upgrade/web-dashboard/backend/tests/  # Backend тесты
├── test_auth_routes.py
├── test_pipeline_routes.py
├── test_results_routes.py
├── test_database.py
├── test_utils.py
├── test_minio_integration.py
├── test_fastq_validator.py
└── test_minio_helper.py
```

**Статус**: Возможно дублирование

**Рекомендация**: 
- ✅ Оставить `/web-dashboard/backend/tests/` (новые, комплексные)
- ⚠️ Проверить `/tests/` - если устарели, удалить или объединить

```bash
# Проверить содержимое корневых тестов
cat /home/nicolaedrabcinski/upgrade/tests/test_pipeline.py

# Если устарели:
# rm -rf /home/nicolaedrabcinski/upgrade/tests/
```

---

### 8. 🔧 ЛИШНИЕ СКРИПТЫ

```bash
/home/nicolaedrabcinski/upgrade/scripts/
├── test_weather_consumer.py       # Тестовый скрипт
├── insert_test_samples.py         # Тестовые данные
├── monitor_pipeline.sh            # Возможно устарел (есть CLI)
├── cli_pipeline_run.sh            # Дублирует upgrade-cli?
├── direct_pipeline_run.sh         # Дублирует upgrade-cli?
└── quick_scan_coords.py           # Одноразовый?
```

**Рекомендация**: Провести аудит скриптов

```bash
# Если есть upgrade-cli, удалить дубликаты:
# rm scripts/cli_pipeline_run.sh
# rm scripts/direct_pipeline_run.sh
# rm scripts/monitor_pipeline.sh

# Переместить тестовые в sandbox
# mv scripts/test_weather_consumer.py sandbox/
# mv scripts/insert_test_samples.py sandbox/
```

---

### 9. 📦 НЕИСПОЛЬЗУЕМЫЕ МОДУЛИ/СЕРВИСЫ

#### Kafka (56KB)

```bash
/home/nicolaedrabcinski/upgrade/kafka/
├── consumer/
│   ├── Dockerfile
│   └── weather_consumer.py
└── producer/
    ├── Dockerfile
    └── weather_producer.py
```

**Статус**: Kafka producer/consumer для погодных данных

**Вопросы**:
- ✅ Используется ли в production?
- ❓ Есть ли активные задачи с погодой?

**Действия**:
```bash
# Проверить использование
docker ps | grep kafka
docker ps | grep weather

# Если контейнеры запущены - ОСТАВИТЬ
# Если нет - рассмотреть архивирование
```

#### Open-Meteo (8KB)

```bash
/home/nicolaedrabcinski/upgrade/open-meteo/
└── config/
```

**Статус**: Конфигурация для погодного API

**Рекомендация**: 
- ✅ Оставить если Kafka используется
- ❌ Удалить если погодный модуль не нужен

---

### 10. 📄 DEPRECATED CODE

#### В коде найдены DEPRECATED метки:

```python
# routes/auth.py:293
# DEPRECATED: Email verification endpoints removed (Dec 21, 2025)

# routes/pipeline.py:1016
# DEPRECATED: This endpoint loads entire files into memory and is inefficient.

# routes/pipeline.py:1931
# TODO: Add authentication and authorization before deploying to production.
```

**Рекомендация**:
1. Удалить deprecated код из `routes/auth.py`
2. Переработать или удалить deprecated endpoint в `routes/pipeline.py:1016`
3. Добавить authentication в endpoint `routes/pipeline.py:1931`

---

### 11. 🗄️ BACKUPS (72KB)

```bash
/home/nicolaedrabcinski/upgrade/backups/
```

**Статус**: Резервные копии

**Рекомендация**:
- ✅ Проверить автоматическую систему бэкапов PostgreSQL
- ✅ Оставить только последние 7 дней бэкапов
- ⚠️ Старые бэкапы архивировать или удалять

```bash
# Проверить содержимое
ls -lah /home/nicolaedrabcinski/upgrade/backups/

# Удалить старые (старше 30 дней)
find /home/nicolaedrabcinski/upgrade/backups/ -type f -mtime +30 -delete
```

---

### 12. 📝 LOGS (размер?)

```bash
/home/nicolaedrabcinski/upgrade/logs/
```

**Рекомендация**: Настроить ротацию логов

```bash
# Проверить размер
du -sh /home/nicolaedrabcinski/upgrade/logs/

# Настроить logrotate или удалить старые
find /home/nicolaedrabcinski/upgrade/logs/ -type f -mtime +7 -name "*.log" -delete
```

---

## 🎯 ПРИОРИТЕТНЫЕ ДЕЙСТВИЯ

### Высокий приоритет (сделать сразу)

1. **Очистить Docker контейнеры**
```bash
docker container prune -f
docker image prune -a -f
```
**Экономия**: ~500MB-2GB

2. **Удалить Python cache**
```bash
find /home/nicolaedrabcinski/upgrade -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find /home/nicolaedrabcinski/upgrade -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null
```
**Экономия**: ~50-100MB

3. **Удалить бэкап файлы**
```bash
cd /home/nicolaedrabcinski/upgrade/web-dashboard/backend
rm app.py.backup run_tests.sh run_tests_uv.sh
```
**Экономия**: ~15KB

### Средний приоритет (проверить и решить)

4. **Архивировать импорт скрипты**
```bash
mkdir -p scripts/archive
mv import_*.py scripts/archive/
mv valid_runs_for_import.json scripts/archive/
```

5. **Очистить sandbox (если не используется)**
```bash
# После проверки:
rm -rf sandbox/ena_test sandbox/ncbi_test
rm sandbox/test_*.py
```
**Экономия**: ~50MB

6. **Проверить корневые тесты**
```bash
# Если дублируются с backend/tests/:
rm -rf /home/nicolaedrabcinski/upgrade/tests/
```

### Низкий приоритет (на будущее)

7. **Рефакторинг кода**
   - Удалить deprecated endpoints
   - Добавить authentication где нужно
   - Убрать TODO комментарии

8. **Настроить автоочистку**
   - Logrotate для логов
   - Cron job для очистки Docker
   - Автоудаление старых бэкапов

---

## 📊 ПОТЕНЦИАЛЬНАЯ ЭКОНОМИЯ МЕСТА

| Категория | Размер | Действие |
|-----------|--------|----------|
| Docker контейнеры/образы | ~1-2 GB | Очистить |
| Python cache | ~50-100 MB | Очистить |
| Sandbox | ~50 MB | Архивировать/удалить |
| Coverage/Test artifacts | ~20 MB | Очистить |
| Backup файлы | ~15 KB | Удалить |
| **ИТОГО** | **~1.5-2.5 GB** | |

---

## ✅ ИТОГОВЫЕ РЕКОМЕНДАЦИИ

### Немедленно удалить:

```bash
# Backend бэкапы и дубликаты
rm /home/nicolaedrabcinski/upgrade/web-dashboard/backend/app.py.backup
rm /home/nicolaedrabcinski/upgrade/web-dashboard/backend/run_tests.sh
rm /home/nicolaedrabcinski/upgrade/web-dashboard/backend/run_tests_uv.sh

# Python cache
find /home/nicolaedrabcinski/upgrade -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find /home/nicolaedrabcinski/upgrade -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null

# Docker cleanup
docker container prune -f
docker image prune -a -f
```

### Проверить перед удалением:

- `/home/nicolaedrabcinski/upgrade/sandbox/` - если тесты завершены
- `/home/nicolaedrabcinski/upgrade/tests/` - если дублируются с backend/tests
- `import_*.py` - если импорт завершен успешно
- `scripts/monitor_pipeline.sh`, `scripts/*_pipeline_run.sh` - если заменены на CLI

### Оставить (используется):

- ✅ `web-dashboard/` - основной код
- ✅ `results/` (29GB) - результаты пайплайнов
- ✅ `data/` (165GB) - исходные данные
- ✅ `nextflow/` - конфигурация пайплайнов
- ✅ `database/` - схема БД и миграции
- ✅ `secrets/` - credentials
- ✅ `monitoring/` - Prometheus/Grafana
- ✅ `docs/` - документация

---

## 🔄 АВТОМАТИЗАЦИЯ ОЧИСТКИ

Создать cron job для регулярной очистки:

```bash
# /etc/cron.daily/upgrade-cleanup.sh
#!/bin/bash

# Очистка Docker
docker container prune -f > /dev/null 2>&1
docker image prune -a -f > /dev/null 2>&1

# Очистка Python cache
find /home/nicolaedrabcinski/upgrade -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find /home/nicolaedrabcinski/upgrade -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null

# Очистка старых логов (старше 7 дней)
find /home/nicolaedrabcinski/upgrade/logs/ -type f -mtime +7 -name "*.log" -delete 2>/dev/null

# Очистка старых бэкапов (старше 30 дней)
find /home/nicolaedrabcinski/upgrade/backups/ -type f -mtime +30 -delete 2>/dev/null

echo "Cleanup completed: $(date)" >> /var/log/upgrade-cleanup.log
```

```bash
chmod +x /etc/cron.daily/upgrade-cleanup.sh
```

---

**Вопросы для уточнения:**

1. Используется ли Kafka/weather модуль в production?
2. Нужны ли скрипты импорта (`import_*.py`) для повторного использования?
3. Содержат ли `/tests/` актуальные тесты или это старая версия?
4. Используются ли скрипты `cli_pipeline_run.sh`, `direct_pipeline_run.sh` или заменены на `upgrade-cli`?

