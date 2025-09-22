from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.docker.operators.docker import DockerOperator

import json
import subprocess
import os
import requests
import redis
import time

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
    description='A genomic data QC pipeline MVP with Nextflow',
    schedule_interval=None,
    max_active_runs=5,
    is_paused_upon_creation=False,  # AUTO ENABLE DAG!
    tags=['genomic', 'qc', 'nextflow', 'upgrade'],
)

def validate_input_data(**context):
    """Валидация входных данных перед запуском пайплайна"""
    dag_run = context['dag_run']
    conf = dag_run.conf or {}
    
    required_params = ['sample_id', 'input_file_path', 'pipeline_id']
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
        'pipeline_id': conf['pipeline_id'],
        'run_id': context['run_id'],
        'sample_type': conf.get('sample_type', 'Unknown'),
        'location_id': conf.get('location_id'),
        'description': conf.get('description', ''),
        'sequencing_platform': conf.get('sequencing_platform', 'Unknown'),
        'priority': conf.get('priority', 'Normal'),
        'expected_organisms': conf.get('expected_organisms', ''),
        'sample_db_id': conf.get('sample_db_id')
    }

def create_pipeline_record(**context):
    """Создание записи о запуске пайплайна в PostgreSQL"""
    ti = context['task_instance']
    params = ti.xcom_pull(task_ids='validate_input')
    
    postgres_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    # SQL для создания записи в pipeline_runs
    sql = """
    INSERT INTO pipeline_runs (
        pipeline_id, sample_id, pipeline_name, status, 
        parameters, started_at, created_at, pipeline_version
    ) VALUES (
        %s, %s, 'genomic_qc_nextflow', 'running', %s, NOW(), NOW(), '1.0'
    )
    ON CONFLICT (pipeline_id) DO UPDATE SET
        status = 'running',
        started_at = NOW(),
        parameters = EXCLUDED.parameters
    """
    
    parameters_json = json.dumps({
        'sample_type': params['sample_type'],
        'sequencing_platform': params['sequencing_platform'],
        'priority': params['priority'],
        'expected_organisms': params['expected_organisms']
    })
    
    try:
        postgres_hook.run(sql, parameters=(
            params['pipeline_id'],
            params.get('sample_db_id', 1),  # Используем sample_db_id
            parameters_json
        ))
        print(f"Created/updated pipeline record for ID {params['pipeline_id']}")
    except Exception as e:
        print(f"Error creating pipeline record: {e}")
        # Не прерываем выполнение, продолжаем с предупреждением
        
    return params

def update_pipeline_status(pipeline_id: int, status: str, step: str = None, progress: int = None):
    """Обновление статуса пайплайна"""
    postgres_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    updates = ['status = %s']
    values = [status]
    
    if step:
        updates.append('pipeline_name = %s')
        values.append(step)
    
    if progress is not None and progress > 0:
        updates.append('runtime_minutes = %s')
        values.append(progress)
    
    if status == 'completed':
        updates.append('completed_at = NOW()')
    
    sql = f"UPDATE pipeline_runs SET {', '.join(updates)} WHERE pipeline_id = %s"
    values.append(pipeline_id)
    
    try:
        postgres_hook.run(sql, parameters=values)
        print(f"Updated pipeline {pipeline_id} status to {status}")
    except Exception as e:
        print(f"Error updating pipeline status: {e}")


def run_nextflow_pipeline(**context):
    """Запуск локального Nextflow с main.nf"""
    ti = context['task_instance']
    params = ti.xcom_pull(task_ids='create_pipeline_record')
    pipeline_id = params['pipeline_id']
    
    try:
        update_pipeline_status(pipeline_id, 'running', 'nextflow_starting')
        
        # Директории
        nextflow_dir = "/home/nicolaedrabcinski/research/lifetech/upgrade/nextflow"
        work_dir = f"{nextflow_dir}/work/{pipeline_id}"
        results_dir = f"{nextflow_dir}/results/{pipeline_id}"
        
        # Создаем директории
        os.makedirs(work_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        
        # Команда для вашего main.nf
        cmd = [
            'nextflow', 'run', 'main.nf',
            '--input', f"/home/nicolaedrabcinski/research/lifetech/upgrade/data/{params['input_file_path']}",
            '--outdir', results_dir,
            '--sample_id', params['sample_id'],
            '-work-dir', work_dir,
            '-with-report', f"{results_dir}/nextflow_report.html",
            '-with-timeline', f"{results_dir}/nextflow_timeline.html", 
            '-with-trace', f"{results_dir}/nextflow_trace.txt",
            '-resume'
        ]
        
        print(f"Running Nextflow from {nextflow_dir}: {' '.join(cmd)}")
        
        update_pipeline_status(pipeline_id, 'running', 'nextflow_executing')
        
        # Запускаем nextflow из директории nextflow
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
            cwd=nextflow_dir  # Запускаем из папки nextflow
        )
        
        if result.returncode == 0:
            update_pipeline_status(pipeline_id, 'completed', 'finished')
            print("Nextflow pipeline completed successfully")
            return {
                'status': 'success',
                'pipeline_id': pipeline_id,
                'stdout': result.stdout[-1000:],
                'results_dir': results_dir
            }
        else:
            update_pipeline_status(pipeline_id, 'failed', 'nextflow_failed')
            print(f"Nextflow stderr: {result.stderr}")
            raise Exception(f"Nextflow failed: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        update_pipeline_status(pipeline_id, 'failed', 'timeout')
        raise Exception("Nextflow pipeline timed out")
    except Exception as e:
        update_pipeline_status(pipeline_id, 'failed', 'error')
        raise e



def parse_results_and_store(**context):
    """Парсинг результатов и сохранение в БД"""
    ti = context['task_instance']
    pipeline_result = ti.xcom_pull(task_ids='run_nextflow')
    params = ti.xcom_pull(task_ids='create_pipeline_record')
    
    if not pipeline_result or pipeline_result['status'] != 'success':
        print("Pipeline failed, skipping results parsing")
        return
    
    pipeline_id = params['pipeline_id']
    
    # Обновляем время завершения в pipeline_runs
    postgres_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    sql = """
    UPDATE pipeline_runs 
    SET completed_at = NOW(),
        runtime_minutes = EXTRACT(EPOCH FROM (NOW() - started_at))/60
    WHERE pipeline_id = %s
    """
    
    try:
        postgres_hook.run(sql, parameters=(pipeline_id,))
        print(f"Results processed for pipeline {pipeline_id}")
    except Exception as e:
        print(f"Error updating completion time: {e}")


def notify_completion(**context):
    """Уведомление о завершении пайплайна"""
    ti = context['task_instance']
    params = ti.xcom_pull(task_ids='create_pipeline_record')
    pipeline_result = ti.xcom_pull(task_ids='run_nextflow')
    
    pipeline_id = params['pipeline_id']
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
            'pipeline_id': pipeline_id,
            'sample_id': sample_id,
            'status': pipeline_result['status'] if pipeline_result else 'failed',
            'timestamp': datetime.now().isoformat(),
            'results_dir': pipeline_result.get('results_dir') if pipeline_result else None
        }
        
        redis_client.lpush('pipeline_notifications', json.dumps(notification))
        redis_client.ltrim('pipeline_notifications', 0, 100)  # Храним последние 100
        
        print(f"Notification sent for pipeline {pipeline_id}")
        
    except Exception as e:
        print(f"Failed to send Redis notification: {e}")


# ===========================================
# Определение задач DAG
# ===========================================

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
    bash_command='nextflow -version',  # Убрали docker exec
    dag=dag
)

# Создание mock workflow если нужно
# create_workflow_task = PythonOperator(
#     task_id='create_mock_workflow',
#     python_callable=create_mock_nextflow_workflow,
#     dag=dag
# )

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

# ===========================================
# Определение зависимостей
# ===========================================
validate_task >> create_record_task >> check_nextflow >> run_pipeline_task >> parse_results_task >> notify_task