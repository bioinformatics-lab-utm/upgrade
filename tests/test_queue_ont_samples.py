#!/usr/bin/env python3
"""
Unit tests for scripts/queue_ont_samples.py

Tests the parameterized SQL query implementation to ensure
SQL injection prevention and correct functionality.
"""

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from queue_ont_samples import (
    get_db_connection,
    exec_sql,
    insert_samples,
)


class TestGetDbConnection:
    """Tests for get_db_connection function."""

    @patch('queue_ont_samples.psycopg2.connect')
    def test_get_db_connection_with_defaults(self, mock_connect):
        """Test connection uses default values when env vars not set."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        # Clear env vars
        env_backup = {
            k: os.environ.pop(k, None)
            for k in ['POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD']
        }

        try:
            conn = get_db_connection()
            mock_connect.assert_called_once_with(
                host='localhost',
                port=5432,
                database='upgrade_db',
                user='upgrade',
                password='upgrade',
            )
            assert conn == mock_conn
        finally:
            # Restore env vars
            for k, v in env_backup.items():
                if v is not None:
                    os.environ[k] = v

    @patch('queue_ont_samples.psycopg2.connect')
    @patch.dict(os.environ, {
        'POSTGRES_HOST': 'custom_host',
        'POSTGRES_PORT': '5433',
        'POSTGRES_DB': 'custom_db',
        'POSTGRES_USER': 'custom_user',
        'POSTGRES_PASSWORD': 'custom_pass',
    })
    def test_get_db_connection_with_env_vars(self, mock_connect):
        """Test connection uses environment variables when set."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        conn = get_db_connection()
        mock_connect.assert_called_once_with(
            host='custom_host',
            port=5433,
            database='custom_db',
            user='custom_user',
            password='custom_pass',
        )
        assert conn == mock_conn


class TestExecSql:
    """Tests for exec_sql function."""

    @patch('queue_ont_samples.get_db_connection')
    def test_exec_sql_fetch_results(self, mock_get_conn):
        """Test exec_sql returns fetched results correctly."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [('value1', 'value2'), ('value3', 'value4')]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        result = exec_sql("SELECT * FROM test WHERE id = %s", (1,))

        mock_cursor.execute.assert_called_once_with("SELECT * FROM test WHERE id = %s", (1,))
        assert result == "value1|value2\nvalue3|value4"
        mock_conn.close.assert_called_once()

    @patch('queue_ont_samples.get_db_connection')
    def test_exec_sql_no_fetch(self, mock_get_conn):
        """Test exec_sql with fetch=False returns rowcount."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 5
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        result = exec_sql("INSERT INTO test VALUES (%s)", ('val',), fetch=False)

        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
        assert result == "5"

    @patch('queue_ont_samples.get_db_connection')
    def test_exec_sql_empty_results(self, mock_get_conn):
        """Test exec_sql returns empty string for no results."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        result = exec_sql("SELECT * FROM test WHERE 1=0")
        assert result == ""

    @patch('queue_ont_samples.get_db_connection')
    def test_exec_sql_handles_db_error(self, mock_get_conn):
        """Test exec_sql handles database errors gracefully."""
        import psycopg2

        mock_get_conn.side_effect = psycopg2.Error("Connection failed")

        result = exec_sql("SELECT 1")
        assert result is None


class TestInsertSamples:
    """Tests for insert_samples function."""

    @patch('queue_ont_samples.get_db_connection')
    def test_insert_samples_valid(self, mock_get_conn):
        """Test inserting valid samples."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # Not in queue
        mock_cursor.rowcount = 1
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        samples = [
            {'run_id': 'SRR123', 'file_size_mb': 100.5, 'lat': 45.0, 'lon': -73.0},
            {'run_id': 'SRR456', 'file_size_mb': 200.0, 'lat': 46.0, 'lon': -74.0},
        ]

        inserted = insert_samples(samples)

        assert inserted == 2
        # Verify parameterized queries were used
        insert_calls = [c for c in mock_cursor.execute.call_args_list if 'INSERT' in str(c)]
        assert len(insert_calls) == 2

    @patch('queue_ont_samples.get_db_connection')
    def test_insert_samples_skips_invalid_coordinates(self, mock_get_conn):
        """Test samples with invalid coordinates are skipped."""
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        samples = [
            {'run_id': 'SRR123', 'file_size_mb': 100.5, 'lat': 'N/A', 'lon': -73.0},
            {'run_id': 'SRR456', 'file_size_mb': 200.0, 'lat': 'invalid', 'lon': -74.0},
            {'run_id': 'SRR789', 'file_size_mb': 150.0, 'lat': 'NULL', 'lon': 'NULL'},
        ]

        inserted = insert_samples(samples)
        assert inserted == 0

    @patch('queue_ont_samples.get_db_connection')
    def test_insert_samples_skips_existing(self, mock_get_conn):
        """Test samples already in queue are skipped."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('SRR123',)  # Already in queue
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        samples = [
            {'run_id': 'SRR123', 'file_size_mb': 100.5, 'lat': 45.0, 'lon': -73.0},
        ]

        inserted = insert_samples(samples)
        assert inserted == 0

    @patch('queue_ont_samples.get_db_connection')
    def test_insert_samples_sql_injection_prevention(self, mock_get_conn):
        """Test that SQL injection attempts are safely handled via parameterization."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.rowcount = 1
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # Attempt SQL injection via accession field
        malicious_accession = "SRR123'; DROP TABLE sample_queue; --"
        samples = [
            {'run_id': malicious_accession, 'file_size_mb': 100.0, 'lat': 45.0, 'lon': -73.0},
        ]

        inserted = insert_samples(samples)

        # Verify the malicious string was passed as a parameter, not interpolated
        insert_calls = [c for c in mock_cursor.execute.call_args_list if 'INSERT' in str(c)]
        assert len(insert_calls) == 1

        # The accession should be in the parameters tuple, not in the SQL string
        call_args = insert_calls[0]
        sql_query = call_args[0][0]
        params = call_args[0][1]

        # SQL should use %s placeholder, not the actual value
        assert malicious_accession not in sql_query
        assert '%s' in sql_query
        assert malicious_accession in params


class TestMainFunction:
    """Tests for main function."""

    @patch('queue_ont_samples.insert_samples')
    @patch('queue_ont_samples.exec_sql')
    def test_main_loads_json_with_samples_key(self, mock_exec_sql, mock_insert):
        """Test main function loads JSON with 'samples' key."""
        from queue_ont_samples import main

        mock_insert.return_value = 1
        mock_exec_sql.return_value = "pending|5|2.5"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'samples': [
                    {'run_id': 'SRR123', 'file_size_mb': 100.0, 'lat': 45.0, 'lon': -73.0}
                ]
            }, f)
            f.flush()

            with patch.object(sys, 'argv', ['queue_ont_samples.py', f.name]):
                main()

            mock_insert.assert_called_once()
            samples_arg = mock_insert.call_args[0][0]
            assert len(samples_arg) == 1
            assert samples_arg[0]['run_id'] == 'SRR123'

        os.unlink(f.name)

    @patch('queue_ont_samples.insert_samples')
    @patch('queue_ont_samples.exec_sql')
    def test_main_loads_json_array_directly(self, mock_exec_sql, mock_insert):
        """Test main function loads JSON that is directly an array."""
        from queue_ont_samples import main

        mock_insert.return_value = 1
        mock_exec_sql.return_value = "pending|5|2.5"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([
                {'run_id': 'SRR456', 'file_size_mb': 200.0, 'lat': 46.0, 'lon': -74.0}
            ], f)
            f.flush()

            with patch.object(sys, 'argv', ['queue_ont_samples.py', f.name]):
                main()

            mock_insert.assert_called_once()
            samples_arg = mock_insert.call_args[0][0]
            assert len(samples_arg) == 1
            assert samples_arg[0]['run_id'] == 'SRR456'

        os.unlink(f.name)

    def test_main_exits_without_args(self):
        """Test main exits with error when no arguments provided."""
        from queue_ont_samples import main

        with patch.object(sys, 'argv', ['queue_ont_samples.py']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
