"""
Tests for Error Handling utilities
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime


class TestAPIError:
    """Tests for APIError base class"""

    def test_api_error_creation(self):
        """Test creating APIError"""
        from utils.error_handling import APIError
        
        error = APIError(
            message="Something went wrong",
            status_code=500,
            error_code="INTERNAL_ERROR"
        )
        
        assert error.message == "Something went wrong"
        assert error.status_code == 500
        assert error.error_code == "INTERNAL_ERROR"

    def test_api_error_to_dict(self):
        """Test APIError to_dict method"""
        from utils.error_handling import APIError
        
        error = APIError(
            message="Test error",
            status_code=400,
            error_code="TEST_ERROR",
            details={"field": "email"}
        )
        
        result = error.to_dict()
        
        assert result["error"] is True
        assert result["error_code"] == "TEST_ERROR"
        assert result["message"] == "Test error"
        assert result["details"]["field"] == "email"
        assert "timestamp" in result

    def test_api_error_default_values(self):
        """Test APIError default values"""
        from utils.error_handling import APIError
        
        error = APIError(message="Error")
        
        assert error.status_code == 500
        assert error.error_code == "INTERNAL_ERROR"
        assert error.details == {}


class TestValidationError:
    """Tests for ValidationError"""

    def test_validation_error_creation(self):
        """Test creating ValidationError"""
        from utils.error_handling import ValidationError
        
        error = ValidationError(
            message="Invalid email format",
            field="email"
        )
        
        assert error.status_code == 400
        assert error.error_code == "VALIDATION_ERROR"
        assert error.details["field"] == "email"

    def test_validation_error_with_details(self):
        """Test ValidationError with additional details"""
        from utils.error_handling import ValidationError
        
        error = ValidationError(
            message="Invalid input",
            field="password",
            details={"min_length": 8}
        )
        
        assert error.details["field"] == "password"
        assert error.details["min_length"] == 8


class TestNotFoundError:
    """Tests for NotFoundError"""

    def test_not_found_error_creation(self):
        """Test creating NotFoundError"""
        from utils.error_handling import NotFoundError
        
        error = NotFoundError(resource="Sample", identifier=123)
        
        assert error.status_code == 404
        assert error.error_code == "NOT_FOUND"
        assert "Sample not found" in error.message
        assert error.details["resource"] == "Sample"
        assert error.details["identifier"] == "123"


class TestDuplicateError:
    """Tests for DuplicateError"""

    def test_duplicate_error_creation(self):
        """Test creating DuplicateError"""
        from utils.error_handling import DuplicateError
        
        error = DuplicateError(
            resource="User",
            identifier="test@example.com",
            existing_id=42
        )
        
        assert error.status_code == 409
        assert error.error_code == "DUPLICATE"
        assert "already exists" in error.message
        assert error.details["existing_id"] == "42"

    def test_duplicate_error_without_existing_id(self):
        """Test DuplicateError without existing_id"""
        from utils.error_handling import DuplicateError
        
        error = DuplicateError(resource="Sample", identifier="S001")
        
        assert error.details["existing_id"] is None


class TestPipelineConflictError:
    """Tests for PipelineConflictError"""

    def test_pipeline_conflict_error_creation(self):
        """Test creating PipelineConflictError"""
        from utils.error_handling import PipelineConflictError
        
        error = PipelineConflictError(
            sample_id=1,
            existing_pipeline_id=42,
            status="running"
        )
        
        assert error.status_code == 409
        assert error.error_code == "PIPELINE_CONFLICT"
        assert error.details["sample_id"] == 1
        assert error.details["existing_pipeline_id"] == 42
        assert error.details["existing_status"] == "running"


class TestStorageError:
    """Tests for StorageError"""

    def test_storage_error_creation(self):
        """Test creating StorageError"""
        from utils.error_handling import StorageError
        
        error = StorageError(
            message="Upload failed",
            bucket="samples",
            key="file.fastq"
        )
        
        assert error.status_code == 502
        assert error.error_code == "STORAGE_ERROR"
        assert error.details["bucket"] == "samples"
        assert error.details["key"] == "file.fastq"


class TestDatabaseError:
    """Tests for DatabaseError"""

    def test_database_error_creation(self):
        """Test creating DatabaseError"""
        from utils.error_handling import DatabaseError
        
        error = DatabaseError(message="Connection failed")
        
        assert error.status_code == 503
        assert error.error_code == "DATABASE_ERROR"
        assert error.message == "Connection failed"

    def test_database_error_default_message(self):
        """Test DatabaseError default message"""
        from utils.error_handling import DatabaseError
        
        error = DatabaseError()
        
        assert "Database operation failed" in error.message


class TestPipelineExecutionError:
    """Tests for PipelineExecutionError"""

    def test_pipeline_execution_error_creation(self):
        """Test creating PipelineExecutionError"""
        from utils.error_handling import PipelineExecutionError
        
        error = PipelineExecutionError(
            pipeline_id=1,
            message="Nextflow failed",
            exit_code=1
        )
        
        assert error.status_code == 500
        assert error.error_code == "PIPELINE_EXECUTION_ERROR"
        assert error.details["pipeline_id"] == 1
        assert error.details["exit_code"] == 1


class TestErrorResponse:
    """Tests for error_response function"""

    def test_error_response(self):
        """Test error_response function"""
        from utils.error_handling import APIError, error_response
        
        error = APIError(message="Test", status_code=400, error_code="TEST")
        response = error_response(error)
        
        assert response.status == 400


class TestHandleErrorsDecorator:
    """Tests for handle_errors decorator"""

    @pytest.mark.asyncio
    async def test_handle_errors_passes_success(self):
        """Test decorator passes successful calls"""
        from utils.error_handling import handle_errors
        
        @handle_errors
        async def success_handler(request):
            return {"success": True}
        
        mock_request = Mock()
        result = await success_handler(mock_request)
        
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_handle_errors_catches_api_error(self):
        """Test decorator catches APIError"""
        from utils.error_handling import handle_errors, ValidationError
        
        @handle_errors
        async def failing_handler(request):
            raise ValidationError("Invalid input", field="email")
        
        mock_request = Mock()
        result = await failing_handler(mock_request)
        
        assert result.status == 400

    @pytest.mark.asyncio
    async def test_handle_errors_catches_value_error(self):
        """Test decorator converts ValueError to ValidationError"""
        from utils.error_handling import handle_errors
        
        @handle_errors
        async def failing_handler(request):
            raise ValueError("Invalid value")
        
        mock_request = Mock()
        result = await failing_handler(mock_request)
        
        assert result.status == 400

    @pytest.mark.asyncio
    async def test_handle_errors_catches_unexpected_error(self):
        """Test decorator catches unexpected errors"""
        from utils.error_handling import handle_errors
        
        @handle_errors
        async def failing_handler(request):
            raise RuntimeError("Unexpected")
        
        mock_request = Mock()
        result = await failing_handler(mock_request)
        
        assert result.status == 500


class TestValidateRequiredFields:
    """Tests for validate_required_fields function"""

    def test_validate_required_fields_pass(self):
        """Test validation passes with all fields"""
        from utils.error_handling import validate_required_fields
        
        data = {"name": "Test", "email": "test@example.com"}
        # Should not raise
        validate_required_fields(data, ["name", "email"])

    def test_validate_required_fields_missing(self):
        """Test validation fails with missing fields"""
        from utils.error_handling import validate_required_fields, ValidationError
        
        data = {"name": "Test"}
        
        with pytest.raises(ValidationError) as exc_info:
            validate_required_fields(data, ["name", "email"])
        
        assert "email" in str(exc_info.value.details)

    def test_validate_required_fields_empty_string(self):
        """Test validation fails with empty string"""
        from utils.error_handling import validate_required_fields, ValidationError
        
        data = {"name": "  ", "email": "test@example.com"}
        
        with pytest.raises(ValidationError) as exc_info:
            validate_required_fields(data, ["name", "email"])
        
        assert "name" in str(exc_info.value.details)

    def test_validate_required_fields_none_value(self):
        """Test validation fails with None value"""
        from utils.error_handling import validate_required_fields, ValidationError
        
        data = {"name": None, "email": "test@example.com"}
        
        with pytest.raises(ValidationError):
            validate_required_fields(data, ["name"])


class TestValidatePositiveInt:
    """Tests for validate_positive_int function"""

    def test_validate_positive_int_valid(self):
        """Test validation passes with positive int"""
        from utils.error_handling import validate_positive_int
        
        result = validate_positive_int(42, "count")
        assert result == 42

    def test_validate_positive_int_string(self):
        """Test validation converts string to int"""
        from utils.error_handling import validate_positive_int
        
        result = validate_positive_int("42", "count")
        assert result == 42

    def test_validate_positive_int_zero(self):
        """Test validation fails for zero"""
        from utils.error_handling import validate_positive_int, ValidationError
        
        with pytest.raises(ValidationError):
            validate_positive_int(0, "count")

    def test_validate_positive_int_negative(self):
        """Test validation fails for negative"""
        from utils.error_handling import validate_positive_int, ValidationError
        
        with pytest.raises(ValidationError):
            validate_positive_int(-5, "count")

    def test_validate_positive_int_invalid_string(self):
        """Test validation fails for invalid string"""
        from utils.error_handling import validate_positive_int, ValidationError
        
        with pytest.raises(ValidationError):
            validate_positive_int("abc", "count")

    def test_validate_positive_int_none(self):
        """Test validation fails for None"""
        from utils.error_handling import validate_positive_int, ValidationError
        
        with pytest.raises(ValidationError):
            validate_positive_int(None, "count")
