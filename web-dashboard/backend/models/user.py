"""
User domain model.

Represents a user account for authentication and authorization.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UserBase(BaseModel):
    """Base user attributes."""

    username: str = Field(..., min_length=3, max_length=100, description="Unique username")
    email: EmailStr = Field(..., description="User email address")
    full_name: Optional[str] = Field(None, max_length=200, description="Display name (split into first_name/last_name in DB)")
    user_type: str = Field(default="researcher", description="lab_technician, public_health_official, researcher, admin")
    is_active: bool = Field(default=True)

    model_config = ConfigDict(from_attributes=True)


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str = Field(..., min_length=8, description="Plain text password (will be hashed)")


class UserUpdate(BaseModel):
    """Schema for updating an existing user. All fields optional."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    user_type: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, description="New password (will be hashed)")

    model_config = ConfigDict(from_attributes=True)


class User(UserBase):
    """Complete user model with database fields."""

    user_id: int = Field(..., description="Primary key")
    password_hash: str = Field(..., description="Bcrypt hashed password")
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    institution_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_login: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    """Schema for user login."""
    
    username: str
    password: str

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """JWT token response."""
    
    access_token: str
    token_type: str = "bearer"

    model_config = ConfigDict(from_attributes=True)
