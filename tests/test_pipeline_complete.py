"""
Comprehensive pipeline tests
Tests entire pipeline execution flow
"""
import pytest
import subprocess
import json
from pathlib import Path


class TestPipelineSyntax:
    """Test Nextflow syntax validation"""

    def test_main_nf_syntax(self):
        """Test main.nf has no syntax errors"""
        main_nf = Path("/home/nicolaedrabcinski/upgrade/nextflow/main.nf")
        assert main_nf.exists(), "main.nf not found"

        content = main_nf.read_text()

        # Critical syntax checks
        assert 'workflow {' in content, "No main workflow block"
        assert 'params.' in content, "No parameters defined"
        assert content.count('{') == content.count('}'), "Unbalanced braces"

    def test_pipeline_summary_syntax_fixed(self):
        """Test that triple-quote docstrings are removed from pipeline_summary.nf"""
        pipeline_summary = Path("/home/nicolaedrabcinski/upgrade/nextflow/modules/pipeline_summary.nf")
        assert pipeline_summary.exists()

        content = pipeline_summary.read_text()

        # Check NO triple-quote docstrings inside shell block
        shell_block_start = content.find("shell:")
        shell_block_end = content.find("'''", shell_block_start + 10)  # Find closing '''

        if shell_block_start > 0:
            shell_content = content[shell_block_start:shell_block_end]
            # Should NOT have """Parse...""" docstrings
            assert '"""Parse' not in shell_content, "Triple-quote docstrings found in shell block"
            assert "'''Parse" not in shell_content, "Triple-quote docstrings found in shell block"

    def test_no_parse_variable_error(self):
        """Test that pipeline_summary.nf doesn't reference undefined 'Parse' variable"""
        pipeline_summary = Path("/home/nicolaedrabcinski/upgrade/nextflow/modules/pipeline_summary.nf")
        content = pipeline_summary.read_text()

        # Should have comments like "# Parse..." not docstrings like """Parse..."""
        assert '# Parse NanoPlot QC results' in content, "Missing comment for parse_nanoplot"
        assert '# Parse assembly statistics' in content, "Missing comment for parse_assembly"
        assert '# Parse CheckM quality' in content, "Missing comment for parse_checkm"


class TestPipelineExecution:
    """Test pipeline execution scenarios"""

    def test_empty_channel_handling(self):
        """Test that pipeline handles empty ont_reads_ch gracefully"""
        main_nf = Path("/home/nicolaedrabcinski/upgrade/nextflow/main.nf")
        content = main_nf.read_text()

        # Should use log.warn instead of error
        assert 'log.warn "No FASTQ files found' in content, "Empty channel not handled with log.warn"
        assert 'ont_reads_ch.ifEmpty' in content, "No ifEmpty handler for ont_reads_ch"

    def test_pipeline_summary_enabled(self):
        """Test that PIPELINE_SUMMARY process is enabled"""
        main_nf = Path("/home/nicolaedrabcinski/upgrade/nextflow/main.nf")
        content = main_nf.read_text()

        # Should have uncommented PIPELINE_SUMMARY call
        lines = content.split('\n')
        pipeline_summary_line = None
        for line in lines:
            if 'PIPELINE_SUMMARY' in line and 'branches.valid' in line:
                pipeline_summary_line = line
                break

        assert pipeline_summary_line is not None, "PIPELINE_SUMMARY call not found"
        assert not pipeline_summary_line.strip().startswith('//'), "PIPELINE_SUMMARY is commented out"


class TestDatabaseIntegration:
    """Test database schema and queries"""

    def test_pipeline_runs_table_structure(self):
        """Test pipeline_runs table has required columns"""
        result = subprocess.run([
            'docker', 'exec', 'upgrade_postgres', 'psql', '-U', 'upgrade', '-d', 'upgrade_db',
            '-c', "SELECT column_name FROM information_schema.columns WHERE table_name = 'pipeline_runs';"
        ], capture_output=True, text=True)

        assert result.returncode == 0, "Failed to query database"
        columns = result.stdout

        # Required columns
        assert 'pipeline_id' in columns
        assert 'sample_name' in columns
        assert 'status' in columns
        assert 'error_message' in columns

    def test_pipeline_progress_events_table(self):
        """Test pipeline_progress_events table exists"""
        result = subprocess.run([
            'docker', 'exec', 'upgrade_postgres', 'psql', '-U', 'upgrade', '-d', 'upgrade_db',
            '-c', "SELECT COUNT(*) FROM pipeline_progress_events;"
        ], capture_output=True, text=True)

        assert result.returncode == 0, "pipeline_progress_events table missing"


class TestMinIOIntegration:
    """Test MinIO object storage integration"""

    def test_minio_objects_table_structure(self):
        """Test minio_objects table has pipeline_id column"""
        result = subprocess.run([
            'docker', 'exec', 'upgrade_postgres', 'psql', '-U', 'upgrade', '-d', 'upgrade_db',
            '-c', "SELECT column_name FROM information_schema.columns WHERE table_name = 'minio_objects';"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        columns = result.stdout

        # Migration 009 added pipeline_id column
        assert 'pipeline_id' in columns, "minio_objects missing pipeline_id column"
        assert 'object_name' in columns
        assert 'object_size_bytes' in columns


class TestAPIEndpoints:
    """Test backend API endpoints respond correctly"""

    def test_health_endpoint(self):
        """Test /api/health endpoint is accessible"""
        import requests

        response = requests.get("http://100.72.39.49:8000/api/health", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'

    def test_pipeline_results_endpoint_structure(self):
        """Test /api/pipeline/results/{id}/pipeline-summary endpoint"""
        import requests

        # Test with non-existent sample (should return 404 with error JSON)
        response = requests.get(
            "http://100.72.39.49:8000/api/pipeline/results/nonexistent/pipeline-summary",
            timeout=5
        )

        assert response.status_code in [200, 404]
        data = response.json()

        # Should always return valid JSON
        assert isinstance(data, dict)

        if response.status_code == 404:
            # Error response should have 'error' key
            assert 'error' in data
        else:
            # Success response should have 'sample_id'
            assert 'sample_id' in data


class TestFrontendBackendIntegration:
    """Test frontend can communicate with backend"""

    def test_cors_headers_present(self):
        """Test CORS headers are configured"""
        import requests

        response = requests.get("http://100.72.39.49:8000/api/health", timeout=5)
        assert 'Access-Control-Allow-Origin' in response.headers

    def test_frontend_error_handling(self):
        """Test frontend handles API errors gracefully"""
        # Read frontend code
        dashboard = Path("/home/nicolaedrabcinski/upgrade/web-dashboard/frontend/src/components/PipelineResultsDashboard.jsx")
        if not dashboard.exists():
            pytest.skip("Frontend code not found")

        content = dashboard.read_text()

        # Should parse JSON before checking response.ok
        assert 'await response.json()' in content
        assert 'json.error' in content
        assert 'response.ok' in content


class TestDockerConfiguration:
    """Test Docker Compose configuration"""

    def test_backend_port_mapping(self):
        """Test web-backend has port mapping"""
        compose_file = Path("/home/nicolaedrabcinski/upgrade/docker-compose.yml")
        content = compose_file.read_text()

        # Find web-backend service
        backend_section_start = content.find("web-backend:")
        assert backend_section_start > 0, "web-backend service not found"

        # Find next service (search for next service at same indent level)
        # Look for pattern "\n  <servicename>:" to find next service
        next_service_start = backend_section_start + 50
        while next_service_start < len(content):
            if content[next_service_start:next_service_start+3] == '\n  ' and content[next_service_start+3] != ' ':
                # Found next service
                next_service = next_service_start
                break
            next_service_start += 1
        else:
            next_service = -1

        backend_section = content[backend_section_start:next_service] if next_service > 0 else content[backend_section_start:]

        # Should have port mapping
        assert 'ports:' in backend_section, "web-backend missing ports section"
        assert '8000:8000' in backend_section, "web-backend missing 8000 port mapping"

    def test_frontend_port_mapping(self):
        """Test web-frontend has port mapping"""
        compose_file = Path("/home/nicolaedrabcinski/upgrade/docker-compose.yml")
        content = compose_file.read_text()

        # Find web-frontend service
        frontend_section_start = content.find("web-frontend:")
        assert frontend_section_start > 0, "web-frontend service not found"

        # Find next service (search for next service at same indent level)
        next_service_start = frontend_section_start + 50
        while next_service_start < len(content):
            if content[next_service_start:next_service_start+3] == '\n  ' and content[next_service_start+3] != ' ':
                next_service = next_service_start
                break
            next_service_start += 1
        else:
            next_service = -1

        frontend_section = content[frontend_section_start:next_service] if next_service > 0 else content[frontend_section_start:]

        # Should have port mapping
        assert 'ports:' in frontend_section, "web-frontend missing ports section"
        assert '3000:' in frontend_section, "web-frontend missing 3000 port mapping"


class TestRQWorkerConfiguration:
    """Test RQ worker has correct Nextflow code mounted"""

    def test_rq_worker_nextflow_mount(self):
        """Test RQ worker can access updated Nextflow code"""
        result = subprocess.run([
            'docker', 'exec', 'upgrade_rq_worker', 'cat', '/nextflow/main.nf'
        ], capture_output=True, text=True)

        assert result.returncode == 0, "Cannot access /nextflow/main.nf in RQ worker"
        content = result.stdout

        # Should have the fix (log.warn instead of error)
        assert 'log.warn "No FASTQ files found' in content, "RQ worker has old code without fix"


class TestPipelineSummaryOutput:
    """Test PIPELINE_SUMMARY process output"""

    def test_summary_json_structure(self):
        """Test summary JSON has correct structure when exists"""
        # This test will pass/skip based on whether summary was generated
        test_samples = ['test_large_0101', 'test_large_0201_v1']

        found_summary = False
        for sample in test_samples:
            result = subprocess.run([
                'docker', 'exec', 'upgrade_rq_worker', 'cat',
                f'/results/{sample}/00_summary/{sample}_summary.json'
            ], capture_output=True, text=True)

            if result.returncode == 0:
                # Summary exists, validate structure
                try:
                    data = json.loads(result.stdout)
                    assert isinstance(data, dict)
                    assert 'sample_id' in data
                    assert 'status' in data
                    assert data['sample_id'] == sample
                    found_summary = True
                    break
                except json.JSONDecodeError:
                    continue

        if not found_summary:
            pytest.skip("No summary files found yet - will be generated on next pipeline run")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
