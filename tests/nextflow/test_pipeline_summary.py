"""
Test PIPELINE_SUMMARY process and empty channel handling
"""
import pytest
from pathlib import Path


class TestPipelineSummaryProcess:
    """Test PIPELINE_SUMMARY process behavior"""

    @pytest.fixture(scope="class")
    def main_nf_path(self):
        """Get path to main.nf"""
        return Path("/home/nicolaedrabcinski/upgrade/nextflow/main.nf")

    @pytest.fixture(scope="class")
    def pipeline_summary_path(self):
        """Get path to pipeline_summary.nf module"""
        return Path("/home/nicolaedrabcinski/upgrade/nextflow/modules/pipeline_summary.nf")

    def test_pipeline_summary_module_exists(self, pipeline_summary_path):
        """Test that pipeline_summary.nf module exists"""
        assert pipeline_summary_path.exists(), "pipeline_summary.nf module not found"
        assert pipeline_summary_path.is_file(), "pipeline_summary.nf is not a file"

    def test_pipeline_summary_has_empty_channel_protection(self, main_nf_path):
        """Test that main.nf has protection against empty channels for PIPELINE_SUMMARY"""
        content = main_nf_path.read_text()

        # Should have ifEmpty or filter to prevent InterruptedException
        assert '.ifEmpty' in content or '.filter' in content, \
            "No empty channel protection found in main.nf"

        # Check specific protection for results_ch/summary_input_ch
        has_protection = (
            'ifEmpty([])' in content or
            'filter { it.size() > 0 }' in content or
            'filter { it != null }' in content
        )

        assert has_protection, \
            "No protection against empty channels for PIPELINE_SUMMARY found"

    def test_pipeline_summary_not_commented_out(self, main_nf_path):
        """Test that PIPELINE_SUMMARY is not commented out"""
        content = main_nf_path.read_text()

        # Should have active PIPELINE_SUMMARY call
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'PIPELINE_SUMMARY' in line and 'summary' in line.lower():
                # Check if line is commented
                stripped = line.strip()
                if stripped.startswith('PIPELINE_SUMMARY('):
                    assert not stripped.startswith('//'), \
                        f"PIPELINE_SUMMARY is commented out at line {i+1}"
                    return

        pytest.fail("No active PIPELINE_SUMMARY call found in main.nf")

    def test_pipeline_summary_has_triple_quote_fix(self, pipeline_summary_path):
        """Test that pipeline_summary.nf has the triple quote bug fixed"""
        content = pipeline_summary_path.read_text()

        # Should NOT have triple quotes in replace() calls
        assert "value.replace(',', ''')" not in content, \
            "Triple quote bug still present in pipeline_summary.nf"

        # Should have correct double quotes
        assert "value.replace(',', '')" in content, \
            "Correct quote syntax not found in pipeline_summary.nf"

    def test_pipeline_summary_publishdir(self, pipeline_summary_path):
        """Test that PIPELINE_SUMMARY publishes to 00_summary"""
        content = pipeline_summary_path.read_text()

        # Should publish to 00_summary directory
        assert 'publishDir' in content, "No publishDir directive found"
        assert '00_summary' in content, "PIPELINE_SUMMARY doesn't publish to 00_summary/"

    def test_results_channel_mapping(self, main_nf_path):
        """Test that results_ch properly maps sample_id and results directory"""
        content = main_nf_path.read_text()

        # Should have results_ch defined
        assert 'results_ch' in content, "results_ch not found in main.nf"

        # Should map to params.outdir
        assert 'params.outdir' in content, "results_ch doesn't use params.outdir"


class TestPipelineSummaryIntegration:
    """Integration tests for PIPELINE_SUMMARY with actual data"""

    def test_summary_json_structure_when_exists(self):
        """Test summary JSON has correct structure when it exists"""
        import json
        import subprocess

        # Check if test_large_0101 summary exists in container
        result = subprocess.run(
            ['docker', 'exec', 'upgrade_rq_worker', 'cat',
             '/results/test_large_0101/00_summary/test_large_0101_summary.json'],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            # Summary exists, validate structure
            data = json.loads(result.stdout)
            assert isinstance(data, dict)
            assert 'sample_id' in data
            assert 'status' in data
            assert data['sample_id'] == 'test_large_0101'
        else:
            # Summary doesn't exist yet, skip
            pytest.skip("Summary file not yet generated for test_large_0101")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
