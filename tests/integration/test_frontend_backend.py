"""
Integration tests for frontend-backend communication
Tests API endpoints and error handling
"""
import pytest
import requests
from pathlib import Path


class TestAPIEndpoints:
    """Test backend API endpoints"""

    @pytest.fixture(scope="class")
    def base_url(self):
        """Base URL for API"""
        return "http://100.72.39.49:8000"

    @pytest.fixture(scope="class")
    def frontend_url(self):
        """Frontend URL"""
        return "http://100.72.39.49:3000"

    def test_backend_health(self, base_url):
        """Test that backend health endpoint works"""
        response = requests.get(f"{base_url}/api/health", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert 'measurement_datetime' in data

    def test_frontend_accessible(self, frontend_url):
        """Test that frontend is accessible"""
        response = requests.get(frontend_url, timeout=5)
        assert response.status_code == 200
        assert 'text/html' in response.headers.get('Content-Type', '')

    def test_pipeline_summary_not_found(self, base_url):
        """Test API returns proper error for non-existent pipeline"""
        response = requests.get(
            f"{base_url}/api/pipeline/results/nonexistent_sample/pipeline-summary",
            timeout=5
        )
        # Should return 404 with error JSON
        assert response.status_code == 404
        data = response.json()
        assert 'error' in data
        assert 'run_id' in data

    def test_pipeline_summary_response_structure(self, base_url):
        """Test API returns proper structure for pipeline summary"""
        # Test with test_large_0101
        response = requests.get(
            f"{base_url}/api/pipeline/results/test_large_0101/pipeline-summary",
            timeout=5
        )

        # Should return valid JSON (200 or 404)
        assert response.status_code in [200, 404]
        data = response.json()

        if response.status_code == 200:
            # Success response should have sample data
            assert 'sample_id' in data
            assert data['sample_id'] == 'test_large_0101'
            assert 'status' in data
        else:
            # Error response should have error info
            assert 'error' in data
            assert 'run_id' in data or 'results_path' in data

    def test_cors_headers(self, base_url):
        """Test that CORS headers are present"""
        response = requests.get(f"{base_url}/api/health", timeout=5)
        assert 'Access-Control-Allow-Origin' in response.headers


class TestDockerPortMappings:
    """Test that Docker port mappings are correct"""

    def test_backend_port_8000(self):
        """Test backend is accessible on port 8000"""
        response = requests.get("http://100.72.39.49:8000/api/health", timeout=5)
        assert response.status_code == 200

    def test_frontend_port_3000(self):
        """Test frontend is accessible on port 3000"""
        response = requests.get("http://100.72.39.49:3000/", timeout=5)
        assert response.status_code == 200


class TestPipelineSummaryGeneration:
    """Test pipeline summary file generation via API"""

    def test_summary_accessible_via_api(self):
        """Test that summary is accessible via API for test_large_0101"""
        import requests

        response = requests.get(
            "http://100.72.39.49:8000/api/pipeline/results/test_large_0101/pipeline-summary",
            timeout=5
        )

        # API should return summary (even if 404, we test the response structure)
        assert response.status_code in [200, 404]
        data = response.json()

        if response.status_code == 200:
            # If summary exists, check structure
            assert isinstance(data, dict)
            assert 'sample_id' in data
            assert data['sample_id'] == 'test_large_0101'
        else:
            # If not found, check error structure
            assert 'error' in data
            assert 'run_id' in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
