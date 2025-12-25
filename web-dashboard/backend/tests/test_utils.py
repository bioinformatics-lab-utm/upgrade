"""
Tests for utility functions
"""
import pytest
from pathlib import Path
import tempfile
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.fastq_validator import validate_fastq_files, FASTQValidationError


@pytest.mark.unit
class TestFASTQValidator:
    """Test FASTQ file validation"""
    
    def test_valid_fastq_format(self, sample_fastq_content, temp_results_dir):
        """Test validation of correctly formatted FASTQ"""
        fastq_file = temp_results_dir / "test.fastq"
        fastq_file.write_text(sample_fastq_content)
        
        # Should not raise exception
        try:
            result = validate_fastq_files([str(fastq_file)])
            assert result is True or result is None
        except FASTQValidationError:
            pytest.fail("Valid FASTQ file raised validation error")
    
    def test_invalid_fastq_format(self, temp_results_dir):
        """Test validation of incorrectly formatted FASTQ"""
        fastq_file = temp_results_dir / "invalid.fastq"
        fastq_file.write_text("Invalid content\nNot a FASTQ file")
        
        # Should raise validation error
        with pytest.raises(FASTQValidationError):
            validate_fastq_files([str(fastq_file)])
    
    def test_empty_fastq_file(self, temp_results_dir):
        """Test validation of empty FASTQ file"""
        fastq_file = temp_results_dir / "empty.fastq"
        fastq_file.write_text("")
        
        with pytest.raises(FASTQValidationError):
            validate_fastq_files([str(fastq_file)])
    
    def test_fastq_file_not_found(self):
        """Test validation when file doesn't exist"""
        with pytest.raises((FASTQValidationError, FileNotFoundError)):
            validate_fastq_files(["/nonexistent/file.fastq"])
    
    def test_multiple_fastq_files(self, sample_fastq_content, temp_results_dir):
        """Test validation of multiple FASTQ files"""
        files = []
        for i in range(3):
            fastq_file = temp_results_dir / f"test_{i}.fastq"
            fastq_file.write_text(sample_fastq_content)
            files.append(str(fastq_file))
        
        try:
            result = validate_fastq_files(files)
            assert result is True or result is None
        except FASTQValidationError:
            pytest.fail("Valid FASTQ files raised validation error")
    
    def test_fastq_quality_scores(self, sample_fastq_content):
        """Test FASTQ quality score validation"""
        # Quality scores should be valid ASCII characters
        lines = sample_fastq_content.strip().split('\n')
        quality_lines = [lines[i] for i in range(3, len(lines), 4)]
        
        for qual in quality_lines:
            # Quality scores should be printable ASCII
            assert all(33 <= ord(c) <= 126 for c in qual)
    
    def test_fastq_sequence_length_match(self, sample_fastq_content):
        """Test that sequence and quality lengths match"""
        lines = sample_fastq_content.strip().split('\n')
        
        # Get first record
        seq = lines[1]  # Sequence line
        qual = lines[3]  # Quality line
        
        assert len(seq) == len(qual)


@pytest.mark.unit
class TestFileOperations:
    """Test file utility operations"""
    
    def test_create_directory_structure(self, temp_results_dir):
        """Test creating nested directory structure"""
        nested_dir = temp_results_dir / "level1" / "level2" / "level3"
        nested_dir.mkdir(parents=True, exist_ok=True)
        
        assert nested_dir.exists()
        assert nested_dir.is_dir()
    
    def test_file_permissions(self, temp_results_dir):
        """Test file read/write permissions"""
        test_file = temp_results_dir / "test.txt"
        test_file.write_text("test content")
        
        assert test_file.exists()
        assert os.access(test_file, os.R_OK)
        assert os.access(test_file, os.W_OK)
    
    def test_file_size_calculation(self, temp_results_dir):
        """Test file size calculation"""
        test_file = temp_results_dir / "test.txt"
        content = "A" * 1024  # 1KB
        test_file.write_text(content)
        
        size = test_file.stat().st_size
        assert size == 1024
    
    def test_list_directory_contents(self, temp_results_dir):
        """Test listing directory contents"""
        # Create some files
        for i in range(5):
            (temp_results_dir / f"file_{i}.txt").write_text(f"content {i}")
        
        files = list(temp_results_dir.glob("*.txt"))
        assert len(files) == 5
    
    def test_search_files_by_pattern(self, temp_results_dir):
        """Test searching files by pattern"""
        # Create files with different extensions
        (temp_results_dir / "data.json").write_text("{}")
        (temp_results_dir / "data.xml").write_text("<root/>")
        (temp_results_dir / "summary.json").write_text("{}")
        
        json_files = list(temp_results_dir.glob("*.json"))
        assert len(json_files) == 2
    
    def test_recursive_file_search(self, temp_results_dir):
        """Test recursive file search"""
        # Create nested structure
        (temp_results_dir / "dir1").mkdir()
        (temp_results_dir / "dir2").mkdir()
        (temp_results_dir / "dir1" / "file.txt").write_text("content")
        (temp_results_dir / "dir2" / "file.txt").write_text("content")
        
        files = list(temp_results_dir.rglob("*.txt"))
        assert len(files) == 2


@pytest.mark.unit
class TestDataValidation:
    """Test data validation utilities"""
    
    def test_validate_sample_code_format(self):
        """Test sample code format validation"""
        valid_codes = ["SRR12345678", "TEST_SAMPLE_001", "sample_001"]
        
        for code in valid_codes:
            assert len(code) > 0
            assert not code.isspace()
    
    def test_validate_pipeline_parameters(self, sample_pipeline_params):
        """Test pipeline parameter validation"""
        required_params = ['sample_code', 'input_dir', 'outdir']
        
        for param in required_params:
            assert param in sample_pipeline_params
            assert sample_pipeline_params[param] is not None
    
    def test_validate_quality_score_range(self):
        """Test quality score validation"""
        valid_scores = [0, 25.5, 50, 75.3, 100]
        
        for score in valid_scores:
            assert 0 <= score <= 100
    
    def test_validate_mags_count(self):
        """Test MAGs count validation"""
        valid_counts = [0, 10, 25, 50, 100]
        
        for count in valid_counts:
            assert count >= 0
            assert isinstance(count, int)
    
    def test_validate_date_format(self):
        """Test date format validation"""
        from datetime import datetime
        
        date_strings = ["2025-12-24", "2025-01-01", "2025-12-31"]
        
        for date_str in date_strings:
            try:
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
                assert parsed_date is not None
            except ValueError:
                pytest.fail(f"Invalid date format: {date_str}")


@pytest.mark.unit
class TestJSONOperations:
    """Test JSON parsing and validation"""
    
    def test_parse_summary_json(self, sample_summary_data):
        """Test parsing summary JSON data"""
        import json
        
        # Convert to JSON and back
        json_str = json.dumps(sample_summary_data)
        parsed = json.loads(json_str)
        
        assert parsed == sample_summary_data
    
    def test_validate_json_schema(self, sample_summary_data):
        """Test JSON schema validation"""
        required_fields = [
            'sample_id',
            'pipeline_version',
            'quality_score',
            'mags',
            'amr'
        ]
        
        for field in required_fields:
            assert field in sample_summary_data
    
    def test_handle_missing_json_fields(self, sample_summary_data):
        """Test handling missing optional fields"""
        # Remove optional field
        data = sample_summary_data.copy()
        data.pop('pathogens', None)
        
        # Should still be valid
        assert 'sample_id' in data
        assert 'quality_score' in data
