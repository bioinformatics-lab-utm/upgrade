"""
Tests for Utility modules
"""
import pytest
from unittest.mock import Mock, patch
import io


class TestFastqValidatorImport:
    """Tests for FASTQ validator imports"""

    def test_validator_module_import(self):
        """Test FASTQ validator module can be imported"""
        from utils import fastq_validator
        assert fastq_validator is not None

    def test_validation_error_class(self):
        """Test FASTQValidationError class exists"""
        from utils.fastq_validator import FASTQValidationError
        assert FASTQValidationError is not None
        
        # Should be an Exception subclass
        assert issubclass(FASTQValidationError, Exception)


class TestValidateFastqFilename:
    """Tests for validate_fastq_filename function"""

    def test_valid_fastq_extension(self):
        """Test valid .fastq extension"""
        from utils.fastq_validator import validate_fastq_filename
        
        is_valid, error = validate_fastq_filename("sample.fastq")
        assert is_valid is True
        assert error == ""

    def test_valid_fq_extension(self):
        """Test valid .fq extension"""
        from utils.fastq_validator import validate_fastq_filename
        
        is_valid, error = validate_fastq_filename("sample.fq")
        assert is_valid is True

    def test_valid_fastq_gz_extension(self):
        """Test valid .fastq.gz extension"""
        from utils.fastq_validator import validate_fastq_filename
        
        is_valid, error = validate_fastq_filename("sample.fastq.gz")
        assert is_valid is True

    def test_valid_fq_gz_extension(self):
        """Test valid .fq.gz extension"""
        from utils.fastq_validator import validate_fastq_filename
        
        is_valid, error = validate_fastq_filename("sample.fq.gz")
        assert is_valid is True

    def test_invalid_extension(self):
        """Test invalid file extension"""
        from utils.fastq_validator import validate_fastq_filename
        
        is_valid, error = validate_fastq_filename("sample.txt")
        assert is_valid is False
        assert "Invalid file extension" in error

    def test_case_insensitive(self):
        """Test case insensitive extension check"""
        from utils.fastq_validator import validate_fastq_filename
        
        is_valid, error = validate_fastq_filename("SAMPLE.FASTQ")
        assert is_valid is True


class TestValidateFastqContent:
    """Tests for validate_fastq_content function"""

    def test_valid_fastq_content(self):
        """Test validating correct FASTQ content"""
        from utils.fastq_validator import validate_fastq_content
        
        # Valid FASTQ record
        valid_fastq = b"""@SEQ_ID
GATTTGGGGTTCAAAGCAGTATCGATCAAATAGTAAATCCATTTGTTCAACTCACAGTTT
+
!''*((((***+))%%%++)(%%%%).1***-+*''))**55CCF>>>>>>CCCCCCC65
"""
        file_obj = io.BytesIO(valid_fastq)
        is_valid, error = validate_fastq_content(file_obj)
        
        assert is_valid is True

    def test_empty_file(self):
        """Test validating empty file"""
        from utils.fastq_validator import validate_fastq_content
        
        file_obj = io.BytesIO(b"")
        is_valid, error = validate_fastq_content(file_obj)
        
        assert is_valid is False


class TestValidateFastqFileSize:
    """Tests for validate_fastq_file_size function"""

    def test_valid_file_size(self):
        """Test validating valid file size"""
        from utils.fastq_validator import validate_fastq_file_size
        
        # 1 MB file
        is_valid, error = validate_fastq_file_size(1024 * 1024)
        assert is_valid is True

    def test_file_too_small(self):
        """Test rejecting file too small"""
        from utils.fastq_validator import validate_fastq_file_size
        
        # 10 bytes
        is_valid, error = validate_fastq_file_size(10)
        assert is_valid is False

    def test_file_too_large(self):
        """Test rejecting file too large"""
        from utils.fastq_validator import validate_fastq_file_size
        
        # 20 GB (exceeds default 10 GB max)
        is_valid, error = validate_fastq_file_size(20 * 1024**3)
        assert is_valid is False


class TestValidateFastqFiles:
    """Tests for validate_fastq_files function"""

    def test_validate_fastq_files_exists(self):
        """Test validate_fastq_files function exists"""
        from utils.fastq_validator import validate_fastq_files
        assert callable(validate_fastq_files)
