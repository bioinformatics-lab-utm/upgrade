#!/usr/bin/env python3
"""
UPGRADE Project Status Checker
Проверяет реальное состояние компонентов проекта
"""

import os
import sys
import json
import subprocess
import psycopg2
import requests
from pathlib import Path
import docker
from minio import Minio
import redis
from datetime import datetime

class UpgradeStatusChecker:
    def __init__(self, project_root="."):
        self.project_root = Path(project_root)
        self.results = {}
        
    def check_all(self):
        """Запуск всех проверок"""
        print("🔍 Проверка статуса проекта UPGRADE...\n")
        
        sections = [
            ("Infrastructure & Docker", self.check_infrastructure),
            ("Database Schema", self.check_database),
            ("Weather Pipeline", self.check_weather_pipeline),
            ("Streamlit App", self.check_streamlit),
            ("Airflow", self.check_airflow),
            ("Nextflow", self.check_nextflow),
            ("File Structure", self.check_file_structure),
        ]
        
        for section_name, check_func in sections:
            print(f"📊 {section_name}")
            print("-" * 50)
            try:
                results = check_func()
                self.results[section_name] = results
                self.print_results(results)
            except Exception as e:
                print(f"❌ Ошибка проверки: {e}")
                self.results[section_name] = {"error": str(e)}
            print()
        
        self.print_summary()
    
    def check_infrastructure(self):
        """Проверка Docker инфраструктуры"""
        results = {}
        
        # Проверка docker-compose файла
        compose_file = self.project_root / "docker-compose.yml"
        results["docker_compose_exists"] = compose_file.exists()
        
        # Проверка запущенных контейнеров
        try:
            client = docker.from_env()
            containers = client.containers.list()
            container_names = [c.name for c in containers]
            
            expected_containers = [
                "upgrade_postgres", "upgrade_minio", "upgrade_redis",
                "upgrade_airflow_webserver", "upgrade_airflow_scheduler",
                "upgrade_streamlit", "upgrade_kafka", "upgrade_zookeeper"
            ]
            
            running_containers = {}
            for expected in expected_containers:
                running_containers[expected] = expected in container_names
            
            results["containers"] = running_containers
            
        except Exception as e:
            results["docker_error"] = str(e)
        
        # Проверка доступности сервисов
        services = {
            "PostgreSQL": ("localhost", 5432),
            "MinIO API": ("localhost", 9000),
            "MinIO Console": ("localhost", 9001),
            "Airflow": ("localhost", 8081),
            "Streamlit": ("localhost", 8501),
            "Kafka": ("localhost", 9092)
        }
        
        service_status = {}
        for service, (host, port) in services.items():
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((host, port))
                service_status[service] = result == 0
                sock.close()
            except:
                service_status[service] = False
        
        results["services"] = service_status
        return results
    
    def check_database(self):
        """Проверка состояния базы данных"""
        results = {}
        
        try:
            # Попытка подключения к БД
            conn = psycopg2.connect(
                host="localhost",
                database="upgrade_db",
                user="upgrade",
                password="upgrade123"
            )
            
            with conn.cursor() as cur:
                # Проверка существования таблиц
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                tables = [row[0] for row in cur.fetchall()]
                
                expected_tables = [
                    "locations", "weather_measurements", 
                    "genomic_uploads", "pipeline_runs"
                ]
                
                table_status = {}
                for table in expected_tables:
                    table_status[table] = table in tables
                
                results["tables"] = table_status
                
                # Проверка данных
                if "locations" in tables:
                    cur.execute("SELECT COUNT(*) FROM locations")
                    results["locations_count"] = cur.fetchone()[0]
                
                if "weather_measurements" in tables:
                    cur.execute("SELECT COUNT(*) FROM weather_measurements")
                    results["weather_records_count"] = cur.fetchone()[0]
                    
                    cur.execute("""
                        SELECT MAX(measurement_datetime) 
                        FROM weather_measurements
                    """)
                    last_measurement = cur.fetchone()[0]
                    results["last_weather_measurement"] = str(last_measurement) if last_measurement else None
            
            conn.close()
            results["database_accessible"] = True
            
        except Exception as e:
            results["database_accessible"] = False
            results["database_error"] = str(e)
        
        return results
    
    def check_weather_pipeline(self):
        """Проверка pipeline погодных данных"""
        results = {}
        
        # Проверка Kafka топиков
        try:
            # Простая проверка через docker exec
            kafka_topics = subprocess.run([
                "docker", "exec", "upgrade_kafka",
                "kafka-topics", "--bootstrap-server", "localhost:9092", "--list"
            ], capture_output=True, text=True, timeout=10)
            
            if kafka_topics.returncode == 0:
                topics = kafka_topics.stdout.strip().split('\n')
                results["kafka_topics"] = topics
                results["weather_topic_exists"] = "weather-data" in topics
            else:
                results["kafka_error"] = kafka_topics.stderr
                
        except Exception as e:
            results["kafka_check_error"] = str(e)
        
        # Проверка MinIO buckets
        try:
            minio_client = Minio(
                "localhost:9000",
                access_key="minioadmin",
                secret_key="minioadmin",
                secure=False
            )
            
            buckets = [bucket.name for bucket in minio_client.list_buckets()]
            results["minio_buckets"] = buckets
            results["weather_bucket_exists"] = "weather-data" in buckets
            
            # Проверка данных в bucket
            if "weather-data" in buckets:
                objects = list(minio_client.list_objects("weather-data", recursive=True))
                results["weather_objects_count"] = len(objects)
                
        except Exception as e:
            results["minio_error"] = str(e)
        
        return results
    
    def check_streamlit(self):
        """Проверка Streamlit приложения"""
        results = {}
        
        # Проверка файлов Streamlit
        streamlit_dir = self.project_root / "streamlit"
        results["streamlit_dir_exists"] = streamlit_dir.exists()
        
        if streamlit_dir.exists():
            app_file = streamlit_dir / "app.py"
            dockerfile = streamlit_dir / "Dockerfile"
            requirements = streamlit_dir / "requirements.txt"
            
            results["app_py_exists"] = app_file.exists()
            results["dockerfile_exists"] = dockerfile.exists()
            results["requirements_exists"] = requirements.exists()
        
        # Проверка доступности приложения
        try:
            response = requests.get("http://localhost:8501", timeout=5)
            results["streamlit_accessible"] = response.status_code == 200
        except:
            results["streamlit_accessible"] = False
        
        return results
    
    def check_airflow(self):
        """Проверка Airflow"""
        results = {}
        
        # Проверка директорий Airflow
        airflow_dir = self.project_root / "airflow"
        results["airflow_dir_exists"] = airflow_dir.exists()
        
        if airflow_dir.exists():
            dags_dir = airflow_dir / "dags"
            plugins_dir = airflow_dir / "plugins"
            config_dir = airflow_dir / "config"
            
            results["dags_dir_exists"] = dags_dir.exists()
            results["plugins_dir_exists"] = plugins_dir.exists()
            results["config_dir_exists"] = config_dir.exists()
            
            # Проверка DAG файлов
            if dags_dir.exists():
                dag_files = list(dags_dir.glob("*.py"))
                results["dag_files_count"] = len(dag_files)
                results["dag_files"] = [f.name for f in dag_files]
        
        # Проверка доступности Airflow UI
        try:
            response = requests.get("http://localhost:8081", timeout=5)
            results["airflow_ui_accessible"] = response.status_code == 200
        except:
            results["airflow_ui_accessible"] = False
        
        # Проверка Airflow API
        try:
            auth = ('admin', 'admin123')
            response = requests.get(
                "http://localhost:8081/api/v1/dags", 
                auth=auth, 
                timeout=5
            )
            if response.status_code == 200:
                dags = response.json().get('dags', [])
                results["airflow_api_accessible"] = True
                results["airflow_dags_count"] = len(dags)
                results["dag_names"] = [dag['dag_id'] for dag in dags]
            else:
                results["airflow_api_accessible"] = False
        except Exception as e:
            results["airflow_api_error"] = str(e)
        
        return results
    
    def check_nextflow(self):
        """Проверка Nextflow"""
        results = {}
        
        # Проверка директории Nextflow
        nextflow_dir = self.project_root / "nextflow"
        results["nextflow_dir_exists"] = nextflow_dir.exists()
        
        if nextflow_dir.exists():
            main_nf = nextflow_dir / "main.nf"
            config_nf = nextflow_dir / "nextflow.config"
            modules_dir = nextflow_dir / "modules"
            
            results["main_nf_exists"] = main_nf.exists()
            results["config_exists"] = config_nf.exists()
            results["modules_dir_exists"] = modules_dir.exists()
            
            # Проверка модулей
            if modules_dir.exists():
                module_files = list(modules_dir.glob("*.nf"))
                results["module_files_count"] = len(module_files)
                results["module_files"] = [f.name for f in module_files]
        
        # Проверка установки Nextflow в контейнере
        try:
            nextflow_version = subprocess.run([
                "docker", "exec", "upgrade_streamlit",
                "which", "nextflow"
            ], capture_output=True, text=True, timeout=10)
            
            results["nextflow_installed"] = nextflow_version.returncode == 0
            
        except Exception as e:
            results["nextflow_check_error"] = str(e)
        
        return results
    
    def check_file_structure(self):
        """Проверка структуры файлов проекта"""
        results = {}
        
        expected_structure = {
            "README.md": "readme_exists",
            "docker-compose.yml": "compose_exists",
            "requirements.txt": "requirements_exists",
            "TODO.md": "todo_exists",
            "docs/": "docs_dir_exists",
            "database/": "database_dir_exists",
            "database/migrations/": "migrations_dir_exists",
            "kafka/": "kafka_dir_exists",
            "kafka/producer/": "producer_dir_exists", 
            "kafka/consumer/": "consumer_dir_exists",
            "results/": "results_dir_exists",
            "data/": "data_dir_exists",
            "sandbox/": "sandbox_dir_exists"
        }
        
        for path, key in expected_structure.items():
            full_path = self.project_root / path
            results[key] = full_path.exists()
        
        return results
    
    def print_results(self, results):
        """Вывод результатов проверки"""
        for key, value in results.items():
            if isinstance(value, bool):
                status = "✅" if value else "❌"
                print(f"  {status} {key.replace('_', ' ').title()}")
            elif isinstance(value, dict):
                print(f"  📋 {key.replace('_', ' ').title()}:")
                for subkey, subvalue in value.items():
                    if isinstance(subvalue, bool):
                        status = "✅" if subvalue else "❌"
                        print(f"    {status} {subkey}")
                    else:
                        print(f"    ℹ️  {subkey}: {subvalue}")
            elif isinstance(value, list):
                print(f"  📋 {key.replace('_', ' ').title()}: {len(value)} items")
                for item in value[:5]:  # Показываем первые 5
                    print(f"    - {item}")
                if len(value) > 5:
                    print(f"    ... и еще {len(value) - 5}")
            else:
                print(f"  ℹ️  {key.replace('_', ' ').title()}: {value}")
    
    def print_summary(self):
        """Вывод общей сводки"""
        print("=" * 60)
        print("📊 ОБЩАЯ СВОДКА ПО ПРОЕКТУ")
        print("=" * 60)
        
        total_checks = 0
        passed_checks = 0
        
        for section, results in self.results.items():
            if "error" in results:
                print(f"❌ {section}: ОШИБКА - {results['error']}")
                continue
                
            section_total = 0
            section_passed = 0
            
            def count_checks(data):
                nonlocal section_total, section_passed
                for key, value in data.items():
                    if isinstance(value, bool):
                        section_total += 1
                        if value:
                            section_passed += 1
                    elif isinstance(value, dict):
                        count_checks(value)
            
            count_checks(results)
            
            if section_total > 0:
                percentage = (section_passed / section_total) * 100
                status = "✅" if percentage > 80 else "⚠️" if percentage > 50 else "❌"
                print(f"{status} {section}: {section_passed}/{section_total} ({percentage:.1f}%)")
            
            total_checks += section_total
            passed_checks += section_passed
        
        print("-" * 60)
        if total_checks > 0:
            overall_percentage = (passed_checks / total_checks) * 100
            overall_status = "✅" if overall_percentage > 80 else "⚠️" if overall_percentage > 50 else "❌"
            print(f"{overall_status} ОБЩИЙ СТАТУС: {passed_checks}/{total_checks} ({overall_percentage:.1f}%)")
        
        # Рекомендации
        print("\n🎯 ПРИОРИТЕТНЫЕ ДЕЙСТВИЯ:")
        
        if not self.results.get("Infrastructure & Docker", {}).get("services", {}).get("PostgreSQL", False):
            print("1. Запустить PostgreSQL: docker-compose up -d postgres")
        
        if not self.results.get("Infrastructure & Docker", {}).get("services", {}).get("Airflow", False):
            print("2. Настроить Airflow: исправить пользователя и запустить")
        
        if not self.results.get("Airflow", {}).get("airflow_api_accessible", False):
            print("3. Создать пользователя Airflow для API доступа")
        
        if not self.results.get("Database Schema", {}).get("weather_records_count", 0):
            print("4. Запустить сбор погодных данных")
        
        print(f"\n⏰ Проверка завершена: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def main():
    if len(sys.argv) > 1:
        project_root = sys.argv[1]
    else:
        project_root = "."
    
    checker = UpgradeStatusChecker(project_root)
    checker.check_all()

if __name__ == "__main__":
    main()