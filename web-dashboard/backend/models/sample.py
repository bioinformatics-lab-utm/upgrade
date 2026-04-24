"""
Sample domain model.

Represents a biological sample collected for genomic surveillance.
"""
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class SampleBase(BaseModel):
    """Base sample attributes shared across operations."""
    
    sample_code: str = Field(..., max_length=100, description="Unique sample identifier")
    collection_date: date = Field(..., description="Date when sample was collected")
    collection_time: Optional[time] = Field(None, description="Time when sample was collected")
    location_id: Optional[int] = Field(None, description="Foreign key to locations table")
    
    # Sample characteristics
    sample_type: Optional[str] = Field(None, max_length=100, description="surface_swab, air_sample, water_sample, soil_sample")
    sample_volume_ml: Optional[Decimal] = Field(None, description="Volume of sample in milliliters")
    collection_method: Optional[str] = Field(None, max_length=150)
    storage_conditions: Optional[str] = Field(None, max_length=100)
    transport_conditions: Optional[str] = Field(None, max_length=100)
    
    # Sequencing information
    sequencing_platform: Optional[str] = Field(None, max_length=150, description="MinION, GridION, PromethION")
    sequencing_kit: Optional[str] = Field(None, max_length=100, description="SQK-LSK109, SQK-RBK004, etc.")
    flowcell_type: Optional[str] = Field(None, max_length=50, description="R9.4.1, R10.4.1")
    read_length_avg: Optional[int] = Field(None, description="Average read length")
    sequencing_depth: Optional[Decimal] = Field(None)
    coverage: Optional[Decimal] = Field(None)
    quality_score: Optional[Decimal] = Field(None, description="Overall quality score")
    
    # Processing status
    status: str = Field(default="collected", description="collected, processing, sequenced, analyzed, archived")
    processing_priority: int = Field(default=1, ge=1, le=5, description="1=highest, 5=lowest")
    expected_results_date: Optional[date] = None
    
    # Project tracking
    project_id: Optional[str] = Field(None, max_length=100)
    batch_id: Optional[str] = Field(None, max_length=100)
    barcode: Optional[str] = Field(None, max_length=50)
    
    notes: Optional[str] = None
    metadata: Optional[dict] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class SampleCreate(SampleBase):
    """Schema for creating a new sample."""
    pass


class SampleUpdate(BaseModel):
    """Schema for updating an existing sample. All fields optional."""
    
    collection_date: Optional[date] = None
    collection_time: Optional[time] = None
    location_id: Optional[int] = None
    sample_type: Optional[str] = None
    sample_volume_ml: Optional[Decimal] = None
    collection_method: Optional[str] = None
    storage_conditions: Optional[str] = None
    transport_conditions: Optional[str] = None
    sequencing_platform: Optional[str] = None
    sequencing_kit: Optional[str] = None
    flowcell_type: Optional[str] = None
    read_length_avg: Optional[int] = None
    sequencing_depth: Optional[Decimal] = None
    coverage: Optional[Decimal] = None
    quality_score: Optional[Decimal] = None
    status: Optional[str] = None
    processing_priority: Optional[int] = Field(None, ge=1, le=5)
    expected_results_date: Optional[date] = None
    project_id: Optional[str] = None
    batch_id: Optional[str] = None
    barcode: Optional[str] = None
    notes: Optional[str] = None
    metadata: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class Sample(SampleBase):
    """Complete sample model with database fields."""
    
    sample_id: int = Field(..., description="Primary key")
    campaign_id: Optional[int] = Field(None, description="Foreign key to sampling_campaigns")
    collector_id: Optional[int] = Field(None, description="Foreign key to researchers")
    pathogen_id: Optional[int] = Field(None, description="Foreign key to pathogen_reference")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(from_attributes=True)
