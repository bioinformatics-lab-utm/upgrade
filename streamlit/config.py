import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Database
    POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
    POSTGRES_DB = os.getenv('POSTGRES_DB', 'upgrade_db')
    POSTGRES_USER = os.getenv('POSTGRES_USER', 'upgrade')
    POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'upgrade123')
    
    # Airflow
    AIRFLOW_API_URL = os.getenv('AIRFLOW_API_URL', 'http://localhost:8081/api/v1')
    AIRFLOW_USERNAME = os.getenv('AIRFLOW_USERNAME', 'admin')
    AIRFLOW_PASSWORD = os.getenv('AIRFLOW_PASSWORD', 'admin123')
    
    # MinIO
    MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
    MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
    MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin')