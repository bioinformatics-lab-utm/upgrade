"""
Standardized error handling for API routes.

Provides consistent error responses with proper HTTP status codes,
error codes, and structured messages for frontend consumption.
"""
import logging
import traceback
from functools import wraps
from datetime import datetime
from typing import Optional, Dict, Any

from sanic.response import json as sanic_json
from sanic.exceptions import SanicException

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base API error with HTTP status code and error code"""
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'error': True,
            'error_code': self.error_code,
            'message': self.message,
            'details': self.details,
            'timestamp': datetime.now().isoformat()
        }


class ValidationError(APIError):
    """Input validation error (400)"""
    def __init__(self, message: str, field: str = None, details: dict = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details={'field': field, **(details or {})}
        )


class NotFoundError(APIError):
    """Resource not found (404)"""
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} not found",
            status_code=404,
            error_code="NOT_FOUND",
            details={'resource': resource, 'identifier': str(identifier)}
        )


class DuplicateError(APIError):
    """Duplicate resource error (409)"""
    def __init__(self, resource: str, identifier: Any, existing_id: Any = None):
        super().__init__(
            message=f"{resource} already exists",
            status_code=409,
            error_code="DUPLICATE",
            details={
                'resource': resource,
                'identifier': str(identifier),
                'existing_id': str(existing_id) if existing_id else None
            }
        )


class PipelineConflictError(APIError):
    """Pipeline already running for sample (409)"""
    def __init__(self, sample_id: int, existing_pipeline_id: int, status: str):
        super().__init__(
            message=f"Active pipeline already exists for this sample",
            status_code=409,
            error_code="PIPELINE_CONFLICT",
            details={
                'sample_id': sample_id,
                'existing_pipeline_id': existing_pipeline_id,
                'existing_status': status
            }
        )


class StorageError(APIError):
    """Storage (MinIO) error (502)"""
    def __init__(self, message: str, bucket: str = None, key: str = None):
        super().__init__(
            message=message,
            status_code=502,
            error_code="STORAGE_ERROR",
            details={'bucket': bucket, 'key': key}
        )


class DatabaseError(APIError):
    """Database error (503)"""
    def __init__(self, message: str = "Database operation failed"):
        super().__init__(
            message=message,
            status_code=503,
            error_code="DATABASE_ERROR"
        )


class PipelineExecutionError(APIError):
    """Pipeline execution failed (500)"""
    def __init__(self, pipeline_id: int, message: str, exit_code: int = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="PIPELINE_EXECUTION_ERROR",
            details={
                'pipeline_id': pipeline_id,
                'exit_code': exit_code
            }
        )


def error_response(error: APIError):
    """Convert APIError to Sanic response"""
    return sanic_json(error.to_dict(), status=error.status_code)


def handle_errors(func):
    """
    Decorator for standardized error handling in route handlers.
    
    Usage:
        @blueprint.route('/endpoint')
        @handle_errors
        async def my_handler(request):
            ...
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except APIError as e:
            logger.warning(f"[API_ERROR] {e.error_code}: {e.message}", extra={
                'error_code': e.error_code,
                'status_code': e.status_code,
                'details': e.details
            })
            return error_response(e)
        except ValueError as e:
            # Convert ValueError to ValidationError
            api_error = ValidationError(str(e))
            logger.warning(f"[VALIDATION] {e}")
            return error_response(api_error)
        except SanicException:
            # Let Sanic handle its own exceptions
            raise
        except Exception as e:
            # Unexpected error - log full traceback
            logger.error(f"[UNHANDLED] {type(e).__name__}: {e}", exc_info=True)
            api_error = APIError(
                message="An unexpected error occurred. Please try again later.",
                status_code=500,
                error_code="INTERNAL_ERROR",
                details={'type': type(e).__name__}
            )
            return error_response(api_error)
    
    return wrapper


def validate_required_fields(data: dict, fields: list) -> None:
    """
    Validate that required fields are present and non-empty.
    
    Args:
        data: Request data dictionary
        fields: List of required field names
        
    Raises:
        ValidationError: If any required field is missing or empty
    """
    missing = []
    for field in fields:
        if field not in data or data[field] is None:
            missing.append(field)
        elif isinstance(data[field], str) and not data[field].strip():
            missing.append(field)
    
    if missing:
        raise ValidationError(
            message=f"Missing required fields: {', '.join(missing)}",
            details={'missing_fields': missing}
        )


def validate_positive_int(value: Any, field_name: str) -> int:
    """
    Validate and convert value to positive integer.
    
    Args:
        value: Value to validate
        field_name: Field name for error message
        
    Returns:
        Validated positive integer
        
    Raises:
        ValidationError: If value is not a valid positive integer
    """
    try:
        int_value = int(value)
        if int_value <= 0:
            raise ValidationError(
                message=f"{field_name} must be a positive integer",
                field=field_name
            )
        return int_value
    except (ValueError, TypeError):
        raise ValidationError(
            message=f"{field_name} must be a valid integer",
            field=field_name
        )
