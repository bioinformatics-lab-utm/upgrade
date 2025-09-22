# app.py
import streamlit as st
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# Page configuration
st.set_page_config(
    page_title="UPGRADE - Environmental Genomic Surveillance",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Import pages
try:
    from pages.dashboard import dashboard_page
    from pages.pipeline import genomic_pipeline_page
    from database.connection import test_db_connection
    from services.airflow_client import AirflowClient
    from services.minio_client import get_minio_client
    from database.queries import get_pipeline_runs_from_db
    
    IMPORTS_AVAILABLE = True
except ImportError as e:
    st.error(f"Import error: {e}")
    IMPORTS_AVAILABLE = False

def create_sidebar():
    """Create enhanced sidebar with status"""
    st.sidebar.markdown("""
    <div style="text-align: center; padding: 1rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; margin-bottom: 1rem;">
        <h2 style="color: white; margin: 0;">🧬 UPGRADE</h2>
        <p style="color: rgba(255,255,255,0.8); margin: 0.5rem 0 0 0;">Environmental Genomic Surveillance</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Navigation
    page = st.sidebar.selectbox(
        "Navigate to:",
        ["🏠 Dashboard", "🧬 Genomic Pipeline", "⚙️ Settings"],
        key="navigation"
    )
    
    # System status
    st.sidebar.markdown("---")
    st.sidebar.markdown("**System Status**")
    
    if IMPORTS_AVAILABLE:
        try:
            db_status = test_db_connection()
            airflow_client = AirflowClient()
            airflow_status = airflow_client.test_connection()['success']
            minio_status = bool(get_minio_client())
            
            status_html = f"""
            <div style="padding: 0.5rem;">
                <p style="margin: 0.2rem 0;">{'✅' if db_status else '❌'} Database</p>
                <p style="margin: 0.2rem 0;">{'✅' if airflow_status else '❌'} Airflow</p>
                <p style="margin: 0.2rem 0;">{'✅' if minio_status else '❌'} MinIO</p>
            </div>
            """
            st.sidebar.markdown(status_html, unsafe_allow_html=True)
            
            # Quick stats
            pipeline_runs_df = get_pipeline_runs_from_db()
            if not pipeline_runs_df.empty:
                running_count = len(pipeline_runs_df[pipeline_runs_df['status'].isin(['running', 'queued'])])
                total_count = len(pipeline_runs_df)
                
                st.sidebar.markdown("---")
                st.sidebar.markdown("**Quick Stats**")
                st.sidebar.metric("Active Pipelines", running_count)
                st.sidebar.metric("Total Runs", total_count)
        
        except Exception as e:
            st.sidebar.error(f"Status check failed: {e}")
    else:
        st.sidebar.error("System components not available")
    
    return page

def settings_page():
    """Settings and system status page"""
    st.title("⚙️ Settings & Configuration")
    st.markdown("---")
    
    if not IMPORTS_AVAILABLE:
        st.error("Cannot load system components. Check your installation.")
        return
    
    st.markdown("### System Health Check")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Database Connection**")
        try:
            db_status = test_db_connection()
            if db_status:
                st.success("✅ Connected")
            else:
                st.error("❌ Connection Failed")
        except Exception as e:
            st.error(f"❌ Error: {e}")
    
    with col2:
        st.markdown("**Airflow Service**")
        try:
            airflow_client = AirflowClient()
            status = airflow_client.test_connection()
            if status['success']:
                st.success("✅ Connected")
            else:
                st.error(f"❌ {status['error']}")
        except Exception as e:
            st.error(f"❌ Error: {e}")
    
    with col3:
        st.markdown("**MinIO Storage**")
        try:
            minio_client = get_minio_client()
            if minio_client:
                st.success("✅ Connected")
            else:
                st.error("❌ Client Unavailable")
        except Exception as e:
            st.error(f"❌ Error: {e}")
    
    # Cache management
    st.markdown("---")
    st.markdown("### Cache Management")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Clear Data Cache"):
            st.cache_data.clear()
            st.success("Cache cleared!")
    
    with col2:
        if st.button("🔄 Reset Session"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.success("Session reset!")
            st.rerun()

def fallback_dashboard():
    """Fallback dashboard when imports fail"""
    st.title("🧬 UPGRADE - Environmental Genomic Surveillance")
    st.markdown("---")
    
    st.error("System components are not properly configured.")
    st.markdown("### Troubleshooting Steps:")
    st.markdown("1. Check that all required Python packages are installed")
    st.markdown("2. Verify database connection settings")
    st.markdown("3. Ensure Airflow service is running")
    st.markdown("4. Check MinIO storage configuration")
    
    st.markdown("---")
    st.markdown("### Environment Check:")
    
    import os
    
    env_vars = [
        'POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_DB', 
        'POSTGRES_USER', 'POSTGRES_PASSWORD',
        'MINIO_ENDPOINT', 'MINIO_ACCESS_KEY', 'MINIO_SECRET_KEY',
        'AIRFLOW_HOST', 'AIRFLOW_PORT'
    ]
    
    for var in env_vars:
        value = os.getenv(var, 'Not Set')
        if value == 'Not Set':
            st.error(f"❌ {var}: {value}")
        else:
            st.success(f"✅ {var}: {'*' * len(value) if 'PASSWORD' in var or 'SECRET' in var else value}")

def fallback_pipeline():
    """Fallback pipeline page when imports fail"""
    st.title("🧬 Genomic Pipeline")
    st.markdown("---")
    
    st.error("Pipeline functionality is not available due to missing system components.")
    st.info("Please check the Settings page to resolve configuration issues.")

def main():
    """Main application function"""
    
    # Create sidebar and get selected page
    page = create_sidebar()
    
    # Footer in sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("""
    <div style="text-align: center; color: #6c757d; font-size: 0.8rem;">
        <p><strong>UPGRADE Project</strong></p>
        <p>🇷🇴 Romania - 🇲🇩 Moldova</p>
        <p>Environmental Genomic Surveillance</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Route to appropriate page
    if page == "🏠 Dashboard":
        if IMPORTS_AVAILABLE:
            try:
                dashboard_page()
            except Exception as e:
                st.error(f"Dashboard error: {e}")
                fallback_dashboard()
        else:
            fallback_dashboard()
    
    # elif page == "🧬 Genomic Pipeline":
    #     if IMPORTS_AVAILABLE:
    #         try:
    #             genomic_pipeline_page()
    #         except Exception as e:
    #             st.error(f"Pipeline error: {e}")
    #             fallback_pipeline()
    #     else:
    #         fallback_pipeline()

    elif page == "🧬 Genomic Pipeline":
        if IMPORTS_AVAILABLE:
            try:
                genomic_pipeline_page()
            except Exception as e:
                st.error(f"Pipeline error: {e}")
                st.exception(e)  # Добавьте эту строку чтобы увидеть полный traceback
                # fallback_pipeline()  # Закомментируйте эту строку временно
        else:
            fallback_pipeline()
    
    elif page == "⚙️ Settings":
        settings_page()

if __name__ == "__main__":
    main()