"""
Tests for SRA Batch Processor
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
import logging


class TestSRABatchProcessorImports:
    """Test SRA Batch Processor imports"""

    def test_os_import(self):
        """Test os can be imported"""
        import os
        assert os is not None

    def test_json_import(self):
        """Test json can be imported"""
        import json
        assert json is not None

    def test_logging_import(self):
        """Test logging can be imported"""
        import logging
        assert logging is not None

    def test_pathlib_import(self):
        """Test pathlib can be imported"""
        from pathlib import Path
        assert Path is not None


class TestSRABatchProcessorClass:
    """Test SRABatchProcessor class"""

    def test_class_exists(self):
        """Test SRABatchProcessor class exists"""
        from sra_batch_processor import SRABatchProcessor
        assert SRABatchProcessor is not None

    def test_init_creates_instance(self):
        """Test init creates instance"""
        from sra_batch_processor import SRABatchProcessor
        
        processor = SRABatchProcessor()
        
        assert processor is not None

    def test_init_sets_db_config(self):
        """Test init sets db_config"""
        from sra_batch_processor import SRABatchProcessor
        
        processor = SRABatchProcessor()
        
        assert processor.db_config is not None
        assert 'host' in processor.db_config
        assert 'port' in processor.db_config
        assert 'database' in processor.db_config
        assert 'user' in processor.db_config

    def test_init_sets_paths(self):
        """Test init sets directory paths"""
        from sra_batch_processor import SRABatchProcessor
        
        processor = SRABatchProcessor()
        
        assert processor.data_dir is not None
        assert processor.results_dir is not None
        assert processor.nextflow_script is not None
        assert processor.metadata_file is not None


class TestSRABatchProcessorDBConnection:
    """Test database connection methods"""

    def test_has_get_db_connection_method(self):
        """Test has _get_db_connection method"""
        from sra_batch_processor import SRABatchProcessor
        
        processor = SRABatchProcessor()
        
        assert hasattr(processor, '_get_db_connection')
        assert callable(processor._get_db_connection)


class TestSRABatchProcessorTables:
    """Test table creation methods"""

    def test_has_create_sample_queue_table_method(self):
        """Test has _create_sample_queue_table method"""
        from sra_batch_processor import SRABatchProcessor
        
        processor = SRABatchProcessor()
        
        assert hasattr(processor, '_create_sample_queue_table')
        assert callable(processor._create_sample_queue_table)


class TestSRABatchProcessorLogger:
    """Test logger configuration"""

    def test_logger_exists(self):
        """Test logger is configured"""
        from sra_batch_processor import logger
        
        assert logger is not None
        assert isinstance(logger, logging.Logger)


class TestSRABatchProcessorConfig:
    """Test configuration defaults"""

    def test_default_db_host(self):
        """Test default database host"""
        import os
        from sra_batch_processor import SRABatchProcessor
        
        processor = SRABatchProcessor()
        
        expected = os.getenv('POSTGRES_HOST', 'postgres')
        assert processor.db_config['host'] == expected

    def test_default_db_port(self):
        """Test default database port"""
        import os
        from sra_batch_processor import SRABatchProcessor
        
        processor = SRABatchProcessor()
        
        expected = os.getenv('POSTGRES_PORT', '5432')
        assert processor.db_config['port'] == expected

    def test_default_db_name(self):
        """Test default database name"""
        import os
        from sra_batch_processor import SRABatchProcessor
        
        processor = SRABatchProcessor()
        
        expected = os.getenv('POSTGRES_DB', 'upgrade_db')
        assert processor.db_config['database'] == expected


class TestSRABatchProcessorPaths:
    """Test path configurations"""

    def test_data_dir_is_path(self):
        """Test data_dir is Path"""
        from pathlib import Path
        from sra_batch_processor import SRABatchProcessor
        
        processor = SRABatchProcessor()
        
        assert isinstance(processor.data_dir, Path)
        assert str(processor.data_dir) == '/data'

    def test_results_dir_is_path(self):
        """Test results_dir is Path"""
        from pathlib import Path
        from sra_batch_processor import SRABatchProcessor
        
        processor = SRABatchProcessor()
        
        assert isinstance(processor.results_dir, Path)
        assert str(processor.results_dir) == '/results'

    def test_nextflow_script_is_path(self):
        """Test nextflow_script is Path"""
        from pathlib import Path
        from sra_batch_processor import SRABatchProcessor
        
        processor = SRABatchProcessor()
        
        assert isinstance(processor.nextflow_script, Path)

    def test_metadata_file_is_path(self):
        """Test metadata_file is Path"""
        from pathlib import Path
        from sra_batch_processor import SRABatchProcessor
        
        processor = SRABatchProcessor()
        
        assert isinstance(processor.metadata_file, Path)
