# pages/pipeline.py
import streamlit as st
from datetime import datetime
from pathlib import Path
import pandas as pd
import time

from components.header import create_header
from components.cards import create_status_card, create_pipeline_status_card
from services.airflow_client import AirflowClient
from services.minio_client import validate_genomic_file, save_file_to_minio
from database.connection import test_db_connection
from database.queries import fetch_locations, get_pipeline_runs_from_db, generate_pipeline_id, save_pipeline_run_to_db, create_sample_record
from services.minio_client import get_minio_client
from database.queries import fetch_locations, get_pipeline_runs_from_db, generate_pipeline_id, save_pipeline_run_to_db, create_sample_record

def genomic_pipeline_page():
    """Enhanced genomic pipeline page"""
    
    create_header(
        title="Genomic Quality Control Pipeline",
        subtitle="Upload FASTQ files and monitor real-time pipeline execution",
        description="Powered by Airflow and MinIO storage"
    )
    
    # Initialize session state
    if 'pipeline_runs' not in st.session_state:
        st.session_state.pipeline_runs = {}
    
    airflow_client = AirflowClient()
    
    # System Status
    st.markdown("### System Status")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        db_status = test_db_connection()
        create_status_card("Database", "Connected" if db_status else "Disconnected")
    
    with col2:
        airflow_status = airflow_client.test_connection()
        create_status_card("Airflow", "Connected" if airflow_status['success'] else "Disconnected")
    
    with col3:
        minio_client = get_minio_client()
        minio_status = bool(minio_client)
        create_status_card("MinIO Storage", "Connected" if minio_status else "Disconnected")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # File Upload Section
    st.markdown("### 1. Upload Sample for Analysis")
    
    with st.form("upload_form", clear_on_submit=False):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            <div style="border: 2px dashed #007bff; border-radius: 10px; padding: 2rem; text-align: center; background-color: #f8f9ff; margin: 1rem 0;">
                <h4>Drop your FASTQ files here</h4>
                <p>Supported formats: .fastq, .fq, .fastq.gz, .fq.gz, .fastq.bz2</p>
            </div>
            """, unsafe_allow_html=True)
            
            uploaded_file = st.file_uploader(
                "Choose FASTQ file",
                type=None,  # Allow all file types including .gz
                help="Upload a FASTQ file for genomic quality control analysis",
                label_visibility="collapsed"
            )
            
            if uploaded_file:
                file_size_mb = uploaded_file.size / (1024 * 1024)
                st.success(f"File selected: {uploaded_file.name} ({file_size_mb:.1f} MB)")
                
                validation_errors = validate_genomic_file(uploaded_file)
                if validation_errors:
                    for error in validation_errors:
                        st.error(f"Validation Error: {error}")
                else:
                    st.success("File validation passed - ready for processing!")
        
        with col2:
            if uploaded_file:
                st.markdown("**File Information**")
                st.info(f"**Extension:** {Path(uploaded_file.name).suffix}")
                st.info(f"**Size:** {uploaded_file.size:,} bytes")
                st.info(f"**Type:** FASTQ Sequencing Data")
        
        # Sample Metadata
        st.markdown("---")
        st.markdown("**Sample Metadata**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            sample_id = st.text_input(
                "Sample ID *",
                value=f"sample_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                help="Unique identifier for this sample"
            )
            
            sample_type = st.selectbox(
                "Sample Type *",
                ["Environmental", "Clinical", "Wastewater", "Soil", "Air", "Surface", "Water"]
            )
            
            sequencing_platform = st.selectbox(
                "Sequencing Platform",
                ["Oxford Nanopore", "Illumina", "PacBio", "Other", "Unknown"]
            )
        
        with col2:
            locations_df = fetch_locations()
            location_options = ["None"]
            if not locations_df.empty:
                location_options.extend([
                    f"{row['city']}, {row['country']} - {row['location_name']}" 
                    for _, row in locations_df.iterrows()
                ])
            
            selected_location = st.selectbox("Sample Location", location_options)
            
            priority = st.selectbox(
                "Analysis Priority",
                ["Normal", "High", "Urgent"],
                help="Higher priority samples are processed first"
            )
            
            expected_organisms = st.text_input(
                "Expected Organisms",
                placeholder="e.g., E. coli, SARS-CoV-2",
                help="Optional: Expected organisms in sample"
            )
        
        description = st.text_area(
            "Description",
            placeholder="Sample collection details, experimental conditions, notes...",
            height=80
        )
        
        st.markdown("---")
        col1, col2, col3 = st.columns([2, 1, 1])
        with col2:
            submitted = st.form_submit_button("🚀 Upload & Start Pipeline", type="primary")
        with col3:
            validate_only = st.form_submit_button("🧪 Validate Only")
        
        # Handle form submission INSIDE the form
        if validate_only and uploaded_file:
            validation_errors = validate_genomic_file(uploaded_file)
            if validation_errors:
                for error in validation_errors:
                    st.error(f"Validation Error: {error}")
            else:
                st.success("File validation passed - ready for upload!")
        
        if submitted and uploaded_file and sample_id and description:
            validation_errors = validate_genomic_file(uploaded_file)
            if not validation_errors:
                process_pipeline_submission(
                    uploaded_file, sample_id, sample_type, selected_location,
                    priority, expected_organisms, sequencing_platform,
                    description, locations_df, location_options, airflow_client
                )
            else:
                st.error("Cannot proceed with validation errors:")
                for error in validation_errors:
                    st.error(error)
        elif submitted and not uploaded_file:
            st.error("Please select a file to upload")
        elif submitted and not sample_id.strip():
            st.error("Please enter a Sample ID")
        elif submitted and not description.strip():
            st.error("Please enter a description")
    
    # Pipeline Monitoring
    st.markdown("---")
    st.markdown("### 2. Pipeline Monitoring Dashboard")
    show_pipeline_monitoring(airflow_client)

def process_pipeline_submission(uploaded_file, sample_id, sample_type, selected_location,
                               priority, expected_organisms, sequencing_platform,
                               description, locations_df, location_options, airflow_client):
    """Process pipeline submission"""
    
    with st.spinner("Processing submission..."):
        try:
            # 1. Generate pipeline ID
            pipeline_id = generate_pipeline_id()
            if not pipeline_id:
                st.error("Failed to generate pipeline ID")
                return
            
            # 2. Save file to MinIO
            minio_path, error = save_file_to_minio(uploaded_file, sample_id)
            if error:
                st.error(f"Upload failed: {error}")
                return
            
            # 3. Get location_id
            location_id = None
            if selected_location != "None" and not locations_df.empty:
                try:
                    location_index = location_options.index(selected_location) - 1
                    if 0 <= location_index < len(locations_df):
                        location_id = locations_df.iloc[location_index]['location_id']
                except (ValueError, IndexError):
                    pass
            
            # 4. CREATE SAMPLE RECORD FIRST
            sample_data = {
                'sample_id': sample_id,
                'sample_type': sample_type,
                'description': description,
                'location_id': location_id,
                'sequencing_platform': sequencing_platform,
                'expected_organisms': expected_organisms,
                'file_path': minio_path,
                'created_at': datetime.now()
            }
            
            sample_db_id = create_sample_record(sample_data)
            if not sample_db_id:
                st.error("Failed to create sample record")
                return
            
            st.success(f"Sample record created with ID: {sample_db_id}")
            
            # 5. Prepare DAG configuration
            dag_conf = {
                'pipeline_id': pipeline_id,
                'sample_id': sample_id,
                'sample_db_id': sample_db_id,
                'input_file_path': minio_path,
                'description': description,
                'sample_type': sample_type,
                'location_id': location_id,
                'sequencing_platform': sequencing_platform,
                'priority': priority,
                'expected_organisms': expected_organisms,
                'triggered_by': 'streamlit_ui',
                'trigger_time': datetime.now().isoformat(),
                'file_size_mb': uploaded_file.size / (1024 * 1024)
            }
            
            # 6. Trigger Airflow DAG
            result = airflow_client.trigger_dag('genomic_qc_pipeline_mvp', dag_conf)
            
            if result['success']:
                dag_run_id = result['dag_run_id']
                
                # 7. Save pipeline run to database with sample_db_id
                run_data = {
                    'run_id': pipeline_id,
                    'sample_db_id': sample_db_id,  # Use database ID instead of string
                    'status': 'queued',
                    'current_step': 'upload_complete',
                    'start_time': datetime.now(),
                    'description': description,
                    'input_file_path': minio_path
                }
                
                save_success = save_pipeline_run_to_db(run_data)
                
                # 8. Store in session state
                st.session_state.pipeline_runs[str(pipeline_id)] = {
                    'pipeline_id': pipeline_id,
                    'dag_run_id': dag_run_id,
                    'sample_id': sample_id,
                    'sample_db_id': sample_db_id,
                    'start_time': datetime.now(),
                    'status': 'queued',
                    'minio_path': minio_path,
                    'sample_type': sample_type,
                    'description': description,
                    'priority': priority
                }
                
                st.success("Pipeline launched successfully!")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.info(f"**Pipeline ID:** `{pipeline_id}`")
                    st.info(f"**Sample ID:** `{sample_id}`")
                    st.info(f"**Sample DB ID:** `{sample_db_id}`")
                with col2:
                    st.info(f"**Status:** {result.get('state', 'queued').upper()}")
                    st.info(f"**DAG Run ID:** `{dag_run_id}`")
                    st.info(f"**MinIO Path:** `{minio_path}`")
                
                if save_success:
                    st.success("Pipeline run saved to database")
                else:
                    st.warning("Pipeline started but database save failed")
                
                st.balloons()
            else:
                st.error(f"Pipeline launch failed: {result['error']}")
                
        except Exception as e:
            st.error(f"Unexpected error: {e}")
            st.write("Exception details:", str(e))

def show_pipeline_monitoring(airflow_client):
    """Display pipeline monitoring section"""
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🔄 Refresh", type="secondary"):
            st.cache_data.clear()
            st.rerun()
    with col2:
        auto_refresh = st.checkbox("Auto-refresh (30s)", value=False)
    with col3:
        show_completed = st.checkbox("Show Completed", value=True)
    with col4:
        show_failed = st.checkbox("Show Failed", value=True)
    
    # Get pipeline data
    db_pipeline_runs = get_pipeline_runs_from_db()

    # st.write("DEBUG - db_pipeline_runs type:", type(db_pipeline_runs))
    st.write("DEBUG - db_pipeline_runs content:", db_pipeline_runs)
    
    all_runs = {}
    
    if not db_pipeline_runs.empty:
        for _, row in db_pipeline_runs.iterrows():
            run_id = row['run_id']
            all_runs[run_id] = {
                'sample_id': row['sample_id'],
                'status': row['status'],
                'current_step': row['current_step'],
                'progress': row['progress_percentage'],
                'start_time': row['start_time'],
                'end_time': row['end_time'],
                'sample_type': row['sample_type'],
                'description': row['description'],
                'error_message': row['error_message'],
                'input_file_path': row['input_file_path']
            }
    
    # Add session state runs
    for run_id, run_data in st.session_state.pipeline_runs.items():
        if run_id not in all_runs:
            all_runs[run_id] = run_data
    
    # Filter runs based on checkboxes
    filtered_runs = {}
    for run_id, run_data in all_runs.items():
        status = run_data.get('status', 'unknown').lower()
        if status in ['completed', 'success'] and not show_completed:
            continue
        if status in ['failed', 'error'] and not show_failed:
            continue
        filtered_runs[run_id] = run_data
    
    if not filtered_runs:
        st.info("No pipeline runs found matching the current filters.")
        return
    
    # Display pipeline runs
    for run_id, run_data in sorted(filtered_runs.items(), 
                                   key=lambda x: x[1].get('start_time', datetime.now()), 
                                   reverse=True):
        display_pipeline_run(run_id, run_data, airflow_client)
    
    # Auto-refresh logic
    if auto_refresh:
        time.sleep(30)
        st.rerun()

# def display_pipeline_run(run_id, run_data, airflow_client):
#     """Display a single pipeline run"""
    
#     # Get latest status from Airflow if available
#     dag_run_id = run_data.get('dag_run_id')
#     if dag_run_id:
#         airflow_status = airflow_client.get_dag_run_status('genomic_qc_pipeline_mvp', dag_run_id)
#         if airflow_status['success']:
#             run_data['status'] = airflow_status['status']
#             run_data['current_step'] = airflow_status.get('current_task', run_data.get('current_step'))
    
#     # Create expandable container for each run
#     status = run_data.get('status', 'unknown').lower()
#     status_emoji = get_status_emoji(status)
    
#     # with st.expander(
#     #     f"{status_emoji} {run_data.get('sample_id', 'Unknown')} - {run_id[:8]}... ({status.upper()})",
#     #     expanded=(status in ['running', 'queued'])
#     # ):

#     with st.expander(
#         f"{status_emoji} {run_data.get('sample_id', 'Unknown')} - {str(run_id)[:8]}... ({status.upper()})",
#         expanded=(status in ['running', 'queued'])
#     ):
#         col1, col2, col3 = st.columns([2, 1, 1])
        
#         with col1:
#             st.markdown(f"**Sample ID:** {run_data.get('sample_id', 'N/A')}")
#             st.markdown(f"**Sample Type:** {run_data.get('sample_type', 'N/A')}")
#             st.markdown(f"**Description:** {run_data.get('description', 'N/A')}")
            
#             if run_data.get('error_message'):
#                 st.error(f"**Error:** {run_data['error_message']}")
        
#         with col2:
#             st.markdown(f"**Status:** {status.upper()}")
#             st.markdown(f"**Current Step:** {run_data.get('current_step', 'N/A')}")
#             st.markdown(f"**Priority:** {run_data.get('priority', 'Normal')}")
        
#         with col3:
#             start_time = run_data.get('start_time')
#             if start_time:
#                 if isinstance(start_time, str):
#                     start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
#                 st.markdown(f"**Started:** {start_time.strftime('%Y-%m-%d %H:%M')}")
            
#             end_time = run_data.get('end_time')
#             if end_time:
#                 if isinstance(end_time, str):
#                     end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
#                 st.markdown(f"**Ended:** {end_time.strftime('%Y-%m-%d %H:%M')}")
                
#                 # Calculate duration
#                 if start_time and end_time:
#                     duration = end_time - start_time
#                     st.markdown(f"**Duration:** {str(duration).split('.')[0]}")
        
#         # Progress bar
#         progress = run_data.get('progress', 0)
#         if isinstance(progress, (int, float)) and 0 <= progress <= 100:
#             st.progress(progress / 100)
#             st.caption(f"Progress: {progress}%")
        
#         # Action buttons
#         col1, col2, col3, col4 = st.columns(4)
        
#         with col1:
#             if st.button(f"📋 Details", key=f"details_{run_id}"):
#                 show_pipeline_details(run_id, run_data, airflow_client)
        
#         with col2:
#             if dag_run_id and st.button(f"📊 Logs", key=f"logs_{run_id}"):
#                 show_pipeline_logs(dag_run_id, airflow_client)
        
#         with col3:
#             if status in ['running', 'queued'] and st.button(f"⏹️ Stop", key=f"stop_{run_id}"):
#                 stop_pipeline_run(dag_run_id, airflow_client)
        
#         with col4:
#             if status in ['completed', 'success'] and st.button(f"📁 Results", key=f"results_{run_id}"):
#                 show_pipeline_results(run_id, run_data)

import time

def display_pipeline_run(run_id, run_data, airflow_client):
    """Display a single pipeline run"""
    
    # Generate unique timestamp for button keys
    timestamp = int(time.time() * 1000)
    
    # Get latest status from Airflow if available
    dag_run_id = run_data.get('dag_run_id')
    if dag_run_id:
        airflow_status = airflow_client.get_dag_run_status('genomic_qc_pipeline_mvp', dag_run_id)
        if airflow_status['success']:
            run_data['status'] = airflow_status['status']
            run_data['current_step'] = airflow_status.get('current_task', run_data.get('current_step'))
    
    # Create expandable container for each run
    status = run_data.get('status', 'unknown').lower()
    status_emoji = get_status_emoji(status)

    with st.expander(
        f"{status_emoji} {run_data.get('sample_id', 'Unknown')} - {str(run_id)[:8]}... ({status.upper()})",
        expanded=(status in ['running', 'queued'])
    ):
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.markdown(f"**Sample ID:** {run_data.get('sample_id', 'N/A')}")
            st.markdown(f"**Sample Type:** {run_data.get('sample_type', 'N/A')}")
            st.markdown(f"**Description:** {run_data.get('description', 'N/A')}")
            
            if run_data.get('error_message'):
                st.error(f"**Error:** {run_data['error_message']}")
        
        with col2:
            st.markdown(f"**Status:** {status.upper()}")
            st.markdown(f"**Current Step:** {run_data.get('current_step', 'N/A')}")
            st.markdown(f"**Priority:** {run_data.get('priority', 'Normal')}")
        
        with col3:
            start_time = run_data.get('start_time')
            if start_time:
                if isinstance(start_time, str):
                    start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                st.markdown(f"**Started:** {start_time.strftime('%Y-%m-%d %H:%M')}")
            
            end_time = run_data.get('end_time')
            if end_time:
                if isinstance(end_time, str):
                    end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                st.markdown(f"**Ended:** {end_time.strftime('%Y-%m-%d %H:%M')}")
                
                # Calculate duration
                if start_time and end_time:
                    duration = end_time - start_time
                    st.markdown(f"**Duration:** {str(duration).split('.')[0]}")
        
        # Progress bar
        progress = run_data.get('progress', 0)
        if isinstance(progress, (int, float)) and 0 <= progress <= 100:
            st.progress(progress / 100)
            st.caption(f"Progress: {progress}%")
        
        # Action buttons with unique keys using timestamp
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button(f"📋 Details", key=f"details_{run_id}_{timestamp}"):
                show_pipeline_details(run_id, run_data, airflow_client)
        
        with col2:
            if dag_run_id and st.button(f"📊 Logs", key=f"logs_{run_id}_{timestamp}"):
                show_pipeline_logs(dag_run_id, airflow_client)
        
        with col3:
            if status in ['running', 'queued'] and st.button(f"⏹️ Stop", key=f"stop_{run_id}_{timestamp}"):
                stop_pipeline_run(dag_run_id, airflow_client)
        
        with col4:
            if status in ['completed', 'success'] and st.button(f"📁 Results", key=f"results_{run_id}_{timestamp}"):
                show_pipeline_results(run_id, run_data)

def get_status_emoji(status):
    """Get emoji for pipeline status"""
    status_emojis = {
        'queued': '⏳',
        'running': '🔄',
        'completed': '✅',
        'success': '✅',
        'failed': '❌',
        'error': '❌',
        'cancelled': '⏹️',
        'stopped': '⏹️'
    }
    return status_emojis.get(status.lower(), '❔')

def show_pipeline_details(run_id, run_data, airflow_client):
    """Show detailed information about a pipeline run"""
    st.markdown("### 📋 Pipeline Run Details")
    
    # Basic information
    st.markdown("#### Basic Information")
    details_df = pd.DataFrame([
        ["Run ID", run_id],
        ["Sample ID", run_data.get('sample_id', 'N/A')],
        ["Status", run_data.get('status', 'N/A')],
        ["Sample Type", run_data.get('sample_type', 'N/A')],
        ["Priority", run_data.get('priority', 'Normal')],
        ["Sequencing Platform", run_data.get('sequencing_platform', 'N/A')],
        ["Expected Organisms", run_data.get('expected_organisms', 'N/A')],
        ["Input File Path", run_data.get('input_file_path', 'N/A')],
    ], columns=["Property", "Value"])
    
    st.dataframe(details_df, use_container_width=True, hide_index=True)
    
    # Timeline information
    st.markdown("#### Timeline")
    timeline_data = []
    
    start_time = run_data.get('start_time')
    if start_time:
        timeline_data.append(["Started", start_time])
    
    end_time = run_data.get('end_time')
    if end_time:
        timeline_data.append(["Ended", end_time])
    
    if timeline_data:
        timeline_df = pd.DataFrame(timeline_data, columns=["Event", "Time"])
        st.dataframe(timeline_df, use_container_width=True, hide_index=True)

def show_pipeline_logs(dag_run_id, airflow_client):
    """Show pipeline logs from Airflow"""
    st.markdown("### 📊 Pipeline Logs")
    
    with st.spinner("Fetching logs from Airflow..."):
        logs_result = airflow_client.get_dag_run_logs('genomic_qc_pipeline_mvp', dag_run_id)
        
        if logs_result['success']:
            logs = logs_result.get('logs', {})
            
            if not logs:
                st.info("No logs available yet.")
                return
            
            # Display logs for each task
            for task_id, task_logs in logs.items():
                with st.expander(f"Task: {task_id}", expanded=True):
                    if task_logs:
                        st.code(task_logs, language='text')
                    else:
                        st.info("No logs for this task yet.")
        else:
            st.error(f"Failed to fetch logs: {logs_result.get('error', 'Unknown error')}")

def stop_pipeline_run(dag_run_id, airflow_client):
    """Stop a running pipeline"""
    if dag_run_id:
        with st.spinner("Stopping pipeline..."):
            result = airflow_client.stop_dag_run('genomic_qc_pipeline_mvp', dag_run_id)
            
            if result['success']:
                st.success("Pipeline stopped successfully!")
                st.rerun()
            else:
                st.error(f"Failed to stop pipeline: {result.get('error', 'Unknown error')}")

def show_pipeline_results(run_id, run_data):
    """Show pipeline results and outputs"""
    st.markdown("### 📁 Pipeline Results")
    
    # Mock results for demonstration
    st.markdown("#### Quality Control Results")
    
    # Sample quality metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Reads", "2,456,789", "12,345")
    with col2:
        st.metric("Quality Score", "28.4", "0.2")
    with col3:
        st.metric("GC Content", "42.1%", "-0.3%")
    with col4:
        st.metric("N50", "1,245 bp", "23 bp")
    
    # Results files
    st.markdown("#### Output Files")
    results_files = [
        {"File": "quality_report.html", "Type": "HTML Report", "Size": "2.4 MB"},
        {"File": "filtered_reads.fastq", "Type": "FASTQ", "Size": "156.7 MB"},
        {"File": "quality_stats.json", "Type": "JSON", "Size": "12.3 KB"},
        {"File": "adapter_trimming_log.txt", "Type": "Log", "Size": "8.9 KB"}
    ]
    
    results_df = pd.DataFrame(results_files)
    st.dataframe(results_df, use_container_width=True, hide_index=True)
    
    # Download buttons
    st.markdown("#### Download Results")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.download_button(
            "📄 Quality Report",
            data="Mock HTML report content...",
            file_name="quality_report.html",
            mime="text/html"
        )
    
    with col2:
        st.download_button(
            "📊 Quality Stats",
            data='{"total_reads": 2456789, "quality_score": 28.4}',
            file_name="quality_stats.json",
            mime="application/json"
        )
    
    with col3:
        st.download_button(
            "📝 Full Log",
            data="Mock log file content...",
            file_name="pipeline_log.txt",
            mime="text/plain"
        )