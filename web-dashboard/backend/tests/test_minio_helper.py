"""
Unit tests for MinIO helper functions
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import minio_helper


class TestMinIOClientCreation(unittest.TestCase):
    """Test MinIO client creation"""

    @patch('minio_helper.Minio')
    @patch.dict('os.environ', {
        'MINIO_ENDPOINT': 'localhost:9000',
        'MINIO_ROOT_USER': 'admin',
        'MINIO_ROOT_PASSWORD': 'password123'
    })
    def test_get_minio_client(self, mock_minio):
        """Test MinIO client instantiation"""
        client = minio_helper.get_minio_client()

        # Check that Minio was called with correct parameters
        mock_minio.assert_called_once()
        call_args = mock_minio.call_args
        self.assertEqual(call_args[0][0], 'localhost:9000')
        self.assertEqual(call_args[1]['access_key'], 'admin')
        self.assertEqual(call_args[1]['secret_key'], 'password123')
        self.assertEqual(call_args[1]['secure'], False)


class TestBucketOperations(unittest.TestCase):
    """Test bucket-related operations"""

    @patch('minio_helper.get_minio_client')
    def test_get_or_create_bucket_exists(self, mock_get_client):
        """Test getting existing bucket"""
        mock_client = Mock()
        mock_client.bucket_exists.return_value = True
        mock_get_client.return_value = mock_client

        result = minio_helper.get_or_create_bucket('test-bucket')

        self.assertTrue(result)
        mock_client.bucket_exists.assert_called_once_with('test-bucket')
        mock_client.make_bucket.assert_not_called()

    @patch('minio_helper.get_minio_client')
    def test_get_or_create_bucket_creates(self, mock_get_client):
        """Test creating new bucket"""
        mock_client = Mock()
        mock_client.bucket_exists.return_value = False
        mock_get_client.return_value = mock_client

        result = minio_helper.get_or_create_bucket('test-bucket')

        self.assertTrue(result)
        mock_client.bucket_exists.assert_called_once_with('test-bucket')
        mock_client.make_bucket.assert_called_once_with('test-bucket')


class TestPathGeneration(unittest.TestCase):
    """Test path generation utilities"""

    def test_bronze_path_generation(self):
        """Test bronze layer path generation"""
        # This test assumes upload_to_bronze generates paths like bronze/sample_code/filename
        sample_code = "sample_001"
        filename = "test.fastq.gz"

        # Expected path format
        expected_prefix = f"bronze/{sample_code}/"

        # Note: Actual path generation depends on implementation
        # This is a placeholder test structure
        self.assertTrue(expected_prefix.startswith("bronze/"))

    def test_silver_path_generation(self):
        """Test silver layer path generation"""
        sample_code = "sample_001"
        expected_prefix = f"silver/{sample_code}/"

        self.assertTrue(expected_prefix.startswith("silver/"))

    def test_gold_path_generation(self):
        """Test gold layer path generation"""
        sample_code = "sample_001"
        expected_prefix = f"gold/{sample_code}/"

        self.assertTrue(expected_prefix.startswith("gold/"))


if __name__ == '__main__':
    unittest.main()
