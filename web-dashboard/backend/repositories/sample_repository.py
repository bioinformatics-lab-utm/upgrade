"""
Sample repository for database operations.
"""
from typing import Optional, List, Dict, Any
from datetime import date
import asyncpg

from .base_repository import BaseRepository
from models.sample import Sample, SampleCreate, SampleUpdate


class SampleRepository(BaseRepository[Sample]):
    """Repository for sample-related database operations."""
    
    @property
    def table_name(self) -> str:
        return "samples"
    
    @property
    def primary_key(self) -> str:
        return "sample_id"
    
    async def create(self, sample_data: SampleCreate) -> int:
        """
        Create a new sample record.
        
        Args:
            sample_data: Sample creation data
            
        Returns:
            ID of the created sample
        """
        query = """
            INSERT INTO samples (
                sample_code, collection_date, collection_time, location_id,
                sample_type, sample_volume_ml, collection_method,
                storage_conditions, transport_conditions,
                sequencing_platform, sequencing_kit, flowcell_type,
                read_length_avg, sequencing_depth, coverage, quality_score,
                status, processing_priority, expected_results_date,
                project_id, batch_id, barcode, notes, metadata
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24
            )
            RETURNING sample_id
        """
        
        # Serialize metadata to JSON string if present
        import json as json_module
        metadata_json = json_module.dumps(sample_data.metadata) if sample_data.metadata else None
        
        async with self.pool.acquire() as conn:
            sample_id = await conn.fetchval(
                query,
                sample_data.sample_code,
                sample_data.collection_date,
                sample_data.collection_time,
                sample_data.location_id,
                sample_data.sample_type,
                sample_data.sample_volume_ml,
                sample_data.collection_method,
                sample_data.storage_conditions,
                sample_data.transport_conditions,
                sample_data.sequencing_platform,
                sample_data.sequencing_kit,
                sample_data.flowcell_type,
                sample_data.read_length_avg,
                sample_data.sequencing_depth,
                sample_data.coverage,
                sample_data.quality_score,
                sample_data.status,
                sample_data.processing_priority,
                sample_data.expected_results_date,
                sample_data.project_id,
                sample_data.batch_id,
                sample_data.barcode,
                sample_data.notes,
                metadata_json
            )
            return sample_id
    
    async def find_by_code(self, sample_code: str) -> Optional[Dict[str, Any]]:
        """
        Find a sample by its unique code.
        
        Args:
            sample_code: The sample code
            
        Returns:
            Dictionary with sample data or None
        """
        query = "SELECT * FROM samples WHERE sample_code = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, sample_code)
            return dict(row) if row else None
    
    async def update(self, sample_id: int, update_data: SampleUpdate) -> bool:
        """
        Update an existing sample.
        
        Args:
            sample_id: ID of sample to update
            update_data: Fields to update
            
        Returns:
            True if sample was updated, False if not found
        """
        import json as json_module
        
        # Build dynamic UPDATE query with only provided fields
        update_fields = []
        values = []
        param_idx = 1
        
        for field, value in update_data.model_dump(exclude_unset=True).items():
            # Serialize metadata to JSON string
            if field == 'metadata' and value is not None:
                value = json_module.dumps(value)
            
            update_fields.append(f"{field} = ${param_idx}")
            values.append(value)
            param_idx += 1
        
        if not update_fields:
            return False  # Nothing to update
        
        values.append(sample_id)
        query = f"""
            UPDATE samples
            SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
            WHERE sample_id = ${param_idx}
            RETURNING sample_id
        """
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, *values)
            return result is not None
    
    async def find_by_status(
        self, 
        status: str, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Find samples by status with pagination.
        
        Args:
            status: Sample status to filter by
            limit: Maximum number of records
            offset: Number of records to skip
            
        Returns:
            List of sample dictionaries
        """
        query = """
            SELECT * FROM samples
            WHERE status = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, status, limit, offset)
            return [dict(row) for row in rows]
    
    async def find_by_date_range(
        self,
        start_date: date,
        end_date: date,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Find samples collected within a date range.
        
        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            limit: Maximum number of records
            offset: Number of records to skip
            
        Returns:
            List of sample dictionaries
        """
        query = """
            SELECT * FROM samples
            WHERE collection_date BETWEEN $1 AND $2
            ORDER BY collection_date DESC
            LIMIT $3 OFFSET $4
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, start_date, end_date, limit, offset)
            return [dict(row) for row in rows]
