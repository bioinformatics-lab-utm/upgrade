"""
User repository for database operations.
"""
from typing import Optional, Dict, Any
import asyncpg

from .base_repository import BaseRepository
from models.user import User, UserCreate, UserUpdate


class UserRepository(BaseRepository[User]):
    """Repository for user-related database operations."""
    
    @property
    def table_name(self) -> str:
        return "users"
    
    @property
    def primary_key(self) -> str:
        return "user_id"
    
    async def create(self, user_data: UserCreate, password_hash: str) -> int:
        """
        Create a new user record.

        Args:
            user_data: User creation data
            password_hash: Hashed password

        Returns:
            ID of the created user
        """
        # Split full_name into first_name and last_name
        name_parts = (user_data.full_name or '').split(maxsplit=1)
        first_name = name_parts[0] if name_parts else None
        last_name = name_parts[1] if len(name_parts) > 1 else None

        query = """
            INSERT INTO users (
                username, email, password_hash, first_name, last_name, user_type, is_active
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING user_id
        """

        async with self.pool.acquire() as conn:
            user_id = await conn.fetchval(
                query,
                user_data.username,
                user_data.email,
                password_hash,
                first_name,
                last_name,
                user_data.user_type,
                user_data.is_active
            )
            return user_id
    
    async def find_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Find a user by username.
        
        Args:
            username: The username
            
        Returns:
            Dictionary with user data or None
        """
        query = "SELECT * FROM users WHERE username = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, username)
            return dict(row) if row else None
    
    async def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Find a user by email.
        
        Args:
            email: The email address
            
        Returns:
            Dictionary with user data or None
        """
        query = "SELECT * FROM users WHERE email = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, email)
            return dict(row) if row else None
    
    async def update(self, user_id: int, update_data: UserUpdate) -> bool:
        """
        Update an existing user.
        
        Args:
            user_id: ID of user to update
            update_data: Fields to update
            
        Returns:
            True if user was updated, False if not found
        """
        update_fields = []
        values = []
        param_idx = 1
        
        for field, value in update_data.model_dump(exclude_unset=True).items():
            if field == "password":
                continue  # Password handled separately via update_password
            update_fields.append(f"{field} = ${param_idx}")
            values.append(value)
            param_idx += 1
        
        if not update_fields:
            return False
        
        values.append(user_id)
        query = f"""
            UPDATE users
            SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ${param_idx}
            RETURNING user_id
        """
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, *values)
            return result is not None
    
    async def update_password(self, user_id: int, password_hash: str) -> bool:
        """
        Update user password.
        
        Args:
            user_id: ID of user
            password_hash: New hashed password
            
        Returns:
            True if updated successfully
        """
        query = """
            UPDATE users
            SET password_hash = $1, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $2
            RETURNING user_id
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, password_hash, user_id)
            return result is not None
    
    async def update_last_login(self, user_id: int) -> bool:
        """
        Update user's last login timestamp.
        
        Args:
            user_id: ID of user
            
        Returns:
            True if updated successfully
        """
        query = """
            UPDATE users
            SET last_login = CURRENT_TIMESTAMP
            WHERE user_id = $1
            RETURNING user_id
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, user_id)
            return result is not None
