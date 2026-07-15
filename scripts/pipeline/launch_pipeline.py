#!/usr/bin/env python3
"""
Простой запуск через систему очередей платформы
"""
import sys
import os
sys.path.insert(0, '/home/nicolaedrabcinski/upgrade/web-dashboard/backend')

# Импорты
from redis import Redis
from rq import Queue
import json

print("=" * 80)
print("  🧬 Запуск через систему очередей платформы")
print("=" * 80)
print()

# Подключение к Redis (который уже используется платформой)
try:
    redis_conn = Redis(host='localhost', port=6380, db=0, decode_responses=False)
    redis_conn.ping()
    print("✅ Redis подключен")
except Exception as e:
    print(f"❌ Redis не доступен: {e}")
    sys.exit(1)

# Создать очередь
queue = Queue('pipelines', connection=redis_conn)

# Данные задачи
task_data = {
    'sample_code': 'ZYMO_QUEUE_001',
    'input_dir': '/home/nicolaedrabcinski/upgrade/data/zymo_mock',
    'output_dir': '/home/nicolaedrabcinski/upgrade/results/zymo_queue_001',
    'params': {
        'flye_genome_size': '50m',
        'flye_meta': True,
        'threads': 32
    }
}

print("📊 ПАРАМЕТРЫ:")
print(f"   Sample: {task_data['sample_code']}")
print(f"   Input: {task_data['input_dir']}")
print(f"   Output: {task_data['output_dir']}")
print()

# Добавить задачу в очередь
try:
    job = queue.enqueue(
        'tasks.pipeline_tasks.run_nextflow_pipeline',
        args=(task_data,),
        job_timeout='12h',
        result_ttl=86400,
        job_id=f"pipeline_{task_data['sample_code']}"
    )
    
    print(f"✅ Задача добавлена в очередь!")
    print(f"   Job ID: {job.id}")
    print(f"   Queue: {queue.name}")
    print(f"   Длина очереди: {len(queue)}")
    print()
    print("📋 Проверить статус:")
    print(f"   redis-cli -p 6380 LLEN rq:queue:pipelines")
    print()
    print("⚠️  ВАЖНО: Убедитесь что RQ worker запущен:")
    print("   docker-compose ps rq-worker")
    print("   docker-compose logs -f rq-worker")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 80)
print("  ✅ ГОТОВО!")
print("=" * 80)
