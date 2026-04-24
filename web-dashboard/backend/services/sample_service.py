"""
Sample service implementing business logic for sample management.
"""
from typing import Optional, List, Dict, Any
from datetime import date, datetime
import logging
import re

from models.sample import Sample, SampleCreate, SampleUpdate
from repositories.sample_repository import SampleRepository

logger = logging.getLogger(__name__)


class SampleService:
    """
    Service for sample-related business logic.
    
    Handles validation, business rules, and orchestrates
    operations across repositories.
    """
    
    def __init__(self, sample_repo: SampleRepository):
        """
        Initialize service with repository.
        
        Args:
            sample_repo: Sample repository instance
        """
        self.sample_repo = sample_repo
    
    async def create_sample(
        self,
        sample_data: SampleCreate,
        validate_code: bool = True
    ) -> int:
        """
        Create a new sample with validation.
        
        Args:
            sample_data: Sample creation data
            validate_code: Whether to validate sample code format
            
        Returns:
            ID of created sample
            
        Raises:
            ValueError: If validation fails
        """
        # Validate sample code format
        if validate_code and not self._is_valid_sample_code(sample_data.sample_code):
            raise ValueError(
                "Invalid sample_code format. Use only alphanumeric, "
                "underscore, and hyphen (max 100 chars)"
            )
        
        # Check for duplicate sample code
        existing = await self.sample_repo.find_by_code(sample_data.sample_code)
        if existing:
            raise ValueError(f"Sample with code '{sample_data.sample_code}' already exists")
        
        # Validate sample type
        if sample_data.sample_type:
            valid_types = ['nanopore', 'illumina', 'pacbio', 'surface_swab', 
                          'air_sample', 'water_sample', 'soil_sample']
            if sample_data.sample_type not in valid_types:
                logger.warning(f"Unusual sample_type: {sample_data.sample_type}")
        
        # Create sample
        sample_id = await self.sample_repo.create(sample_data)
        logger.info(f"Created sample {sample_id} with code {sample_data.sample_code}")
        
        return sample_id
    
    async def get_sample(self, sample_id: int) -> Optional[Sample]:
        """
        Get sample by ID.
        
        Args:
            sample_id: Sample ID
            
        Returns:
            Sample model or None if not found
        """
        data = await self.sample_repo.find_by_id(sample_id)
        return Sample(**data) if data else None
    
    async def get_sample_by_code(self, sample_code: str) -> Optional[Sample]:
        """
        Get sample by unique code.
        
        Args:
            sample_code: Sample code
            
        Returns:
            Sample model or None if not found
        """
        data = await self.sample_repo.find_by_code(sample_code)
        return Sample(**data) if data else None
    
    async def update_sample(
        self,
        sample_id: int,
        update_data: SampleUpdate
    ) -> bool:
        """
        Update an existing sample.
        
        Args:
            sample_id: ID of sample to update
            update_data: Fields to update
            
        Returns:
            True if updated, False if not found
            
        Raises:
            ValueError: If validation fails
        """
        # Check sample exists
        existing = await self.sample_repo.find_by_id(sample_id)
        if not existing:
            return False
        
        # Validate status transition if status is being updated
        if update_data.status:
            valid_statuses = ['collected', 'processing', 'sequenced', 'analyzed', 'archived']
            if update_data.status not in valid_statuses:
                raise ValueError(f"Invalid status. Must be one of: {valid_statuses}")
        
        return await self.sample_repo.update(sample_id, update_data)
    
    async def delete_sample(self, sample_id: int) -> bool:
        """
        Delete a sample.
        
        Args:
            sample_id: Sample ID
            
        Returns:
            True if deleted, False if not found
        """
        return await self.sample_repo.delete(sample_id)
    
    async def list_samples(
        self,
        status: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Sample]:
        """
        List samples with optional filters.
        
        Args:
            status: Filter by status
            start_date: Filter by collection date range (start)
            end_date: Filter by collection date range (end)
            limit: Maximum number of records
            offset: Number of records to skip
            
        Returns:
            List of Sample models
        """
        if status:
            rows = await self.sample_repo.find_by_status(status, limit, offset)
        elif start_date and end_date:
            rows = await self.sample_repo.find_by_date_range(
                start_date, end_date, limit, offset
            )
        else:
            rows = await self.sample_repo.find_all(limit, offset)
        
        return [Sample(**row) for row in rows]
    
    async def count_samples(self, status: Optional[str] = None) -> int:
        """
        Count samples, optionally filtered by status.
        
        Args:
            status: Optional status filter
            
        Returns:
            Number of matching samples
        """
        if status:
            return await self.sample_repo.count("status = $1", (status,))
        return await self.sample_repo.count()
    
    def _is_valid_sample_code(self, sample_code: str) -> bool:
        """
        Validate sample code format.
        
        Args:
            sample_code: Code to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not sample_code or len(sample_code) > 100:
            return False
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', sample_code))
