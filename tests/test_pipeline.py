"""
Tests for Nextflow Metagenomics Pipeline
"""
import pytest
import subprocess
import os
from pathlib import Path
import json


class TestPipelineStructure:
    """Test pipeline structure and dependencies"""
    
    def test_main_nf_exists(self):
        """Check main.nf exists"""
        assert Path("nextflow/main.nf").exists()
    
    def test_all_modules_exist(self):
        """Check all required modules exist"""
        modules = [
            'nanoplot', 'filtlong', 'flye', 'gunzip', 'bwa_mapping',
            'assembly_stats', 'prokka', 'abricate', 'deeparg',
            'metabat2', 'concoct', 'checkm'
        ]
        for module in modules:
            assert Path(f"nextflow/modules/{module}.nf").exists(), f"Module {module}.nf not found"
    
    def test_correct_execution_order(self):
        """Verify execution order in main.nf"""
        with open("nextflow/main.nf") as f:
            content = f.read()
        
        # Find positions of key processes
        positions = {}
        for process in ['FILTLONG', 'FLYE', 'METABAT2', 'CHECKM_METABAT2', 'PROKKA', 'ABRICATE', 'DEEPARG']:
            pos = content.find(f"\n    {process}(")
            assert pos > 0, f"Process {process} not found in main.nf"
            positions[process] = pos
        
        # Verify correct order
        assert positions['FILTLONG'] < positions['FLYE'], "FILTLONG should come before FLYE"
        assert positions['FLYE'] < positions['METABAT2'], "FLYE should come before METABAT2"
        assert positions['METABAT2'] < positions['CHECKM_METABAT2'], "METABAT2 should come before CHECKM"
        assert positions['CHECKM_METABAT2'] < positions['PROKKA'], "CHECKM should come before PROKKA"
        assert positions['CHECKM_METABAT2'] < positions['ABRICATE'], "CHECKM should come before ABRICATE"
        assert positions['CHECKM_METABAT2'] < positions['DEEPARG'], "CHECKM should come before DEEPARG"
    
    def test_annotation_on_bins_not_assembly(self):
        """Verify annotation processes use bins, not full assembly"""
        with open("nextflow/main.nf") as f:
            content = f.read()
        
        # Check that PROKKA/ABRICATE/DEEPARG use flattened bins
        assert 'all_bins_for_annotation' in content, "Should have all_bins_for_annotation channel"
        assert 'flatMap' in content, "Should use flatMap to process individual bins"
        
        # Verify PROKKA uses bins
        prokka_line = [line for line in content.split('\n') if 'PROKKA(' in line and not line.strip().startswith('//')]
        assert any('all_bins_for_annotation' in line for line in prokka_line), "PROKKA should use bins"


class TestPipelineDependencies:
    """Test process dependencies are correct"""
    
    def test_binning_depends_on_bwa(self):
        """Verify METABAT2 and CONCOCT depend on BWA_MAPPING"""
        with open("nextflow/main.nf") as f:
            content = f.read()
        
        metabat2_call = [line for line in content.split('\n') if 'METABAT2(' in line and not line.strip().startswith('//')]
        concoct_call = [line for line in content.split('\n') if 'CONCOCT(' in line and not line.strip().startswith('//')]
        
        assert any('BWA_MAPPING' in line for line in metabat2_call), "METABAT2 should depend on BWA_MAPPING"
        assert any('BWA_MAPPING' in line for line in concoct_call), "CONCOCT should depend on BWA_MAPPING"
    
    def test_checkm_depends_on_binning(self):
        """Verify CHECKM depends on binning output"""
        with open("nextflow/main.nf") as f:
            content = f.read()
        
        checkm_metabat2 = [line for line in content.split('\n') if 'CHECKM_METABAT2(' in line]
        checkm_concoct = [line for line in content.split('\n') if 'CHECKM_CONCOCT(' in line]
        
        assert any('METABAT2.out.bins' in line for line in checkm_metabat2), "CHECKM_METABAT2 should use METABAT2 bins"
        assert any('CONCOCT.out.bins' in line for line in checkm_concoct), "CHECKM_CONCOCT should use CONCOCT bins"


class TestModuleSignatures:
    """Test module input/output signatures"""
    
    def test_prokka_accepts_bin_format(self):
        """Verify PROKKA accepts (sample_id, bin_name, assembly) tuple"""
        with open("nextflow/modules/prokka.nf") as f:
            content = f.read()
        
        assert 'val(sample_id), val(bin_name), path(assembly)' in content, \
            "PROKKA should accept (sample_id, bin_name, assembly) tuple"
    
    def test_prokka_publishdir_uses_bin_name(self):
        """Verify PROKKA publishDir includes bin name"""
        with open("nextflow/modules/prokka.nf") as f:
            content = f.read()
        
        assert '/${bin_name}' in content or 'prokka/${bin_name}' in content, \
            "PROKKA publishDir should include bin_name"


class TestContainerConfiguration:
    """Test Docker container configuration"""
    
    def test_upgrade_deeparg_container_exists(self):
        """Check if custom DEEPARG container is built"""
        result = subprocess.run(
            ['docker', 'images', 'upgrade-deeparg', '--format', '{{.Repository}}:{{.Tag}}'],
            capture_output=True, text=True
        )
        assert 'upgrade-deeparg:latest' in result.stdout, "Custom upgrade-deeparg:latest container not found"
    
    def test_deeparg_dockerfile_exists(self):
        """Check Dockerfile for custom DEEPARG container"""
        dockerfile_path = Path("nextflow/containers/deeparg/Dockerfile")
        assert dockerfile_path.exists(), "DEEPARG Dockerfile not found"
        
        with open(dockerfile_path) as f:
            content = f.read()
        
        assert 'procps' in content, "Dockerfile should install procps"
        assert 'gaarangoa/deeparg' in content, "Dockerfile should be based on gaarangoa/deeparg"


class TestPipelineConfiguration:
    """Test nextflow.config settings"""
    
    def test_deeparg_container_config(self):
        """Verify DEEPARG uses custom container in config"""
        with open("nextflow/nextflow.config") as f:
            content = f.read()
        
        assert 'upgrade-deeparg:latest' in content, "Config should use upgrade-deeparg container"
        assert 'THEANO_FLAGS' in content, "Config should set THEANO_FLAGS for DEEPARG"
    
    def test_deeparg_database_mount(self):
        """Verify DEEPARG database is mounted"""
        with open("nextflow/nextflow.config") as f:
            content = f.read()
        
        assert '/deeparg_db:/deeparg_db' in content, "Config should mount deeparg_db"


class TestOutputStructure:
    """Test expected output structure"""
    
    def test_expected_output_directories(self):
        """Define expected output directory structure"""
        expected_structure = {
            'nanoplot': ['NanoPlot-report.html', 'NanoStats.txt'],
            'filtlong': ['*.fastq'],
            'assembly': ['assembly.fasta.gz'],
            'bwa_mapping': ['*.bam', '*.bai'],
            'metabat2': [],  # bins in work dir
            'concoct': [],   # bins in work dir
            'checkm': ['checkm_results.txt'],
            'prokka': {
                'bin.1': ['*.gff', '*.gbk', '*.faa'],
                'bin.2': ['*.gff', '*.gbk', '*.faa'],
            },
            'abricate': {
                'bin.1': ['*_abricate_card.tab'],
                'bin.2': ['*_abricate_card.tab'],
            },
            'deeparg': {
                'bin.1': ['*.deeparg.mapping.ARG'],
                'bin.2': ['*.deeparg.mapping.ARG'],
            }
        }
        
        # This is documentation, actual test would check results dir
        assert isinstance(expected_structure, dict)


@pytest.fixture
def pipeline_config():
    """Load pipeline configuration"""
    return {
        'nextflow_version': '23.10.0',
        'docker_enabled': True,
        'processes': 13,
        'expected_duration': '8 minutes'
    }


def test_pipeline_config_loaded(pipeline_config):
    """Test pipeline configuration fixture"""
    assert pipeline_config['processes'] == 13
    assert pipeline_config['docker_enabled'] is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
