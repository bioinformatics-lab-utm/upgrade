#!/usr/bin/env python3
"""
Запуск Nextflow пайплайна через веб-платформу API
"""
import requests
import json
import sys
import time
from datetime import datetime

# Конфигурация
API_BASE = "http://localhost:8000"
API_HEALTH = f"{API_BASE}/api/health"
API_LOGIN = f"{API_BASE}/api/auth/login"
API_SUBMIT = f"{API_BASE}/api/pipeline/submit"
API_STATUS = f"{API_BASE}/api/pipeline/runs"

# Учетные данные (из вашего проекта)
USERNAME = "admin"
PASSWORD = "admin123"  # Измените если нужно

def print_header(text):
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)

def check_health():
    """Проверка здоровья API"""
    print_header("🔍 Проверка здоровья API")
    try:
        response = requests.get(API_HEALTH, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API здоров: {data}")
            return True
        else:
            print(f"❌ API вернул статус {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Не удалось подключиться к API: {e}")
        return False

def login():
    """Аутентификация"""
    print_header("🔐 Аутентификация")
    try:
        response = requests.post(
            API_LOGIN,
            json={"username": USERNAME, "password": PASSWORD},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('token') or data.get('access_token')
            if token:
                print(f"✅ Аутентификация успешна")
                print(f"   Пользователь: {data.get('user', {}).get('username', USERNAME)}")
                return token
        
        print(f"❌ Аутентификация не удалась: {response.status_code}")
        print(f"   Ответ: {response.text}")
        return None
        
    except Exception as e:
        print(f"❌ Ошибка аутентификации: {e}")
        return None

def submit_pipeline(token, sample_code, input_path, genome_size="50m", threads=32):
    """Отправка пайплайна на выполнение"""
    print_header(f"🚀 Запуск пайплайна для {sample_code}")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "sample_code": sample_code,
        "sample_type": "nanopore",
        "collection_date": datetime.now().date().isoformat(),
        "pipeline_name": "nextflow_pipeline",
        "input_path": input_path,
        "parameters": {
            "flye_genome_size": genome_size,
            "flye_meta": True,
            "threads": threads,
            "flye_mode": "--nano-raw",
            "run_medaka": True
        },
        "notes": f"ZymoBIOMICS mock community test - запущен через API {datetime.now()}"
    }
    
    print(f"📊 Параметры:")
    print(f"   Sample: {sample_code}")
    print(f"   Input: {input_path}")
    print(f"   Genome size: {genome_size}")
    print(f"   Threads: {threads}")
    print()
    
    try:
        response = requests.post(
            API_SUBMIT,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code in [200, 201, 202]:
            data = response.json()
            print(f"✅ Пайплайн отправлен на выполнение!")
            print(f"   Job ID: {data.get('job_id', 'N/A')}")
            print(f"   Pipeline ID: {data.get('pipeline_id', 'N/A')}")
            print(f"   Status: {data.get('status', 'queued')}")
            return data
        else:
            print(f"❌ Ошибка отправки: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка при отправке: {e}")
        return None

def check_status(token, pipeline_id=None):
    """Проверка статуса пайплайнов"""
    print_header("📊 Статус пайплайнов")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.get(
            API_STATUS,
            headers=headers,
            params={"limit": 10, "offset": 0},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            runs = data.get('runs', [])
            
            print(f"✅ Найдено {len(runs)} пайплайнов:")
            print()
            
            for run in runs[:5]:  # Показать последние 5
                print(f"   • Pipeline ID: {run.get('pipeline_id')}")
                print(f"     Sample: {run.get('sample_name')}")
                print(f"     Status: {run.get('status')}")
                print(f"     Queued: {run.get('queued_at', 'N/A')}")
                print()
            
            return runs
        else:
            print(f"❌ Ошибка получения статуса: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return []

def main():
    """Главная функция"""
    print_header("🧬 UPGRADE Pipeline - Запуск через Web API")
    
    # 1. Проверка здоровья
    if not check_health():
        print("\n❌ API недоступен. Убедитесь, что веб-бэкенд запущен:")
        print("   docker-compose up -d web-backend")
        sys.exit(1)
    
    # 2. Аутентификация
    token = login()
    if not token:
        print("\n❌ Не удалось авторизоваться. Проверьте логин/пароль.")
        sys.exit(1)
    
    # 3. Отправка пайплайна
    result = submit_pipeline(
        token=token,
        sample_code="ZYMO_API_TEST_001",
        input_path="/home/nicolaedrabcinski/upgrade/data/zymo_mock",
        genome_size="50m",
        threads=32
    )
    
    if not result:
        print("\n❌ Не удалось отправить пайплайн")
        sys.exit(1)
    
    # 4. Проверка статуса
    time.sleep(2)
    check_status(token)
    
    print_header("✅ ГОТОВО!")
    print("\n📋 Следующие шаги:")
    print("   1. Отслеживайте прогресс в веб-интерфейсе: http://localhost:3000")
    print("   2. Или через API: curl -H 'Authorization: Bearer <token>' http://localhost:8000/api/pipeline/runs")
    print(f"   3. Результаты будут в: results/ZYMO_API_TEST_001/")
    print()

if __name__ == "__main__":
    main()
