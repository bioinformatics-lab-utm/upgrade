# config/settings.py
import os
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
STATIC_DIR = PROJECT_ROOT / "static"

# Streamlit page configuration
PAGE_CONFIG = {
    'page_title': 'UPGRADE - Environmental Genomic Surveillance',
    'page_icon': '🧬',
    'layout': 'wide',
    'initial_sidebar_state': 'expanded'
}

# Database configuration
DATABASE_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'postgres'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'upgrade_db'),
    'user': os.getenv('POSTGRES_USER', 'upgrade'),
    'password': os.getenv('POSTGRES_PASSWORD', 'upgrade123')
}

# Airflow configuration
AIRFLOW_CONFIG = {
    'base_url': os.getenv('AIRFLOW_API_URL', 'http://airflow-webserver:8080/api/v1'),
    'username': os.getenv('_AIRFLOW_WWW_USER_USERNAME', 'admin'),
    'password': os.getenv('_AIRFLOW_WWW_USER_PASSWORD', 'admin123'),
    'timeout': 30
}

# MinIO configuration
MINIO_CONFIG = {
    'endpoint': os.getenv('MINIO_ENDPOINT', 'minio:9000'),
    'access_key': os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
    'secret_key': os.getenv('MINIO_SECRET_KEY', 'minioadmin'),
    'secure': False,
    'default_bucket': 'genomic-data'
}

# Theme configuration
THEME_CONFIG = {
    'primary_color': '#007bff',
    'secondary_color': '#6c757d',
    'success_color': '#28a745',
    'warning_color': '#ffc107',
    'error_color': '#dc3545',
    'info_color': '#17a2b8'
}

# File validation settings
FILE_VALIDATION = {
    'allowed_extensions': ['.fastq', '.fastq.gz', '.fq', '.fq.gz', '.fasta', '.fa', '.fastq.bz2'],
    'max_size_mb': 10000,
    'min_size_bytes': 1024
}

# Cache settings
CACHE_CONFIG = {
    'weather_ttl': 300,  # 5 minutes
    'locations_ttl': 300,  # 5 minutes
    'pipeline_ttl': 60  # 1 minute
}