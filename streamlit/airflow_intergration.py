# Интеграция Streamlit с Airflow

import streamlit as st
import requests
import json
import base64
from datetime import datetime
import pandas as pd
import time

class AirflowClient:
    """Клиент для взаимодействия с Airflow API"""
    
    def __init__(self):
        self.base_url = "http://airflow-webserver:8080/api/v1"
        self.auth = ('admin', 'admin123')  # Из вашего docker-compose
    
    def trigger_dag(self, dag_id: str, conf: dict) -> dict:
        """Запуск DAG через Airflow API"""
        url = f"{self.base_url}/dags/{dag_id}/dagRuns"
        
        payload = {
            "conf": conf,
            "dag_run_id": f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{conf.get('sample_id', 'unknown')}"
        }
        
        try:
            response = requests.post(
                url,
                json=payload,
                auth=self.auth,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'dag_run_id': response.json()['dag_run_id'],
                    'execution_date': response.json()['execution_date']
                }
            else:
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}: {response.text}"
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_dag_run_status(self, dag_id: str, dag_run_id: str) -> dict:
        """Получение статуса выполнения DAG"""
        url = f"{self.base_url}/dags/{dag_id}/dagRuns/{dag_run_id}"
        
        try:
            response = requests.get(url, auth=self.auth)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'state': data['state'],
                    'start_date': data['start_date'],
                    'end_date': data.get('end_date'),
                    'execution_date': data['execution_date']
                }
            else:
                return {'success': False, 'error': f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_task_instances(self, dag_id: str, dag_run_id: str) -> dict:
        """Получение статуса задач в DAG run"""
        url = f"{self.base_url}/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances"
        
        try:
            response = requests.get(url, auth=self.auth)
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'task_instances': response.json()['task_instances']
                }
            else:
                return {'success': False, 'error': f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}

def enhanced_genomic_upload_with_airflow():
    """Улучшенная страница загрузки с интеграцией через Airflow"""
    st.header("Genomic Data Upload & Analysis via Airflow")
    st.markdown("Upload genomic files and trigger automated quality control pipeline")
    
    # Инициализация
    if 'airflow_runs' not in st.session_state:
        st.session_state.airflow_runs = {}
    
    airflow_client = AirflowClient()
    
    # Форма загрузки
    with st.form("upload_and_trigger_form"):
        st.subheader("Upload New Sample")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            uploaded_file = st.file_uploader(
                "Choose FASTQ file",
                type=['fastq', 'fq', 'fastq.gz', 'fq.gz'],
                help="Select a FASTQ file for quality control analysis"
            )
            
            if uploaded_file:
                file_size_mb = uploaded_file.size / (1024 * 1024)
                st.success(f"File: {uploaded_file.name} ({file_size_mb:.1f} MB)")
        
        with col2:
            if uploaded_file:
                st.info(f"**Size:** {file_size_mb:.1f} MB")
                st.info(f"**Type:** {Path(uploaded_file.name).suffix}")
        
        # Метаданные
        col1, col2 = st.columns(2)
        
        with col1:
            sample_id = st.text_input(
                "Sample ID",
                value=f"sample_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                help="Unique identifier for this sample"
            )
            
            # Локации
            locations_df = fetch_locations()
            location_options = ["None"]
            if not locations_df.empty:
                location_options.extend([
                    f"{row['city']}, {row['country']} - {row['location_name']}" 
                    for _, row in locations_df.iterrows()
                ])
            
            selected_location = st.selectbox("Sample Location", location_options)
        
        with col2:
            sample_type = st.selectbox(
                "Sample Type",
                ["Environmental", "Clinical", "Wastewater", "Soil", "Air", "Surface"]
            )
            
            description = st.text_area(
                "Description",
                placeholder="Sample collection details...",
                height=80
            )
        
        # Опции анализа
        st.subheader("Analysis Options")
        pipeline_options = st.multiselect(
            "Select Pipeline Steps",
            ["Quality Control (NanoPlot)", "Read Filtering (Filtlong)", "Generate Reports"],
            default=["Quality Control (NanoPlot)", "Read Filtering (Filtlong)", "Generate Reports"]
        )
        
        submitted = st.form_submit_button("Upload & Trigger Pipeline", type="primary")
    
    # Обработка отправки формы
    if submitted and uploaded_file and sample_id and description:
        with st.spinner("Uploading file and triggering Airflow pipeline..."):
            try:
                # 1. Загружаем файл в MinIO
                nextflow_manager = UpgradeNextflowManager()
                minio_path = nextflow_manager.upload_to_raw_layer(uploaded_file, sample_id)
                
                # 2. Сохраняем метаданные в PostgreSQL
                location_id = None
                if selected_location != "None":
                    location_index = location_options.index(selected_location) - 1
                    location_id = locations_df.iloc[location_index]['location_id']
                
                upload_id = save_upload_metadata(
                    filename=sample_id,
                    original_name=uploaded_file.name,
                    file_size=uploaded_file.size,
                    file_hash=hashlib.sha256(uploaded_file.read()).hexdigest(),
                    minio_path=minio_path,
                    location_id=location_id,
                    sample_type=sample_type,
                    description=description
                )
                
                # 3. Формируем конфигурацию для Airflow DAG
                dag_conf = {
                    'sample_id': sample_id,
                    'input_file_path': minio_path,
                    'upload_id': upload_id,
                    'sample_type': sample_type,
                    'location_id': location_id,
                    'description': description,
                    'pipeline_options': pipeline_options,
                    'triggered_by': 'streamlit',
                    'trigger_time': datetime.now().isoformat()
                }
                
                # 4. Запускаем Airflow DAG
                result = airflow_client.trigger_dag('genomic_qc_pipeline', dag_conf)
                
                if result['success']:
                    dag_run_id = result['dag_run_id']
                    
                    # Сохраняем информацию о запуске
                    st.session_state.airflow_runs[dag_run_id] = {
                        'sample_id': sample_id,
                        'start_time': datetime.now(),
                        'status': 'triggered',
                        'upload_id': upload_id,
                        'minio_path': minio_path
                    }
                    
                    st.success(f"Pipeline triggered successfully!")
                    st.info(f"DAG Run ID: {dag_run_id}")
                    st.info(f"File uploaded to: {minio_path}")
                    st.balloons()
                else:
                    st.error(f"Failed to trigger pipeline: {result['error']}")
                    
            except Exception as e:
                st.error(f"Error: {e}")
    
    # Мониторинг активных пайплайнов
    st.markdown("---")
    display_airflow_pipeline_monitoring(airflow_client)

def display_airflow_pipeline_monitoring(airflow_client: AirflowClient):
    """Отображение мониторинга Airflow пайплайнов"""
    st.subheader("Pipeline Monitoring (Airflow)")
    
    if not st.session_state.airflow_runs:
        st.info("No pipeline runs found")
        return
    
    # Кнопка обновления
    if st.button("Refresh Status"):
        st.rerun()
    
    # Отображение каждого запуска
    for dag_run_id, run_info in st.session_state.airflow_runs.items():
        with st.expander(
            f"Sample: {run_info['sample_id']} - DAG: {dag_run_id[:20]}...",
            expanded=run_info.get('status') not in ['success', 'failed']
        ):
            # Получаем актуальный статус из Airflow
            dag_status = airflow_client.get_dag_run_status('genomic_qc_pipeline', dag_run_id)
            
            if dag_status['success']:
                current_state = dag_status['state']
                start_date = dag_status['start_date']
                end_date = dag_status.get('end_date')
                
                # Обновляем локальный статус
                st.session_state.airflow_runs[dag_run_id]['status'] = current_state
                
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # Статус
                    if current_state == 'running':
                        st.info(f"Status: {current_state.upper()}")
                    elif current_state == 'success':
                        st.success(f"Status: {current_state.upper()}")
                    elif current_state == 'failed':
                        st.error(f"Status: {current_state.upper()}")
                    else:
                        st.warning(f"Status: {current_state.upper()}")
                    
                    # Временные метки
                    st.write(f"**Started:** {start_date}")
                    if end_date:
                        st.write(f"**Ended:** {end_date}")
                        # Рассчитываем длительность
                        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                        duration = end_dt - start_dt
                        st.write(f"**Duration:** {duration}")
                
                with col2:
                    st.write("**Sample Info:**")
                    st.write(f"ID: `{run_info['sample_id']}`")
                    st.write(f"Upload ID: {run_info['upload_id']}")
                    
                    # Ссылка на Airflow UI
                    airflow_url = f"http://localhost:8081/dags/genomic_qc_pipeline/graph?dag_run_id={dag_run_id}"
                    st.markdown(f"[View in Airflow]({airflow_url})")
                
                # Детали задач
                task_status = airflow_client.get_task_instances('genomic_qc_pipeline', dag_run_id)
                
                if task_status['success']:
                    st.write("**Task Status:**")
                    task_df = pd.DataFrame(task_status['task_instances'])
                    
                    if not task_df.empty:
                        # Отображаем только нужные колонки
                        display_cols = ['task_id', 'state', 'start_date', 'end_date']
                        available_cols = [col for col in display_cols if col in task_df.columns]
                        st.dataframe(task_df[available_cols], use_container_width=True)
            else:
                st.error(f"Failed to get status: {dag_status['error']}")

# Добавляем в основное Streamlit приложение
def main_with_airflow():
    """Главная функция с интеграцией Airflow"""
    st.set_page_config(
        page_title="UPGRADE - Genomic Surveillance",
        page_icon="🧬",
        layout="wide"
    )
    
    st.title("UPGRADE - Environmental Genomic Surveillance")
    st.markdown("Real-time genomic analysis platform with Airflow orchestration")
    
    # Навигация
    tab1, tab2, tab3, tab4 = st.tabs([
        "Dashboard", 
        "Upload & Analysis (Airflow)", 
        "Sample Map", 
        "System Monitor"
    ])
    
    with tab1:
        dashboard_page()
    
    with tab2:
        enhanced_genomic_upload_with_airflow()
    
    with tab3:
        display_results_map()
    
    with tab4:
        system_status_page()

if __name__ == "__main__":
    main_with_airflow()