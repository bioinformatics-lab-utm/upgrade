from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.http.sensors.http import HttpSensor

import json
import subprocess
import os
import requests
import redis

default_args = {
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'catchup': False
}

dag = DAG(
    'genomic_qc_pipeline_mvp',
    default_args=default_args,
    description='A genomic data QC pipeline MVP',
    schedule_interval=None,
    max_active_runs=5,
)

def validate_input_data(**context):
    """Валидация входных данных перед запуском пайплайна"""
    dag_run = context['dag_run']
    conf = dag_run.conf or {}
    
    required_params = ['sample_id', 'input_file_path', 'upload_id']
    for param in required_params:
        if param not in conf:
            raise ValueError(f"Missing required parameter: {param}")
    
    # Проверяем существование файла в MinIO
    sample_id = conf['sample_id']
    input_file = conf['input_file_path']
    
    print(f"Validating pipeline input for sample {sample_id}")
    print(f"Input file: {input_file}")
    
    # Сохраняем валидированные параметры в XCom
    return {
        'sample_id': sample_id,
        'input_file_path': input_file,
        'upload_id': conf['upload_id'],
        'run_id': context['run_id'],
        'sample_type': conf.get('sample_type', 'Unknown'),
        'location_id': conf.get('location_id'),
        'description': conf.get('description', '')
    }

def create_pipeline_record(**context):
    """Создание записи о запуске пайплайна в PostgreSQL"""
    ti = context['task_instance']
    params = ti.xcom_pull(task_ids='validate_input')
    
    postgres_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    # SQL для создания записи
    sql = """
    INSERT INTO pipeline_runs (
        run_id, upload_id, sample_id, pipeline_name, status, 
        input_file_path, output_directory, current_step, progress_percentage
    ) VALUES (
        %s, %s, %s, 'genomic_qc', 'pending', %s, %s, 'initializing', 0
    )
    """
    
    output_dir = f"s3://genomic-data/results/{params['run_id']}"
    
    postgres_hook.run(sql, parameters=(
        params['run_id'],
        params['upload_id'],
        params['sample_id'],
        params['input_file_path'],
        output_dir
    ))
    
    print(f"Created pipeline record for run {params['run_id']}")
    return params


def update_pipeline_status(run_id: str, status: str, step: str = None, progress: int = None):
    """Обновление статуса пайплайна"""
    postgres_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    updates = ['status = %s', 'updated_at = NOW()']
    values = [status]
    
    if step:
        updates.append('current_step = %s')
        values.append(step)
    
    if progress is not None:
        updates.append('progress_percentage = %s')
        values.append(progress)
    
    sql = f"UPDATE pipeline_runs SET {', '.join(updates)} WHERE run_id = %s"
    values.append(run_id)
    
    postgres_hook.run(sql, parameters=values)


def run_nextflow_pipeline(**context):
    """Запуск Nextflow пайплайна"""
    ti = context['task_instance']
    params = ti.xcom_pull(task_ids='create_pipeline_record')
    run_id = params['run_id']
    
    try:
        # Обновляем статус
        update_pipeline_status(run_id, 'running', 'nextflow_starting', 10)
        
        # Настройка путей
        nextflow_dir = "/opt/airflow/dags/nextflow"  # Путь в контейнере Airflow
        main_nf = f"{nextflow_dir}/main.nf"
        config_file = f"{nextflow_dir}/nextflow.config"
        work_dir = f"/tmp/nextflow-work/{run_id}"
        
        # Создаем рабочую директорию
        os.makedirs(work_dir, exist_ok=True)
        
        # Команда для запуска Nextflow
        cmd = [
            'nextflow', 'run', main_nf,
            '-c', config_file,
            '-work-dir', work_dir,
            '--input_dir', f"s3://genomic-data/{params['input_file_path']}",
            '--outdir', f"s3://genomic-data/results/{run_id}",
            '--sample_id', params['sample_id'],
            '-with-report', f"s3://genomic-data/reports/{run_id}/report.html",
            '-with-timeline', f"s3://genomic-data/reports/{run_id}/timeline.html",
            '-with-trace', f"s3://genomic-data/reports/{run_id}/trace.txt",
            '-profile', 'docker',
            '-resume'
        ]
        
        print(f"Running command: {' '.join(cmd)}")
        
        # Обновляем статус
        update_pipeline_status(run_id, 'running', 'nextflow_executing', 20)
        
        # Запускаем Nextflow
        result = subprocess.run(
            cmd,
            cwd=nextflow_dir,
            capture_output=True,
            text=True,
            timeout=3600  # 1 час таймаут
        )
        
        if result.returncode == 0:
            update_pipeline_status(run_id, 'completed', 'finished', 100)
            print("Nextflow pipeline completed successfully")
            return {
                'status': 'success',
                'run_id': run_id,
                'stdout': result.stdout[-1000:],  # Последние 1000 символов
                'output_dir': f"s3://genomic-data/results/{run_id}"
            }
        else:
            update_pipeline_status(run_id, 'failed', 'nextflow_failed', 0)
            raise Exception(f"Nextflow failed with return code {result.returncode}: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        update_pipeline_status(run_id, 'failed', 'timeout', 0)
        raise Exception("Nextflow pipeline timed out")
    except Exception as e:
        update_pipeline_status(run_id, 'failed', 'error', 0)
        raise e
    

def parse_results_and_store(**context):
    """Парсинг результатов и сохранение в БД"""
    ti = context['task_instance']
    pipeline_result = ti.xcom_pull(task_ids='run_nextflow')
    params = ti.xcom_pull(task_ids='create_pipeline_record')
    
    if not pipeline_result or pipeline_result['status'] != 'success':
        print("Pipeline failed, skipping results parsing")
        return
    
    run_id = params['run_id']
    
    # Здесь можно добавить парсинг результатов NanoPlot и Filtlong
    # Пока заглушка для сохранения базовой информации
    
    postgres_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    # Обновляем время завершения
    sql = """
    UPDATE pipeline_runs 
    SET end_time = NOW(),
        duration_seconds = EXTRACT(EPOCH FROM (NOW() - start_time))
    WHERE run_id = %s
    """
    
    postgres_hook.run(sql, parameters=(run_id,))
    
    print(f"Results processed for run {run_id}")

def notify_completion(**context):
    """Уведомление о завершении пайплайна"""
    ti = context['task_instance']
    params = ti.xcom_pull(task_ids='create_pipeline_record')
    pipeline_result = ti.xcom_pull(task_ids='run_nextflow')
    
    run_id = params['run_id']
    sample_id = params['sample_id']
    
    # Обновляем Redis для real-time уведомлений в Streamlit
    try:
        redis_client = redis.Redis(
            host='redis',
            port=6379,
            password=os.getenv('REDIS_PASSWORD', ''),
            decode_responses=True
        )
        
        notification = {
            'type': 'pipeline_completed',
            'run_id': run_id,
            'sample_id': sample_id,
            'status': pipeline_result['status'] if pipeline_result else 'failed',
            'timestamp': datetime.now().isoformat(),
            'output_dir': pipeline_result.get('output_dir') if pipeline_result else None
        }
        
        redis_client.lpush('pipeline_notifications', json.dumps(notification))
        redis_client.ltrim('pipeline_notifications', 0, 100)  # Храним последние 100
        
        print(f"Notification sent for pipeline {run_id}")
        
    except Exception as e:
        print(f"Failed to send Redis notification: {e}")

# Определение задач DAG
validate_task = PythonOperator(
    task_id='validate_input',
    python_callable=validate_input_data,
    dag=dag
)

create_record_task = PythonOperator(
    task_id='create_pipeline_record',
    python_callable=create_pipeline_record,
    dag=dag
)

# Проверка доступности Nextflow
check_nextflow = BashOperator(
    task_id='check_nextflow_available',
    bash_command='which nextflow && nextflow -version',
    dag=dag
)

run_pipeline_task = PythonOperator(
    task_id='run_nextflow',
    python_callable=run_nextflow_pipeline,
    dag=dag
)

parse_results_task = PythonOperator(
    task_id='parse_results',
    python_callable=parse_results_and_store,
    dag=dag
)

notify_task = PythonOperator(
    task_id='notify_completion',
    python_callable=notify_completion,
    dag=dag,
    trigger_rule='all_done'  # Выполняется независимо от успеха/неудачи
)

# Определение зависимостей
validate_task >> create_record_task >> check_nextflow >> run_pipeline_task >> parse_results_task >> notify_task