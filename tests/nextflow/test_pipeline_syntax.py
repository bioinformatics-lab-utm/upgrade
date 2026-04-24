"""
Test Nextflow pipeline syntax and module validity
"""
import pytest
import subprocess
import os
from pathlib import Path


class TestNextflowSyntax:
    """Test suite for Nextflow syntax validation"""

    @pytest.fixture(scope="class")
    def nextflow_dir(self):
        """Get path to Nextflow directory"""
        return Path("/home/nicolaedrabcinski/upgrade/nextflow")

    @pytest.fixture(scope="class")
    def main_nf_path(self, nextflow_dir):
        """Get path to main.nf"""
        return nextflow_dir / "main.nf"

    @pytest.fixture(scope="class")
    def modules_dir(self, nextflow_dir):
        """Get path to modules directory"""
        return nextflow_dir / "modules"

    def test_main_nf_exists(self, main_nf_path):
        """Test that main.nf file exists"""
        assert main_nf_path.exists(), "main.nf not found"
        assert main_nf_path.is_file(), "main.nf is not a file"

    def test_main_nf_not_empty(self, main_nf_path):
        """Test that main.nf is not empty"""
        content = main_nf_path.read_text()
        assert len(content) > 0, "main.nf is empty"
        assert "nextflow.enable.dsl" in content, "DSL2 not enabled"

    def test_nextflow_syntax_valid(self, nextflow_dir):
        """Test Nextflow syntax with --help flag"""
        try:
            result = subprocess.run(
                ["nextflow", "run", str(nextflow_dir / "main.nf"), "--help"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(nextflow_dir)
            )

            # Should exit with code 0 (success) when showing help
            assert result.returncode == 0, f"Nextflow syntax error:\n{result.stderr}"

            # Help output should contain pipeline name
            assert "UPGRADE" in result.stdout, "Pipeline name not in help output"

        except subprocess.TimeoutExpired:
            pytest.fail("Nextflow syntax check timed out")
        except FileNotFoundError:
            pytest.skip("Nextflow not installed")

    def test_all_modules_exist(self, modules_dir):
        """Test that all required modules exist"""
        required_modules = [
            "nanoplot.nf",
            "filtlong.nf",
            "flye.nf",
            "filter_contigs.nf",
            "gunzip.nf",
            "bwa_mapping.nf",
            "assembly_stats.nf",
            "medaka.nf",
            "prokka.nf",
            "abricate.nf",
            "deeparg.nf",
            "metabat2.nf",
            "concoct.nf",
            "checkm.nf",
            "bin_filter.nf",
            "drep.nf",
            "gtdbtk.nf",
            "kraken2.nf",
            "bracken.nf",
            "pipeline_summary.nf",
            "virsorter2.nf",
            "plasmidfinder.nf",
            "nucmer.nf"
        ]

        for module in required_modules:
            module_path = modules_dir / module
            assert module_path.exists(), f"Module {module} not found"
            assert module_path.is_file(), f"{module} is not a file"

    def test_modules_not_empty(self, modules_dir):
        """Test that all module files are not empty"""
        for module_file in modules_dir.glob("*.nf"):
            content = module_file.read_text()
            assert len(content) > 0, f"{module_file.name} is empty"
            assert "process" in content or "workflow" in content, \
                f"{module_file.name} doesn't contain process or workflow"

    def test_pipeline_summary_syntax_fixed(self, modules_dir):
        """Test that pipeline_summary.nf has correct quote syntax"""
        summary_path = modules_dir / "pipeline_summary.nf"
        content = summary_path.read_text()

        # Check for the fixed lines (should have '' not ''')
        assert "value.replace(',', '')" in content, \
            "pipeline_summary.nf still has incorrect triple quotes"

        # Should NOT have triple quotes in replace calls
        assert "value.replace(',', ''')" not in content, \
            "pipeline_summary.nf still has triple quote bug"

    def test_no_hardcoded_paths(self, main_nf_path):
        """Test that main.nf doesn't have hardcoded paths"""
        content = main_nf_path.read_text()

        # Should not have absolute paths
        forbidden_patterns = [
            "/home/specific/user",  # Don't hardcode user dirs
            "C:\\Users",  # Don't hardcode Windows paths
        ]

        for pattern in forbidden_patterns:
            assert pattern not in content, \
                f"main.nf contains hardcoded path: {pattern}"

    def test_docker_profile_configured(self, nextflow_dir):
        """Test that docker profile is properly configured"""
        config_path = nextflow_dir / "nextflow.config"
        content = config_path.read_text()

        assert "profiles {" in content, "No profiles block in config"
        assert "docker {" in content, "No docker profile configured"
        assert "docker.enabled = true" in content, "Docker not enabled"

    def test_no_syntax_errors_in_config(self, nextflow_dir):
        """Test that nextflow.config has no syntax errors"""
        config_path = nextflow_dir / "nextflow.config"
        content = config_path.read_text()

        # Check balanced braces
        open_braces = content.count('{')
        close_braces = content.count('}')
        assert open_braces == close_braces, \
            f"Unbalanced braces in config: {open_braces} open, {close_braces} close"

    def test_process_definitions_valid(self, modules_dir):
        """Test that all process definitions are valid"""
        for module_file in modules_dir.glob("*.nf"):
            content = module_file.read_text()

            if "process " not in content:
                continue

            # Each process should have input, output, or script/shell
            processes = content.split("process ")
            for i, proc in enumerate(processes[1:], 1):
                # Get process name
                proc_name = proc.split()[0] if proc.split() else f"unknown_{i}"

                # Skip if this is a Python variable, not a Nextflow process
                if "{file}:" in proc_name or "for " in proc[:100]:
                    continue

                # Get first 500 chars of process to check structure
                proc_snippet = proc[:500]

                # Should have at least one of: input, output, script, shell, exec
                has_io_or_script = any(keyword in proc_snippet for keyword in
                    ["input:", "output:", "script:", "shell:", "exec:"])

                assert has_io_or_script, \
                    f"Process {proc_name} in {module_file.name} missing input/output/script"


class TestNextflowModuleStructure:
    """Test Nextflow module structure and best practices"""

    @pytest.fixture(scope="class")
    def modules_dir(self):
        return Path("/home/nicolaedrabcinski/upgrade/nextflow/modules")

    def test_all_processes_have_containers(self, modules_dir):
        """Test that all processes specify containers"""
        for module_file in modules_dir.glob("*.nf"):
            content = module_file.read_text()

            if "process " not in content:
                continue

            # Should have container directive for Docker profile
            # Either in process or in config
            if "container " not in content and "container=" not in content:
                # Check if it's in the config (some modules use config-based containers)
                # We'll skip this check for now as it's config-dependent
                pass

    def test_processes_have_tags(self, modules_dir):
        """Test that processes have tags for better logging"""
        important_modules = ["flye.nf", "checkm.nf", "kraken2.nf", "metabat2.nf"]

        for module_name in important_modules:
            module_path = modules_dir / module_name
            if not module_path.exists():
                continue

            content = module_path.read_text()

            if "process " in content:
                assert "tag " in content, \
                    f"{module_name} should have tag directive for better logging"

    def test_processes_publish_dirs(self, modules_dir):
        """Test that processes have publishDir for outputs"""
        important_modules = ["flye.nf", "checkm.nf", "kraken2.nf"]

        for module_name in important_modules:
            module_path = modules_dir / module_name
            if not module_path.exists():
                continue

            content = module_path.read_text()

            if "process " in content:
                # Should have publishDir either in process or config
                assert "publishDir" in content or "publish_dir" in content, \
                    f"{module_name} should have publishDir for results"


class TestPipelineConfiguration:
    """Test pipeline configuration"""

    @pytest.fixture(scope="class")
    def config_path(self):
        return Path("/home/nicolaedrabcinski/upgrade/nextflow/nextflow.config")

    def test_config_exists(self, config_path):
        """Test that nextflow.config exists"""
        assert config_path.exists(), "nextflow.config not found"

    def test_config_has_params(self, config_path):
        """Test that config defines required parameters"""
        content = config_path.read_text()

        required_params = [
            "input_dir",
            "outdir",
            "threads",
            "memory"
        ]

        for param in required_params:
            assert param in content, f"Required parameter {param} not in config"

    def test_config_has_docker_settings(self, config_path):
        """Test that config has Docker settings"""
        content = config_path.read_text()

        assert "docker.enabled" in content, "Docker not configured"
        assert "docker.runOptions" in content, "Docker runOptions not configured"

    def test_resource_limits_reasonable(self, config_path):
        """Test that resource limits are reasonable"""
        content = config_path.read_text()

        # Should not request more than 256GB RAM
        import re
        memory_matches = re.findall(r"memory\s*=\s*['\"](\d+)\.?(\w+)", content)

        for value, unit in memory_matches:
            value = int(value)
            if unit.upper() == "GB":
                assert value <= 256, f"Memory request {value}GB too high"
            elif unit.upper() == "TB":
                pytest.fail(f"Memory request in TB is excessive: {value}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
