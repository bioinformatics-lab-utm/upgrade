"""
Tests for Worker Init module
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import logging


class TestWorkerInitImports:
    """Test worker_init imports"""

    def test_asyncio_import(self):
        """Test asyncio can be imported"""
        import asyncio
        assert asyncio is not None

    def test_logging_import(self):
        """Test logging can be imported"""
        import logging
        assert logging is not None

    def test_pathlib_import(self):
        """Test pathlib can be imported"""
        from pathlib import Path
        assert Path is not None


class TestReadSecret:
    """Test read_secret (the worker reads its passwords from Docker secrets)"""

    def test_reads_and_strips(self, tmp_path):
        """Test the secret file content is returned without the trailing newline"""
        from worker_init import read_secret

        secret = tmp_path / "redis_password"
        secret.write_text("s3cret\n")

        assert read_secret(str(secret)) == "s3cret"

    def test_missing_file_returns_none(self, tmp_path):
        """Test a missing secret falls back to None (env vars are used instead)"""
        from worker_init import read_secret

        assert read_secret(str(tmp_path / "missing")) is None


class TestWorkerInitLogger:
    """Test logger configuration"""

    def test_logger_exists(self):
        """Test logger is configured"""
        from worker_init import logger
        
        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_logger_name(self):
        """Test logger has correct name"""
        from worker_init import logger
        
        assert logger.name == 'worker_init'


class TestWorkerInitConfiguration:
    """Test worker init configuration"""

    def test_imports_database_pool(self):
        """Test imports DatabasePool"""
        from database import DatabasePool
        assert DatabasePool is not None

    def test_imports_config(self):
        """Test imports config"""
        import config
        assert config is not None
