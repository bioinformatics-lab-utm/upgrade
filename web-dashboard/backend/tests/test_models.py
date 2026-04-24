"""
Tests for Pydantic Models
"""
import pytest
from datetime import date, datetime, time
from decimal import Decimal
from pydantic import ValidationError


class TestUserModels:
    """Tests for User Pydantic models"""

    def test_user_create_valid(self):
        """Test creating a valid UserCreate"""
        from models.user import UserCreate
        
        user = UserCreate(
            username="testuser",
            email="test@example.com",
            password="securepassword123"
        )
        
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.password == "securepassword123"
        assert user.is_active is True

    def test_user_create_with_optional_fields(self):
        """Test UserCreate with optional fields"""
        from models.user import UserCreate

        user = UserCreate(
            username="testuser",
            email="test@example.com",
            password="securepassword123",
            full_name="Test User",
            user_type="admin"
        )

        assert user.full_name == "Test User"
        assert user.user_type == "admin"

    def test_user_create_invalid_email(self):
        """Test UserCreate with invalid email"""
        from models.user import UserCreate
        
        with pytest.raises(ValidationError):
            UserCreate(
                username="testuser",
                email="invalid-email",
                password="securepassword123"
            )

    def test_user_create_short_username(self):
        """Test UserCreate with too short username"""
        from models.user import UserCreate
        
        with pytest.raises(ValidationError):
            UserCreate(
                username="ab",
                email="test@example.com",
                password="securepassword123"
            )

    def test_user_create_short_password(self):
        """Test UserCreate with too short password"""
        from models.user import UserCreate
        
        with pytest.raises(ValidationError):
            UserCreate(
                username="testuser",
                email="test@example.com",
                password="short"
            )

    def test_user_update_optional_fields(self):
        """Test UserUpdate with optional fields"""
        from models.user import UserUpdate
        
        update = UserUpdate(email="new@example.com")
        
        assert update.email == "new@example.com"
        assert update.full_name is None
        assert update.is_active is None

    def test_user_model_dict_serialization(self):
        """Test User model serialization to dict"""
        from models.user import User
        
        user = User(
            user_id=1,
            username="testuser",
            email="test@example.com",
            password_hash="hashed_password",
            role="user"
        )
        
        data = user.model_dump()
        
        assert data["user_id"] == 1
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"

    def test_user_login_model(self):
        """Test UserLogin model"""
        from models.user import UserLogin
        
        login = UserLogin(username="testuser", password="password123")
        
        assert login.username == "testuser"
        assert login.password == "password123"

    def test_token_model(self):
        """Test Token model"""
        from models.user import Token
        
        token = Token(access_token="abc123token")
        
        assert token.access_token == "abc123token"
        assert token.token_type == "bearer"


class TestSampleModels:
    """Tests for Sample Pydantic models"""

    def test_sample_create_valid(self):
        """Test creating a valid SampleCreate"""
        from models.sample import SampleCreate
        
        sample = SampleCreate(
            sample_code="SAMPLE001",
            collection_date=date(2024, 1, 15)
        )
        
        assert sample.sample_code == "SAMPLE001"
        assert sample.collection_date == date(2024, 1, 15)
        assert sample.status == "collected"

    def test_sample_create_with_optional_fields(self):
        """Test SampleCreate with optional fields"""
        from models.sample import SampleCreate
        
        sample = SampleCreate(
            sample_code="SAMPLE002",
            collection_date=date(2024, 1, 15),
            sample_type="surface_swab",
            sample_volume_ml=Decimal("10.5"),
            sequencing_platform="MinION",
            processing_priority=2
        )
        
        assert sample.sample_type == "surface_swab"
        assert sample.sample_volume_ml == Decimal("10.5")
        assert sample.sequencing_platform == "MinION"
        assert sample.processing_priority == 2

    def test_sample_update_optional(self):
        """Test SampleUpdate with optional fields"""
        from models.sample import SampleUpdate
        
        update = SampleUpdate(status="processing")
        
        assert update.status == "processing"
        assert update.sample_type is None

    def test_sample_model_with_all_fields(self):
        """Test full Sample model"""
        from models.sample import Sample
        
        sample = Sample(
            sample_id=1,
            sample_code="SAMPLE003",
            collection_date=date(2024, 1, 15),
            status="sequenced"
        )
        
        assert sample.sample_id == 1
        assert sample.sample_code == "SAMPLE003"

    def test_sample_processing_priority_validation(self):
        """Test processing priority must be 1-5"""
        from models.sample import SampleCreate
        
        with pytest.raises(ValidationError):
            SampleCreate(
                sample_code="SAMPLE004",
                collection_date=date(2024, 1, 15),
                processing_priority=10
            )

    def test_sample_model_dict_serialization(self):
        """Test Sample model serialization"""
        from models.sample import Sample
        
        sample = Sample(
            sample_id=1,
            sample_code="SAMPLE005",
            collection_date=date(2024, 1, 15)
        )
        
        data = sample.model_dump()
        
        assert data["sample_id"] == 1
        assert data["sample_code"] == "SAMPLE005"

    def test_sample_with_metadata(self):
        """Test Sample with metadata dict"""
        from models.sample import SampleCreate
        
        sample = SampleCreate(
            sample_code="SAMPLE006",
            collection_date=date(2024, 1, 15),
            metadata={"key": "value", "count": 42}
        )
        
        assert sample.metadata["key"] == "value"
        assert sample.metadata["count"] == 42


class TestPipelineRunModels:
    """Tests for PipelineRun Pydantic models"""

    def test_pipeline_run_create_valid(self):
        """Test creating a valid PipelineRunCreate"""
        from models.pipeline_run import PipelineRunCreate
        
        run = PipelineRunCreate(
            sample_id=1,
            pipeline_name="nextflow_amr_pipeline",
            pipeline_version="2.0.0"
        )
        
        assert run.sample_id == 1
        assert run.pipeline_name == "nextflow_amr_pipeline"
        assert run.status == "queued"

    def test_pipeline_run_create_with_parameters(self):
        """Test PipelineRunCreate with parameters dict"""
        from models.pipeline_run import PipelineRunCreate
        
        run = PipelineRunCreate(
            sample_id=1,
            pipeline_name="test_pipeline",
            parameters={"min_quality": 30, "threads": 8}
        )
        
        assert run.parameters["min_quality"] == 30
        assert run.parameters["threads"] == 8

    def test_pipeline_run_update_optional(self):
        """Test PipelineRunUpdate optional fields"""
        from models.pipeline_run import PipelineRunUpdate
        
        update = PipelineRunUpdate(status="running")
        
        assert update.status == "running"
        assert update.exit_code is None

    def test_pipeline_run_update_with_error(self):
        """Test PipelineRunUpdate with error info"""
        from models.pipeline_run import PipelineRunUpdate
        
        update = PipelineRunUpdate(
            status="failed",
            exit_code=1,
            error_message="Pipeline failed at step 3"
        )
        
        assert update.status == "failed"
        assert update.exit_code == 1
        assert update.error_message == "Pipeline failed at step 3"

    def test_pipeline_run_model_full(self):
        """Test full PipelineRun model"""
        from models.pipeline_run import PipelineRun
        
        run = PipelineRun(
            pipeline_id=1,
            sample_id=1,
            pipeline_name="amr_detection",
            status="completed",
            exit_code=0
        )
        
        assert run.pipeline_id == 1
        assert run.status == "completed"
        assert run.exit_code == 0

    def test_pipeline_run_status_values(self):
        """Test various status values"""
        from models.pipeline_run import PipelineRunCreate
        
        for status in ["queued", "running", "completed", "failed", "cancelled"]:
            run = PipelineRunCreate(
                sample_id=1,
                pipeline_name="test",
                status=status
            )
            assert run.status == status

    def test_pipeline_run_dict_serialization(self):
        """Test PipelineRun serialization"""
        from models.pipeline_run import PipelineRun
        
        run = PipelineRun(
            pipeline_id=1,
            sample_id=1,
            pipeline_name="test"
        )
        
        data = run.model_dump()
        
        assert data["pipeline_id"] == 1
        assert data["sample_id"] == 1

    def test_pipeline_run_with_paths(self):
        """Test PipelineRun with result paths"""
        from models.pipeline_run import PipelineRun
        
        run = PipelineRun(
            pipeline_id=1,
            sample_id=1,
            pipeline_name="test",
            results_path="/minio/results/run_1",
            log_file_path="/minio/logs/run_1.log"
        )
        
        assert run.results_path == "/minio/results/run_1"
        assert run.log_file_path == "/minio/logs/run_1.log"

    def test_pipeline_run_with_resources(self):
        """Test PipelineRun with computational resources"""
        from models.pipeline_run import PipelineRunCreate
        
        run = PipelineRunCreate(
            sample_id=1,
            pipeline_name="test",
            cpu_cores=16,
            memory_gb=64,
            runtime_minutes=120
        )
        
        assert run.cpu_cores == 16
        assert run.memory_gb == 64
        assert run.runtime_minutes == 120


class TestModelImports:
    """Tests for model imports from __init__"""

    def test_import_all_models(self):
        """Test importing all models from models package"""
        from models import User, Sample, PipelineRun
        
        assert User is not None
        assert Sample is not None
        assert PipelineRun is not None

    def test_import_create_models(self):
        """Test importing create models"""
        from models.user import UserCreate
        from models.sample import SampleCreate
        from models.pipeline_run import PipelineRunCreate
        
        assert UserCreate is not None
        assert SampleCreate is not None
        assert PipelineRunCreate is not None

    def test_import_update_models(self):
        """Test importing update models"""
        from models.user import UserUpdate
        from models.sample import SampleUpdate
        from models.pipeline_run import PipelineRunUpdate
        
        assert UserUpdate is not None
        assert SampleUpdate is not None
        assert PipelineRunUpdate is not None
