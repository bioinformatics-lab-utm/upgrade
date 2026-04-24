"""
Pipeline run domain model.

Represents an execution of a bioinformatics pipeline on a sample.
"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class PipelineRunBase(BaseModel):
    """Base pipeline run attributes."""
    
    sample_id: int = Field(..., description="Foreign key to samples table")
    pipeline_name: str = Field(..., max_length=150, description="Name of the pipeline")
    pipeline_version: Optional[str] = Field(None, max_length=50)
    software_name: Optional[str] = Field(None, max_length=150, description="Flye+Medaka, Kraken2+Bracken, Abricate")
    software_version: Optional[str] = Field(None, max_length=50)
    
    # Analysis parameters (stored as JSONB in DB, handled as Dict in code)
    parameters: Optional[Dict[str, Any]] = Field(None, description="Pipeline parameters")
    reference_database: Optional[str] = Field(None, max_length=150, description="CARD, VFDB, RefSeq")
    reference_db_version: Optional[str] = Field(None, max_length=100)
    
    # Computational resources
    cpu_cores: Optional[int] = None
    memory_gb: Optional[int] = None
    runtime_minutes: Optional[int] = None
    
    # Results paths (MinIO)
    results_path: Optional[str] = Field(None, max_length=255)
    log_file_path: Optional[str] = Field(None, max_length=255)
    
    # Status
    status: str = Field(default="queued", description="queued, running, completed, failed, cancelled")
    exit_code: Optional[int] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PipelineRunCreate(PipelineRunBase):
    """Schema for creating a new pipeline run."""
    
    sample_name: Optional[str] = Field(None, description="Sample name for tracking")
    job_id: Optional[str] = Field(None, description="Background job identifier")


class PipelineRunUpdate(BaseModel):
    """Schema for updating an existing pipeline run. All fields optional."""
    
    # Base fields
    pipeline_name: Optional[str] = None
    pipeline_version: Optional[str] = None
    software_name: Optional[str] = None
    software_version: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    
    # Paths
    bronze_path: Optional[str] = None
    silver_path: Optional[str] = None
    results_path: Optional[str] = None
    log_file_path: Optional[str] = None
    
    # Job tracking
    job_id: Optional[str] = None
    
    status: Optional[str] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    runtime_minutes: Optional[int] = None
    results_path: Optional[str] = None
    log_file_path: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    bronze_path: Optional[str] = None
    silver_path: Optional[str] = None
    job_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PipelineRun(PipelineRunBase):
    """Complete pipeline run model with database fields."""
    
    pipeline_id: int = Field(..., description="Primary key")
    sequencing_run_id: Optional[int] = Field(None, description="Foreign key to sequencing_runs")
    sample_name: Optional[str] = Field(None, description="Sample name for easy reference")
    job_id: Optional[str] = Field(None, description="Background job identifier")
    
    # Timing
    queued_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(from_attributes=True)
