"""
Base repository class providing common database operations.
"""
from typing import Generic, TypeVar, Optional, List, Dict, Any
from abc import ABC, abstractmethod
import asyncpg


T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """
    Base repository providing common CRUD operations.
    
    Subclasses must implement table_name property.
    """
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize repository with database connection pool.
        
        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool
    
    @property
    @abstractmethod
    def table_name(self) -> str:
        """Return the name of the database table."""
        pass
    
    @property
    @abstractmethod
    def primary_key(self) -> str:
        """Return the name of the primary key column."""
        pass
    
    async def find_by_id(self, id_value: int) -> Optional[Dict[str, Any]]:
        """
        Find a record by its primary key.
        
        Args:
            id_value: The primary key value
            
        Returns:
            Dictionary with record data or None if not found
        """
        query = f"SELECT * FROM {self.table_name} WHERE {self.primary_key} = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, id_value)
            return dict(row) if row else None
    
    async def find_all(
        self, 
        limit: int = 100, 
        offset: int = 0,
        order_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find all records with pagination.
        
        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip
            order_by: Column name to order by (default: primary key DESC)
            
        Returns:
            List of dictionaries with record data
        """
        order_clause = order_by or f"{self.primary_key} DESC"
        query = f"""
            SELECT * FROM {self.table_name}
            ORDER BY {order_clause}
            LIMIT $1 OFFSET $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit, offset)
            return [dict(row) for row in rows]
    
    async def count(self, where_clause: str = "", params: tuple = ()) -> int:
        """
        Count records matching criteria.
        
        Args:
            where_clause: SQL WHERE clause (without WHERE keyword)
            params: Query parameters
            
        Returns:
            Number of matching records
        """
        where = f"WHERE {where_clause}" if where_clause else ""
        query = f"SELECT COUNT(*) FROM {self.table_name} {where}"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *params)
    
    async def exists(self, where_clause: str, params: tuple) -> bool:
        """
        Check if a record exists matching criteria.
        
        Args:
            where_clause: SQL WHERE clause (without WHERE keyword)
            params: Query parameters
            
        Returns:
            True if at least one record exists
        """
        count = await self.count(where_clause, params)
        return count > 0
    
    async def delete(self, id_value: int) -> bool:
        """
        Delete a record by its primary key.
        
        Args:
            id_value: The primary key value
            
        Returns:
            True if record was deleted, False if not found
        """
        query = f"DELETE FROM {self.table_name} WHERE {self.primary_key} = $1 RETURNING {self.primary_key}"
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, id_value)
            return result is not None

    async def execute_in_transaction(self, queries: list) -> bool:
        """
        Execute multiple queries in a single transaction.
        
        Args:
            queries: List of (query_string, params_tuple) tuples
            
        Returns:
            True if all queries succeeded, False on rollback
            
        Raises:
            Exception: If transaction fails, automatically rolls back
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for query, params in queries:
                    await conn.execute(query, *params)
                return True
    
    def transaction(self):
        """
        Return a transaction context manager for complex operations.
        
        Usage:
            async with repo.transaction() as conn:
                await conn.execute(...)
                await conn.execute(...)
        """
        return TransactionContext(self.pool)


class TransactionContext:
    """Context manager for database transactions"""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.conn = None
        self.transaction = None
    
    async def __aenter__(self):
        self.conn = await self.pool.acquire()
        try:
            self.transaction = self.conn.transaction()
            await self.transaction.start()
        except Exception:
            await self.pool.release(self.conn)
            self.conn = None
            raise
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                await self.transaction.commit()
            else:
                await self.transaction.rollback()
        finally:
            if self.conn is not None:
                await self.pool.release(self.conn)
